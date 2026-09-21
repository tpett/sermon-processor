from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sermon.pipeline.render import (
    FADE_S,
    LAME_Q,
    TARGET_I,
    TARGET_LRA,
    TARGET_TP,
    probe_format,
    probe_loudness,
    render,
)

PUBLISHED_I = -17.0
TOLERANCE_LU = 1.0
CEILING_TP = TARGET_TP
LOWEST_KBPS = 96
HIGHEST_KBPS = 108
CHANNEL_NAMES = {"channel 1": 0, "channel 2": 1}


class ChannelsNeedReview(RuntimeError):
    pass


class RenderProducedNothing(RuntimeError):
    pass


def reads_source_channel(mono_source):
    return CHANNEL_NAMES.get(mono_source or "", 0)


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

    def misses(self):
        return ()


@dataclass(frozen=True)
class RendersMp3:
    renders: object = render

    def __call__(self, source, start, end, destination, channel=0):
        raise NotImplementedError(str(destination))
