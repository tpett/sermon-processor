"""Real 43-minute renders of synthesised programme material, cached between runs.

The cache is keyed on the render chain's own digest, so editing the chain
re-renders everything rather than handing back what the old chain produced.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple
from dataclasses import replace
from pathlib import Path

from sermon.jobs import renders_kept_audio as kept_chain
from sermon.jobs.probes_recording import MeasuresRecordingAudio, ProbeResult, ProbesRecording
from sermon.jobs.renders_mp3 import RendersMp3
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.pipeline import render as chain
from sermon.sends_notification import SendsNotification

CACHE = Path(tempfile.gettempdir()) / "sermon-test-renders"

SOURCE_SECONDS = 9872.0
CONTENT_START = 7212.0
CYCLE_SECONDS = 30.0
FLOOR_UNTIL = 2.0
QUIET_UNTIL = 6.0
FLOOR_GAIN = 0.001
QUIET_GAIN = 0.105
AMPLITUDE = 0.353
SWING = "(0.85+0.15*sin(2*PI*t/150))"
TONES = (
    "0.30*sin(2*PI*(140+40*sin(2*PI*0.7*t))*t)"
    "+0.20*sin(2*PI*880*t)"
    "+0.15*sin(2*PI*3300*t)"
    "+0.12*sin(2*PI*7000*t)"
    "+0.10*sin(2*PI*12000*t)"
    "+0.08*sin(2*PI*16000*t)"
)
FRICATIVE_AMPLITUDE = 0.30
SYLLABLE_HZ = 4.5
SYLLABLE_DEPTH = 0.6

ISOLATED_PEAK_AT = 8000.5
ISOLATED_PEAK_SECONDS = 0.3
ISOLATED_PEAK_GAIN = 3.981
ISOLATED_PEAK_HEADROOM = 0.398
CLIPPED_AT = 8300.0
CLIPPED_SECONDS = 0.3
CLIPPED_GAIN = 2.9

Variant = namedtuple("Variant", "amplitude envelope")

VARIANTS = {
    "default": Variant(amplitude=1.0, envelope=None),
    "quieter": Variant(amplitude=0.398, envelope=None),
    "isolated peak": Variant(
        amplitude=ISOLATED_PEAK_HEADROOM,
        envelope=f"if(between(t,{ISOLATED_PEAK_AT - CONTENT_START},"
        f"{ISOLATED_PEAK_AT + ISOLATED_PEAK_SECONDS - CONTENT_START}),{ISOLATED_PEAK_GAIN},1)",
    ),
    "clipped": Variant(
        amplitude=1.0,
        envelope=f"if(between(t,{CLIPPED_AT - CONTENT_START},"
        f"{CLIPPED_AT + CLIPPED_SECONDS - CONTENT_START}),{CLIPPED_GAIN},1)",
    ),
    "very quiet": Variant(amplitude=0.189, envelope=None),
}

MEAN_VOLUME = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB")
PEAK_LEVEL = re.compile(r"Peak level dB:\s*(-?\d+(?:\.\d+)?)")
MP3_FRAME_SECONDS = 1152 / 44100
SPOKEN_WORD_SECONDS = 0.15
REVIEWER = "reviewer"


def _runs(arguments):
    finished = subprocess.run(arguments, capture_output=True, text=True)
    if finished.returncode != 0:
        raise RuntimeError(finished.stderr.strip()[-2000:])
    return finished.stderr


def places(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)
    return destination


def copies(source, destination):
    """A render a later pass may overwrite; sharing the inode would erase it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _digests(*parts):
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]


def _recipe():
    return _digests(
        *sorted(VARIANTS.items()),
        AMPLITUDE,
        TONES,
        FRICATIVE_AMPLITUDE,
        SYLLABLE_HZ,
        SWING,
        SOURCE_SECONDS,
        CONTENT_START,
        CYCLE_SECONDS,
        FLOOR_UNTIL,
        QUIET_UNTIL,
        FLOOR_GAIN,
        QUIET_GAIN,
        SYLLABLE_DEPTH,
    )


def _memo(key, compute):
    CACHE.mkdir(parents=True, exist_ok=True)
    held = CACHE / f"{key}.json"
    if held.is_file():
        return json.loads(held.read_text())
    value = compute()
    held.write_text(json.dumps(value))
    return value


