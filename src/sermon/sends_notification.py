from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Reviewer, Store


def now():
    return datetime.now(UTC)


def does_not_send(notification):
    return None


@dataclass(frozen=True)
class SendsNotification:
    store: Store
    sends: object = does_not_send
    clock: object = now

    def __call__(self, notification):
        reviewer = self.store.loads(Reviewer, notification.recipient)
        if reviewer is not None and reviewer.receives_notifications:
            self.sends(notification)
        return notification
