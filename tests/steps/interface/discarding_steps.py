from dataclasses import replace

from pytest_bdd import given, parsers, then, when

from sermon import object_store
from sermon.approves_segment import ApprovesSegment
from sermon.skips_segment import SkipsSegment
from sermon.store import Job, LogEntry, Proposal, Recording, Segment
from sermon.web import creates_app
from steps import _web
from steps._interface_honesty import holds
from steps._markup import reads_field, reads_rows

MUTATIONS = ("put", "delete", "removes", "writes", "uploads", "moves")


def names_mutating_operations(module):
    return [
        name
        for name in dir(module)
        if not name.startswith("_") and any(word in name.lower() for word in MUTATIONS)
    ]


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
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}")
        .get_data(as_text=True)
    )
    assert [row for row in reads_rows(page, "segment") if row["segment-state"] == "skipped"]


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


@when(parsers.parse('I discard it with the reason "{reason}"'), target_fixture="detail_page")
def _(store, recording, reason, clock):
    return _web.posts(
        store, _web.recording_action(recording, "discard"), clock=clock, reason=reason
    )


@when("I discard it", target_fixture="detail_page")
def _(store, recording, clock):
    return _web.posts(store, _web.recording_action(recording, "discard"), clock=clock)


@then("it no longer appears in the default list")
def _(store, recording):
    page = creates_app(store=store).test_client().get("/").get_data(as_text=True)
    assert all(row["id"] != recording.recording_id for row in reads_rows(page, "recording"))


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


@when("I restore it", target_fixture="detail_page")
def _(store, recording, clock):
    return _web.posts(store, _web.recording_action(recording, "restore"), clock=clock)


@then("it returns to the state it was in before it was discarded")
def _(store, recording, detail_page, held_before_discard):
    assert recording.state == "discarded", recording.state
    assert store.loads(Recording, recording.recording_id).state == held_before_discard["state"]
    assert reads_field(detail_page, "state") == held_before_discard["state"]


@then("the Recording's record and analysis artifacts are retained")
def _(store, recording, held_before_discard):
    assert store.loads(Recording, recording.recording_id).state == "discarded"
    now_held = holds(store, recording)
    assert held_before_discard["artifacts"], "nothing was analysed before the discard"
    assert now_held["artifacts"] == held_before_discard["artifacts"]
    assert now_held["blocks"] == held_before_discard["blocks"]
    assert now_held["segments"] == held_before_discard["segments"]


@then("its Segments are intact")
def _(store, recording, detail_page):
    held = store.lists(Segment, recording_id=recording.recording_id)
    listed = reads_rows(detail_page, "segment")
    assert len(listed) == len(held)
    assert [row["segment-state"] for row in listed] == [one.state for one in held]


@then("the source object in the object store is untouched")
def _(store, recording):
    assert names_mutating_operations(object_store) == []
    assert store.loads(Recording, recording.recording_id).object_key == recording.object_key
