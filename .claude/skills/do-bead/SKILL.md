---
name: do-bead
description: Implement one Beads issue end to end with a TDD implementer subagent, then a review path that matches the risk — mutation for scenario work, the eight-concern reviewer only for store, pipeline, or harness. Use when the user names a bead (e.g. "do sp-1vn.1", "work the next bead") or asks to start the next ready piece of work.
argument-hint: "[bead id, or omit to take the first from bd ready]"
---

# Do Bead

Take a bead — or a batch of beads that are one change — from open to closed. The
implementer is always a subagent. The reviewer is a subagent only when the risk
warrants it.

The conventions live in `CLAUDE.md` and `CONVENTIONS.md`. **Do not paste them
into a subagent prompt.** Tell the subagent which files to read, and quote only
the bead, the governing scenarios, and the comment rule.

## Input

A bead id, or nothing. With nothing, take the highest-priority item from
`bd ready` and say which one you took before starting.

## 0. Batch first — this is the largest lever there is

**Take several beads in one pass when they are one change.** Beads that touch the
same files are cheaper *and safer* together: run separately, each cycle
invalidates the next one's edits, and you pay a full implement-review-fix round
every time. Measured on this project: eight beads in one batch cost about what one
bead cost unbatched.

When implementing scenarios, **the unit of work is one feature file**, not one
scenario. Fixtures and the step-definition module are the fixed cost — amortise
them across every non-`@deferred` scenario in the file.

Batch when the beads share files, share a design decision, or would conflict.
**Do not batch** work with genuinely independent designs, a high-risk bead with
anything else, or work across layers (a Flask route and canvas client work are
separate). Do not fill a parallel slot with a file that is downstream of one
you have not finished — the three-click week is a chain; throughput of random
files is not speed on that path. Parallel only true siblings (different
step-definition directories **and** different product modules).

When you batch, say so and say why.

## 1. Read the bead and claim it

```bash
bd show <id>
bd show <id> --json
bd update <id> --claim
```

Read the **acceptance criteria** as the definition of done. If the bead has none,
derive them from the governing scenarios and say so in the close reason.

If the bead has a parent, read the parent too (`bd show <parent>`).

**Refuse to start if the bead is blocked.** `bd ready` will not offer it, but an
explicitly named id can be. Say what blocks it.

**But check whether the block is real.** If the blocker is an *epic* rather than a
specific bead, the dependency is probably wrong: an epic stays open for its least
related child. Repoint the edge at the beads whose output is actually needed
(`bd dep remove`, `bd dep add`), record why, and proceed. Do not `--force` close
an epic whose children are genuinely open.

## 2. Locate the governing spec

```bash
grep -rn "<the behaviour>" features/
```

Name the governing feature file and `Rule:` in your plan. A bead that implements
no scenario is either foundational work (scaffolding, extraction, deployment) or
a bead that should not exist — decide which and say so.

## 3. Choose the worktree

Per ADR-LS-002, parallel or long-running work gets its own worktree:

```bash
git worktree add worktrees/<bead-id> -b tpett/ai/<bead-id>
```

Use the **repo-root venv**, never install a second one:

```bash
../.venv/bin/python -m pytest …
```

(`worktrees/<name>` is one level below the root.) For a small, self-contained
bead the working tree is acceptable — **ask first**.

Implementers commit on their branch only. **You** merge into `tpett/ai/v1-build`
(never `master`), in slice order if several worktrees are in flight, so they do
not retry each other's conflicts.

## 4. Dispatch the implementer subagent

Record the baseline: `BASE_SHA=$(git rev-parse HEAD)`.

**One implementer. Wait for it. Never overlap.**

`spawn_subagent` defaults to `background: true` and returns immediately. That is
how this project got three implementers in the same worktree, a minute apart,
stomping the same bead. On Grok:

1. Call `spawn_subagent` **once** with `background: false` (it blocks until the
   child finishes). If you must use `background: true`, immediately
   `get_command_or_subagent_output` with a long timeout and **do not continue**
   until it completes or fails.
2. Do not spawn a second implementer for this bead while the first is running,
   waiting, or "Thinking". Do not retry on a snapshot. Do not interpret an
   immediate subagent id as "it didn't start".
3. Before spawning, if this worktree already has a running implementer or this
   fire already has a child id, stop — report one line and exit.

Dispatch **one** `general-purpose` subagent. Its prompt contains:

- The bead's **title, description and acceptance criteria**, verbatim.
- The **governing feature file path**, with the scenarios quoted. That file is
  the spec for this bead. Do not send `STATE.md`, `ARCHITECTURE.md`, or
  `features/DOMAIN.md` unless the bead is store work (`DOMAIN.md`), structural
  (`ARCHITECTURE.md`), or measured behaviour (`FINDINGS.md`).
- An instruction to **read** `CLAUDE.md` sections "Conventions" and "Things that
  will bite you" from disk — do not paste those sections.
