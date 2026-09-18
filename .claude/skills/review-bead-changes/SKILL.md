---
name: review-bead-changes
description: Review a range of commits against a bead's acceptance criteria, the governing Gherkin scenarios, and this repository's conventions — using parallel reviewer subagents, a bounded fix loop and an explicit verdict. Invoked by do-bead; also usable directly on any commit range.
argument-hint: "[BASE_SHA..HEAD_SHA] [bead id]"
---

# Review Bead Changes

Find what is actually wrong with a change, fix what is worth fixing, and return a
verdict. Dispatch reviewers in parallel so each has one job and none is grading
its own work.

## Input

A commit range and a bead id. Called from `do-bead` both are supplied; called
directly, derive the range from `git log` and ask for the bead if it is not obvious.

## 1. Establish what changed

```bash
git diff --name-only $BASE..$HEAD
git diff --stat $BASE..$HEAD
```

If the range is empty, stop — there is nothing to review, and that is itself a
finding about the implementer.

## 2. Dispatch the reviewer set, in parallel

One `Task` subagent per reviewer, all in a single message so they run
concurrently. **Reviewers do not nest their own subagents.** Always dispatch
these four:

| Reviewer | Checks only |
| --- | --- |
| **Acceptance** | Does the change satisfy the bead's acceptance criteria, and does it do anything the bead did not ask for? |
| **Scenario fidelity** | Do the implemented step definitions actually assert what the Gherkin says, or do they pass while testing something weaker? |
| **Comment discipline** | ADR-LS-004 only. |
| **Code quality** | Correctness, naming, structure, dead code. Not comments — that is another reviewer's job. |

Add one **discretionary** reviewer per constraint the bead implies. Read them out
of the bead and the conventions rather than inventing them. Common ones here:

- *behaviour preservation* — for anything touching `experiments/src` or the
  extracted pipeline: re-derive and re-score, compare against the baseline,
  identical or it is wrong.
- *spec portability* — if `features/` changed: `validate_spec.py` passes, and no
  implementation vocabulary entered a scenario.
- *TDD ordering* — ADR-LS-001: does the commit history show a failing test before
  its implementation?

### Reviewer prompt template

Every reviewer prompt must contain: the diff or the range with an instruction to
run `git diff $BASE..$HEAD`; **its own single concern and nothing else**; the
source of truth for that concern quoted in full (the acceptance criteria, the
scenarios, the ADR's rules, the constraint phrase); and this exact return shape as
the final lines of its message:

```
STATUS: APPROVED | ISSUES_FOUND
FINDINGS:
- [CRITICAL|IMPORTANT|MINOR] <path>:<line> <message>
```

Three instructions that materially improve what comes back:

- **Verify every line number against the file in the worktree before reporting
  it.** Line numbers invented from diff hunk headers are the most common false
  finding.
- **Try to falsify the change, not to confirm it works.** Run the tests. Weight an
  executed experiment far above a plausible reading.
- **Report only your own concern.** A reviewer straying into another's produces
  duplicate findings that cost a fix iteration.

For the comment-discipline reviewer, each finding must quote the rule it breaks —
`[IMPORTANT] src/sermon/pipeline/segments.py:88 ADR-LS-004 [must] "No comment
carries rationale, history, changelog voice, first person…" — comment narrates
the 2026-09-13 failure`.

## 3. Collect, dedupe, classify

Merge the findings. Collapse duplicates, keeping the most specific. Classify:

- **Critical** — data loss, a corrupted corpus, a wrong published cut, a broken
  build, ground truth contaminated by machine output.
- **Important** — incorrect behaviour, a scenario passing without testing what it
  says, missing tests for new code, a convention broken, acceptance criteria unmet.
- **Minor** — style, naming, nitpicks, optional improvements.

**A scenario that passes while asserting something weaker than the Gherkin is
Important, not Minor.** It is the failure mode this whole approach exists to
prevent: the suite goes green and the spec stops meaning anything.

## 4. Bounded fix loop — at most two iterations

While Critical or Important findings remain and iterations ≤ 2:

1. Dispatch **one** fixer subagent with all Critical and Important findings, the
   range, and the relevant rules quoted. Instruct it to commit each fix, tagged
   `[AI]`, and to explain anything it deliberately does not fix.
2. Re-dispatch **only the reviewers whose findings were addressed**.
3. Re-collect and re-classify. No Critical or Important left: stop.

**Minor findings are never fixed here.** They are recorded and become follow-up
beads.

After two iterations, stop. Remaining Critical or Important findings are
unresolved and drive the verdict.

## 5. Verdict

- **`green`** — no unresolved Critical or Important findings. Minor may remain.
- **`changes_requested`** — one or more could not be resolved in two iterations.

Return the verdict, each Critical and Important finding with whether it was fixed
and in which commit, and the Minor findings as a list for `do-bead` to file.

## Do not

- Review with a single general-purpose reviewer. Parallel, single-concern
  reviewers find more and produce cleaner findings.
- Let a reviewer fix anything. Reviewers report; the fixer fixes.
- Fix Minor findings.
- Return `green` because the tests pass. The tests passing is one reviewer's
  evidence, not the verdict.
