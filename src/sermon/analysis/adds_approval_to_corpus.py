from __future__ import annotations

from dataclasses import dataclass

from sermon.store import Store

REVIEWER_MOVED = "human"
REVIEWED_STATES = frozenset({"approved", "processing", "complete"})


@dataclass(frozen=True)
class AddsApprovalToCorpus:
    store: Store
    derives: object | None = None

    def __call__(self, segment):
        return None
