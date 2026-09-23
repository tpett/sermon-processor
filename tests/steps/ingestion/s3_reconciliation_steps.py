from datetime import UTC, date, datetime, timedelta

from pytest_bdd import given, parsers, then, when

from sermon.reconciles_bucket import ReconcilesBucket
from sermon.store import Discovery, Job, Recording, SkippedObject
from sermon.web import creates_app

FLAC_BYTES = b"fLaC" + bytes(64)
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


def bucket(store, object_store, clock):
    cutoff = getattr(store, "_ingest_cutoff", date(2026, 1, 1))
    return ReconcilesBucket(
        store=store,
        lists_objects=object_store.lists,
        clock=clock,
        ingest_cutoff=cutoff,
    )


@given(parsers.parse('it contains a bucket "{name}"'))
def _():
    return None


@given("the Processor scans the bucket on a schedule")
def _(store, object_store, clock):
    store._reconciles = bucket(store, object_store, clock)


@given("the bucket contains:")
def _(object_store, clock, datatable):
    headers = datatable[0]
    for row in datatable[1:]:
        data = dict(zip(headers, row))
        last_modified = clock() - timedelta(hours=1)
        if data.get("last_modified"):
            last_modified = datetime.fromisoformat(data["last_modified"])
            if last_modified.tzinfo is None:
                last_modified = last_modified.replace(tzinfo=UTC)
        body = FLAC_BYTES
        object_store.stores(
            data["object_key"],
            body,
            last_modified=last_modified,
            size_bytes=int(data["size_bytes"]) if data.get("size_bytes") else len(body),
        )


@given(parsers.parse('the Processor has never seen "{object_key}"'))
def _(store, object_key):
    assert store.lists(Recording, object_key=object_key) == []


@when("the reconciliation scan runs")
def _(store, object_store, clock):
    bucket(store, object_store, clock)()


@then(parsers.parse('a Recording is created for "{object_key}"'))
def _(store, object_key):
    recordings = store.lists(Recording, object_key=object_key)
    assert len(recordings) == 1
    assert recordings[0].state == "discovered"


@then(parsers.parse('no duplicate is created for "{object_key}"'))
def _(store, object_key):
    assert len(store.lists(Recording, object_key=object_key)) == 1


@given(parsers.parse('the bucket contains "{object_key}" modified {seconds:d} seconds ago'))
def _(object_store, clock, object_key, seconds):
    object_store.stores(
        object_key,
        FLAC_BYTES,
        last_modified=clock() - timedelta(seconds=seconds),
    )


@then("no Recording is created yet")
def _(store):
    assert store.lists(Recording) == []


@then("the object is reconsidered on the next scan")
def _(store, object_store):
    assert store.lists(SkippedObject) == []
    assert object_store.lists()


@then("no Recordings are created")
def _(store):
    assert store.lists(Recording) == []


@then("the sidecar metadata file is associated with its parent recording if one exists")
def _(store):
    parents = [item for item in store.lists(Recording) if item.sidecar_present]
    skipped = store.lists(SkippedObject)
    assert parents or skipped


@given("the Processor's ingest cutoff date is its deployment date")
def _(store):
    store._ingest_cutoff = date(2026, 6, 1)


@given("the bucket contains a recording from before that date")
def _(object_store, clock):
    object_store.stores(
        "recordings/recording_20240107_101500.flac",
        FLAC_BYTES,
        last_modified=clock() - timedelta(hours=1),
    )


@then("no Recording is created for it")
def _(store):
    assert store.lists(Recording) == []


@then("it can still be ingested manually for testing")
def _(store, object_store, clock):
    recording = bucket(store, object_store, clock).ingests(
        "recordings/recording_20240107_101500.flac"
    )
    assert recording.state == "discovered"


@given("the object store returns connection errors")
def _(object_store):
    object_store.error = "connection"


@then("the scan fails without changing any Recording state")
def _(store):
    assert store.lists(Recording) == []
    assert store.lists(Discovery, kind="scan")[0].failure == "transient"


@then("the failure is surfaced on the system health view")
def _(store):
    health = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()
    assert health.get("scan_failure") == "transient" or health.get("object_store") != "healthy"


@given("the reconciliation scan skips an object")
def _(store, object_store, clock):
    object_store.stores("recordings/README.txt", b"readme", last_modified=clock() - timedelta(hours=1))
    bucket(store, object_store, clock)()


@then("the object key and the reason are recorded")
def _(store):
    skipped = store.lists(SkippedObject)
    assert skipped
    assert skipped[0].object_key
    assert skipped[0].reason


@then("an operator can see every object the Processor has ever skipped")
def _(store):
    assert store.lists(SkippedObject)


@then("no alert is raised for it")
def _(store):
    from sermon.store import Notification

    assert store.lists(Notification) == []


@given(parsers.parse('an object "{key}"'))
def _(object_store, clock, key):
    object_store.stores(key, b"x", last_modified=clock() - timedelta(hours=1))


@then(parsers.parse('it is recorded as skipped with the reason "{reason}"'))
def _(store, reason):
    skipped = store.lists(SkippedObject)
    assert skipped
    assert skipped[0].reason == reason


@given(parsers.parse('the object store responds with "{error}"'))
def _(object_store, error):
    object_store.error = error


@then("it is not retried as a transient failure")
def _(store):
    discovery = store.lists(Discovery, kind="scan")[0]
    assert discovery.failure == "credentials"


@then("it is surfaced on the system health view as a credential problem")
def _(store):
    health = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()
    assert health.get("scan_failure") == "credentials"


@when(
    parsers.parse('they submit the object key "{object_key}" for manual ingestion'),
    target_fixture="ingest_response",
)
def _(store, object_store, clock, object_key):
    return (
        creates_app(store=store, clock=clock, lists_objects=object_store.lists)
        .test_client()
        .post("/api/ingest", json={"object_key": object_key})
    )


@then("a Recording is created regardless of the ingest cutoff date")
def _(store):
    recordings = store.lists(Recording)
    assert recordings
    assert recordings[0].recording_id == "recording_20240107_101500"


@then("this is how the sample corpus is loaded for the accuracy suite")
def _(store):
    assert store.lists(Recording)
