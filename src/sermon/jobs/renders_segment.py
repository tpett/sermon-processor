from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.jobs.renders_mp3 import (
    reads_source_channel,
    refuses_unsettled_stereo,
)
from sermon.records_publication_details import names_output
from sermon.recuts_segment import current_renders
from sermon.raises_notification import TellsProcessingOutcome
from sermon.store import Artifact, Job, LogEntry, Recording, Segment, Store, layout


def now():
    return datetime.now(UTC)


PROCESS_STEPS = ("extract", "normalize", "encode", "name", "publish")
DIGEST_CHUNK_BYTES = 8 * 1024 * 1024
STAGED_SUFFIX = ".rendering"


def digests(path):
    digest = hashlib.sha256()
    with path.open("rb") as held:
        while chunk := held.read(DIGEST_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class StepFailed(RuntimeError):
    def __init__(self, step, error="failed"):
        super().__init__(error)
        self.step = step
        self.error = error


@dataclass(frozen=True)
class RendersSegment:
    store: Store
    steps: object
    notifies: object
    clock: object = now
    renders: object = None

    def _fails(self, segment, reason, *, final):
        entered = "processing_failed" if final else "approved"
        self.store.saves(replace(self.store.loads(Segment, segment.segment_id), state=entered))
        self.store.saves(
            LogEntry(
                recording_id=segment.recording_id,
                segment_id=segment.segment_id,
                kind="state_change",
                occurred_at=self.clock(),
                correlation_id=f"render:{segment.segment_id}",
                entered_state=entered,
                error=reason,
            )
        )
        if final:
            TellsProcessingOutcome(store=self.store, notifies=self.notifies, clock=self.clock)(
                self.store.loads(Segment, segment.segment_id), reason=reason
            )

    def __call__(self, segment, *, final_attempt=True):
        refuses_unsettled_stereo(self.store.loads(Recording, segment.recording_id))
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
        try:
            processing, filename = self._renders(processing)
        except Exception as error:
            step = getattr(error, "step", "encode")
            self._fails(segment, f"{step}: {error}", final=final_attempt)
            raise StepFailed(step, str(error)) from error
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
        TellsProcessingOutcome(store=self.store, notifies=self.notifies, clock=self.clock)(
            complete, filename=filename
        )
        return complete

    def _renders(self, processing):
        for name in PROCESS_STEPS:
            self.steps(name)
        recording = self.store.loads(Recording, processing.recording_id)
        filename = names_output(recording, processing.label)
        warnings = list(processing.warnings)
        if recording.integrated_loudness_lufs is not None and recording.integrated_loudness_lufs <= -30:
            if "source was very quiet" not in warnings:
                warnings.append("source was very quiet")
        processing = self.store.saves(replace(processing, warnings=tuple(warnings)))
        artifact = Artifact(
            recording_id=processing.recording_id,
            segment_id=processing.segment_id,
            kind="rendered_mp3",
            path=layout.published_path(filename),
            size_bytes=1,
            checksum="stub",
        )
        destination = self.store.resolves(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = destination.with_name(f"{destination.stem}{STAGED_SUFFIX}{destination.suffix}")
        try:
            if self.renders is not None:
                rendered = self.renders(
                    self.store.resolves(recording),
                    processing.punch_in_seconds,
                    processing.punch_out_seconds,
                    staged,
                    channel=reads_source_channel(recording.mono_source),
                    **({"removed": processing.removed_spans} if processing.removed_spans else {}),
                )
                artifact = replace(
                    artifact,
                    size_bytes=staged.stat().st_size,
                    checksum=digests(staged),
                    render_settings=rendered.settings,
                    input_loudness_lufs=rendered.input_loudness_lufs,
                    output_loudness_lufs=rendered.achieved_loudness_lufs,
                    output_true_peak_dbtp=rendered.achieved_true_peak_dbtp,
                )
            else:
                staged.write_bytes(b"")
            staged.replace(destination)
        finally:
            staged.unlink(missing_ok=True)
        self._supersedes_earlier_renders(self.store.saves(artifact))
        return processing, filename

    def _supersedes_earlier_renders(self, current):
        earlier = [
            item
            for item in current_renders(self.store, current)
            if item.artifact_id != current.artifact_id
        ]
        for item in earlier:
            self.store.saves(replace(item, superseded_by=current.artifact_id))
        still_published = {
            item.path for item in self.store.lists(Artifact, kind="rendered_mp3")
            if item.superseded_by is None
        }
        for item in earlier:
            if item.path not in still_published:
                self.store.resolves(item).unlink(missing_ok=True)


@dataclass(frozen=True)
class RunsRenderJob:
    store: Store
    steps: object
    notifies: object
    clock: object = now
    renders: object = None
    job_id: int | None = None

    def __call__(self):
        job = [
            queued
            for queued in self.store.lists(Job, kind="render", state="queued")
            if self.job_id in (None, queued.job_id)
        ][0]
        running = self.store.saves(replace(job, state="running", started_at=self.clock()))
        segment = self.store.loads(Segment, running.segment_id)
        attempts = (running.attempts or 0) + 1
        final = attempts >= running.max_attempts
        try:
            RendersSegment(
                store=self.store,
                steps=self.steps,
                notifies=self.notifies,
                clock=self.clock,
                renders=self.renders,
            )(segment, final_attempt=final)
        except StepFailed as error:
            self.store.saves(
                replace(
                    running,
                    state="failed" if final else "queued",
                    last_error=f"{error.step}: {error}",
                    attempts=attempts,
                    failed_permanently=final,
                )
            )
            return
        self.store.saves(replace(running, state="succeeded"))
