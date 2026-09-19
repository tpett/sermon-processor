#!/usr/bin/env python3
"""Re-derive segments from stored blocks, without re-running any model.

Boundary refinement is a shared downstream stage. Changing it must not cost a
full ladder re-run, so classification output (blocks) and segment derivation are
decoupled here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import segments as SEG  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

SEG.DATA_ROOT = DATA

n = 0
for path in sorted((DATA / "blocks").glob("*.json")):
    res = json.loads(path.read_text())
    doc_path = DATA / "transcripts" / f"{res['recording_id']}.{res['asr_config']}.json"
    if not doc_path.exists():
        continue
    doc = json.loads(doc_path.read_text())
    derived = SEG.derive(res["blocks"], doc)
    res["derived_segments"] = derived
    res["segments"] = SEG.choose(res.get("model_segments") or [], derived, doc)
    path.write_text(json.dumps(res, indent=1))
    n += 1
print(f"re-derived segments for {n} results")
