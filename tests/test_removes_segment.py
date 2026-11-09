from datetime import UTC, datetime

import pytest

from sermon.removes_segment import (
    IN_FLIGHT,
    PUBLISHED,
    RemovesSegment,
    SegmentCannotBeRemoved,
)
from sermon.store import Artifact, Job, LogEntry, Proposal, Recording, Segment, SpeakerProfile, opens_store

RECORDING_ID = "recording_20261107_082943"
MOMENT = datetime(2026, 11, 9, 21, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def recording(store):
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"2026/11/07/{RECORDING_ID}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 11, 7, 13, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )


def segment(store, **overrides):
    fields = dict(
        recording_id=RECORDING_ID,
        classification="sermon",
        state="proposed",
        span_start_seconds=0.0,
        span_end_seconds=541.0,
        punch_in_seconds=0.99,
        punch_out_seconds=541.36,
        boundary_source="human",
    )
    fields.update(overrides)
    return store.saves(Segment(**fields))


def test_an_unpublished_segment_is_removed_and_the_source_stays(store):
    recording(store)
    held = segment(store)

    removed = RemovesSegment(store=store, clock=lambda: MOMENT)(held, actor="pastor@reformation.example")

    assert removed == held.segment_id
    assert store.loads(Segment, held.segment_id) is None
    assert store.loads(Recording, RECORDING_ID).object_key.endswith(".flac")
    entry = next(item for item in store.lists(LogEntry, recording_id=RECORDING_ID) if item.kind == "segment_removed")
    assert (entry.kind, entry.actor, entry.segment_id) == (
        "segment_removed",
        "pastor@reformation.example",
        None,
    )
    assert entry.punch_in_seconds == pytest.approx(0.99)


def test_a_published_segment_cannot_be_removed(store):
    recording(store)
    held = segment(store, state="complete")
    store.saves(
        Artifact(
            recording_id=RECORDING_ID,
            segment_id=held.segment_id,
            kind="rendered_mp3",
            path="published/kept.mp3",
            size_bytes=1,
            checksum="ac5f0d2b9e1c4477",
        )
    )

    with pytest.raises(SegmentCannotBeRemoved, match=PUBLISHED):
        RemovesSegment(store=store)(held)

    assert store.loads(Segment, held.segment_id) is not None


def test_a_segment_that_is_rendering_cannot_be_removed(store):
    recording(store)
    held = segment(store, state="processing")

    with pytest.raises(SegmentCannotBeRemoved, match=IN_FLIGHT):
        RemovesSegment(store=store)(held)


def test_a_failed_render_can_be_removed_without_leaving_its_references(store):
    recording(store)
    held = segment(store, state="processing_failed")
    job = store.saves(
        Job(
            recording_id=RECORDING_ID,
            segment_id=held.segment_id,
            kind="render",
            state="failed",
            attempts=1,
            max_attempts=3,
            dedupe_key=f"render:{RECORDING_ID}:{held.segment_id}",
            last_error="ffmpeg exited 1",
            queued_at=MOMENT,
        )
    )
    proposal = store.saves(
        Proposal(
            segment_id=held.segment_id,
            classification_confidence="low",
            boundary_confidence="low",
            punch_in_grade="moderate",
            punch_out_grade="moderate",
        )
    )
    store.saves(
        LogEntry(
            recording_id=RECORDING_ID,
            segment_id=held.segment_id,
            job_id=job.job_id,
            proposal_id=proposal.proposal_id,
            kind="job_attempt",
            occurred_at=MOMENT,
            correlation_id=job.dedupe_key,
            error="ffmpeg exited 1",
        )
    )
    profile = store.saves(
        SpeakerProfile(name="Travis", embedding=b"voice", enrolled_from=(held.segment_id,))
    )

    RemovesSegment(store=store, clock=lambda: MOMENT)(held)

    assert store.loads(Segment, held.segment_id) is None
    assert store.loads(Job, job.job_id) is None
    assert store.loads(Proposal, proposal.proposal_id) is None
    attempt = next(item for item in store.lists(LogEntry, recording_id=RECORDING_ID) if item.kind == "job_attempt")
    assert (attempt.segment_id, attempt.job_id, attempt.proposal_id) == (None, None, None)
    assert store.loads(SpeakerProfile, profile.speaker_profile_id).enrolled_from == ()
