"""A recording lands in the bucket and the reviewer is told, with nobody at a terminal.

The worker's loop runs the scheduled scan, the download, the analysis and the
notification in turn. Every seam that would reach the bucket, ffprobe, a
transcriber or a model is a double; the loop, the queue and the store are real.
"""

from argparse import Namespace
from datetime import UTC, datetime, timedelta

import pytest

from sermon.cli import drains
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.queues_new_recordings import QueuesNewRecordings
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.scans_on_schedule import ScansOnSchedule
from sermon.sends_notification import SendsNotification
from sermon.store import Job, Notification, Recording, Reviewer, Segment, opens_store

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)
LANDED = "recording_20261004_100000"
FLAC = b"fLaC" + bytes(64)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


class Stops(BaseException):
    pass


def stops_when_idle(*_):
    raise Stops


def proposes_a_sermon(store):
    def analyses(recording):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="proposed",
                span_start_seconds=1800.0,
                span_end_seconds=4200.0,
                punch_in_seconds=1800.0,
                punch_out_seconds=4200.0,
            )
        )

    return analyses


def finds_nothing(_recording):
    return None


def runs_itself(store, analyses, sent):
    clock = lambda: NOW  # noqa: E731
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    store.saves(
        Recording(
            recording_id="recording_20260927_095721",
            object_key="recordings/recording_20260927_095721.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    bucket = FetchesObject()
    for stamp in ("20260412_102318", "20260927_095721", "20261004_100000"):
        bucket.stores(
            f"recordings/recording_{stamp}.flac", FLAC, last_modified=NOW - timedelta(hours=2)
        )
    runs = RunsQueuedJobs(
        store=store,
        clock=clock,
        downloads=RunsDownloadJob(
            store=store,
            fetches=bucket,
            probes=ProbesAudio(duration_seconds=5400.0, sample_rate=44100, channels=2),
            clock=clock,
        ),
        analyzes=RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store, sends=sent.append),
            analyses=analyses,
            clock=clock,
        ),
        renders=stops_when_idle,
    )
    scans = ScansOnSchedule(
        reconciles=ReconcilesBucket(store=store, lists_objects=bucket.lists, clock=clock),
        queues=QueuesNewRecordings(store=store, clock=clock),
        interval=timedelta(hours=3),
        clock=clock,
        prints=lambda _line: None,
    )
    asked = Namespace(once=False, limit=0, poll=5.0)
    with pytest.raises(Stops):
        drains(runs, asked, lambda _line: None, stops_when_idle, scans=scans)
    return bucket


def test_a_landed_recording_is_downloaded_analysed_and_the_reviewer_told(store):
    sent = []
    runs_itself(store, proposes_a_sermon(store), sent)

    assert store.loads(Recording, LANDED).state == "awaiting_review"
    assert [(job.kind, job.state) for job in store.lists(Job, recording_id=LANDED)] == [
        ("download", "succeeded"),
        ("analyze", "succeeded"),
    ]
    told = store.lists(Notification, recording_id=LANDED)
    assert [(item.kind, item.recipient) for item in told] == [("segment_proposed", "reviewer")]
    assert sent == told


def test_only_the_landed_recording_is_fetched(store):
    bucket = runs_itself(store, proposes_a_sermon(store), [])

    assert [path.parent.name for path in bucket.destinations] == [LANDED]
    assert store.loads(Recording, "recording_20260412_102318").state == "discovered"
    assert store.lists(Job, recording_id="recording_20260412_102318") == []


def test_an_analysis_that_proposes_nothing_tells_nobody(store):
    sent = []
    runs_itself(store, finds_nothing, sent)

    assert store.loads(Recording, LANDED).state == "awaiting_review"
    assert store.lists(Notification) == []
    assert sent == []
