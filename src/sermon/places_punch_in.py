from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Store


@dataclass(frozen=True)
class PlacesPunchIn:
    store: Store

    def __call__(self, segment, *, punch_in_seconds):
        return self.store.saves(replace(segment, punch_in_seconds=punch_in_seconds))
