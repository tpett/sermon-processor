#!/usr/bin/env python3
"""How much would each candidate feature actually buy?

Measures the *oracle* for a feature: the best punch-in and punch-out a perfect
consumer of that feature could achieve. Cheap to run, and it says whether a
feature is worth wiring into the pipeline before any of that work is done.
"""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path(__file__).resolve().parent.parent / "data"
ASR = "whisper-large-v3-turbo+words"


def nearest(edges: list[float], t: float) -> float:
    if not edges:
        return float("inf")
    i = bisect.bisect_left(edges, t)
    best = float("inf")
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(edges):
            best = min(best, abs(edges[j] - t), key=abs) if False else min(best, abs(edges[j] - t))
    return best


def main() -> int:
    gt = json.loads((DATA / "groundtruth.json").read_text())
    rows = []
    for rec in gt["recordings"]:
        rid = rec.get("recording_id")
        if not rid or not rec.get("segments") or rec["split"] != "dev":
            continue
        tpath = DATA / "transcripts" / f"{rid}.{ASR}.json"
        dpath = DATA / "diarization" / f"{rid}.json"
        if not tpath.exists():
            continue
        doc = json.loads(tpath.read_text())

        utt_edges = sorted({u["start"] for u in doc["utterances"]} |
                           {u["end"] for u in doc["utterances"]})
        sil_edges = sorted({s["start"] for s in doc["silences"]} |
                           {s["end"] for s in doc["silences"]})
        dia_edges = []
        if dpath.exists():
            d = json.loads(dpath.read_text())
            dia_edges = sorted({t["start"] for t in d["turns"]} |
                               {t["end"] for t in d["turns"]})

        for s in rec["segments"]:
            rows.append({
                "label": rec["desktop_label"],
                "utt_in": nearest(utt_edges, s["punch_in"]),
                "utt_out": nearest(utt_edges, s["punch_out"]),
                "sil_in": nearest(sil_edges, s["punch_in"]),
                "dia_in": nearest(dia_edges, s["punch_in"]) if dia_edges else None,
                "dia_out": nearest(dia_edges, s["punch_out"]) if dia_edges else None,
                "both_in": min(nearest(utt_edges, s["punch_in"]),
                               nearest(dia_edges, s["punch_in"])) if dia_edges else None,
            })

    if not rows:
        print("nothing to measure yet")
        return 1

    print(f"{'recording':<34}{'utt|in|':>9}{'dia|in|':>9}{'best|in|':>10}"
          f"{'utt|out|':>10}{'dia|out|':>10}")
    for r in rows:
        d_in = f"{r['dia_in']:.2f}s" if r["dia_in"] is not None else "  --"
        b_in = f"{r['both_in']:.2f}s" if r["both_in"] is not None else "  --"
        d_out = f"{r['dia_out']:.2f}s" if r["dia_out"] is not None else "  --"
        print(f"{r['label'][:33]:<34}{r['utt_in']:8.2f}s{d_in:>9}{b_in:>10}"
              f"{r['utt_out']:9.2f}s{d_out:>10}")

    def med(key):
        vals = sorted(x[key] for x in rows if x.get(key) is not None)
        return vals[len(vals) // 2] if vals else float("nan")

    def within(key, t):
        vals = [x[key] for x in rows if x.get(key) is not None]
        return 100 * sum(1 for v in vals if v <= t) / len(vals) if vals else float("nan")

    print(f"\n{'feature':<28}{'median':>9}{'≤0.5s':>8}{'≤1s':>8}{'≤2s':>8}")
    for name, key in (("transcript edges (in)", "utt_in"),
                      ("diarization edges (in)", "dia_in"),
                      ("both (in)", "both_in"),
                      ("transcript edges (out)", "utt_out"),
                      ("diarization edges (out)", "dia_out")):
        if all(x.get(key) is None for x in rows):
            continue
        print(f"{name:<28}{med(key):8.2f}s{within(key,0.5):7.0f}%"
              f"{within(key,1.0):7.0f}%{within(key,2.0):7.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
