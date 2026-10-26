from datetime import UTC, datetime

import pytest

from sermon.skips_segment import SkipsSegment
from sermon.store import LogEntry, Recording, Segment, opens_store

RECORDING_ID = "recording_20260913_090014"
MOMENT = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def segment(store):
    store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"2026/09/13/{RECORDING_ID}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    return store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="proposed",
            span_start_seconds=5320.0,
            span_end_seconds=11520.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
            boundary_source="model",
        )
    )


def entries_for(store, segment):
    return [
        entry
        for entry in store.lists(LogEntry, recording_id=RECORDING_ID)
        if entry.segment_id == segment.segment_id and entry.entered_state == "skipped"
    ]


def test_skipping_logs_who_skipped_and_when(store, segment):
    SkipsSegment(store=store, clock=lambda: MOMENT)(segment, actor="pastor@reformation.example")
    (entry,) = entries_for(store, segment)
    assert (entry.kind, entry.actor, entry.occurred_at) == (
        "state_change",
        "pastor@reformation.example",
        MOMENT,
    )
    assert entry.correlation_id == f"skip:{segment.segment_id}"


def test_skipping_without_naming_anyone_is_the_reviewers(store, segment):
    SkipsSegment(store=store, clock=lambda: MOMENT)(segment)
    assert [entry.actor for entry in entries_for(store, segment)] == ["reviewer"]
