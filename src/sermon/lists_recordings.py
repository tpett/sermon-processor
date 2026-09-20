from __future__ import annotations

from dataclasses import dataclass

from sermon.store import Proposal, Recording, Segment, Store

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def formats_clock(seconds):
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def formats_recorded_at(moment):
    return moment.strftime("%Y-%m-%d %I:%M %p")


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


@dataclass(frozen=True)
class ListsRecordings:
    store: Store

    def __call__(self, *, include_discarded=False, filter_name=None, classification=None, q=None):
        recordings = [
            recording
            for recording in self.store.lists(Recording)
            if include_discarded or recording.state != "discarded"
        ]
        recordings.sort(key=lambda recording: recording.started_at, reverse=True)
        rows = tuple(self._row(recording) for recording in recordings)
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
        if q:
            needle = q.lower()
            rows = tuple(
                row
                for row in rows
                if needle in row.recorded_at.lower()
                or any(needle in label.lower() for label in row.labels)
                or any(needle in item[0].lower() for item in row.segments)
            )
        return rows[:50]

    def _row(self, recording):
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
        return RecordingRow(
            recording_id=recording.recording_id,
            recorded_at=formats_recorded_at(recording.started_at),
            duration=formats_clock(recording.duration_seconds or 0),
            state=recording.state,
            segments=tuple(summaries),
            confidence=best,
            needs_attention=awaiting > 0,
            failed=recording.state == "analysis_failed",
            awaiting_disposition=awaiting,
            labels=labels,
        )
