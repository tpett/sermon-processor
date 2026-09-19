"""Spike 1 — the render chain. Turn an approved span into a publishable MP3.

Encodes the decisions taken in QUESTIONS.md:
  Q66  take channel 1 and discard channel 2; never average (the source is a mono
       signal fed into a stereo recorder, so a downmix costs 6 dB)
  Q49  one loudness operation, not normalize-then-compress
  Q48  -16 LUFS integrated, -1.5 dBTP ceiling
  Q50  mono MP3, 44.1 kHz, around 100 kbps
  Q47  short fades so the cut does not click

Two-pass loudnorm: measure the trimmed span, then correct it. Single-pass
loudnorm is a dynamic filter and will not hit a target reliably on programme
material this long.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

TARGET_I = -16.0
TARGET_TP = -1.5
TARGET_LRA = 11.0
FADE_S = 0.02
# -q:a 5 gave 68-77 kbps mono against the 96-108 kbps of the hand-made files.
# Not audibly worse for speech, but matching what is already shipped removes a
# variable from the listening test.
LAME_Q = 3


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stderr


def measure(src: Path, start: float, dur: float) -> dict:
    """Pass 1 — loudnorm's own measurement of the span we are about to render."""
    err = _run(["ffmpeg", "-v", "info", "-nostats",
                "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                "-af", f"pan=mono|c0=c0,loudnorm=I={TARGET_I}:TP={TARGET_TP}:"
                       f"LRA={TARGET_LRA}:print_format=json",
                "-f", "null", "-"])
    a, b = err.rfind("{"), err.rfind("}")
    if a < 0 or b < a:
        raise RuntimeError("loudnorm measurement pass produced no JSON")
    return json.loads(err[a:b + 1])


def render(src: Path, start: float, end: float, dst: Path,
           loudness: bool = True, fades: bool = True) -> dict:
    dur = end - start
    dst.parent.mkdir(parents=True, exist_ok=True)

    chain = ["pan=mono|c0=c0"]
    m = {}
    if loudness:
        m = measure(src, start, dur)
        chain.append(
            f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"offset={m['target_offset']}:linear=true:print_format=summary")
    if fades:
        chain.append(f"afade=t=in:st=0:d={FADE_S}")
        chain.append(f"afade=t=out:st={max(dur - FADE_S, 0):.3f}:d={FADE_S}")

    _run(["ffmpeg", "-v", "error", "-nostats",
          "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
          "-af", ",".join(chain),
          "-c:a", "libmp3lame", "-q:a", str(LAME_Q), "-ar", "44100", "-ac", "1",
          "-y", str(dst)])
    return m


def probe_loudness(path: Path) -> dict:
    err = _run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path),
                "-filter_complex", "ebur128=peak=true", "-f", "null", "-"])
    tail = err[-1400:]
    out = {}
    for key, label in (("I", "I:"), ("LRA", "LRA:"), ("Peak", "Peak:")):
        for line in reversed(tail.splitlines()):
            s = line.strip()
            if s.startswith(label):
                try:
                    out[key] = float(s.split()[1])
                except (IndexError, ValueError):
                    pass
                break
    return out


def probe_format(path: Path) -> dict:
    o = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,bit_rate,size", "-show_entries", "stream=channels,sample_rate",
         "-of", "json", str(path)], capture_output=True, text=True).stdout
    d = json.loads(o)
    st = (d.get("streams") or [{}])[0]
    fm = d.get("format", {})
    return {"duration": float(fm.get("duration", 0)),
            "kbps": int(fm.get("bit_rate", 0)) // 1000,
            "mb": int(fm.get("size", 0)) / 1e6,
            "channels": st.get("channels"), "sr": st.get("sample_rate")}
