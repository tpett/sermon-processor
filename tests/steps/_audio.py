"""Real audio for steps that must hear something, cached between runs."""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from sermon.pipeline import preview
from sermon.store import Artifact

CACHE = Path(tempfile.gettempdir()) / "sermon-test-audio"
SHORT_SECONDS = 12.0
MEAN_VOLUME = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB")
TONE_HZ = 220


def _runs(arguments):
    finished = subprocess.run(arguments, capture_output=True, text=True)
    if finished.returncode != 0:
        raise RuntimeError(finished.stderr.strip())
    return finished.stderr


def _channel_one(seconds):
    if seconds > SHORT_SECONDS:
        return f"anullsrc=r=44100:cl=mono:d={seconds}"
    return f"sine=frequency={TONE_HZ}:sample_rate=44100:duration={seconds}"


def stereo_source(seconds=SHORT_SECONDS):
    """A stereo FLAC shaped like the recorder's: signal on 1, silence on 2."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"source-{seconds:g}s.flac"
    if path.is_file() and path.stat().st_size:
        return path
    partial = path.with_name(path.name + ".partial.flac")
    _runs([
        "ffmpeg", "-v", "error",
        "-f", "lavfi", "-i", _channel_one(seconds),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={seconds}",
        "-filter_complex", "[0:a][1:a]amerge=inputs=2[merged]",
        "-map", "[merged]", "-t", f"{seconds}",
        "-c:a", "flac", "-sample_fmt", "s32", "-y", str(partial),
    ])
    partial.replace(path)
    return path


def rendition(seconds):
    """A real preview. Long ones are the short one's frames copied, not re-encoded."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"preview-{seconds:g}s-{preview.KBPS}k{preview.SUFFIX}"
    if path.is_file() and path.stat().st_size:
        return path
    if seconds <= SHORT_SECONDS:
        return preview.encodes(stereo_source(seconds), path)
    partial = path.with_name(path.name + ".partial.mp3")
    _runs([
        "ffmpeg", "-v", "error",
        "-stream_loop", str(int(seconds // SHORT_SECONDS) + 1),
        "-i", str(rendition(SHORT_SECONDS)),
        "-c", "copy", "-t", f"{seconds}", "-f", "mp3", "-y", str(partial),
    ])
    partial.replace(path)
    return path


def places(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)
    return destination


def local_source(store, recording, seconds=SHORT_SECONDS):
    stored = store.saves(
        replace(recording, local_path=recording.object_key, duration_seconds=float(seconds))
    )
    places(stereo_source(seconds), store.resolves(stored))
    return stored


def cached_encoder(seconds):
    """A stand-in for the encoder that hands back an already rendered preview."""
    ready = rendition(seconds)

    def encodes(source, destination, channel=preview.SOURCE_CHANNEL):
        return places(ready, destination)

    return encodes


def mean_volume_db(path, filters=None):
    chain = ",".join([*(filters or []), "volumedetect"])
    measured = _runs([
        "ffmpeg", "-v", "info", "-nostats", "-i", str(path),
        "-af", chain, "-f", "null", "-",
    ])
    found = MEAN_VOLUME.findall(measured)
    return float(found[-1]) if found else None


def registers_preview(store, recording, seconds=None):
    length = float(seconds or recording.duration_seconds or SHORT_SECONDS)
    ready = rendition(length)
    artifact = Artifact(
        recording_id=recording.recording_id,
        kind="preview",
        path=f"{recording.recording_id}/preview{preview.SUFFIX}",
        size_bytes=0,
        checksum="",
    )
    places(ready, store.resolves(artifact))
    return store.saves(
        replace(
            artifact,
            size_bytes=ready.stat().st_size,
            checksum=f"preview-{length:g}s",
            render_settings={
                **preview.settings(),
                "duration_seconds": length,
                "measured_kbps": preview.KBPS,
            },
        )
    )


def spoken_source(name, seconds, channel_one):
    """A stereo FLAC whose channel 1 is `channel_one`, an ffmpeg expression in t."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"source-{name}-{seconds:g}s.flac"
    if path.is_file() and path.stat().st_size:
        return path
    partial = path.with_name(path.name + ".partial.flac")
    _runs([
        "ffmpeg", "-v", "error",
        "-f", "lavfi", "-i", f"aevalsrc='{channel_one}':s=44100:d={seconds}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={seconds}",
        "-filter_complex", "[0:a][1:a]amerge=inputs=2[merged]",
        "-map", "[merged]", "-t", f"{seconds}",
        "-c:a", "flac", "-sample_fmt", "s32", "-y", str(partial),
    ])
    partial.replace(path)
    return path


def holds_source(store, recording, source):
    stored = store.saves(replace(recording, local_path=recording.object_key, state="downloaded"))
    places(source, store.resolves(stored))
    return stored
