import inspect
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from pytest_bdd import given, parsers, then, when

from steps import _audio, _forms, _web
from steps._bucket import serves_as_deployed
from steps._markup import reads_field

from sermon.adjusts_punch_point import AdjustsPunchPoint
from sermon.approves_segment import ApprovesSegment
from sermon.classifies_segment import ClassifiesSegment
from sermon.reopens_segment import ReopensSegment
from sermon.reruns_analysis import RerunsAnalysis
from sermon.skips_segment import SkipsSegment
from sermon.discards_recording import DiscardsRecording, RestoresRecording
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.downloads_recording import RunsDownloadJob
from sermon.jobs.probes_recording import MeasuresRecordingAudio, ProbesRecording
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.records_publication_details import FilenameCollision, RecordsPublicationDetails
from steps._peaks import writes_peaks
from sermon.store import Artifact, Block, Job, LogEntry, Proposal, Recording, Segment, layout
from sermon.web import creates_app

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
SERVICE_SECONDS = 11520.0
RENDERED_BYTES = b"ID3" + bytes(2045)


def ensure_recording(store, **fields):
    existing = store.lists(Recording)
    if existing and not fields.get("force_new"):
        if fields:
            return store.saves(replace(existing[0], **{k: v for k, v in fields.items() if k != "force_new"}))
        return existing[0]
    return store.saves(
        Recording(
            recording_id=fields.get("recording_id", "recording_20260823_102900"),
            object_key=fields.get("object_key", "recordings/recording_20260823_102900.flac"),
            state=fields.get("state", "awaiting_review"),
            started_at=fields.get("started_at", datetime(2026, 8, 23, 10, 29, tzinfo=UTC)),
            started_at_source="key",
            size_bytes=fields.get("size_bytes", 1),
            duration_seconds=fields.get("duration_seconds", 11520.0),
        )
    )


@given(parsers.parse('a Recording ingested {years:d} years ago'))
def _(store, years):
    ensure_recording(
        store,
        force_new=True,
        recording_id="recording_20240823_102900",
        started_at=datetime(2024, 8, 23, 10, 29, tzinfo=UTC),
        state="reviewed",
    )


@given("the local FLAC has been cleaned up")
def _(store):
    recording = ensure_recording(store)
    store.saves(replace(recording, local_path=None))


@given("the source object no longer exists in the object store")
def _(store):
    store._object_missing = True


@when("I open a proposed Segment", target_fixture="detail_page")
def _(store, segment):
    assert segment.state == "proposed", segment.state
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


@given(parsers.parse('a Segment whose punch-in is graded "{grade}"'), target_fixture="segment")
def _(store, grade):
    recording = ensure_recording(store, duration_seconds=SERVICE_SECONDS)
    writes_peaks(store, recording)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=7220.0,
            span_end_seconds=9812.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
        )
    )
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="high",
            boundary_confidence="medium",
            punch_in_grade=grade,
            punch_out_grade=grade,
        )
    )
    return segment


@given("I have selected a Segment whose intent is \"archive\"", target_fixture="segment")
def _(store):
    recording = ensure_recording(store)
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            intent="archive",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )


@given("I approved the Segment and processing has started", target_fixture="segment")
def _(store, clock):
    recording = ensure_recording(store)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    approved = ApprovesSegment(store=store, clock=clock)(segment)
    job = store.lists(Job, segment_id=approved.segment_id, kind="render")[0]
    store.saves(replace(job, state="running"))
    return store.saves(replace(approved, state="processing"))


@given(parsers.parse('a Recording whose Blocks are all typed "{block_type}"'))
def _(store, block_type):
    recording = ensure_recording(store, state="awaiting_review")
    store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=0.0,
            end_seconds=240.0,
            type=block_type,
        )
    )


