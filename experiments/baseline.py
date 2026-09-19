from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "extraction-baseline/1"
DATA = Path(__file__).resolve().parent / "data"
BASELINE = DATA / "extraction-baseline.json"

DERIVED = ("blocks", "transcripts", "diarization")
VALUED = ("segments", "derived_segments", "block_spans", "lines")
CANONICAL_FILES = ("groundtruth.json",)
LITERAL_FILES = ("bucket.txt", "test_access.log")
SIZED = {
    "results_rows": "results",
    "block_files": "blocks",
    "transcript_files": "transcripts",
    "diarization_files": "diarization",
}


class BaselineUnusable(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    scope: str
    kind: str
    detail: str

    def __str__(self):
        return f"{self.scope}: {self.kind}: {self.detail}"


def renders_canonically(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digests(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reads_result_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarises_json(path):
    parsed = json.loads(path.read_text())
    return {"digest": digests(renders_canonically(parsed)), "bytes": path.stat().st_size}


def summarises_block(path):
    parsed = json.loads(path.read_text())
    summary = summarises_json(path)
    summary["fields"] = {
        field: digests(renders_canonically(value)) for field, value in parsed.items()
    }
    summary["block_spans"] = [
        [block.get("start"), block.get("end"), block.get("type")]
        for block in parsed.get("blocks", [])
    ]
    for field in ("segments", "derived_segments"):
        summary[field] = parsed.get(field)
    return summary


def summarises_literally(path):
    raw = path.read_bytes()
    return {
        "digest": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "lines": raw.decode("utf-8").count("\n"),
    }


def counts_derived(root, name, summarises):
    directory = root / name
    if not directory.is_dir():
        raise BaselineUnusable(f"there is no {name} directory under {root}")
    return {path.name: summarises(path) for path in sorted(directory.glob("*.json"))}


@dataclass(frozen=True)
class CapturesBaseline:
    data_root: Path

    def __call__(self):
        if not self.data_root.is_dir():
            raise BaselineUnusable(f"there is no data root at {self.data_root}")
        try:
            rows = reads_result_rows(self.data_root / "results.jsonl")
            captured = {
                "schema": SCHEMA,
                "results": rows,
                "blocks": counts_derived(self.data_root, "blocks", summarises_block),
                "transcripts": counts_derived(self.data_root, "transcripts", summarises_json),
                "diarization": counts_derived(self.data_root, "diarization", summarises_json),
                "files": {
                    **{name: summarises_json(self.data_root / name) for name in CANONICAL_FILES},
                    **{name: summarises_literally(self.data_root / name) for name in LITERAL_FILES},
                },
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as failure:
            raise BaselineUnusable(
                f"{self.data_root} cannot be captured: {type(failure).__name__}: {failure}"
            ) from failure
        captured["counts"] = counts_of(captured, rows)
        validates_baseline(captured)
        return captured


def counts_of(captured, rows):
    splits = {}
    for row in rows:
        splits[row["split"]] = splits.get(row["split"], 0) + 1
    return {
        "results_rows": len(rows),
        "result_configs": len({row["config_id"] for row in rows}),
        "result_recordings": len({row["recording_id"] for row in rows}),
        "result_splits": dict(sorted(splits.items())),
        "block_files": len(captured["blocks"]),
        "block_configs": len({name.split(".", 1)[1] for name in captured["blocks"]}),
        "transcript_files": len(captured["transcripts"]),
        "diarization_files": len(captured["diarization"]),
        "access_log_lines": captured["files"]["test_access.log"]["lines"],
    }


def validates_baseline(baseline):
    if not isinstance(baseline, dict):
        raise BaselineUnusable("the baseline is not an object")
    if baseline.get("schema") != SCHEMA:
        raise BaselineUnusable(
            f"the baseline declares schema {baseline.get('schema')!r}, not {SCHEMA!r}"
        )
    counts = baseline.get("counts")
    if not isinstance(counts, dict):
        raise BaselineUnusable("the baseline records no counts")
    for name, collection in SIZED.items():
        held = len(baseline.get(collection) or ())
        if not held:
            raise BaselineUnusable(f"the baseline holds no {collection}")
        if counts.get(name) != held:
            raise BaselineUnusable(
                f"the baseline claims {counts.get(name)} for {name} and holds {held}"
            )
    for name in ("result_configs", "result_recordings", "block_configs", "access_log_lines"):
        if not counts.get(name):
            raise BaselineUnusable(f"the baseline records no {name}")
    missing = {*CANONICAL_FILES, *LITERAL_FILES} - set(baseline.get("files") or {})
    if missing:
        raise BaselineUnusable(f"the baseline fingerprints no {', '.join(sorted(missing))}")
    return baseline


def reads_baseline(path):
    try:
        return validates_baseline(json.loads(Path(path).read_text()))
    except OSError as unreadable:
        raise BaselineUnusable(f"{path} could not be read: {unreadable}") from unreadable
    except json.JSONDecodeError as unparseable:
        raise BaselineUnusable(f"{path} is not JSON: {unparseable}") from unparseable


def compares_fields(scope, was, now):
    findings = []
    for field in sorted({*was, *now}):
        if field not in now:
            findings.append(Finding(scope, "missing", f"the {field} field, which was {was[field]}"))
        elif field not in was:
            findings.append(Finding(scope, "unexpected", f"the {field} field, now {now[field]}"))
        elif was[field] != now[field]:
            findings.append(Finding(scope, "changed", f"the {field} field"))
    return findings


def compares_values(scope, was, now):
    findings = []
    for field in sorted({*was, *now}):
        rendered_was, rendered_now = renders_canonically(was.get(field)), renders_canonically(
            now.get(field)
        )
        if field not in now:
            findings.append(Finding(scope, "missing", f"{field} was {rendered_was}"))
        elif field not in was:
            findings.append(Finding(scope, "unexpected", f"{field} is {rendered_now}"))
        elif rendered_was != rendered_now:
            findings.append(
                Finding(scope, "changed", f"{field} was {rendered_was}, is {rendered_now}")
            )
    return findings


def compares_summary(scope, was, now):
    if was.get("digest") == now.get("digest"):
        return []
    return [
        *compares_fields(f"{scope} fields", was.get("fields") or {}, now.get("fields") or {}),
        *compares_values(
            scope,
            {field: was[field] for field in VALUED if field in was},
            {field: now[field] for field in VALUED if field in now},
        ),
        Finding(scope, "changed", f"digest was {was.get('digest')}, is {now.get('digest')}"),
    ]


def compares_derived(scope, expected, directory, summarises):
    if not directory.is_dir():
        return [
            Finding(f"{scope}/{name}", "missing", f"there is no {scope} directory")
            for name in sorted(expected)
        ]
    present = {path.name for path in directory.glob("*.json")}
    findings = []
    for name in sorted({*expected, *present}):
        where = f"{scope}/{name}"
        if name not in present:
            findings.append(Finding(where, "missing", "the artefact is not there"))
        elif name not in expected:
            findings.append(Finding(where, "unexpected", "the artefact is not in the baseline"))
        else:
            findings += reads_and_compares(where, expected[name], directory / name, summarises)
    return findings


def reads_and_compares(scope, expected, path, summarises):
    try:
        found = summarises(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as failure:
        return [Finding(scope, "unreadable", f"{type(failure).__name__}: {failure}")]
    return compares_summary(scope, expected, found)


def compares_results(expected, path):
    if not path.exists():
        return [Finding("results.jsonl", "missing", "the scored output is not there")]
    try:
        found = reads_result_rows(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as failure:
        return [Finding("results.jsonl", "unreadable", f"{type(failure).__name__}: {failure}")]
    findings = []
    if len(found) != len(expected):
        findings.append(
            Finding(
                "results.jsonl", "count", f"{len(expected)} rows were stored, {len(found)} found"
            )
        )
    for position, (was, now) in enumerate(zip(expected, found)):
        findings += compares_values(f"results.jsonl row {position}", was, now)
    return findings


def compares_files(expected, data_root):
    findings = []
    for name, summarises in (
        *((name, summarises_json) for name in CANONICAL_FILES),
        *((name, summarises_literally) for name in LITERAL_FILES),
    ):
        path = data_root / name
        if not path.exists():
            findings.append(Finding(name, "missing", "the artefact is not there"))
        else:
            findings += reads_and_compares(name, expected[name], path, summarises)
    return findings


@dataclass(frozen=True)
class ComparesBaseline:
    baseline: dict
    data_root: Path

    def __call__(self):
        validates_baseline(self.baseline)
        if not self.data_root.is_dir():
            raise BaselineUnusable(f"there is no data root at {self.data_root}")
        findings = compares_results(self.baseline["results"], self.data_root / "results.jsonl")
        for scope, summarises in zip(DERIVED, (summarises_block, summarises_json, summarises_json)):
            findings += compares_derived(
                scope, self.baseline[scope], self.data_root / scope, summarises
            )
        return findings + compares_files(self.baseline["files"], self.data_root)


def reports_drift(findings, counts):
    if not findings:
        pinned = ", ".join(f"{counts[name]} {name}" for name in SIZED)
        return f"no drift — {pinned} unchanged"
    return "\n".join(
        [*(str(finding) for finding in findings), f"DRIFT — {len(findings)} findings"]
    )


def parses_arguments(argv):
    parser = argparse.ArgumentParser(
        description="Compare the stored extraction artefacts against the committed baseline"
    )
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def captures(arguments, out):
    if arguments.baseline.exists() and not arguments.force:
        raise BaselineUnusable(
            f"{arguments.baseline} is already there; --force overwrites it and discards the proof"
        )
    captured = CapturesBaseline(data_root=arguments.data)()
    arguments.baseline.write_text(json.dumps(captured, indent=1, sort_keys=True) + "\n")
    print(f"captured {arguments.baseline}", file=out)
    print(json.dumps(captured["counts"], indent=1, sort_keys=True), file=out)
    return 0


def main(argv=None, out=None):
    out = out or sys.stdout
    arguments = parses_arguments(argv)
    try:
        if arguments.capture:
            return captures(arguments, out)
        baseline = reads_baseline(arguments.baseline)
        findings = ComparesBaseline(baseline=baseline, data_root=arguments.data)()
        print(reports_drift(findings, baseline["counts"]), file=out)
        return 1 if findings else 0
    except BaselineUnusable as unusable:
        print(f"cannot compare: {unusable}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
