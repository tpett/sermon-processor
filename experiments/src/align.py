#!/usr/bin/env python3
"""Stage 0 — derive ground-truth punch points.

Joins each renamed Desktop FLAC back to its bucket object (recovering the
wall-clock start time the renaming destroyed), then finds where each published
MP3 sits inside its source recording.

Nothing here uses a model. The output is the yardstick every later stage is
measured against, so it validates aggressively and excludes rather than guesses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import audio  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
WORK = HERE / "work"
DATA = HERE / "data"
SERMONS = Path(os.path.expanduser("~/Desktop/Sermons"))
BUCKET = "s3://reformation-recordings/"
AWS_PROFILE = "nas"

COARSE_HZ = 100
FINE_HZ = 1_000
PROBE_S = 60          # length of each fine-alignment probe
PROBE_AT = (0.10, 0.30, 0.50, 0.70, 0.90)  # five, so drift can be fitted not just detected
FINE_SEARCH_S = 4.0   # how far around the coarse estimate to look

# Validation gates. A pair failing any of these is excluded and reported.
MIN_COARSE_NCC = 0.30
MIN_COARSE_RATIO = 1.5
MIN_PROBE_NCC = 0.30
# A contiguous excerpt can still disagree between probes if the two files run on
# slightly different clocks. Measured on this corpus: three early-2026 recordings
# drift about -130 ppm against their exports (a soundcard running at ~44094 Hz
# while labelled 44100), which is 0.23 s across a 50-minute sermon. Everything
# from 2026-03-29 onward is within 0.3 ppm.
#
# So the contiguity test is the *residual from a straight line*, not the raw
# spread: drift is linear and correctable, a real edit is not.
MAX_FIT_RESIDUAL_S = 0.06
MAX_DRIFT_PPM = 400.0

DEV_LABELS = [
    "2026-04-12 - John",
    "2026-05-03 - TEC",
    "2026-05-10 - Hebrews",
    "2026-05-31 - Hebrews",
    "2026-06-14 - Hebrews",
    "2026-06-28 - Members Meeting",
    "2026-07-12 - Hebrews",
    "2026-08-09 - Hebrews",
]

# Two-level cases: one recording holding two sessions, each published separately.
#
# 2026-08-02 was extracted to intermediate FLACs first, so its sessions and its
# segments can both be recovered. 2026-04-05 went straight from the source to two
# MP3s, so only the segments exist — which is the commoner shape and the one the
# system will actually see.
TWO_LEVEL_PARENT = "2026-08-02"
TWO_LEVEL_CHILDREN = ["2026-08-02 - TEC - Speech", "2026-08-02 - Hebrews 11.29-31"]

MULTI_OUTPUT = {
    "2026-04-05": ["2026-04-05 - TEC - Forgiveness", "2026-04-05 - Matthew 12.38-42"],
}


# --------------------------------------------------------------------------- #
# corpus assembly


def bucket_listing(refresh: bool = False) -> dict[int, list[str]]:
    """Object keys from the raw bucket, indexed by byte size."""
    cache = DATA / "bucket.txt"
    if refresh or not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(
            ["aws", "--profile", AWS_PROFILE, "s3", "ls", BUCKET],
            capture_output=True, text=True, check=True,
        ).stdout
        cache.write_text(out)
    by_size: dict[int, list[str]] = {}
    for line in cache.read_text().splitlines():
        m = re.match(r"\S+ \S+\s+(\d+)\s+(.+\.flac)$", line.strip())
        if m:
            by_size.setdefault(int(m.group(1)), []).append(m.group(2))
    return by_size


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def probe_bits(path: Path) -> int | None:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=bits_per_raw_sample", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out) if out.isdigit() else None


# Published outputs that were NOT cut by a human. These are real publications --
# the machine's proposal was approved and shipped unchanged -- but as ground
# truth they are circular: aligning one teaches the system that its own answer
# was correct, and every future measurement against it is self-graded.
#
# 2026-09-06 is the first. The reviewer approved the machine cut and published it
# without editing (confirmed 2026-09-14). It is a genuine result for the
# acceptance rate and must never be a yardstick.
#
# Match on the mp3 filename, because the sibling FLAC may not be on the Desktop
# today and the failure this prevents is someone adding it later.
MACHINE_CUT_MP3S = {
    "2026-09-06 - Hebrews 12.18-24.mp3",
    # 2026-09-13, both Segments of the class-plus-service recording. Approved by
    # ear and copied into the corpus on 2026-09-14 without edit.
    "2026-09-13 - TEC - Giving.mp3",
    "2026-09-13 - Hebrews 12.25-29.mp3",
}


def build_corpus() -> list[dict]:
    """Every Desktop FLAC, joined to its bucket object where one exists."""
    by_size = bucket_listing()
    items = []
    for flac in sorted(SERMONS.glob("*.flac")):
        size = flac.stat().st_size
        keys = by_size.get(size, [])
        mp3 = flac.with_suffix(".mp3")
        if mp3.name in MACHINE_CUT_MP3S:
            print(f"  skipping {mp3.name}: machine cut, not a human edit "
                  f"(see MACHINE_CUT_MP3S)")
            mp3 = flac.with_suffix(".__machine_cut__")
        label = flac.stem
        item = {
            "desktop_label": label,
            "source_path": str(flac),
            "size_bytes": size,
            "bits_per_raw_sample": probe_bits(flac),
            "source_duration": round(probe_duration(flac), 3),
            "mp3_path": str(mp3) if mp3.exists() else None,
            "mp3_duration": round(probe_duration(mp3), 3) if mp3.exists() else None,
            "object_key": keys[0] if len(keys) == 1 else None,
            "join": "unique" if len(keys) == 1 else f"{len(keys)}-matches",
            "split": "dev" if any(label.startswith(p) for p in DEV_LABELS) else "test",
        }
        if item["object_key"]:
            m = re.match(r"recording_(\d{8})_(\d{6})\.flac", item["object_key"])
            stamp = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            item["recording_id"] = item["object_key"][:-5]
            item["started_at"] = stamp.isoformat()
        else:
            item["recording_id"] = None
            item["started_at"] = None
        items.append(item)
    return items


# --------------------------------------------------------------------------- #
# alignment


def envelopes(src: Path, tag: str) -> tuple[np.ndarray, np.ndarray]:
    """Coarse and fine envelopes, decoding once and caching both."""
    paths = {hz: WORK / "env" / f"{tag}.{hz}hz.npy" for hz in (COARSE_HZ, FINE_HZ)}
    if all(p.exists() for p in paths.values()):
        return np.load(paths[COARSE_HZ]), np.load(paths[FINE_HZ])
    raw = audio.decode(src, WORK / "raw" / f"{tag}.raw")
    out = {}
    for hz, p in paths.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        out[hz] = audio.envelope(raw, hz)
        np.save(p, out[hz])
    raw.unlink(missing_ok=True)  # ~300 MB per recording; envelopes are the artifact
    return out[COARSE_HZ], out[FINE_HZ]


def align(parent_src: Path, parent_tag: str, child_src: Path, child_tag: str) -> dict:
    """Find where `child` sits inside `parent`. Offsets in seconds."""
    p_coarse, p_fine = envelopes(parent_src, parent_tag)
    c_coarse, c_fine = envelopes(child_src, child_tag)

    result: dict = {"probes": [], "reasons": []}

    if len(c_coarse) > len(p_coarse):
        result["status"] = "excluded"
        result["reasons"].append("child is longer than parent")
        return result

    corr = audio.ncc(p_coarse, c_coarse)
    idx, ncc_val, ratio = audio.peak_and_ratio(corr, guard=COARSE_HZ * 5)
    coarse_off = idx / COARSE_HZ
    result |= {"coarse_offset": round(coarse_off, 3),
               "coarse_ncc": round(ncc_val, 4),
               "coarse_peak_ratio": round(ratio, 2) if np.isfinite(ratio) else None}

    if ncc_val < MIN_COARSE_NCC:
        result["reasons"].append(f"coarse NCC {ncc_val:.3f} below {MIN_COARSE_NCC}")
    if ratio < MIN_COARSE_RATIO:
        result["reasons"].append(f"coarse peak ratio {ratio:.2f} below {MIN_COARSE_RATIO}")

    # Three independent fine alignments. They must agree: if the child is not a
    # contiguous excerpt (material cut from the middle, or two parts joined),
    # they will disagree and that is exactly what we want to catch.
    child_len_s = len(c_fine) / FINE_HZ
    search = int(FINE_SEARCH_S * FINE_HZ)
    for frac in PROBE_AT:
        p_start = max(0.0, min(frac * child_len_s, child_len_s - PROBE_S))
        a = int(p_start * FINE_HZ)
        b = a + int(PROBE_S * FINE_HZ)
        if b > len(c_fine):
            continue
        short = c_fine[a:b]
        centre = int((coarse_off + p_start) * FINE_HZ)
        lo = max(0, centre - search)
        hi = min(len(p_fine), centre + search + len(short))
        if hi - lo < len(short):
            continue
        c = audio.ncc(p_fine[lo:hi], short)
        j, val, r = audio.peak_and_ratio(c, guard=FINE_HZ // 2)
        result["probes"].append({
            "at_s": round(p_start, 1),
            "offset": round((lo + j) / FINE_HZ - p_start, 4),
            "ncc": round(val, 4),
            "peak_ratio": round(r, 2) if np.isfinite(r) else None,
        })

    good = [p for p in result["probes"] if p["ncc"] >= MIN_PROBE_NCC]
    if len(good) < 2:
        result["reasons"].append(f"only {len(good)} usable probes")
        result["status"] = "excluded"
        return result

    at = np.array([p["at_s"] for p in good], dtype=float)
    offsets = np.array([p["offset"] for p in good], dtype=float)
    spread = float(offsets.max() - offsets.min())

    # offset(p) = punch_in + p * drift. The intercept is the true start; the
    # slope is the clock difference between source and export. Fitting it
    # separates correctable drift from a genuine discontinuity — the residual
    # from the line is the real contiguity test, not the raw spread.
    if len(good) >= 3:
        drift, intercept = np.polyfit(at, offsets, 1)
        resid = float(np.max(np.abs(offsets - (intercept + drift * at))))
        offset = float(intercept)
    else:
        drift, resid, offset = 0.0, 0.0, float(np.median(offsets))

    result["drift_ppm"] = round(float(drift) * 1e6, 1)
    result["fit_residual_s"] = round(resid, 4)
    if resid > MAX_FIT_RESIDUAL_S:
        result["reasons"].append(
            f"probes deviate {resid:.3f}s from a straight line — not a contiguous excerpt")
    if abs(result["drift_ppm"]) > MAX_DRIFT_PPM:
        result["reasons"].append(f"clock drift {result['drift_ppm']:.0f} ppm is implausible")
    # A child cannot begin before its parent. A tiny negative is alignment
    # noise on an exact match at zero; a large one means something is wrong.
    if -0.05 <= offset < 0:
        offset = 0.0
    elif offset < -0.05:
        result["reasons"].append(f"offset {offset:.3f}s is before the start of the parent")
    result["offset"] = round(offset, 4)
    result["probe_spread_s"] = round(spread, 4)
    result["probe_ncc_min"] = round(min(p["ncc"] for p in good), 4)

    result["status"] = "excluded" if result["reasons"] else "ok"
    return result


# --------------------------------------------------------------------------- #
# cut difficulty


def difficulty(env_coarse: np.ndarray, t: float) -> dict:
    """How much quiet surrounds a boundary, per classification-spec.md."""
    db = 20 * np.log10(np.maximum(env_coarse, 1e-6))
    speech = float(np.percentile(db, 75))
    floor = float(np.percentile(db, 5))
    thresh = max(speech - 20.0, floor + 6.0)
    quiet = db < thresh

    i = int(round(t * COARSE_HZ))
    i = max(0, min(i, len(quiet) - 1))
    if not quiet[i]:
        return {"label": "hard", "quiet_ms": 0, "reason": "audio at the cut point"}

    lo = i
    while lo > 0 and quiet[lo - 1]:
        lo -= 1
    hi = i
    while hi < len(quiet) - 1 and quiet[hi + 1]:
        hi += 1
    ms = (hi - lo + 1) * (1000 // COARSE_HZ)

    label = "easy" if ms >= 2000 else "moderate" if ms >= 250 else "hard"
    return {"label": label, "quiet_ms": int(ms)}


# --------------------------------------------------------------------------- #
# driver


def run(only: str | None, refresh: bool) -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus()
    by_label = {c["desktop_label"]: c for c in corpus}

    joined = sum(1 for c in corpus if c["join"] == "unique")
    print(f"corpus: {len(corpus)} Desktop FLACs, {joined} joined uniquely to the bucket")
    for c in corpus:
        if c["join"] != "unique":
            print(f"  no unique bucket match: {c['desktop_label']} "
                  f"({c['join']}, {c['bits_per_raw_sample']}-bit)")

    records = []
    for c in corpus:
        label = c["desktop_label"]
        if only and only not in label:
            continue
        if c["bits_per_raw_sample"] != 32:
            continue  # derived extraction, not recorder output
        if label == TWO_LEVEL_PARENT or label in MULTI_OUTPUT:
            continue  # handled below, as its own multi-output case
        if not c["mp3_path"]:
            rec = dict(c, segments=[], validation={"status": "no-output",
                       "reasons": ["no published MP3"]})
            records.append(rec)
            print(f"  {label:<38} no MP3 — kept as a negative example")
            continue

        print(f"  {label:<38} aligning...", end="", flush=True)
        res = align(Path(c["source_path"]), label, Path(c["mp3_path"]), label + " [mp3]")
        rec = dict(c)
        if res["status"] == "ok":
            env_coarse, _ = envelopes(Path(c["source_path"]), label)
            pin = res["offset"]
            pout = pin + c["mp3_duration"]
            if pout > c["source_duration"] + 1.0:
                res["status"] = "excluded"
                res["reasons"].append("segment runs past the end of the source")
            else:
                rec["segments"] = [{
                    "punch_in": round(pin, 3),
                    "punch_out": round(pout, 3),
                    "derived_from": Path(c["mp3_path"]).name,
                    "difficulty_in": difficulty(env_coarse, pin),
                    "difficulty_out": difficulty(env_coarse, min(pout, c["source_duration"] - 0.01)),
                }]
                print(f" in={pin:8.2f}s out={pout:8.2f}s "
                      f"ncc={res['probe_ncc_min']:.2f} fit={res['fit_residual_s']*1000:4.0f}ms "
                      f"drift={res['drift_ppm']:+7.1f}ppm")
        if res["status"] != "ok":
            rec["segments"] = []
            print(f" EXCLUDED: {'; '.join(res['reasons'])}")
        rec["validation"] = res
        records.append(rec)

    # Recordings that produced several published outputs from one source.
    for parent_label, outputs in MULTI_OUTPUT.items():
        if only and only not in parent_label:
            continue
        parent = by_label.get(parent_label)
        if not parent:
            continue
        print(f"\nmulti-output: {parent_label}")
        prec = dict(parent, segments=[])
        env_coarse, _ = envelopes(Path(parent["source_path"]), parent_label)
        for name in outputs:
            mp3 = SERMONS / f"{name}.mp3"
            if not mp3.exists():
                print(f"  {name:<40} missing"); continue
            res = align(Path(parent["source_path"]), parent_label, mp3, name + " [mp3]")
            if res["status"] != "ok":
                print(f"  {name:<40} EXCLUDED: {'; '.join(res['reasons'])}"); continue
            pin = res["offset"]
            pout = pin + round(probe_duration(mp3), 3) * (1 + res.get("drift_ppm", 0) / 1e6)
            prec["segments"].append({
                "punch_in": round(pin, 3), "punch_out": round(pout, 3),
                "derived_from": mp3.name,
                "difficulty_in": difficulty(env_coarse, pin),
                "difficulty_out": difficulty(env_coarse, min(pout, parent["source_duration"] - 0.01)),
                "validation": res,
            })
            print(f"  {name:<40} {pin:8.2f} - {pout:8.2f}  "
                  f"ncc={res['probe_ncc_min']:.2f} drift={res.get('drift_ppm',0):+.0f}ppm")
        prec["segments"].sort(key=lambda s: s["punch_in"])
        prec["validation"] = {"status": "multi-output"}
        prec["split"] = "multi-output"
        records.append(prec)

    # The two-level case, handled separately: two sessions inside one recording,
    # each with its own extraction and its own published MP3.
    parent = by_label.get(TWO_LEVEL_PARENT)
    if parent and (not only or only in TWO_LEVEL_PARENT):
        print(f"\ntwo-level case: {TWO_LEVEL_PARENT}")
        prec = dict(parent, sessions=[], segments=[])
        env_coarse, _ = envelopes(Path(parent["source_path"]), TWO_LEVEL_PARENT)
        for child_label in TWO_LEVEL_CHILDREN:
            child = by_label.get(child_label)
            if not child:
                continue
            sess = align(Path(parent["source_path"]), TWO_LEVEL_PARENT,
                         Path(child["source_path"]), child_label)
            entry = {"label": child_label, "kind": "session", "validation": sess}
            if sess["status"] == "ok":
                entry["start"] = round(sess["offset"], 3)
                entry["end"] = round(sess["offset"] + child["source_duration"], 3)
                print(f"  session {child_label:<34} {entry['start']:8.2f} – {entry['end']:8.2f}")
            else:
                print(f"  session {child_label:<34} EXCLUDED: {'; '.join(sess['reasons'])}")
            prec["sessions"].append(entry)

            if child["mp3_path"]:
                seg = align(Path(parent["source_path"]), TWO_LEVEL_PARENT,
                            Path(child["mp3_path"]), child_label + " [mp3]")
                if seg["status"] == "ok":
                    pin = seg["offset"]
                    pout = pin + child["mp3_duration"] * (1 + seg.get("drift_ppm", 0) / 1e6)
                    prec["segments"].append({
                        "punch_in": round(pin, 3),
                        "punch_out": round(pout, 3),
                        "derived_from": Path(child["mp3_path"]).name,
                        "within_session": child_label,
                        "difficulty_in": difficulty(env_coarse, pin),
                        "difficulty_out": difficulty(env_coarse, pout),
                        "validation": seg,
                    })
                    print(f"  segment {child_label:<34} {pin:8.2f} – {pout:8.2f}")
                else:
                    print(f"  segment {child_label:<34} EXCLUDED: {'; '.join(seg['reasons'])}")
        prec["validation"] = {"status": "two-level"}
        prec["split"] = "two-level"
        records.append(prec)

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "method": {
            "coarse_hz": COARSE_HZ, "fine_hz": FINE_HZ,
            "probe_seconds": PROBE_S, "probe_positions": list(PROBE_AT),
            "gates": {
                "min_coarse_ncc": MIN_COARSE_NCC,
                "min_coarse_peak_ratio": MIN_COARSE_RATIO,
                "min_probe_ncc": MIN_PROBE_NCC,
                "max_fit_residual_s": MAX_FIT_RESIDUAL_S,
                "max_drift_ppm": MAX_DRIFT_PPM,
            },
        },
        "recordings": records,
    }
    path = DATA / ("groundtruth.json" if not only else "groundtruth.partial.json")
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {path}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="substring of a Desktop label, for a quick check")
    ap.add_argument("--refresh-bucket", action="store_true")
    args = ap.parse_args()
    run(args.only, args.refresh_bucket)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
