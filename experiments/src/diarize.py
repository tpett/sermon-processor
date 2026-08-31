#!/usr/bin/env python3
"""Speaker diarization — who speaks when.

Motivation is specific rather than general. The measurement in FINDINGS shows
punch-out is solved and punch-in is the entire remaining gap, with errors
skewed late. The sermon punch-in *is* a speaker change (Q16: the preacher comes
up right after the scripture reading), and nothing in the pipeline currently
detects one. This supplies that signal.

Runs fully offline via sherpa-onnx. No HuggingFace token, no hosted service.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
MODELS = WORK / "models"

SEG_MODEL = MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"
EMB_MODEL = MODELS / "nemo_en_titanet_small.onnx"


# Measured on dev: at the sherpa default the clusterer returns 12-27 "speakers"
# for a service with about four, and splits one preacher across two labels — the
# first 40 s of a sermon under one, the rest under another. Block assembly then
# folds that short opening into the *previous* block, moving the boundary 40 s
# past the punch-in. Raising the merge threshold gives 4-5 speakers and puts the
# block edge exactly on the punch-in (+0.00 s on the recording tested).
DEFAULT_THRESHOLD = 0.9


def build(num_speakers: int = -1, threshold: float = DEFAULT_THRESHOLD, threads: int = 8):
    import sherpa_onnx
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(SEG_MODEL)),
            num_threads=threads),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(EMB_MODEL), num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers, threshold=threshold),
        min_duration_on=1.0,     # ignore sub-second turns; we want structure, not turns
        min_duration_off=0.5,
    )
    if not cfg.validate():
        raise RuntimeError("sherpa-onnx diarization config failed validation")
    return sherpa_onnx.OfflineSpeakerDiarization(cfg)


def wav16k(src: Path, tag: str) -> Path:
    wav = WORK / "raw" / f"{tag}.16k.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    if not wav.exists():
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(src), "-af", "pan=mono|c0=c0",
             "-ar", "16000", "-ac", "1", "-y", str(wav)], check=True)
    return wav


def diarize_one(sd, wav: Path) -> list[dict]:
    import soundfile as sf
    audio, sr = sf.read(str(wav), dtype="float32", always_2d=False)
    assert sr == 16000, sr
    res = sd.process(audio).sort_by_start_time()
    return [{"start": round(s.start, 3), "end": round(s.end, 3),
             "speaker": f"S{s.speaker}"} for s in res]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out_dir = DATA / "diarization"
    out_dir.mkdir(parents=True, exist_ok=True)
    gt = json.loads((DATA / "groundtruth.json").read_text())
    targets = [r for r in gt["recordings"] if r.get("recording_id")]
    if args.split != "all":
        targets = [r for r in targets if r["split"] == args.split]
    if args.only:
        targets = [r for r in targets if args.only in r["desktop_label"]]

    sd = build(threshold=args.threshold)
    for i, rec in enumerate(targets, 1):
        rid, label = rec["recording_id"], rec["desktop_label"]
        dst = out_dir / f"{rid}.json"
        if dst.exists() and not args.force:
            print(f"[{i}/{len(targets)}] {label[:36]:<38} cached")
            continue
        print(f"[{i}/{len(targets)}] {label[:36]:<38} ", end="", flush=True)
        t0 = time.time()
        wav = wav16k(Path(rec["source_path"]), label)
        turns = diarize_one(sd, wav)
        el = time.time() - t0
        speakers = sorted({t["speaker"] for t in turns})
        dst.write_text(json.dumps({
            "recording_id": rid, "desktop_label": label,
            "threshold": args.threshold, "turns": turns,
            "n_speakers": len(speakers), "seconds": round(el, 1)}))
        print(f"{len(turns):5d} turns  {len(speakers):2d} speakers  "
              f"{el:6.1f}s ({rec['source_duration']/el:.0f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