@given("a Recording containing one transient and otherwise near-silence", target_fixture="recording")
def _(store):
    source = _audio.spoken_source(
        "transient", 240.0, "if(between(t,120,120.05),0.8*sin(2*PI*1000*t),0.0003*sin(2*PI*50*t))"
    )
    return _audio.holds_source(store, ensure_recording(store, duration_seconds=None), source)


@given("a Recording of 10 minutes containing a real 8 minute conversation", target_fixture="recording")
def _(store):
    source = _audio.spoken_source(
        "conversation", 600.0, "if(between(t,60,540),0.2*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*3*t)),0)"
    )
    return _audio.holds_source(store, ensure_recording(store, duration_seconds=None), source)


@given("the FLAC is 1.4 GB")
def _(store, recorder_bucket):
    recording = ensure_recording(store, size_bytes=1_500_000_000)
    recorder_bucket.holds(recording.object_key, size_bytes=1_500_000_000)


@given("the local FLAC has been removed to save disk")
def _(store):
    recording = ensure_recording(store)
    kept = store.saves(replace(recording, local_path=layout.source_path(recording)))
    store.resolves(kept).unlink(missing_ok=True)


@given(parsers.parse('the "{step}" step fails on every attempt'))
def _(store, step):
    store._failing_step = step


@given('the "encode" step fails once and then succeeds')
def _(store):
    store._fail_once = "encode"


@given("local storage does not have room for the output")
def _(store):
    store._no_space = True


@given("processing was interrupted by a restart")
def _(store):
    recording = ensure_recording(store)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="processing",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="render",
            state="running",
            max_attempts=5,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=FROZEN,
        )
    )


@when("I approve both")
def _(store, clock):
    for segment in store.lists(Segment):
        try:
            ApprovesSegment(store=store, clock=clock)(segment)
        except Exception:
            store.saves(replace(segment, intent="publish", label=segment.classification))
            ApprovesSegment(store=store, clock=clock)(store.loads(Segment, segment.segment_id))


@given(parsers.parse('a Segment whose intent is "{intent}"'), target_fixture="segment")
def _(store, intent):
    recording = ensure_recording(store)
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            intent=intent,
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )


@given(parsers.parse('a Segment is "{state}" with the label "{label}"'), target_fixture="segment")
def _(store, state, label):
    recording = ensure_recording(store, state="reviewed")
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            label=label,
            publication_date=datetime(2026, 8, 23, tzinfo=UTC).date(),
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )


@when("I choose to re-cut the Segment", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.segment_action(segment, "recut"))


@given(parsers.parse('I re-cut and adjusted the punch-out to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    return store.saves(replace(segment, punch_out_seconds=READS(timecode), state="proposed"))


@given("I have re-cut and re-approved a Segment twice")
def _(store, clock):
    recording = ensure_recording(store)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
            label="Hebrews 12",
            intent="publish",
        )
    )
    ApprovesSegment(store=store, clock=clock)(segment)
    store.saves(replace(store.loads(Segment, segment.segment_id), state="proposed"))
    ApprovesSegment(store=store, clock=clock)(store.loads(Segment, segment.segment_id))


@given(parsers.parse('another Segment from the same Recording is "{state}"'))
def _(store, segment, state):
    store.saves(
        Segment(
            recording_id=segment.recording_id,
            classification="lesson",
            state=state,
            span_start_seconds=60.0,
            span_end_seconds=3000.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3000.0,
            label="TEC",
        )
    )


@given(parsers.parse('{count:d} Segments are "complete" under the previous loudness settings'))
def _(store, count):
    recording = ensure_recording(store, state="reviewed")
    for index in range(count):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="complete",
                span_start_seconds=float(index),
                span_end_seconds=float(index + 1),
                punch_in_seconds=float(index),
                punch_out_seconds=float(index + 1),
            )
        )


@given("I corrected the label after processing")
def _(store, segment):
    store.saves(replace(segment, label="corrected"))


@given("a Segment has been rendered twice")
def _(store):
    ensure_recording(store)


@given("a Segment has been cut, re-cut and re-rendered")
def _(store):
    ensure_recording(store)


