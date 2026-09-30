# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

## What this project is

A system that finds the sermon inside a recorded church service, lets one person
review and approve the cut, and renders an MP3. Read `STATE.md` first — it is the
handoff and it is kept current.

`features/` is **the specification and the test suite**, 466 Gherkin scenarios.
`experiments/` is a **frozen record** of the spike that proved the approach; every
number in `FINDINGS.md` traces to the code there.

## Build & Test

```bash
uv venv --python 3.13 && uv pip install -e ".[dev]"  # python3 on PATH is out of range
.venv/bin/python -m pytest tests/test_spec.py -k "<Feature or Rule title>"
.venv/bin/python features/validate_spec.py          # spec guardrail — also runs as a test
.venv/bin/python -m pytest                          # full suite: store, pipeline, harness, or before master
.venv/bin/python -m pytest --collect-only -q tests/test_spec.py   # 610 tests (Outlines expand)
bd ready                                            # what to work on next
```

For a feature-file change, run that file's scenarios, `validate_spec.py`, and
unit tests for modules you touched. Do not run a bare `pytest` on scenario work.
**A worktree needs its own `.venv`.** `uv venv --python 3.13 && uv pip install -e
".[dev]"` inside it. The repo-root venv cannot serve a worktree: its editable
install resolves `sermon` to the primary tree's `src/`, so tests would pass
against code you are not editing. Pipeline tests also need
`SERMON_SPIKE_DATA=<primary tree>/experiments/data`, and `experiments/baseline.py`
needs `--data` pointing there, because `blocks/`, `transcripts/` and
`diarization/` are gitignored and exist only in the primary tree.

## Running it

Every command reads the gitignored `.env` in the working directory, and a
variable already set in the environment wins over the file.

```bash
.venv/bin/sermon-reconcile   # scan the bucket; prints what it found, exit 1 on failure
.venv/bin/sermon-serve       # serve the reviewer's app; SERMON_BIND_HOST, SERMON_PORT
.venv/bin/sermon-work        # drain the job queue; --once, --limit N, --poll SECONDS
.venv/bin/sermon-fetch recordings/recording_20260823_103015.flac
.venv/bin/sermon-organize    # move an old data root onto the layout; --dry-run reports only
.venv/bin/sermon-render recording_20260823_103015 \
    --from 2:00:20 --to 2:43:32 --label "Hebrews 12.4-11" --date 2026-08-23
.venv/bin/sermon-propose recording_20260412_102318 --corpus experiments/data
.venv/bin/sermon-regrade --corpus experiments/data   # grade every proposal against the human cut
.venv/bin/sermon-regrade --corpus experiments/data --before tests/pipeline_boundary_fingerprint.json
.venv/bin/sermon-analyze recording_20260712_103000 --corpus experiments/data --summaries none
.venv/bin/sermon-align recording_20260927_095721 "~/Desktop/Sermons/2026-09-27 - Hebrews 13.7-8.mp3" \
    --source "~/Desktop/Sermons/2026-09-27 - Hebrews 13.7-8.flac"
```

`sermon-reconcile` lists the bucket and downloads nothing. `sermon-serve` binds
the tailnet address by default; `SERMON_BIND_HOST=127.0.0.1` reaches it locally.

`sermon-work` is the only thing that runs queued work. Nothing else drains the
queue — not the server, not any other command — so without it a webhook's
download, an approval's render and every analyze job sit in `queued` forever. It
recovers first: a job left `running` by a crash or a restart returns to `queued`
without a second job being enqueued and without refunding the attempt it spent.
**`--once` runs a single job**, because the queue holds 93 downloads against a
read-only 39 GiB bucket and draining it must never be one keystroke. It handles
analyze jobs only when given `--corpus`, since analysis still reads its
transcript from a corpus directory.

