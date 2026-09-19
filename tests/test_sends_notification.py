from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.sends_notification import SendsNotification
from sermon.store import Recording, opens_store
from test_store import configured_reviewer, minimal_notification, minimal_recording


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_a_reviewer_configured_to_receive_is_sent_the_notification(store):
    store.saves(configured_reviewer())
    notification = store.saves(minimal_notification(store.saves(minimal_recording())))
    sent = []
    SendsNotification(store=store, sends=sent.append)(notification)
    assert sent == [notification]


def test_no_further_notifications_are_sent_after_opting_out(store):
    reviewer = store.saves(configured_reviewer())
    recording = store.saves(minimal_recording())
    first = store.saves(minimal_notification(recording))
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
    assert pending.state == "pending"


def test_opting_out_does_not_hide_recordings_from_the_list(store):
    recording = store.saves(minimal_recording())
    store.saves(replace(store.saves(configured_reviewer()), receives_notifications=False))
    assert store.lists(Recording) == [recording]


def test_sending_with_no_channel_configured_does_not_fail(store):
    store.saves(configured_reviewer())
    notification = store.saves(minimal_notification(store.saves(minimal_recording())))
    assert SendsNotification(store=store)(notification) == notification
