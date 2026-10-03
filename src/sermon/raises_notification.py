from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.store import Block, Notification, Proposal, Recording, Segment, Store

REVIEWER = "reviewer"
SEGMENT_PROPOSED = "segment_proposed"
NOTHING_PUBLISHABLE = "nothing_publishable"
NO_TEACHING_IDENTIFIED = "no_teaching_identified"
ANALYSIS_FAILED = "analysis_failed"
RENDER_COMPLETE = "render_complete"
PROCESSING_FAILED = "processing_failed"
REVIEW_REMINDER = "review_reminder"
NOT_SUBSTANTIVE = frozenset({"music", "rehearsal", "announcements", "prayer", "communion"})
SUBSTANTIVE_SPEECH_SECONDS = 600.0
COUNTED = {2: "two", 3: "three", 4: "four", 5: "five"}
UPDATED = "Updated proposal: "


def now():
    return datetime.now(UTC)


def formats_length(seconds):
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def recorded_on(recording):
    return recording.started_at.date().isoformat()


def names_session(segment):
    return f"{segment.classification} ({formats_length(segment.punch_out_seconds - segment.punch_in_seconds)})"


def why_uncertain(proposal):
    if proposal is None:
        return None
    reasons = []
    if proposal.classification_confidence == "low":
        reasons.append("classification confidence is low")
    if proposal.boundary_confidence == "low":
        reasons.append("boundary confidence is low")
    if not reasons:
        return None
    missing = f" (missing: {', '.join(proposal.missing_evidence)})" if proposal.missing_evidence else ""
    return f"{' and '.join(reasons)}{missing}"


@dataclass(frozen=True)
class RaisesNotification:
    """Records a Notification for the reviewer, then hands a pending one to delivery."""

    store: Store
    notifies: object
    clock: object = now

    def __call__(self, kind, summary, *, recording_id=None, segment_id=None, suppressed=False):
        notification = self.store.saves(
            Notification(
                recording_id=recording_id,
                segment_id=segment_id,
                kind=kind,
                recipient=REVIEWER,
                summary=summary,
                created_at=self.clock(),
                state="suppressed" if suppressed else "pending",
            )
        )
        if not suppressed:
            self.notifies(notification)
        return self.store.loads(Notification, notification.notification_id)


@dataclass(frozen=True)
class TellsAnalysisOutcome:
    """What a finished Analysis found, raised once per Recording."""

    store: Store
    notifies: object
    clock: object = now

    def __call__(self, recording):
        raises = RaisesNotification(store=self.store, notifies=self.notifies, clock=self.clock)
        segments = sorted(
            self.store.lists(Segment, recording_id=recording.recording_id),
            key=lambda item: item.punch_in_seconds,
        )
        if segments:
            return raises(
                SEGMENT_PROPOSED,
                self._updates(recording) + self._proposes(recording, segments),
                recording_id=recording.recording_id,
                segment_id=segments[0].segment_id if len(segments) == 1 else None,
            )
        if self._speaks(recording):
            return raises(
                NO_TEACHING_IDENTIFIED,
                f"Recording of {recorded_on(recording)}: content was found but no teaching was "
                f"identified, so nothing was proposed. A Block can be retyped as teaching to produce a Segment.",
                recording_id=recording.recording_id,
            )
        return raises(
            NOTHING_PUBLISHABLE,
            f"Recording of {recorded_on(recording)}: nothing publishable was found.",
            recording_id=recording.recording_id,
            suppressed=True,
        )

    def _updates(self, recording):
        earlier = self.store.lists(Notification, recording_id=recording.recording_id, kind=SEGMENT_PROPOSED)
        return UPDATED if earlier else ""

    def _proposes(self, recording, segments):
        if len(segments) == 1:
            said = f"Recording of {recorded_on(recording)}: a {names_session(segments[0])} was proposed."
        else:
            counted = COUNTED.get(len(segments), str(len(segments)))
            named = ", ".join(names_session(item) for item in segments)
            said = f"Recording of {recorded_on(recording)}: {counted} sessions were found: {named}."
        for segment in segments:
            proposals = self.store.lists(Proposal, segment_id=segment.segment_id)
            uncertain = why_uncertain(proposals[0] if proposals else None)
            if uncertain is not None:
                said += f" The {segment.classification} needs careful review: {uncertain}."
        return said

    def _speaks(self, recording):
        spoken = sum(
            block.end_seconds - block.start_seconds
            for block in self.store.lists(Block, recording_id=recording.recording_id)
            if block.type not in NOT_SUBSTANTIVE
        )
        return spoken >= SUBSTANTIVE_SPEECH_SECONDS


@dataclass(frozen=True)
class TellsAnalysisFailed:
    store: Store
    notifies: object
    clock: object = now

    def __call__(self, recording, reason):
        return RaisesNotification(store=self.store, notifies=self.notifies, clock=self.clock)(
            ANALYSIS_FAILED,
            f"Analysis of the {recorded_on(recording)} recording failed: {reason}",
            recording_id=recording.recording_id,
        )


@dataclass(frozen=True)
class TellsProcessingOutcome:
    store: Store
    notifies: object
    clock: object = now

    def __call__(self, segment, *, filename=None, reason=None):
        recording = self.store.loads(Recording, segment.recording_id)
        raises = RaisesNotification(store=self.store, notifies=self.notifies, clock=self.clock)
        if reason is not None:
            return raises(
                PROCESSING_FAILED,
                f"Processing the {recorded_on(recording)} {segment.classification} failed: {reason}",
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
            )
        return raises(
            RENDER_COMPLETE,
            f"The MP3 of the {recorded_on(recording)} {segment.classification} is ready: {filename}",
            recording_id=segment.recording_id,
            segment_id=segment.segment_id,
        )
