from __future__ import annotations

from dataclasses import dataclass

from sermon.store import Reviewer, Store


def does_not_send(notification):
    return None


@dataclass(frozen=True)
class SendsNotification:
    store: Store
    sends: object = does_not_send

    def __call__(self, notification):
        reviewer = self.store.loads(Reviewer, notification.recipient)
        if reviewer is not None and reviewer.receives_notifications:
            self.sends(notification)
        return notification
