#!/usr/bin/env python3
"""Spike 6 — calibrate the "no substantive content" test.

Q36: "a single noise, like a pop from somebody turning the system on or off,
might trigger a recording that's 10 minutes long... the substance will just be a
single noise and almost entirely silence. If we can easily classify those and
mark them as ignored, that would be good."

The corpus contains no examples — everything in ~/Desktop/Sermons is material
that was kept — so the threshold in the spec was invented. These are real
unpublished recordings pulled from the bucket.

The measure is the proportion of the recording above its own noise floor, not an
absolute level: the whole point is to separate "a room with something happening
in it" from "a room with one bang in it".
"""
from __future__ import annotations

import json, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import audio as A  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
WORK, DATA = HERE / "work", HERE / "data"
HZ = 100


def profile(path: Path, tag: str) -> dict:
    env = A.cached_envelope(path, WORK, HZ, tag)
    db = 20 * np.log10(np.maximum(env, 1e-6))
    floor = float(np.percentile(db, 5))
    loud = float(np.percentile(db, 95))
    # "Active" = meaningfully above this recording's own floor.
    thr = floor + 12.0
    active = float(np.mean(db > thr))
    # Longest continuous active run, in seconds — one bang is short, a service is not.
    m = db > thr
    best = cur = 0
    for v in m:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return {"minutes": len(env) / HZ / 60, "floor": floor, "loud": loud,
            "dynamic": loud - floor, "active": active, "longest_active_s": best / HZ}


def main() -> int:
    rows = []
    for p in sorted((WORK / "bucket").glob("*.flac")):
        rows.append(("unpublished", p.stem, profile(p, "bkt_" + p.stem)))
    gt = json.loads((DATA / "groundtruth.json").read_text())
    for r in sorted(gt["recordings"], key=lambda x: x["desktop_label"])[:5]:
        if not r.get("segments"):
            continue
        rows.append(("published", r["desktop_label"],
                     profile(Path(r["source_path"]), r["desktop_label"])))

    print(f"{'kind':<12}{'recording':<34}{'min':>7}{'active%':>9}"
          f"{'longest active':>16}{'dynamic':>9}")
    for kind, name, s in rows:
        print(f"{kind:<12}{name[:33]:<34}{s['minutes']:7.1f}{100*s['active']:8.1f}%"
              f"{s['longest_active_s']:14.1f}s{s['dynamic']:8.1f}dB")

    pub = [s for k, _, s in rows if k == "published"]
    unp = [s for k, _, s in rows if k == "unpublished"]
    print(f"\npublished  : active {min(s['active'] for s in pub)*100:.1f}-"
          f"{max(s['active'] for s in pub)*100:.1f}%, "
          f"longest active {min(s['longest_active_s'] for s in pub):.0f}-"
          f"{max(s['longest_active_s'] for s in pub):.0f}s")
    print(f"unpublished: active {min(s['active'] for s in unp)*100:.1f}-"
          f"{max(s['active'] for s in unp)*100:.1f}%, "
          f"longest active {min(s['longest_active_s'] for s in unp):.0f}-"
          f"{max(s['longest_active_s'] for s in unp):.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
