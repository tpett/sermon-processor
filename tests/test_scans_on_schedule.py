"""The worker's periodic scan: when it runs, what it says, and that it never dies.

No real bucket is reached; `FetchesObject` is the in-memory double the download
tests already use, and the clock is a list the test advances by hand.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from sermon.jobs.downloads_recording import FetchesObject
from sermon.queues_new_recordings import QueuesNewRecordings
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.scans_on_schedule import ScansOnSchedule
from sermon.store import Discovery, Job, Recording, opens_store

START = datetime(2026, 10, 4, 18, tzinfo=UTC)
EVERY = timedelta(hours=3)
FLAC = b"fLaC" + bytes(64)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


class Clock:
    def __init__(self):
        self.moment = START

    def __call__(self):
        return self.moment

    def advances(self, by):
        self.moment += by


def holds(bucket, *stamps):
    for stamp in stamps:
        bucket.stores(
            f"recordings/recording_{stamp}.flac",
            FLAC,
            last_modified=START - timedelta(hours=2),
        )


def reviewed(store, stamp):
    store.saves(
        Recording(
            recording_id=f"recording_{stamp}",
            object_key=f"recordings/recording_{stamp}.flac",
            state="awaiting_review",
            started_at=datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )


def schedule(store, bucket, clock, said, **over):
    return ScansOnSchedule(
        reconciles=over.pop(
            "reconciles",
            ReconcilesBucket(store=store, lists_objects=bucket.lists, clock=clock),
        ),
        queues=QueuesNewRecordings(store=store, clock=clock),
        interval=EVERY,
        clock=clock,
        prints=said.append,
        **over,
    )


def queued(store):
    return sorted(job.recording_id for job in store.lists(Job, kind="download", state="queued"))


def test_the_first_scan_runs_at_once_and_queues_a_missed_webhook(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    reviewed(store, "20260927_095721")
    holds(bucket, "20260927_095721", "20261004_100000")

    assert schedule(store, bucket, clock, said)() is True

    assert queued(store) == ["recording_20261004_100000"]
    assert said == [
        "scheduled scan: discovered 1, queued 1 for download: recording_20261004_100000"
    ]


def test_the_back_catalogue_is_discovered_but_never_queued(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    reviewed(store, "20260927_095721")
    holds(bucket, "20260412_102318", "20260816_102958")

    schedule(store, bucket, clock, said)()

    assert len(store.lists(Recording)) == 3
    assert queued(store) == []
    assert said == ["scheduled scan: discovered 2, queued 0 for download"]


def test_it_waits_out_the_interval_between_scans(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    scans = schedule(store, bucket, clock, said)

    scans()
    clock.advances(EVERY - timedelta(seconds=1))
    assert scans() is False
    clock.advances(timedelta(seconds=1))
    assert scans() is True

    assert len(store.lists(Discovery, kind="scan")) == 2


def test_a_recording_landing_between_scans_is_queued_by_the_next(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    reviewed(store, "20260927_095721")
    scans = schedule(store, bucket, clock, said)
    scans()
    holds(bucket, "20261004_100000")

    clock.advances(EVERY)
    scans()

    assert queued(store) == ["recording_20261004_100000"]


def test_an_unreachable_bucket_is_logged_and_retried_next_interval(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    reviewed(store, "20260927_095721")
    holds(bucket, "20261004_100000")
    bucket.error = "connection reset"
    scans = schedule(store, bucket, clock, said)

    assert scans() is True
    assert said == ["scheduled scan failed: transient; next scan in 3:00:00"]
    assert queued(store) == []

    bucket.error = None
    clock.advances(EVERY)
    scans()
    assert queued(store) == ["recording_20261004_100000"]


def test_a_refused_credential_is_named_as_such(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    bucket.error = "403 Forbidden"

    schedule(store, bucket, clock, said)()

    assert said == ["scheduled scan failed: credentials; next scan in 3:00:00"]


def test_an_unexpected_error_never_escapes_and_the_next_scan_still_runs(store):
    bucket, clock, said = FetchesObject(), Clock(), []
    calls = []

    def explodes():
        calls.append(clock())
        raise sqlite3.OperationalError("database is locked")

    scans = schedule(store, bucket, clock, said, reconciles=explodes)

    assert scans() is True
    assert said == [
        "scheduled scan failed: OperationalError: database is locked; next scan in 3:00:00"
    ]
    clock.advances(EVERY)
    scans()
    assert calls == [START, START + EVERY]


def test_a_failure_while_queueing_never_escapes(store):
    bucket, clock, said = FetchesObject(), Clock(), []

    def explodes():
        raise RuntimeError("no queue")

    scans = ScansOnSchedule(
        reconciles=ReconcilesBucket(store=store, lists_objects=bucket.lists, clock=clock),
        queues=explodes,
        interval=EVERY,
        clock=clock,
        prints=said.append,
    )

    assert scans() is True
    assert said == ["scheduled scan failed: RuntimeError: no queue; next scan in 3:00:00"]
