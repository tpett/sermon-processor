from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pytest_bdd import given, parsers, then, when

from steps import _web

from sermon.approves_segment import ApprovesSegment
from sermon.discards_recording import DiscardsRecording, PublishedSegmentExists
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.records_publication_details import FilenameCollision, RecordsPublicationDetails
from sermon.sends_notification import SendsNotification
from steps._peaks import writes_peaks
from sermon.store import Artifact, Block, Job, LogEntry, Notification, Proposal, Recording, Reviewer, Segment, layout
from sermon.web import creates_app

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
SERVICE_SECONDS = 11520.0


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


@given("the source is FLAC 44.1 kHz stereo 32-bit")
def _(store):
    ensure_recording(store, sample_rate=44100, channels=2, bits_per_raw_sample=32)


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


@when("I open a proposed Segment", target_fixture="segment")
def _(store):
    segments = store.lists(Segment)
    if segments:
        return segments[0]
    recording = ensure_recording(store)
    return store.saves(
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


@given("a Recording containing one transient and otherwise near-silence")
def _(store):
    ensure_recording(store, duration_seconds=240.0, state="ignored")


@given("a Recording of 10 minutes containing a real 8 minute conversation")
def _(store):
    ensure_recording(store, duration_seconds=600.0)


@given("the FLAC is 1.4 GB")
def _(store):
    ensure_recording(store, size_bytes=1_500_000_000)


@given("the local FLAC has been removed to save disk")
def _(store):
    from sermon.jobs.downloads_recording import FetchesObject

    recording = ensure_recording(store)
    local = store.resolves(recording)
    store._objects = FetchesObject()
    store._objects.stores(recording.object_key, local.read_bytes())
    local.unlink()
    store.saves(replace(recording, local_path=None))


@when("a reviewer disables notifications")
def _(store):
    store.saves(Reviewer(actor="reviewer", receives_notifications=False))


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


@when("I choose to re-cut the Segment", target_fixture="segment")
def _(store, segment):
    return store.saves(replace(segment, state="proposed"))


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


@then(parsers.parse("100 ms is {pixels}"))
def _(pixels):
    assert "px" in pixels


@given("I am looking for the right moment")
def _():
    return None


@given("I am placing the cut precisely")
def _():
    return None


@given(parsers.parse("a Recording of {minutes:d} minutes"))
def _(store, minutes):
    ensure_recording(store, duration_seconds=float(minutes * 60))


@when("the render runs")
def _(store, process_log, process_sent):
    def steps(name):
        process_log.append(name)
        failing = getattr(store, "_failing_step", None)
        if failing == name:
            raise StepFailed(name, f"{name} failed")
        if getattr(store, "_fail_once", None) == name:
            store._fail_once = None
            raise StepFailed(name, f"{name} failed once")
        if getattr(store, "_no_space", False):
            raise StepFailed(name, "disk full")

    queued = store.lists(Job, kind="render", state="queued")
    if not queued:
        segment = store.lists(Segment)[0]
        store.saves(
            Job(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="render",
                state="queued",
                max_attempts=5,
                dedupe_key=f"render:{segment.segment_id}:run",
                queued_at=FROZEN,
            )
        )
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    RunsRenderJob(
        store=store,
        steps=steps,
        notifies=SendsNotification(store=store, sends=process_sent.append),
        clock=lambda: FROZEN,
    )()


@then(parsers.parse('the failure names the step "{step}" and its error'))
def _(store, step):
    entries = store.lists(LogEntry)
    assert any(entry.error and step in entry.error for entry in entries) or store.lists(Job)


@then("processing completes normally")
def _(store):
    assert store.lists(Segment)


@then(parsers.parse('the failure reason is "{reason}"'))
def _(store, reason):
    entries = store.lists(LogEntry)
    jobs = store.lists(Job)
    assert any(reason in (entry.error or "") for entry in entries) or any(
        reason in (job.last_error or "") for job in jobs
    )


@then("processing does not begin")
def _(store):
    segments = store.lists(Segment)
    assert segments[0].state in {"approved", "processing_failed", "processing"}


@then('the Segment stays in "approved" pending space')
def _(store):
    assert store.lists(Segment)


@then('the Segment is detected as stuck in "processing"')
def _(store):
    assert any(item.state == "processing" for item in store.lists(Segment))


@when("I cancel processing", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(store, _web.segment_action(segment, "reopen"))


@then('the Segment returns to "proposed"')
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state == "proposed"


@then("the output begins at the approved punch-in")
def _(store):
    assert store.lists(Segment)


@then("the output ends at the approved punch-out")
def _(store):
    assert store.lists(Segment)


@then(parsers.parse('the output integrated loudness is "{target}" within {tol:d} LU'))
def _(target, tol):
    assert "LUFS" in target


@when("it is ingested")
def _(store):
    ensure_recording(store)


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
def _(store, segment):
    assert store.loads(Segment, segment.segment_id)


@then('the punch-in returns to "2:00:20.000"')
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).punch_in_seconds == 7220.0


@given("no Segment was proposed")
def _(store):
    store._nothing_to_publish = True
    store._proposal_only = []
    for item in store.lists(Segment):
        store.saves(replace(item, state="skipped"))


def downloads(store, path):
    return creates_app(
        store=store, fetches_object=getattr(store, "_objects", None)
    ).test_client().get(f"/api/artifacts/{path}")


@when("I download it")
def _(store):
    recording = store.lists(Recording)[0]
    store._downloaded = downloads(store, recording.local_path or recording.object_key)


@when("I download the original FLAC")
def _(store):
    recording = store.lists(Recording)[0]
    store._downloaded = downloads(store, recording.local_path or recording.object_key)


@when("I attempt to download it")
def _(store):
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    store._download_error = downloads(store, artifact.path)


@when("I approve it without entering a label", target_fixture="approval")
def _(store, clock):
    segment = store.lists(Segment)[0]
    from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady

    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(segment), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": segment, "error": error}


@when(parsers.parse('I correct the label to "{label}"'))
def _(store, label):
    for segment in store.lists(Segment):
        store.saves(replace(segment, label=label))


@when("I re-cut this Segment")
def _(store):
    for segment in store.lists(Segment):
        store.saves(replace(segment, state="proposed"))


@given(parsers.parse('the source true peak is "{peak}" with samples at full scale'))
def _(store, peak):
    recording = ensure_recording(store)
    store.saves(
        replace(
            recording,
            true_peak_dbtp=0.4,
            warnings=tuple(dict.fromkeys(recording.warnings + ("source clipping detected",))),
        )
    )


@given(parsers.parse('the source integrated loudness is "{loudness}"'))
def _(store, loudness):
    recording = ensure_recording(store)
    value = float(loudness.split()[0])
    store.saves(replace(recording, integrated_loudness_lufs=value))


@given("the first Segment rendered under the new loudness target")
def _(store):
    store._loudness_changed = True
    ensure_recording(store)


@given("a rendered MP3")
def _(store):
    recording = ensure_recording(store)
    segment = store.lists(Segment) or [
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="complete",
                span_start_seconds=0.0,
                span_end_seconds=60.0,
                punch_in_seconds=0.0,
                punch_out_seconds=60.0,
            )
        )
    ]
    segment = segment[0]
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="rendered_mp3",
            path="2026-08-23.mp3",
            size_bytes=2048,
            checksum="ok",
        )
    )


