"""T0 — the rules rung. No model of any kind.

The floor of the reasoning ladder. If this lands close to the frontier control,
the whole model question dissolves and the answer to Q13/Q76 is "neither".

Deliberately a genuine attempt rather than a strawman: it uses every signal the
spec says matters — ASR confidence as a music proxy, the lexical cues, the
running order, and wall-clock time.
"""

from __future__ import annotations

import datetime as dt

from . import blocks as B
from . import cues as C

# A block is teaching if it is long, dense, and confidently transcribed.
TEACH_MIN_S = 900          # 15 minutes
TEACH_MIN_WPM = 90
MUSIC_MAX_WPM = 55
MUSIC_MAX_LOGPROB = -0.55


def classify_block(b: dict, st: dict) -> tuple[str, float, str]:
    text = B.text_of(b)
    dur, wpm = st["duration"], st["words_per_min"]

    if st["words"] < 15 or wpm < MUSIC_MAX_WPM or st["avg_logprob"] < MUSIC_MAX_LOGPROB:
        return "music", 0.6, f"sparse or low-confidence speech ({wpm:.0f} wpm)"

    qa_hits = C.count_hits(text, C.QA)
    if qa_hits >= 1 and dur > 300:
        return "qa", 0.5, "question-and-answer phrasing"

    if C.any_hit(text, C.COMMUNION) and dur < 900:
        return "communion", 0.6, "communion invitation phrasing"

    if dur >= TEACH_MIN_S and wpm >= TEACH_MIN_WPM:
        return "sermon", 0.6, f"sustained teaching, {dur/60:.0f} min at {wpm:.0f} wpm"

    scripture = C.count_hits(text, C.SCRIPTURE)
    prayer = C.count_hits(text, C.PRAYER)
    if scripture >= 2 and dur < 600:
        return "scripture_reading", 0.5, "scripture reading phrasing"
    if prayer >= 2 and dur < 600:
        return "prayer", 0.5, "prayer phrasing"
    if C.any_hit(text, C.ANNOUNCEMENTS) and dur < 900:
        return "announcements", 0.5, "welcome and notices phrasing"
    return "other", 0.3, f"{dur/60:.0f} min, {wpm:.0f} wpm, no clear cue"


def refine_punch_in(utts: list[dict]) -> float | None:
    """Prefer the first utterance after the last scripture cue near the start."""
    if not utts:
        return None
    head = [u for u in utts if u["start"] - utts[0]["start"] < 420]
    last_scripture = None
    for i, u in enumerate(head):
        if C.count_hits(u["text"], C.SCRIPTURE) >= 1:
            last_scripture = i
    if last_scripture is not None and last_scripture + 1 < len(head):
        return head[last_scripture + 1]["start"]
    return utts[0]["start"]


def refine_punch_out(utts: list[dict]) -> float | None:
    """Stop before the communion invitation, or after the closing amen."""
    if not utts:
        return None
    tail_from = utts[-1]["end"] - 900
    tail = [u for u in utts if u["end"] >= tail_from]
    for u in tail:
        if C.any_hit(u["text"], C.COMMUNION):
            return u["start"]
    for u in reversed(tail):
        if "amen" in u["text"].lower():
            return u["end"]
    return utts[-1]["end"]


def run(doc: dict) -> dict:
    cands = B.candidates(doc)
    out_blocks = []
    for b in cands:
        st = B.stats(b)
        t, conf, ev = classify_block(b, st)
        out_blocks.append({
            "start": b["start"], "end": b["end"], "type": t,
            "confidence": conf, "evidence": ev, "_utterances": b["utterances"],
        })

    # A recording has at most one sermon. Keep the longest teaching block and
    # demote the rest, which is what stops a long announcements block winning.
    teaching = [i for i, b in enumerate(out_blocks) if b["type"] in ("sermon", "lesson")]
    if len(teaching) > 1:
        best = max(teaching, key=lambda i: out_blocks[i]["end"] - out_blocks[i]["start"])
        for i in teaching:
            if i != best:
                out_blocks[i]["type"] = "other"
                out_blocks[i]["evidence"] += "; shorter than the main teaching block"

    # Q&A after a teaching block makes it a lesson rather than a sermon.
    for i, b in enumerate(out_blocks):
        if b["type"] == "sermon":
            nxt = out_blocks[i + 1: i + 3]
            if any(n["type"] == "qa" for n in nxt):
                b["type"] = "lesson"
                b["evidence"] += "; followed by questions"

    segments = []
    for i, b in enumerate(out_blocks):
        if b["type"] not in ("sermon", "lesson"):
            continue
        utts = b["_utterances"]
        pin = refine_punch_in(utts) or b["start"]
        pout = refine_punch_out(utts) or b["end"]
        # Extend through an immediately following prayer block, per the rule.
        if i + 1 < len(out_blocks) and out_blocks[i + 1]["type"] == "prayer":
            nxt = out_blocks[i + 1]["_utterances"]
            if nxt:
                pout = refine_punch_out(nxt) or out_blocks[i + 1]["end"]
        if pout > pin:
            segments.append({
                "punch_in": round(pin, 3), "punch_out": round(pout, 3),
                "classification": b["type"], "confidence": b["confidence"],
            })

    for b in out_blocks:
        b.pop("_utterances", None)
    return {"blocks": out_blocks, "segments": segments}
