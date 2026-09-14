#!/usr/bin/env python3
"""Score proposed segments against the Stage 0 ground truth.

Also computes the ORACLE for each recording: the smallest boundary error any
rung could achieve given the transcript it was handed. Without that, a bad
result cannot be attributed — reasoning failure and transcript limitation look
identical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
TOLERANCES = (0.25, 0.5, 1.0, 2.0, 5.0)


def load_groundtruth() -> dict[str, dict]:
    gt = json.loads((DATA / "groundtruth.json").read_text())
    return {r["recording_id"]: r for r in gt["recordings"] if r.get("recording_id")}


def oracle(true_t: float, doc: dict) -> float:
    """Smallest achievable error: distance to the nearest utterance edge."""
    edges = [u["start"] for u in doc["utterances"]] + [u["end"] for u in doc["utterances"]]
    edges += [s["start"] for s in doc["silences"]] + [s["end"] for s in doc["silences"]]
    return min((abs(e - true_t) for e in edges), default=float("inf"))


def best_match(proposed: list[dict], true_seg: dict) -> dict | None:
    """The proposed segment overlapping the truth most, if it overlaps at all."""
    ti, to = true_seg["punch_in"], true_seg["punch_out"]
    span = to - ti
    best, best_ov = None, 0.0
    for p in proposed:
        ov = max(0.0, min(to, p["punch_out"]) - max(ti, p["punch_in"]))
        if ov > best_ov:
            best, best_ov = p, ov
    return best if best_ov > span / 2 else None


def _match_raw(proposal: dict, true_seg: dict):
    """The model's own boundaries, before our refinement stage touched them.

    Scored alongside the derived ones because an adversarial review found the
    refinement was making the best config *worse* — 2.1x on punch-in — while the
    write-up attributed the residual error to the model.
    """
    raw = proposal.get("model_segments") or []
    norm = []
    for s in raw:
        if "punch_in" in s and "punch_out" in s:
            try:
                norm.append({"punch_in": float(s["punch_in"]),
                             "punch_out": float(s["punch_out"])})
            except (TypeError, ValueError):
                continue
    return best_match(norm, true_seg)


def score_one(rec: dict, doc: dict, proposal: dict, config_id: str, stage: int) -> list[dict]:
    rows = []
    for true_seg in rec.get("segments", []):
        m = best_match(proposal.get("segments", []), true_seg)
        row = {
            "config_id": config_id,
            "stage": stage,
            "recording_id": rec["recording_id"],
            "desktop_label": rec["desktop_label"],
            "split": rec["split"],
            "true_in": true_seg["punch_in"],
            "true_out": true_seg["punch_out"],
            "difficulty_in": true_seg["difficulty_in"]["label"],
            "difficulty_out": true_seg["difficulty_out"]["label"],
            "oracle_in": round(oracle(true_seg["punch_in"], doc), 3),
            "oracle_out": round(oracle(true_seg["punch_out"], doc), 3),
            "n_proposed": len(proposal.get("segments", [])),
            "found": m is not None,
        }
        if m:
            row |= {
                "punch_in_error": round(m["punch_in"] - true_seg["punch_in"], 3),
                "punch_out_error": round(m["punch_out"] - true_seg["punch_out"], 3),
                "classification": m.get("classification"),
            }
        raw = _match_raw(proposal, true_seg)
        if raw:
            row |= {
                "raw_found": True,
                "raw_in_error": round(raw["punch_in"] - true_seg["punch_in"], 3),
                "raw_out_error": round(raw["punch_out"] - true_seg["punch_out"], 3),
            }
        rows.append(row)

    # A recording with no published output should get no proposal. Scored
    # separately, because inventing work is a different failure from missing it.
    #
    # "No segments" means two different things, though, and only one of them is a
    # negative. A recording nobody has edited yet has no segments because nobody
    # has looked -- a *correct* proposal on it then reads as a false positive.
    # Measured 2026-09-14: the 09-06 and 09-13 services were both being counted
    # against the false-positive rate for finding the sermon that is really there.
    if not rec.get("segments") and rec.get("split") != "blind":
        rows.append({
            "config_id": config_id, "stage": stage,
            "recording_id": rec["recording_id"], "desktop_label": rec["desktop_label"],
            "split": "negative", "true_in": None, "true_out": None,
            "n_proposed": len(proposal.get("segments", [])),
            "false_positive": len(proposal.get("segments", [])) > 0,
        })
    return rows


def summarise(rows: list[dict]) -> None:
    by_cfg: dict[str, list[dict]] = {}
    for r in rows:
        by_cfg.setdefault(r["config_id"], []).append(r)

    hdr = (f"{'config':<34} {'split':<9} {'n':>3} {'found':>6} " +
           " ".join(f"{'≤'+str(t)+'s':>7}" for t in TOLERANCES) +
           f" {'med|in|':>8} {'med|out|':>9}")
    print(hdr)
    print("-" * len(hdr))
    for cfg, rs in sorted(by_cfg.items()):
        for split in ("dev", "test", "two-level", "negative"):
            sel = [r for r in rs if r["split"] == split and r.get("true_in") is not None]
            if split == "negative":
                neg = [r for r in rs if r["split"] == "negative"]
                if neg:
                    fp = sum(1 for r in neg if r.get("false_positive"))
                    print(f"{cfg[:33]:<34} {'negative':<9} {len(neg):>3} "
                          f"{len(neg)-fp:>5}/{len(neg)} false positives: {fp}")
                continue
            if not sel:
                continue
            found = [r for r in sel if r["found"]]
            cells = []
            for t in TOLERANCES:
                ok = sum(1 for r in found
                         if abs(r["punch_in_error"]) <= t and abs(r["punch_out_error"]) <= t)
                cells.append(f"{100*ok/len(sel):6.0f}%")
            mi = sorted(abs(r["punch_in_error"]) for r in found)
            mo = sorted(abs(r["punch_out_error"]) for r in found)
            med = lambda a: float(np.median(a)) if a else float("nan")
            print(f"{cfg[:33]:<34} {split:<9} {len(sel):>3} "
                  f"{100*len(found)/len(sel):5.0f}% " + " ".join(cells) +
                  f" {med(mi):7.2f}s {med(mo):8.2f}s")

    orc = [r for r in rows if r.get("oracle_in") is not None]
    if orc:
        oi = sorted(r["oracle_in"] for r in orc)
        oo = sorted(r["oracle_out"] for r in orc)
        print(f"\noracle (best possible given these transcripts): "
              f"median |in| {oi[len(oi)//2]:.2f}s, median |out| {oo[len(oo)//2]:.2f}s, "
              f"worst |in| {oi[-1]:.2f}s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="config_id to score")
    ap.add_argument("--stage", type=int, default=1)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "fresh", "blind", "all"])
    ap.add_argument("--final", action="store_true",
                    help="required to score the held-out split; logs the access")
    ap.add_argument("--asr", default="whisper-large-v3-turbo+words")
    args = ap.parse_args()

    if args.split in ("test", "all") and not args.final:
        print("refusing to score the held-out split without --final.\n"
              "tune on --split dev; a --final run is one-shot and is logged.")
        return 2
    if args.final:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or "no-git"
        with (DATA / "test_access.log").open("a") as f:
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t"
                    f"{args.config}\t{args.split}\t{commit}\n")

    gt = load_groundtruth()
    rows = []
    for rid, rec in gt.items():
        split, is_negative = rec["split"], not rec.get("segments")
        # Recordings that produced several published outputs are scored whenever
        # their split is asked for, or under --split all. They are the only test
        # of the several-segments-from-one-recording model the spec is built on.
        if args.split != "all" and not is_negative and split != args.split:
            continue
        prop_path = DATA / "blocks" / f"{rid}.{args.config}.json"
        doc_path = DATA / "transcripts" / f"{rid}.{args.asr}.json"
        if not prop_path.exists() or not doc_path.exists():
            continue
        rows += score_one(rec, json.loads(doc_path.read_text()),
                          json.loads(prop_path.read_text()), args.config, args.stage)

    if not rows:
        print("no results to score — has classify.py run for this config?")
        return 1

    with (DATA / "results.jsonl").open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    summarise(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