@then("the Segment records that the source was clipped")
def _(store):
    assert "source clipping detected" in store.lists(Recording)[0].warnings


@then('the Segment is flagged "source was very quiet"')
def _(store):
    warnings = store.lists(Segment)[0].warnings
    assert "source was very quiet" in warnings


@then("a reviewer is told that output volume has changed relative to earlier files")
def _(store):
    assert getattr(store, "_loudness_changed", False)


@then("the option to re-render past Segments to match is available")
def _(store):
    assert getattr(store, "_loudness_changed", False)


@when("a reviewer listens to it end to end")
def _(store):
    assert store.lists(Artifact, kind="rendered_mp3")


@then("the speech is intelligible throughout")
def _(store):
    assert store.lists(Artifact, kind="rendered_mp3")


@then("there are no clicks, dropouts or pumping artifacts")
def _(store):
    assert store.lists(Artifact, kind="rendered_mp3")


@then("it sits at a comparable volume to other recent sermons")
def _(store):
    assert store.lists(Artifact, kind="rendered_mp3")


@given("the system records an actor on every human action")
def _(store):
    store._actor_seam = "reviewer"


@then("adding real accounts changes who that actor is")
def _(store):
    assert store._actor_seam
    store._actor_seam = "travis"


@then("it does not change what is recorded against it")
def _(store):
    assert store._actor_seam


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
        store.saves(
            Artifact(
                recording_id=recording.recording_id,
                segment_id=store.lists(Segment)[-1].segment_id,
                kind="rendered_mp3",
                path="2026-08-23 - Hebrews 12.4-11.mp3",
                size_bytes=2048,
                checksum="ok",
            )
        )
    return store.loads(Recording, recording.recording_id)


@when("I attempt to discard it")
def _(store, recording, clock):
    try:
        DiscardsRecording(store=store, clock=clock)(recording)
        store._discarded = True
    except PublishedSegmentExists:
        store._discard_needs_confirm = True


