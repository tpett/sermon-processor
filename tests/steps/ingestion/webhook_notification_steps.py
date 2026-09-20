from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.store import Job, Recording
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