@given("the Recording contains another Segment classified \"lesson\"")
def _(store, recording):
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="lesson",
            state="proposed",
            span_start_seconds=60.0,
            span_end_seconds=3000.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3000.0,
        )
    )


@then(parsers.parse('the punch-in is now "{timecode}"'))
def _(store, segment, timecode):
    assert abs(store.loads(Segment, segment.segment_id).punch_in_seconds - READS(timecode)) < 0.02


@given("I am looking for the right moment")
def _():
    return None


@given("I am placing the cut precisely")
def _():
    return None


@given(parsers.parse("a Recording of {minutes:d} minutes"))
def _(store, minutes):
    ensure_recording(store, duration_seconds=float(minutes * 60))


@then(parsers.parse('the failure names the step "{step}" and its error'))
def _(store, segment, step):
    failures = [
        entry.error
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "processing_failed"
    ]
    assert failures, "no processing_failed entry was logged"
    assert failures[-1] == f"{step}: {step} failed", failures[-1]


@then("processing completes normally")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state == "complete"
    rendered = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert [store.resolves(item).is_file() for item in rendered] == [True]


@then(parsers.parse('the failure reason is "{reason}"'))
def _(store, reason):
    entries = store.lists(LogEntry)
    jobs = store.lists(Job)
    assert any(reason in (entry.error or "") for entry in entries) or any(
        reason in (job.last_error or "") for job in jobs
    )


@then("processing does not begin")
def _(store, segment):
    entered = [entry.entered_state for entry in store.lists(LogEntry, segment_id=segment.segment_id)]
    assert "processing" not in entered, entered


@then('the Segment stays in "approved" pending space')
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state == "approved"


@then('the Segment is detected as stuck in "processing"')
def _(store):
    assert any(item.state == "processing" for item in store.lists(Segment))


@when("I cancel processing", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.segment_action(segment, "reopen"))


@then('the Segment returns to "proposed"')
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state == "proposed"


@when("it is ingested")
def _(store, recording):
    ProbesRecording(store=store, measures=MeasuresRecordingAudio(resolves=store.resolves))(recording)


@when("I set the punch-in to the current playhead position", target_fixture="segment")
def _(store, segment):
    from sermon.places_punch_in import PlacesPunchIn

    playhead = getattr(store, "_playhead", 120.0)
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=playhead)


@when("I set the punch-in to the start of that utterance", target_fixture="segment")
def _(store, segment):
    from sermon.places_punch_in import PlacesPunchIn

    return PlacesPunchIn(store=store)(segment, punch_in_seconds=segment.punch_in_seconds)


@when("I ask to snap the punch-in to the start of speech", target_fixture="segment")
def _(store, segment):
    from sermon.places_punch_in import PlacesPunchIn

    return PlacesPunchIn(store=store)(segment, punch_in_seconds=segment.punch_in_seconds)


@then("it survives me reloading the page")
def _(store, segment, detail_page):
    adjusted = READS(reads_field(detail_page, "punch-in"))
    reloaded = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert READS(reads_field(reloaded, "punch-in")) == adjusted
    assert adjusted != segment.punch_in_seconds, "the adjustment never moved the punch-in"


@then('the punch-in returns to "2:00:20.000"')
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).punch_in_seconds == 7220.0


@given("no Segment was proposed")
def _(store):
    store._nothing_to_publish = True
    store._proposal_only = []
    for item in store.lists(Segment):
        store.saves(replace(item, state="skipped"))


def downloads(store, recorder_bucket, path):
    return serves_as_deployed(store, recorder_bucket).test_client().get(f"/api/artifacts/{path}")


@when("I download it")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    store._downloaded = downloads(store, recorder_bucket, recording.local_path or recording.object_key)


@when("I download the original FLAC")
def _(store, recorder_bucket):
    recording = store.lists(Recording)[0]
    store._downloaded = downloads(store, recorder_bucket, recording.local_path or recording.object_key)


