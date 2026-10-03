import json
import urllib.error
from datetime import UTC, datetime

import pytest

from sermon.config import (
    Credential,
    ReadsConfiguration,
    UnusableConfiguration,
)
from sermon.posts_to_slack import PostsToSlack, SlackRefused
from sermon.sends_notification import SendsNotification, UnknownChannel, opens_channel
from sermon.store import LogEntry, Notification, Recording, Reviewer, opens_store

HOOK = "https://hooks.slack.com/services/TFAKE000/BFAKE000/notarealsecretatall"
SECRET = "notarealsecretatall"
FROZEN = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
RECORDING = "recording_20261004_100000"

BASE = {
    "SERMON_DATA_ROOT": "/data",
    "SERMON_OBJECT_STORE_ENDPOINT": "https://s3.example.invalid",
    "SERMON_OBJECT_STORE_BUCKET": "bucket",
    "SERMON_OBJECT_STORE_ACCESS_KEY_ID": "id",
    "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": "secret",
    "SERMON_MODEL_ENDPOINT": "http://model.invalid:11434",
}


class Answers:
    def __init__(self, status=200, body=b"ok", raises=None):
        self.status, self.body, self.raises = status, body, raises
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.raises is not None:
            raise self.raises
        answer = self

        class Response:
            status = answer.status

            def read(self):
                return answer.body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


def told(summary="Recording of 2026-10-04: a sermon (0:40:00) was proposed.", **fields):
    return Notification(
        recording_id=RECORDING,
        kind="segment_proposed",
        recipient="reviewer",
        summary=summary,
        created_at=FROZEN,
        state="pending",
        **fields,
    )


def test_a_notification_is_posted_to_the_webhook_as_its_summary():
    opener = Answers()
    PostsToSlack(Credential(HOOK), opens=opener)(told())
    request, timeout = opener.requests[0]
    assert request.full_url == HOOK
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data)["text"] == (
        "Recording of 2026-10-04: a sermon (0:40:00) was proposed."
    )
    assert timeout <= 15


def test_the_message_links_to_the_recording_when_the_app_address_is_known():
    opener = Answers()
    PostsToSlack(Credential(HOOK), opens=opener, links_to="https://app.example.invalid/")(told())
    text = json.loads(opener.requests[0][0].data)["text"]
    assert f"<https://app.example.invalid/recordings/{RECORDING}|Open the recording>" in text


def test_a_refusal_from_slack_raises_without_naming_the_webhook():
    with pytest.raises(SlackRefused) as refused:
        PostsToSlack(Credential(HOOK), opens=Answers(status=403, body=b"invalid_token"))(told())
    assert SECRET not in str(refused.value)
    assert "403" in str(refused.value)


def test_an_unreachable_slack_raises_without_naming_the_webhook():
    failure = urllib.error.URLError(f"cannot reach {HOOK}")
    with pytest.raises(SlackRefused) as refused:
        PostsToSlack(Credential(HOOK), opens=Answers(raises=failure))(told())
    assert SECRET not in str(refused.value)


def test_the_sender_never_shows_the_webhook_in_its_repr():
    assert SECRET not in repr(PostsToSlack(Credential(HOOK)))


def test_the_slack_channel_needs_its_webhook():
    with pytest.raises(UnknownChannel):
        opens_channel("slack", None)
    assert isinstance(opens_channel("slack", Credential(HOOK)), PostsToSlack)


def test_configuration_reads_the_slack_channel_and_keeps_its_webhook_secret():
    configuration = ReadsConfiguration(
        {**BASE, "SERMON_NOTIFICATION_CHANNEL": "slack", "SERMON_SLACK_WEBHOOK_URL": HOOK}
    )()
    assert configuration.notification_channel == "slack"
    assert configuration.slack_webhook.reveals() == HOOK
    assert SECRET not in repr(configuration)


@pytest.mark.parametrize(
    "webhook",
    [
        None,
        "http://hooks.slack.com/services/TFAKE000/BFAKE000/notarealsecretatall",
        "https://example.invalid/services/TFAKE000/BFAKE000/notarealsecretatall",
    ],
)
def test_the_slack_channel_refuses_a_missing_or_foreign_webhook(webhook):
    environment = {**BASE, "SERMON_NOTIFICATION_CHANNEL": "slack"}
    if webhook is not None:
        environment["SERMON_SLACK_WEBHOOK_URL"] = webhook
    with pytest.raises(UnusableConfiguration) as refused:
        ReadsConfiguration(environment)()
    assert SECRET not in str(refused.value)


