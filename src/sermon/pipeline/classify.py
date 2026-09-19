from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

from sermon.config import ReachesModelEndpoint, UnusableConfiguration

from . import blocks as B
from . import features as F
from . import segments as SEG
from .roots import requires_directory_under_root, requires_root

# Injected, never derived from this module's own location, for the same reason
# as segments.DATA_ROOT: reading either of these from __file__ made the module's
# place on disk part of its behaviour. Both are required by the functions that
# read a prompt template or a diarization artefact.
DATA = None
PROMPTS = None

ENDPOINT = None

MAX_REPAIRS = 2
TIMEOUT_S = 900
RECORDING_BUDGET_S = 900  # AGENT-BRIEF: 15 min per recording per config


def hms(t: float) -> str:
    return f"{int(t//3600)}:{int(t%3600//60):02d}:{int(t%60):02d}"


def render_transcript(doc: dict) -> str:
    lines, prev_end = [], 0.0
    for u in doc["utterances"]:
        gap = u["start"] - prev_end
        if gap >= 10:
            lines.append(f"--- silence {gap:.0f}s ---")
        lines.append(f"[{u['start']:.1f}] {u['text']}")
        prev_end = u["end"]
    return "\n".join(lines)


def ollama(model: str, prompt: str, think: bool = False) -> str:
    """One generation. `think` is a config axis, not a detail — see FINDINGS.

    With thinking on, `format: json` must be off: ollama constrains generation
    from the first token, so the model spends its budget on reasoning the grammar
    then discards, and returns an empty string. With thinking off, `format: json`
    is what keeps small models from replying in prose.
    """
    opts = {"temperature": 0, "seed": 0, "num_ctx": 40960,
            "num_predict": 16384 if think else 8192}
    body = {"model": model, "prompt": prompt, "stream": False, "options": opts}
    if think:
        body["think"] = True
    else:
        body["think"] = False
        body["format"] = "json"
    def post(b: dict) -> str:
        if ENDPOINT is None:
            raise UnusableConfiguration(
                f"nothing set {__name__}.ENDPOINT; the caller owning the model host must"
            )

        def over(endpoint):
            req = urllib.request.Request(
                urljoin(endpoint, "/api/generate"),
                data=json.dumps(b).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return json.loads(r.read())["response"]

        return ReachesModelEndpoint(endpoint=ENDPOINT, over=over)()

    try:
        return post(body)
    except urllib.error.HTTPError as e:
        # ollama 0.34.0 regression: MLX-backend models reject `format: json`
        # with 501 "structured output is unavailable". GGUF models on the same
        # server still accept it, and 0.32.15 accepted it for both -- which is
        # what every number in FINDINGS was measured under.
        #
        # Measured 2026-09-17 on the real prompt: the 35B returns clean,
        # parseable JSON without the constraint anyway (18 blocks, 1 segment,
        # 28.3 s), because `parse_json` already strips fences and think blocks.
        # So drop the constraint rather than the model.
        if e.code != 501 or "format" not in body:
            raise
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:  # noqa: BLE001
            pass
        print(f"    [structured output refused ({detail.strip()}); "
              f"retrying unconstrained]", flush=True)
        body.pop("format", None)
        return post(body)


def parse_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except json.JSONDecodeError:
            return None
    return None


def call_json(model: str, prompt: str, think: bool = False) -> tuple[dict | None, int]:
    for attempt in range(MAX_REPAIRS + 1):
        p = prompt if attempt == 0 else (
            prompt + "\n\nYour previous reply was not valid JSON. "
                     "Reply with the JSON object only, nothing else.")
        try:
            out = parse_json(ollama(model, p, think))
        except (urllib.error.URLError, TimeoutError) as e:
            return None, attempt
        if out is not None:
            return out, attempt
    return None, MAX_REPAIRS


def coerce_blocks(raw: dict, doc: dict) -> list[dict]:
    """Clamp a model's blocks into the contiguous, in-range shape we require."""
    out = []
    for b in raw.get("blocks", []) or []:
        try:
            s, e = float(b["start"]), float(b["end"])
        except (KeyError, TypeError, ValueError):
            continue
        s = max(0.0, min(s, doc["duration"]))
        e = max(0.0, min(e, doc["duration"]))
        if e <= s:
            continue
        out.append({"start": s, "end": e, "type": str(b.get("type", "other")),
                    "confidence": float(b.get("confidence", 0.5) or 0.5),
                    "evidence": str(b.get("evidence", ""))[:200]})
    out.sort(key=lambda x: x["start"])
    for i in range(1, len(out)):
        if out[i]["start"] < out[i - 1]["end"]:
            out[i]["start"] = out[i - 1]["end"]
    return [b for b in out if b["end"] > b["start"]]


def run_whole(model: str, doc: dict, think: bool = False) -> dict:
    tpl = (requires_root(__name__, "PROMPTS", PROMPTS) / "whole_transcript.v2.md").read_text()
    prompt = (tpl.replace("{started_at}", doc["started_at"])
                 .replace("{duration_hms}", hms(doc["duration"]))
                 .replace("{duration}", f"{doc['duration']:.1f}")
                 .replace("{transcript}", render_transcript(doc)))
    raw, repairs = call_json(model, prompt, think)
    if raw is None:
        return {"blocks": [], "segments": [], "status": "invalid-json", "repairs": repairs}
    blks = coerce_blocks(raw, doc)
    derived = SEG.derive(blks, doc)
    model_segs = raw.get("segments", [])
    return {"blocks": blks, "derived_segments": derived,
            "segments": SEG.choose(model_segs, derived, doc),
            "model_segments": model_segs,
            "status": "ok" if blks else "no-blocks", "repairs": repairs}


def load_diarization(rid: str) -> dict | None:
    p = requires_directory_under_root(__name__, "DATA", DATA, "diarization") / f"{rid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def run_structured(model: str, doc: dict, think: bool = False) -> dict:
    """Hand the model a measured block table instead of the raw transcript."""
    dia = load_diarization(doc["recording_id"])
    if not dia:
        return {"blocks": [], "segments": [], "status": "no-diarization", "repairs": 0}

    cands = F.blocks_from_diarization(doc, dia)
    if not cands:
        return {"blocks": [], "segments": [], "status": "no-blocks", "repairs": 0}

    tpl = (requires_root(__name__, "PROMPTS", PROMPTS) / "structured.v1.md").read_text()
    prompt = (tpl.replace("{started_at}", doc["started_at"])
                 .replace("{duration_hms}", hms(doc["duration"]))
                 .replace("{table}", F.render_table(cands, doc, dia)))
    raw, repairs = call_json(model, prompt, think)
    if raw is None:
        return {"blocks": [], "segments": [], "status": "invalid-json", "repairs": repairs}

    # The model labels blocks by index; the timestamps stay ours, so it cannot
    # invent or fumble a boundary. That is the whole point of this strategy.
    typed = []
    by_index = {}
    for e in raw.get("blocks", []) or []:
        try:
            by_index[int(e["index"])] = e
        except (KeyError, TypeError, ValueError):
            continue
    for i, c in enumerate(cands):
        e = by_index.get(i, {})
        typed.append({"start": c["start"], "end": c["end"],
                      "type": str(e.get("type", "other")),
                      "confidence": float(e.get("confidence", 0.5) or 0.5),
                      "evidence": str(e.get("evidence", ""))[:200],
                      "speaker": c.get("speaker")})
    return {"blocks": typed, "segments": SEG.derive(typed, doc),
            "model_segments": raw.get("segments", []),
            "status": "ok", "repairs": repairs}


def run_perblock(model: str, doc: dict, think: bool = False) -> dict:
    deadline = time.time() + RECORDING_BUDGET_S
    tpl = (requires_root(__name__, "PROMPTS", PROMPTS) / "per_block.v2.md").read_text()
    cands = B.candidates(doc)
    start_dt = doc["started_at"]
    summaries = [f"{(c['end']-c['start'])/60:.0f} min of speech" for c in cands]
    out, repairs = [], 0
    for i, c in enumerate(cands):
        wall = ""
        try:
            import datetime as dt
            wall = (dt.datetime.fromisoformat(start_dt)
                    + dt.timedelta(seconds=c["start"])).strftime("%-I:%M %p")
        except Exception:
            pass
        prompt = (tpl.replace("{started_at}", start_dt)
                     .replace("{block_start_hms}", hms(c["start"]))
                     .replace("{block_end_hms}", hms(c["end"]))
                     .replace("{block_duration_hms}", hms(c["end"] - c["start"]))
                     .replace("{block_wallclock}", wall or "unknown")
                     .replace("{prev_summary}", summaries[i-1] if i else "nothing, this is the start")
                     .replace("{next_summary}", summaries[i+1] if i+1 < len(cands) else "nothing, the recording ends")
                     .replace("{block_text}", B.text_of(c, max_chars=12000) or "(no speech)"))
        if time.time() > deadline:
            out.append({"start": c["start"], "end": c["end"], "type": "other",
                        "confidence": 0.0, "evidence": "not reached: budget exhausted"})
            continue
        raw, rep = call_json(model, prompt, think)
        repairs += rep
        out.append({"start": c["start"], "end": c["end"],
                    "type": str((raw or {}).get("type", "other")),
                    "confidence": float((raw or {}).get("confidence", 0.5) or 0.5),
                    "evidence": str((raw or {}).get("evidence", ""))[:200]})
    unreached = sum(1 for b in out if b["confidence"] == 0.0)
    return {"blocks": out, "segments": SEG.derive(out, doc),
            "status": "ok" if not unreached else f"budget-exhausted:{unreached}-blocks",
            "repairs": repairs}
