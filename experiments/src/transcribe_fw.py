#!/usr/bin/env python3
"""Transcribe with faster-whisper, for the production container.

The deployment boundary settled 2026-09-17 puts transcription on the app server:
Linux, x86_64, CPU-only (Ryzen 9700X, no GPU), and therefore no mlx. Every
boundary figure in FINDINGS was measured on mlx word timestamps that punch-ins
snap to, so the question this script exists to answer is narrow and important:

    does changing the inference engine move the boundaries?

Same weights (large-v3-turbo), same language, same no-condition-on-previous-text
handling. Different engine, different word-timestamp alignment. Output shape is
identical to transcribe.py so every downstream stage reads it unchanged, and the
asr_config differs so both can sit side by side and be scored against each other.
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
from sermon.pipeline import audio  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
WORK = HERE / "work"

DEFAULT_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
COARSE_HZ = 100


def asr_config_id(model: str, compute: str, word_timestamps: bool) -> str:
    return f"fw-{model.split('/')[-1]}.{compute}{'+words' if word_timestamps else ''}"


def transcribe_one(src: Path, tag: str, model_name: str, compute: str,
                   word_timestamps: bool, threads: int) -> dict:
    from faster_whisper import WhisperModel

    wav = WORK / "raw" / f"{tag}.16k.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    made_wav = not wav.exists()
    if made_wav:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(src),
             "-af", "pan=mono|c0=c0", "-ar", "16000", "-ac", "1", "-y", str(wav)],
            check=True)

    model = WhisperModel(model_name, device="cpu", compute_type=compute,
                         cpu_threads=threads)
    t0 = time.time()
    # condition_on_previous_text=False for the same reason as the mlx path: long
    # stretches of singing send long-form Whisper into repetition loops.
    #
    # vad_filter stays OFF deliberately. It would drop the silences, and the
    # silence runs are load-bearing downstream -- blocking splits on them and the
    # emptiness gate reads them.
    segments, _info = model.transcribe(
        str(wav), language="en", word_timestamps=word_timestamps,
        condition_on_previous_text=False, vad_filter=False)

    utterances = []
    for s in segments:  # generator: work happens here
        u = {
            "start": round(float(s.start), 3),
            "end": round(float(s.end), 3),
            "speaker": None,
            "text": s.text.strip(),
            "avg_logprob": round(float(s.avg_logprob or 0.0), 4),
            "no_speech_prob": round(float(s.no_speech_prob or 0.0), 4),
            "compression_ratio": round(float(s.compression_ratio or 0.0), 3),
        }
        if word_timestamps and s.words:
            u["words"] = [{"w": w.word.strip(),
                           "start": round(float(w.start), 3),
                           "end": round(float(w.end), 3)} for w in s.words]
        utterances.append(u)
    elapsed = time.time() - t0
    if made_wav:
        wav.unlink(missing_ok=True)
    return {"utterances": utterances, "elapsed_s": round(elapsed, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--compute", default="int8",
                    choices=["int8", "int8_float32", "float32"])
    ap.add_argument("--threads", type=int, default=8,
                    help="production is 8 cores / 16 threads")
    ap.add_argument("--no-word-timestamps", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--split")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    word_ts = not args.no_word_timestamps
    cfg = asr_config_id(args.model, args.compute, word_ts)
    out_dir = DATA / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    gt = json.loads((DATA / "groundtruth.json").read_text())
    targets = [r for r in gt["recordings"] if r.get("recording_id")]
    if args.only:
        targets = [r for r in targets if args.only in r["desktop_label"]]
    if args.split:
        targets = [r for r in targets if r["split"] == args.split]
    if args.limit:
        targets = targets[:args.limit]

    print(f"config: {cfg}   threads={args.threads}   recordings: {len(targets)}")
    total_audio = total_wall = 0.0
    for i, rec in enumerate(targets, 1):
        rid, label = rec["recording_id"], rec["desktop_label"]
        dst = out_dir / f"{rid}.{cfg}.json"
        if dst.exists() and not args.force:
            print(f"[{i}/{len(targets)}] {label[:38]:<40} cached")
            continue
        print(f"[{i}/{len(targets)}] {label[:38]:<40} ", end="", flush=True)
        res = transcribe_one(Path(rec["source_path"]), label, args.model,
                             args.compute, word_ts, args.threads)

        env_path = WORK / "env" / f"{label}.{COARSE_HZ}hz.npy"
        env = (np.load(env_path) if env_path.exists()
               else audio.cached_envelope(Path(rec["source_path"]), WORK, COARSE_HZ, label))
        doc = {
            "recording_id": rid, "desktop_label": label, "asr_config": cfg,
            "model": args.model, "compute_type": args.compute,
            "word_timestamps": word_ts, "started_at": rec["started_at"],
            "duration": rec["source_duration"], "split": rec["split"],
            "utterances": res["utterances"],
            "silences": audio.quiet_runs(env, COARSE_HZ, min_seconds=2.0),
            "transcribe_seconds": res["elapsed_s"],
        }
        dst.write_text(json.dumps(doc))
        total_audio += rec["source_duration"]
        total_wall += res["elapsed_s"]
        nw = sum(len(u.get("words", [])) for u in res["utterances"])
        print(f"{len(res['utterances']):5d} utts  {nw:6d} words  "
              f"{res['elapsed_s']:7.1f}s ({rec['source_duration']/res['elapsed_s']:.1f}x)")

    if total_wall:
        print(f"\n{total_audio/3600:.1f}h of audio in {total_wall/60:.1f} min "
              f"({total_audio/total_wall:.1f}x realtime on this host)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
