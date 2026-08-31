#!/usr/bin/env python3
"""Is the punch-out visible in the waveform?

The editor's own trick: the closing prayer is quiet, there is a brief pause, and
then the communion pitch comes in noticeably louder. If that step is real and
measurable, it is a punch-out heuristic that owes nothing to the transcript —
and punch-out is the one boundary the lexical rules already handle well, so this
is a cross-check rather than a replacement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
HZ = 100


def db(env: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.maximum(env, 1e-6))


def window_mean(d: np.ndarray, a: float, b: float) -> float:
    i, j = max(0, int(a * HZ)), min(len(d), int(b * HZ))
    return float(np.mean(d[i:j])) if j > i else float("nan")


def profile(d: np.ndarray, t: float, w: float = 25.0) -> dict:
    """Level before, level after, and the quietest point around a boundary."""
    before = window_mean(d, t - w, t)
    after = window_mean(d, t, t + w)
    i = int(t * HZ)
    lo, hi = max(0, i - int(8 * HZ)), min(len(d), i + int(8 * HZ))
    local = d[lo:hi]
    return {"before": before, "after": after, "step": after - before,
            "dip": float(np.min(local)) if len(local) else float("nan"),
            "dip_rel": (float(np.min(local)) - before) if len(local) else float("nan")}


def main() -> int:
    gt = json.loads((DATA / "groundtruth.json").read_text())
    rows = []
    for rec in gt["recordings"]:
        if not rec.get("segments") or rec["split"] not in ("dev",):
            continue
        env_path = WORK / "env" / f"{rec['desktop_label']}.{HZ}hz.npy"
        if not env_path.exists():
            continue
        d = db(np.load(env_path))
        for s in rec["segments"]:
            p_out = profile(d, s["punch_out"])
            p_in = profile(d, s["punch_in"])
            # A control: the same measurement at 40 random points, to show
            # whether the step at the true punch-out is actually distinctive.
            rng = np.random.default_rng(0)
            span = s["punch_out"] - s["punch_in"]
            rand = [profile(d, float(x))["step"]
                    for x in rng.uniform(s["punch_in"] + 60, s["punch_out"] - 60, 40)]
            rows.append({"label": rec["desktop_label"], "kind": rec.get("split"),
                         "out": p_out, "in": p_in,
                         "rand_p90": float(np.percentile(rand, 90)),
                         "rand_max": float(np.max(rand))})

    print(f"{'recording':<34}{'before':>8}{'after':>8}{'STEP':>8}{'dip':>8}"
          f"{'  |  in-step':>12}{'rand p90':>10}{'rand max':>10}")
    for r in rows:
        o, i = r["out"], r["in"]
        print(f"{r['label'][:33]:<34}{o['before']:7.1f} {o['after']:7.1f} "
              f"{o['step']:+7.1f} {o['dip_rel']:+7.1f}"
              f"{i['step']:+11.1f} {r['rand_p90']:+9.1f} {r['rand_max']:+9.1f}")

    steps = [r["out"]["step"] for r in rows]
    dips = [r["out"]["dip_rel"] for r in rows]
    p90 = [r["rand_p90"] for r in rows]
    print(f"\npunch-out step:      median {np.median(steps):+.1f} dB   "
          f"positive on {sum(1 for s in steps if s > 0)}/{len(steps)}")
    print(f"punch-out local dip: median {np.median(dips):+.1f} dB below the run-up")
    print(f"random-point step:   median p90 {np.median(p90):+.1f} dB  "
          f"— the bar the real step has to clear to be distinctive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
