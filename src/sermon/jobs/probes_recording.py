from __future__ import annotations

from dataclasses import dataclass, replace

from datetime import UTC, datetime

from sermon.store import ChannelLevel, LogEntry, Recording, Store


def now():
    return datetime.now(UTC)

SILENT_RMS_DB = -80.0
EMPTY_DYNAMIC_RANGE_DB = 12.0
EMPTY_ACTIVE_FRACTION = 0.01


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float
    sample_rate: int
    channels: int
    bits_per_raw_sample: int | None = None
    channel_levels: tuple[ChannelLevel, ...] = ()
    integrated_loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_range_lu: float | None = None
    dynamic_range_db: float | None = None
    active_fraction: float | None = None
    damaged_container: bool = False


@dataclass(frozen=True)
class ProbesRecording:
    store: Store
    measures: object

    def __call__(self, recording):
        measured = self.measures(recording)
        warnings = list(recording.warnings)
        mono_source = recording.mono_source
        if measured.channel_levels:
            silent = [level.channel for level in measured.channel_levels if level.rms_db <= SILENT_RMS_DB]
            live = [level.channel for level in measured.channel_levels if level.rms_db > SILENT_RMS_DB]
            if len(live) == 1:
                mono_source = f"channel {live[0]}"
            elif len(live) > 1 and "unexpected stereo content" not in warnings:
                warnings.append("unexpected stereo content")
        if measured.true_peak_dbtp is not None and measured.true_peak_dbtp >= 0.0:
            if "source clipping detected" not in warnings:
                warnings.append("source clipping detected")
        if measured.damaged_container and "damaged container" not in warnings:
            warnings.append("damaged container")
        silent = (
            measured.dynamic_range_db == 0
            or measured.active_fraction == 0
        )
        empty = (
            measured.dynamic_range_db is not None
            and measured.dynamic_range_db <= EMPTY_DYNAMIC_RANGE_DB
        ) or (
            measured.active_fraction is not None
            and measured.active_fraction <= EMPTY_ACTIVE_FRACTION
        )
        if silent:
            state = "analysis_failed"
        elif empty:
            state = "ignored"
        else:
            state = recording.state
        saved = self.store.saves(
            replace(
                recording,
                state=state,
                duration_seconds=measured.duration_seconds,
                sample_rate=measured.sample_rate,
                channels=measured.channels,
                bits_per_raw_sample=measured.bits_per_raw_sample,
                channel_levels=measured.channel_levels,
                integrated_loudness_lufs=measured.integrated_loudness_lufs,
                true_peak_dbtp=measured.true_peak_dbtp,
                loudness_range_lu=measured.loudness_range_lu,
                dynamic_range_db=measured.dynamic_range_db,
                active_fraction=measured.active_fraction,
                mono_source=mono_source,
                warnings=tuple(warnings),
            )
        )
        if state == "analysis_failed":
            self.store.saves(
                LogEntry(
                    recording_id=recording.recording_id,
                    kind="state_change",
                    occurred_at=now(),
                    correlation_id=f"probe:{recording.recording_id}",
                    entered_state="analysis_failed",
                    error="no audio content",
                )
            )
        return saved
