import pytest
from pytest_bdd import given, then, when

from sermon.store import Job, Notification, Recording, Reviewer
from sermon.web import creates_app

from steps import _notifications
from steps._markup import reads_rows


@pytest.fixture
def delivery_channel():
    return _notifications.Channel()


@pytest.fixture
def moments():
    return _notifications.Moments()


def notifications_page(store, moments):
    return creates_app(store=store, clock=moments).test_client().get("/notifications").get_data(as_text=True)


def listed(page):
    return {int(row["id"]): row for row in reads_rows(page, "notification")}


@given("a reviewer is configured to receive notifications")
def _(store):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))


@given("no delivery channel is configured")
def _(delivery_channel):
    delivery_channel.configured = False


@when("something happens that a reviewer should know about")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.SUNDAY, delivery_channel, moments)


@when("a Notification is created")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.SUNDAY, delivery_channel, moments)


@then("a Notification is created with:")
def _(store, datatable, moments):
    fields = [row[0] for row in datatable[1:]]
    assert fields == ["subject", "kind", "recipient", "summary", "created_at", "state"]
    recording = _notifications.the_recording(store)
    notification = _notifications.the_only(store)
    assert notification.recording_id == recording.recording_id
    assert notification.kind == "segment_proposed"
    assert notification.recipient == "reviewer"
    assert "2026-08-23" in notification.summary
    assert notification.created_at == moments()
    assert notification.state == "delivered"


@then("the Notification exists whether or not any channel is configured")
def _(store, delivery_channel):
    notification = _notifications.the_only(store)
    assert notification.notification_id is not None
    assert [item.notification_id for item in delivery_channel.received] == [notification.notification_id]


@then("it is recorded and left undelivered")
def _(store, delivery_channel):
    notification = _notifications.the_only(store)
    assert notification.kind == "segment_proposed"
    assert notification.state == "pending"
    assert delivery_channel.attempts == 0


@then("it is visible in the interface")
def _(store, moments):
    notification = _notifications.the_only(store)
    shown = listed(notifications_page(store, moments))
    assert list(shown) == [notification.notification_id]
    assert notification.summary in shown[notification.notification_id]["text"]


@then("nothing fails")
def _(store):
    recording = _notifications.the_recording(store)
    assert recording.state == "awaiting_review"
    assert [job.state for job in store.lists(Job, recording_id=recording.recording_id)] == ["succeeded"]


@when("I open the interface", target_fixture="opened_interface")
def _(store, moments):
    return creates_app(store=store, clock=moments).test_client().get("/").get_data(as_text=True)


@then("I see the Notifications raised for me")
def _(store, moments, opened_interface):
    raised = [item for item in store.lists(Notification) if item.recipient == "reviewer"]
    assert raised, "no Notification has been raised for the reviewer, so there is nothing to see"
    assert 'href="/notifications" data-field="notifications-link"' in opened_interface
    assert set(listed(notifications_page(store, moments))) == {item.notification_id for item in raised}


@then("I can see which were delivered and which were not")
def _(store, moments):
    raised = store.lists(Notification)
    assert raised, "no Notification has been raised, so nothing shows whether it was delivered"
    shown = listed(notifications_page(store, moments))
    assert {key: item["state"] for key, item in shown.items()} == {
        item.notification_id: item.state for item in raised
    }
