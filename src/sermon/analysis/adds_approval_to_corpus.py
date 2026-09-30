from __future__ import annotations

from dataclasses import dataclass

from sermon.analysis.stages import DerivesGroundTruth
from sermon.store import Store

REVIEWER_MOVED = "human"
REVIEWED_STATES = frozenset({"approved", "processing", "complete"})


@dataclass(frozen=True)
class AddsApprovalToCorpus:
    """A boundary the reviewer moved is a labelled example; a proposal shipped whole is not."""

    store: Store
    derives: object | None = None

    def __call__(self, segment):
        if segment.state not in REVIEWED_STATES:
            return None
        if segment.boundary_source != REVIEWER_MOVED:
            return None
        derives = self.derives or DerivesGroundTruth(store=self.store)
        return derives(
            segment.recording_id,
            punch_in=segment.punch_in_seconds,
            punch_out=segment.punch_out_seconds,
            classification=segment.classification,
            punch_in_difficulty=None,
            punch_out_difficulty=None,
        )
