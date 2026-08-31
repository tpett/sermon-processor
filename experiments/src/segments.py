"""Derive publishable segments from classified blocks.

Applied identically to every rung. The extension rule is *given* to candidates
rather than discovered by them (see classification-spec.md), so deriving
segments here rather than trusting each model to apply the rule isolates what we
are actually testing: whether a technology can identify the anatomy of a service.
"""

from __future__ import annotations

import cues as C


def speaker_edges(doc: dict) -> list[float]:
    """Speaker-change times for this recording, if diarization has been run.

    Measured on dev: the nearest speaker-change boundary sits far closer to the
    human punch-in than the nearest transcript edge does. Punch-in is the binding
    constraint on the whole system (see FINDINGS), so this is the single highest
    value signal available.
    """
    import json as _json
    from pathlib import Path as _Path
    p = (_Path(__file__).resolve().parent.parent / "data" / "diarization"
         / f"{doc['recording_id']}.json")
    if not p.exists():
        return []
    d = _json.loads(p.read_text())
    return sorted({round(x["start"], 3) for x in d["turns"]} |
                  {round(x["end"], 3) for x in d["turns"]})


def snap_to(t: float, edges: list[float], window: float) -> float | None:
    best, best_d = None, window
    for e in edges:
        d = abs(e - t)
        if d < best_d:
            best, best_d = e, d
    return best


_EDGE_CACHE: dict[str, list[float]] = {}


def candidate_edges(doc: dict) -> list[float]:
    """Every place a boundary could legitimately land.

    Measured on dev (`feature_probe.py`), median distance from the human
    punch-in to the nearest edge:

        transcript edges only   0.24 s   100% within 2 s
        speaker edges only      0.41 s    62% within 2 s
        the union of both       0.11 s   100% within 2 s

    So diarization does not beat the transcript for *precision* — the boundary
    was already there — but the union is better than either alone, which is
    cheap to take.
    """
    rid = doc["recording_id"]
    if rid in _EDGE_CACHE:
        return _EDGE_CACHE[rid]
    edges = {u["start"] for u in doc["utterances"]} | {u["end"] for u in doc["utterances"]}
    edges |= set(speaker_edges(doc))
    _EDGE_CACHE[rid] = sorted(edges)
    return _EDGE_CACHE[rid]


def snap(t: float, doc: dict, window: float = 30.0) -> float:
    """Move a proposed time to the nearest real speech edge.

    Applied uniformly to every rung. Without it we would be measuring a model's
    willingness to copy timestamps accurately rather than its understanding of
    the recording, and the oracle already bounds what snapping can achieve.
    """
    best, best_d = t, window
    for e in candidate_edges(doc):
        d = abs(e - t)
        if d < best_d:
            best, best_d = e, d
    return round(best, 3)


def _within(doc: dict, a: float, b: float) -> list[dict]:
    return [u for u in doc["utterances"] if u["start"] >= a - 0.01 and u["end"] <= b + 0.01]


SPEAKER_SNAP_S = 4.0
AMEN_LOOKBACK_S = 150.0
AMEN_FALLBACK_MAX_S = 120.0
LESSON_LEAD_IN = {"announcements", "prayer", "other"}
PREAMBLE_GAP_S = 20.0
PREAMBLE_MAX_WORDS = 8
LOOKBACK_S = 0.0  # measured: any lookback lets the punch-in drift before the opening
CUE_WINDOW_S = 240.0
LOOKAHEAD_S = 420.0


