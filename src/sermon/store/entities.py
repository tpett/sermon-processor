from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, kw_only=True)
class Recording:
    recording_id: str
    object_key: str
    state: str
    started_at: datetime
    size_bytes: int
    kind: str | None = None
    duration_seconds: float | None = None
    channels: int | None = None
    sample_rate: int | None = None
    bits_per_raw_sample: int | None = None
    local_path: str | None = None
    checksum: str | None = None
    dynamic_range_db: float | None = None
    active_fraction: float | None = None
    longest_active_seconds: float | None = None
    waiting_since: datetime | None = None
    skip_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class Block:
    block_id: int | None = None
    recording_id: str
    start_seconds: float
    end_seconds: float
    type: str
    classification_confidence: str | None = None
    self_reported_confidence: float | None = None
    evidence: tuple[Evidence, ...] = ()
    summary: str | None = None
    cue_start_seconds: float | None = None
    cue_end_seconds: float | None = None
    retyped_by_human: bool = False
    speaker_matches: tuple[SpeakerMatch, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Segment:
    segment_id: int | None = None
    recording_id: str
    seed_block_id: int | None = None
    classification: str
    state: str
    punch_in_seconds: float
    punch_out_seconds: float
    proposed_punch_in: float | None = None
    proposed_punch_out: float | None = None
    intent: str | None = None
    disposition_at: datetime | None = None
    distribution_confirmed: bool | None = None
    boundary_source: str | None = None
    leading_silence_seconds: float | None = None
    publication_date: date | None = None
    label: str | None = None


@dataclass(frozen=True, kw_only=True)
class Evidence:
    timecode: float
    finding: str
    implies: str


@dataclass(frozen=True, kw_only=True)
class SpeakerMatch:
    speaker_profile_id: int
    similarity: float


@dataclass(frozen=True, kw_only=True)
class Proposal:
    proposal_id: int | None = None
    segment_id: int
    classification_confidence: str
    boundary_confidence: str
    punch_in_difficulty: str
    punch_out_difficulty: str
    agreement_gap_seconds: float | None = None
    superseded_by: int | None = None
    evidence: tuple[Evidence, ...] = ()
    missing_evidence: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Artifact:
    artifact_id: int | None = None
    recording_id: str
    segment_id: int | None = None
    kind: str
    path: str
    size_bytes: int
    checksum: str
    render_settings: dict | None = None
    asr_config: dict | None = None
    superseded_by: int | None = None


@dataclass(frozen=True, kw_only=True)
class Job:
    job_id: int | None = None
    recording_id: str
    segment_id: int | None = None
    kind: str
    state: str
    attempts: int = 0
    max_attempts: int
    dedupe_key: str
    last_error: str | None = None
    failed_permanently: bool = False
    queued_at: datetime
    started_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class SpeakerProfile:
    speaker_profile_id: int | None = None
    name: str
    embedding: bytes
    enrolled_from: tuple[str, ...] = ()
    confirmed_by_human: bool = False


@dataclass(frozen=True, kw_only=True)
class Notification:
    notification_id: int | None = None
    recording_id: str
    segment_id: int | None = None
    kind: str
    recipient: str
    summary: str
    created_at: datetime
    state: str
