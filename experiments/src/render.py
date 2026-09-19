#!/usr/bin/env python3
"""Spike 1 — the render chain. Turn an approved span into a publishable MP3.

Encodes the decisions taken in QUESTIONS.md:
  Q66  take channel 1 and discard channel 2; never average (the source is a mono
       signal fed into a stereo recorder, so a downmix costs 6 dB)
  Q49  one loudness operation, not normalize-then-compress
  Q48  -16 LUFS integrated, -1.5 dBTP ceiling
  Q50  mono MP3, 44.1 kHz, around 100 kbps
  Q47  short fades so the cut does not click

Two-pass loudnorm: measure the trimmed span, then correct it. Single-pass
loudnorm is a dynamic filter and will not hit a target reliably on programme
material this long.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sermon.pipeline.render import probe_format, probe_loudness, render

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--no-loudness", action="store_true")
    args = ap.parse_args()

    out_dir = WORK / "render"
    gt = json.loads((DATA / "groundtruth.json").read_text())
    recs = [r for r in gt["recordings"] if r.get("segments") and r.get("mp3_path")]
    recs = sorted(recs, key=lambda r: r["desktop_label"])[:args.limit]

    print(f"{'recording':<32}{'ours: LUFS':>11}{'peak':>7}{'LRA':>6}{'kbps':>6}{'MB':>6}"
          f"{'   |':>4}{'theirs: LUFS':>13}{'peak':>7}{'LRA':>6}{'kbps':>6}{'MB':>6}")
    ours_i, theirs_i = [], []
    for r in recs:
        s = r["segments"][0]
        dst = out_dir / f"{r['desktop_label']}.ours.mp3"
        render(Path(r["source_path"]), s["punch_in"], s["punch_out"], dst,
               loudness=not args.no_loudness)
        a, af = probe_loudness(dst), probe_format(dst)
        b, bf = probe_loudness(Path(r["mp3_path"])), probe_format(Path(r["mp3_path"]))
        ours_i.append(a.get("I")); theirs_i.append(b.get("I"))
        print(f"{r['desktop_label'][:31]:<32}{a.get('I',0):11.1f}{a.get('Peak',0):7.1f}"
              f"{a.get('LRA',0):6.1f}{af['kbps']:6d}{af['mb']:6.1f}{'   |':>4}"
              f"{b.get('I',0):13.1f}{b.get('Peak',0):7.1f}{b.get('LRA',0):6.1f}"
              f"{bf['kbps']:6d}{bf['mb']:6.1f}")

    def spread(xs):
        xs = [x for x in xs if x is not None]
        return max(xs) - min(xs) if xs else float("nan")
    print(f"\nweek-to-week loudness spread — ours {spread(ours_i):.1f} LU, "
          f"theirs {spread(theirs_i):.1f} LU")
    print(f"rendered to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
