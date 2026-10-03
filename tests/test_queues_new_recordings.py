"""Which discovered recordings a scheduled scan may queue for download.

The bucket holds 39 GiB of services already edited and published, so the rule
is a high-water mark: only a recording newer than every one the Processor has
already acted on is queued, oldest first, a few per scan.
"""

from datetime import UTC, datetime, timedelta

import pytest

from sermon.queues_new_recordings import MAX_QUEUED_PER_SCAN, QueuesNewRecordings
from sermon.store import Job, LogEntry, Recording, opens_store

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def recording(store, stamp, state="discovered"):
    started = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    return store.saves(
        Recording(
            recording_id=f"recording_{stamp}",
            object_key=f"recordings/recording_{stamp}.flac",
            state=state,
            started_at=started,
            started_at_source="key",
            size_bytes=1,
        )
    )


def download(store, held, state="succeeded"):
    store.saves(
        Job(
            recording_id=held.recording_id,
            kind="download",
            state=state,
            max_attempts=5,
            dedupe_key=f"download:{held.recording_id}",
            queued_at=NOW - timedelta(days=30),
        )
    )


def queued_ids(store):
    return sorted(
        job.recording_id for job in store.lists(Job, kind="download", state="queued")
    )


def queues(store, **over):
    return QueuesNewRecordings(store=store, clock=lambda: NOW, **over)()


def test_a_recording_newer_than_everything_acted_on_is_queued(store):
    recording(store, "20260927_095721", state="awaiting_review")
    recording(store, "20261004_100000")

    queued = queues(store)

    assert [item.recording_id for item in queued] == ["recording_20261004_100000"]
    assert queued_ids(store) == ["recording_20261004_100000"]


def test_the_back_catalogue_behind_the_mark_is_never_queued(store):
    recording(store, "20260412_102318")
    recording(store, "20260816_102958")
    recording(store, "20260927_095721", state="awaiting_review")

    assert queues(store) == ()
    assert queued_ids(store) == []


def test_nothing_is_queued_while_nothing_has_been_acted_on(store):
    recording(store, "20260927_095721")
    recording(store, "20261004_100000")

    assert queues(store) == ()


def test_a_queued_download_counts_as_acted_on(store):
    older = recording(store, "20260927_095721")
    download(store, older, state="queued")
    recording(store, "20260920_094416")
    recording(store, "20261004_100000")

    assert [item.recording_id for item in queues(store)] == ["recording_20261004_100000"]


def test_a_recording_already_given_a_download_is_not_queued_again(store):
    recording(store, "20260927_095721", state="awaiting_review")
    newer = recording(store, "20261004_100000")
    download(store, newer, state="failed")

    assert queues(store) == ()
    assert len(store.lists(Job, kind="download")) == 1


def test_no_more_than_the_limit_are_queued_and_the_oldest_go_first(store):
    recording(store, "20260927_095721", state="awaiting_review")
    for day in ("20261001", "20261002", "20261003", "20261004"):
        recording(store, f"{day}_100000")

    queued = queues(store)

    assert MAX_QUEUED_PER_SCAN == 2
    assert [item.recording_id for item in queued] == [
        "recording_20261001_100000",
        "recording_20261002_100000",
    ]
    assert queued_ids(store) == [
        "recording_20261001_100000",
        "recording_20261002_100000",
    ]


def test_the_next_scan_takes_the_rest_rather_than_stranding_them(store):
    recording(store, "20260927_095721", state="awaiting_review")
    for day in ("20261001", "20261002", "20261003"):
        recording(store, f"{day}_100000")

    queues(store)
    second = queues(store)

    assert [item.recording_id for item in second] == ["recording_20261003_100000"]


def test_the_limit_is_injectable(store):
    recording(store, "20260927_095721", state="awaiting_review")
    for day in ("20261001", "20261002", "20261003"):
        recording(store, f"{day}_100000")

    assert len(queues(store, limit=1)) == 1


def test_a_recording_dated_in_the_future_is_neither_queued_nor_the_mark(store):
    recording(store, "20260927_095721", state="awaiting_review")
    recording(store, "20990101_100000", state="awaiting_review")
    recording(store, "20380119_031407")
    recording(store, "20261004_100000")

    assert [item.recording_id for item in queues(store)] == ["recording_20261004_100000"]


def test_each_queued_download_is_logged_against_its_recording(store):
    recording(store, "20260927_095721", state="awaiting_review")
    recording(store, "20261004_100000")

    queues(store)

    logged = [
        entry
        for entry in store.lists(LogEntry, recording_id="recording_20261004_100000")
        if entry.kind == "download_queued"
    ]
    assert [(entry.actor, entry.occurred_at) for entry in logged] == [("scheduled scan", NOW)]
