#!/usr/bin/env python3
"""Spike 4 — segment summaries and a Preview excerpt.

Q10/Q70: a summary or guess of what each segment is, plus "a piece of that
segment that's most likely going to be highly identifiable for the human" that a
Preview button plays.

The cue excerpt is located by asking for a verbatim quote and then finding it in
the word-level transcript, so the model never has to produce a timestamp — a
thing small models are bad at, and which is unnecessary when the words already
carry times.
"""
from __future__ import annotations

import argparse, difflib, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import classify as C   # noqa: E402
from sermon.pipeline import features as F   # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK, PROMPTS = HERE / "data", HERE / "work", HERE / "prompts"
C.DATA, C.PROMPTS = DATA, PROMPTS
ASR = "whisper-large-v3-turbo+words"


def norm(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def locate(quote: str, words: list[dict]) -> tuple[float, float] | None:
    """Find a verbatim quote in the word stream. Fuzzy, because ASR text and the
    model's copy of it differ in punctuation and the odd token."""
    q = norm(quote)
    if len(q) < 3:
        return None
    hay = [w["w"].lower().strip(".,!?;:\"'") for w in words]
    best, best_score = None, 0.0
    for i in range(0, max(1, len(hay) - len(q) + 1)):
        window = hay[i:i + len(q)]
        score = difflib.SequenceMatcher(None, q, window).ratio()
        if score > best_score:
            best, best_score = i, score
    if best is None or best_score < 0.55:
        return None
    j = min(len(words) - 1, best + len(q) - 1)
    return words[best]["start"], words[j]["end"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--label", default="2026-08-23 - Hebrews 12.4-11")
    ap.add_argument("--blocks", default="c-frontier.whole.v2",
                    help="which config's blocks to summarise")
    args = ap.parse_args()

    gt = json.loads((DATA / "groundtruth.json").read_text())
    rec = next(r for r in gt["recordings"] if r["desktop_label"] == args.label)
    doc = json.loads((DATA / "transcripts" / f"{rec['recording_id']}.{ASR}.json").read_text())
    bp = DATA / "blocks" / f"{rec['recording_id']}.{args.blocks}.json"
    blocks = json.loads(bp.read_text())["blocks"]

    words = []
    for u in doc["utterances"]:
        words.extend(u.get("words", []))
    tpl = (PROMPTS / "summarize.v1.md").read_text()

    print(f"{args.label} — {args.model}\n")
    rows, total = [], 0.0
    for b in blocks:
        us = [u for u in doc["utterances"] if b["start"] <= u["start"] < b["end"]]
        text = " ".join(u["text"] for u in us).strip()
        if len(text.split()) < 40:
            continue
        prompt = (tpl.replace("{block_start}", C.hms(b["start"]))
                     .replace("{block_end}", C.hms(b["end"]))
                     .replace("{block_minutes}", f"{(b['end']-b['start'])/60:.0f}")
                     .replace("{block_text}", text[:14000]))
        t0 = time.time()
        raw, _ = C.call_json(args.model, prompt)
        el = time.time() - t0
        total += el
        if not raw:
            print(f"  {b['type']:<18} FAILED ({el:.0f}s)"); continue
        summary = str(raw.get("summary", ""))[:110]
        quote = str(raw.get("cue_quote", ""))
        bw = [w for w in words if b["start"] <= w["start"] < b["end"]]
        span = locate(quote, bw)
        loc = "not found"
        if span:
            loc = f"{C.hms(span[0])} +{span[1]-span[0]:.1f}s"
            inside = b["start"] <= span[0] <= b["end"]
            if not inside:
                loc += " OUTSIDE BLOCK"
        rows.append({"type": b["type"], "start": b["start"], "end": b["end"],
                     "summary": summary, "quote": quote,
                     "cue": list(span) if span else None, "seconds": round(el, 1)})
        print(f"  {b['type']:<18}{el:5.1f}s  {summary}")
        print(f"  {'':<18}       cue: {loc}  \"{quote[:72]}\"")

    out = WORK / f"summaries.{args.model.replace(':','-')}.json"
    out.write_text(json.dumps({"label": args.label, "model": args.model,
                               "blocks": rows}, indent=1))
    found = sum(1 for r in rows if r["cue"])
    print(f"\n{len(rows)} blocks, {total:.0f}s total ({total/max(len(rows),1):.1f}s each)")
    print(f"cue quote located in the transcript: {found}/{len(rows)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
