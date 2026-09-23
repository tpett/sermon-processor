from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.approves_segment import ApprovesSegment
from sermon.store import Segment, Store

WHOLE_RECORDING_CLASSIFICATION = "meeting"


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class ArchivesWholeRecording:
    store: Store
    clock: object = now

    def __call__(self, recording):
        whole = float(recording.duration_seconds or 0.0)
        segment = self.store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=WHOLE_RECORDING_CLASSIFICATION,
                state="proposed",
                span_start_seconds=0.0,
                span_end_seconds=whole,
                punch_in_seconds=0.0,
                punch_out_seconds=whole,
                intent="archive",
                boundary_source="human",
            )
        )
        return ApprovesSegment(store=self.store, clock=self.clock)(segment)
