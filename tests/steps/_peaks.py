import base64
import subprocess
from dataclasses import replace

import numpy as np

from sermon.analysis.io import reads_json, writes_json
from sermon.jobs.generates_waveform_peaks import (
    DETAIL_HZ,
    FULL_SCALE,
    OVERVIEW_BINS,
    Resolution,
    folds,
)

TONE_RATE = 4000
TONE_AMPLITUDE = 0.5
SYLLABLE_HZ = 3.0
PHRASE_SECONDS = 7.0


def reads_peaks(store, recording):
    return reads_json(store, recording, "waveform_peaks") or {}


def signed(encoded):
    return [value - 256 if value > 127 else value for value in base64.b64decode(encoded)]


def writes_peaks(store, recording):
    seconds = recording.duration_seconds or 0.0
    bins = max(int(seconds * DETAIL_HZ), 1)
    moment = np.arange(bins) / DETAIL_HZ
    syllables = (0.5 + 0.5 * np.sin(2 * np.pi * SYLLABLE_HZ * moment)) ** 2
    phrases = np.sin(2 * np.pi * moment / PHRASE_SECONDS)
    breathing = np.where(phrases > -0.2, 1.0, 0.02)
    envelope = (0.08 + 0.55 * syllables) * breathing * FULL_SCALE
    detail = Resolution(
        bins=bins,
        seconds_per_bin=1.0 / DETAIL_HZ,
        lows=(-envelope).astype(np.int8),
        highs=envelope.astype(np.int8),
    )
    return writes_json(
        store,
        recording,
        "waveform_peaks",
        {
            "recording_id": recording.recording_id,
            "duration_seconds": detail.seconds,
            "full_scale": FULL_SCALE,
            "normalized": False,
            "measured": True,
            "resolutions": {
                "overview": folds(detail, OVERVIEW_BINS).sent(),
                "detail": detail.sent(),
            },
        },
    )


def writes_tone(store, recording, *, amplitude=TONE_AMPLITUDE):
    return writes_sound(store, recording, f"{amplitude}*sin(2*PI*440*t)")


def writes_sound(store, recording, expression):
    seconds = recording.duration_seconds or 0.0
    local_path = f"{recording.recording_id}/source.flac"
    destination = store.resolves(replace(recording, local_path=local_path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi",
            "-i", f"aevalsrc={expression}:s={TONE_RATE}:d={seconds}",
            "-c:a", "flac", str(destination),
        ],
        check=True,
    )
    return store.saves(replace(recording, local_path=local_path))


def writes_speaker_turns(store, recording, turns):
    return writes_json(store, recording, "diarization", {"turns": list(turns)})


def writes_unmeasured_peaks(store, recording):
    return writes_json(
        store,
        recording,
        "waveform_peaks",
        {
            "recording_id": recording.recording_id,
            "duration_seconds": recording.duration_seconds or 0.0,
            "full_scale": FULL_SCALE,
            "normalized": False,
            "measured": False,
            "resolutions": {},
        },
    )


def writes_utterances(store, recording, spoken):
    return writes_json(
        store,
        recording,
        "transcript",
        {
            "utterances": [
                {"start": start, "end": end, "text": text, "speaker": "preacher"}
                for start, end, text in spoken
            ]
        },
    )