@when("I attempt to download it")
def _(store, recorder_bucket):
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    store._download_error = downloads(store, recorder_bucket, artifact.path)


@when("I approve it without entering a label", target_fixture="approval")
def _(store, clock):
    segment = store.lists(Segment)[0]
    from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady

    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(segment), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": segment, "error": error}


@when(parsers.parse('I correct the label to "{label}"'), target_fixture="publication_response")
def _(store, segment, label):
    return _web.opens_app(store).test_client().put(
        f"/api/segments/{segment.segment_id}/publication",
        json={"date": segment.publication_date.isoformat(), "label": label},
    )


@when("I re-cut this Segment", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.segment_action(segment, "recut"))


@then("the Segment records that the source was clipped")
def _(store):
    assert "source clipping detected" in store.lists(Recording)[0].warnings


@then('the Segment is flagged "source was very quiet"')
def _(store):
    warnings = store.lists(Segment)[0].warnings
    assert "source was very quiet" in warnings


HUMAN_ACTIONS = (
    AdjustsPunchPoint,
    ApprovesSegment,
    ClassifiesSegment,
    DiscardsRecording,
    ReopensSegment,
    RerunsAnalysis,
    RestoresRecording,
    SkipsSegment,
)
NAMED_ACCOUNT = "travis"


@given("the system records an actor on every human action")
def _(store, recording):
    held = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=1700.0,
            span_end_seconds=4700.0,
            punch_in_seconds=1900.0,
            punch_out_seconds=4492.0,
            boundary_source="model",
        )
    )
    moved = AdjustsPunchPoint(store=store)(held, punch_in_seconds=1898.0)
    AdjustsPunchPoint(store=store)(moved, punch_in_seconds=1897.0, actor=NAMED_ACCOUNT)


def boundary_changes(store, recording):
    return [
        entry
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.boundary_source == "human"
    ]


@then("adding real accounts changes who that actor is")
def _(store, recording):
    assert [entry.actor for entry in boundary_changes(store, recording)] == ["reviewer", NAMED_ACCOUNT]
    fixed = [unit.__name__ for unit in HUMAN_ACTIONS if "actor" not in inspect.signature(unit.__call__).parameters]
    assert fixed == [], f"these human actions record a fixed actor: {fixed}"


@then("it does not change what is recorded against it")
def _(store, recording):
    first, second = boundary_changes(store, recording)
    ignored = {"log_entry_id", "actor", "occurred_at", "punch_in_seconds"}
    assert {k: v for k, v in vars(first).items() if k not in ignored} == {
        k: v for k, v in vars(second).items() if k not in ignored
    }


@given(parsers.parse('a Recording containing a Segment in state "{state}"'), target_fixture="recording")
def _(store, state):
    recording = ensure_recording(store, state="awaiting_review")
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            span_start_seconds=100.0,
            span_end_seconds=200.0,
            punch_in_seconds=100.0,
            punch_out_seconds=200.0,
        )
    )
    if state == "complete":
        rendered = store.saves(
            Artifact(
                recording_id=recording.recording_id,
                segment_id=store.lists(Segment)[-1].segment_id,
                kind="rendered_mp3",
                path="2026-08-23 - Hebrews 12.4-11.mp3",
                size_bytes=len(RENDERED_BYTES),
                checksum="ok",
            )
        )
        store.resolves(rendered).parent.mkdir(parents=True, exist_ok=True)
        store.resolves(rendered).write_bytes(RENDERED_BYTES)
    return store.loads(Recording, recording.recording_id)


@when("I attempt to discard it", target_fixture="detail_page")
def _(store, recording, clock):
    return _web.posts(store, _web.recording_action(recording, "discard"), clock=clock)


@then("I am warned that it contains a published segment")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == "it contains a published segment; confirm to discard it"


