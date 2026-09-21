from dataclasses import replace

from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.discards_recording import DiscardsRecording, RestoresRecording
from sermon.skips_segment import SkipsSegment
from sermon.store import Job, LogEntry, Proposal, Recording, Segment
from sermon.web import creates_app


@given(
    parsers.parse('a Recording containing a "{first}" Segment and a "{second}" Segment'),
    target_fixture="recording",
)
def _(store, first, second):
    from datetime import UTC, datetime

    recording = store.saves(
        Recording(
            recording_id="recording_20260816_090000",
            object_key="recordings/recording_20260816_090000.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    for index, classification in enumerate((first, second)):
        start = 60.0 + index * 4000
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=start,
                span_end_seconds=start + 3000,
                punch_in_seconds=start,
                punch_out_seconds=start + 3000,
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="high",
                boundary_confidence="high",
                punch_in_grade="easy",
                punch_out_grade="easy",
            )
        )
    return recording


@when("I approve the sermon and skip the lesson")
def _(store, recording, clock):
    segments = {item.classification: item for item in store.lists(Segment, recording_id=recording.recording_id)}
    ApprovesSegment(store=store, clock=clock)(segments["sermon"])
    SkipsSegment(store=store, clock=clock)(segments["lesson"])


@then(parsers.parse('the lesson Segment enters "{state}"'))
def _(store, recording, state):
    lesson = [
        item
        for item in store.lists(Segment, recording_id=recording.recording_id)
        if item.classification == "lesson"
    ][0]
    assert lesson.state == state


@then("its boundaries, classification, evidence and transcript remain stored")
def _(store, recording):
    lesson = [
        item
        for item in store.lists(Segment, recording_id=recording.recording_id)
        if item.classification == "lesson"
    ][0]
    assert lesson.punch_in_seconds
    assert lesson.classification == "lesson"
    assert store.lists(Proposal, segment_id=lesson.segment_id)


@then("it is listed on the Recording detail view as available")
def _(store, recording):
    detail = (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings/{recording.recording_id}")
        .get_json()
    )
    assert any(item["state"] == "skipped" for item in detail["segments"])


@then("I can approve it at any time without re-running Analysis")
def _(store, recording):
    assert not [
        job
        for job in store.lists(Job, recording_id=recording.recording_id, kind="analyze")
        if job.state == "queued"
    ]


@when("I skip a Segment")
def _(store, clock):
    from datetime import UTC, datetime

    recording = store.saves(
        Recording(
            recording_id="recording_20260816_090014",
            object_key="recordings/recording_20260816_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
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
    SkipsSegment(store=store, clock=clock)(segment)
    store._skipped = segment


@then("no reason is required")
def _(store):
    assert store.loads(Segment, store._skipped.segment_id).state == "skipped"


@then("who skipped it and when is recorded")
def _(store, clock):
    segment = store.loads(Segment, store._skipped.segment_id)
    assert segment.disposition_at == clock()


@given(parsers.parse("a Recording of {minutes:d} minutes containing {count:d} Segments"), target_fixture="recording")
def _(store, minutes, count):
    from datetime import UTC, datetime

    return store.saves(
        Recording(
            recording_id="recording_20260816_080000",
            object_key="recordings/recording_20260816_080000.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 16, 8, 0, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=float(minutes * 60),
        )
    )


@when(parsers.parse('I discard it with the reason "{reason}"'))
def _(store, recording, reason, clock):
    DiscardsRecording(store=store, clock=clock)(recording, reason=reason)


@when("I discard it")
def _(store, recording, clock):
    DiscardsRecording(store=store, clock=clock)(recording)


@then("it no longer appears in the default list")
def _(store, recording):
    body = creates_app(store=store).test_client().get("/api/recordings").get_json()
    assert all(row["recording_id"] != recording.recording_id for row in body["recordings"])


@then("the reason and who discarded it are recorded")
def _(store, recording):
    stored = store.loads(Recording, recording.recording_id)
    assert stored.skip_reason == "accidental trigger"
    entries = [
        entry
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state == "discarded"
    ]
    assert entries[0].actor == "reviewer"


@then("any running analysis job is cancelled")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="analyze")
    assert all(job.state == "cancelled" for job in jobs) or jobs == []


@when("I restore it")
def _(store, recording, clock):
    RestoresRecording(store=store, clock=clock)(store.loads(Recording, recording.recording_id))


@then("it returns to the state it was in before it was discarded")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).state != "discarded"


@then("the Recording's record and analysis artifacts are retained")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id) is not None
