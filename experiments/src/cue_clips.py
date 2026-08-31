#!/usr/bin/env python3
"""Render the cue excerpts so a human can judge whether they identify the block."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import classify as C  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
OUT = WORK / "cues"
PAD = 0.4
MIN_S, MAX_S = 4.0, 12.0

src_map = {r["desktop_label"]: r["source_path"]
           for r in json.loads((DATA / "groundtruth.json").read_text())["recordings"]}
d = json.loads((WORK / "summaries.qwen3-4b.json").read_text())
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*.mp3"): f.unlink()

n = 0
for i, b in enumerate(d["blocks"]):
    if not b.get("cue"): continue
    a, e = b["cue"]
    e = max(e, a + MIN_S); e = min(e, a + MAX_S)
    name = f"{i:02d} {b['type']} @ {C.hms(a).replace(':','.')}.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0,a-PAD):.3f}",
                    "-t", f"{e-a+2*PAD:.3f}", "-i", src_map[d["label"]],
                    "-af", "pan=mono|c0=c0,loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a", "libmp3lame", "-q:a", "5", "-y", str(OUT / name)],
                   check=True)
    n += 1
    print(f"  {name:<44} {b['summary'][:60]}")
print(f"\nwrote {n} cue excerpts to {OUT}")
