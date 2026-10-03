from datetime import UTC, datetime, timedelta
from pathlib import Path

from pytest_bdd import given, parsers, then, when

from sermon.config import Credential
from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.runs_queued_jobs import ATTEMPT, RunsQueuedJobs
from sermon.store import Discovery, Job, LogEntry, Recording
from sermon.web import creates_app
from steps._worker import refuses_other_work

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


FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
FLAC_BYTES = b"fLaC" + bytes(64)
PROBED = ProbesAudio(duration_seconds=99.5, sample_rate=48000, channels=1)
READABLE_ON_ATTEMPT = 3
WORKER_POLL_GAP = timedelta(seconds=30)
MOST_WORKER_PASSES = 500
SPEC_TOKEN = "the-token-only-the-spec-suite-issues"
UNISSUED_TOKEN = "a-token-the-processor-was-never-given"
WEBHOOK_TOKEN_VARIABLE = "SERMON_WEBHOOK_TOKEN"
PRESENTED = {
    "a token the Processor was not given": {"Authorization": f"Bearer {UNISSUED_TOKEN}"},
    "a header that is not a bearer token": {"Authorization": SPEC_TOKEN},
    "no authorization at all": {},
}


def posts_webhook(processor_client, webhook_endpoint, payload, credentials):
    method, path = webhook_endpoint.split(" ", 1)
    return processor_client.open(path, method=method, json=payload, headers=credentials)


@given("the Sermon Processor is running", target_fixture="processor_client")
def _(store):
    return creates_app(store=store, webhook_token=Credential(SPEC_TOKEN)).test_client()


@given(
    "the Recorder holds the bearer token the Processor was configured with",
    target_fixture="webhook_credentials",
)
def _():
    return {"Authorization": f"Bearer {SPEC_TOKEN}"}


@given(parsers.parse('the webhook endpoint is "{webhook_endpoint}"'), target_fixture="webhook_endpoint")
def _(webhook_endpoint):
    return webhook_endpoint


@given("the Recorder reaches it over the tailnet")
def _():
    return None


@when("the Recorder sends a webhook with the payload:", target_fixture="processor_response")
def _(processor_client, webhook_endpoint, webhook_credentials, datatable):
    return posts_webhook(
        processor_client, webhook_endpoint, dict(datatable[1:]), webhook_credentials
    )


@when("the Recorder sends a webhook with no host identity", target_fixture="processor_response")
def _(processor_client, webhook_endpoint, webhook_credentials):
    return posts_webhook(
        processor_client, webhook_endpoint, WEBHOOK_WITHOUT_HOST_IDENTITY, webhook_credentials
    )


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
def _(processor_client, webhook_endpoint, webhook_credentials):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)


@then("no duplicate Recording is created")
def _(store):
    held = [(item.recording_id, item.object_key) for item in store.lists(Recording)]
    assert held == [(Path(IDENTICAL["object_key"]).stem, IDENTICAL["object_key"])], held


@then("no additional download is queued")
def _(store):
    assert len(store.lists(Job, kind="download")) == 1


@given("the reconciliation scan has just created a Recording for an object key", target_fixture="recording")
def _(store):
    object_key = IDENTICAL["object_key"]
    recording_id = Path(object_key).stem
    return store.saves(
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
def _(processor_client, webhook_endpoint, webhook_credentials):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)


@then("whichever arrived first owns the Recording")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id) == recording, "the later webhook rewrote the Recording"


@when("two identical webhooks are handled concurrently", target_fixture="processor_response")
def _(processor_client, webhook_endpoint, webhook_credentials):
    first = posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)
    posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)
    return first


@then("exactly one Recording exists afterwards")
def _(store):
    assert len(store.lists(Recording)) == 1


@then("exactly one download is queued")
def _(store):
    assert len(store.lists(Job, kind="download")) == 1


@when(parsers.parse('the Recorder sends a webhook with "{field}" omitted'), target_fixture="processor_response")
def _(processor_client, webhook_endpoint, webhook_credentials, field):
    payload = dict(IDENTICAL)
    payload.pop(field, None)
    return posts_webhook(processor_client, webhook_endpoint, payload, webhook_credentials)


@then(parsers.parse('the response body names the missing field "{field}"'))
def _(processor_response, field):
    assert processor_response.get_json()["missing"] == field


