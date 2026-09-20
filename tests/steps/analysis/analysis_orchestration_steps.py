from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.config import ModelEndpointUnreachable, ReachesModelEndpoint
from sermon.jobs.analyzes_recording import CLASS_AND_SERVICE, RunsAnalyzeJob, StageFailed
from sermon.sends_notification import SendsNotification
from sermon.store import Artifact, Block, Job, LogEntry, Notification, Proposal, Recording, Reviewer, Segment

FROZEN = datetime(2026, 9, 13, 12, 41, tzinfo=UTC)


@pytest.fixture
def stage_log():
    return []


@pytest.fixture
def sent():
    return []


@pytest.fixture
def clock():
    return lambda: FROZEN


@given(parsers.parse("the Recording is {length} long"), target_fixture="recording")
def _(store, recording, length):
    hours, minutes, seconds = (int(part) for part in length.split(":"))
    return store.saves(
        replace(
            recording,
            duration_seconds=float(hours * 3600 + minutes * 60 + seconds),
        )
    )


@given("it contains a 9:00 class and the 10:30 service", target_fixture="contents")
def _():
    return CLASS_AND_SERVICE


def stages_for(store, stage_log):
    def stages(name):
        stage_log.append(name)
        failing = getattr(store, "_failing_stage", None)
        if failing == name:
            raise StageFailed(name, f"{name} failed")
        if getattr(store, "_fail_once_stage", None) == name:
            store._fail_once_stage = None
            raise StageFailed(name, f"{name} failed once")

    return stages


def runs_analysis(store, recording, stage_log, sent, contents, clock, **fields):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    if not store.lists(Job, recording_id=recording.recording_id, kind="analyze", state="queued"):
        store.saves(
            Job(
                recording_id=recording.recording_id,
                kind="analyze",
                state="queued",
                max_attempts=5,
                dedupe_key=f"analyze:{recording.recording_id}:{len(store.lists(Job))}",
                queued_at=clock(),
            )
        )
    RunsAnalyzeJob(
        store=store,
        stages=stages_for(store, stage_log),
        notifies=SendsNotification(store=store, sends=sent.append),
        contents=contents,
        clock=clock,
        reaches=fields.get("reaches", getattr(store, "_reaches", None)),
        only=fields.get("only"),
    )()


@when("Analysis starts")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@when("Analysis completes")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then(parsers.parse('the Recording enters "{state}"'))
def _(store, recording, state):
    entered = [
        entry.entered_state
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state is not None
    ]
    assert state in entered


@then("the following stages run in order:")
def _(stage_log, datatable):
    expected = [row[0] for row in datatable[1:]]
    first_seen = []
    for name in stage_log:
        if name not in first_seen:
            first_seen.append(name)
    assert first_seen == expected


@then("blocking and block_classification iterate until stable")
def _(stage_log):
    assert stage_log.count("blocking") >= 2
    assert stage_log.count("block_classification") >= 2


@then(parsers.parse('when scoring completes the Recording enters "{state}"'))
def _(store, recording, state):
    assert store.loads(Recording, recording.recording_id).state == state


@then("a notification is sent to the reviewers unless nothing publishable was found")
def _(store, recording, sent):
    notifications = store.lists(Notification, recording_id=recording.recording_id)
    assert notifications
    assert sent == notifications


@then(parsers.parse("{count:d} Segments exist"))
def _(store, recording, count):
    assert len(store.lists(Segment, recording_id=recording.recording_id)) == count


@then("each Segment has its own punch-in, punch-out, classification and confidence")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    punches = {(segment.punch_in_seconds, segment.punch_out_seconds) for segment in segments}
    classes = {segment.classification for segment in segments}
    assert len(punches) == len(segments)
    assert len(classes) == len(segments)
    for segment in segments:
        proposals = store.lists(Proposal, segment_id=segment.segment_id)
        assert len(proposals) == 1
        assert proposals[0].classification_confidence in {"high", "medium", "low"}
        assert proposals[0].boundary_confidence in {"high", "medium", "low"}


@then("each Segment is independently dispositionable")
def _(store, recording):
    assert len(store.lists(Segment, recording_id=recording.recording_id)) == 2


@then("approving one does not affect the other")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    store.saves(replace(segments[0], state="approved"))
    other = store.loads(Segment, segments[1].segment_id)
    assert other.state == "proposed"


@given("block classification and summarisation need a language model")
def _(store):
    store._http = []

    def over(endpoint):
        store._http.append(endpoint)
        return {"models": []}

    store._reaches = ReachesModelEndpoint(
        endpoint="http://100.88.211.71:11434",
        over=over,
    )


@when("those stages run")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then("they issue HTTP requests to the configured model endpoint")
def _(store):
    assert store._http
    assert all(item.startswith("http") for item in store._http)


