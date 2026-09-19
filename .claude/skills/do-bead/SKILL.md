---
name: do-bead
description: Implement one Beads issue end to end with subagent-driven development — a TDD implementer subagent, then an independent reviewer subagent, a bounded fix loop, and a verdict. Use when the user names a bead (e.g. "do sp-1vn.1", "work the next bead") or asks to start the next ready piece of work.
argument-hint: "[bead id, or omit to take the first from bd ready]"
---

# Do Bead

Take a bead — or a batch of beads that are one change — from open to closed, with
the implementation and the review each done by subagents so neither is marking its
own homework.

The conventions this enforces live in `CLAUDE.md` and `CONVENTIONS.md`. **Do not
restate them to subagents from memory — read them and pass them.** That is the
whole reason they are written down.

## Input

A bead id, or nothing. With nothing, take the highest-priority item from
`bd ready` and say which one you took before starting.

## 0. Batch first — this is the largest lever there is

**Take several beads in one pass when they are one change.** Beads that touch the
same files are cheaper *and safer* together: run separately, each cycle
invalidates the next one's edits, and you pay a full implement-review-fix round
every time. Measured on this project: eight beads in one batch cost about what one
bead cost unbatched.

Batch when the beads share files, share a design decision, or would conflict.
Six domain-model gaps, five "X is flagged with a condition" beads, two new
entities — each was one coherent change. **Do not batch** work with genuinely
independent designs, or a high-risk bead with anything else.

When you batch, say so and say why, and give the reviewer the whole set.

**One review round is the default.** Spend a second round only on work with a
multiplier — the harness every later bead builds on, the extraction every number
rests on. The store got one round and that was right; the harness got two and that
was also right.

## 1. Read the bead and claim it

```bash
bd show <id>                    # title, description, acceptance, parent, deps
bd show <id> --json             # when you need fields programmatically
bd update <id> --claim
```

Read the **acceptance criteria** as the definition of done. If the bead has none,
stop and ask for them rather than inventing them — a bead without acceptance
criteria cannot be reviewed, only guessed at.

If the bead has a parent, read the parent too (`bd show <parent>`): the parent
carries the phase context the child assumes.

**Refuse to start if the bead is blocked.** `bd ready` will not offer it, but an
explicitly named id can be. Say what blocks it.

**But check whether the block is real.** If the blocker is an *epic* rather than a
specific bead, the dependency is probably wrong: an epic stays open for its least
related child. A P0 epic here was invisible for nine iterations that way. Repoint
the edge at the beads whose output is actually needed (`bd dep remove`,
`bd dep add`), record why, and proceed. Do not `--force` close an epic whose
children are genuinely open — that erases the record of what is undone.

## 2. Locate the governing spec

Most beads implement scenarios. Find them:

```bash
grep -rn "<the behaviour>" features/          # find the Rule and its scenarios
```

Name the governing feature file and `Rule:` in your plan. A bead that implements
no scenario is either foundational work (scaffolding, extraction, deployment) or
a bead that should not exist — decide which and say so.

## 3. Choose the worktree

Per ADR-LS-002, parallel or long-running work gets its own worktree:

```bash
git worktree add worktrees/<bead-id> -b tpett/ai/<bead-id>
```

For a small, self-contained bead the working tree is acceptable — **ask first**.

## 4. Dispatch the implementer subagent

Record the baseline: `BASE_SHA=$(git rev-parse HEAD)`.

Dispatch **one** `Task` subagent (`subagent_type: general-purpose`) whose prompt
contains, in full:

- The bead's **title, description and acceptance criteria**, verbatim.
- The **governing feature file and Rule**, with the scenarios quoted.
- The **contents of `CLAUDE.md`'s Conventions and "Things that will bite you"
  sections** — read them, do not paraphrase.
- Any **project documents the bead depends on**: `features/DOMAIN.md` for store
  work, `ARCHITECTURE.md` for structural work, the relevant `FINDINGS.md` section
  for anything touching measured behaviour.
