# Conventions

This project inherits Launch Supply's firm-level foundations ADRs from
`~/Source/launch-supply/silo/global/adrs/foundations/`. Silo is authoritative;
this file records which apply here, how the Ruby-shaped ones translate to Python,
and where this project deliberately differs.

Precedence, per silo's own rule: a project-local decision outranks a firm-level
one, which outranks `CLAUDE.md` prose.

## What applies

| ADR | Applies | How it lands here |
| --- | --- | --- |
| **LS-001** TDD-first | yes, `(global)` | Already the shape of this project — see below. |
| **LS-002** Worktree isolation | yes, `(global)` | `worktrees/<name>`, branch `tpett/ai/<name>`. No Linear team, so no issue-key prefix. |
| **LS-003** Service objects | **no** | Scoped to `app/services/**/*.rb`. Not a Rails app. The *naming* convention is worth keeping: third-person singular verb phrases. |
| **LS-004** Comment discipline | yes, `(global)`, every language | The one with real consequences here. See below. |

## LS-001 — TDD, and why this project is already mid-cycle

460 scenarios exist and nothing implements them. **That is the Red phase for the
whole build**, written before any code, which is the strongest form of the ADR
rather than an exception to it.

So the cycle runs per scenario, not per feature file: pick a scenario, write the
step definitions, watch it **fail** (not error — an error is a setup problem),
implement the minimum, move on. Commits stay granular and tagged `[AI]`.

The one place to be careful: `experiments/` was exploratory work and predates
this. It is frozen as the record of how the numbers were produced, not held to
the cycle retroactively.

## LS-003 — the part worth keeping without the Rails

No `Supplies::Functional`, no `app/services/`. What translates:

- **One operation per unit, named as a third-person singular verb phrase.**
  `ProposesSegments`, `RendersSegment`, `ReconcilesBucket` — not
  `SegmentProposer`, not `propose_segments` scattered across a module.
- **Dependencies injected, defaults provided**, so a test can substitute the
  model host or the clock without patching globals.
- **A single entry point.** Python's equivalent of `.call` is `__call__` or a
  module-level function; pick one and keep it uniform.

## LS-004 — comment discipline, and the debt this project already carries

The bar, unchanged: **a comment is permitted only where the code cannot show
it**, it must be defensible in one sentence, that defense goes in the commit
message and never in the comment, and the source carries only the mitigating fact
— one line, three at the ceiling. No dates, no first person, no narrative, no
changelog voice. Zero new comments is the expected outcome.

**Measured against `experiments/src` on adoption:** 239 comment lines at 6.3%
density, but **21 blocks over the three-line ceiling** (worst: 16 lines), **12
containing dates**, 12 in "Measured…" narrative voice, 5 using first person.
Substantially non-compliant, and the cause is diagnostic: most of those comments
**duplicate `FINDINGS.md`**. The rationale already had a home and was written
twice.

Cleanup is opportunistic and in **dedicated commits**, never mixed into a feature
diff — ADR §7. The extraction of `experiments/src` into `src/sermon/pipeline/` is
the natural moment, but it must not be combined with the behaviour-preserving move
(see ARCHITECTURE.md): extract first and prove it identical, then clean comments
in a separate commit.

### Where this project's rationale lives

The ADR routes rationale to "the commit message, a README, or an ADR". Commit
messages do not travel to a rewritten repo, and this project's stated reason for
existing is that the spec carries everything a rewrite needs. So:

| Content | Home |
| --- | --- |
| What a number is and where it came from | `experiments/FINDINGS.md` |
| Why the system is shaped this way | `ARCHITECTURE.md` |
| What the system must do | `features/` |
| What it holds | `features/DOMAIN.md` |
| Why a comment was necessary | The commit message |
| The mitigating fact itself | The comment, ≤3 lines |

### Gherkin is specification, not code

**The feature files keep their explanatory comments.** This is a deliberate
project-local departure, and the reasoning is the owner's requirement that the
cucumber files carry everything needed to rewrite this in another language — a
measurement citation in a scenario is specification content, not a code comment
justifying an implementation.

The ADR's *form* discipline still applies to them, because it costs nothing: no
first person, no narrative for its own sake, and a comment that merely restates
its scenario gets deleted. `features/validate_spec.py` enforces the harder rule
that matters more here — no implementation vocabulary leaks in.
