#!/usr/bin/env python3
"""Stage 1/2 — produce the frozen transcript for a recording.

Stage 1 runs every rung of the reasoning ladder over an identical transcript, so
this runs once per ASR configuration and its output is then immutable.

Captures per-segment ASR confidence alongside the text. Those numbers are the
cheap music-versus-speech signal the spec hopes will make a dedicated classifier
unnecessary (Q10), so they are worth keeping whether or not we end up using them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import audio  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
WORK = HERE / "work"

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
COARSE_HZ = 100


def asr_config_id(model: str, word_timestamps: bool) -> str:
    slug = model.split("/")[-1]
    return f"{slug}{'+words' if word_timestamps else ''}"


def transcribe_one(src: Path, tag: str, model: str, word_timestamps: bool) -> dict:
    import mlx_whisper

    wav = WORK / "raw" / f"{tag}.16k.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    if not wav.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(src),
             "-af", "pan=mono|c0=c0", "-ar", "16000", "-ac", "1", "-y", str(wav)],
            check=True)

    t0 = time.time()
    # condition_on_previous_text=False: long-form Whisper is prone to repetition
    # loops over music and silence, and twenty minutes of singing is exactly the
    # condition that triggers them.
    r = mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=model, language="en",
        word_timestamps=word_timestamps, condition_on_previous_text=False,
        verbose=False)
    elapsed = time.time() - t0
    wav.unlink(missing_ok=True)

    utterances = []
    for s in r["segments"]:
        u = {
            "start": round(float(s["start"]), 3),
            "end": round(float(s["end"]), 3),
            "speaker": None,          # filled in only by the Stage 3 diarization arm
            "text": s["text"].strip(),
            "avg_logprob": round(float(s.get("avg_logprob", 0.0)), 4),
            "no_speech_prob": round(float(s.get("no_speech_prob", 0.0)), 4),
            "compression_ratio": round(float(s.get("compression_ratio", 0.0)), 3),
        }
        if word_timestamps and s.get("words"):
            u["words"] = [{"w": w["word"].strip(),
                           "start": round(float(w["start"]), 3),
                           "end": round(float(w["end"]), 3)} for w in s["words"]]
        utterances.append(u)
    return {"utterances": utterances, "elapsed_s": round(elapsed, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-word-timestamps", action="store_true")
    ap.add_argument("--only", help="substring of a Desktop label")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    word_ts = not args.no_word_timestamps
    cfg = asr_config_id(args.model, word_ts)
    out_dir = DATA / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    gt = json.loads((DATA / "groundtruth.json").read_text())
    targets = [r for r in gt["recordings"] if r.get("recording_id")]
    if args.only:
        targets = [r for r in targets if args.only in r["desktop_label"]]

    total_audio = total_wall = 0.0
    for i, rec in enumerate(targets, 1):
        rid, label = rec["recording_id"], rec["desktop_label"]
        dst = out_dir / f"{rid}.{cfg}.json"
        if dst.exists() and not args.force:
            print(f"[{i}/{len(targets)}] {label[:38]:<40} cached")
            continue

        print(f"[{i}/{len(targets)}] {label[:38]:<40} ", end="", flush=True)
        res = transcribe_one(Path(rec["source_path"]), label, args.model, word_ts)

        # Stage 0 only cached envelopes for recordings it aligned, so the
        # negatives (no published MP3) arrive here without one.
        env_path = WORK / "env" / f"{label}.{COARSE_HZ}hz.npy"
        if env_path.exists():
            env = np.load(env_path)
        else:
            env = audio.cached_envelope(Path(rec["source_path"]), WORK, COARSE_HZ, label)
        doc = {
            "recording_id": rid,
            "desktop_label": label,
            "asr_config": cfg,
            "model": args.model,
            "word_timestamps": word_ts,
            "started_at": rec["started_at"],
            "duration": rec["source_duration"],
            "split": rec["split"],
            "utterances": res["utterances"],
            "silences": audio.quiet_runs(env, COARSE_HZ, min_seconds=2.0),
            "transcribe_seconds": res["elapsed_s"],
        }
        dst.write_text(json.dumps(doc))
        total_audio += rec["source_duration"]
        total_wall += res["elapsed_s"]
        n_words = sum(len(u.get("words", [])) for u in res["utterances"])
        print(f"{len(res['utterances']):5d} utts  {n_words:6d} words  "
              f"{len(doc['silences']):3d} silences  "
              f"{res['elapsed_s']:6.1f}s ({rec['source_duration']/res['elapsed_s']:.0f}x)")

    if total_wall:
        print(f"\ntranscribed {total_audio/3600:.1f}h of audio in "
              f"{total_wall/60:.1f} min ({total_audio/total_wall:.0f}x realtime)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
