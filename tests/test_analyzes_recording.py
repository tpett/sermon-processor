import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from steps._asr import transcribes_for

from sermon.analysis.diarizes_audio import DiarizationUnavailable
from sermon.analysis.io import reads_json, reads_model_segments, writes_json, writes_model_segments
from sermon.analysis.proposes_from_transcript import BindsCorpusRoots, DividesByReasoning
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


def queued_analyze(store, recording, max_attempts=5):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    return store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=max_attempts,
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
        divides=divides_into_nothing_publishable,
    )


def test_runs_analyze_job_picks_the_queued_job(store, roots):
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
        divides=divides_into_nothing_publishable,
    )()
    job = store.lists(Job, recording_id=recording.recording_id, kind="analyze")[0]
    assert job.state == "succeeded"
    assert job.started_at == FROZEN


def test_state_log_is_downloaded_analyzing_awaiting_review(store, roots):
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


def test_two_segments_have_distinct_punch_points_and_classifications(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert {(s.classification, s.punch_in_seconds, s.punch_out_seconds) for s in segments} == {
        ("lesson", 60.0, 3300.0),
        ("sermon", 5400.0, 10800.0),
    }


def test_each_segment_has_a_proposal_with_confidence(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        proposal = store.lists(Proposal, segment_id=segment.segment_id)[0]
        assert proposal.classification_confidence == "high"
        assert proposal.boundary_confidence == "medium"


def test_a_notification_is_sent_when_segments_are_proposed(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    sent = []
    analyzes(store, [], sent)(recording)
    notifications = store.lists(Notification, recording_id=recording.recording_id)
    assert len(notifications) == 1
    assert [item.notification_id for item in sent] == [notifications[0].notification_id]
    assert notifications[0].state == "delivered"
    assert notifications[0].kind == "segment_proposed"
    assert notifications[0].recipient == "reviewer"


def test_stages_run_in_gherkin_order_and_blocking_iterates(store, roots):
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


def test_approving_one_segment_does_not_mutate_the_other(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    analyzes(store, [], [])(recording)
    lesson, sermon = store.lists(Segment, recording_id=recording.recording_id)
    store.saves(replace(lesson, state="approved"))
    assert store.loads(Segment, sermon.segment_id).state == "proposed"


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
        **{"stages": lambda _name: None, "divides": divides_into_nothing_publishable} | fields,
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
    told = store.lists(Notification, recording_id=recording.recording_id)
    assert [(item.kind, item.state) for item in told] == [("nothing_publishable", "suppressed")]
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
    queued_analyze(store, recording, max_attempts=1)

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


def test_a_blocking_failure_is_logged_under_blocking(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording, max_attempts=1)

    def divides_badly(doc):
        raise RuntimeError("the divider broke")

    walks(store, [], divides=divides_badly)()
    failures = [
        entry.error
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state == "analysis_failed"
    ]
    assert failures == ["blocking: the divider broke"]


def a_recording_on_disk(store, tmp_path):
    recording = downloaded_recording()
    local = replace(recording, local_path=str(layout.source_path(recording)))
    source = tmp_path / local.local_path
    source.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ac", "1", str(source)],
        check=True,
        capture_output=True,
    )
    return store.saves(local)


def blocks_the_artifact(tmp_path, recording, kind):
    (tmp_path / layout.artifact_path(recording.recording_id, kind)).mkdir(parents=True)


def optional_failures(store, recording):
    return [
        entry.error
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.error and entry.entered_state is None
    ]


@pytest.mark.parametrize(("stage", "kind"), [("waveform", "waveform_peaks"), ("preview", "preview")])
def test_an_optional_stage_whose_work_fails_does_not_fail_the_walk(store, roots, tmp_path, stage, kind):
    recording = a_recording_on_disk(store, tmp_path)
    queued_analyze(store, recording)
    blocks_the_artifact(tmp_path, recording, kind)
    walks(store, [])()
    assert store.lists(Job, recording_id=recording.recording_id)[0].state == "succeeded"
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"
    assert not store.lists(Artifact, recording_id=recording.recording_id, kind=kind)
    assert [error for error in optional_failures(store, recording) if error.startswith(f"{stage}: ")]


def test_the_envelope_stage_records_no_artifact_it_did_not_write(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    walks(store, [])()
    for artifact in store.lists(Artifact, recording_id=recording.recording_id):
        assert store.resolves(artifact).is_file(), artifact.kind


def spoken(*words):
    return {"start": words[0][1], "end": words[-1][2], "text": " ".join(w for w, _, _ in words),
            "words": [{"w": w, "start": start, "end": end} for w, start, end in words]}


OPENS_INSIDE_A_WORD = {
    "recording_id": "recording_20260913_090014",
    "duration": 11520.0,
    "utterances": [
        spoken(("You", 130.0, 130.3), ("may", 130.3, 130.5), ("be", 130.5, 130.6),
               ("seated.", 130.6, 131.0)),
        spoken(("Well,", 151.87, 152.31), ("good", 152.31, 152.75), ("morning.", 152.75, 153.05)),
        spoken(("Please", 154.19, 154.67), ("open", 154.67, 154.99), ("to", 154.99, 155.17),
               ("Hebrews", 155.17, 155.63), ("13.", 155.63, 156.0)),
        spoken(("As", 160.21, 160.69), ("you", 160.69, 160.79), ("do,", 160.79, 160.95)),
        spoken(("In", 3799.0, 3799.5), ("Jesus'", 3799.5, 3800.0), ("name,", 3800.0, 3800.5),
               ("amen.", 3800.5, 3801.0)),
    ],
}

REASONED = {
    "blocks": [
        {"start": 0.0, "end": 140.0, "type": "music", "confidence": 0.9},
        {"start": 140.0, "end": 3805.0, "type": "sermon", "confidence": 0.9},
        {"start": 3805.0, "end": 11520.0, "type": "music", "confidence": 0.9},
    ],
    "model_segments": [
        {"punch_in": 151.9, "punch_out": 3801.5, "classification": "sermon", "confidence": 0.9},
    ],
}


def walks_the_reasoned_opening(store, divides):
    recording = store.saves(downloaded_recording())
    writes_json(store, recording, "transcript", OPENS_INSIDE_A_WORD)
    queued_analyze(store, recording)
    AnalyzesRecording(
        store=store,
        stages=[].append,
        notifies=SendsNotification(store=store, sends=[].append),
        clock=lambda: FROZEN,
        divides=divides,
    )(recording)
    return recording


def test_blocking_keeps_the_reasonings_own_segments_beside_the_blocks(store, roots):
    recording = walks_the_reasoned_opening(store, lambda doc: REASONED)
    assert reads_model_segments(store, recording) == REASONED["model_segments"]


def test_dividing_afresh_with_only_blocks_leaves_no_earlier_answer_behind(store, roots):
    writes_model_segments(store, downloaded_recording(), REASONED["model_segments"])
    recording = walks_the_reasoned_opening(store, lambda doc: REASONED["blocks"])
    assert reads_model_segments(store, recording) == []


def test_keeping_the_reasonings_segments_needs_no_new_kind_of_row(store, roots):
    recording = walks_the_reasoned_opening(store, lambda doc: REASONED)
    kinds = {item.kind for item in store.lists(Artifact, recording_id=recording.recording_id)}
    assert "model_segments" not in kinds


def test_the_reasoning_divider_hands_blocking_its_whole_answer(store, roots):
    recording = walks_the_reasoned_opening(
        store, DividesByReasoning(reasons=lambda doc: REASONED)
    )
    assert reads_model_segments(store, recording) == REASONED["model_segments"]


def test_the_walk_stores_what_the_diarizer_heard(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)
    turns = [{"start": 0.0, "end": 5000.0, "speaker": "S0"}, {"start": 5000.0, "end": 11520.0, "speaker": "S1"}]
    walks(store, [], diarizes=lambda _recording: [dict(turn) for turn in turns])()
    assert reads_json(store, recording, "diarization") == {"turns": turns}
    assert [error for error in optional_failures(store, recording) if error.startswith("diarization")] == []


def test_a_diarizer_that_is_unavailable_leaves_the_walk_carrying_on(store, roots):
    recording = store.saves(downloaded_recording())
    queued_analyze(store, recording)

    def unavailable(_recording):
        raise DiarizationUnavailable("no diarization models are configured")

    walks(store, [], diarizes=unavailable)()
    assert store.lists(Job, recording_id=recording.recording_id)[0].state == "succeeded"
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"
    assert reads_json(store, recording, "diarization") is None
    assert [error for error in optional_failures(store, recording) if error.startswith("diarization")] == [
        "diarization: no diarization models are configured"
    ]