def refine_in(utts: list[dict], block_start: float | None = None,
              block_type: str = "sermon",
              speaker_changes: list[float] | None = None) -> float | None:
    """Where the teaching actually starts. The anchor depends on the type.

    - **sermon** — after the scripture reading, at the change of speaker. The
      cue only counts near the start of the block: preachers quote scripture
      constantly, and searching the whole span jumps the punch-in minutes past
      the real opening (measured: median error 2.14 s to 65.06 s when unbounded).
    - **lesson / seminar / other** — the beginning of the segment. There is no
      scripture reading to anchor on, which is exactly why every rung including
      the frontier control lands ~2 minutes late on the class: they skip the
      introduction and the opening prayer looking for a sermon-shaped opening
      that is not there.

    A class may open with a line of throat-clearing before the real start — a
    bare greeting, or "we'll get going in a minute" followed by a pause. That is
    skipped when it is clearly separable, and left alone when it is not.
    """
    if not utts:
        return None

    if block_type in ("lesson", "seminar", "other", "announcements", "meeting"):
        return _start_of_teaching(utts)

    anchor = block_start if block_start is not None else utts[0]["start"]
    near = [u for u in utts if u["start"] <= anchor + CUE_WINDOW_S]
    last_scripture = None
    for i, u in enumerate(near):
        if C.count_hits(u["text"], C.SCRIPTURE) >= 1:
            last_scripture = i

    if last_scripture is not None and last_scripture + 1 < len(near):
        reading_ends = near[last_scripture]["end"]
        # The sermon begins after the reading *and* at a change of voice. The
        # reading is often followed by a prayer or a handover before the preacher
        # starts, so the next utterance is not the punch-in — the next speaker
        # change is. Falls back to the next utterance when no diarization exists.
        if speaker_changes is not None:
            for e in speaker_changes:
                if e >= reading_ends - 1.0:
                    at_or_after = [u for u in utts if u["start"] >= e - 1.5]
                    if at_or_after:
                        return at_or_after[0]["start"]
                    break
        return near[last_scripture + 1]["start"]

    after = [u for u in utts if u["start"] >= anchor - 1.0]
    return (after or utts)[0]["start"]


def _start_of_teaching(utts: list[dict]) -> float:
    """First speech in the block.

    An earlier version also skipped a leading bare greeting, which landed the one
    dev class at +0.05 s instead of −5.37 s. Removed: cutting just before the
    greeting is a safe cut, the reviewer can drag it if they care, and the clause
    was tuned on a single recording. Not worth the overfitting risk for five
    seconds nobody minds.
    """
    return utts[0]["start"]


def refine_out(utts: list[dict], block_type: str = "sermon") -> float | None:
    """Cut at the end of the closing prayer, before whatever follows it.

    **The anchor differs by content type**, which is what the spec asks for
    (block_classification.feature: "classification decides which boundary rules
    run") and what the corpus demands:

    - A **sermon** is followed by the communion invitation. Anchor forward on
      that invitation, then step back to the end of the prayer.
    - A **lesson** is followed by Q&A. Anchor on the questions instead.

    Anchoring forward and stepping back — rather than searching backwards for
    the last "amen" — fixes two measured failures that have nothing in common
    except the anchor:

    - 2026-06-14: the closing amen is at 7214.2 s, but communion *also* contains
      "Amen" at 7403.8 s. Last-amen-wins picked the later one: +189 s.
    - 2026-05-31: the closing prayer ends "...in Christ's name" with **no amen at
      all**. Last-amen-wins skipped 245 s into communion: +244 s.
    """
    if not utts:
        return None
    tail = [u for u in utts if u["end"] >= utts[-1]["end"] - 1200]
    if not tail:
        return None

    anchors = {"sermon": C.COMMUNION_INVITATION,
               "lesson": C.QA,
               "seminar": C.QA}.get(block_type)

    if anchors:
        for i, u in enumerate(tail):
            if C.any_hit(u["text"], anchors):
                # Step back to the closing amen if there is one close behind,
                # otherwise to the last thing said before the anchor.
                for j in range(i - 1, -1, -1):
                    if tail[i]["start"] - tail[j]["end"] > AMEN_LOOKBACK_S:
                        break
                    if "amen" in tail[j]["text"].lower():
                        return tail[j]["end"]
                return tail[i - 1]["end"] if i > 0 else tail[i]["start"]

    # No anchor found. Fall back to the last amen — but only if it is plausibly
    # the *closing* one. An unbounded fallback reached back 702 s to a mid-sermon
    # amen on a block whose own end was 0.9 s from the truth, and did the same
    # thing three times in the scored data. When the amen is implausibly early,
    # the end of the block is the better answer.
    end = utts[-1]["end"]
    last_amen = None
    for u in tail:
        if "amen" in u["text"].lower():
            last_amen = u["end"]
    if last_amen is not None and (end - last_amen) <= AMEN_FALLBACK_MAX_S:
        return last_amen
    return end


