"""The seekable review rendition — features/analysis/preview_audio.feature.

One constant-bitrate file, so the byte offset of a moment is arithmetic and no
seek index is read before the first seek. Channel 1 only, never a downmix.
No loudness treatment: that decision belongs to the published render.

KBPS is the measured candidate's 37.6 MB over a 104-minute source. "Seekability
buys quality back" is raising this number and nothing else.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

KBPS = 48
SAMPLE_RATE = 44100
CHANNELS = 1
CODEC = "libmp3lame"
SUFFIX = ".mp3"
MEDIA_TYPE = "audio/mpeg"
SOURCE_CHANNEL = 0
BYTES_PER_SECOND = KBPS * 1000 // 8


class PreviewUnavailable(RuntimeError):
    pass


class PreviewEncodingFailed(PreviewUnavailable):
    pass


def byte_offset(seconds, size_bytes=None, bytes_per_second=BYTES_PER_SECOND):
    """Where a moment sits in the file: arithmetic, because the bitrate is constant."""
    offset = max(0, int(seconds * bytes_per_second))
    if size_bytes is None:
        return offset
    return min(offset, max(size_bytes - 1, 0))


def byte_range(seconds, window_seconds, size_bytes=None):
    start = byte_offset(seconds, size_bytes)
    end = byte_offset(seconds + window_seconds, size_bytes)
    return start, max(end, start)


def channel_filter(channel: int = SOURCE_CHANNEL) -> str:
    return f"pan=mono|c0=c{channel}"


def settings(channel: int = SOURCE_CHANNEL) -> dict:
    return {
        "codec": CODEC,
        "bitrate_kbps": KBPS,
        "constant_bitrate": True,
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "source_channel": channel + 1,
        "channel_filter": channel_filter(channel),
    }


def command(source: Path, destination: Path, channel: int = SOURCE_CHANNEL) -> list[str]:
    return [
        "ffmpeg", "-v", "error", "-nostats",
        "-i", str(source),
        "-af", channel_filter(channel),
        "-c:a", CODEC,
        "-b:a", f"{KBPS}k",
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-f", "mp3",
        "-y", str(destination),
    ]


def encodes(source: Path, destination: Path, channel: int = SOURCE_CHANNEL) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    finished = subprocess.run(command(source, partial), capture_output=True, text=True)
    if finished.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise PreviewEncodingFailed(finished.stderr.strip() or str(source))
    partial.replace(destination)
    return destination
