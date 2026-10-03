from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.config import IN_APP, SLACK
from sermon.posts_to_slack import PostsToSlack
from sermon.store import LogEntry, Notification, Reviewer, Store

DELIVERY_ATTEMPTS = 3
DELIVERY_FAILED = "notification_delivery_failed"


class UnknownChannel(ValueError):
    pass


def now():
    return datetime.now(UTC)


def does_not_send(notification):
    return None


def opens_channel(name, slack_webhook=None, links_to=None):
    """The sender a configured channel name stands for."""
    if name == IN_APP:
        return does_not_send
    if name == SLACK and slack_webhook is not None:
        return PostsToSlack(slack_webhook, links_to=links_to)
    raise UnknownChannel(
        f"no {name!r} notification channel can be opened; the channels are {IN_APP!r} "
        f"and {SLACK!r}, which needs a webhook"
    )


@dataclass(frozen=True)
class SendsNotification:
    """Delivers a pending Notification through the configured sender and records the outcome."""

    store: Store
    sends: object = does_not_send
    clock: object = now
    attempts: int = DELIVERY_ATTEMPTS

    def __call__(self, notification):
        if notification.notification_id is None:
            notification = self.store.saves(notification)
        if notification.state != "pending" or self.sends is does_not_send:
            return notification
        reviewer = self.store.loads(Reviewer, notification.recipient)
        if reviewer is None or not reviewer.receives_notifications:
            return notification
        for attempt in range(1, self.attempts + 1):
            try:
                self.sends(notification)
            except Exception as error:
                self._records_failure(notification, attempt, error)
                continue
            return self.store.saves(replace(notification, state="delivered"))
        return self.store.saves(replace(notification, state="failed"))

    def _records_failure(self, notification, attempt, error):
        if notification.recording_id is None:
            return
        self.store.saves(
            LogEntry(
                recording_id=notification.recording_id,
                segment_id=notification.segment_id,
                kind=DELIVERY_FAILED,
                occurred_at=self.clock(),
                correlation_id=f"notification:{notification.notification_id}",
                error=f"attempt {attempt}: {error}",
            )
        )


def lists_undelivered(store):
    return [item for item in store.lists(Notification) if item.state == "failed"]
