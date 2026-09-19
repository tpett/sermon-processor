#!/usr/bin/env python3
"""Spike 2 — export real data for the waveform + words interface.

Everything the page needs, from one real recording: multi-resolution peaks, every
word with its timestamp, the classified blocks, the true boundaries, and a short
audio excerpt so playback can be demonstrated inside a self-contained page.
"""
from __future__ import annotations

import base64, json, subprocess, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import audio  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
ASR = "whisper-large-v3-turbo+words"
LABEL = "2026-08-23 - Hebrews 12.4-11"
CLIP_S = 75.0          # audio window embedded for the playback demo


def peaks(env: np.ndarray, n: int) -> list[int]:
    """Downsample an envelope to n buckets, 0-100."""
    if len(env) == 0:
        return []
    idx = np.linspace(0, len(env), n + 1).astype(int)
    out = []
    mx = float(np.percentile(env, 99.9)) or 1.0
    for i in range(n):
        seg = env[idx[i]:idx[i + 1]]
        out.append(int(min(100, 100 * float(seg.max()) / mx)) if len(seg) else 0)
    return out


def main() -> int:
    gt = json.loads((DATA / "groundtruth.json").read_text())
    rec = next(r for r in gt["recordings"] if r["desktop_label"] == LABEL)
    doc = json.loads((DATA / "transcripts" / f"{rec['recording_id']}.{ASR}.json").read_text())
    seg = rec["segments"][0]

    env = np.load(WORK / "env" / f"{LABEL}.100hz.npy")
    dur = rec["source_duration"]

    words = []
    for u in doc["utterances"]:
        for w in u.get("words", []):
            words.append([round(w["start"], 2), round(w["end"] - w["start"], 2), w["w"]])
    words.sort(key=lambda x: x[0])

    blocks = []
    bp = DATA / "blocks" / f"{rec['recording_id']}.c-frontier.whole.v2.json"
    if bp.exists():
        for b in json.loads(bp.read_text())["blocks"]:
            blocks.append([round(b["start"], 1), round(b["end"], 1), b["type"]])

    # A window of real audio around the punch-in, so the page can actually play.
    clip_start = max(0.0, seg["punch_in"] - CLIP_S / 2)
    tmp = WORK / "ui_clip.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{clip_start:.3f}",
                    "-t", f"{CLIP_S:.3f}", "-i", rec["source_path"],
                    "-af", "pan=mono|c0=c0", "-c:a", "libmp3lame", "-q:a", "6",
                    "-ar", "22050", "-ac", "1", "-y", str(tmp)], check=True)
    b64 = base64.b64encode(tmp.read_bytes()).decode()

    payload = {
        "label": LABEL,
        "recording_id": rec["recording_id"],
        "started_at": rec["started_at"],
        "duration": dur,
        "truth": {"punch_in": seg["punch_in"], "punch_out": seg["punch_out"]},
        "overview": peaks(env, 1800),
        "detail_hz": 100,
        "detail": [int(min(100, x)) for x in
                   (100 * env / (float(np.percentile(env, 99.9)) or 1.0)).astype(int)],
        "words": words,
        "blocks": blocks,
        "clip": {"start": round(clip_start, 3), "seconds": CLIP_S,
                 "data": f"data:audio/mpeg;base64,{b64}"},
    }
    out = WORK / "ui_data.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"{LABEL}: {dur/60:.0f} min, {len(words)} words, {len(blocks)} blocks, "
          f"{len(payload['detail'])} detail peaks")
    print(f"audio clip {CLIP_S:.0f}s = {len(b64)/1e6:.2f} MB base64")
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
