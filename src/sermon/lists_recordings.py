from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sermon.forces_ingestion import (
    INGEST_ACTION,
    NOTHING_QUEUED,
    RUNNING,
    WAITING,
    reads_standing,
)
from sermon.glossary import ReadsGlossary
from sermon.store import Block, Job, LogEntry, Proposal, Recording, RecordingTitle, Segment, Store


def now():
    return datetime.now(UTC)

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

INGEST_STATE = "discovered"

PAGE_SIZE = 50

FAILED_STATES = frozenset({"ingest_failed", "analysis_failed", "processing_failed"})

KIND_TAGS = {
    "service": "Service",
    "class": "Class",
    "special_service": "Special",
    "meeting": "Meeting",
    "rehearsal": "Rehearsal",
    "empty": "Silence or noise",
}


STATE_WORDS = {
    "discovered": ("Waiting to download", "accent"),
    "downloading": ("Downloading", "accent"),
    "downloaded": ("Waiting to analyse", "accent"),
    "analyzing": ("Analysing", "accent"),
    "awaiting_review": ("Awaiting review", "warn"),
    "ingest_failed": ("Ingest failed", "bad"),
    "analysis_failed": ("Analysis failed", "bad"),
    "ignored": ("Ignored", "muted"),
    "discarded": ("Discarded", "muted"),
}

PUBLISHED = ("Published", "muted")
ARCHIVED = ("Archived", "muted")
NOTHING_TO_PUBLISH = ("Nothing to publish", "muted")


def says_state(state, segments):
    if state == "reviewed":
        complete = [segment for segment in segments if segment.state == "complete"]
        if not complete:
            return NOTHING_TO_PUBLISH
        return ARCHIVED if all(segment.intent == "archive" for segment in complete) else PUBLISHED
    if state == "awaiting_review" and not segments:
        return NOTHING_TO_PUBLISH
    return STATE_WORDS.get(state, (state.replace("_", " ").capitalize(), "muted"))


def week_ending(moment):
    day = moment.date()
    return day + timedelta(days=6 - day.weekday())


def tags_kind(kind, series, glossary):
    if series:
        abbreviated = glossary.abbreviates(series)
        if abbreviated != series:
            return abbreviated
    return KIND_TAGS.get(kind)


def reads_failure(store, recording_id, segment_id=None):
    entered = [
        entry.error
        for entry in store.lists(LogEntry, recording_id=recording_id)
        if entry.entered_state in FAILED_STATES
        and entry.error
        and (segment_id is None or entry.segment_id == segment_id)
    ]
    return entered[-1] if entered else None

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
    hours, rest = divmod(math.floor(float(seconds) * 100 + 0.5), 360000)
    minutes, centis = divmod(rest, 6000)
    return f"{hours}:{minutes:02d}:{centis // 100:02d}.{centis % 100:02d}"


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
class BandView:
    type: str
    left: float
    width: float
    emphasised: bool


@dataclass(frozen=True)
class ProposalView:
    classification: str
    span: str
    length: str


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
    summaries: tuple = ()
    failure: str | None = None
    title: str | None = None
    kind: str | None = None
    tag: str | None = None
    state_label: str = ""
    state_tone: str = "muted"
    day: str = ""
    week_ending: str = ""
    bands: tuple = ()
    proposals: tuple = ()


@dataclass(frozen=True)
class Week:
    ending: str
    heading: str
    rows: tuple


@dataclass(frozen=True)
class RecordingPage:
    rows: tuple
    weeks: tuple
    waiting: tuple
    page: int
    pages: int
    total: int
    awaiting: int
    previous: int | None
    next: int | None


def groups_by_week(rows):
    weeks = []
    for row in rows:
        if not weeks or weeks[-1][0] != row.week_ending:
            weeks.append((row.week_ending, []))
        weeks[-1][1].append(row)
    return tuple(
        Week(
            ending=ending,
            heading=f"Week ending {datetime.strptime(ending, '%Y-%m-%d'):%a %-d %b}",
            rows=tuple(members),
        )
        for ending, members in weeks
    )