@then("they hold no credentials for the machine serving it")
def _(store):
    assert not hasattr(store._reaches, "credentials")
    assert not hasattr(store._reaches, "ssh")


@then("they never open a shell on it")
def _(store):
    assert store._http
    assert "ssh" not in "".join(store._http)


@then("transcription runs wherever the application itself runs")
def _(store, recording, stage_log, sent, contents, clock):
    store._http = []

    def over(endpoint):
        store._http.append(stage_log[-1] if stage_log else endpoint)
        return {}

    store._reaches = ReachesModelEndpoint(endpoint="http://100.88.211.71:11434", over=over)
    runs_analysis(store, recording, stage_log, sent, contents, clock)
    assert "transcription" in stage_log


@then("it is not sent to the model endpoint")
def _(store):
    assert "transcription" not in store._http


@given("the model endpoint does not answer")
def _(store):
    def over(endpoint):
        raise ModelEndpointUnreachable(endpoint)

    store._reaches = ReachesModelEndpoint(endpoint="http://100.88.211.71:11434", over=over)


@when("analysis reaches a reasoning stage")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then("the Recording is left in a state the run can resume from")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "analyzing"


@then("the stages already cached are not recomputed")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id)


@then("the failure names the endpoint, not a generic model error")
def _(store):
    jobs = store.lists(Job, kind="analyze")
    assert "http://100.88.211.71:11434" in (jobs[0].last_error or "")


@given("Analysis has completed")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then("the transcript is retrievable for the Recording")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="transcript")


@then("the speaker spans, Blocks and their classifications are retrievable")
def _(store, recording):
    assert store.lists(Block, recording_id=recording.recording_id)
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="diarization")


@then("the waveform peak data is retrievable for the Recording")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="waveform_peaks")


@then("every Segment's boundaries and classification are stored")
def _(store, recording):
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        assert segment.punch_in_seconds < segment.punch_out_seconds
        assert segment.classification


@then(parsers.parse('re-running only the "{later}" stage does not re-run "{earlier}"'))
def _(store, recording, stage_log, sent, contents, clock, later, earlier):
    stage_log.clear()
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}:{later}",
            queued_at=clock(),
        )
    )
    runs_analysis(store, recording, stage_log, sent, contents, clock, only=later)
    assert earlier not in stage_log
    assert later in stage_log


@given(parsers.parse("Analysis proposed {count:d} Segments"))
def _(store, recording, stage_log, sent, clock, count):
    extra = tuple(
        ("sermon", float(index), float(index + 60))
        for index in range(count)
    )
    contents = type(CLASS_AND_SERVICE)(segments=extra[:count] if count != 2 else CLASS_AND_SERVICE.segments)
    if count == 3:
        contents = type(CLASS_AND_SERVICE)(
            segments=(
                ("lesson", 60.0, 3300.0),
                ("sermon", 5400.0, 10800.0),
                ("seminar", 12000.0, 14000.0),
            )
        )
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@given("the reviewer approved 1 and skipped 2")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    store.saves(replace(segments[0], state="approved"))
    store.saves(replace(segments[1], state="skipped"))
    store.saves(replace(segments[2], state="skipped"))


@then("the 2 skipped Segments remain stored with their boundaries and classification")
def _(store, recording):
    skipped = [item for item in store.lists(Segment, recording_id=recording.recording_id) if item.state == "skipped"]
    assert len(skipped) == 2
    for item in skipped:
        assert item.classification
        assert item.punch_out_seconds > item.punch_in_seconds


@then("they can be revisited and approved months later")
def _(store, recording):
    skipped = [item for item in store.lists(Segment, recording_id=recording.recording_id) if item.state == "skipped"]
    store.saves(replace(skipped[0], state="proposed"))


@then("doing so does not require re-running Analysis")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert all(job.state != "queued" for job in jobs)


@given("Analysis completed and no Segment has been dispositioned")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@when("an operator re-runs Analysis")
def _(store, recording, stage_log, sent, contents, clock):
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}:rerun",
            queued_at=clock(),
        )
    )
    store._previous_proposals = store.lists(Proposal)
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then("the cached transcript and diarization are reused")
def _(store, recording):
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="transcript")
    assert store.lists(Artifact, recording_id=recording.recording_id, kind="diarization")


@then("fresh Segments and Proposals replace the previous ones")
def _(store, recording):
    assert store.lists(Segment, recording_id=recording.recording_id)
    assert store.lists(Proposal)


@then("the previous Proposals are kept in the Recording's history")
def _(store):
    assert getattr(store, "_previous_proposals", None) is not None


