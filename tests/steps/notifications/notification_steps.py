from datetime import UTC, datetime

from pytest_bdd import given, then, when

from sermon.sends_notification import SendsNotification
from sermon.store import Notification, Recording, Reviewer


@given("a reviewer is configured to receive notifications")
def _(store):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))


@when("something happens that a reviewer should know about")
def _(store, clock):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="segment_proposed",
            recipient="reviewer",
            summary="publishable Segments were found",
            created_at=clock() if callable(clock) else datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
            state="pending",
        )
    )


@then("a Notification is created with:")
def _(store, datatable):
    fields = {row[0] for row in datatable[1:]}
    notification = store.lists(Notification)[0]
    assert "kind" in fields
    assert notification.kind
    assert notification.recipient
    assert notification.summary
    assert notification.created_at
    assert notification.state


@then("the Notification exists whether or not any channel is configured")
def _(store):
    assert store.lists(Notification)


@when("a Notification is created")
def _(store):
    recording = store.lists(Recording) or [
        store.saves(
            Recording(
                recording_id="recording_20260823_102900",
                object_key="recordings/recording_20260823_102900.flac",
                state="awaiting_review",
                started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
                started_at_source="key",
                size_bytes=1,
            )
        )
    ]
    recording = recording[0] if isinstance(recording, list) else store.lists(Recording)[0]
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="segment_proposed",
            recipient="reviewer",
            summary="publishable Segments were found",
            created_at=datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
            state="pending",
        )
    )


@then("it is recorded and left undelivered")
def _(store):
    notification = store.lists(Notification)[0]
    sent = []
    SendsNotification(store=store, sends=sent.append)(notification)
    assert notification.state == "pending"


@then("it is visible in the interface")
def _(store):
    assert store.lists(Notification)


@then("I can see which were delivered and which were not")
def _(store):
    for notification in store.lists(Notification):
        assert notification.state in {"pending", "delivered", "failed", "suppressed"}
