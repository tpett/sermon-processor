from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.adjusts_punch_point import EDITABLE_STATES
from sermon.store import LogEntry, Segment, Store
from sermon.store.vocabularies import SEGMENT_CLASSIFICATIONS


def now():
    return datetime.now(UTC)


class ClassificationRejected(ValueError):
    pass


@dataclass(frozen=True)
class ClassifiesSegment:
    """Correct what the machine decided a Segment is.

    The classification is not only a label: it picks the intent a Segment is
    approved with, so a Segment called something other than a sermon defaults to
    archive rather than publish. Getting it wrong therefore costs more than a
    word, and the reviewer has no other way to put it right.
    """

    store: Store
    clock: object = now

    def __call__(self, segment, classification, *, actor="reviewer"):
        if classification not in SEGMENT_CLASSIFICATIONS:
            raise ClassificationRejected(
                "that is not a classification a Segment can have"
            )
        if segment.state not in EDITABLE_STATES:
            raise ClassificationRejected(
                "a Segment that has been approved cannot be reclassified"
            )
        if classification == segment.classification:
            return segment
        classified = self.store.saves(replace(segment, classification=classification))
        self.store.saves(
            LogEntry(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="classification_change",
                occurred_at=self.clock(),
                correlation_id=f"classify:{segment.segment_id}",
                actor=actor,
            )
        )
        return classified