def test_a_failed_post_is_recorded_without_the_webhook(tmp_path):
    store = opens_store(tmp_path)
    try:
        store.saves(
            Recording(
                recording_id=RECORDING,
                object_key=f"{RECORDING}.flac",
                state="awaiting_review",
                started_at=FROZEN,
                started_at_source="key",
                size_bytes=1,
            )
        )
        store.saves(Reviewer(actor="reviewer", receives_notifications=True))
        sends = PostsToSlack(Credential(HOOK), opens=Answers(status=500, body=b"error"))
        outcome = SendsNotification(store=store, sends=sends, clock=lambda: FROZEN)(told())
        assert outcome.state == "failed"
        errors = [entry.error for entry in store.lists(LogEntry)]
        assert len(errors) == 3
        assert all(SECRET not in error for error in errors)
    finally:
        store.close()


def test_an_http_error_from_slack_raises_without_naming_the_webhook():
    failure = urllib.error.HTTPError(HOOK, 404, "no_service", {}, None)
    with pytest.raises(SlackRefused) as refused:
        PostsToSlack(Credential(HOOK), opens=Answers(raises=failure))(told())
    assert SECRET not in str(refused.value)
    assert "404" in str(refused.value)


MALFORMED_SECRET = "notareal secret\nat all"
MALFORMED_HOOKS = (
    f"https://hooks.slack.com/services/TFAKE000/BFAKE000/{MALFORMED_SECRET}",
    f" https://hooks.slack.com/services/TFAKE000/BFAKE000/{MALFORMED_SECRET}",
)


def names_the_secret(text):
    return any(part in text for part in ("notareal", "at all", MALFORMED_SECRET))


def every_message_in(error):
    seen = []
    while error is not None:
        seen += [str(error), repr(error)]
        error = error.__cause__ or error.__context__
    return seen


class RefusesTheUrl:
    """What urlopen does with a URL holding whitespace: it raises naming the URL."""

    def __call__(self, request, timeout):
        import http.client

        raise http.client.InvalidURL(f"URL can't contain control characters. {request.full_url!r}")


@pytest.mark.parametrize("hook", MALFORMED_HOOKS)
def test_a_malformed_webhook_raises_slack_refused_without_naming_it(hook):
    with pytest.raises(SlackRefused) as refused:
        PostsToSlack(Credential(hook), opens=RefusesTheUrl())(told())
    assert not any(names_the_secret(message) for message in every_message_in(refused.value))


@pytest.mark.parametrize("hook", MALFORMED_HOOKS)
def test_a_malformed_webhook_is_logged_without_naming_it(tmp_path, hook):
    store = opens_store(tmp_path)
    try:
        store.saves(
            Recording(
                recording_id=RECORDING,
                object_key=f"{RECORDING}.flac",
                state="awaiting_review",
                started_at=FROZEN,
                started_at_source="key",
                size_bytes=1,
            )
        )
        store.saves(Reviewer(actor="reviewer", receives_notifications=True))
        sends = PostsToSlack(Credential(hook), opens=RefusesTheUrl())
        outcome = SendsNotification(store=store, sends=sends, clock=lambda: FROZEN)(told())
        assert outcome.state == "failed"
        recorded = [entry.error or "" for entry in store.lists(LogEntry)] + [repr(entry) for entry in store.lists(LogEntry)]
        assert recorded and not any(names_the_secret(text) for text in recorded)
        assert not names_the_secret(repr(sends))
    finally:
        store.close()


@pytest.mark.parametrize("hook", MALFORMED_HOOKS + (
    "https://hooks.slack.com/services/TFAKE000/BFAKE000/notarealsecret\tatall",
    "https://hooks.slack.com/services/TFAKE000/BFAKE000/notarealsecret\x7fatall",
))
def test_configuration_refuses_a_webhook_holding_whitespace_or_control_characters(hook):
    environment = {**BASE, "SERMON_NOTIFICATION_CHANNEL": "slack", "SERMON_SLACK_WEBHOOK_URL": hook}
    with pytest.raises(UnusableConfiguration) as refused:
        ReadsConfiguration(environment)()
    assert not any(names_the_secret(message) or "atall" in message for message in every_message_in(refused.value))
