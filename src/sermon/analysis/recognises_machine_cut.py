from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sermon.store import Artifact, Segment, Store

MACHINE = "machine"
PUBLISHED = "rendered_mp3"
REVIEWED_STATES = frozenset({"approved", "processing", "complete"})
UNADJUSTED = frozenset({"model", "refined", "model-in/refined-out"})

PUBLISHED_BEFORE_PROVENANCE_WAS_STORED = frozenset(
    {
        "2026-09-06 - Hebrews 12.18-24.mp3",
        "2026-09-13 - TEC - Giving.mp3",
        "2026-09-13 - Hebrews 12.25-29.mp3",
    }
)


@dataclass(frozen=True)
class RecognisesMachineCut:
    """Whether a published output is the system's own answer rather than a human edit."""

    store: Store
    published_before_provenance_was_stored: frozenset[str] = (
        PUBLISHED_BEFORE_PROVENANCE_WAS_STORED
    )

    def __call__(self, recording_id, edit) -> bool:
        if Path(edit).name in self.published_before_provenance_was_stored:
            return True
        return any(
            segment.boundary_source in UNADJUSTED and self.rendered(segment)
            for segment in self.store.lists(Segment, recording_id=recording_id)
            if segment.state in REVIEWED_STATES
        )

    def rendered(self, segment):
        return any(
            held.kind == PUBLISHED
            for held in self.store.lists(Artifact, segment_id=segment.segment_id)
        )