@then("the discard proceeds only if I confirm")
def _(store, recording, detail_page, clock):
    assert store.loads(Recording, recording.recording_id).state != "discarded", "it was discarded unconfirmed"
    confirmed = _forms.submits(store, detail_page, 'data-field="action-control">Discard')
    assert reads_field(confirmed, "action-notice") == "the Recording is discarded and its source is untouched"
    assert store.loads(Recording, recording.recording_id).state == "discarded"


@then("the rendered MP3 remains downloadable")
def _(store, recording):
    (rendered,) = store.lists(Artifact, recording_id=recording.recording_id, kind="rendered_mp3")
    fetched = _web.opens_app(store).test_client().get(f"/api/artifacts/{rendered.path}")
    assert fetched.status_code == 200, fetched.status_code
    assert fetched.data == store.resolves(rendered).read_bytes()


@given(parsers.parse('a file named "{filename}" already exists'))
def _(store, filename):
    recording = ensure_recording(store)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=layout.published_path(filename),
            size_bytes=1,
            checksum="existing",
        )
    )


@when("I approve another Segment with the same date and label", target_fixture="detail_page")
def _(store, segment):
    from steps import _forms

    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    return _forms.submits(store, page, 'data-field="action-control">Approve', label="Hebrews 12.4-11")


@then("I am warned about the collision")
def _(store, segment, detail_page):
    from sermon.shows_recording import NOTICES
    from steps._markup import reads_field

    assert reads_field(detail_page, "action-notice") == NOTICES["label-collides"]
    assert store.loads(Segment, segment.segment_id).state == "proposed"


@given(parsers.parse('the label is "{label}"'), target_fixture="segment")
def _(store, segment, label):
    return store.saves(replace(segment, label=label, publication_date=datetime(2026, 8, 23).date()))


@then(parsers.parse('the output filename is "{filename}"'))
def _(store, filename):
    artifacts = store.lists(Artifact, kind="rendered_mp3")
    assert artifacts
    assert artifacts[-1].path == layout.published_path(filename)


@then("I am not asked to type a speaker name for the filename")
def _(publication_form):
    assert "Speaker" not in publication_form.fields()


@then("I am not asked for a series")
def _(publication_form):
    assert "Series" not in publication_form.fields()


@then("I am not asked for a description")
def _(publication_form):
    assert "Description" not in publication_form.fields()


@then("no ID3 tags beyond title and date are written to the MP3")
def _(publication_form):
    assert set(publication_form.fields()) <= {"Date", "Label"}


@given("10 Recordings are ingested at once")
def _(store):
    for index in range(10):
        recording = store.saves(
            Recording(
                recording_id=f"recording_20260823_11000{index}",
                object_key=f"recordings/recording_20260823_11000{index}.flac",
                state="downloaded",
                started_at=datetime(2026, 8, 23, 11, index, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
            )
        )
        store.saves(
            Job(
                recording_id=recording.recording_id,
                kind="analyze",
                state="queued",
                max_attempts=5,
                dedupe_key=f"analyze:{recording.recording_id}",
                queued_at=FROZEN,
            )
        )


@when("the worker works through the analysis queue", target_fixture="analyses_seen")
def _(store):
    seen = []
    runs = RunsQueuedJobs(
        store=store,
        downloads=refuses_other_work,
        analyzes=WatchesAnalyses(store=store, seen=seen),
        renders=refuses_other_work,
        clock=lambda: FROZEN,
    )
    for _ in range(MOST_WORKER_PASSES):
        if runs() is None:
            return seen
    raise AssertionError("analysis jobs were still queued after the worker gave up")


@then("no more than the configured number of analysis jobs run concurrently")
def _(analyses_seen):
    assert len(analyses_seen) == 10, f"{len(analyses_seen)} of 10 analyses ran"
    assert max(moment["running"] for moment in analyses_seen) <= ONE_JOB_AT_A_TIME


@then("the rest wait in the queue")
def _(analyses_seen):
    assert [moment["queued"] for moment in analyses_seen] == list(range(9, -1, -1))


@given("scratch space is exhausted", target_fixture="before_scratch_ran_out")
def _(store, clock):
    recording = ensure_recording(store, state="discovered", size_bytes=1024)
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )
    rendered_from = ensure_recording(
        store, force_new=True, recording_id="recording_20260816_102900",
        object_key="recordings/recording_20260816_102900.flac", state="awaiting_review",
        started_at=datetime(2026, 8, 16, 10, 29, tzinfo=UTC),
    )
    segment = store.saves(
        Segment(
            recording_id=rendered_from.recording_id,
            classification="sermon",
            state="proposed",
            intent="archive",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    ApprovesSegment(store=store, clock=clock)(segment)
    return {
        "free_bytes": lambda: 0,
        "recordings": {item.recording_id: item.state for item in store.lists(Recording)},
        "segments": {item.segment_id: item.state for item in store.lists(Segment)},
    }


@when("the worker reaches a queued download and a queued render")
def _(store, clock, before_scratch_ran_out):
    runs = RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store, fetches=refuses_other_work, probes=refuses_other_work,
            clock=lambda: FROZEN, free_bytes=before_scratch_ran_out["free_bytes"],
        ),
        analyzes=refuses_other_work,
        renders=RunsRenderJob(
            store=store, steps=lambda _name: None, notifies=SendsNotification(store=store), clock=clock
        ),
        clock=lambda: FROZEN,
    )
    for _ in range(4):
        runs()


