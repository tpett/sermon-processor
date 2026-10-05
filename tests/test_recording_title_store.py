import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sermon.store import DATABASE_NAME, Recording, RecordingTitle, opens_store

SCHEMA_AT_2E7B55B = Path(__file__).parent / "fixtures" / "schema_at_2e7b55b.sql"


def recording():
    return Recording(
        recording_id="recording_20260913_090014",
        object_key="recordings/recording_20260913_090014.flac",
        state="reviewed",
        started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1,
        kind="class",
    )


def a_database_master_made(data_root):
    """The schema exactly as the code before titles created it, holding one Recording."""
    connection = sqlite3.connect(data_root / DATABASE_NAME)
    with connection:
        connection.executescript(SCHEMA_AT_2E7B55B.read_text())
        connection.execute(
            "INSERT INTO recording (recording_id, object_key, state, started_at, "
            "started_at_source, size_bytes, kind) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "recording_20260913_090014",
                "recordings/recording_20260913_090014.flac",
                "reviewed",
                "2026-09-13T09:00:14+00:00",
                "key",
                1,
                "class",
            ),
        )
    connection.close()


def test_the_fixture_is_a_database_without_titles(tmp_path):
    a_database_master_made(tmp_path)
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    connection.close()
    assert "recording" in tables
    assert "recording_title" not in tables


def test_a_database_made_before_titles_opens_and_can_hold_one(tmp_path):
    a_database_master_made(tmp_path)
    store = opens_store(tmp_path)
    try:
        assert store.loads(Recording, "recording_20260913_090014") == recording()
        assert store.loads(RecordingTitle, "recording_20260913_090014") is None
        store.saves(
            RecordingTitle(
                recording_id="recording_20260913_090014",
                title="Theological Equipping Class - Giving",
                series="Theological Equipping Class",
            )
        )
    finally:
        store.close()
    reopened = opens_store(tmp_path)
    try:
        assert reopened.loads(RecordingTitle, "recording_20260913_090014") == RecordingTitle(
            recording_id="recording_20260913_090014",
            title="Theological Equipping Class - Giving",
            series="Theological Equipping Class",
            edited_by_human=False,
        )
        assert reopened.loads(Recording, "recording_20260913_090014") == recording()
    finally:
        reopened.close()


def test_a_title_names_a_recording_that_exists(tmp_path):
    store = opens_store(tmp_path)
    try:
        try:
            store.saves(RecordingTitle(recording_id="recording_nowhere", title="Members Meeting"))
        except sqlite3.IntegrityError:
            return
        raise AssertionError("a title was stored for a Recording that does not exist")
    finally:
        store.close()
