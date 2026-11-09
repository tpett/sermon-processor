from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.settles_recording import SettlesRecording
from sermon.store import Artifact, Job, LogEntry, Notification, Proposal, SpeakerProfile, Store

REMOVABLE = frozenset({"proposed", "skipped", "recut", "processing_failed"})
PUBLISHED = "a published segment cannot be removed"
IN_FLIGHT = "a segment that is rendering cannot be removed"


def now():
    return datetime.now(UTC)


class SegmentCannotBeRemoved(ValueError):
    pass


@dataclass(frozen=True)
class RemovesSegment:
    """Drop a segment that was never published. The source file is untouched."""

    store: Store
    clock: object = now

    def __call__(self, segment, *, actor="reviewer"):
        if self.store.lists(Artifact, segment_id=segment.segment_id):
            raise SegmentCannotBeRemoved(PUBLISHED)
        if segment.state not in REMOVABLE:
            raise SegmentCannotBeRemoved(IN_FLIGHT)
        occurred = self.clock()
        recording_id = segment.recording_id
        identity = segment.segment_id
        jobs = self.store.lists(Job, segment_id=identity)
        proposals = self.store.lists(Proposal, segment_id=identity)
        job_ids = {job.job_id for job in jobs}
        proposal_ids = {proposal.proposal_id for proposal in proposals}
        self._detaches_log(identity, job_ids, proposal_ids)
        self._drops_enrolment(identity)
        self._clears_superseded(proposal_ids)
        for proposal in proposals:
            self.store.forgets(self.store.loads(Proposal, proposal.proposal_id))
        for job in jobs:
            self.store.forgets(job)
        for notice in self.store.lists(Notification, segment_id=identity):
            self.store.forgets(notice)
        self.store.forgets(segment)
        self.store.saves(
            LogEntry(
                recording_id=recording_id,
                kind="segment_removed",
                occurred_at=occurred,
                correlation_id=f"remove:{identity}",
                actor=actor,
                punch_in_seconds=segment.punch_in_seconds,
                punch_out_seconds=segment.punch_out_seconds,
            )
        )
        SettlesRecording(self.store, clock=self.clock)(recording_id)
        return identity

    def _detaches_log(self, identity, job_ids, proposal_ids):
        seen = set()
        entries = list(self.store.lists(LogEntry, segment_id=identity))
        for job_id in job_ids:
            entries.extend(self.store.lists(LogEntry, job_id=job_id))
        for proposal_id in proposal_ids:
            entries.extend(self.store.lists(LogEntry, proposal_id=proposal_id))
        for entry in entries:
            if entry.log_entry_id in seen:
                continue
            seen.add(entry.log_entry_id)
            cleared = replace(
                entry,
                segment_id=None if entry.segment_id == identity else entry.segment_id,
                job_id=None if entry.job_id in job_ids else entry.job_id,
                proposal_id=None if entry.proposal_id in proposal_ids else entry.proposal_id,
            )
            if cleared != entry:
                self.store.saves(cleared)

    def _drops_enrolment(self, identity):
        for profile in self.store.lists(SpeakerProfile):
            if identity not in profile.enrolled_from:
                continue
            self.store.saves(
                replace(
                    profile,
                    enrolled_from=tuple(item for item in profile.enrolled_from if item != identity),
                )
            )

    def _clears_superseded(self, proposal_ids):
        for proposal in self.store.lists(Proposal):
            if proposal.superseded_by in proposal_ids:
                self.store.saves(replace(proposal, superseded_by=None))
