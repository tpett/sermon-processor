"""Notifications raised by the shipped analyze and render jobs, delivered through a channel double.

Nothing here writes a Notification. A scenario lays out what a Recording holds, the
job runs, and whatever the product raised is what the Thens read back.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from sermon.jobs.renders_segment import RendersSegment, StepFailed
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.reminds_reviewer import RemindsReviewer
from sermon.sends_notification import SendsNotification, does_not_send
from sermon.store import Job, LogEntry, Notification, Recording, Segment

from steps import _analysis
from steps._worker import refuses_other_work

STARTED = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
ANALYZE_ATTEMPTS = 5
WORKER_POLL_GAP = timedelta(hours=1)
SUNDAY = _analysis.SUNDAY
LESSON_AND_SERMON = (
    ("0:00:00", "0:05:00", "music"),
    ("0:05:00", "0:45:00", "lesson"),
    ("0:45:00", "0:47:00", "prayer"),
    ("0:47:00", "1:30:12", "sermon"),
)
UNCUED_SERMON = (
    ("0:00:00", "0:25:00", "music"),
    ("0:25:00", "1:10:00", "sermon", "and so we come to the point where the argument turns on what was said before"),
    ("1:10:00", "1:30:12", "music"),
)
ONLY_MUSIC = (("0:00:00", "1:30:12", "music"),)
NO_TEACHING = (
    ("0:00:00", "0:10:00", "music"),
    ("0:10:00", "1:20:00", "other", "the members will now consider the budget for next year and the elders report"),
    ("1:20:00", "1:30:12", "music"),
)


class ChannelUnavailable(ConnectionError):
    pass


@dataclass
class Channel:
    """The delivery channel as a test sees it: what reached it, and whether it answers."""

    received: list = field(default_factory=list)
    configured: bool = True
    available: bool = True
    attempts: int = 0

    def sends(self, notification):
        self.attempts += 1
        if not self.available:
            raise ChannelUnavailable("the channel refused the connection")
        self.received.append(notification)

    def as_configured(self):
        return self.sends if self.configured else does_not_send


@dataclass
class Moments:
    now: datetime = STARTED

    def __call__(self):
        return self.now

    def passes(self, elapsed):
        self.now = self.now + elapsed


def delivers(store, channel, moments):
    return SendsNotification(store=store, sends=channel.as_configured(), clock=moments)


def registered(store, recording_id=_analysis.RECORDING_ID, started_at=None):
    found = store.loads(Recording, recording_id)
    if found is not None:
        return found
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state="downloaded",
            started_at=started_at or datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=_analysis.DURATION_S,
        )
    )


def runs_analysis(store, recording, channel, moments):
    """The analyze job as `sermon-work` runs it, its notifications going to `channel`."""
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=5,
            dedupe_key=f"analyze:{recording.recording_id}:{len(store.lists(Job))}",
            queued_at=moments(),
        )
    )
    RunsAnalyzeJob(
        store=store,
        stages=lambda _name: None,
        notifies=delivers(store, channel, moments),
        clock=moments,
        recording_id=recording.recording_id,
    )()
    return store.loads(Recording, recording.recording_id)


def finishes_analysis(store, rows, channel, moments, recording_id=_analysis.RECORDING_ID, started_at=None):
    recording = registered(store, recording_id, started_at)
    _analysis.lays_out(
        store, recording, [(_analysis.READS(start), _analysis.READS(end), *rest) for start, end, *rest in rows]
    )
    return runs_analysis(store, recording, channel, moments)


def fails_analysis(store, channel, moments):
    """A Recording with no transcript, drained by the worker until its analyze budget is spent."""
    recording = registered(store)
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=ANALYZE_ATTEMPTS,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=moments(),
        )
    )
    worker = RunsQueuedJobs(
        store=store,
        downloads=refuses_other_work,
        analyzes=RunsAnalyzeJob(
            store=store, stages=lambda _name: None, notifies=delivers(store, channel, moments), clock=moments
        ),
        renders=refuses_other_work,
        clock=moments,
    )
    for _ in range(ANALYZE_ATTEMPTS):
        worker()
        moments.passes(WORKER_POLL_GAP)
    assert not store.lists(Job, kind="analyze", state="queued"), "the analyze job was still queued"
    return store.loads(Recording, recording.recording_id)


def approved_segment(store):
    recording = replace(registered(store), state="reviewed")
    store.saves(recording)
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            intent="publish",
            label="Hebrews 12.4-11",
            span_start_seconds=1900.0,
            span_end_seconds=4360.0,
            punch_in_seconds=1900.0,
            punch_out_seconds=4360.0,
        )
    )


def renders(store, segment, channel, moments, failing_step=None):
    def steps(name):
        if name == failing_step:
            raise StepFailed(name, "the encoder exited with status 1")

    try:
        RendersSegment(store=store, steps=steps, notifies=delivers(store, channel, moments), clock=moments)(segment)
    except StepFailed:
        pass
    return store.loads(Segment, segment.segment_id)


def sweeps(store, channel, moments, days):
    """The worker's idle poll, once a day for `days` days."""
    for _ in range(days):
        moments.passes(timedelta(days=1))
        RemindsReviewer(store=store, notifies=delivers(store, channel, moments), clock=moments)()


def raised(store, **criteria):
    return store.lists(Notification, **criteria)


def the_only(store, **criteria):
    found = raised(store, **criteria)
    assert len(found) == 1, [(item.kind, item.summary) for item in found]
    return found[0]


def failure_of(store, **criteria):
    errors = [item.error for item in store.lists(LogEntry, **criteria) if item.kind == "state_change" and item.error]
    assert errors, "the product logged no failure"
    return errors[-1]


def formats_length(seconds):
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def labelled(segment):
    return replace(segment, intent="publish", label="Hebrews 12.4-11")


def the_recording(store):
    return _analysis.the_recording(store)
