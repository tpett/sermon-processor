"""Acoustic punch-out cues, from the editor's own trick.

The closing prayer is quiet, there is a brief pause, then the communion pitch
comes in louder. Measured across the dev sermons, the discriminating part is not
the step up — it is the *dip*: the level at the true punch-out sits 19 to 29 dB
below the surrounding speech, every time, while random points inside a sermon
reach only about +4 dB of step at the 90th percentile.

Continuous speech simply does not go that quiet for that long, which is what
makes the pause visible on a waveform and clickable by eye.
"""
from __future__ import annotations

import numpy as np

HZ = 100
CONTEXT_S = 25.0      # window either side used as the "surrounding speech" level
MIN_DIP_DB = 15.0     # how far below the run-up a pause has to fall to count
MIN_PAUSE_S = 0.6     # and how long it has to stay there


def to_db(env: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.maximum(env, 1e-6))


def find_pauses(d: np.ndarray, lo_s: float, hi_s: float) -> list[dict]:
    """Deep, sustained level drops between two times, scored and ranked.

    Each candidate carries the two things the editor reads off the waveform: how
    far the level fell, and how much louder it is afterwards than before.
    """
    n = len(d)
    lo, hi = max(0, int(lo_s * HZ)), min(n, int(hi_s * HZ))
    if hi - lo < int(2 * CONTEXT_S * HZ):
        return []

    w = int(CONTEXT_S * HZ)
    kernel = np.ones(w) / w
    smooth = np.convolve(d, kernel, mode="same")

    out: list[dict] = []
    i = lo
    while i < hi:
        if d[i] < smooth[i] - MIN_DIP_DB:
            j = i
            while j < hi and d[j] < smooth[j] - MIN_DIP_DB:
                j += 1
            if (j - i) / HZ >= MIN_PAUSE_S:
                a, b = max(0, i - w), min(n, j + w)
                before = float(np.mean(d[a:i])) if i > a else float("nan")
                after = float(np.mean(d[j:b])) if b > j else float("nan")
                depth = before - float(np.min(d[i:j]))
                out.append({
                    "start": round(i / HZ, 3),
                    "end": round(j / HZ, 3),
                    "duration": round((j - i) / HZ, 3),
                    "depth_db": round(depth, 1),
                    "step_db": round(after - before, 1) if np.isfinite(after) else 0.0,
                })
            i = j
        i += 1

    for c in out:
        # Depth says "this is a real pause"; step says "something louder starts
        # here". Both matter, and depth is the more reliable of the two.
        c["score"] = round(c["depth_db"] + 1.5 * max(0.0, c["step_db"]), 2)
    out.sort(key=lambda c: -c["score"])
    return out


LONG_W_S = 60.0       # the prayer is quiet for a while, not for a moment
SNAP_W_S = 25.0       # how far from the level rise to look for the actual pause


def level_rise(d: np.ndarray, lo_s: float, hi_s: float) -> list[dict]:
    """Sustained quiet followed by sustained loud — the shape on the waveform.

    A first attempt scored individual dips and failed badly: a 15 dB drop is just
    an ordinary gap between sentences, so a 15-minute window yields ~180
    candidates and the true punch-out ranks about 100th.

    What is actually distinctive is the *duration* of the quiet. The closing
    prayer is quiet for a minute or more and then the communion pitch arrives
    much louder, so the discriminating measurement is a long-window level step,
    not a short-window dip.
    """
    n = len(d)
    lo, hi = max(0, int(lo_s * HZ)), min(n, int(hi_s * HZ))
    w = int(LONG_W_S * HZ)
    if hi - lo < 2:
        return []

    cs = np.concatenate(([0.0], np.cumsum(d)))

    def mean(a: int, b: int) -> float:
        a, b = max(0, a), min(n, b)
        return (cs[b] - cs[a]) / max(b - a, 1)

    out = []
    for i in range(lo, hi):
        before = mean(i - w, i)
        after = mean(i, i + w)
        out.append({"t": i / HZ, "step": after - before})
    out.sort(key=lambda c: -c["step"])
    return out


def punch_out_candidates(d: np.ndarray, lo_s: float, hi_s: float,
                         top: int = 4) -> list[dict]:
    """Rank plausible punch-outs: find the level rise, then the pause inside it."""
    rises = level_rise(d, lo_s, hi_s)
    if not rises:
        return []

    picked: list[dict] = []
    for r in rises:
        if len(picked) >= top:
            break
        if any(abs(r["t"] - p["rise_t"]) < LONG_W_S for p in picked):
            continue  # same rise, one sample over
        pauses = find_pauses(d, r["t"] - SNAP_W_S, r["t"] + SNAP_W_S)
        if pauses:
            best = max(pauses, key=lambda c: c["depth_db"])
            t = best["end"]
            depth = best["depth_db"]
        else:
            t, depth = r["t"], 0.0
        picked.append({"t": round(t, 3), "rise_t": round(r["t"], 3),
                       "rise_db": round(r["step"], 1), "depth_db": depth,
                       "score": round(r["step"] + 0.3 * depth, 2)})
    picked.sort(key=lambda c: -c["score"])
    return picked
