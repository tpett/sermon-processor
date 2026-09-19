from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, kw_only=True)
class Recording:
    recording_id: str
    object_key: str
    state: str
    started_at: datetime
    started_at_source: str
    size_bytes: int
    capture_device: str | None = None
    kind: str | None = None
    duration_seconds: float | None = None
    channels: int | None = None
    sample_rate: int | None = None
    bits_per_raw_sample: int | None = None
    channel_levels: tuple[ChannelLevel, ...] = ()
    mono_source: str | None = None
    mono_source_confirmed: bool | None = None
    local_path: str | None = None
    checksum: str | None = None
    sidecar_present: bool | None = None
    integrated_loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_range_lu: float | None = None
    dynamic_range_db: float | None = None
    active_fraction: float | None = None
    longest_active_seconds: float | None = None
    waiting_since: datetime | None = None
    warnings: tuple[str, ...] = ()
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
    possibly_multiple_types: bool = False
    speaker_matches: tuple[SpeakerMatch, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Segment:
    segment_id: int | None = None
    recording_id: str
    seed_block_id: int | None = None
    classification: str
    state: str
    span_start_seconds: float
    span_end_seconds: float
    punch_in_seconds: float
    punch_out_seconds: float
    intent: str | None = None
    disposition_at: datetime | None = None
    distribution_confirmed: bool | None = None
    confirmed_speaker_profile_id: int | None = None
    boundary_source: str | None = None
    leading_silence_seconds: float | None = None
    summary: str | None = None
    warnings: tuple[str, ...] = ()
    publication_date: date | None = None
    label: str | None = None


@dataclass(frozen=True, kw_only=True)
class Evidence:
    timecode: float
    finding: str
    implies: str


@dataclass(frozen=True, kw_only=True)
class ChannelLevel:
    channel: int
    rms_db: float


@dataclass(frozen=True, kw_only=True)
class Candidate:
    timecode: float
    considered_because: str


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
    punch_in_grade: str
    punch_out_grade: str
    agreement_gap_seconds: float | None = None
    superseded_by: int | None = None
    evidence: tuple[Evidence, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    punch_in_candidates: tuple[Candidate, ...] = ()


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
    enrolled_from: tuple[int, ...] = ()
    confirmed_by_human: bool = False


@dataclass(frozen=True, kw_only=True)
class Reviewer:
    actor: str
    receives_notifications: bool = True


@dataclass(frozen=True, kw_only=True)
class Notification:
    notification_id: int | None = None
    recording_id: str | None = None
    segment_id: int | None = None
    kind: str
    recipient: str
    summary: str
    created_at: datetime
    state: str


@dataclass(frozen=True, kw_only=True)
class LogEntry:
    log_entry_id: int | None = None
    recording_id: str
    segment_id: int | None = None
    job_id: int | None = None
    proposal_id: int | None = None
    artifact_id: int | None = None
    kind: str
    occurred_at: datetime
    correlation_id: str
    actor: str | None = None
    entered_state: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    punch_in_seconds: float | None = None
    punch_out_seconds: float | None = None
    boundary_source: str | None = None


@dataclass(frozen=True, kw_only=True)
class SkippedObject:
    object_key: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class Discovery:
    discovery_id: int | None = None
    kind: str
    occurred_at: datetime
    discovered_count: int
    failure: str | None = None
    event: str | None = None


@dataclass(frozen=True, kw_only=True)
class CorpusPair:
    corpus_pair_id: int | None = None
    recording_id: str
    classification: str
    provenance: str
    alignment: str | None = None
    punch_in_seconds: float | None = None
    punch_out_seconds: float | None = None
    drift_ppm: float | None = None
    punch_in_difficulty: str | None = None
    punch_out_difficulty: str | None = None
    covers_more_than_95_percent: bool = False
