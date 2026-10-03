from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Store


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class RemindsReviewer:
    store: Store
    notifies: object
    clock: object = now

    def __call__(self):
        return ()
