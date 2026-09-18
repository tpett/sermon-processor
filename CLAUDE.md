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
pytest                                  # the suite is features/, via pytest-bdd
pytest --collect-only -q                # 604 tests expected (Outlines expand)
python3 features/validate_spec.py       # spec portability guardrail — must pass
bd ready                                # what to work on next
```

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
- **Extracting `experiments/src` must be provably behaviour-preserving.** Re-derive
  and re-score against a frozen baseline; identical or revert. Never combine that
  move with refactoring or comment cleanup.
- **Never send `format: json` to an MLX-backed ollama model.** 0.34.0 answers
  HTTP 501 `structured output is unavailable`. Unconstrained also scores better.
- **`experiments/data/test_access.log` records every held-out scoring run.** One
  shot per configuration; honour it.
- **Some published MP3s are machine cuts, not human edits.** `align.MACHINE_CUT_MP3S`
  excludes them from ground truth. Add to that set whenever a proposal ships
  unedited, or the corpus starts grading itself.