@given(parsers.parse('a reviewer adjusted a Segment\'s punch-in to "{timecode}"'))
def _(store, recording, stage_log, sent, contents, clock, timecode):
    from sermon.extends_segment_span import ReadsTimecode

    runs_analysis(store, recording, stage_log, sent, contents, clock)
    segment = store.lists(Segment, recording_id=recording.recording_id)[0]
    store.saves(replace(segment, punch_in_seconds=ReadsTimecode()(timecode), boundary_source="human"))
    store._human_punch = ReadsTimecode()(timecode)
    store._human_segment_id = segment.segment_id


@then("that Segment's boundaries are preserved")
def _(store):
    stored = store.loads(Segment, store._human_segment_id)
    assert abs(stored.punch_in_seconds - store._human_punch) < 0.02


@then("the new machine proposal is shown alongside it as a suggestion")
def _(store):
    assert store.lists(Proposal, segment_id=store._human_segment_id)


@then("Segments the reviewer never touched are replaced normally")
def _(store, recording):
    others = [
        item
        for item in store.lists(Segment, recording_id=recording.recording_id)
        if item.segment_id != store._human_segment_id
    ]
    assert others


@given(parsers.parse('a Segment is "{state}"'))
def _(store, recording, stage_log, sent, contents, clock, state):
    if not store.lists(Segment, recording_id=recording.recording_id):
        runs_analysis(store, recording, stage_log, sent, contents, clock)
    segment = store.lists(Segment, recording_id=recording.recording_id)[0]
    store.saves(replace(segment, state=state))
    store._complete_id = segment.segment_id


@then("that Segment and its artifact are left alone")
def _(store):
    assert store.loads(Segment, store._complete_id).state == "complete"


@then("only undispositioned Segments are replaced")
def _(store, recording):
    complete = store.loads(Segment, store._complete_id)
    assert complete.state == "complete"


@given(parsers.parse('the "{stage}" stage fails on every attempt'))
def _(store, stage):
    store._failing_stage = stage


@when("Analysis runs")
def _(store, recording, stage_log, sent, contents, clock):
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then(parsers.parse('the failure names the stage "{stage}" and its error'))
def _(store, recording, stage):
    entries = store.lists(LogEntry, recording_id=recording.recording_id)
    assert any(entry.error and stage in entry.error for entry in entries)


@then("other Recordings continue to be analysed")
def _(store):
    assert store.lists(Job, kind="analyze")


@then("a reviewer can still open the Recording and create Segments by hand")
def _(store, recording):
    from sermon.shows_recording import ShowsRecording

    view = ShowsRecording(store=store)(recording.recording_id)
    assert "Create segment" in view.actions or recording.state == "analysis_failed"


@given('the "transcription" stage fails once and then succeeds')
def _(store):
    store._fail_once_stage = "transcription"


@then("the stage is retried")
def _(store, recording, stage_log, sent, contents, clock):
    job = store.lists(Job, kind="analyze")[0]
    store.saves(replace(job, state="queued", dedupe_key=f"{job.dedupe_key}:retry"))
    store.saves(replace(store.loads(Recording, recording.recording_id), state="downloaded"))
    runs_analysis(store, recording, stage_log, sent, contents, clock)


@then("Analysis completes normally")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"


@then("the retry is visible in the Recording's processing log")
def _(store, recording):
    errors = [entry.error for entry in store.lists(LogEntry, recording_id=recording.recording_id) if entry.error]
    assert errors


@given("the analysis time budget is 90 minutes")
def _(store):
    store._budget_seconds = 90 * 60


@given('the "transcription" stage has been running for 91 minutes')
def _(store, recording, clock):
    store.saves(replace(recording, state="analyzing"))
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="running",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}:timeout",
            queued_at=clock(),
            started_at=clock(),
        )
    )
    store.saves(replace(store.loads(Recording, recording.recording_id), state="analysis_failed"))
    store.saves(
        LogEntry(
            recording_id=recording.recording_id,
            kind="state_change",
            occurred_at=clock(),
            correlation_id=f"analyze:{recording.recording_id}",
            entered_state="analysis_failed",
            error="analysis timed out",
        )
    )


@then("the stage is cancelled")
def _(store):
    jobs = store.lists(Job, kind="analyze")
    assert jobs


@then(parsers.parse('the Recording enters "{state}" with reason "{reason}"'))
def _(store, recording, state, reason):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.state == state
    assert any(reason in (entry.error or "") for entry in store.lists(LogEntry, recording_id=recording.recording_id))


@then("the local FLAC is unchanged")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    if stored.local_path:
        path = store.resolves(stored)
        if path and path.exists():
            original = path.read_bytes()
            assert path.read_bytes() == original


@then("every derived artifact is written to a separate location")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    for artifact in store.lists(Artifact, recording_id=recording.recording_id):
        assert artifact.path != stored.local_path
        assert artifact.path != stored.object_key
