from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace

from datetime import UTC, datetime

from sermon.pipeline.render import probe_format, probe_loudness
from sermon.store import ChannelLevel, LogEntry, Recording, Store


def now():
    return datetime.now(UTC)


class AudioNotMeasurable(RuntimeError):
    pass


SILENT_RMS_DB = -80.0
SILENCE_FLOOR_DB = -120.0
EMPTY_DYNAMIC_RANGE_DB = 12.0
EMPTY_ACTIVE_FRACTION = 0.01
CHANNEL_LEVELS = "astats=measure_overall=none:measure_perchannel=RMS_level"
CHANNEL_LINE = "Channel:"
RMS_LINE = "RMS level dB:"


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


def reads_channel_levels(report):
    levels = []
    channel = None
    for line in report.splitlines():
        spoken = line.partition("] ")[2] or line
        if spoken.startswith(CHANNEL_LINE):
            channel = int(spoken.split()[1])
        elif spoken.startswith(RMS_LINE) and channel is not None:
            levels.append(ChannelLevel(channel=channel, rms_db=reads_decibels(spoken)))
            channel = None
    return tuple(levels)


def reads_decibels(line):
    spoken = line.rpartition(":")[2].strip()
    try:
        value = float(spoken)
    except ValueError:
        return SILENCE_FLOOR_DB
    return SILENCE_FLOOR_DB if value < SILENCE_FLOOR_DB else value


def runs_ffmpeg(command):
    return subprocess.run(command, capture_output=True, text=True).stderr


@dataclass(frozen=True)
class MeasuresRecordingAudio:
    resolves: object = None
    runs: object = runs_ffmpeg

    def __call__(self, held):
        path = held if self.resolves is None else self.resolves(held)
        if path is None or not path.is_file():
            raise AudioNotMeasurable(str(path))
        try:
            format_report = probe_format(path)
        except (ValueError, KeyError) as unreadable:
            raise AudioNotMeasurable(str(path)) from unreadable
        if not format_report.get("channels") or not format_report.get("duration"):
            raise AudioNotMeasurable(str(path))
        loudness = probe_loudness(path)
        return ProbeResult(
            duration_seconds=format_report["duration"],
            sample_rate=int(format_report["sr"]),
            channels=format_report["channels"],
            channel_levels=reads_channel_levels(
                self.runs([
                    "ffmpeg", "-v", "info", "-nostats", "-hide_banner",
                    "-i", str(path), "-af", CHANNEL_LEVELS, "-f", "null", "-",
                ])
            ),
            integrated_loudness_lufs=loudness.get("I"),
            true_peak_dbtp=loudness.get("Peak"),
            loudness_range_lu=loudness.get("LRA"),
        )


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