`sermon-organize` is the only command that rewrites stored rows. It moves a data
root laid out by whoever wrote to it first onto the layout `ARCHITECTURE.md`
describes — sources under `recordings/<id>/source.flac`, rendered MP3s under
`published/`, the pipeline's `diarization` root under `corpus/` — moving each file
and then rewriting its row, so an interruption leaves a row naming a missing file
that a re-run repairs rather than a file nothing can find. It is idempotent: a
second run prints only `in place`. `--dry-run` reports the whole move and touches
nothing. It exits non-zero if it refused anything.

`sermon-fetch` streams **one** named object into the data root and measures it,
printing duration, channels, sample rate, loudness, true peak and a level per
channel. Either an object key or a recording id names it.

`sermon-propose` drives the analysis stages over a transcript already on disk —
blocking, classification, summarisation, proposal, boundary refinement, scoring —
and prints the proposed punch-in and punch-out with the signed error in seconds
against `experiments/data/groundtruth.json` and the difficulty each boundary
carries. It sends no audio anywhere and invokes no transcriber. `--corpus` points
at the tree holding `transcripts/`, `blocks/`, `diarization/` and
`groundtruth.json`; `--summaries none` skips the per-block summary calls;
`--store` puts the Blocks, Segments and Proposals somewhere other than the data
root. It exits non-zero when a labelled Segment was not found.

`sermon-regrade` grades a proposed cut by **which silence run it lands in**
rather than by how many seconds it is out. A silence run is a gap of at least
1.0 s between consecutive words, plus the region before the first word and after
the last; two cuts inside one run are *the same cut* however many seconds apart
they are, while one second across a word is a different cut. So the headline per
cut point is whether the proposal is in the same run as the human cut, and when
it is not, how many **speech-seconds** lie between the two. The signed delta is
reported and decides nothing.

It re-derives every tagged block file under `--corpus` through the live
`derive()` and `choose()` and has three modes:

- **By default it measures accuracy** against `groundtruth.json`, pairing each
  proposal to a human segment by maximum overlap the way `sermon-propose` does,
  and prints a row per labelled cut point plus a summary. It exits non-zero only
  when nothing could be scored at all: the corpus holds deliberately bad ladder
  rungs, so a count of proposals that missed their labelled segment is data
  rather than a fault.
- **`--before <path>` grades a code change.** It scores a saved set of
  proposals and the live ones against the same human cuts and reports, per cut
  point, whether the change moved the cut closer to or further from the human —
  `improved`, `degraded`, `same cut` or `equal`. **It exits non-zero when any cut
  degraded**, and that is the regression gate. `--save <path>` writes the live
  proposals in the same shape, and `tests/pipeline_boundary_fingerprint.json`
  can be handed straight to `--before` because it already records what the
  current code produces.
- **`--drift` compares the block files' own stored `segments` field against live
  output.** That is *drift, not accuracy*: nine of those fields predate the
  current `segments.py` (`sp-66k`), so drift is expected on an unchanged tree and
  **never decides the exit code.**

**A recording the human archived whole is not graded as a cut.** A members
meeting is converted whole — "it's a members meeting so we don't really make any
cuts we just archive the whole thing usually" — so its labelled span *is* the
file, and there is no boundary decision in it to be right or wrong about. Both
modes that read `groundtruth.json` leave it out, keyed on the labelled span
covering more than 95% of the source, which is the coverage the ground-truth
checker already flags an untrimmed archive by. `recording_20260628_130014` is the
only one in the corpus and grading it cost an hour chasing a phantom regression.
**Excluding it moves every corpus-wide figure**: 158 proposals / 340 cut points
becomes 147 / 318, and `--tag whole.v2` 112 / 238 becomes 106 / 226. Read older
numbers against the older baseline.

`--tag <text>` restricts every mode to the tags containing it, which is how to
look at the shipping `*.whole.v2` configs alone. It reads the corpus and writes
nothing to it, sends no audio anywhere, and invokes neither a transcriber nor a
classifier, so it needs no `.env` and no model host.