def _fingerprint(path):
    size = path.stat().st_size
    with path.open("rb") as held:
        held.seek(size // 2)
        middle = held.read(1 << 20)
    return _digests(size, hashlib.sha256(middle).hexdigest())


def _envelope(amplitude, extra):
    levels = (
        f"if(lt(mod(t,{CYCLE_SECONDS}),{FLOOR_UNTIL}),{FLOOR_GAIN},"
        f"if(lt(mod(t,{CYCLE_SECONDS}),{QUIET_UNTIL}),{QUIET_GAIN},1))"
    )
    return f"{AMPLITUDE * amplitude}*{SWING}*{levels}" + (f"*{extra}" if extra else "")


def _generates(destination, amplitude, extra):
    content = SOURCE_SECONDS - CONTENT_START
    _runs([
        "ffmpeg", "-v", "error",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={CONTENT_START}",
        "-f", "lavfi", "-i", f"aevalsrc={TONES}:s=44100:c=mono:d={content}",
        "-f", "lavfi",
        "-i", f"anoisesrc=c=white:r=44100:a={FRICATIVE_AMPLITUDE}:d={content}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={SOURCE_SECONDS}",
        "-filter_complex",
        f"[1:a][2:a]amix=inputs=2:normalize=0,"
        f"tremolo=f={SYLLABLE_HZ}:d={SYLLABLE_DEPTH},"
        f"volume=volume='{_envelope(amplitude, extra)}':eval=frame[spoken];"
        f"[0:a][spoken]concat=n=2:v=0:a=1[one];"
        f"[one][3:a]amerge=inputs=2[both]",
        "-map", "[both]", "-t", f"{SOURCE_SECONDS}",
        "-c:a", "flac", "-sample_fmt", "s32", "-y", str(destination),
    ])
    return destination


def source(variant="default"):
    """The source the Background describes: 44.1 kHz stereo, channel 2 silent."""
    CACHE.mkdir(parents=True, exist_ok=True)
    held = CACHE / f"source-{variant.replace(' ', '-')}-{_recipe()}.flac"
    if held.is_file() and held.stat().st_size:
        return held
    partial = held.with_suffix(".partial.flac")
    _generates(partial, *VARIANTS[variant])
    partial.replace(held)
    return held


def _window(arguments, start=None, length=None):
    return [
        *(["-ss", f"{start:.3f}"] if start is not None else []),
        *(["-t", f"{length:.3f}"] if length is not None else []),
        *arguments,
    ]


def loudness(path, start=None, length=None, filters=None):
    def measures():
        report = _runs([
            "ffmpeg", "-nostats", "-hide_banner",
            *_window(["-i", str(path)], start, length),
            "-filter_complex", f"{filters + ',' if filters else ''}ebur128=peak=true",
            "-f", "null", "-",
        ])
        return _reads_ebur128(report)

    return _memo(_digests("loudness", _fingerprint(path), start, length, filters), measures)


def _reads_ebur128(report):
    tail = report[-1400:]
    found = {}
    for key, label in (("I", "I:"), ("LRA", "LRA:"), ("Peak", "Peak:")):
        for line in reversed(tail.splitlines()):
            spoken = line.strip()
            if spoken.startswith(label):
                found[key] = float(spoken.split()[1])
                break
    return found


def level_db(path, start=None, length=None, filters=None):
    def measures():
        chained = ",".join([*([filters] if filters else []), "volumedetect"])
        report = _runs([
            "ffmpeg", "-v", "info", "-nostats",
            *_window(["-i", str(path)], start, length),
            "-af", chained, "-f", "null", "-",
        ])
        return float(MEAN_VOLUME.findall(report)[-1])

    return _memo(_digests("level", _fingerprint(path), start, length, filters), measures)


def tail_level_db(path, length):
    """The last stretch of a file, seeked from the end so no frame is missed."""
    def measures():
        report = _runs([
            "ffmpeg", "-v", "info", "-nostats", "-sseof", f"-{length:.3f}",
            "-i", str(path), "-af", "volumedetect", "-f", "null", "-",
        ])
        return float(MEAN_VOLUME.findall(report)[-1])

    return _memo(_digests("tail", _fingerprint(path), length), measures)


def frame_sizes(path):
    """How many distinct sizes the encoded frames take; a constant rate takes two."""
    def measures():
        listed = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "packet=size", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True,
        ).stdout.split()
        return len({int(one) for one in listed if one.isdigit()})

    return _memo(_digests("frames", _fingerprint(path)), measures)


def peak_db(path, start=None, length=None):
    def measures():
        report = _runs([
            "ffmpeg", "-v", "info", "-nostats", "-hide_banner",
            *_window(["-i", str(path)], start, length),
            "-af", "astats=measure_perchannel=none", "-f", "null", "-",
        ])
        return float(PEAK_LEVEL.findall(report)[-1])

    return _memo(_digests("peak", _fingerprint(path), start, length), measures)


