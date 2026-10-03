from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sermon.raises_notification import RaisesNotification
from sermon.reminds_reviewer import RemindsReviewer
from sermon.store import Notification, Reviewer, Segment, opens_store
from test_store import minimal_recording

PROPOSED_AT = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def proposed(store, state="proposed"):
    store.saves(Reviewer(actor="reviewer"))
    recording = store.saves(replace(minimal_recording(), state="awaiting_review"))
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            span_start_seconds=60.0,
            span_end_seconds=3000.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3000.0,
        )
    )
    RaisesNotification(store=store, notifies=lambda _n: None, clock=lambda: PROPOSED_AT)(
        "segment_proposed", "a sermon was proposed", recording_id=recording.recording_id,
        segment_id=segment.segment_id,
    )
    return segment


def reminds(store, after):
    sent = []
    RemindsReviewer(store=store, notifies=sent.append, clock=lambda: PROPOSED_AT + after)()
    return sent


def reminders(store):
    return [item for item in store.lists(Notification) if item.kind == "review_reminder"]


def test_nothing_is_raised_before_three_days(store):
    proposed(store)
    assert reminds(store, timedelta(days=2, hours=23)) == []
    assert reminders(store) == []


def test_a_segment_waiting_three_days_raises_one_reminder_linked_to_it(store):
    segment = proposed(store)
    sent = reminds(store, timedelta(days=3))
    [reminder] = reminders(store)
    assert (reminder.recording_id, reminder.segment_id) == (segment.recording_id, segment.segment_id)
    assert reminder.created_at == PROPOSED_AT + timedelta(days=3)
    assert "3 days" in reminder.summary
    assert [item.notification_id for item in sent] == [reminder.notification_id]


def test_a_reminder_is_raised_once_per_proposal(store):
    proposed(store)
    reminds(store, timedelta(days=3))
    reminds(store, timedelta(days=4))
    assert len(reminders(store)) == 1


@pytest.mark.parametrize("state", ["approved", "skipped", "complete"])
def test_a_dispositioned_segment_is_not_reminded_about(store, state):
    proposed(store, state=state)
    assert reminds(store, timedelta(days=5)) == []
    assert reminders(store) == []


def test_a_discarded_recording_is_not_reminded_about(store):
    proposed(store)
    store.saves(replace(minimal_recording(), state="discarded"))
    assert reminds(store, timedelta(days=5)) == []
