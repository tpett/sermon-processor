#!/usr/bin/env python3
"""Run one rung of the reasoning ladder over the frozen transcripts."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sermon.pipeline import classify as _library
from sermon.pipeline import rules as RULES
from sermon.pipeline import segments as _segments
from sermon.pipeline.classify import hms, run_perblock, run_structured, run_whole

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
PROMPTS = HERE / "prompts"

# The library halves resolve no path of their own; this driver owns the layout.
_library.DATA, _library.PROMPTS = DATA, PROMPTS
_segments.DATA_ROOT = DATA


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", required=True, choices=["rules", "ollama"])
    ap.add_argument("--model", default="")
    ap.add_argument("--strategy", default="whole",
                    choices=["whole", "perblock", "structured"])
    ap.add_argument("--rung", required=True, help="ladder rung, e.g. t0 or t3")
    ap.add_argument("--asr", default="whisper-large-v3-turbo+words")
    ap.add_argument("--only")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "fresh", "blind", "all"])
    ap.add_argument("--think", action="store_true",
                    help="let the model reason before answering; recorded in config_id")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    slug = (args.model.split(":")[0].replace("/", "-") or "rules")
    config_id = f"{args.rung}-{slug}.{args.strategy}{'.think' if args.think else ''}.v2"
    out_dir = DATA / "blocks"
    out_dir.mkdir(parents=True, exist_ok=True)

    docs = sorted((DATA / "transcripts").glob(f"*.{args.asr}.json"))
    if not docs:
        print(f"no transcripts for asr config {args.asr}")
        return 1

    print(f"config: {config_id}   transcripts: {len(docs)}")
    for path in docs:
        doc = json.loads(path.read_text())
        if args.only and args.only not in doc["desktop_label"]:
            continue
        if args.split != "all" and doc["split"] not in (args.split, "two-level"):
            continue
        dst = out_dir / f"{doc['recording_id']}.{config_id}.json"
        if dst.exists() and not args.force:
            print(f"  {doc['desktop_label'][:36]:<38} cached")
            continue

        t0 = time.time()
        if args.backend == "rules":
            res = RULES.run(doc)
            res["status"] = "ok"
            res["repairs"] = 0
        elif args.strategy == "whole":
            res = run_whole(args.model, doc, args.think)
        elif args.strategy == "structured":
            res = run_structured(args.model, doc, args.think)
        else:
            res = run_perblock(args.model, doc, args.think)
        res |= {"config_id": config_id, "recording_id": doc["recording_id"],
                "desktop_label": doc["desktop_label"], "asr_config": args.asr,
                "wall_clock_s": round(time.time() - t0, 1)}
        dst.write_text(json.dumps(res, indent=1))
        seg = res["segments"][0] if res["segments"] else None
        where = (f"in={hms(seg['punch_in'])} out={hms(seg['punch_out'])}" if seg
                 else "no segment proposed")
        print(f"  {doc['desktop_label'][:36]:<38} {len(res['blocks']):3d} blocks  "
              f"{len(res['segments'])} seg  {where:<28} {res['wall_clock_s']:6.1f}s"
              + ("" if res["status"] == "ok" else f"  [{res['status']}]"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
