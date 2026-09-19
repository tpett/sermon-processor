from __future__ import annotations

from dataclasses import dataclass

from sermon.store import Store


def does_not_send(notification):
    return None


@dataclass(frozen=True)
class SendsNotification:
    store: Store
    sends: object = does_not_send

    def __call__(self, notification):
        self.sends(notification)
        return notification
