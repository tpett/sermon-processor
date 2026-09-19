#!/usr/bin/env python3
"""Can the waveform trick actually find the punch-out?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import acoustic as A  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"

gt = json.loads((DATA / "groundtruth.json").read_text())
print(f"{'recording':<34}{'cands':>6}{'rank':>6}{'err':>9}{'depth':>7}{'step':>7}"
      f"{'  |  top-1 err':>14}")
ranks, errs, top1 = [], [], []
for rec in gt["recordings"]:
    if not rec.get("segments") or rec["split"] != "dev":
        continue
    ep = WORK / "env" / f"{rec['desktop_label']}.100hz.npy"
    if not ep.exists():
        continue
    d = A.to_db(np.load(ep))
    for s in rec["segments"]:
        # Search only the closing stretch of the proposed sermon, which is what
        # a human does: they know roughly where the end is and look for the gap.
        lo = s["punch_in"] + (s["punch_out"] - s["punch_in"]) * 0.75
        hi = min(s["punch_out"] + 240, rec["source_duration"])
        cands = A.punch_out_candidates(d, lo, hi, top=4)
        if not cands:
            print(f"{rec['desktop_label'][:33]:<34}{0:>6}{'-':>6}{'-':>9}")
            continue
        best_i = min(range(len(cands)),
                     key=lambda k: abs(cands[k]["t"] - s["punch_out"]))
        c = cands[best_i]
        err = c["t"] - s["punch_out"]
        t1 = cands[0]["t"] - s["punch_out"]
        ranks.append(best_i + 1); errs.append(abs(err)); top1.append(abs(t1))
        print(f"{rec['desktop_label'][:33]:<34}{len(cands):>6}{best_i+1:>6}"
              f"{err:+8.2f}s{c['depth_db']:>7.1f}{c['rise_db']:>+7.1f}"
              f"{t1:+13.2f}s")

if errs:
    print(f"\nbest candidate: median |err| {np.median(errs):.2f}s, "
          f"within 2s on {sum(1 for e in errs if e <= 2)}/{len(errs)}, "
          f"median rank {np.median(ranks):.0f}")
    print(f"top-scored candidate: median |err| {np.median(top1):.2f}s, "
          f"within 2s on {sum(1 for e in top1 if e <= 2)}/{len(top1)}")
