import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from steps._asr import transcribes_for

from sermon.analysis.proposes_from_transcript import BindsCorpusRoots
from sermon.jobs.analyzes_recording import AnalyzesRecording, CLASS_AND_SERVICE, RunsAnalyzeJob, StageFailed
from sermon.jobs.probes_recording import ProbeResult
from sermon.pipeline import classify, segments
from sermon.sends_notification import SendsNotification
from sermon.store import (
    Artifact,
    ChannelLevel,
    Job,
    LogEntry,
    Notification,
    Proposal,
    Recording,
    Reviewer,
    Segment,
    layout,
    opens_store,
)

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
        transcribes=transcribes_for(store, downloaded_recording()),
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
        transcribes=transcribes_for(store, recording),
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


@pytest.fixture
def roots(tmp_path):
    held = (classify.DATA, classify.PROMPTS, segments.DATA_ROOT)
    layout.diarization_root(tmp_path).mkdir(parents=True, exist_ok=True)
    BindsCorpusRoots(
        corpus_root=layout.corpus_root(tmp_path),
        prompts_root=Path(__file__).resolve().parents[1] / "experiments/prompts",
    )()
    yield
    classify.DATA, classify.PROMPTS, segments.DATA_ROOT = held


def divides_into_nothing_publishable(doc):
    return [{"start": 0.0, "end": doc["duration"], "type": "music", "confidence": 0.9}]


def measures_loudness(recording):
    return ProbeResult(
        duration_seconds=recording.duration_seconds,
        sample_rate=44100,
        channels=1,
        channel_levels=(ChannelLevel(channel=1, rms_db=-30.0),),
        integrated_loudness_lufs=-20.4,
        true_peak_dbtp=-1.2,
    )


def walks(store, sent, **fields):
    return RunsAnalyzeJob(
        store=store,
        notifies=SendsNotification(store=store, sends=sent.append),
        clock=lambda: FROZEN,
        transcribes=transcribes_for(store, downloaded_recording()),
        divides=divides_into_nothing_publishable,
        **{"stages": lambda _name: None} | fields,
    )


def test_a_walk_that_proposes_nothing_fabricates_no_segment(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    sent = []
    walks(store, sent)()
    assert store.lists(Job, recording_id=recording.recording_id)[0].state == "succeeded"
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"
    assert store.lists(Segment, recording_id=recording.recording_id) == []
    assert store.lists(Proposal) == []
    assert store.lists(Notification, recording_id=recording.recording_id) == []
    assert sent == []


def test_what_the_probe_measured_survives_the_end_of_the_walk(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    walks(store, [], measures=measures_loudness)()
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == "awaiting_review"
    assert stored.integrated_loudness_lufs == -20.4
    assert stored.true_peak_dbtp == -1.2
    assert stored.channel_levels == (ChannelLevel(channel=1, rms_db=-30.0),)


def test_what_the_probe_measured_survives_a_failed_walk(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)

    def fails_at_scoring(name):
        if name == "scoring":
            raise StageFailed(name, "scoring failed")

    walks(store, [], measures=measures_loudness, stages=fails_at_scoring)()
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == "analysis_failed"
    assert stored.integrated_loudness_lufs == -20.4
    assert stored.channel_levels == (ChannelLevel(channel=1, rms_db=-30.0),)


def test_a_later_stage_reads_what_the_probe_measured(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)

    def measures_a_shorter_file(item):
        return replace(measures_loudness(item), duration_seconds=10990.0)

    walks(store, [], measures=measures_a_shorter_file)()
    peaks = store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")[0]
    assert json.loads(store.resolves(peaks).read_text())["duration_seconds"] == 10990.0
