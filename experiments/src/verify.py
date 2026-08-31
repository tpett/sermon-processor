#!/usr/bin/env python3
"""Stage 0 verification — consistency checks and the Gate 0 listening clips.

Alignment quality is self-reported by align.py. This checks the things
alignment cannot check about itself: that the numbers are internally coherent,
that the corpus is complete, and that a human can hear whether it is right.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
CLIPS = HERE / "work" / "clips"


def hms(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def checks(gt: dict) -> list[str]:
    """Internal coherence. Anything returned here is a failure."""
    problems = []
    ids = [r["desktop_label"] for r in gt["recordings"]]
    for dup, n in Counter(ids).items():
        if n > 1:
            problems.append(f"{dup}: appears {n} times in the output")

    # An already-edited source — a lossless copy of just the message, which is
    # what the pre-S3 archive contains — yields degenerate ground truth: the
    # punch-in is 0 and the punch-out is the end. Worse than useless, because it
    # would teach that the sermon always starts at the beginning. Legitimate
    # untrimmed archives (a members meeting converted whole) look identical, so
    # this flags rather than excludes.
    for r in gt["recordings"]:
        if not r.get("segments"):
            continue
        published = sum(s["punch_out"] - s["punch_in"] for s in r["segments"])
        coverage = published / max(r["source_duration"], 1)
        if coverage > 0.95:
            problems.append(
                f"{r['desktop_label']}: output covers {100*coverage:.0f}% of the source — "
                f"either an already-edited file (unusable as ground truth) or an "
                f"untrimmed archive (fine, but exclude from boundary statistics)")

    for r in gt["recordings"]:
        label, dur = r["desktop_label"], r["source_duration"]
        for s in r.get("segments", []):
            pin, pout = s["punch_in"], s["punch_out"]
            if pin < 0:
                problems.append(f"{label}: punch_in {pin} is negative")
            if pout > dur + 1.0:
                problems.append(f"{label}: punch_out {pout} past source end {dur}")
            if pout <= pin:
                problems.append(f"{label}: punch_out not after punch_in")
            if r.get("mp3_duration"):
                got, want = pout - pin, r["mp3_duration"]
                if abs(got - want) > 0.05:
                    problems.append(
                        f"{label}: span {got:.3f}s does not match MP3 {want:.3f}s")
        # Two-level: every published segment must sit inside one of the sessions.
        for s in r.get("segments", []):
            if "within_session" not in s:
                continue
            sess = next((x for x in r.get("sessions", [])
                         if x["label"] == s["within_session"] and "start" in x), None)
            if not sess:
                problems.append(f"{label}: segment references an unaligned session")
            elif not (sess["start"] - 1 <= s["punch_in"] and s["punch_out"] <= sess["end"] + 1):
                problems.append(
                    f"{label}: segment {s['punch_in']:.0f}–{s['punch_out']:.0f} "
                    f"falls outside its session {sess['start']:.0f}–{sess['end']:.0f}")
    return problems


def summary(gt: dict) -> None:
    aligned = [r for r in gt["recordings"] if r.get("segments")]
    excluded = [r for r in gt["recordings"]
                if r.get("validation", {}).get("status") == "excluded"]
    negatives = [r for r in gt["recordings"]
                 if r.get("validation", {}).get("status") == "no-output"]

    print(f"{'recording':<34} {'split':<10} {'punch-in':>10} {'punch-out':>10} "
          f"{'len':>8}  {'ncc':>5} {'in':<9} {'out':<9}")
    for r in sorted(aligned, key=lambda x: x["desktop_label"]):
        for s in r["segments"]:
            v = r.get("validation", {})
            ncc = v.get("probe_ncc_min") or s.get("validation", {}).get("probe_ncc_min", 0)
            print(f"{r['desktop_label'][:33]:<34} {r['split']:<10} "
                  f"{hms(s['punch_in']):>10} {hms(s['punch_out']):>10} "
                  f"{hms(s['punch_out']-s['punch_in']):>8}  {ncc:>5.2f} "
                  f"{s['difficulty_in']['label']:<9} {s['difficulty_out']['label']:<9}")

    print(f"\naligned {len(aligned)}  excluded {len(excluded)}  "
          f"negatives (no published output) {len(negatives)}")
    for r in negatives:
        print(f"  negative: {r['desktop_label']}")

    diff = Counter()
    for r in aligned:
        for s in r["segments"]:
            diff[("in", s["difficulty_in"]["label"])] += 1
            diff[("out", s["difficulty_out"]["label"])] += 1
    print("\ncut difficulty")
    for side in ("in", "out"):
        row = "  ".join(f"{lab}={diff[(side, lab)]}" for lab in ("easy", "moderate", "hard"))
        print(f"  punch-{side:<4} {row}")

    ncc_vals = [r["validation"]["probe_ncc_min"] for r in aligned
                if r.get("validation", {}).get("probe_ncc_min")]
    spreads = [r["validation"]["probe_spread_s"] for r in aligned
               if r.get("validation", {}).get("probe_spread_s") is not None]
    if ncc_vals:
        print(f"\nalignment confidence: min NCC {min(ncc_vals):.3f}, "
              f"worst probe spread {max(spreads)*1000:.1f} ms")


def clips(gt: dict, n: int, seconds: float) -> None:
    """Cut listening clips across each derived boundary, for Gate 0.

    A human should hear the sermon begin (and end) exactly where the cut lands.
    """
    CLIPS.mkdir(parents=True, exist_ok=True)
    for f in list(CLIPS.glob("*.flac")) + list(CLIPS.glob("*.mp3")):
        f.unlink()
    aligned = [r for r in gt["recordings"] if r.get("segments")]
    # Spread the sample across the corpus rather than taking the first n.
    step = max(1, len(aligned) // n)
    chosen = aligned[::step][:n]
    made = []
    for r in chosen:
        s = r["segments"][0]
        for side, t in (("in", s["punch_in"]), ("out", s["punch_out"])):
            start = max(0.0, t - seconds / 2)
            name = f"{r['desktop_label'][:30].replace('/', '-')} [{side} @ {hms(t)}].mp3"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}",
                 "-t", f"{seconds:.3f}", "-i", r["source_path"],
                 "-af", "pan=mono|c0=c0", "-b:a", "96k", "-y", str(CLIPS / name)],
                check=True)
            made.append((name, side, t, s[f"difficulty_{side}"]))
    print(f"\nwrote {len(made)} clips to {CLIPS}")
    print(f"each is {seconds:.0f}s with the derived boundary at the midpoint\n")
    for name, side, t, d in made:
        expect = ("speech should START halfway through" if side == "in"
                  else "speech should STOP halfway through")
        print(f"  {name}")
        print(f"      {expect}; {d['label']} cut, {d['quiet_ms']} ms of quiet")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clips", type=int, default=0,
                    help="how many recordings to cut listening clips from")
    ap.add_argument("--clip-seconds", type=float, default=20.0)
    args = ap.parse_args()

    gt = json.loads((DATA / "groundtruth.json").read_text())
    summary(gt)

    problems = checks(gt)
    print()
    if problems:
        print(f"FAILED {len(problems)} consistency checks:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("all consistency checks passed")

    if args.clips:
        clips(gt, args.clips, args.clip_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