@then("no Recording is created")
def _(store):
    assert store.lists(Recording) == []


@when(parsers.parse('the Recorder sends a webhook with event "{event}"'), target_fixture="processor_response")
def _(processor_client, webhook_endpoint, webhook_credentials, event):
    payload = dict(IDENTICAL)
    payload["event"] = event
    return posts_webhook(processor_client, webhook_endpoint, payload, webhook_credentials)


@then("the ignored event type is logged")
def _(store):
    discoveries = store.lists(Discovery, kind="webhook")
    assert discoveries
    assert discoveries[-1].event == "recording.started"


class AppearsOnAttempt(FetchesObject):
    """An object the bucket lists but cannot serve until the given fetch."""

    def __init__(self, key, attempt):
        super().__init__()
        self.key, self.attempt, self.asked = key, attempt, 0

    def __call__(self, key, destination):
        if key == self.key:
            self.asked += 1
            if self.asked == self.attempt:
                self.stores(key, FLAC_BYTES)
        return super().__call__(key, destination)


class MovesOn:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


@given("the object store has not yet made the object available", target_fixture="object_store")
def _():
    return AppearsOnAttempt(IDENTICAL["object_key"], READABLE_ON_ATTEMPT)


@given("the object store is a Garage S3 instance reachable over the tailnet")
def _():
    return None


@when("the Recorder sends a webhook for that object key", target_fixture="processor_response")
def _(store, processor_client, webhook_endpoint, webhook_credentials, object_store):
    response = posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)
    clock = MovesOn(FROZEN)
    runs = RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(store=store, fetches=object_store, probes=PROBED, clock=clock),
        analyzes=refuses_other_work,
        renders=refuses_other_work,
        clock=clock,
    )
    for _ in range(MOST_WORKER_PASSES):
        if not store.lists(Job, kind="download", state="queued"):
            break
        if runs() is None:
            clock.at += WORKER_POLL_GAP
    return response


@then("the download is retried until the object becomes readable")
def _(store):
    (job,) = store.lists(Job, kind="download")
    errors = [entry.error for entry in store.lists(LogEntry, job_id=job.job_id) if entry.kind == ATTEMPT]
    assert len(errors) >= 2 and errors[-1] is None, f"attempt errors {errors}"
    assert all(errors[:-1]), f"attempt errors {errors}"
    assert store.loads(Recording, job.recording_id).state == "downloaded"


@then(parsers.parse('the Recording does not enter "{state}" before {attempts:d} attempts'))
def _(store, state, attempts):
    (job,) = store.lists(Job, kind="download")
    entered = [entry.entered_state for entry in store.lists(LogEntry, recording_id=job.recording_id)]
    assert state not in entered, entered
    tried = [entry for entry in store.lists(LogEntry, job_id=job.job_id) if entry.kind == ATTEMPT]
    assert len(tried) == attempts, f"{len(tried)} attempts were made"


@then("it is queued for download")
def _(store, ingest_response):
    forced = ingest_response.get_json()["recording_id"]
    downloads = [(job.state, job.dedupe_key) for job in store.lists(Job, recording_id=forced, kind="download")]
    assert downloads == [("queued", f"download:{forced}")], downloads


@when(
    parsers.parse("the Recorder presents {credential} with an otherwise valid webhook"),
    target_fixture="processor_response",
)
def _(processor_client, webhook_endpoint, credential):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL, PRESENTED[credential])


@then("the refusal does not repeat what was presented")
def _(processor_response):
    body = processor_response.get_data(as_text=True)
    assert SPEC_TOKEN not in body
    assert UNISSUED_TOKEN not in body


@then("no Discovery is recorded")
def _(store):
    assert store.lists(Discovery) == []


@then("no download is queued")
def _(store):
    assert store.lists(Job, kind="download") == []


@given("the Processor has no bearer token configured", target_fixture="processor_client")
def _(store):
    return creates_app(store=store, webhook_token=None).test_client()


@when(
    "the Recorder sends a webhook presenting the token it holds",
    target_fixture="processor_response",
)
def _(processor_client, webhook_endpoint, webhook_credentials):
    return posts_webhook(processor_client, webhook_endpoint, IDENTICAL, webhook_credentials)


@then("the response body names the configuration that is missing")
def _(processor_response):
    assert WEBHOOK_TOKEN_VARIABLE in processor_response.get_data(as_text=True)
