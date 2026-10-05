import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sermon.store import DATABASE_NAME, LogEntry, RemovedSpan, Segment, opens_store

WRITTEN_BY_MASTER = Path(__file__).parent / "fixtures" / "store_at_2e7b55b.sql"
PUBLISHED_SEGMENT = 12
BUMP = RemovedSpan(start_seconds=3060.0, end_seconds=3060.7)


@pytest.fixture
def older_root(tmp_path):
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    connection.executescript(WRITTEN_BY_MASTER.read_text())
    connection.close()
    return tmp_path


def stored_tables(root):
    connection = sqlite3.connect(root / DATABASE_NAME)
    try:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()


def test_the_fixture_predates_removed_spans(older_root):
    tables = stored_tables(older_root)
    assert "segment" in tables
    assert "segment_removed_span" not in tables
    assert "log_entry_removed_span" not in tables


def test_a_database_written_before_removed_spans_opens_and_keeps_its_rows(older_root):
    store = opens_store(older_root)
    try:
        segments = store.lists(Segment)
        published = store.loads(Segment, PUBLISHED_SEGMENT)
        assert len(segments) == 14
        assert (published.state, published.label) == ("complete", "Hebrews 13.7-8")
        assert all(segment.removed_spans == () for segment in segments)
        assert len(store.lists(LogEntry)) == 9
    finally:
        store.close()
    assert {"segment_removed_span", "log_entry_removed_span"} <= stored_tables(older_root)


def test_removed_spans_are_kept_in_a_database_written_before_them(older_root):
    store = opens_store(older_root)
    try:
        held = store.loads(Segment, PUBLISHED_SEGMENT)
        store.saves(replace(held, removed_spans=(BUMP,)))
        store.saves(
            LogEntry(
                recording_id=held.recording_id,
                segment_id=held.segment_id,
                kind="span_removed",
                occurred_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
                correlation_id=f"remove-span:{held.segment_id}",
                actor="reviewer",
                removed_spans=(BUMP,),
            )
        )
    finally:
        store.close()
    reopened = opens_store(older_root)
    try:
        assert reopened.loads(Segment, PUBLISHED_SEGMENT).removed_spans == (BUMP,)
        assert reopened.lists(LogEntry, kind="span_removed")[0].removed_spans == (BUMP,)
    finally:
        reopened.close()
