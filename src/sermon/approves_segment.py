from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.analysis.adds_approval_to_corpus import AddsApprovalToCorpus
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.settles_recording import SettlesRecording
from sermon.store import Job, LogEntry, Store


class SegmentNotReady(ValueError):
    pass


class PublicationLabelRequired(ValueError):
    pass


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class ReviewSession:
    waveform_editor_opened: bool = False

    def previews_punch_in(self, segment):
        return segment

    def previews_punch_out(self, segment):
        return segment


@dataclass(frozen=True)
class ApprovesSegment:
    store: Store
    clock: object = now
    adds_to_corpus: object | None = None

    def __call__(self, segment):
        if segment.state not in {"proposed", "skipped"}:
            raise SegmentNotReady(segment.state)
        if segment.intent == "publish" and not segment.label:
            raise PublicationLabelRequired("a publication label is required")
        occurred = self.clock()
        approved = self.store.saves(
            replace(segment, state="approved", disposition_at=occurred)
        )
        self.store.saves(
            LogEntry(
                recording_id=approved.recording_id,
                segment_id=approved.segment_id,
                kind="state_change",
                occurred_at=occurred,
                correlation_id=f"approve:{approved.segment_id}",
                actor="reviewer",
                entered_state="approved",
                punch_in_seconds=approved.punch_in_seconds,
                punch_out_seconds=approved.punch_out_seconds,
            )
        )
        adds = self.adds_to_corpus or AddsApprovalToCorpus(store=self.store)
        adds(approved)
        EnqueuesJob(self.store)(
            Job(
                recording_id=approved.recording_id,
                segment_id=approved.segment_id,
                kind="render",
                state="queued",
                max_attempts=5,
                dedupe_key=f"render:{approved.segment_id}",
                queued_at=self.clock(),
            )
        )
        SettlesRecording(self.store, clock=self.clock)(approved.recording_id)
        return approved
