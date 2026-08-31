#!/usr/bin/env python3
"""Is the punch-in even *proposed* as a block boundary?

If blocking divides the recording correctly, the sermon punch-in should already
be a block edge and refinement should be trivial. Everything downstream that
reaches backwards into the previous block is compensating for a boundary that
was drawn in the wrong place.

So the question is which of these is failing:
  (a) no block boundary is drawn near the true punch-in  -> blocking is wrong
  (b) one is drawn, but the wrong block is chosen        -> selection is wrong
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import features as F  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
ASR = "whisper-large-v3-turbo+words"


def nearest(edges, t):
    return min((abs(e - t) for e in edges), default=float("inf"))


def chosen_start(cfg: str, rid: str):
    p = DATA / "blocks" / f"{rid}.{cfg}.json"
    if not p.exists():
        return None, None
    d = json.loads(p.read_text())
    edges = [b["start"] for b in d["blocks"]] + [b["end"] for b in d["blocks"]]
    seg = d["segments"][0] if d["segments"] else None
    return edges, (seg["punch_in"] if seg else None)


gt = json.loads((DATA / "groundtruth.json").read_text())
CFGS = ["t3-qwen3.6.whole.v2", "c-frontier.whole.v2", "t3-qwen3.6.structured.v2"]

print(f"{'recording':<30}{'diar':>8}{'  |':>3}"
      + "".join(f"{c.split('.')[0][:12]:>26}" for c in CFGS))
print(f"{'':<30}{'edge':>8}{'  |':>3}" + "".join(f"{'nearest edge':>13}{'chosen':>13}" for c in CFGS))

acc = {c: {"edge": [], "chosen": []} for c in CFGS}
diar_acc = []
for rec in gt["recordings"]:
    rid = rec.get("recording_id")
    if not rid or not rec.get("segments") or rec["split"] != "dev":
        continue
    tp = DATA / "transcripts" / f"{rid}.{ASR}.json"
    dp = DATA / "diarization" / f"{rid}.json"
    if not tp.exists():
        continue
    doc = json.loads(tp.read_text())
    pi = rec["segments"][0]["punch_in"]

    d_edge = float("inf")
    if dp.exists():
        dia = json.loads(dp.read_text())
        blks = F.blocks_from_diarization(doc, dia)
        d_edge = nearest([b["start"] for b in blks] + [b["end"] for b in blks], pi)
        diar_acc.append(d_edge)

    row = f"{rec['desktop_label'][:29]:<30}{d_edge:7.1f}s{'  |':>3}"
    for c in CFGS:
        edges, chosen = chosen_start(c, rid)
        if edges is None:
            row += f"{'--':>13}{'--':>13}"
            continue
        e = nearest(edges, pi)
        acc[c]["edge"].append(e)
        row += f"{e:12.1f}s"
        if chosen is None:
            row += f"{'none':>13}"
        else:
            acc[c]["chosen"].append(abs(chosen - pi))
            row += f"{chosen - pi:+12.1f}s"
    print(row)

print()
if diar_acc:
    print(f"diarization block edges : median {np.median(diar_acc):6.1f}s   "
          f"within 5s {sum(1 for x in diar_acc if x <= 5)}/{len(diar_acc)}")
for c in CFGS:
    e, ch = acc[c]["edge"], acc[c]["chosen"]
    if not e:
        continue
    print(f"{c[:24]:<24}: nearest edge median {np.median(e):6.1f}s "
          f"(within 5s {sum(1 for x in e if x <= 5)}/{len(e)})   "
          f"chosen median {np.median(ch):6.1f}s "
          f"(within 5s {sum(1 for x in ch if x <= 5)}/{len(ch)})")