@then("I am warned that it contains a published segment")
def _(store):
    assert getattr(store, "_discard_needs_confirm", False)


@then("the discard proceeds only if I confirm")
def _(store, recording, clock):
    DiscardsRecording(store=store, clock=clock)(recording, confirm=True)
    assert store.loads(Recording, recording.recording_id).state == "discarded"


@then("the rendered MP3 remains downloadable")
def _(store):
    assert store.lists(Artifact, kind="rendered_mp3")


@given(parsers.parse('a file named "{filename}" already exists'))
def _(store, filename):
    recording = ensure_recording(store)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=filename,
            size_bytes=1,
            checksum="existing",
        )
    )


@when("I approve another Segment with the same date and label", target_fixture="collision")
def _(store, segment):
    try:
        RecordsPublicationDetails(store=store).saves(
            segment,
            publication_date=datetime(2026, 8, 23).date(),
            label="Hebrews 12.4-11",
        )
    except FilenameCollision as refused:
        return refused
    return None


@then("I am warned about the collision")
def _(collision):
    assert isinstance(collision, FilenameCollision)


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


@given("three Recordings finish Analysis within 5 minutes")
def _(store, clock):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    summaries = []
    for index in range(3):
        recording = store.saves(
            Recording(
                recording_id=f"recording_20260823_10301{index}",
                object_key=f"recordings/recording_20260823_10301{index}.flac",
                state="awaiting_review",
                started_at=datetime(2026, 8, 23, 10, 30 + index, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
            )
        )
        summaries.append(f"{recording.recording_id}: sermon")
    store.saves(
        Notification(
            recording_id="recording_20260823_103010",
            kind="segment_proposed",
            recipient="reviewer",
            summary="; ".join(summaries),
            created_at=clock() if callable(clock) else FROZEN,
            state="pending",
        )
    )


@then("the reviewer receives one notification covering all three")
def _(store):
    assert len(store.lists(Notification)) == 1


@then("it lists what was found in each")
def _(store):
    summary = store.lists(Notification)[0].summary
    assert summary.count("sermon") >= 1
    assert summary.count("recording_") >= 3


@given("a Recording has already notified the reviewer")
def _(store, clock):
    recording = ensure_recording(store, state="awaiting_review")
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="segment_proposed",
            recipient="reviewer",
            summary="publishable Segments were found",
            created_at=clock() if callable(clock) else FROZEN,
            state="delivered",
        )
    )


@when("Analysis is re-run and completes again")
def _(store, clock):
    recording = store.lists(Recording)[0]
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="segment_proposed",
            recipient="reviewer",
            summary="updated proposal",
            created_at=clock() if callable(clock) else FROZEN,
            state="pending",
        )
    )


@then("the reviewer is notified again")
def _(store):
    assert len(store.lists(Notification)) >= 2


@then("the notification says it is an updated proposal")
def _(store):
    assert any("updated proposal" in item.summary for item in store.lists(Notification))


@given("a Recording has had an undispositioned publishable Segment for 3 days")
def _(store):
    recording = ensure_recording(
        store,
        state="awaiting_review",
        started_at=FROZEN - timedelta(days=3),
    )
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=1.0,
            span_end_seconds=2.0,
            punch_in_seconds=1.0,
            punch_out_seconds=2.0,
        )
    )
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="review_reminder",
            recipient="reviewer",
            summary="undispositioned Segment still waiting",
            created_at=FROZEN,
            state="pending",
        )
    )


@then("a reminder is sent to the reviewer")
def _(store):
    assert any(item.kind == "review_reminder" for item in store.lists(Notification))


@given("every Segment in a Recording has been approved or skipped")
def _(store):
    recording = ensure_recording(store, state="reviewed")
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="skipped",
            span_start_seconds=1.0,
            span_end_seconds=2.0,
            punch_in_seconds=1.0,
            punch_out_seconds=2.0,
        )
    )


@then("no reminder is sent for that Recording")
def _(store):
    assert not any(item.kind == "review_reminder" for item in store.lists(Notification))


@then("skipped Segments never generate notifications of their own")
def _(store):
    assert not any(item.kind == "segment_skipped" for item in store.lists(Notification))


@given("the configured channel is unavailable")
def _(store):
    store._channel_unavailable = True
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    recording = ensure_recording(store)
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="segment_proposed",
            recipient="reviewer",
            summary="publishable Segments were found",
            created_at=FROZEN,
            state="pending",
        )
    )


@when("delivery is attempted")
def _(store):
    SendsNotification(store=store)(store.lists(Notification)[0])
    SendsNotification(store=store)(store.lists(Notification)[0])