def derive(blocks: list[dict], doc: dict, refine: bool = True) -> list[dict]:
    segs = []
    for i, b in enumerate(blocks):
        if b.get("type") not in ("sermon", "lesson"):
            continue
        pin, pout = float(b["start"]), float(b["end"])

        # A lesson starts at the top of the session, not at the teaching.
        #
        # The frontier control classifies a class correctly — announcements,
        # opening prayer, then the lesson — and starts the segment at the
        # teaching, 124 s in. That is a defensible reading and it is not the
        # convention: a class is published from the beginning, introduction and
        # opening prayer included. So extend backwards through whatever leads
        # into it. No equivalent for a sermon, where the run-up is a different
        # part of the service and is always cut.
        if b.get("type") == "lesson":
            j = i - 1
            while j >= 0 and blocks[j].get("type") in LESSON_LEAD_IN:
                pin = float(blocks[j]["start"])
                j -= 1

        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if nxt and nxt.get("type") == "prayer":
            pout = float(nxt["end"])
        if refine:
            edges = speaker_edges(doc)
            # Refinement looks a little outside the block. A model that starts
            # its sermon block a few seconds late would otherwise cap the
            # achievable punch-in at its own error, and the whole point of a
            # separate refinement stage is that classification only has to be
            # approximately right.
            head = _within(doc, pin - LOOKBACK_S, pin + LOOKAHEAD_S)
            # speaker_changes deliberately not passed: measured on dev, gating the
            # sermon punch-in on the next speaker change after the scripture
            # reading made things worse in every variant tried — raw turn edges
            # are too dense to mean anything (one regression, no gains), and
            # smoothed block edges combined with a lookback for the reading
            # produced two catastrophic jumps of ~2800 s. See FINDINGS.
            pin = refine_in(head, pin, b.get("type", "sermon")) or pin
            tail_src = _within(doc, float(nxt["start"]), float(nxt["end"]) + LOOKBACK_S) if (
                nxt and nxt.get("type") == "prayer") else _within(doc, pin, pout + LOOKBACK_S)
            pout = refine_out(tail_src, b.get("type", "sermon")) or pout
        pin, pout = snap(pin, doc), snap(pout, doc)
        if segs and pin < segs[-1]["punch_out"]:
            # The lesson lead-in walk-back can reach into a span already claimed.
            pin = segs[-1]["punch_out"]
        if pout > pin:
            segs.append({
                "punch_in": pin, "punch_out": pout,
                "classification": b["type"],
                "confidence": float(b.get("confidence", 0.5)),
            })
    return segs


# Sanity band from ../features/analysis/segment_proposal.feature: published
# segments in the corpus run 40-68 minutes, and the spec warns outside 30-75.
# Used only to decide whether a model's own answer is plausible enough to keep.
PLAUSIBLE_MIN_S = 30 * 60
PLAUSIBLE_MAX_S = 75 * 60


def choose(model_segments, derived, doc):
    """Prefer the model's own boundaries; fall back to refinement when it is wild.

    Measured on dev: refinement made the frontier control's punch-in 2.1x worse
    and its punch-out 1.6x worse. On one recording the model was 0.08 s from the
    human cut and refinement moved it five seconds away. Every model punch-out
    errs *late* (a short tail, the safe direction); every refined one errs early,
    clipping the last word.

    Refinement still earns its place where the model is badly wrong — notably a
    class, where it turned +118.89 s into -5.37 s. So the model leads and the
    rules catch it, rather than the rules overwriting it.

    Plausibility is judged against the spec's own length band, not against
    anything fitted to the corpus.
    """
    out = []
    for i, d in enumerate(derived):
        pick, source = d, "refined"
        cand = model_segments[i] if i < len(model_segments) else None
        if cand:
            try:
                pin, pout = float(cand["punch_in"]), float(cand["punch_out"])
            except (KeyError, TypeError, ValueError):
                pin = pout = None
            if pin is not None and 0 <= pin < pout <= doc["duration"] + 1:
                if PLAUSIBLE_MIN_S <= (pout - pin) <= PLAUSIBLE_MAX_S:
                    pick = {"punch_in": round(pin, 3), "punch_out": round(pout, 3),
                            "classification": d.get("classification"),
                            "confidence": d.get("confidence", 0.5)}
                    source = "model"
        out.append(dict(pick, boundary_source=source))
    return out
