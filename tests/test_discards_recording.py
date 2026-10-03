from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sermon.discards_recording import DiscardsRecording, RestoresRecording
from sermon.store import LogEntry, Recording, Segment, opens_store

EARLIER = datetime(2026, 9, 13, 11, 0, tzinfo=UTC)
LATER = EARLIER + timedelta(hours=1)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def a_recording(store, state):
    recording = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recordings/recording_20260913_090014.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(
        LogEntry(
            recording_id=recording.recording_id,
            kind="state_change",
            occurred_at=EARLIER,
            correlation_id=f"analyze:{recording.recording_id}",
            entered_state=state,
        )
    )
    return recording


def test_a_discard_is_not_recorded_as_an_error(store):
    recording = a_recording(store, "awaiting_review")
    DiscardsRecording(store=store, clock=lambda: LATER)(recording)
    discarded = [
        entry
        for entry in store.lists(LogEntry, recording_id=recording.recording_id)
        if entry.entered_state == "discarded"
    ]
    assert [entry.error for entry in discarded] == [None]


def test_restoring_returns_to_the_state_logged_before_the_discard(store):
    recording = a_recording(store, "awaiting_review")
    discarded = DiscardsRecording(store=store, clock=lambda: LATER)(recording)
    restored = RestoresRecording(store=store, clock=lambda: LATER + timedelta(hours=1))(discarded)
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"
    assert restored.state == "awaiting_review"


def test_restoring_after_a_second_discard_reads_the_latest_one(store):
    recording = a_recording(store, "awaiting_review")
    discards = DiscardsRecording(store=store, clock=lambda: LATER)
    restores = RestoresRecording(store=store, clock=lambda: LATER + timedelta(hours=1))
    restored = restores(discards(recording))
    store.saves(
        LogEntry(
            recording_id=recording.recording_id,
            kind="state_change",
            occurred_at=LATER + timedelta(hours=2),
            correlation_id="approve",
            entered_state="reviewed",
        )
    )
    reviewed = store.saves(replace(restored, state="reviewed"))
    again = DiscardsRecording(store=store, clock=lambda: LATER + timedelta(hours=3))(reviewed)
    RestoresRecording(store=store, clock=lambda: LATER + timedelta(hours=4))(again)
    assert store.loads(Recording, recording.recording_id).state == "reviewed"


def test_a_recording_with_no_logged_state_restores_to_discovered(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recordings/recording_20260913_090014.flac",
            state="discovered",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    discarded = DiscardsRecording(store=store, clock=lambda: LATER)(recording)
    RestoresRecording(store=store, clock=lambda: LATER)(discarded)
    assert store.loads(Recording, recording.recording_id).state == "discovered"


def test_a_segment_transition_is_not_taken_for_the_recordings_state(store):
    recording = a_recording(store, "awaiting_review")
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    store.saves(
        LogEntry(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="state_change",
            occurred_at=EARLIER + timedelta(minutes=30),
            correlation_id=f"approve:{segment.segment_id}",
            entered_state="approved",
        )
    )
    discarded = DiscardsRecording(store=store, clock=lambda: LATER)(recording)
    RestoresRecording(store=store, clock=lambda: LATER)(discarded)
    assert store.loads(Recording, recording.recording_id).state == "awaiting_review"
