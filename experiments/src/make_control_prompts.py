#!/usr/bin/env python3
"""Write one self-contained prompt file per recording for the frontier control.

The control runs as a subagent per recording. Writing the prompt to disk keeps
the transcript out of the orchestrating context and makes the exact input each
subagent saw reproducible.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import classify as C  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK, PROMPTS = HERE / "data", HERE / "work", HERE / "prompts"

ap = argparse.ArgumentParser()
ap.add_argument("--split", default="dev")
ap.add_argument("--asr", default="whisper-large-v3-turbo+words")
args = ap.parse_args()

out = WORK / "control"
out.mkdir(parents=True, exist_ok=True)
tpl = (PROMPTS / "whole_transcript.v2.md").read_text()

made = []
for path in sorted((DATA / "transcripts").glob(f"*.{args.asr}.json")):
    doc = json.loads(path.read_text())
    if doc["split"] != args.split:
        continue
    body = (tpl.replace("{started_at}", doc["started_at"])
               .replace("{duration_hms}", C.hms(doc["duration"]))
               .replace("{duration}", f"{doc['duration']:.1f}")
               .replace("{transcript}", C.render_transcript(doc)))
    p = out / f"{doc['recording_id']}.prompt.md"
    p.write_text(body)
    made.append((doc["recording_id"], doc["desktop_label"], len(body)))

for rid, label, n in made:
    print(f"{rid}  {label[:34]:<36} {n/1000:6.1f}k chars")
print(f"\n{len(made)} prompts in {out}")
