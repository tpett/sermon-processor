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

`features/` is **the specification and the test suite**, 460 Gherkin scenarios.
`experiments/` is a **frozen record** of the spike that proved the approach; every
number in `FINDINGS.md` traces to the code there.

## Build & Test

```bash
uv venv --python 3.13 && uv pip install -e ".[dev]"  # python3 on PATH is out of range
.venv/bin/python -m pytest tests/test_spec.py -k "<Feature or Rule title>"
.venv/bin/python features/validate_spec.py          # spec guardrail — also runs as a test
.venv/bin/python -m pytest                          # full suite: store, pipeline, harness, or before master
.venv/bin/python -m pytest --collect-only -q tests/test_spec.py   # 604 tests (Outlines expand)
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
.venv/bin/sermon-fetch recordings/recording_20260823_103015.flac
.venv/bin/sermon-render recording_20260823_103015 \
    --from 2:00:20 --to 2:43:32 --label "Hebrews 12.4-11" --date 2026-08-23
.venv/bin/sermon-propose recording_20260412_102318 --corpus experiments/data
.venv/bin/sermon-analyze recording_20260712_103000 --corpus experiments/data --summaries none
```

`sermon-reconcile` lists the bucket and downloads nothing. `sermon-serve` binds
the tailnet address by default; `SERMON_BIND_HOST=127.0.0.1` reaches it locally.

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

`sermon-analyze` is `sermon-propose` without the corpus grading and with the
store the server reads: it registers the Recording from the stored transcript,
queues an `analyze` job for it, drains that one job through the same analysis
stages, and leaves the Blocks, the Segment, the Proposal and the reviewer
notification in the configured data root with the Recording `awaiting_review`.
One recording id per invocation. It exits non-zero when nothing was proposed.

`sermon-render` is the whole cut in one command: it fetches and probes the source
if it is not already local, creates the Segment from the boundaries you gave it,
approves it, renders the MP3, and prints what the output achieved against every
published target. **It exits non-zero when a target was missed** and the MP3 is
still written — the process it replaces shipped 9 LU quiet without anyone
noticing, so an off-target render must not read as a success. `--date` defaults to
the recorded date.

## Where the work is now, and what that means for choices

The foundations are done: the harness over all 604 scenarios, the store, config,
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

**142 Rules is not a plan.** One bead per Rule is roughly 142 beads and more
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
