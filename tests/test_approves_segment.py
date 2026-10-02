from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from sermon.approves_segment import ApprovesSegment, ReviewSession
from sermon.store import CorpusPair, Job, Proposal, Recording, Segment, opens_store

FROZEN = datetime(2026, 9, 13, 12, 41, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def sermon_segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=6967.0,
            span_end_seconds=9910.0,
            punch_in_seconds=6967.0,
            punch_out_seconds=9910.0,
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
    return segment


def test_approval_queues_a_render_job_and_marks_the_segment_approved(store):
    segment = sermon_segment(store)
    approved = ApprovesSegment(store=store, clock=lambda: FROZEN)(segment)
    stored = store.loads(Segment, approved.segment_id)
    assert stored.state == "approved"
    assert stored.disposition_at == FROZEN
    jobs = store.lists(Job, segment_id=stored.segment_id, kind="render")
    assert len(jobs) == 1
    assert jobs[0].state == "queued"
    assert jobs[0].recording_id == stored.recording_id
    assert jobs[0].dedupe_key == f"render:{stored.segment_id}"
    assert jobs[0].queued_at == FROZEN


def test_preview_does_not_open_the_waveform_editor():
    session = ReviewSession()
    session.previews_punch_in(None)
    session.previews_punch_out(None)
    assert session.waveform_editor_opened is False


def test_approving_a_boundary_the_reviewer_moved_leaves_a_labelled_pair(store):
    segment = sermon_segment(store)
    moved = store.saves(
        replace(segment, boundary_source="human", punch_in_seconds=6970.5)
    )
    ApprovesSegment(store=store, clock=lambda: FROZEN)(moved)
    pairs = store.lists(CorpusPair, recording_id=moved.recording_id)
    assert [(pair.provenance, pair.alignment) for pair in pairs] == [("human", "aligned")]
    assert (pairs[0].punch_in_seconds, pairs[0].punch_out_seconds) == (6970.5, 9910.0)
    assert (pairs[0].classification, pairs[0].labelled) == ("sermon", True)


def test_approving_an_untouched_proposal_leaves_no_labelled_pair(store):
    segment = sermon_segment(store)
    untouched = store.saves(replace(segment, boundary_source="model"))
    ApprovesSegment(store=store, clock=lambda: FROZEN)(untouched)
    assert store.lists(CorpusPair) == []


def test_approving_a_refined_boundary_leaves_no_labelled_pair(store):
    segment = sermon_segment(store)
    refined = store.saves(replace(segment, boundary_source="model-in/refined-out"))
    ApprovesSegment(store=store, clock=lambda: FROZEN)(refined)
    assert store.lists(CorpusPair) == []


def test_approving_a_publication_places_it_on_the_recordings_own_date(store):
    offered = store.saves(
        replace(sermon_segment(store), intent="publish", label="Hebrews 12.25-29")
    )
    approved = ApprovesSegment(store=store, clock=lambda: FROZEN)(offered)
    assert store.loads(Segment, approved.segment_id).publication_date == date(2026, 9, 13)


def test_a_publication_date_the_reviewer_entered_survives_approval(store):
    entered = store.saves(
        replace(
            sermon_segment(store),
            intent="publish",
            label="Hebrews 12.25-29",
            publication_date=date(2026, 9, 20),
        )
    )
    approved = ApprovesSegment(store=store, clock=lambda: FROZEN)(entered)
    assert store.loads(Segment, approved.segment_id).publication_date == date(2026, 9, 20)


def test_an_archival_segment_is_placed_on_the_date_its_filename_is_built_from(store):
    offered = store.saves(replace(sermon_segment(store), intent="archive"))
    approved = ApprovesSegment(store=store, clock=lambda: FROZEN)(offered)
    assert store.loads(Segment, approved.segment_id).publication_date == date(2026, 9, 13)