- An explicit TDD instruction:

  > 1. **Red** — write the failing test (usually step definitions for a
  >    scenario). Run it. Confirm it **fails rather than errors**; an error means
  >    your harness is wrong, so fix that and get a real failure first.
  > 2. **Green** — the minimum code that passes. Run the tests.
  > 3. **Refactor** — only if needed, tests staying green.
  > 4. **Commit each step separately**, tagged `[AI]`.

- The comment rule stated as a constraint, because it is the one subagents break
  most: *zero new comments is the expected outcome; a comment that survives
  carries only the fact the reader needs, in at most three lines, with no dates,
  no first person and no narrative; the justification belongs in the commit
  message.*

Require the subagent to end its final message with exactly one status line:

```
STATUS: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
```

Handle it:

| Status | Do |
| --- | --- |
| `DONE` | Record `HEAD_SHA`, go to step 5. |
| `DONE_WITH_CONCERNS` | Read the concerns, keep them for step 6, go to step 5. |
| `NEEDS_CONTEXT` | Supply what it asked for and dispatch a **fresh** implementer. Do not continue the old one. |
| `BLOCKED` | Try once more with more context. Still blocked: stop, report, and leave the bead claimed with a note (`bd update <id> --append-notes`). |

**Never implement the bead yourself.** If the subagent cannot, that is a finding
about the bead, not an invitation to take over.

### Verify the claims yourself, by mutation

A subagent's report is a claim. Before accepting one, **break the thing the test
says it covers and confirm the test fails.** Reading a test is not enough: three
times on this project a test that read correctly did not bite — six columns with no
UPDATE-path coverage, a refusal test that never checked nothing was stored, a guard
a comment satisfied. Each read fine.

Two practical notes. Give your own scratch scripts **unique filenames** — a
subagent writing its proof to the same scratchpad path once made me re-run its
script and report it as my own check. And mutate the real mechanism, not a string
that looks like it: an `ON CONFLICT DO UPDATE` list generated from table metadata
is not patched by editing a literal.

## 5. Review it

Invoke `review-bead-changes` over `$BASE_SHA..$HEAD_SHA`, passing the bead and the
governing scenarios. Follow that skill; do not re-specify it here.

It returns a verdict of `green` or `changes_requested`, plus any Minor findings.

## 6. Close or report

Run the suite and the guardrail before closing anything:

```bash
.venv/bin/python -m pytest                      # a bare pytest/python3 is 3.14 and wrong
.venv/bin/python features/validate_spec.py
```

If the change touched `src/sermon/pipeline/`, also run the three pipeline
instruments named in `CLAUDE.md`'s "Things that will bite you".

**Verdict `green`, suite passing:**

```bash
bd close <id> --reason="<what was built, one line>"
```

Record anything worth keeping for later:

```bash
bd remember "<a durable fact this work established>"
bd create "<follow-up>" --type=task --priority=3 --deps="discovered-from:<id>"
```

Minor findings are **not** automatically beads. File one only if it blocks
something, will cost real time later, or is a correctness risk someone could trip
over. Otherwise name it in the close reason and let it go — filing every nitpick
built a 66-item P3 queue that nobody will work and that hides the real path. Never
*fix* a Minor here.

**Verdict `changes_requested`, or the suite failing:** leave the bead open and
claimed, append what remains, and report. Do not close a bead whose acceptance
criteria are unmet, and do not weaken the criteria to make them met.

## 7. Report back

State plainly: what was built, the verdict, the commits, what you closed, what you
filed, and anything you could not do. If a convention had to be broken, say which
and why — that is a decision for the human, not a detail to absorb.

## Do not

- Implement or review in the top-level session. Both are subagent work, and the
  point is that the reviewer is not the author.
- Restate conventions from memory. Read `CLAUDE.md` and pass it.
- Close a bead on a `changes_requested` verdict.
- Fix Minor findings. File them.
- Touch `experiments/` (frozen), `~/Desktop/Sermons` (read-only ground truth), or
  the held-out split without an explicit reason.