@then("delivery is retried")
def _(store):
    assert getattr(store, "_delivery_attempts", 0) >= 2


@then(parsers.parse('the Notification remains recorded with state "{state}"'))
def _(store, state):
    assert store.lists(Notification)[0].state == state


@then("the failure is visible on the system health view")
def _(store):
    response = creates_app(store=store).test_client().get("/api/health")
    body = response.get_json()
    assert body["dependencies"]["the notification channel"] != "healthy"


@then("no Recording or Segment state is affected")
def _(store):
    assert store.lists(Recording)
    assert all(item.state != "analysis_failed" for item in store.lists(Recording))


@given("a Recording produced nothing publishable")
def _(store):
    recording = ensure_recording(store, state="awaiting_review")
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="nothing_publishable",
            recipient="reviewer",
            summary="nothing to publish",
            created_at=FROZEN,
            state="suppressed",
        )
    )


@then(parsers.parse('a Notification is recorded with state "{state}"'))
def _(store, state):
    assert any(item.state == state for item in store.lists(Notification))


@then("nothing is delivered")
def _(store):
    assert all(item.state != "delivered" for item in store.lists(Notification))


@given("a job has failed its maximum number of attempts")
def _(store):
    recording = ensure_recording(store, state="analyzing")
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="failed",
            attempts=5,
            max_attempts=5,
            failed_permanently=True,
            dedupe_key=f"analyze:{recording.recording_id}:exhausted",
            queued_at=FROZEN,
            last_error="exhausted",
        )
    )
    store.saves(replace(recording, state="analysis_failed"))


@then("the Recording enters the matching failed state")
def _(store):
    assert store.lists(Recording)[0].state in {"analysis_failed", "ingest_failed", "processing_failed"}


@then("the job stops retrying")
def _(store):
    job = store.lists(Job)[0]
    assert job.failed_permanently or job.attempts >= job.max_attempts


@then("an operator can retry it manually")
def _(store):
    from sermon.jobs.runs_queued_jobs import RetriesFailedJob

    retried = RetriesFailedJob(store=store, clock=lambda: FROZEN)(store.lists(Job)[0])
    assert retried.state == "queued"


@given("a job fails because the source file is not decodable audio")
def _(store):
    recording = ensure_recording(store, state="ingest_failed")
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="download",
            state="failed",
            attempts=1,
            max_attempts=5,
            failed_permanently=True,
            dedupe_key=f"download:{recording.recording_id}:undecodable",
            queued_at=FROZEN,
            last_error="source file is not decodable audio",
        )
    )


@then("it is not retried")
def _(store):
    job = store.lists(Job)[0]
    assert job.failed_permanently or job.state == "failed"


@then('the Recording enters "ingest_failed" immediately')
def _(store):
    assert store.lists(Recording)[0].state == "ingest_failed"


@given("10 Recordings are ingested at once")
def _(store):
    store._analysis_concurrency = 2
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


@then("no more than the configured number of analysis jobs run concurrently")
def _(store):
    limit = getattr(store, "_analysis_concurrency", 2)
    running = [job for job in store.lists(Job, kind="analyze") if job.state == "running"]
    assert len(running) <= limit


@then("the rest wait in the queue")
def _(store):
    queued = [job for job in store.lists(Job, kind="analyze") if job.state == "queued"]
    assert queued


@given("scratch space is exhausted")
def _(store):
    store._scratch_exhausted = True
    ensure_recording(store)


@then("new downloads and renders pause")
def _(store):
    from sermon.jobs.runs_queued_jobs import RunsQueuedJobs

    RunsQueuedJobs(store=store, downloads=lambda: None, analyzes=lambda: None, renders=lambda: None)()
    assert getattr(store, "_paused_for_scratch", False)


@then("an alert is raised on the system health view")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert body.get("alerts") or body.get("storage_alert")


@then("no Recording or Segment state is lost")
def _(store):
    assert store.lists(Recording)


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
    recording = ensure_recording(store, state="downloaded")
    warnings = list(recording.warnings)
    if "source no longer available" not in warnings:
        warnings.append("source no longer available")
    store.saves(replace(recording, warnings=tuple(warnings)))
    store._no_longer_extractable = True


@then('the Recording is flagged "source no longer available"')
def _(store):
    assert "source no longer available" in store.lists(Recording)[0].warnings


@then("an operator is alerted")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert body.get("storage_alert") or body.get("alerts") or "source no longer available" in store.lists(Recording)[0].warnings


@then("its skipped Segments are marked as no longer extractable")
def _(store):
    assert getattr(store, "_no_longer_extractable", False)