`sermon-analyze` is `sermon-propose` without the corpus grading and with the
store the server reads: it registers the Recording from the stored transcript,
queues an `analyze` job for it, drains that one job through the same analysis
stages, and leaves the Blocks, the Segment, the Proposal and the reviewer
notification in the configured data root with the Recording `awaiting_review`.
One recording id per invocation. It exits non-zero when nothing was proposed.

`sermon-align` turns one human edit into ground truth. It finds where a published
MP3 sits inside its Recording's source, writes one `CorpusPair` row, and prints
the boundaries, the correlation, the drift and the difficulty of each cut. That is
the loop that had been open: the edit is made by hand about once a week and none
of it became measurable data, so `corpus_pair` was empty and the frozen 39-example
corpus in `experiments/data/groundtruth.json` was the only yardstick there was.

**It exits non-zero and derives no boundaries when the alignment is not
trustworthy, and it records the exclusion.** One `CorpusPair` row per named
recording carries the verdict, no boundaries and no difficulties, so a refused
pair is on the record instead of being re-attempted forever, and
`CorpusPair.labelled` keeps it out of ground truth. Five gates decide: coarse correlation at least 0.30, a peak standing 1.5× above
the next alignment, probe correlation at least 0.30, probes within 0.06 s of a
straight line, and fitted drift under 400 ppm. A row that is silently wrong
poisons every later measurement and nothing downstream would catch it, because on
disk a wrong row looks exactly like a right one. The refusal names which gate
failed and whether the verdict is `cannot be aligned` or `not a contiguous
excerpt` — the second is what probes off a straight line mean, and it is the one
diagnosis worth telling apart, since drift is correctable and a missing middle is
not.

The punch-in is the **intercept** of the fit through five 60-second probes, not
the average of them, and the punch-out is the punch-in plus the edit's duration
scaled by the fitted drift. On 2026-09-27 that is punch-in 3055.0258 s, punch-out
5597.3500 s, coarse NCC 0.986, peak ratio 13.72, fit residual 0.0004 s, drift
−0.2 ppm, difficulty easy/easy — the same figures the spike's `align.py` produced
for that pair, which is how the port is known to be faithful.

**A machine cut is never a yardstick.** Before any audio is read the command asks
whether the output is the system's own answer: a published Artifact rendered from
boundaries the reviewer never moved, or one of the three filenames that shipped
before provenance was stored. Either way it records the pair as published with
`machine` provenance and no boundaries, and exits 0. The output is counted and it
is not truth.

**One edit can span two source recordings**, so the command takes more than one
recording id, in source order, and writes one row for each. The head of the edit
places in the first source, where that source runs out sets the split, and each
side is fitted and gated on its own probes. If either side fails, or if the edit
stops short of the first source's end — which would mean the seam is a human cut
rather than a file boundary — both are refused and both are recorded as
`cannot be aligned`, including a side that placed on its own probes.
`2026-07-18 - CT-Islam.mp3` is refused for a third reason: the human removed about
177 s from inside the first part, so it is three contiguous excerpts and a
`CorpusPair` holds one span per recording. That refusal is now stored, so the
pair is not tried again blindly.

`--source` names a source that is on disk but outside the data root, which is the
shape every historical `~/Desktop/Sermons` pair is in; one `--source` per named
recording. `--classification` is how one recording yields both a class and a
sermon, since the pair is identified by recording, classification and provenance
together. `--work` holds the cached envelopes, which are what survive the decode;
the raw audio is deleted as soon as the envelopes exist. It sends no audio
anywhere and invokes no transcriber.

**An approval feeds the corpus.** Approving a Segment whose `boundary_source` is
`human` writes the labelled pair, so a boundary the reviewer moved becomes
ground truth without `sermon-align` being run by hand. An approval the reviewer
did not touch writes nothing: it is the machine's own answer, and it is recorded
as a `machine` pair by `sermon-align` once the output has been rendered.