- An explicit TDD instruction:

  > 1. **Red** — write the failing test (usually step definitions for a
  >    scenario). Run it. Confirm it **fails rather than errors**; an error means
  >    your harness is wrong, so fix that and get a real failure first.
  > 2. **Green** — the minimum code that passes. Run the tests for this feature
  >    file, `features/validate_spec.py`, and unit tests for modules you touched.
  >    Do not run a bare `pytest` on scenario work.
  > 3. **Refactor** — only if needed, tests staying green.
  > 4. **Commit each step separately**, tagged `[AI]`.

- The comment rule, because it is the one subagents break most: *zero new
  comments is the expected outcome; a comment that survives carries only the fact
  the reader needs, in at most three lines, with no dates, no first person and no
  narrative; the justification belongs in the commit message.*

Require the subagent to end its final message with exactly one status line:

```
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
```

Handle it:

| Status | Do |
| --- | --- |
| `DONE` | Record `HEAD_SHA`, go to step 5. |
| `DONE_WITH_CONCERNS` | Read the concerns, keep them for close, go to step 5. |
| `NEEDS_CONTEXT` | Kill the old implementer first, then dispatch one fresh one. Never two at once. |
| `BLOCKED` | Try once more with more context. Still blocked: stop, report, and leave the bead claimed with a note (`bd update <id> --append-notes`). |

**Never implement the bead yourself.** If the subagent cannot, that is a finding
about the bead, not an invitation to take over.

### Verify the claims yourself, by mutation

A subagent's report is a claim. Before accepting one, **break the thing the test
says it covers and confirm the test fails.** Reading a test is not enough: three
times on this project a test that read correctly did not bite.

Give your own scratch scripts **unique filenames**. Mutate the real mechanism,
not a string that looks like it.

## 5. Review it

**Scenario implementation** (new or changed step definitions for a feature file,
and the product code they call): do **not** invoke `review-bead-changes`. The
mutation check in step 4 *is* the review. One targeted question: does each new
step definition assert what its Gherkin says, or does it pass while testing
something weaker? Weaken an assertion and confirm the scenario still fails. No
second review round.

**Foundation work** — the diff touches `src/sermon/store`, `src/sermon/pipeline`,
or `tests/test_spec_harness.py`: invoke `review-bead-changes` over
`$BASE_SHA..$HEAD_SHA`. One review round is the default. A second round only
when the work has a multiplier (the harness every later bead builds on, the
extraction every number rests on).

It returns a verdict of `green` or `changes_requested`, plus any Minor findings.

For scenario work, treat a passing mutation check as `green`. A step that still
passes after you weaken its assertion is `changes_requested`.

## 6. Close or report

Do **not** run a bare `pytest` on scenario work. Run:

```bash
../.venv/bin/python -m pytest tests/test_spec.py -k "<Feature or Rule title>"
../.venv/bin/python features/validate_spec.py
../.venv/bin/python -m pytest tests/test_<touched_module>.py   # if you changed one
```

(From the repo root, drop the `../`.) Full suite
(`.venv/bin/python -m pytest`) only for store, pipeline, or harness changes.

If the change touched `src/sermon/pipeline/`, also run the three pipeline
instruments named in `CLAUDE.md`'s "Things that will bite you", before and after.
Any drift: revert, stop, do not patch.

Integrity for scenario work is those commands plus the mutation check — not a
separate bead.

**Verdict `green`, those gates passing:**

```bash
bd close <id> --reason="<what was built, one line>"
```

```bash
bd remember "<a durable fact this work established>"
```

Minor findings are **not** automatically beads. File one only if it blocks
something, will cost real time later, or is a correctness risk someone could trip
over. Otherwise name it in the close reason and let it go. Never *fix* a Minor
here.

**Verdict `changes_requested`, or the gates failing:** leave the bead open and
claimed, append what remains, and report. Do not close a bead whose acceptance
criteria are unmet, and do not weaken the criteria to make them met.

## 7. Report back

State plainly: what was built, the verdict, the commits, what you closed, what you
filed, scenarios-green count for the feature file, and anything you could not do.
If a convention had to be broken, say which and why — that is a decision for the
human, not a detail to absorb.

## Do not

- Implement the bead in the top-level session. The implementer is a subagent.
  Mutation (step 4) is orchestrator work; the eight-concern reviewer is not, except
  on store / pipeline / harness.
- Paste `CLAUDE.md` into a subagent prompt. Tell it to read the file.
- Close a bead on a `changes_requested` verdict.
- Fix Minor findings. File them only when they block, cost real time later, or
  are a correctness risk.
- Touch `experiments/` (frozen), `~/Desktop/Sermons` (read-only ground truth), or
  the held-out split without an explicit reason.
- `uv pip install` inside a worktree. Use the repo-root `.venv`.
- Merge worktree branches in parallel into `tpett/ai/v1-build`. You merge, in
  slice order.
- Touch `master`.
- Spawn a second implementer for the same bead. `spawn_subagent` is async unless
  you pass `background: false` — wait, or you will triplicate.
