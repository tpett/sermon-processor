from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.store import Artifact, Job, LogEntry, Notification, Recording, Segment, Store


def now():
    return datetime.now(UTC)


PROCESS_STEPS = ("extract", "normalize", "encode", "name", "publish")


@dataclass(frozen=True)
class RendersSegment:
    store: Store
    steps: object
    notifies: object
    clock: object = now

    def __call__(self, segment):
        correlation_id = f"render:{segment.segment_id}"
        processing = self.store.saves(replace(segment, state="processing"))
        self.store.saves(
            LogEntry(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="processing",
            )
        )
        for name in PROCESS_STEPS:
            self.steps(name)
        published_on = processing.publication_date
        if published_on is None:
            published_on = self.store.loads(Recording, processing.recording_id).started_at.date()
        if processing.label:
            filename = f"{published_on.isoformat()} - {processing.label}.mp3"
        else:
            filename = f"{published_on.isoformat()}.mp3"
        self.store.saves(
            Artifact(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="rendered_mp3",
                path=filename,
                size_bytes=1,
                checksum="stub",
            )
        )
        complete = self.store.saves(replace(processing, state="complete"))
        self.store.saves(
            LogEntry(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                entered_state="complete",
            )
        )
        notification = self.store.saves(
            Notification(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="render_complete",
                recipient="reviewer",
                summary=filename,
                created_at=self.clock(),
                state="pending",
            )
        )
        self.notifies(notification)
        return complete


@dataclass(frozen=True)
class RunsRenderJob:
    store: Store
    steps: object
    notifies: object
    clock: object = now

    def __call__(self):
        job = self.store.lists(Job, kind="render", state="queued")[0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        segment = self.store.loads(Segment, running.segment_id)
        RendersSegment(
            store=self.store,
            steps=self.steps,
            notifies=self.notifies,
            clock=self.clock,
        )(segment)
        self.store.saves(replace(running, state="succeeded"))
