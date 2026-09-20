from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.jobs.analyzes_recording import AnalyzesRecording, CLASS_AND_SERVICE, RunsAnalyzeJob
from sermon.sends_notification import SendsNotification
from sermon.store import Job, LogEntry, Notification, Proposal, Recording, Reviewer, Segment, opens_store

FROZEN = datetime(2026, 9, 13, 12, 41, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def downloaded_recording():
    return Recording(
        recording_id="recording_20260913_090014",
        object_key="2026/09/13/recording_20260913_090014.flac",
        state="downloaded",
        started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1,
        duration_seconds=11520.0,
    )


def queued_analyze(store, recording):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    return store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )


def analyzes(store, stages, sent):
    return AnalyzesRecording(
        store=store,
        stages=stages.append,
        notifies=SendsNotification(store=store, sends=sent.append),
        contents=CLASS_AND_SERVICE,
        clock=lambda: FROZEN,
    )


def test_runs_analyze_job_picks_the_queued_job(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    stages = []
    sent = []
    RunsAnalyzeJob(
        store=store,
        stages=stages.append,
        notifies=SendsNotification(store=store, sends=sent.append),
        clock=lambda: FROZEN,
    )()
    job = store.lists(Job, recording_id=recording.recording_id, kind="analyze")[0]
    assert job.state == "succeeded"
    assert job.started_at == FROZEN


def test_state_log_is_downloaded_analyzing_awaiting_review(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == "awaiting_review"
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state is not None
    ]
    assert entered == ["analyzing", "awaiting_review"]


def test_two_segments_have_distinct_punch_points_and_classifications(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert {(s.classification, s.punch_in_seconds, s.punch_out_seconds) for s in segments} == {
        ("lesson", 60.0, 3300.0),
        ("sermon", 5400.0, 10800.0),
    }


def test_each_segment_has_a_proposal_with_confidence(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        proposal = store.lists(Proposal, segment_id=segment.segment_id)[0]
        assert proposal.classification_confidence == "high"
        assert proposal.boundary_confidence == "medium"


def test_a_notification_is_sent_when_segments_are_proposed(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    sent = []
    analyzes(store, [], sent)(recording)
    notifications = store.lists(Notification, recording_id=recording.recording_id)
    assert len(notifications) == 1
    assert sent == notifications
    assert notifications[0].kind == "segment_proposed"
    assert notifications[0].recipient == "reviewer"


def test_stages_run_in_gherkin_order_and_blocking_iterates(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    stages = []
    analyzes(store, stages, [])(recording)
    assert stages == [
        "envelope",
        "probe",
        "waveform",
        "preview",
        "transcription",
        "diarization",
        "blocking",
        "block_classification",
        "blocking",
        "block_classification",
        "summarization",
        "segment_proposal",
        "boundary_refinement",
        "scoring",
    ]


def test_approving_one_segment_does_not_mutate_the_other(store):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    lesson, sermon = store.lists(Segment, recording_id=recording.recording_id)
    store.saves(replace(lesson, state="approved"))
    assert store.loads(Segment, sermon.segment_id).state == "proposed"
