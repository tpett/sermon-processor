#!/usr/bin/env python3
"""Turn the control subagents' answers into a scoreable config.

Applies exactly the same coercion, refinement and segment derivation as every
other rung — the control is measured on identical terms, or it is not a control.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import classify as C   # noqa: E402
from sermon.pipeline import segments as SEG # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
CONFIG = "c-frontier.whole.v2"
ASR = "whisper-large-v3-turbo+words"

out_dir = DATA / "blocks"
out_dir.mkdir(parents=True, exist_ok=True)

n_ok = n_bad = 0
for ans in sorted((WORK / "control").glob("*.answer.json")):
    rid = ans.name.replace(".answer.json", "")
    doc_path = DATA / "transcripts" / f"{rid}.{ASR}.json"
    if not doc_path.exists():
        print(f"  {rid}: no transcript"); n_bad += 1; continue
    doc = json.loads(doc_path.read_text())

    raw = C.parse_json(ans.read_text())
    if raw is None:
        print(f"  {doc['desktop_label'][:36]:<38} unparseable answer"); n_bad += 1; continue

    blks = C.coerce_blocks(raw, doc)
    res = {
        "blocks": blks,
        "segments": SEG.derive(blks, doc),
        "model_segments": raw.get("segments", []),
        "status": "ok" if blks else "no-blocks",
        "repairs": 0,
        "config_id": CONFIG,
        "recording_id": rid,
        "desktop_label": doc["desktop_label"],
        "asr_config": ASR,
        "wall_clock_s": None,
    }
    (out_dir / f"{rid}.{CONFIG}.json").write_text(json.dumps(res, indent=1))
    seg = res["segments"][0] if res["segments"] else None
    where = (f"in={C.hms(seg['punch_in'])} out={C.hms(seg['punch_out'])}" if seg
             else "no segment proposed")
    print(f"  {doc['desktop_label'][:36]:<38} {len(blks):3d} blocks  "
          f"{len(res['segments'])} seg  {where}")
    n_ok += 1

print(f"\ningested {n_ok} control answers ({n_bad} problems) as {CONFIG}")
