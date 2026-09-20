from pytest_bdd import given, parsers, then, when

from sermon.store import Job, Recording
from sermon.web import creates_app

WEBHOOK_WITHOUT_HOST = {
    "event": "recording.uploaded",
    "bucket": "sermons",
    "object_key": "recordings/recording_20260823_102952.flac",
    "metadata_key": "recordings/recording_20260823_102952.flac.meta.json",
    "size_bytes": "841368564",
    "md5": "8f14e45fceea167a5a36dedd4bea2543",
    "recorded_at": "2026-08-23T10:29:52-05:00",
    "duration": "6268.95",
    "sample_rate": "44100",
    "channels": "2",
}


@given("the Sermon Processor is running", target_fixture="processor")
def _(store):
    return creates_app(store=store).test_client()


@given(parsers.parse('the webhook endpoint is "{endpoint}"'), target_fixture="webhook_endpoint")
def _(endpoint):
    return endpoint


@given("the Recorder reaches it over the tailnet")
def _():
    return None


@when("the Recorder sends a webhook with the payload:", target_fixture="webhook_response")
def _(processor, webhook_endpoint, datatable):
    method, path = webhook_endpoint.split(" ", 1)
    return processor.open(path, method=method, json=dict(datatable[1:]))


@when("the Recorder sends a webhook with no host identity", target_fixture="webhook_response")
def _(processor, webhook_endpoint):
    method, path = webhook_endpoint.split(" ", 1)
    return processor.open(path, method=method, json=WEBHOOK_WITHOUT_HOST)


@then(parsers.parse('the Processor responds with "{code:d} {reason}"'))
def _(webhook_response, code, reason):
    assert webhook_response.status_code == code
    assert webhook_response.status.split(" ", 1)[1].casefold() == reason.casefold()


@then(
    parsers.parse('a Recording is created with the state "{state}"'),
    target_fixture="created_recording",
)
def _(store, state):
    recordings = store.lists(Recording)
    assert len(recordings) == 1
    assert recordings[0].state == state
    return recordings[0]


@then("the Recording is queued for download")
def _(store, created_recording):
    jobs = store.lists(Job, recording_id=created_recording.recording_id)
    assert len(jobs) == 1
    assert (jobs[0].kind, jobs[0].state) == ("download", "queued")


@then("no audio has been downloaded yet")
def _(created_recording):
    assert created_recording.local_path is None


@then("the Recording is created without a device identity")
def _(store):
    recordings = store.lists(Recording)
    assert len(recordings) == 1
    assert recordings[0].capture_device is None
