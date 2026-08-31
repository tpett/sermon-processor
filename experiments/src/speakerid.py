#!/usr/bin/env python3
"""Spike 5 — identify the preacher rather than merely diarize.

Q12: one primary preacher plus three or four others. Diarization answers "who
spoke when" with anonymous labels. Identification answers "is this the regular
preacher", which is the strongest available signal for the thing the local models
are actually weakest at — deciding which block is the sermon.

Enrolment is free: every ground-truth sermon span is, by definition, a labelled
sample of whoever preached it. No separate enrolment session is needed, which is
what makes this cheap enough to be worth having.
"""
from __future__ import annotations

import argparse, json, subprocess, sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import diarize as D  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
EMB_MODEL = WORK / "models" / "nemo_en_titanet_small.onnx"
SAMPLE_S = 20.0          # per excerpt
EXCERPTS = 4             # excerpts per span, spread through it


def extractor(threads: int = 8):
    import sherpa_onnx
    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=str(EMB_MODEL), num_threads=threads)
    if not cfg.validate():
        raise RuntimeError("embedding extractor config invalid")
    return sherpa_onnx.SpeakerEmbeddingExtractor(cfg)


def embed_span(ex, src: Path, start: float, end: float) -> np.ndarray | None:
    """Mean embedding over several excerpts, so one noisy moment cannot define a voice."""
    import soundfile as sf
    vecs = []
    span = end - start
    for k in range(EXCERPTS):
        at = start + span * (k + 0.5) / EXCERPTS - SAMPLE_S / 2
        at = max(start, min(at, end - SAMPLE_S))
        if at < 0 or SAMPLE_S > span:
            continue
        tmp = WORK / "spk.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-t", f"{SAMPLE_S}",
                        "-i", str(src), "-af", "pan=mono|c0=c0", "-ar", "16000",
                        "-ac", "1", "-y", str(tmp)], check=True)
        a, sr = sf.read(str(tmp), dtype="float32")
        s = ex.create_stream(); s.accept_waveform(sr, a); s.input_finished()
        if ex.is_ready(s):
            vecs.append(np.array(ex.compute(s), dtype=np.float32))
    if not vecs:
        return None
    v = np.mean(vecs, axis=0)
    return v / (np.linalg.norm(v) + 1e-9)


def cos(a, b) -> float:
    return float(np.dot(a, b))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()

    gt = json.loads((DATA / "groundtruth.json").read_text())
    recs = [r for r in gt["recordings"] if r.get("segments") and r.get("recording_id")]
    ex = extractor()

    print("Embedding every ground-truth teaching span (this is the enrolment set)\n")
    voices = {}
    for r in sorted(recs, key=lambda x: x["desktop_label"]):
        s = r["segments"][0]
        v = embed_span(ex, Path(r["source_path"]), s["punch_in"], s["punch_out"])
        if v is None:
            continue
        voices[r["desktop_label"]] = v
        print(f"  {r['desktop_label'][:38]:<40} ok")

    labels = list(voices)
    M = np.array([voices[l] for l in labels])
    S = M @ M.T
    print(f"\nPairwise similarity across {len(labels)} teaching spans")
    off = S[~np.eye(len(labels), dtype=bool)]
    print(f"  same-corpus similarity: median {np.median(off):.3f}, "
          f"min {off.min():.3f}, max {off.max():.3f}")

    # Cluster greedily: how many distinct voices does the corpus actually contain?
    for thr in (0.5, 0.6, 0.7, 0.8):
        assigned, clusters = {}, []
        for i, l in enumerate(labels):
            placed = False
            for ci, c in enumerate(clusters):
                if np.mean([S[i][j] for j in c]) >= thr:
                    c.append(i); assigned[l] = ci; placed = True; break
            if not placed:
                clusters.append([i]); assigned[l] = len(clusters) - 1
        sizes = sorted((len(c) for c in clusters), reverse=True)
        print(f"  threshold {thr:.1f} -> {len(clusters)} voices, sizes {sizes}")

    out = WORK / "voices.json"
    out.write_text(json.dumps({l: voices[l].tolist() for l in labels}))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def rank_blocks(ex, rec, voices, exclude_label):
    """Score each block of a recording against the enrolled primary voice.

    Leave-one-out: the recording under test never contributes to the profile it
    is scored against, so a match cannot be trivially self-referential.
    """
    import numpy as _np
    others = [v for l, v in voices.items() if l != exclude_label]
    if not others:
        return []
    # Primary = the largest cluster's centroid, found greedily at 0.65.
    M = _np.array(others); S = M @ M.T
    best_i = int(_np.argmax(S.sum(axis=1)))
    prim = M[(S[best_i] >= 0.65)].mean(axis=0)
    prim = prim / (_np.linalg.norm(prim) + 1e-9)

    bp = DATA / "blocks" / f"{rec['recording_id']}.c-frontier.whole.v2.json"
    if not bp.exists():
        return []
    out = []
    for b in json.loads(bp.read_text())["blocks"]:
        if b["end"] - b["start"] < 90:
            continue
        v = embed_span(ex, Path(rec["source_path"]), b["start"], b["end"])
        if v is None:
            continue
        out.append({"type": b["type"], "start": b["start"], "end": b["end"],
                    "sim": round(cos(v, prim), 3)})
    out.sort(key=lambda x: -x["sim"])
    return out
