from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.forces_ingestion import (
    INGEST_ACTION,
    NOTHING_QUEUED,
    RUNNING,
    WAITING,
    reads_standing,
)
from sermon.store import Job, Proposal, Recording, Segment, Store


def now():
    return datetime.now(UTC)

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

INGEST_STATE = "discovered"

PAGE_SIZE = 50

INGEST_STANDINGS = {
    NOTHING_QUEUED: "Nothing is queued for this Recording yet",
    WAITING: "Queued for download, waiting for the worker",
    RUNNING: "The download is running now",
}


def formats_clock(seconds):
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def formats_precise(seconds):
    hours, rest = divmod(float(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def formats_recorded_at(moment):
    return moment.strftime("%Y-%m-%d %I:%M %p")


@dataclass(frozen=True)
class IngestView:
    outcome: str
    position: int | None
    queued_count: int
    since: str | None
    standing: str
    url: str


def reads_ingest(store, recording, queued=None):
    if recording.state != INGEST_STATE:
        return None
    standing = reads_standing(store, recording, queued=queued)
    described = INGEST_STANDINGS[standing.outcome]
    if standing.outcome == WAITING and standing.position is not None:
        described = (
            f"{described} — {standing.position} of {standing.queued_count} queued jobs"
        )
    if standing.since is not None:
        described = f"{described}, since {formats_recorded_at(standing.since)}"
    return IngestView(
        outcome=standing.outcome,
        position=standing.position,
        queued_count=standing.queued_count,
        since=None if standing.since is None else formats_recorded_at(standing.since),
        standing=described,
        url=f"/recordings/{recording.recording_id}/actions/{INGEST_ACTION}",
    )


@dataclass(frozen=True)
class RecordingRow:
    recording_id: str
    recorded_at: str
    duration: str
    state: str
    segments: tuple
    confidence: str | None
    needs_attention: bool
    failed: bool
    awaiting_disposition: int
    labels: tuple
    ingest: IngestView | None = None


@dataclass(frozen=True)
class RecordingPage:
    rows: tuple
    page: int
    pages: int
    total: int
    awaiting: int
    previous: int | None
    next: int | None


def builds_page(rows, page):
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    current = min(max(1, page or 1), pages)
    start = (current - 1) * PAGE_SIZE
    return RecordingPage(
        rows=rows[start : start + PAGE_SIZE],
        page=current,
        pages=pages,
        total=len(rows),
        awaiting=sum(row.awaiting_disposition for row in rows),
        previous=current - 1 if current > 1 else None,
        next=current + 1 if current < pages else None,
    )


@dataclass(frozen=True)
class ListsRecordings:
    store: Store
    clock: object = now

    def __call__(
        self, *, include_discarded=False, filter_name=None, classification=None, q=None, page=1
    ):
        return self.paginates(
            include_discarded=include_discarded,
            filter_name=filter_name,
            classification=classification,
            q=q,
            page=page,
        ).rows

    def paginates(
        self, *, include_discarded=False, filter_name=None, classification=None, q=None, page=1
    ):
        recordings = [
            recording
            for recording in self.store.lists(Recording)
            if include_discarded or recording.state != "discarded"
        ]
        recordings.sort(key=lambda recording: recording.started_at, reverse=True)
        queued = (
            self.store.lists(Job, state="queued")
            if any(recording.state == INGEST_STATE for recording in recordings)
            else ()
        )
        rows = tuple(self._row(recording, queued) for recording in recordings)
        if classification:
            rows = tuple(
                row for row in rows if any(item[0] == classification for item in row.segments)
            )
        if filter_name == "Needs attention":
            rows = tuple(row for row in rows if row.needs_attention)
        elif filter_name == "In progress":
            rows = tuple(row for row in rows if row.state in {"analyzing", "processing"})
        elif filter_name == "Failed":
            rows = tuple(row for row in rows if row.state in {"analysis_failed", "processing_failed"})
        elif filter_name == "Published":
            rows = tuple(
                row for row in rows if any(item[2] == "complete" for item in row.segments)
            )
        elif filter_name == "Nothing to publish":
            rows = tuple(row for row in rows if not row.segments)
        elif filter_name == "Skipped segments":
            rows = tuple(
                row for row in rows if any(item[2] == "skipped" for item in row.segments)
            )
        elif filter_name == "Ignored":
            rows = tuple(row for row in rows if row.state == "ignored")
        if filter_name is None:
            rows = tuple(row for row in rows if row.state != "ignored")
        if q:
            needle = q.lower()
            rows = tuple(
                row
                for row in rows
                if needle in row.recorded_at.lower()
                or any(needle in label.lower() for label in row.labels)
                or any(needle in item[0].lower() for item in row.segments)
            )
        return builds_page(rows, page)

    def _row(self, recording, queued=()):
        segments = self.store.lists(Segment, recording_id=recording.recording_id)
        summaries = []
        awaiting = 0
        best = None
        for segment in segments:
            proposals = self.store.lists(Proposal, segment_id=segment.segment_id)
            confidence = proposals[0].classification_confidence if proposals else None
            summaries.append((segment.classification, confidence, segment.state))
            if segment.state == "proposed":
                awaiting += 1
            if confidence is not None and (
                best is None or CONFIDENCE_RANK[confidence] < CONFIDENCE_RANK[best]
            ):
                best = confidence
        labels = tuple(segment.label for segment in segments if segment.label)
        waiting = False
        if recording.waiting_since is not None:
            waiting = (self.clock() - recording.waiting_since).total_seconds() > 86400
        return RecordingRow(
            recording_id=recording.recording_id,
            recorded_at=formats_recorded_at(recording.started_at),
            duration=formats_clock(recording.duration_seconds or 0),
            state=recording.state,
            segments=tuple(summaries),
            confidence=best,
            needs_attention=awaiting > 0 or waiting,
            failed=recording.state == "analysis_failed",
            awaiting_disposition=awaiting,
            labels=labels,
            ingest=reads_ingest(self.store, recording, queued=queued),
        )
