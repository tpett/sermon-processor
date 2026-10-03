from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sermon.raises_notification import REVIEW_REMINDER, SEGMENT_PROPOSED, RaisesNotification, recorded_on
from sermon.store import Notification, Recording, Segment, Store

REMINDED_AFTER = timedelta(days=3)
WAITING = "awaiting_review"


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class RemindsReviewer:
    """Reminds the reviewer once about a proposal left undispositioned for three days."""

    store: Store
    notifies: object
    clock: object = now
    after: timedelta = REMINDED_AFTER

    def __call__(self):
        return tuple(
            reminder
            for recording in self.store.lists(Recording, state=WAITING)
            if (reminder := self._reminds(recording)) is not None
        )

    def _reminds(self, recording):
        waiting = self.store.lists(Segment, recording_id=recording.recording_id, state="proposed")
        told = self.store.lists(Notification, recording_id=recording.recording_id)
        proposals = [item for item in told if item.kind == SEGMENT_PROPOSED]
        if not waiting or not proposals:
            return None
        since = proposals[-1].created_at
        if any(item.kind == REVIEW_REMINDER and item.created_at >= since for item in told):
            return None
        waited = self.clock() - since
        if waited < self.after:
            return None
        return RaisesNotification(store=self.store, notifies=self.notifies, clock=self.clock)(
            REVIEW_REMINDER,
            f"Recording of {recorded_on(recording)}: {len(waiting)} proposed Segment"
            f"{'' if len(waiting) == 1 else 's'} {'has' if len(waiting) == 1 else 'have'} waited "
            f"{waited.days} days for review.",
            recording_id=recording.recording_id,
            segment_id=waiting[0].segment_id if len(waiting) == 1 else None,
        )
