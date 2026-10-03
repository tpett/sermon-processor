from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.sends_notification import IN_APP, SendsNotification, UnknownChannel, does_not_send, opens_channel
from sermon.store import LogEntry, Notification, Recording, opens_store
from test_store import configured_reviewer, minimal_notification, minimal_recording


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_a_reviewer_configured_to_receive_is_sent_the_notification(store):
    store.saves(configured_reviewer())
    notification = store.saves(
        replace(minimal_notification(store.saves(minimal_recording())), state="pending")
    )
    sent = []
    SendsNotification(store=store, sends=sent.append)(notification)
    assert sent == [notification]


def test_no_further_notifications_are_sent_after_opting_out(store):
    reviewer = store.saves(configured_reviewer())
    recording = store.saves(minimal_recording())
    first = store.saves(replace(minimal_notification(recording), state="pending"))
    sent = []
    SendsNotification(store=store, sends=sent.append)(first)
    store.saves(replace(reviewer, receives_notifications=False))
    further = store.saves(
        replace(
            minimal_notification(recording),
            kind="analysis_failed",
            created_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            state="pending",
        )
    )
    SendsNotification(store=store, sends=sent.append)(further)
    assert sent == [first]


def test_a_notification_already_pending_is_not_sent_after_opt_out(store):
    store.saves(configured_reviewer())
    pending = store.saves(
        replace(minimal_notification(store.saves(minimal_recording())), state="pending")
    )
    store.saves(replace(configured_reviewer(), receives_notifications=False))
    sent = []
    SendsNotification(store=store, sends=sent.append)(pending)
    assert sent == []
    assert store.loads(Notification, pending.notification_id).state == "pending"


def test_opting_out_does_not_hide_recordings_from_the_list(store):
    recording = store.saves(minimal_recording())
    store.saves(replace(store.saves(configured_reviewer()), receives_notifications=False))
    assert store.lists(Recording) == [recording]


def test_sending_with_no_channel_configured_does_not_fail(store):
    store.saves(configured_reviewer())
    notification = store.saves(minimal_notification(store.saves(minimal_recording())))
    assert SendsNotification(store=store)(notification) == notification
    assert store.loads(Notification, notification.notification_id) == notification


def pending_notification(store):
    store.saves(configured_reviewer())
    return store.saves(
        replace(minimal_notification(store.saves(minimal_recording())), kind="segment_proposed", state="pending")
    )


class Refuses:
    def __init__(self, times):
        self.times = times
        self.calls = 0

    def __call__(self, notification):
        self.calls += 1
        if self.calls <= self.times:
            raise ConnectionError("the channel refused the connection")


def test_a_delivered_notification_is_recorded_as_delivered(store):
    pending = pending_notification(store)
    sent = []
    SendsNotification(store=store, sends=sent.append)(pending)
    assert [item.notification_id for item in sent] == [pending.notification_id]
    assert store.loads(Notification, pending.notification_id).state == "delivered"


def test_a_refused_delivery_is_retried_until_it_succeeds(store):
    pending = pending_notification(store)
    refuses = Refuses(times=2)
    SendsNotification(store=store, sends=refuses, attempts=3)(pending)
    assert refuses.calls == 3
    assert store.loads(Notification, pending.notification_id).state == "delivered"


def test_a_delivery_refused_on_every_attempt_is_recorded_as_failed_with_each_error(store):
    pending = pending_notification(store)
    refuses = Refuses(times=99)
    returned = SendsNotification(store=store, sends=refuses, attempts=3)(pending)
    assert refuses.calls == 3
    assert returned.state == "failed"
    assert store.loads(Notification, pending.notification_id).state == "failed"
    logged = [item for item in store.lists(LogEntry) if item.kind == "notification_delivery_failed"]
    assert [(item.correlation_id, item.error) for item in logged] == [
        (f"notification:{pending.notification_id}", "attempt 1: the channel refused the connection"),
        (f"notification:{pending.notification_id}", "attempt 2: the channel refused the connection"),
        (f"notification:{pending.notification_id}", "attempt 3: the channel refused the connection"),
    ]


def test_with_no_channel_a_notification_stays_pending(store):
    pending = pending_notification(store)
    SendsNotification(store=store)(pending)
    assert store.loads(Notification, pending.notification_id).state == "pending"


def test_a_suppressed_notification_is_never_sent(store):
    store.saves(configured_reviewer())
    suppressed = store.saves(minimal_notification(store.saves(minimal_recording())))
    sent = []
    SendsNotification(store=store, sends=sent.append)(suppressed)
    assert sent == []
    assert store.loads(Notification, suppressed.notification_id).state == "suppressed"


def test_an_unsaved_notification_is_recorded_before_it_is_sent(store):
    store.saves(configured_reviewer())
    recording = store.saves(minimal_recording())
    sent = []
    SendsNotification(store=store, sends=sent.append)(
        replace(minimal_notification(recording), kind="analysis_failed", state="pending")
    )
    stored = store.lists(Notification)
    assert [item.notification_id for item in sent] == [stored[0].notification_id]
    assert stored[0].state == "delivered"


def test_the_in_app_channel_sends_nothing_anywhere():
    assert opens_channel(IN_APP) is does_not_send


def test_a_channel_nothing_implements_is_refused():
    with pytest.raises(UnknownChannel, match="in-app"):
        opens_channel("email")