`sermon-render` is the whole cut in one command: it fetches and probes the source
if it is not already local, creates the Segment from the boundaries you gave it,
approves it, renders the MP3, and prints what the output achieved against every
published target. **It exits non-zero when a target was missed** and the MP3 is
still written — the process it replaces shipped 9 LU quiet without anyone
noticing, so an off-target render must not read as a success. `--date` defaults to
the recorded date.

## Where the work is now, and what that means for choices

The foundations are done: the harness over all 610 scenarios, the store, config,
and the validated pipeline extracted and provably unchanged. **Almost nothing is
implemented** — the spec is still overwhelmingly Red, and turning it green is the
only work that now matters.

Four rules follow from that, and they override the instinct to be thorough:

**Scenarios pull the model, not the other way round.** An exhaustive audit of all
460 scenarios already listed every gap between the spec and `features/DOMAIN.md`,
so the unknowns are known and finite. Closing the rest speculatively is the wrong
order. Add a field when a scenario being implemented needs it.

**No more machinery.** The store already has generated DDL, a `Presence`
primitive, closed vocabularies and canonical digests — for 39 recordings at about
one a week, with one reviewer. That is paid for and it caught two data-corruption
bugs, so it stays. But every *new* abstraction has to justify itself against
"39 recordings, ~1/week", and most cannot.

**The target is the three-click week**, the thing the spec itself names: a
recording appears, the pipeline analyses it, a reviewer previews punch-in and
punch-out, approves, an MP3 lands. One path through ingestion, analysis, review
and processing. It tells you which open beads actually matter; until it exists,
none of them provably do.

**143 Rules is not a plan.** One bead per Rule is roughly 142 beads and more
tokens than any single budget. Implement the vertical slice, then widen. One
feature file per bead; serial the three-click chain; parallel only true siblings.
Scenario work is reviewed by mutating the new assertions, not by the
eight-concern reviewer.

## Architecture

`ARCHITECTURE.md` is authoritative. In one line: Python throughout, the validated
pipeline as a package, Flask as a thin API, a `Job` table rather than a broker,
SQLite and files, a vanilla ES-modules client, reasoning on mac-m1 over HTTP.

## Conventions

These are inherited from `~/Source/launch-supply/silo/global/adrs/foundations/`
and recorded in `CONVENTIONS.md` with the reasoning. The short form:

### Tests come first (ADR-LS-001)

Red, Green, Refactor, in that order, with granular commits tagged `[AI]`.

**In the Red phase the test must FAIL, not ERROR.** An error means the harness is
wrong, not that the behaviour is missing — fix the setup and get a real failure
before writing implementation.

The scenarios already exist, so Red usually means writing step definitions for a
scenario and watching it fail for the right reason.

### Comments are a last resort (ADR-LS-004)

**Zero new comments is the expected outcome of a change.** Before writing one,
try: rename it, extract it, make the mistake impossible with a type or guard,
write a test. Only if all four fail does a comment earn its place.

A permitted comment carries **only the fact the reader needs** — one line, three
at the absolute ceiling. No dates, no first person, no narrative, no discovery
story, no "Measured on…". The justification goes in the commit message, never in
the comment.

Rationale has homes that are not the source: a number and where it came from goes
in `experiments/FINDINGS.md`; why the system is shaped this way goes in
`ARCHITECTURE.md`; what it must do goes in `features/`.

### The spec is the primary artifact

It is deliberately language-agnostic so a rewrite in another language needs
nothing else. Two consequences:

- **Step definitions carry no logic.** A step translates English into a call and
  asserts on the result. Anything else belongs in `src/sermon/`.
- **Scenarios name what the system talks to, never what it is built with.** HTTP,
  S3, ffmpeg, ollama, a tailnet: fine. Flask, SQLite, Python, pytest: not in a
  scenario. Technology names are allowed in comments, where they cite measurements.

`features/validate_spec.py` enforces the second and fails the build otherwise.

