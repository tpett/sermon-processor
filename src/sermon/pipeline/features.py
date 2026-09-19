"""Turn a recording into a compact structured summary.

The point is to stop handing a model 22,000 tokens of raw transcript and ask it
to infer structure, and instead hand it a dozen rows of already-extracted
structure and ask it one question: which row is the sermon.

That is a far smaller reasoning task, which is what makes a small model viable —
and every feature here comes from a tool that is cheaper to run than the model.
"""
from __future__ import annotations

import datetime as dt

from . import cues as C

# Consecutive turns by the same voice are one block however long the pause
# between them. Turns are time-ordered, so "consecutive" already means no other
# speaker intervened — and the spec is explicit that the 15-20s silent prayer
# inside the sermon must not create a boundary (blocking.feature, Q20).
# Measured: a 20s cap split one 56-minute sermon into five blocks.
MIN_BLOCK_S = 45.0
SNAP_WINDOW_S = 20.0


def blocks_from_diarization(doc: dict, dia: dict) -> list[dict]:
    """Blocks bounded by speaker change rather than by silence.

    Diarization over-clusters — a 90 minute service comes back with 20-plus
    labels — and scatters brief spurious turns through a long monologue. A single
    merge pass therefore leaves a 56-minute sermon split into six blocks, which
    destroys the whole point: the model is then asked to pick "the sermon" from
    six fragments of it.

    So smoothing is iterative: absorb anything too short to be a section of a
    service into its larger neighbour, re-merge neighbours that now agree, and
    repeat until stable.
    """
    turns = sorted(dia["turns"], key=lambda t: t["start"])
    if not turns:
        return []

    segs = [{"start": turns[0]["start"], "end": turns[0]["end"],
             "speaker": turns[0]["speaker"]}]
    for t in turns[1:]:
        prev = segs[-1]
        if t["speaker"] == prev["speaker"]:
            prev["end"] = max(prev["end"], t["end"])
        else:
            segs.append({"start": max(t["start"], prev["end"]),
                         "end": max(t["end"], prev["end"]), "speaker": t["speaker"]})

    for _ in range(50):
        changed = False

        # Absorb a too-short block into whichever neighbour is longer, adopting
        # that neighbour's voice so the next merge pass can join them.
        i = 0
        while i < len(segs):
            if len(segs) > 1 and (segs[i]["end"] - segs[i]["start"]) < MIN_BLOCK_S:
                left = segs[i - 1] if i > 0 else None
                right = segs[i + 1] if i + 1 < len(segs) else None
                me = segs[i]["speaker"]
                # Voice before length: a preacher's short opening turns are
                # otherwise absorbed backwards into the scripture reading,
                # moving the block edge 30-40 s past the punch-in.
                if left is not None and left["speaker"] == me:
                    pick = left
                elif right is not None and right["speaker"] == me:
                    pick = right
                elif right is None:
                    pick = left
                elif left is None:
                    pick = right
                else:
                    pick = left if (left["end"] - left["start"]) >= (right["end"] - right["start"]) else right
                pick["start"] = min(pick["start"], segs[i]["start"])
                pick["end"] = max(pick["end"], segs[i]["end"])
                segs.pop(i)
                changed = True
                continue
            i += 1

        # Join neighbours that share a voice.
        i = 1
        while i < len(segs):
            if segs[i]["speaker"] == segs[i - 1]["speaker"]:
                segs[i - 1]["end"] = max(segs[i - 1]["end"], segs[i]["end"])
                segs.pop(i)
                changed = True
                continue
            i += 1

        if not changed:
            break

    # Snap every boundary to a real speech edge.
    #
    # A block edge is meant to be the moment one thing stops and the next
    # starts. The diarizer's own turn times are approximate, and the smoothing
    # above moves them further, so raw edges land a median 8.5 s from the true
    # punch-in — against 0.24 s for the nearest transcript edge. Downstream that
    # showed up as refinement reaching backwards into the previous block to
    # recover a boundary that should have been drawn correctly here.
    starts = sorted({u["start"] for u in doc["utterances"]})
    ends = sorted({u["end"] for u in doc["utterances"]})

    def snap(t: float, cands: list[float], window: float = SNAP_WINDOW_S) -> float:
        best, best_d = t, window
        for c in cands:
            d = abs(c - t)
            if d < best_d:
                best, best_d = c, d
        return best

    bounds = [0.0]
    for m in segs[1:]:
        # A boundary sits between the end of the last utterance of one block and
        # the start of the first of the next, so prefer an utterance start.
        bounds.append(snap(m["start"], starts))
    bounds.append(doc["duration"])

    blocks = []
    for i in range(len(segs)):
        start, end = bounds[i], bounds[i + 1]
        if end <= start:
            continue
        blocks.append({"start": round(start, 3), "end": round(end, 3),
                       "speaker": segs[i]["speaker"],
                       "utterances": [u for u in doc["utterances"]
                                      if start - 0.5 <= u["start"] < end]})
    return blocks


