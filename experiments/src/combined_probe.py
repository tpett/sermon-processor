#!/usr/bin/env python3
"""Acoustic region + lexical anchor.

Neither cue is sufficient alone. The waveform trick finds the right *region* but
lands where the communion speech starts, tens of seconds late. The lexical rule
("last amen") is exact but cannot tell a closing amen from a mid-sermon one, so
searching a long window picks the wrong one.

Used together the acoustic step narrows the window and the amen supplies the
exact point.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import acoustic as A  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
ASR = "whisper-large-v3-turbo+words"
BACK_S = 90.0   # how far back from the level rise to look for the closing amen


def last_amen_before(doc: dict, t: float, back: float) -> float | None:
    best = None
    for u in doc["utterances"]:
        if u["end"] <= t + 5.0 and u["end"] >= t - back and "amen" in u["text"].lower():
            best = u["end"]
    return best


gt = json.loads((DATA / "groundtruth.json").read_text())
print(f"{'recording':<34}{'acoustic':>10}{'+amen':>10}{'lexical only':>14}")
comb, acou, lex = [], [], []
for rec in gt["recordings"]:
    if not rec.get("segments") or rec["split"] != "dev":
        continue
    ep = WORK / "env" / f"{rec['desktop_label']}.100hz.npy"
    tp = DATA / "transcripts" / f"{rec['recording_id']}.{ASR}.json"
    if not ep.exists() or not tp.exists():
        continue
    d = A.to_db(np.load(ep))
    doc = json.loads(tp.read_text())
    for s in rec["segments"]:
        lo = s["punch_in"] + (s["punch_out"] - s["punch_in"]) * 0.75
        hi = min(s["punch_out"] + 240, rec["source_duration"])
        cands = A.punch_out_candidates(d, lo, hi, top=4)

        # Acoustic alone: highest-scoring candidate.
        a_err = (cands[0]["t"] - s["punch_out"]) if cands else float("nan")

        # Acoustic region, then the closing amen inside it. Prefer the
        # highest-scoring candidate that actually has an amen behind it.
        c_err = float("nan")
        for c in cands:
            t = last_amen_before(doc, c["t"], BACK_S)
            if t is not None:
                c_err = t - s["punch_out"]
                break

        # Lexical alone, over the whole trailing stretch — the current rule.
        l = last_amen_before(doc, s["punch_out"] + 240, 900.0)
        l_err = (l - s["punch_out"]) if l is not None else float("nan")

        for lst, v in ((acou, a_err), (comb, c_err), (lex, l_err)):
            if np.isfinite(v):
                lst.append(abs(v))
        f = lambda v: f"{v:+.2f}s" if np.isfinite(v) else "   --"
        print(f"{rec['desktop_label'][:33]:<34}{f(a_err):>10}{f(c_err):>10}{f(l_err):>14}")

def summarise(name, xs):
    if not xs:
        print(f"{name:<22} no data"); return
    print(f"{name:<22} median {np.median(xs):7.2f}s   "
          f"≤2s {sum(1 for x in xs if x<=2)}/{len(xs)}   "
          f"≤5s {sum(1 for x in xs if x<=5)}/{len(xs)}")
print()
summarise("acoustic only", acou)
summarise("acoustic + amen", comb)
summarise("lexical only", lex)