### Naming

One operation per unit, named as a third-person singular verb phrase —
`ProposesSegments`, `RendersSegment`, `ReconcilesBucket`. Not `SegmentProposer`,
not a module of loose functions. Dependencies injected with defaults so a test can
substitute the model host or the clock without patching globals.

### Beads: depend on children, never on an epic

A bead that depends on an **epic** is hostage to that epic's least related child.
The P0 pipeline extraction sat invisible to `bd ready` for nine iterations because
it depended on the Foundations epic, which stayed open for a Dockerfile bead and
two P3 nitpicks it did not need. Depend on the specific beads whose output you
consume.

The same rule in reverse: **`bd ready` is not the whole picture.** It shows
unblocked leaves, so higher-priority work can be hidden behind bookkeeping.
Inspect the blocked set periodically for work whose blocker is not substance.

### A Minor finding is not automatically a bead

Filing every review nitpick produced a 66-item P3 queue nobody will work, which
obscures the path rather than protecting it. File a Minor finding only if it
**blocks something, will cost real time later, or is a correctness risk someone
could trip over.** A redundant subprocess, a noun-phrase helper name, a duplicated
constant: note it in the close reason and move on. Beads are for work that will
actually be done.

### DOMAIN.md cites what the Gherkin says, never an inference

Three times this document attributed a conclusion to a scenario that the scenario
did not state — "they coincide when a Segment is first made", "the scenario leaves
a `reviewed` Recording `reviewed`", and a citation that no longer supported its
field. Each inference was sound; the phrasing claimed it was quoted. Cite the
clause, and mark reasoning as reasoning. This document is what a rewrite in
another language would lean on.

### Worktrees (ADR-LS-002)

Parallel or long-running work gets its own worktree: `worktrees/<name>`, branch
`tpett/ai/<name>`. Small fixes may go straight to the working tree — ask first.

## Things that will bite you

- **`~/Desktop/Sermons` is the only copy of the ground truth.** Read-only except
  for adding new source/edit pairs.
- **`s3://reformation-recordings/` is read-only.** List and download named
  objects; never put, never delete, never pull the whole 36 GB bucket.
- **No audio leaves the machine.** Ever, to anything.
- **`experiments/` is frozen.** It is the record of how the numbers were made. Do
  not refactor it or hold it to the TDD cycle retroactively.
- **The pipeline is extracted and guarded by three instruments. Run all three
  before and after touching `src/sermon/pipeline/`:** `experiments/baseline.py`
  (stored-artefact drift, exit 0/1/2), `tests/test_pipeline_library.py` (re-derives
  all 181 stored block files; needs primary data via `SERMON_SPIKE_DATA`), and
  `tests/test_pipeline_behaviour.py` (the other seven modules). Each is needed:
  the first never executes the pipeline, and before the third existed, gutting
  `blocks.speech_runs` to `raise` left the whole suite green.
- **Never run `rederive.py` against `experiments/data`.** It rewrites
  `blocks/` in place, and those 181 files *are* the extraction baseline.
- **A `__file__`-relative path is how a verbatim move stops preserving behaviour.**
  The pipeline's data roots are injected — `segments.DATA_ROOT`, `classify.DATA`,
  `classify.PROMPTS` — and an unset one fails loudly naming module and setting.
- **After any change to `pyproject.toml` dependencies, run
  `uv pip install -e ".[dev]"` in the root venv before trusting the suite.** A
  stale venv once read as a merge regression (598 failed rather than 597).
- **Sweeping `experiments/` wholesale reads the spike's own venv.** Scan
  first-party source only; `experiments/.venv` holds a Python 2 file that
  `ast.parse` rejects, and `experiments/work/models/` holds downloaded scripts.
- **Never send `format: json` to an MLX-backed ollama model.** 0.34.0 answers
  HTTP 501 `structured output is unavailable`. Unconstrained also scores better.
