from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.store import Discovery, Job, Recording
from sermon.web import creates_app

WEBHOOK_WITHOUT_HOST_IDENTITY = {
    "event": "recording.uploaded",
    "bucket": "sermons",
    "object_key": "recordings/recording_20260823_102952.flac",
    "metadata_key": "recordings/recording_20260823_102952.flac.meta.json",
    "size_bytes": 841368564,
    "md5": "8f14e45fceea167a5a36dedd4bea2543",
    "recorded_at": "2026-08-23T10:29:52-05:00",
    "duration": 6268.95,
    "sample_rate": 44100,
    "channels": 2,
}


def posts_webhook(processor_client, webhook_endpoint, payload):
    method, path = webhook_endpoint.split(" ", 1)
    return processor_client.open(path, method=method, json=payload)


@given("the Sermon Processor is running", target_fixture="processor_client")
def _(store):
    return creates_app(store=store).test_client()


@given(parsers.parse('the webhook endpoint is "{webhook_endpoint}"'), target_fixture="webhook_endpoint")
def _(webhook_endpoint):
    return webhook_endpoint


@given("the Recorder reaches it over the tailnet")
def _():
    return None


@when("the Recorder sends a webhook with the payload:", target_fixture="processor_response")
def _(processor_client, webhook_endpoint, datatable):
    return posts_webhook(processor_client, webhook_endpoint, dict(datatable[1:]))


@when("the Recorder sends a webhook with no host identity", target_fixture="processor_response")
def _(processor_client, webhook_endpoint):
    return posts_webhook(processor_client, webhook_endpoint, WEBHOOK_WITHOUT_HOST_IDENTITY)


@then(parsers.parse('the Processor responds with "{status}"'))
def _(processor_response, status):
    assert processor_response.status.lower() == status.lower()


@then(parsers.parse('a Recording is created with the state "{state}"'))
def _(store, state):
    recordings = store.lists(Recording)
    assert len(recordings) == 1
    recording = recordings[0]
    assert recording.state == state
    assert recording.recording_id == "recording_20260823_102952"
    assert recording.object_key == "recordings/recording_20260823_102952.flac"
    assert recording.started_at == datetime(2026, 8, 23, 10, 29, 52, tzinfo=UTC)
    assert recording.started_at_source == "key"
    assert recording.size_bytes == 841368564
    assert recording.local_path is None


@then("the Recording is queued for download")
def _(store):
    recording = store.lists(Recording)[0]
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="download")
    assert len(jobs) == 1
    assert jobs[0].state == "queued"
    assert jobs[0].segment_id is None
    assert jobs[0].max_attempts == 5
    assert jobs[0].dedupe_key == f"download:{recording.recording_id}"


@then("no audio has been downloaded yet")
def _(store):
    assert store.lists(Recording)[0].local_path is None


@then("the Recording is created without a device identity")
def _(store):
    recordings = store.lists(Recording)
    assert len(recordings) == 1
    assert recordings[0].capture_device is None


IDENTICAL = {
    "event": "recording.uploaded",
    "bucket": "sermons",
    "object_key": "recordings/recording_20260823_102952.flac",
    "size_bytes": 841368564,
    "recorded_at": "2026-08-23T10:29:52-05:00",
}


@given(parsers.parse('a Recording exists for object key "{object_key}"'))
def _(store, object_key, clock):
    from pathlib import Path

    recording_id = Path(object_key).stem
    store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state="discovered",
            started_at=datetime.strptime(recording_id, "recording_%Y%m%d_%H%M%S").replace(
                tzinfo=UTC
            ),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(
        Job(
            recording_id=recording_id,
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{recording_id}",
            queued_at=clock(),
        )
    )


@when("the Recorder sends an identical webhook for that object key", target_fixture="processor_response")
def _(processor_client, webhook_endpoint):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL)


@then("no duplicate Recording is created")
def _(store):
    assert len(store.lists(Recording)) == 1


@then("no additional download is queued")
def _(store):
    assert len(store.lists(Job, kind="download")) == 1