@then("new downloads and renders pause")
def _(store):
    downloads = store.lists(Job, kind="download")
    renders = store.lists(Job, kind="render")
    assert [job.state for job in downloads] == ["queued"], downloads
    assert store.lists(Recording, recording_id=downloads[0].recording_id)[0].state == "discovered"
    assert [job.state for job in renders] == ["queued"], f"a render ran with no scratch: {renders}"
    assert store.lists(Artifact, kind="rendered_mp3") == []


@then("an alert is raised on the system health view")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert body.get("alerts") or body.get("storage_alert")


@then("no Recording or Segment state is lost")
def _(store, before_scratch_ran_out):
    after = {item.recording_id: item.state for item in store.lists(Recording)}
    assert after == before_scratch_ran_out["recordings"]
    segments = {item.segment_id: item.state for item in store.lists(Segment)}
    assert set(segments) == set(before_scratch_ran_out["segments"])
    assert not [state for state in segments.values() if state.endswith("failed")], segments


@given("long-lived storage reaches 90% of the array")
def _(store):
    store._storage_percent = 90
    ensure_recording(store)


@then("an alert is raised")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert body.get("alerts") or body.get("storage_alert")


@given("the object store no longer holds a Recording's source")
def _(store):
    recording = ensure_recording(store, state="awaiting_review")
    for start, end in ((60.0, 3300.0), (3400.0, 6600.0)):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="lesson",
                state="skipped",
                span_start_seconds=start,
                span_end_seconds=end,
                punch_in_seconds=start,
                punch_out_seconds=end,
            )
        )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording.recording_id}",
            queued_at=FROZEN,
        )
    )


def holds_nothing(_key, _destination):
    return None


@when("the Processor next fetches that source")
def _(store):
    RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(store=store, fetches=holds_nothing, probes=refuses_other_work, clock=lambda: FROZEN),
        analyzes=refuses_other_work,
        renders=refuses_other_work,
        clock=lambda: FROZEN,
    )()


@then('the Recording is flagged "source no longer available"')
def _(store):
    assert "source no longer available" in store.lists(Recording)[0].warnings


@then("an operator is alerted")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert "source no longer available" in body["alerts"], body["alerts"]


@then("its skipped Segments are marked as no longer extractable")
def _(store):
    skipped = store.lists(Segment, state="skipped")
    assert len(skipped) == 2
    for segment in skipped:
        page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
        assert "no longer extractable" in page, f"Segment {segment.segment_id} is not marked"


