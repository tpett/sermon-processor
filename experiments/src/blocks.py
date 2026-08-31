"""Pre-split a transcript into candidate blocks.

Used by the rules rung and by the per-block prompting strategy. Splits on gaps
in speech, because speaker labels are not available in the Stage 1 arm — this is
the "blocking degrades without speaker information" path in
../features/analysis/blocking.feature.
"""

from __future__ import annotations

GAP_S = 12.0        # a gap this long ends a candidate block
MIN_BLOCK_S = 60.0  # anything shorter is merged into its neighbour


def speech_runs(utterances: list[dict], gap_s: float = GAP_S) -> list[dict]:
    """Group utterances into runs separated by gaps of at least `gap_s`."""
    runs: list[dict] = []
    for u in utterances:
        if runs and u["start"] - runs[-1]["end"] <= gap_s:
            runs[-1]["end"] = u["end"]
            runs[-1]["utterances"].append(u)
        else:
            runs.append({"start": u["start"], "end": u["end"], "utterances": [u]})
    return runs


def merge_short(runs: list[dict], min_s: float = MIN_BLOCK_S) -> list[dict]:
    """Fold sub-minimum runs into whichever neighbour they are closer to."""
    if not runs:
        return runs
    out = [dict(runs[0])]
    for r in runs[1:]:
        prev = out[-1]
        if (r["end"] - r["start"]) < min_s or (prev["end"] - prev["start"]) < min_s:
            prev["end"] = r["end"]
            prev["utterances"] = prev["utterances"] + r["utterances"]
        else:
            out.append(dict(r))
    return out


def candidates(doc: dict, gap_s: float = GAP_S, min_s: float = MIN_BLOCK_S) -> list[dict]:
    """Candidate blocks covering the whole recording, contiguous and gapless."""
    runs = merge_short(speech_runs(doc["utterances"], gap_s), min_s)
    if not runs:
        return [{"start": 0.0, "end": doc["duration"], "utterances": []}]

    # Push each boundary into the middle of the gap it sits in, so a block edge
    # lands in silence rather than clipping the start of the next utterance.
    blocks = []
    for i, r in enumerate(runs):
        start = 0.0 if i == 0 else (runs[i - 1]["end"] + r["start"]) / 2
        end = doc["duration"] if i == len(runs) - 1 else (r["end"] + runs[i + 1]["start"]) / 2
        blocks.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "speech_start": r["start"],
            "speech_end": r["end"],
            "utterances": r["utterances"],
        })
    return blocks


def text_of(block: dict, max_chars: int | None = None) -> str:
    t = " ".join(u["text"] for u in block["utterances"]).strip()
    if max_chars and len(t) > max_chars:
        half = max_chars // 2
        t = t[:half] + "\n[...]\n" + t[-half:]
    return t


def stats(block: dict) -> dict:
    """Signals that separate speech from music without a dedicated classifier."""
    us = block["utterances"]
    dur = max(block["end"] - block["start"], 1e-6)
    words = sum(len(u["text"].split()) for u in us)
    if not us:
        return {"duration": dur, "words": 0, "words_per_min": 0.0,
                "avg_logprob": -10.0, "no_speech_prob": 1.0, "speech_frac": 0.0}
    return {
        "duration": dur,
        "words": words,
        "words_per_min": words / (dur / 60),
        "avg_logprob": sum(u["avg_logprob"] for u in us) / len(us),
        "no_speech_prob": sum(u["no_speech_prob"] for u in us) / len(us),
        "speech_frac": sum(u["end"] - u["start"] for u in us) / dur,
    }