@given("the reconciliation scan has just created a Recording for an object key")
def _(store):
    from pathlib import Path

    object_key = IDENTICAL["object_key"]
    recording_id = Path(object_key).stem
    store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state="discovered",
            started_at=datetime.strptime(recording_id, "recording_%Y%m%d_%H%M%S").replace(
                tzinfo=UTC
            ),
            started_at_source="key",
            size_bytes=1,
        )
    )


@when("a webhook arrives for the same object key", target_fixture="processor_response")
def _(processor_client, webhook_endpoint):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL)


@then("whichever arrived first owns the Recording")
def _(store):
    assert len(store.lists(Recording)) == 1


@when("two identical webhooks are handled concurrently", target_fixture="processor_response")
def _(processor_client, webhook_endpoint):
    first = posts_webhook(processor_client, webhook_endpoint, IDENTICAL)
    posts_webhook(processor_client, webhook_endpoint, IDENTICAL)
    return first


@then("exactly one Recording exists afterwards")
def _(store):
    assert len(store.lists(Recording)) == 1


@then("exactly one download is queued")
def _(store):
    assert len(store.lists(Job, kind="download")) == 1


@when(parsers.parse('the Recorder sends a webhook with "{field}" omitted'), target_fixture="processor_response")
def _(processor_client, webhook_endpoint, field):
    payload = dict(IDENTICAL)
    payload.pop(field, None)
    return posts_webhook(processor_client, webhook_endpoint, payload)


@then(parsers.parse('the response body names the missing field "{field}"'))
def _(processor_response, field):
    assert processor_response.get_json()["missing"] == field


@then("no Recording is created")
def _(store):
    assert store.lists(Recording) == []


@when(parsers.parse('the Recorder sends a webhook with event "{event}"'), target_fixture="processor_response")
def _(processor_client, webhook_endpoint, event):
    payload = dict(IDENTICAL)
    payload["event"] = event
    return posts_webhook(processor_client, webhook_endpoint, payload)


@then("the ignored event type is logged")
def _(store):
    discoveries = store.lists(Discovery, kind="webhook")
    assert discoveries
    assert discoveries[-1].event == "recording.started"


@given("the object store has not yet made the object available")
def _(object_store):
    return object_store


@given("the object store is a Garage S3 instance reachable over the tailnet")
def _():
    return None


@when("the Recorder sends a webhook for that object key", target_fixture="processor_response")
def _(processor_client, webhook_endpoint):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL)


@then("the download is queued anyway")
def _(store):
    assert store.lists(Job, kind="download")


@then("the download job retries until the object appears")
def _(store, object_store, clock):
    from sermon.jobs.downloads_recording import ProbesAudio, RunsDownloadJob

    probes = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
    RunsDownloadJob(store=store, fetches=object_store, probes=probes, clock=clock)()
    recording = store.lists(Recording)[0]
    object_store.stores(recording.object_key, b"fLaC" + bytes(64))
    RunsDownloadJob(store=store, fetches=object_store, probes=probes, clock=clock)()
    assert store.loads(Recording, recording.recording_id).state == "downloaded"


@then("the download is retried until the object becomes readable")
def _(store, object_store, clock):
    from sermon.jobs.downloads_recording import ProbesAudio, RunsDownloadJob

    probes = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
    RunsDownloadJob(store=store, fetches=object_store, probes=probes, clock=clock)()
    recording = store.lists(Recording)[0]
    assert recording.state != "ingest_failed"
    object_store.stores(recording.object_key, b"fLaC" + bytes(64))
    RunsDownloadJob(store=store, fetches=object_store, probes=probes, clock=clock)()
    assert store.loads(Recording, recording.recording_id).state == "downloaded"


@then(parsers.parse('the Recording does not enter "{state}" before {attempts:d} attempts'))
def _(store, state, attempts):
    recording = store.lists(Recording)[0]
    job = store.lists(Job, kind="download")[0]
    assert recording.state != state
    assert job.attempts < attempts


@then("a Recording is created for it")
def _(store):
    assert store.lists(Recording)


@then("it is queued for download")
def _(store):
    assert store.lists(Job, kind="download")
