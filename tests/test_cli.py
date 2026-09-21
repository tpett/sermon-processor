from datetime import UTC, datetime, timedelta

import pytest

from sermon.cli import (
    ENVIRONMENT_FILE,
    lists_bucket,
    reconciles,
    resolves_settings,
    serves,
)
from sermon.jobs.downloads_recording import FetchesObject
from sermon.object_store import ListsBucketObjects
from sermon.store import Recording, opens_store

ENDPOINT = "https://s3.home.tpett.me"
BUCKET = "reformation-recordings"
ACCESS_KEY_ID = "an-access-key-id-that-is-not-real"
SECRET_ACCESS_KEY = "a-secret-access-key-that-is-not-real"
MODEL_ENDPOINT = "http://mac-m1:11434"
FLAC_BYTES = b"fLaC" + bytes(64)
SEEN = "recordings/recording_20260823_103015.flac"
UNSEEN = "recordings/recording_20260816_102958.flac"
FROZEN = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def settings_file(root, **overrides):
    values = {
        "SERMON_DATA_ROOT": str(root / "data"),
        "SERMON_OBJECT_STORE_ENDPOINT": ENDPOINT,
        "SERMON_OBJECT_STORE_BUCKET": BUCKET,
        "SERMON_OBJECT_STORE_ACCESS_KEY_ID": ACCESS_KEY_ID,
        "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": SECRET_ACCESS_KEY,
        "SERMON_MODEL_ENDPOINT": MODEL_ENDPOINT,
        **overrides,
    }
    (root / ENVIRONMENT_FILE).write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return values


def bucket_holding(*keys):
    objects = FetchesObject()
    for key in keys:
        objects.stores(key, FLAC_BYTES, last_modified=FROZEN - timedelta(days=1))
    return objects


class RecordsLines:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    def __str__(self):
        return "\n".join(self.lines)


class RecordsServer:
    def __init__(self):
        self.app = None
        self.host = None
        self.port = None

    def __call__(self, app, host, port):
        self.app = app
        self.host = host
        self.port = port


def test_the_environment_file_supplies_every_setting(tmp_path):
    written = settings_file(tmp_path)
    assert resolves_settings(root=tmp_path, environment={}) == written


def test_the_process_environment_wins_over_the_environment_file(tmp_path):
    settings_file(tmp_path)
    resolved = resolves_settings(
        root=tmp_path, environment={"SERMON_OBJECT_STORE_BUCKET": "another-bucket"}
    )
    assert resolved["SERMON_OBJECT_STORE_BUCKET"] == "another-bucket"
    assert resolved["SERMON_OBJECT_STORE_ENDPOINT"] == ENDPOINT


def test_blank_lines_comments_and_quotes_are_not_settings(tmp_path):
    (tmp_path / ENVIRONMENT_FILE).write_text(
        '\n# the endpoint\nSERMON_OBJECT_STORE_BUCKET="quoted-bucket"\n\n',
        encoding="utf-8",
    )
    assert resolves_settings(root=tmp_path, environment={}) == {
        "SERMON_OBJECT_STORE_BUCKET": "quoted-bucket"
    }


def test_no_environment_file_leaves_the_process_environment_alone(tmp_path):
    assert resolves_settings(root=tmp_path, environment={"SERMON_DATA_ROOT": "/srv"}) == {
        "SERMON_DATA_ROOT": "/srv"
    }


def test_the_listing_is_built_for_the_configured_bucket(tmp_path):
    from sermon.config import ReadsConfiguration

    listing = lists_bucket(ReadsConfiguration(settings_file(tmp_path))())
    assert isinstance(listing, ListsBucketObjects)
    assert listing.bucket == BUCKET


def test_reconciling_discovers_what_the_bucket_holds(tmp_path):
    settings = settings_file(tmp_path)
    assert reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists) == 0
    store = opens_store(settings["SERMON_DATA_ROOT"])
    try:
        assert sorted(item.object_key for item in store.lists(Recording)) == [UNSEEN, SEEN]
    finally:
        store.close()


def test_reconciling_reports_what_it_found(tmp_path):
    prints = RecordsLines()
    reconciles(
        settings=settings_file(tmp_path),
        lists_objects=bucket_holding(SEEN, UNSEEN).lists,
        prints=prints,
    )
    assert BUCKET in str(prints)
    assert "2" in str(prints)


def test_reconciling_reports_a_refused_credential_and_fails(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding(SEEN)
    objects.error = "403 Forbidden"
    outcome = reconciles(
        settings=settings_file(tmp_path), lists_objects=objects.lists, prints=prints
    )
    assert outcome == 1
    assert "credentials" in str(prints)


def test_reconciling_reports_an_unreachable_store_and_fails(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding(SEEN)
    objects.error = "connection reset"
    outcome = reconciles(
        settings=settings_file(tmp_path), lists_objects=objects.lists, prints=prints
    )
    assert outcome == 1
    assert "transient" in str(prints)


def test_reconciling_never_prints_a_credential(tmp_path):
    prints = RecordsLines()
    reconciles(
        settings=settings_file(tmp_path),
        lists_objects=bucket_holding(SEEN).lists,
        prints=prints,
    )
    assert ACCESS_KEY_ID not in str(prints)
    assert SECRET_ACCESS_KEY not in str(prints)


def test_serving_binds_the_configured_host_and_port(tmp_path):
    runs = RecordsServer()
    serves(
        settings=settings_file(tmp_path, SERMON_BIND_HOST="127.0.0.1", SERMON_PORT="8123"),
        lists_objects=bucket_holding().lists,
        runs=runs,
    )
    assert runs.host == "127.0.0.1"
    assert runs.port == 8123


def test_the_served_app_shows_what_reconciliation_discovered(tmp_path):
    settings = settings_file(tmp_path)
    reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists)
    runs = RecordsServer()
    serves(settings=settings, lists_objects=bucket_holding().lists, runs=runs)
    body = runs.app.test_client().get("/api/recordings").get_json()
    assert sorted(row["recording_id"] for row in body["recordings"]) == [
        "recording_20260816_102958",
        "recording_20260823_103015",
    ]


def test_the_served_home_page_names_every_discovered_recording(tmp_path):
    settings = settings_file(tmp_path)
    reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists)
    runs = RecordsServer()
    serves(settings=settings, lists_objects=bucket_holding().lists, runs=runs)
    page = runs.app.test_client().get("/").get_data(as_text=True)
    assert "recording_20260823_103015" in page
    assert "recording_20260816_102958" in page


def test_an_incomplete_environment_is_refused_rather_than_guessed(tmp_path):
    from sermon.config import MissingConfiguration

    with pytest.raises(MissingConfiguration):
        reconciles(settings={"SERMON_DATA_ROOT": str(tmp_path)}, lists_objects=lambda: [])