def builds_page(rows, page):
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    current = min(max(1, page or 1), pages)
    start = (current - 1) * PAGE_SIZE
    shown = rows[start : start + PAGE_SIZE]
    return RecordingPage(
        rows=shown,
        weeks=groups_by_week(shown),
        waiting=tuple(row for row in rows if row.proposals) if current == 1 else (),
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
    glossary: object = None

    def __call__(
        self, *, include_discarded=False, filter_name=None, classification=None, q=None, page=1,
        kind=None,
    ):
        return self.paginates(
            include_discarded=include_discarded,
            filter_name=filter_name,
            classification=classification,
            q=q,
            page=page,
            kind=kind,
        ).rows

    def paginates(
        self, *, include_discarded=False, filter_name=None, classification=None, q=None, page=1,
        kind=None,
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
        glossary = self.glossary or ReadsGlossary()()
        rows = tuple(self._row(recording, queued, glossary) for recording in recordings)
        if kind:
            rows = tuple(row for row in rows if row.kind == kind)
        if classification:
            rows = tuple(
                row for row in rows if any(item[0] == classification for item in row.segments)
            )
        if filter_name == "Needs attention":
            rows = tuple(row for row in rows if row.needs_attention)
        elif filter_name == "In progress":
            rows = tuple(row for row in rows if row.state in {"analyzing", "processing"})
        elif filter_name == "Failed":
            rows = tuple(row for row in rows if row.failed)
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
                or needle in (row.title or "").lower()
                or any(needle in label.lower() for label in row.labels)
                or any(needle in summary.lower() for summary in row.summaries)
                or any(needle in item[0].lower() for item in row.segments)
            )
        return builds_page(rows, page)

    def _row(self, recording, queued=(), glossary=None):
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
        failing = [
            reads_failure(self.store, recording.recording_id, segment.segment_id)
            for segment in segments
            if segment.state == "processing_failed"
        ]
        if recording.state in FAILED_STATES:
            failing.insert(0, reads_failure(self.store, recording.recording_id))
        waiting = False
        if recording.waiting_since is not None:
            waiting = (self.clock() - recording.waiting_since).total_seconds() > 86400
        titled = self.store.loads(RecordingTitle, recording.recording_id)
        label, tone = says_state(recording.state, segments)
        bands, proposals = (
            self._offers_review(recording, segments)
            if recording.state == "awaiting_review"
            else ((), ())
        )
        return RecordingRow(
            recording_id=recording.recording_id,
            recorded_at=formats_recorded_at(recording.started_at),
            duration=formats_clock(recording.duration_seconds or 0),
            state=recording.state,
            segments=tuple(summaries),
            confidence=best,
            needs_attention=awaiting > 0 or waiting,
            failed=bool(failing),
            awaiting_disposition=awaiting,
            labels=labels,
            ingest=reads_ingest(self.store, recording, queued=queued),
            summaries=tuple(
                block.summary
                for block in self.store.lists(Block, recording_id=recording.recording_id)
                if block.summary
            ),
            failure=next((reason for reason in failing if reason), None),
            title=titled.title if titled else None,
            kind=recording.kind,
            tag=tags_kind(recording.kind, titled.series if titled else None, glossary or ReadsGlossary()()),
            state_label=label,
            state_tone=tone,
            day=recording.started_at.strftime("%a"),
            week_ending=week_ending(recording.started_at).isoformat(),
            bands=bands,
            proposals=proposals,
        )

    def _offers_review(self, recording, segments):
        proposed = [segment for segment in segments if segment.state == "proposed"]
        if not proposed:
            return (), ()
        blocks = self.store.lists(Block, recording_id=recording.recording_id)
        total = recording.duration_seconds or max((block.end_seconds for block in blocks), default=0)
        seeds = {segment.seed_block_id for segment in proposed}
        bands = tuple(
            BandView(
                type=block.type,
                left=round(100 * block.start_seconds / total, 3),
                width=round(100 * (block.end_seconds - block.start_seconds) / total, 3),
                emphasised=block.block_id in seeds,
            )
            for block in blocks
            if total
        )
        proposals = tuple(
            ProposalView(
                classification=segment.classification,
                span=f"{formats_clock(segment.punch_in_seconds)} \u2013 {formats_clock(segment.punch_out_seconds)}",
                length=formats_clock(segment.punch_out_seconds - segment.punch_in_seconds),
            )
            for segment in proposed
        )
        return bands, proposals