def _cycle_at(after):
    ordinal = max(0, int((after - CONTENT_START) // CYCLE_SECONDS) + 1)
    return CONTENT_START + ordinal * CYCLE_SECONDS


def floor_window(after):
    """Near-silence at the top of a cycle: the source's own noise floor."""
    return _cycle_at(after) + 0.2, FLOOR_UNTIL - 0.4


def quiet_window(after):
    """The passage the speech stands more than 18 dB above."""
    return _cycle_at(after) + FLOOR_UNTIL + 0.2, QUIET_UNTIL - FLOOR_UNTIL - 0.4


def speech_window(after):
    return _cycle_at(after) + QUIET_UNTIL + 0.5, 10.0


def isolated_peak_window():
    return ISOLATED_PEAK_AT, ISOLATED_PEAK_SECONDS


def clipped_window():
    return CLIPPED_AT, CLIPPED_SECONDS


def _chain_digest(removed):
    digests = [hashlib.sha256(Path(chain.__file__).read_bytes()).hexdigest()]
    if removed:
        digests.append(hashlib.sha256(Path(kept_chain.__file__).read_bytes()).hexdigest())
    return digests


def _renders_or_reuses(source_path, start, end, destination, channel=0, removed=()):
    leaving_out = [(span.start_seconds, span.end_seconds) for span in removed]
    key = _digests(
        "mp3",
        _fingerprint(source_path),
        start,
        end,
        channel,
        *([leaving_out] if leaving_out else []),
        *_chain_digest(removed),
    )
    held = CACHE / f"render-{key}.mp3"
    measured = CACHE / f"render-{key}.json"
    if held.is_file() and held.stat().st_size and measured.is_file():
        copies(held, destination)
        return json.loads(measured.read_text())
    found = kept_chain.renders_kept_audio(
        source_path, start, end, destination, channel=channel, removed=removed
    )
    if not destination.is_file():
        raise RuntimeError(f"the render chain wrote nothing to {destination}")
    CACHE.mkdir(parents=True, exist_ok=True)
    copies(destination, held)
    measured.write_text(json.dumps(found))
    return found


def renders_span(source_path, start, end):
    """The chain's output for a span, so one render can be compared against another."""
    destination = Path(tempfile.mkdtemp()) / "span.mp3"
    _renders_or_reuses(source_path, start, end, destination)
    return destination


def _keeps(renderer, produced):
    def renders_and_keeps(*arguments, **named):
        rendered = renderer(*arguments, **named)
        produced.append(rendered)
        return rendered

    return renders_and_keeps


def _snapshots(rendered):
    """A re-render overwrites the published name, so each output is kept aside."""
    aside = Path(tempfile.mkdtemp()) / rendered.path.name
    return replace(rendered, path=copies(rendered.path, aside))


def renders(store, reuse=True):
    """Drain one queued render job through the production path and keep its output."""
    produced = []
    RunsRenderJob(
        store=store,
        steps=lambda _name: None,
        notifies=SendsNotification(store=store),
        renders=_keeps(
            RendersMp3(
                renders=_renders_or_reuses if reuse else kept_chain.renders_kept_audio,
                probes_loudness=loudness,
            ),
            produced,
        ),
    )()
    return _snapshots(produced[-1]) if produced else None


def probes(store, recording):
    """The real probe, over measurements taken once and cached."""
    path = store.resolves(recording)
    fields = _memo(
        _digests("probe", _fingerprint(path)),
        lambda: _measured_fields(MeasuresRecordingAudio()(path)),
    )
    return ProbesRecording(store=store, measures=lambda _held: _rebuilds(fields))(recording)


def _measured_fields(result):
    return {
        "duration_seconds": result.duration_seconds,
        "sample_rate": result.sample_rate,
        "channels": result.channels,
        "channel_levels": [
            {"channel": level.channel, "rms_db": level.rms_db} for level in result.channel_levels
        ],
        "integrated_loudness_lufs": result.integrated_loudness_lufs,
        "true_peak_dbtp": result.true_peak_dbtp,
        "loudness_range_lu": result.loudness_range_lu,
    }


def _rebuilds(fields):
    from sermon.store import ChannelLevel

    return ProbeResult(
        duration_seconds=fields["duration_seconds"],
        sample_rate=fields["sample_rate"],
        channels=fields["channels"],
        channel_levels=tuple(
            ChannelLevel(channel=level["channel"], rms_db=level["rms_db"])
            for level in fields["channel_levels"]
        ),
        integrated_loudness_lufs=fields["integrated_loudness_lufs"],
        true_peak_dbtp=fields["true_peak_dbtp"],
        loudness_range_lu=fields["loudness_range_lu"],
    )