- **`experiments/data/test_access.log` records every held-out scoring run.** One
  shot per configuration; honour it.
- **Some published MP3s are machine cuts, not human edits.** `align.MACHINE_CUT_MP3S`
  excludes them from ground truth. Add to that set whenever a proposal ships
  unedited, or the corpus starts grading itself.

### The pins have moved twice, on purpose

The harness pins were **34 files / 460 scenarios / 142 rules / 604 collected**.
On 2026-09-22 the user asked for a visual indicator of the cut instant during a
preview — "we need a visual indicator when the cut happens when previewing it so
that I can tell if it's the right point or not". Nothing in the spec said the
boundary is marked *while* it is auditioned: `Auditioning a boundary` gave the
5-seconds-either-side window and `Playing from anywhere` gave a playhead, but a
punch-in half a second late sounds like a clean one if the reviewer cannot see
which instant was the cut. So `The cut is marked while I audition it` was added
to `features/interface/waveform_review.feature`.

On the same day they asked for the instant itself to be shown: "come up with a
way to show the precise moment the cut happens during the preview. Like a cut
light or other visual indicator." That is a different affordance from a mark on
the waveform — it is read while listening rather than looked at — so
`A cut light shows the exact instant` was added beside it.

On 2026-09-24 they asked for a way to reclassify a Segment after it is created:
the classification picks the intent a Segment is approved with, so one called
anything but a sermon defaults to archive rather than publish, and nothing could
correct the machine's guess. `Correcting what the machine decided a Segment is`
and `A Segment that has been approved keeps its classification` were added to
`features/interface/segment_review.feature`.

On 2026-09-27 they asked to be able to refresh the list by hand: nothing scans
the bucket on a schedule and the webhook is still to come, so a recording that
has just landed is invisible and cannot be ingested at all. `Scanning the bucket
on demand` and `Asking for a scan while the object store is unreachable` were
added to `features/ingestion/s3_reconciliation.feature`.

On 2026-09-29 they said what manual editing still lacks: "The ability to fine
tune scrub is probably the biggest lack. slight zoom in/out using some hotkeys
would be huge too. Much like how Audacity works. I use CMD-1 and CMD-3 to zoom
in/out respectively. Then I can click anywhere in the timecode timeline to jump
the playhead there. If I could do this and also have a quick punch-in/out button
available by the waveform (not burried in a lower card) that would probably give
me what I need for manual editing."

Three of those four were absent from the spec. Nothing said the *playhead* could
be moved by hand or by key — `Nudging with keyboard controls` moves a boundary,
which is a different act — so `Scrubbing the playhead to a precise instant` was
added. `Playing from anywhere` makes the waveform seek and `Moving around from
the overview` moves the window without seeking; the ruler was a third surface
that did neither, so `Jumping the playhead from the timecode ruler` was added.
`Zoom is chosen from named steps` named the steps but no keystroke reached them,
so `Zooming in and out from the keyboard` was added. All three are in
`features/interface/waveform_review.feature`.

The fourth was a placement, not a behaviour: `Setting a boundary from the
playhead` already existed and only the lower card offered it, so `Punching a
boundary in from beside the waveform` was added to
`features/interface/punch_point_adjustment.feature` asserting where the control
sits.

Pins are now **34 files / 470 scenarios / 144 rules / 614 collected**, and
`SPEC_STEPS` is 1942.

`tests/test_spec_harness.py` asserts all of these, in `SPEC_SHAPE`, `SPEC_TESTS`
and `SPEC_STEPS`. Grepping the repository for the literal numbers does not find
them, which is how this file came to disagree with the harness once: a merge
resolved with `-X theirs` took a branch's older copy of this section and reverted
it silently while the tests stayed green on the newer values. Change both
together.

A pin moves only when the product owner asks for something the spec does not
cover, and the move is recorded here with the words that prompted it. An agent
that finds the count different from what its instructions said should check this
section before assuming it broke something.
