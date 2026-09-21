---
name: review-bead-changes
description: Review a range of commits against a bead's acceptance criteria, the governing Gherkin scenarios, and this repository's conventions — using one reviewer subagent working a fixed checklist, a bounded fix loop and an explicit verdict. Invoked by do-bead; also usable directly on any commit range.
argument-hint: "[BASE_SHA..HEAD_SHA] [bead id]"
---

# Review Bead Changes

Find what is actually wrong with a change, fix what is worth fixing, and return a
verdict.

do-bead invokes this **only** for diffs that touch `src/sermon/store`,
`src/sermon/pipeline`, or `tests/test_spec_harness.py`. Scenario implementation
uses a mutation check instead — do not run this checklist on that path.

**One reviewer subagent, not several.** Parallel single-concern reviewers find
more, but each one costs another full copy of the diff, and at this project's size
that is the wrong trade. The coverage they gave is preserved as a **fixed checklist
the single reviewer must answer item by item** — see §2. The tradeoff is real and
the mitigation is §2's per-concern verdict: a concern that goes unanswered is
visible instead of silently skipped, which is the failure mode of a single
open-ended reviewer.

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

## 2. Dispatch one reviewer subagent

One `Task` subagent, `subagent_type: general-purpose`. Its prompt contains the
range with an instruction to run `git diff $BASE..$HEAD` itself (do not paste a
large diff), the bead's acceptance criteria verbatim, the governing scenarios
quoted, and the relevant sections of `CLAUDE.md` — read them, do not paraphrase.

It must work this checklist **in order**, and report a verdict for every item even
when it has nothing to say:

| # | Concern | Source of truth |
| --- | --- | --- |
| 1 | **Acceptance** — criteria met, and nothing built that was not asked for | the bead |
| 2 | **Scenario fidelity** — do the step definitions assert what the Gherkin says, or pass while testing something weaker? | the feature file |
| 3 | **Comment discipline** | ADR-LS-004, in `CONVENTIONS.md` |
| 4 | **Code quality** — correctness, naming, structure, dead code | judgment |
| 5+ | **Each constraint the bead implies** — see below | as named |

Add a numbered item for each constraint the bead implies. Read them out of the
bead and the conventions rather than inventing them. Recurring ones here:

- **behaviour preservation** — anything touching `experiments/src` or the extracted
  pipeline: re-derive, re-score, compare against the baseline. Identical or it is
  wrong.
- **spec portability** — if `features/` changed: `validate_spec.py` passes and no
  implementation vocabulary entered a scenario.
- **TDD ordering** — ADR-LS-001: does the commit history show a failing test before
  its implementation?

### Required return shape

The final lines of its message, exactly:

```
CONCERN 1 acceptance: APPROVED | ISSUES_FOUND
CONCERN 2 scenario-fidelity: APPROVED | ISSUES_FOUND
CONCERN 3 comments: APPROVED | ISSUES_FOUND
CONCERN 4 code-quality: APPROVED | ISSUES_FOUND
CONCERN 5 <name>: APPROVED | ISSUES_FOUND
FINDINGS:
- [CRITICAL|IMPORTANT|MINOR] <concern #> <path>:<line> <message>
```

**A missing `CONCERN` line is a failed review, not an approval.** Re-dispatch once,
naming the omission. This is the check that replaces reviewer independence.

Three instructions that materially improve what comes back — include them:

- **Verify every line number against the file in the worktree before reporting
  it.** Line numbers invented from diff hunk headers are the most common false
  finding.
- **Try to falsify the change, not to confirm it works.** Run the tests. Weight an
  executed experiment far above a plausible reading. **Mutate the mechanism the test
  claims to cover and confirm the test fails** — every guard this project trusted on
  a reading alone turned out not to bite. Mutate the real mechanism, not a literal
  that resembles it, and confirm your copy is the one being imported before
  believing a mutation result.
- **Use unique filenames for scratch scripts**, and leave the worktree clean. Two
  agents writing a proof to the same scratchpad path have already caused one false
  verification here.
- **Work the checklist in order and do not stop early.** Later concerns are the
  ones a single reviewer under-reports; budget attention for them.

For a comment-discipline finding, quote the rule broken —
`[IMPORTANT] 3 src/sermon/pipeline/segments.py:88 ADR-LS-004 [must] "No comment
carries rationale, history, changelog voice, first person…" — comment narrates a
past failure`.

## 3. Classify

- **Critical** — data loss, a corrupted corpus, a wrong published cut, a broken
  build, ground truth contaminated by machine output, **or a safeguard the spec
  requires being silently defeatable**.
- **Important** — incorrect behaviour, a scenario passing without testing what it
  says, missing tests for new code, a convention broken, acceptance criteria unmet,
  **a guard that does not bite**, **a citation that does not support its field**, or
  **a previously enforced guarantee now resting on caller discipline**.
- **Minor** — style, naming, nitpicks, optional improvements.

**Most Minor findings should not become beads.** Report them, but say which are
worth filing: one that blocks something, costs real time later, or is a correctness
risk someone could trip over. The rest are noted and dropped. Volume here is not a
sign of rigour — filing every nitpick built a 66-item P3 queue nobody will work.

**A scenario that passes while asserting something weaker than its Gherkin is
Important, not Minor.** It is the failure mode this whole approach exists to
prevent: the suite goes green and the spec stops meaning anything.

**Two Important classes this project keeps producing, so look for them by name.**
A test that only exercises the INSERT path where production writes an UPDATE —
prove coverage by removing the column from the update and watching a test fail. And
a constraint relaxed to admit a new case that silently dropped what it was *also*
guaranteeing: when a `NOT NULL` or a unique goes, ask what else it enforced.

Trust the reviewer's severities only as a starting point — reclassify anything
clearly mislabelled, in either direction.

## 4. Bounded fix loop — at most two iterations

While Critical or Important findings remain and iterations ≤ 2:

1. Dispatch **one** fixer subagent with all Critical and Important findings, the
   range, and the relevant rules quoted. Instruct it to commit each fix, tagged
   `[AI]`, and to explain anything it deliberately does not fix.
2. Re-dispatch the reviewer, **scoped to the concerns whose findings were
   addressed** — it need not re-run the whole checklist, and the scoping is where
   the token saving from a single reviewer is actually realised.
3. Re-classify. No Critical or Important left: stop.

**Minor findings are never fixed here.** They are recorded and become follow-up
beads.

After two iterations, stop. Remaining Critical or Important findings are
unresolved and drive the verdict.

## 5. Verdict

- **`green`** — no unresolved Critical or Important findings. Minor may remain.
- **`changes_requested`** — one or more could not be resolved in two iterations,
  or the reviewer never answered a concern after a re-dispatch.

Return the verdict, each Critical and Important finding with whether it was fixed
and in which commit, and the Minor findings as a list for `do-bead` to file.

## Do not

- Let the reviewer fix anything. It reports; the fixer fixes.
- Accept a review missing a `CONCERN` line.
- Fix Minor findings.
- Return `green` because the tests pass. The tests passing is one item on the
  checklist, not the verdict.
