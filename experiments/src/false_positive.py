#!/usr/bin/env python3
"""Does the pipeline invent a sermon where there is none?

The survey asked an open question — "what is this recording?" — which is easier
than the question production asks. This gives the unpublished recordings the
*real* prompt, the one that assumes a sermon might be there and explains how to
find it, and counts how often a segment comes back.
"""
from __future__ import annotations

import datetime as dt, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import classify as C  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
WORK, PROMPTS = HERE / "work", HERE / "prompts"
MODEL = "qwen3.6:35b-mlx"

survey = {r["key"]: r for r in json.loads((WORK / "unpublished_survey.json").read_text())}
tpl = (PROMPTS / "whole_transcript.v2.md").read_text()

print(f"{'recording':<22}{'what the survey called it':<44}{'segments':>9}  verdict")
inv = tot = 0
for key, s in sorted(survey.items(), key=lambda x: x[1]["when"]):
    cache = WORK / "unpub" / f"{key}.json"
    if not cache.exists():
        print(f"{key[10:]:<22}{s['what'][:42]:<44}{'—':>9}  empty room, never transcribed")
        continue
    doc = json.loads(cache.read_text())
    when = dt.datetime.fromisoformat(s["when"])
    lines, prev = [], 0.0
    for u in doc["utterances"]:
        if u["start"] - prev >= 10:
            lines.append(f"--- silence {u['start']-prev:.0f}s ---")
        lines.append(f"[{u['start']:.1f}] {u['text']}")
        prev = u["start"]
    prompt = (tpl.replace("{started_at}", when.isoformat())
                 .replace("{duration_hms}", C.hms(s["minutes"] * 60))
                 .replace("{duration}", f"{s['minutes']*60:.1f}")
                 .replace("{transcript}", "\n".join(lines)[:60000]))
    raw, _ = C.call_json(MODEL, prompt)
    segs = (raw or {}).get("segments") or []
    tot += 1
    bad = len(segs) > 0 and not s["publishable"]
    inv += 1 if bad else 0
    verdict = ("INVENTED A SEGMENT" if bad else
               "proposed (survey agrees it is publishable)" if segs else "correctly declined")
    print(f"{key[10:]:<22}{s['what'][:42]:<44}{len(segs):>9}  {verdict}")

print(f"\nof {tot} recordings with real audio that were never published, "
      f"{inv} produced a segment the survey judged unpublishable")
