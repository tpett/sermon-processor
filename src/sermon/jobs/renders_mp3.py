from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sermon.jobs.renders_kept_audio import renders_kept_audio
from sermon.pipeline.render import (
    FADE_S,
    LAME_Q,
    TARGET_I,
    TARGET_LRA,
    TARGET_TP,
    probe_format,
    probe_loudness,
)

PUBLISHED_I = -17.0
TOLERANCE_LU = 1.0
CEILING_TP = -0.5
LOWEST_KBPS = 96
HIGHEST_KBPS = 108
CHANNEL_NAMES = {"channel 1": 0, "channel 2": 1}
STEREO_UNSETTLED = "unexpected stereo content"


class ChannelsNeedReview(RuntimeError):
    def __init__(self, recording_id):
        super().__init__(f"{recording_id} carries signal on both channels")


class RenderProducedNothing(RuntimeError):
    pass


def reads_source_channel(mono_source):
    return CHANNEL_NAMES.get(mono_source or "", 0)


def refuses_unsettled_stereo(recording):
    if STEREO_UNSETTLED in recording.warnings and not recording.mono_source_confirmed:
        raise ChannelsNeedReview(recording.recording_id)


@dataclass(frozen=True)
class RenderedAudio:
    path: Path
    size_bytes: int
    duration_seconds: float
    channels: int
    sample_rate: int
    kbps: int
    input_loudness_lufs: float | None
    achieved_loudness_lufs: float | None
    achieved_true_peak_dbtp: float | None
    achieved_loudness_range_lu: float | None
    settings: dict
    input_true_peak_dbtp: float | None = None

    def misses(self):
        missed = []
        if self.achieved_loudness_lufs is None or abs(
            self.achieved_loudness_lufs - PUBLISHED_I
        ) > TOLERANCE_LU:
            missed.append(
                f"integrated loudness {self.achieved_loudness_lufs} LUFS is not "
                f"{PUBLISHED_I} within {TOLERANCE_LU} LU"
            )
        if self.achieved_true_peak_dbtp is None or self.achieved_true_peak_dbtp > CEILING_TP:
            missed.append(
                f"true peak {self.achieved_true_peak_dbtp} dBTP exceeds {CEILING_TP}"
            )
        if not LOWEST_KBPS <= self.kbps <= HIGHEST_KBPS:
            missed.append(
                f"bitrate {self.kbps} kbps is outside {LOWEST_KBPS}-{HIGHEST_KBPS}"
            )
        return tuple(missed)


def reads_loudness(measured, name):
    try:
        return float(measured[name])
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RendersMp3:
    renders: object = renders_kept_audio
    probes_loudness: object = probe_loudness
    probes_format: object = probe_format

    def __call__(self, source, start, end, destination, channel=0, removed=()):
        leaving_out = {"removed": tuple(removed)} if removed else {}
        measured = self.renders(source, start, end, destination, channel=channel, **leaving_out)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RenderProducedNothing(str(destination))
        achieved = self.probes_loudness(destination)
        shape = self.probes_format(destination)
        if not shape.get("duration"):
            raise RenderProducedNothing(str(destination))
        return RenderedAudio(
            path=destination,
            size_bytes=destination.stat().st_size,
            duration_seconds=shape["duration"],
            channels=shape["channels"],
            sample_rate=int(shape["sr"]),
            kbps=shape["kbps"],
            input_loudness_lufs=reads_loudness(measured, "input_i"),
            input_true_peak_dbtp=reads_loudness(measured, "input_tp"),
            achieved_loudness_lufs=achieved.get("I"),
            achieved_true_peak_dbtp=achieved.get("Peak"),
            achieved_loudness_range_lu=achieved.get("LRA"),
            settings={
                "loudness_lufs": TARGET_I,
                "true_peak_dbtp": TARGET_TP,
                "loudness_range_lu": TARGET_LRA,
                "lame_quality": LAME_Q,
                "fade_seconds": FADE_S,
                "sample_rate": shape["sr"],
                "channels": shape["channels"],
                "source_channel": channel + 1,
                **(
                    {"removed_spans": [[span.start_seconds, span.end_seconds] for span in removed]}
                    if removed
                    else {}
                ),
            },
        )
