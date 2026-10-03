"""Whether a change moves production's first proposal toward the human cut or away from it.

The live proposals come from replaying production's analyze job; the reference is a
stored snapshot of the same replay, which moves only by an acceptance that records
its reason, the commit and the judge it was taken under. Both are judged against the
human cut by `judges_cut`, recording by recording, on production's configuration and
the dev split unless asked otherwise.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sermon.analysis.judges_cut import (
    BETTER,
    JUDGE_DIGEST,
    UNCHANGED,
    WORSE,
    JudgesCut,
    archived_whole,
    compares,
    pairs,
)
from sermon.analysis.replays_shipping_walk import ProposedCut, ReplaysShippingWalk

PRODUCTION_TAG = "fw-qwen3.6.whole.v2"
SEEN_SPLIT = "dev"
MIXED = "mixed"
BOUNDARIES = ("punch_in", "punch_out")

PASSED = "passed"
WORSENED = "worsened"
CANNOT_GATE = "cannot gate"


class HeldOutSealed(PermissionError):
    pass


def describes_commit():
    try:
        found = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return found.stdout.strip() or "unknown"


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Baseline:
    judge: str
    proposals: dict
    accepted: tuple


def reads_baseline(path):
    path = Path(path)
    if not path.is_file():
        return None
    held = json.loads(path.read_text())
    return Baseline(
        judge=held["judge"],
        proposals={
            name: tuple(ProposedCut(**cut) for cut in cuts)
            for name, cuts in held["proposals"].items()
        },
        accepted=tuple(held.get("accepted") or ()),
    )


def block_files(corpus_root):
    return sorted((Path(corpus_root) / "blocks").glob("*.json"))


@dataclass(frozen=True)
class Acceptance:
    moved: tuple
    refused: str | None = None


@dataclass(frozen=True)
class AcceptsBaseline:
    corpus_root: Path
    path: Path
    replays: object | None = None
    describes_commit: object = describes_commit
    clock: object = now

    def __call__(self, reason):
        if not reason or not reason.strip():
            raise ValueError("an acceptance must say why the reference is moving")
        replays = self.replays or ReplaysShippingWalk(corpus_root=self.corpus_root)
        live = {}
        for path in block_files(self.corpus_root):
            found = replays(path)
            if found is not None:
                live[found.name] = found.proposals
        standing = reads_baseline(self.path)
        moved = tuple(
            sorted(
                name
                for name in live
                if standing is None or standing.proposals.get(name) != live[name]
            )
        )
        if standing is not None and standing.judge != JUDGE_DIGEST and moved:
            return Acceptance(
                moved=moved,
                refused=(
                    f"the judge changed ({standing.judge} -> {JUDGE_DIGEST}) and {len(moved)} "
                    "proposals moved; accept the judge on an unchanged pipeline first"
                ),
            )
        history = list(standing.accepted if standing else ())
        history.append(
            {
                "at": self.clock(),
                "commit": self.describes_commit(),
                "judge": JUDGE_DIGEST,
                "moved": len(moved),
                "reason": reason.strip(),
            }
        )
        Path(self.path).write_text(
            json.dumps(
                {
                    "judge": JUDGE_DIGEST,
                    "accepted": history,
                    "proposals": {
                        name: [cut.__dict__ for cut in cuts] for name, cuts in sorted(live.items())
                    },
                },
                indent=1,
                sort_keys=True,
            )
            + "\n"
        )
        return Acceptance(moved=moved)


@dataclass(frozen=True)
class RecordsHeldOutRead:
    path: Path
    clock: object = now
    describes_commit: object = describes_commit

    def __call__(self, reason, tag, splits):
        if not Path(self.path).parent.is_dir():
            raise HeldOutSealed(f"nowhere to record a held-out read: {self.path}")
        with Path(self.path).open("a") as log:
            log.write(
                f"{self.clock()}\t{self.describes_commit()}\t{tag}\t{','.join(splits)}\t"
                f"judge {JUDGE_DIGEST}\t{reason.strip()}\n"
            )


@dataclass(frozen=True)
class JudgedCut:
    boundary: str
    human: float
    before: object
    after: object

    @property
    def verdict(self):
        return compares(self.before, self.after)


@dataclass(frozen=True)
class JudgedRecording:
    recording_id: str
    label: str
    split: str
    tag: str
    cuts: tuple
    unpaired_before: int
    unpaired_after: int

    @property
    def verdict(self):
        verdicts = {cut.verdict for cut in self.cuts}
        if self.unpaired_after != self.unpaired_before:
            verdicts.add(WORSE if self.unpaired_after > self.unpaired_before else BETTER)
        if WORSE in verdicts:
            return MIXED if BETTER in verdicts else WORSE
        return BETTER if BETTER in verdicts else UNCHANGED


@dataclass(frozen=True)
class GateReport:
    tag: str
    splits: tuple
    recordings: tuple
    not_in_baseline: tuple
    baseline_judge: str
    accepted: tuple

    @property
    def judge_changed(self):
        return self.baseline_judge != JUDGE_DIGEST

    @property
    def counts(self):
        found = {BETTER: 0, WORSE: 0, MIXED: 0, UNCHANGED: 0}
        for one in self.recordings:
            found[one.verdict] += 1
        return found

    @property
    def outcome(self):
        if not self.recordings or self.judge_changed:
            return CANNOT_GATE
        counted = self.counts
        return WORSENED if counted[WORSE] or counted[MIXED] else PASSED


@dataclass(frozen=True)
class GatesShippingCuts:
    corpus_root: Path
    baseline: Baseline
    replays: object | None = None
    tag: str = PRODUCTION_TAG
    splits: tuple = (SEEN_SPLIT,)
    unsealed: str | None = None
    records: object | None = None

    def __call__(self):
        sealed = [split for split in self.splits if split != SEEN_SPLIT]
        if sealed:
            if not self.unsealed or not self.unsealed.strip() or self.records is None:
                raise HeldOutSealed(
                    f"the {', '.join(sealed)} split is held out; it is read only when unsealed "
                    "with a reason, and the read is recorded"
                )
            self.records(self.unsealed, self.tag, self.splits)
        replays = self.replays or ReplaysShippingWalk(corpus_root=self.corpus_root)
        labelled = self._labelled()
        judged, missing = [], []
        for path in block_files(self.corpus_root):
            recording_id = path.name.split(".", 1)[0]
            if path.name != f"{recording_id}.{self.tag}.json" or recording_id not in labelled:
                continue
            if path.name not in self.baseline.proposals:
                missing.append(recording_id)
                continue
            found = replays(path)
            if found is None:
                continue
            judged.append(
                self._judges(
                    labelled[recording_id],
                    path,
                    self.baseline.proposals[path.name],
                    found.proposals,
                )
            )
        return GateReport(
            tag=self.tag,
            splits=tuple(self.splits),
            recordings=tuple(judged),
            not_in_baseline=tuple(missing),
            baseline_judge=self.baseline.judge,
            accepted=self.baseline.accepted,
        )

    def _labelled(self):
        held = json.loads((Path(self.corpus_root) / "groundtruth.json").read_text())
        return {
            entry["recording_id"]: entry
            for entry in held["recordings"]
            if entry.get("split") in self.splits
            and entry.get("segments")
            and not archived_whole(entry)
        }

    def _judges(self, labelled, path, before, after):
        stored = json.loads(path.read_text())
        transcript = json.loads(
            (
                Path(self.corpus_root)
                / "transcripts"
                / f"{labelled['recording_id']}.{stored['asr_config']}.json"
            ).read_text()
        )
        judges = JudgesCut(transcript=transcript)
        cuts, paired_before, paired_after = [], set(), set()
        for human in labelled["segments"]:
            was = pairs([(cut.punch_in, cut.punch_out) for cut in before], human)
            now = pairs([(cut.punch_in, cut.punch_out) for cut in after], human)
            paired_before.add(was)
            paired_after.add(now)
            for index, boundary in enumerate(BOUNDARIES):
                cuts.append(
                    JudgedCut(
                        boundary=boundary,
                        human=human[boundary],
                        before=judges(was[index] if was else None, human[boundary]),
                        after=judges(now[index] if now else None, human[boundary]),
                    )
                )
        return JudgedRecording(
            recording_id=labelled["recording_id"],
            label=labelled.get("desktop_label") or labelled["recording_id"],
            split=labelled.get("split"),
            tag=self.tag,
            cuts=tuple(cuts),
            unpaired_before=_unpaired(before, paired_before),
            unpaired_after=_unpaired(after, paired_after),
        )


def _unpaired(proposals, paired):
    return sum((cut.punch_in, cut.punch_out) not in paired for cut in proposals)
