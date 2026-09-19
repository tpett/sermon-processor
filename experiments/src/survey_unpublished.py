#!/usr/bin/env python3
"""What are the recordings nobody edited?

52 of the 83 bucket objects have no published output. The corpus has never
looked at them, so the taxonomy in the spec was derived entirely from material
that was kept. This transcribes a sample and asks — with an open question, not a
fixed list of types — what each one actually is.
"""
from __future__ import annotations

import argparse, datetime as dt, json, re, subprocess, sys, time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from sermon.pipeline import audio as A       # noqa: E402
from sermon.pipeline import classify as C    # noqa: E402

HERE = Path(__file__).resolve().parent.parent
WORK, DATA, PROMPTS = HERE / "work", HERE / "data", HERE / "prompts"
C.DATA, C.PROMPTS = DATA, PROMPTS
BUCKET = WORK / "bucket"
MODEL = "qwen3.6:35b-mlx"

PROMPT = """Below is a transcript of a recording made by a microphone in a church
auditorium. Nobody edited or published this recording, and we do not know what it
is. It might be a rehearsal, a meeting, a class, a service, a sound check, or a
microphone left running in an empty room.

Say what it actually is. Do not try to fit it into any category — describe what
you observe.

The recording started at {started} on a {weekday} and runs {minutes} minutes.

Return only JSON, with these keys:
- `what`: what this recording is, in under 12 words
- `evidence`: the specific thing in the transcript that tells you, under 20 words
- `publishable`: true only if this contains teaching or a service someone might
  want to distribute; false for rehearsals, sound checks, empty rooms, and
  private meetings
- `speech`: "none", "sparse", or "continuous"

Transcript:

{transcript}
"""


def probe_dur(p: Path) -> tuple[float, bool]:
    """Duration, and whether the container could report it.

    Some uploads have a damaged or missing STREAMINFO block, so ffprobe returns
    N/A. Decoding still works, so the fallback counts samples. A real ingest
    path needs this: a corrupt header is not a reason to drop a recording, but it
    is a reason to flag it.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out), True
    except ValueError:
        pass
    err = subprocess.run(["ffmpeg", "-v", "error", "-nostats", "-i", str(p),
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    got = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "a:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(got), False
    except ValueError:
        return 0.0, False


def transcribe(p: Path, tag: str) -> dict:
    import mlx_whisper
    cache = WORK / "unpub" / f"{tag}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return json.loads(cache.read_text())
    wav = WORK / "raw" / f"{tag}.16k.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-af", "pan=mono|c0=c0",
                    "-ar", "16000", "-ac", "1", "-y", str(wav)], check=True)
    r = mlx_whisper.transcribe(str(wav), path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
                               language="en", condition_on_previous_text=False, verbose=False)
    wav.unlink(missing_ok=True)
    out = {"utterances": [{"start": round(s["start"], 2), "text": s["text"].strip(),
                           "no_speech_prob": round(float(s.get("no_speech_prob", 0)), 3)}
                          for s in r["segments"]]}
    cache.write_text(json.dumps(out))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    files = sorted(BUCKET.glob("recording_*.flac"))
    print(f"{len(files)} unpublished recordings sampled\n")
    rows = []
    for p in files:
        m = re.match(r"recording_(\d{8})_(\d{6})", p.stem)
        when = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        dur, header_ok = probe_dur(p)
        env = A.cached_envelope(p, WORK, 100, "bkt_" + p.stem)
        db = 20 * np.log10(np.maximum(env, 1e-6))
        dyn = float(np.percentile(db, 95) - np.percentile(db, 5))

        if dyn < 15:
            rows.append({"key": p.stem, "when": when.isoformat(), "minutes": dur / 60,
                         "header_ok": header_ok,
                         "dynamic_db": round(dyn, 1), "what": "empty room — no content",
                         "evidence": f"dynamic range {dyn:.1f} dB", "publishable": False,
                         "speech": "none", "seconds": 0.0})
            print(f"  {when:%a %m-%d %H:%M}  {dur/60:5.0f}m  dyn {dyn:4.1f}dB   "
                  f"empty room (skipped, no transcription needed)")
            continue

        doc = transcribe(p, p.stem)
        text = " ".join(u["text"] for u in doc["utterances"])[:16000]
        prompt = (PROMPT.replace("{started}", when.strftime("%-I:%M %p"))
                        .replace("{weekday}", when.strftime("%A"))
                        .replace("{minutes}", f"{dur/60:.0f}")
                        .replace("{transcript}", text or "(no speech detected)"))
        t0 = time.time()
        raw, _ = C.call_json(args.model, prompt)
        el = time.time() - t0
        raw = raw or {}
        rows.append({"key": p.stem, "when": when.isoformat(), "minutes": dur / 60,
                     "header_ok": header_ok,
                     "dynamic_db": round(dyn, 1), "what": str(raw.get("what", "?"))[:70],
                     "evidence": str(raw.get("evidence", ""))[:80],
                     "publishable": bool(raw.get("publishable", False)),
                     "speech": str(raw.get("speech", "?")), "seconds": round(el, 1)})
        print(f"  {when:%a %m-%d %H:%M}  {dur/60:5.0f}m  dyn {dyn:4.1f}dB   "
              f"{'PUBLISHABLE' if rows[-1]['publishable'] else 'not published'}  "
              f"{'[BAD HEADER] ' if not header_ok else ''}{rows[-1]['what']}")

    out = WORK / "unpublished_survey.json"
    out.write_text(json.dumps(rows, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