def describe(block: dict, doc: dict, dia: dict | None) -> dict:
    us = block["utterances"]
    dur = max(block["end"] - block["start"], 1e-6)
    words = sum(len(u["text"].split()) for u in us)
    text = " ".join(u["text"] for u in us).strip()

    logprob = sum(u["avg_logprob"] for u in us) / len(us) if us else -10.0
    nospeech = sum(u["no_speech_prob"] for u in us) / len(us) if us else 1.0
    wpm = words / (dur / 60)

    try:
        wall = (dt.datetime.fromisoformat(doc["started_at"])
                + dt.timedelta(seconds=block["start"])).strftime("%-I:%M %p")
    except Exception:
        wall = "?"

    # Whisper confidence and word density are a usable music proxy on their own,
    # which is worth knowing before deploying a dedicated music classifier (Q10).
    likely_music = wpm < 55 or logprob < -0.55 or nospeech > 0.4

    return {
        "start": block["start"], "end": block["end"], "duration": dur,
        "wall": wall, "speaker": block.get("speaker", "?"),
        "words": words, "wpm": wpm,
        "logprob": logprob, "no_speech": nospeech,
        "likely_music": likely_music,
        "scripture": C.count_hits(text, C.SCRIPTURE),
        "prayer": C.count_hits(text, C.PRAYER),
        "communion": C.count_hits(text, C.COMMUNION),
        "qa": C.count_hits(text, C.QA),
        "opens": text[:180].replace("\n", " "),
        "closes": text[-180:].replace("\n", " ") if len(text) > 360 else "",
    }


def render_table(blocks: list[dict], doc: dict, dia: dict | None) -> str:
    """The whole recording as a readable table, a few hundred tokens per block."""
    def hms(t):
        return f"{int(t//3600)}:{int(t%3600//60):02d}:{int(t%60):02d}"

    speaker_totals: dict[str, float] = {}
    rows = [describe(b, doc, dia) for b in blocks]
    for r in rows:
        speaker_totals[r["speaker"]] = speaker_totals.get(r["speaker"], 0) + r["duration"]

    lines = []
    for i, r in enumerate(rows):
        recurs = sum(1 for x in rows if x["speaker"] == r["speaker"])
        tags = []
        if r["likely_music"]:
            tags.append("LIKELY MUSIC OR NON-SPEECH")
        if recurs > 1:
            tags.append(f"this voice appears in {recurs} separate blocks")
        for k, label in (("scripture", "scripture-reading phrases"),
                         ("prayer", "prayer phrases"),
                         ("communion", "communion phrases"),
                         ("qa", "question-and-answer phrases")):
            if r[k]:
                tags.append(f"{r[k]} {label}")
        lines.append(
            f"BLOCK {i}  {hms(r['start'])}–{hms(r['end'])}  "
            f"({r['duration']/60:.1f} min, starts {r['wall']})\n"
            f"  voice: {r['speaker']}   words: {r['words']} ({r['wpm']:.0f}/min)   "
            f"asr confidence: {r['logprob']:.2f}\n"
            + (f"  signals: {'; '.join(tags)}\n" if tags else "")
            + f"  opens: \"{r['opens']}\"\n"
            + (f"  closes: \"{r['closes']}\"\n" if r["closes"] else ""))
    return "\n".join(lines)
