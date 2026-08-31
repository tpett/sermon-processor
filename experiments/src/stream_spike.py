#!/usr/bin/env python3
"""Spike 3 — can the browser seek into a long recording without downloading it?

Q27: "allowing the player in the browser to jump to certain points and only
download segments of the file relevant to where they're scrubbed... as long as
it's not overly complicated."

Two candidates:
  A. one constant-bitrate MP3 served over HTTP range requests
  B. HLS — the file cut into segments with a manifest

A is far simpler. The question is whether byte-offset seeking actually lands
where you asked, because with CBR the player computes position arithmetically.
This measures that against the real audio rather than assuming it.
"""
from __future__ import annotations

import json, subprocess, sys, time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import audio as A  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
DATA, WORK = HERE / "data", HERE / "work"
OUT = WORK / "stream"
SEEK_TESTS = [600.0, 1800.0, 3600.0, 5400.0, 6000.0]
WINDOW_S = 10.0


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def make_cbr(src: Path, dst: Path, kbps: int) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    sh(["ffmpeg", "-v", "error", "-i", str(src), "-af", "pan=mono|c0=c0",
        "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-ar", "44100", "-ac", "1",
        "-write_xing", "0", "-y", str(dst)])
    return {"seconds": time.time() - t0, "mb": dst.stat().st_size / 1e6}


def make_hls(src: Path, ddir: Path, kbps: int, seg: int = 10) -> dict:
    ddir.mkdir(parents=True, exist_ok=True)
    for f in ddir.glob("*"):
        f.unlink()
    t0 = time.time()
    sh(["ffmpeg", "-v", "error", "-i", str(src), "-af", "pan=mono|c0=c0",
        "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-ar", "44100", "-ac", "1",
        "-f", "hls", "-hls_time", str(seg), "-hls_list_size", "0",
        "-hls_segment_type", "mpegts", "-y", str(ddir / "index.m3u8")])
    files = list(ddir.glob("*.ts"))
    return {"seconds": time.time() - t0,
            "mb": sum(f.stat().st_size for f in files) / 1e6,
            "segments": len(files)}


def envelope_of(path: Path, tag: str, hz: int = 50) -> np.ndarray:
    raw = WORK / "raw" / f"{tag}.stream.raw"
    raw.parent.mkdir(parents=True, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-i", str(path), "-ar", "16000", "-ac", "1",
        "-f", "s16le", "-y", str(raw)])
    e = A.envelope(raw, hz)
    raw.unlink(missing_ok=True)
    return e


def main() -> int:
    gt = json.loads((DATA / "groundtruth.json").read_text())
    rec = next(r for r in gt["recordings"]
               if r["desktop_label"] == "2026-08-23 - Hebrews 12.4-11")
    src = Path(rec["source_path"])
    dur = rec["source_duration"]
    print(f"source: {rec['desktop_label']}  {dur/60:.0f} min\n")

    KBPS = 48
    cbr = OUT / "preview.cbr.mp3"
    a = make_cbr(src, cbr, KBPS)
    h = make_hls(src, OUT / "hls", KBPS)
    print(f"A  CBR MP3 {KBPS}k   {a['mb']:7.1f} MB   built in {a['seconds']:.0f}s   1 file")
    print(f"B  HLS     {KBPS}k   {h['mb']:7.1f} MB   built in {h['seconds']:.0f}s   "
          f"{h['segments']} segments + manifest\n")

    # Byte-range seek accuracy: compute the offset arithmetically, as a player
    # would, fetch only that slice, and check where the audio actually lands.
    size = cbr.stat().st_size
    bps = size / dur
    src_env = envelope_of(src, "seek_src", 50)
    print(f"{'seek to':>9}{'bytes fetched':>15}{'% of file':>11}{'lands at':>11}{'error':>10}")
    errs = []
    for t in SEEK_TESTS:
        if t + WINDOW_S > dur:
            continue
        start = int(t * bps); nbytes = int(WINDOW_S * bps)
        slice_path = OUT / "slice.mp3"
        with open(cbr, "rb") as f:
            f.seek(start)
            slice_path.write_bytes(f.read(nbytes))
        se = envelope_of(slice_path, "seek_slice", 50)
        if len(se) < 50:
            print(f"{t:8.0f}s   slice did not decode"); continue
        probe = se[25:25 + 250]
        lo, hi = max(0, int((t - 30) * 50)), min(len(src_env), int((t + 40) * 50))
        corr = A.ncc(src_env[lo:hi], probe)
        idx, val, _ = A.peak_and_ratio(corr, guard=25)
        landed = (lo + idx) / 50 - 0.5
        err = landed - t
        errs.append(abs(err))
        print(f"{t:8.0f}s{nbytes/1e6:14.2f}MB{100*nbytes/size:10.2f}%"
              f"{landed:10.1f}s{err:+9.2f}s")
    if errs:
        print(f"\nbyte-offset seek error: median {np.median(errs):.2f}s, worst {max(errs):.2f}s")
    print(f"a 10-second window is {100*WINDOW_S*bps/size:.2f}% of the file "
          f"({WINDOW_S*bps/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
