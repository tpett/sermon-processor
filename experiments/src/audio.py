"""Audio decoding and envelope helpers.

Everything here works on the *energy envelope* rather than the raw waveform.
The published MP3s are peak-normalized copies of a span of the source, and some
may have had compression applied. Envelope correlation is robust to both, where
raw-waveform correlation is not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 16_000


def decode(src: Path, dst: Path, sr: int = SR) -> Path:
    """Decode channel 1 of `src` to headerless mono s16le at `sr`.

    Channel 1 only, never a downmix: channel 2 of the recorder's output is
    silent, and averaging would cost 6 dB and fold in its noise.
    """
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".partial")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src),
         "-af", "pan=mono|c0=c0", "-ar", str(sr), "-ac", "1",
         "-f", "s16le", "-y", str(tmp)],
        check=True,
    )
    tmp.rename(dst)
    return dst


def envelope(raw: Path, hz: int, sr: int = SR, chunk: int = 1 << 24) -> np.ndarray:
    """RMS energy envelope at `hz` frames per second, computed in chunks."""
    x = np.memmap(raw, dtype=np.int16, mode="r")
    win = sr // hz
    n_frames = len(x) // win
    out = np.empty(n_frames, dtype=np.float32)
    step = max(win, (chunk // win) * win)
    i = o = 0
    while o < n_frames:
        seg = np.asarray(x[i:i + step], dtype=np.float32)
        m = min(len(seg) // win, n_frames - o)
        if m == 0:
            break
        seg = seg[:m * win].reshape(m, win)
        out[o:o + m] = np.sqrt((seg * seg).mean(axis=1) + 1e-9)
        i += m * win
        o += m
    return out[:o]


def cached_envelope(src: Path, work: Path, hz: int, tag: str) -> np.ndarray:
    """Decode-and-envelope with both steps cached on disk."""
    key = f"{tag}.{hz}hz"
    npy = work / "env" / f"{key}.npy"
    if npy.exists():
        return np.load(npy)
    raw = decode(src, work / "raw" / f"{tag}.raw")
    env = envelope(raw, hz)
    npy.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy, env)
    return env


def ncc(long_env: np.ndarray, short_env: np.ndarray) -> np.ndarray:
    """Normalized cross-correlation of `short_env` at every offset in `long_env`.

    Returns an array of length len(long) - len(short) + 1, values in [-1, 1].
    Normalization makes this invariant to the gain difference between the
    source and the peak-normalized export.
    """
    a = np.asarray(long_env, dtype=np.float64)
    b = np.asarray(short_env, dtype=np.float64)
    m, n = len(b), len(a)
    if n < m:
        raise ValueError(f"short ({m}) longer than long ({n})")

    b = b - b.mean()
    b_norm = np.sqrt((b * b).sum())
    if b_norm == 0:
        raise ValueError("short envelope is flat")

    nfft = 1 << (n + m - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(a, nfft) * np.fft.rfft(b[::-1], nfft), nfft)
    corr = corr[m - 1: m - 1 + (n - m + 1)]

    # Sliding window variance of `a`, via cumulative sums. Because `b` is
    # zero-mean, the window mean of `a` drops out of the numerator.
    cs = np.concatenate(([0.0], np.cumsum(a)))
    cs2 = np.concatenate(([0.0], np.cumsum(a * a)))
    s = cs[m:] - cs[:-m]
    s2 = cs2[m:] - cs2[:-m]
    var = np.maximum(s2 - s * s / m, 1e-12)

    return corr / (np.sqrt(var) * b_norm)


def peak_and_ratio(corr: np.ndarray, guard: int) -> tuple[int, float, float]:
    """Best offset, its NCC, and how far it stands above the next real peak.

    `guard` masks out the neighbourhood of the winner, so the runner-up is a
    genuinely different alignment rather than the same peak one frame over.
    """
    idx = int(np.argmax(corr))
    best = float(corr[idx])
    masked = corr.copy()
    lo, hi = max(0, idx - guard), min(len(corr), idx + guard + 1)
    masked[lo:hi] = -np.inf
    runner = float(np.max(masked)) if np.isfinite(masked).any() else 0.0
    ratio = best / runner if runner > 1e-6 else float("inf")
    return idx, best, ratio


def quiet_mask(env_coarse, speech_pct: float = 75, drop_db: float = 20.0,
               floor_margin_db: float = 6.0):
    """Boolean mask of frames quiet enough to cut in, plus the threshold used.

    Relative to the recording's own speech level rather than an absolute dB, so
    it survives the week-to-week level variation in the source material.
    """
    import numpy as _np
    db = 20 * _np.log10(_np.maximum(env_coarse, 1e-6))
    speech = float(_np.percentile(db, speech_pct))
    floor = float(_np.percentile(db, 5))
    thresh = max(speech - drop_db, floor + floor_margin_db)
    return db < thresh, thresh


def quiet_runs(env_coarse, hz: int, min_seconds: float = 2.0):
    """Contiguous quiet spans of at least `min_seconds`, as (start, end) seconds."""
    import numpy as _np
    mask, _ = quiet_mask(env_coarse)
    if not mask.any():
        return []
    edges = _np.diff(mask.astype(_np.int8))
    starts = list(_np.flatnonzero(edges == 1) + 1)
    ends = list(_np.flatnonzero(edges == -1) + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        ends.append(len(mask))
    out = []
    for a, b in zip(starts, ends):
        if (b - a) / hz >= min_seconds:
            out.append({"start": round(a / hz, 2), "end": round(b / hz, 2)})
    return out
