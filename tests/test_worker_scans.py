"""`sermon-work` runs the scheduled scan only when an interval is configured.

The bucket and the fetch are doubles, and the fetch double stops the worker the
moment it is asked for anything, so no download runs past its first request.
"""

from datetime import UTC, datetime, timedelta

import pytest

from sermon.cli import ENVIRONMENT_FILE, parses_work_command, works
from sermon.jobs.downloads_recording import FetchesObject
from sermon.pipeline import classify, segments
from sermon.scans_on_schedule import SCAN_INTERVAL
from sermon.store import Discovery, Job, LogEntry, Recording, opens_store

FLAC = b"fLaC" + bytes(64)
LANDED = "recording_20261004_100000"


class Stops(BaseException):
    pass


def stops(*_):
    raise Stops


class Watches:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return []


class StopsAtTheFetch:
    def __init__(self):
        self.asked = []

    def __call__(self, object_key, _destination):
        self.asked.append(object_key)
        raise Stops


@pytest.fixture(autouse=True)
def keeps_pipeline_roots(monkeypatch):
    for module, name in (
        (classify, "ENDPOINT"),
        (classify, "DATA"),
        (classify, "PROMPTS"),
        (segments, "DATA_ROOT"),
    ):
        monkeypatch.setattr(module, name, getattr(module, name))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    values = {
        "SERMON_DATA_ROOT": str(tmp_path / "data"),
        "SERMON_OBJECT_STORE_ENDPOINT": "https://object-store.invalid",
        "SERMON_OBJECT_STORE_BUCKET": "sermons",
        "SERMON_OBJECT_STORE_ACCESS_KEY_ID": "not-a-real-key",
        "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": "not-a-real-secret",
        "SERMON_MODEL_ENDPOINT": "http://model-host.invalid:11434",
    }
    store = opens_store(tmp_path / "data")
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
    store.close()
    return values


def bucket_holding(*stamps):
    bucket = FetchesObject()
    for stamp in stamps:
        bucket.stores(
            f"recordings/recording_{stamp}.flac",
            FLAC,
            last_modified=datetime.now(UTC) - timedelta(hours=2),
        )
    return bucket


def stored(settings):
    return opens_store(settings["SERMON_DATA_ROOT"])


def test_the_interval_is_an_option_in_seconds():
    assert parses_work_command(["--scan-every", "10800"], print).scan_every == 10800.0
    assert parses_work_command([], print).scan_every is None


def test_the_usage_names_the_scan_option():
    said = []
    parses_work_command(["--no-such-option"], said.append)
    assert "[--scan-every SECONDS]" in said[0]


def test_a_worker_given_an_interval_scans_and_queues_the_landed_recording(settings):
    bucket, said = bucket_holding("20260412_102318", LANDED[len("recording_"):]), []
    fetch = StopsAtTheFetch()

    with pytest.raises(Stops):
        works(
            settings=settings,
            arguments=["--scan-every", "10800"],
            prints=said.append,
            sleeps=stops,
            lists_objects=bucket.lists,
            fetches_object=fetch,
        )

    assert f"scheduled scan: discovered 2, queued 1 for download: {LANDED}" in said
    assert fetch.asked == [f"recordings/{LANDED}.flac"]
    store = stored(settings)
    try:
        assert [job.kind for job in store.lists(Job, recording_id=LANDED)] == ["download"]
        assert store.lists(Job, recording_id="recording_20260412_102318") == []
        assert [entry.kind for entry in store.lists(LogEntry, recording_id=LANDED)][:1] == [
            "download_queued"
        ]
    finally:
        store.close()


def test_the_interval_can_come_from_the_environment(settings):
    bucket, said = bucket_holding(LANDED[len("recording_"):]), []

    with pytest.raises(Stops):
        works(
            settings={**settings, SCAN_INTERVAL: "10800"},
            arguments=[],
            prints=said.append,
            sleeps=stops,
            lists_objects=bucket.lists,
            fetches_object=stops,
        )

    assert f"scheduled scan: discovered 1, queued 1 for download: {LANDED}" in said


def test_the_environment_file_can_set_the_interval(settings, tmp_path):
    (tmp_path / ENVIRONMENT_FILE).write_text(
        "\n".join(f"{name}={value}" for name, value in {**settings, SCAN_INTERVAL: "60"}.items()),
        encoding="utf-8",
    )
    said = []

    with pytest.raises(Stops):
        works(
            arguments=[],
            prints=said.append,
            sleeps=stops,
            lists_objects=bucket_holding().lists,
            fetches_object=stops,
        )

    assert "scheduled scan: discovered 0, queued 0 for download" in said


@pytest.mark.parametrize("configured", [None, "0", ""])
def test_no_interval_means_no_scan(settings, configured):
    over = {} if configured is None else {SCAN_INTERVAL: configured}
    said, listing = [], Watches()

    with pytest.raises(Stops):
        works(
            settings={**settings, **over},
            arguments=[],
            prints=said.append,
            sleeps=stops,
            lists_objects=listing,
            fetches_object=stops,
        )

    assert listing.calls == 0
    assert not [line for line in said if "scheduled scan" in line]
    store = stored(settings)
    try:
        assert store.lists(Discovery) == []
    finally:
        store.close()


def test_the_option_wins_over_the_environment(settings):
    said, listing = [], Watches()

    with pytest.raises(Stops):
        works(
            settings={**settings, SCAN_INTERVAL: "10800"},
            arguments=["--scan-every", "0"],
            prints=said.append,
            sleeps=stops,
            lists_objects=listing,
            fetches_object=stops,
        )

    assert listing.calls == 0
    assert not [line for line in said if "scheduled scan" in line]


@pytest.mark.parametrize("bounded", [["--once"], ["--limit", "3"]])
def test_a_bounded_run_never_scans(settings, bounded):
    said, listing = [], Watches()

    assert (
        works(
            settings=settings,
            arguments=["--scan-every", "10800", *bounded],
            prints=said.append,
            sleeps=stops,
            lists_objects=listing,
            fetches_object=stops,
        )
        == 0
    )
    assert listing.calls == 0
    assert said == ["nothing queued"]


def test_an_interval_that_is_not_a_number_is_refused(settings):
    said = []

    assert (
        works(
            settings={**settings, SCAN_INTERVAL: "three hours"},
            arguments=[],
            prints=said.append,
            sleeps=stops,
            lists_objects=stops,
            fetches_object=stops,
        )
        == 1
    )
    assert said == [f"{SCAN_INTERVAL} must be a number of seconds, not 'three hours'"]


def test_the_scan_honours_the_configured_ingest_cutoff(settings):
    bucket, said = bucket_holding("20260412_102318", LANDED[len("recording_"):]), []

    with pytest.raises(Stops):
        works(
            settings={**settings, "SERMON_INGEST_CUTOFF": "2026-10-01"},
            arguments=["--scan-every", "10800"],
            prints=said.append,
            sleeps=stops,
            lists_objects=bucket.lists,
            fetches_object=stops,
        )

    assert f"scheduled scan: discovered 1, queued 1 for download: {LANDED}" in said
