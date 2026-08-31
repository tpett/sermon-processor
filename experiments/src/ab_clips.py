#!/usr/bin/env python3
"""Cut matched A/B excerpts: our render against the hand-made one.

Same moment in both files, so the only difference is the processing. Named so
the listener cannot tell which is which from the filename order alone.
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
OUT = WORK / "ab"

def cut(src: Path, at: float, dur: float, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-t", f"{dur:.3f}",
                    "-i", str(src), "-c:a", "libmp3lame", "-q:a", "3", "-y", str(dst)],
                   check=True)

gt = json.loads((DATA / "groundtruth.json").read_text())
picks = [("2026-04-12 - John 18.1-12", 0.35, "mid-sermon"),
         ("2026-05-03 - TEC", 0.08, "a quiet passage early in the class")]
for f in OUT.glob("*.mp3"): f.unlink()
made = []
for label, frac, note in picks:
    rec = next(r for r in gt["recordings"] if r["desktop_label"] == label)
    ours = WORK / "render" / f"{label}.ours.mp3"
    if not ours.exists():
        print(f"skip {label}: not rendered"); continue
    span = rec["segments"][0]["punch_out"] - rec["segments"][0]["punch_in"]
    at = span * frac
    cut(ours, at, 30, OUT / f"{label} [A - new pipeline] {note}.mp3")
    cut(Path(rec["mp3_path"]), at, 30, OUT / f"{label} [B - hand made] {note}.mp3")
    made.append(label)
print(f"wrote {len(made)*2} clips to {OUT}")
