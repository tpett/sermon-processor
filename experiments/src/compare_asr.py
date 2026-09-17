#!/usr/bin/env python3
"""Does swapping the inference engine move the boundaries?

Punch-ins snap to transcript utterance edges (segments.candidate_edges), so a
different Whisper implementation can move a boundary without getting a single
word wrong. This measures that directly, in three layers:

1. **Edge geometry** — for each human punch-in and punch-out, how far is the
   nearest transcript edge under each engine? That is the oracle: the best any
   downstream stage could do with the transcript it was handed.
2. **Text agreement** — word counts and utterance counts, to separate "the
   timestamps moved" from "it heard something different".
3. **End-to-end** — re-derive segments from stored blocks against each
   transcript and compare the boundary errors that actually result.

Layer 3 holds the model's *blocks* fixed on purpose. Those came from the mlx
transcript, so reusing them isolates the refinement-and-snapping effect from the
separate question of whether the model would classify differently. A full
re-classification is the next experiment, not this one.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import score as S      # noqa: E402
import segments as SEG  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"


def load(rid: str, asr: str) -> dict | None:
    p = DATA / "transcripts" / f"{rid}.{asr}.json"
    return json.loads(p.read_text()) if p.exists() else None


def nearest_edge(t: float, doc: dict) -> float:
    edges = [u["start"] for u in doc["utterances"]] + [u["end"] for u in doc["utterances"]]
    return min((abs(e - t) for e in edges), default=float("inf"))


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="whisper-large-v3-turbo+words")
    ap.add_argument("--alt", required=True)
    ap.add_argument("--config", default="t3-qwen3.6.whole.v2",
                    help="whose stored blocks to re-derive against")
    args = ap.parse_args()

    gt = S.load_groundtruth()
    rows, textrows, e2e = [], [], []

    for rid, rec in sorted(gt.items()):
        if not rec.get("segments"):
            continue
        a, b = load(rid, args.base), load(rid, args.alt)
        if not a or not b:
            continue

        wa = sum(len(u.get("words", [])) for u in a["utterances"])
        wb = sum(len(u.get("words", [])) for u in b["utterances"])
        textrows.append((rec["desktop_label"], len(a["utterances"]), len(b["utterances"]), wa, wb))

        for seg in rec["segments"]:
            rows.append({
                "label": rec["desktop_label"],
                "in_base": nearest_edge(seg["punch_in"], a),
                "in_alt": nearest_edge(seg["punch_in"], b),
                "out_base": nearest_edge(seg["punch_out"], a),
                "out_alt": nearest_edge(seg["punch_out"], b),
            })

        bp = DATA / "blocks" / f"{rid}.{args.config}.json"
        if not bp.exists():
            continue
        stored = json.loads(bp.read_text())
        blocks = stored["blocks"]
        model_segs = stored.get("model_segments") or []
        for doc, tag in ((a, "base"), (b, "alt")):
            SEG._EDGE_CACHE.clear()
            derived = SEG.derive(blocks, doc)
            # The shipping path: the model's own punch-in (never snapped to a
            # transcript edge) with refinement's punch-out. This is the one that
            # matters -- `refined` alone is a diagnostic, not what runs.
            shipped = SEG.choose(model_segs, derived, doc)
            for seg in rec["segments"]:
                m = S.best_match(derived, seg)
                if m:
                    e2e.append({"label": rec["desktop_label"], "which": tag,
                                "layer": "refined", "in_err": m["punch_in"] - seg["punch_in"],
                                "out_err": m["punch_out"] - seg["punch_out"]})
                k = S.best_match(shipped, seg)
                if k:
                    e2e.append({"label": rec["desktop_label"], "which": tag,
                                "layer": "shipped", "in_err": k["punch_in"] - seg["punch_in"],
                                "out_err": k["punch_out"] - seg["punch_out"]})

    if not rows:
        print(f"no recordings have both {args.base} and {args.alt}")
        return 1

    print(f"base = {args.base}\nalt  = {args.alt}\n")

    print("=== 1. text agreement ===")
    print(f"{'recording':<34}{'utts base':>10}{'alt':>7}{'words base':>12}{'alt':>8}{'Δwords':>8}")
    for label, ua, ub, wa, wb in textrows:
        print(f"{label[:33]:<34}{ua:>10}{ub:>7}{wa:>12}{wb:>8}{wb-wa:>+8}")

    print("\n=== 2. nearest transcript edge to the human cut (the oracle) ===")
    print(f"{'recording':<34}{'in base':>9}{'in alt':>9}{'out base':>10}{'out alt':>9}")
    for r in rows:
        print(f"{r['label'][:33]:<34}{r['in_base']:>9.2f}{r['in_alt']:>9.2f}"
              f"{r['out_base']:>10.2f}{r['out_alt']:>9.2f}")
    print(f"{'median':<34}{med([r['in_base'] for r in rows]):>9.2f}"
          f"{med([r['in_alt'] for r in rows]):>9.2f}"
          f"{med([r['out_base'] for r in rows]):>10.2f}"
          f"{med([r['out_alt'] for r in rows]):>9.2f}")
    worse = sum(1 for r in rows if r["in_alt"] > r["in_base"] + 0.05)
    better = sum(1 for r in rows if r["in_alt"] < r["in_base"] - 0.05)
    print(f"\npunch-in oracle: {worse} worse, {better} better, "
          f"{len(rows)-worse-better} within 50 ms")

    if e2e:
        print("\n=== 3. boundaries derived, blocks held fixed ===")
        for layer in ("refined", "shipped"):
            print(f"  -- {layer} --")
            for which in ("base", "alt"):
                sel = [r for r in e2e if r["which"] == which and r["layer"] == layer]
                if not sel:
                    continue
                i1 = sum(1 for r in sel if abs(r["in_err"]) <= 1)
                o1 = sum(1 for r in sel if abs(r["out_err"]) <= 1)
                o2 = sum(1 for r in sel if abs(r["out_err"]) <= 2)
                print(f"     {which:<5} n={len(sel)}  "
                      f"med|in| {med([abs(r['in_err']) for r in sel]):6.2f}s  "
                      f"med|out| {med([abs(r['out_err']) for r in sel]):5.2f}s  "
                      f"in<=1s {i1}/{len(sel)}  out<=1s {o1}/{len(sel)}  out<=2s {o2}/{len(sel)}")
        print()
        e2e = [r for r in e2e if r["layer"] == "shipped"] or e2e
        print("  per recording, SHIPPED path:")
        for which in ("base",):
            sel = [r for r in e2e if r["which"] == which]
            i1 = sum(1 for r in sel if abs(r["in_err"]) <= 1)
            o1 = sum(1 for r in sel if abs(r["out_err"]) <= 1)
            pass
        print(f"  {'recording':<34}{'in base':>9}{'in alt':>9}{'out base':>10}{'out alt':>9}")
        bykey = {}
        for r in e2e:
            bykey.setdefault(r["label"], {})[r["which"]] = r
        for label, d in bykey.items():
            if "base" in d and "alt" in d:
                print(f"  {label[:33]:<34}{d['base']['in_err']:>+9.2f}{d['alt']['in_err']:>+9.2f}"
                      f"{d['base']['out_err']:>+10.2f}{d['alt']['out_err']:>+9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
