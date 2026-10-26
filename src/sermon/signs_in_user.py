from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Store, User


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class SignsInUser:
    store: Store
    clock: object = now

    def __call__(self, email):
        known = self.store.loads(User, email)
        if known is not None:
            return known
        return self.store.saves(User(email=email, first_seen_at=self.clock()))
