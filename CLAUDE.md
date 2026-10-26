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

`features/` is **the specification and the test suite**, 535 Gherkin scenarios.
`experiments/` is a **frozen record** of the spike that proved the approach; every
number in `FINDINGS.md` traces to the code there.

## Build & Test

```bash
uv venv --python 3.13 && uv pip install -e ".[dev]"  # python3 on PATH is out of range
.venv/bin/python -m pytest -m "not slow"            # the normal run
.venv/bin/python -m pytest                          # the pre-merge run; before master
.venv/bin/python -m pytest tests/test_spec.py -k "<Feature or Rule title>"
.venv/bin/python features/validate_spec.py          # spec guardrail — also runs as a test
.venv/bin/python -m pytest --collect-only -q tests/test_spec.py   # 705 tests (Outlines expand)
bd ready                                            # what to work on next
```

**There are two tiers, and `-m "not slow"` is the one to reach for.** 55 s for
the 1,764 tests it selects: the store, config, the three pipeline instruments,
all of the spec but its four `@slow` features, and every harness guard that
reads the spec without running it.

**A bare `pytest` is the pre-merge run**, 2:00 for all 1,837. It adds the four
`@slow` features and the two guards that prove the spec suite is honest — that
every scenario it does not defer actually executed, and that none of them
errored rather than failed. Those two read the outcomes of the run they are part
of, so a bare `pytest` pays for the spec once. Asked for on their own
(`pytest tests/test_spec_harness.py`) they have no run to read and start one in
a subprocess, which is why that file alone costs 1:30 rather than 3 s. Nothing
between the two tiers is worth a third: the whole difference is one render.

Only `processing/audio_rendering.feature` costs anything. It renders a
43-minute MP3 through the real chain and measures the file, caching the
synthesised sources and every render under `$TMPDIR/sermon-test-renders`
against a digest of `pipeline/render.py`. Warm that is a single render, because
`The same input produces the same output` has to write one for real to have
anything to compare it against. A cold cache is about a quarter of an hour and
450 MB; editing the chain re-renders but keeps the sources.

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
.venv/bin/sermon-regrade                        # the gate: production's walk vs the human cut, dev split
.venv/bin/sermon-regrade --accept "<why>"       # move the reference, on purpose, with a reason
.venv/bin/sermon-regrade --corpus-regime --before tests/pipeline_boundary_fingerprint.json  # old replay
.venv/bin/sermon-approvals   # the headline: what fraction was approved untouched
.venv/bin/sermon-approvals --since 2026-09-01 --until 2026-09-30
.venv/bin/sermon-analyze recording_20260712_103000 --corpus experiments/data --summaries none
.venv/bin/sermon-corpus recording_20260920_094416 --prompts experiments/prompts
.venv/bin/sermon-align recording_20260927_095721 "~/Desktop/Sermons/2026-09-27 - Hebrews 13.7-8.mp3" \
    --source "~/Desktop/Sermons/2026-09-27 - Hebrews 13.7-8.flac"
.venv/bin/sermon-title --dry-run             # name recordings analysed before titles existed
```

**Configuration.** Every variable is read from the environment or `.env`; only
the first six are required.

| Variable | What it sets |
|---|---|
| `SERMON_DATA_ROOT` | the store, sources, previews, renders |
| `SERMON_OBJECT_STORE_ENDPOINT` / `_BUCKET` / `_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` | the bucket, read-only |
| `SERMON_MODEL_ENDPOINT` | mac-m1's ollama, text only |
| `SERMON_WEBHOOK_TOKEN` | the bearer token the recorder presents; unset refuses every webhook |
| `SERMON_NOTIFICATION_CHANNEL` | `in-app` (default) or `slack` |
| `SERMON_SLACK_WEBHOOK_URL` | required for `slack`; it is itself a credential |
| `SERMON_APP_URL` | where a Slack message's "Open the recording" link points |
| `SERMON_SCAN_INTERVAL_SECONDS` | `sermon-work`'s scheduled scan; unset or 0 is off |
| `SERMON_INGEST_CUTOFF` | discovery ignores objects recorded before this date |
| `SERMON_ASR_ENDPOINT` | a transcriber on the tailnet instead of in-process; audio is posted to it, so it must resolve to a private address |
| `SERMON_DIARIZATION_MODELS` | the sherpa-onnx models; unset means analysis runs without speaker evidence |
| `SERMON_PROMPTS_ROOT` | the classifier's prompts |
| `SERMON_BIND_HOST` / `SERMON_PORT` | where `sermon-serve` listens |
| `SERMON_ACCESS_TEAM_DOMAIN` / `SERMON_ACCESS_AUD` | Cloudflare Access sign-in: both set requires a valid `Cf-Access-Jwt-Assertion` on every request, neither leaves the app open, exactly one refuses to start |
| `SERMON_TAILNET_HOST` | with Access on, the one Host (e.g. `sermon-processor.home.tpett.me`) that needs no sign-in, unless the request carries `Cf-Ray` or `Cf-Connecting-Ip`; unset exempts nothing |

`sermon-reconcile` lists the bucket and downloads nothing. `sermon-serve` binds
the tailnet address by default; `SERMON_BIND_HOST=127.0.0.1` reaches it locally.

**Sign-in.** `SERMON_ACCESS_TEAM_DOMAIN` is the team domain in Cloudflare Zero
Trust (Settings > Custom Pages, or the host of the login page, e.g.
`myteam.cloudflareaccess.com`); `SERMON_ACCESS_AUD` is the Application Audience
(AUD) tag on the application's Overview tab (Access > Applications > the app).
The token is checked here, not trusted from the proxy: RS256 only, signature
against `https://<team domain>/cdn-cgi/access/certs` (cached an hour, fetched
again for an unknown key id at most once a minute), `aud`, `iss`, `exp`/`nbf`
and an `email` claim. Without a valid one a request gets a plain 401, or a 503
when Cloudflare's keys cannot be fetched at all. The only exemption is the
tailnet host, and only for a request with neither Cloudflare header: Access
cannot reach a 700 MB FLAC over its proxy, and the Recorder's webhook, which
still answers to `SERMON_WEBHOOK_TOKEN`, posts there. `IdentifiesRequester` is
the one place that turns a request into a verified email or nothing; nobody on
the tailnet is identified yet, so those requests are recorded as `reviewer`.
There is no health route exempt: `/api/health` needs a sign-in like the rest, and
nothing probes it.

`sermon-work` is the only thing that runs queued work. Nothing else drains the
queue — not the server, not any other command — so without it a webhook's
download, an approval's render and every analyze job sit in `queued` forever. It
recovers first: a job left `running` by a crash or a restart returns to `queued`
without a second job being enqueued and without refunding the attempt it spent.
**`--once` runs a single job** and `--limit N` stops after N, for a manual,
bounded run; neither ever scans. Production runs it unflagged as its own
container, transcribing locally and analysing without `--corpus`. A bucket scan
queues nothing and the scheduled scan queues only recordings newer than any
already taken up, so an unbounded run no longer pulls the back catalogue — but
a local store that still holds old queued downloads would, so check the queue
before draining one.

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

`sermon-regrade` answers one question: **does this change make production's
first proposal closer to or further from where the human cut, on the recordings
we have?** It replays production's analyze job itself — `RunsAnalyzeJob` and the
stage walk as `sermon-work` builds it with no corpus, roots bound to an empty
`corpus/diarization` — over each stored transcript, handing the stored model
answer in at the walk's `divides` seam. Stages needing audio or a model
(waveform, preview, diarization, summarization, titling) are refused before they start,
and only optional ones. No audio leaves the machine and no model is called; it
needs `SERMON_SPIKE_DATA` or `--corpus`.

**The judge is `analysis/judges_cut.py` and nothing else**, and every run prints
its version and digest. A pause is a gap of at least 1.0 s between words, or the
quiet before the first word or after the last. A proposal in the human's pause
*is* the human's cut. Any other proposal is as far from it as the speech-seconds
between them, and a move under 0.1 speech-seconds outside the human's pause is
unchanged. Clearance from a word and landing inside one are diagnostics, never
ranking keys. Pairing (more than half the human span) and the archived-whole
exclusion (over 95% of the source) live there too.

**The reference is `tests/shipping_baseline.json`**: the shipping replay's
proposals for every block file, with a history of who accepted them, at which
commit, under which judge and why. It moves only by `--accept "<reason>"`.
Accepting a changed judge together with moved proposals is refused — change the
judge on an unchanged pipeline first. When the live proposals differ from it the
gate says so; accept an improvement you want kept, or a later change can undo it
and still pass.

By default it judges **recordings, not configurations**: `fw-qwen3.6.whole.v2`
(faster-whisper int8 + `qwen3.6:35b-mlx`, which is what production runs) on the
**dev split**, 7 recordings once 2026-06-28 (archived whole) is excluded. `--tag`
names another config exactly; `--all` spells out unchanged recordings too. **Any
other split is held out**: `--split test|all` is refused without `--unseal
"<reason>"`, and an unsealed read is appended to `tests/held_out_reads.log`
before anything is read — commit that line. The test split was scored
repeatedly on 2026-10-03 and counts as seen.

It exits **0** when no recording got worse, **1** when one did (worse at either
cut, a mixed result, or a new proposal no human cut pairs with), and **2** when
it cannot say: no baseline, nothing compared, a held-out split refused, or the
judge changed since the baseline was accepted. `tests/test_shipping_gate.py`
runs the same check in the fast suite.

`--corpus-regime` keeps the old replay (stored block files through `derive()` and
`choose(model_segments)`) with its accuracy, `--before`, `--save`, `--store` and
`--drift` modes; those flags select it on their own. It is not the walk
production runs, and its `--before` against
`tests/pipeline_boundary_fingerprint.json` is no longer a gate. That file stays
as `test_pipeline_library.py`'s pin.

`sermon-approvals` prints the owner's headline measure: of the Segments
published in a period, the fraction approved with no boundary edit. The period
**defaults to all time**, because at one recording a week a calendar month is
usually empty and the whole record is still only a handful of cuts; `--since`
and `--until` take ISO dates and either may stand alone. It reads the store and
nothing else — no corpus, no object store, no model host — so it needs only
`SERMON_DATA_ROOT`, and `--store <data-root>` points it at another root.

**It exits non-zero when the period published nothing**, saying there is no rate
rather than printing 0%: the proportion is undefined over an empty period, and a
zero would read as every cut having been edited. The summary names the
denominator beside the proportion, because a rate over two cuts is not a trend.
Each published cut is listed with whether the reviewer moved its boundaries and,
where they did, the signed error of the machine's proposal against the boundary
they chose. **An untouched cut carries no error figure and says so** — there is
no human answer to subtract, and a printed 0.000 would be the system scoring
itself. **A published Segment carrying no `publication_date` is in no period at
all**, so those are counted on their own line rather than vanishing, and without
the line the command would report nothing published and give no hint why.
Approval now places the date from the Recording's start where the reviewer
entered none, so nothing newly published lands there; the line catches only rows
written before that — production's four, until they are backfilled.

`sermon-analyze` is `sermon-propose` without the corpus grading and with the
store the server reads: it registers the Recording from the stored transcript,
queues an `analyze` job for it, drains that one job through the same analysis
stages, and leaves the Blocks, the Segment, the Proposal and the reviewer
notification in the configured data root with the Recording `awaiting_review`.
One recording id per invocation. It exits non-zero when nothing was proposed.

`sermon-corpus` makes an analysed Recording gradeable. **The population
`sermon-regrade` walks is the tagged block files, not the answer key**, so a
`CorpusPair` for a recording with no block file is graded against nothing — which
is why `--store` reported 0 proposals while the store held a labelled pair. The
command reads the Recording's stored transcript artifact, writes it and any
diarization where `pipeline.segments` looks, reasons over it once, and records
the classifier's `blocks`, its own `model_segments` and the chosen boundaries as
`<corpus>/blocks/<id>.<tag>.json`. `--corpus` defaults to `<data-root>/corpus`,
which the layout already reserves; `--prompts` defaults beside it the way
`sermon-analyze` does, so a real run needs `--prompts experiments/prompts`.

**The classifier's answer has to be frozen, not re-read from the store.** The
store keeps no part of it but the Blocks it became — not `model_segments`, which
`choose` prefers at the punch-in. Measured over the 181 corpus block files,
dropping `model_segments` changes the boundaries of 64 proposals and moves 68
punch-ins by a median 2.100 s and a maximum 650.360 s, so a store-fed population
would grade a different algorithm from the one that ships. The command therefore
**refuses to write any file that already exists in the target corpus** — the
transcript and diarization as well as the block file — and **refuses a corpus
root inside the frozen spike tree outright**, both before any model call; it
creates files exclusively and removes what it created if a later step fails, so
a failed run can simply be retried. It writes no stored row — `sermon-organize`
is still the only command that does.

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

`sermon-title` names Recordings that were analysed before the walk had a
`titling` stage. It reads only what is stored — the Blocks and their summaries,
the Segments and their labels, the weekday and start time — and sends that text
to `SERMON_MODEL_ENDPOINT`; no audio and no re-analysis. It reads the stored
transcript only to count what was said, so a recording with no music and fewer
than 20 different utterances is named "Silence or noise" without asking the
model. It needs only `SERMON_DATA_ROOT` (or `--store`) and the endpoint. It
prints one line per recording: start, kind, title, any label it suggests, id —
`2026-09-13 09:00  class  Theological Equipping Class - Stewardship, then Sunday
Service - Hebrews 12:25-29  label: TEC - Stewardship (lesson)  [recording_…]`.
By default it names only Recordings with no title yet; `--again` re-asks for
machine titles too. A Recording a reviewer titled is never touched — not its
title, kind or labels — and is listed as kept. Labels are suggested only for
Segments that have none. `--dry-run` prints the same lines and writes nothing;
the owner previews production with it before any write.

**The names glossary is `src/sermon/names.toml`**, one `ACRONYM = "Full name"`
line each (`TEC`, `CT` today). A title spells a name out; the list's kind tag
and a class's suggested label use the acronym. To add a name, add a line; it
ships in the image with the code. The titling prompt is
`src/sermon/analysis/prompts/titles.v1.md`, also shipped with the code: the
classifier's prompts are the frozen `experiments/prompts`, copied by the
Dockerfile to `SERMON_PROMPTS_ROOT`, and nothing new may be added there.

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
- **Know which guard can see the seam you changed, before citing it as a gate.**
  `sermon-regrade` (and `tests/test_shipping_gate.py`) executes the shipping walk
  from the stored, already-coerced block table onward: the walk's stage list,
  `ClassifiesBlocks`, `ProposesSegments`, `RefinesPunchIn/Out` → `_chooses` →
  `ChoosesBoundaries`, and all of `pipeline/segments.py`. Deleting refinement
  from the walk or shifting the punch-in +3 s fails it. It cannot see
  `coerce_blocks` or anything else upstream of the stored blocks, the model's
  variance (one frozen draw per recording), transcription, diarization,
  summarization, `works()`'s own wiring, or anything after proposal; for
  `coerce_blocks` only `test_pipeline_behaviour.py` notices (`sp-glwk`).
  `test_pipeline_library.py` and `sermon-regrade --corpus-regime` replay
  `choose(model_segments)`, which production does not run, and stay green under
  both mutations above — they pin the library, they do not gate quality.
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
- **The classifier still sends `format: json` when thinking is off, and the
  MLX model refuses it.** ollama 0.34.0 answers HTTP 501 `structured output is
  unavailable`, `pipeline/classify.py` retries unconstrained, and that retry is
  the answer every production classification actually uses — unconstrained also
  scores better. So each classification costs one refused request. The pipeline
  is frozen; dropping the constrained attempt is a behaviour change to measure,
  not a tidy-up.
- **`experiments/data/test_access.log` is the spike's frozen record** of held-out
  scoring runs. New held-out reads go to `tests/held_out_reads.log` through
  `sermon-regrade --unseal`, which refuses without a reason.
- **Some published MP3s are machine cuts, not human edits.** `align.MACHINE_CUT_MP3S`
  excludes them from ground truth. Add to that set whenever a proposal ships
  unedited, or the corpus starts grading itself.

### The pins have moved, on purpose

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

On 2026-09-30 the product owner declined the back-catalogue work outright —
"do nothing with teh old stuff" — and then authorised removing the scenarios that
claimed it: "Yes you can cut those specs". Four went, because a scenario the owner
has refused is not a backlog item, it is the spec asserting something untrue:
`The back catalogue will sound quieter than new output` and the whole Rule `The
back catalogue does not match the new output` with both its scenarios, from
`features/processing/audio_rendering.feature`, and `Re-rendering the back
catalogue after settling the loudness target` from
`features/processing/reprocessing.feature`. That Rule emptied, so the Rule count
moved too — the first time a pin has gone *down*.

Deliberately kept, because they are not the back catalogue: `An archival segment
is converted, not produced` (an archive-intent Segment is this week's members
meeting, not an old file) and `Re-rendering after changing render settings` (one
Segment, not a bulk pass).

Also on 2026-09-30, after using the waveform editor, they asked for the
transport on the spacebar: "Bind the spacebar to play/pause (obviously, we'll
need to make sure this doesn't make form inputs unable to type or cause a
play/pause event when typing)". No scenario put the transport on a key at all —
`Playing from anywhere` clicks the waveform and `Zooming in and out from the
keyboard` only reaches the zoom steps — and the exemption they named is half the
requirement, so `Playing and pausing from the keyboard` was added to
`features/interface/waveform_review.feature` under `Rule: I can listen to the
audio`, asserting both the key and that the screen says when it is not taken.

On 2026-10-01 they reported the zoom chords working only intermittently and
asked for better keys: "The CMD-1 and CMD-3 ones still only work sometimes.
Seems to be dependent on what part of the page I'm focused on. Any thoughts for
fixing that? Another option is to come up with different hotkeys that wouldn't
be problematic. Any thoughts based on industry standards of similar timeline
based editing tools?"

Half of that was a bug — the chord handler bailed out while focus sat in a
field, which handed the chord back to the browser — and needed no spec change.
The other half did: nothing said a zoom keystroke had to be one the browser
would actually deliver, and nothing reached the whole recording in one press. So
`Zooming in and out from the keyboard` grew two assertions rather than gaining a
scenario beside it, because the behaviour is the one it already describes and
only the keys differ. No scenario, Rule or file count moved; `SPEC_STEPS` moved
by the two declared steps.

Which keys was then settled by the owner rather than by us: "let's adopt
Premiere Pro. You can leave the Audacity bindings though too. Audacity
ergonomics are actually better (left handed with mouse in right hand whereas on
my keyboard - is on the right side and = is on the left) nevertheless, the - and
= keys will work reliably. Similar to spacebar we will need to make sure this
works and inputs remain working". So Premiere's `-`, `=` and `\` lead, the
Audacity digits and chords stay, and the Audacity chords are the preferred
binding rather than a tolerated alias.

On 2026-10-01 the owner settled two things about the webhook endpoint, which
until then accepted any POST at all. On authentication: "Just use a simple
bearer token configured in an environment variable. Simple enough. We have no
auth anywhere else, but we might add it at some point." Nothing in the spec said
the Processor authenticates its caller — the feature's own prose said "the
network is the boundary" — so the new Rule `Only a caller presenting the bearer
token can report a recording` was added to
`features/ingestion/webhook_notification.feature` with a Scenario Outline over a
wrong token, a header that is not a bearer token and no authorization at all,
plus `The Processor has no bearer token configured`. A Background step was added
for the token the Recorder holds, because the existing scenarios would otherwise
depend on a credential the spec never mentions. **This is the first Rule added
since the count last moved**, so the Rule pin goes up.

On the scenario that was only ever about the Recorder: "Yeah, let's move that to
the test suite in the other repo. No need to include that in our specs." So `The
Processor is down when the Recorder fires the webhook` was deleted — every one of
its five assertions was about the Recorder's retries and delivery failures, a
component in the audio-recorder repository that this suite cannot reach, which is
why it had never been anything but red. Its Rule `The Processor is resilient to
delivery failures` keeps `The webhook arrives before the object is readable in
the bucket`, so that Rule survives and the deletion moved no Rule count. A
comment in its place cites where the behaviour is now specified, so the
requirement is not silently absent.

On 2026-10-03 the owner settled a contradiction about diarization. They want it
built and treated as useful when it is there — "It might be useful in certain
cases, we should build it unless there's a major lift" — and
`features/analysis/speaker_diarization.feature`'s `Diarization fails` already
said analysis carries on with transcript evidence alone. The Outline `A stage
fails permanently` in `features/analysis/analysis_orchestration.feature`
disagreed, listing `diarization` among the stages whose failure sends the
Recording to `analysis_failed`. Evidence that is only useful when available
cannot also be fatal when absent, so the `diarization` Examples row was removed.
One expanded test went; no scenario, Rule or step count moved.

The same day, asked about the list's transcript search: "Search is less
important for now." `Finding a recording by what it was` in
`features/interface/recording_list.feature` asserts a search the list does not
have. Its text is unchanged; it is tagged `@deferred` with the owner's words, so
it is a decision on the record rather than a gap. No pin moved; `DEFERRED_TESTS`
went from 7 to 8.

On mobile they said "Mobile is good enough as is." The Rule in
`features/interface/segment_review.feature` still read `Mobile can check and
approve; editing is a desktop job`, and `A segment needing real editing says so
on mobile` asserted a "better made at a desk" message and no editor at all on a
phone — the opposite of what shipped, which offers the phone the full editor
and reflows it to fit. The Rule is now `A phone gets the full editor, reflowed
to fit`, and that scenario became `A segment needing real editing can be edited
on a phone`, asserting in a phone-sized Chromium that the waveform and the nudge
controls are offered, the page is no wider than the screen, and skip and approve
are still there. Same step count; no pin moved.

On publication dates: "Naming is always based on recording date. Publication
date is irrelevant other than for logging." `features/interface/publication_details.feature`
made Date a required, prefilled, changeable reviewer entry and built the file
name from it, and the product agreed: the render named the MP3 from
`Segment.publication_date` whenever one was set, so a date written through
`PUT /api/segments/<id>/publication` renamed the output. The Rule is now `A
published segment needs a label, and is dated by its recording`. `Entering
publication details` asserts on the rendered page that a label is asked for and
a date is not; `The date defaults from the recording` became `The publication
date is the recording's, kept for the log`, approving through the page and
reading back the label and the placed date; `A publication date never names the
file` was added, recording a different date through the real request and then
processing; and the filename Outline's Given now sets the Recording's date
rather than a publication date. The render and the collision check both name
the file from the Recording's start, and `publication_date` is still stored.
One scenario and five steps were added and one expanded test with them.

On the lead-in: "Lead-in silence is not necessary, but if it's too long it's a
problem. 1-2s is probably about as long as you want to go or someone who's
started the recording playback thinks nothing is happening." And on any cut:
"there is some buffer needed due to room echo and other pre "word" sounds. 50ms
is probably a good buffer but it might need to be a bit longer... Almost always
though moving more into the silence produces a better cut."
`features/analysis/punch_in_detection.feature`'s `A short lead-in is included`
had turned an older remark, "One second is perfect", into an exact punch-in at
`0:31:40.500` and a 1.0 s ceiling — an instant, where the owner's own measure is
that two cuts in one silence are the same cut. It now asserts the punch-in is
in the silence before the first word, at least 50 ms clear of the words either
side, and never more than 2.0 s ahead of the first word; the Rule became `The
punch-in sits in the silence before the first word`. `The lead-in is shortened
rather than crossing into the previous block` traded its 1.0 s figure for the
same 50 ms buffer. That scenario had been green with the cut landing exactly on
the first word; it is now red until the buffer is placed, which is the honest
state. The punch-out's 1.5 s tail was left alone: the owner chose it by ear
from three real cuts and it is nowhere near a word. One step was added.

Also on 2026-10-03 the owner approved, with a plain "Yes", the When and Given
lines a run of scenarios could not be honest without, the rewording of `The
punch-out would land before the punch-in` to "no later than", and the two
`When the Recording is analysed` rewordings already made in
`block_classification.feature`. These scenarios had a Then and nothing for it to
observe, so their step definitions either acted inside the Then or asserted that
some row existed. Each now has its action: the worker draining the queue
(`Concurrency is bounded`, `Scratch fills up`, `Nothing renders without an
explicit approval`, `An archival segment needs no label`), the Processor
fetching a missing source, the preview stage, block classification after
blocking without diarization, segment proposal (four `segment_proposal.feature`
scenarios and the seeding Outline in `block_classification.feature`), the
approval rate reported over a period, a neighbouring Segment and a second
extension that would overlap it, and classification run twice with the model
reporting 0.95 and 0.10. `Silence before the first word is bounded` became a
check on a proposal that exceeds the cap, at the owner's new 2.0 s, and the
segment-proposal invariant moved to 2.0 s with it. The punch-out scenario now
says what refinement can actually return — the punch-in itself — and is fed
that answer at the stage's own seam. Several went red, every one a claim the
product does not meet: a render runs with no scratch, skipped Segments are not
marked when their source vanishes, Block confidence does not drop without
diarization and does follow the model's self-reported number, no leading-silence
flag exists, and the punch-out falls back to the end of the span rather than of
the seeding Block. Twenty-two steps were added; no scenario or Rule.

On 2026-10-05 the owner asked to cut pieces out from inside a Segment. A
Segment was one continuous span rendered straight through, and this week's
sermon opens "Good morning", then a loud bump on the podium, then the message.
Their words: "Yes, build it — marking spans by hand is enough. This will be
useful for other things too. Seminars often have large breaks, or there could be
times when there are long prayer segments with silence that we would want to cut
out. Having the ability to trim small pieces out of a message is nice. We don't
need any kind of automation with the detection pipeline right now... just being
able to do that manually would be good enough."

Nothing in the spec let a Segment be anything but one stretch, so a new file,
`features/interface/removed_spans.feature`, specifies the removed span: marked
from the playhead or by typing timecodes, listed with its length and drawn on the
waveform, restorable, strictly inside the punch points, refused rather than
merged when it overlaps another, never stranded by a boundary move (the move is
refused), locked by approval like the boundaries, untouched by analysis, logged,
and audible as a join before approval. Its eight Rules hold fifteen scenarios
(twenty-one tests). `features/processing/audio_rendering.feature` gained the Rule
`Spans the reviewer removed are left out of the output` with three scenarios:
the output omits each span, each join fades rather than clicks, and the loudness
pass measures only the audio that ships. That is **one file, eighteen scenarios
and nine Rules** added; 85 steps.

Later on 2026-10-05 the owner rendered a Segment and then wanted the podium
bump out of it, but a `complete` Segment offered no action at all. Asked whether
to add a Re-cut action for a completed segment so the bump could be removed and
the Segment approved again, they said "yes build it". `processing/reprocessing.feature`
already specified re-cutting; it said nothing about removed spans, about the
published name colliding with the Segment's own file, about skipping a re-cut,
or about cancelling its render. Four scenarios were added to `A completed
segment can be sent back for re-cutting`: `Re-cutting to take a span out`,
`Re-approving under the same label is not a name collision`, `Skipping a re-cut
keeps the MP3 already published` and `Cancelling a re-approved render goes back
to re-cutting`. `Approving the new cut` gained `And the worker renders it`, the
action its Then had nothing to observe without, the same kind of When the owner
approved on 2026-10-03. Four scenarios, no Rule, 22 steps.

On 2026-10-05 the owner asked for the list to say what each recording is,
because they were inferring it from the date and time: "Pre-Service Rehearsal",
"Theological Equipping Class - Giving", "Sunday Service - Hebrews 13:1-6". The
date stays on every row and the title does not repeat it: "Sunday Service -
Hebrews 13:1-6 would be more indicative when the date is already there." On
names: "CT is Culture and Theology. I think for the title, spelling it out looks
nicer, for more concise parts of the view, using the acronym is preferred." And
the class topic feeds the suggested label as scripture does for a sermon: "Note
that for the scripture we sub `:` for `.` since some of the platforms we use
reject `:` in filenames. So Hebrews 13:1-6 becomes Hebrews 13.1-6." Nothing in
the spec named a recording at all, so `features/analysis/recording_titles.feature`
was added: six Rules, eighteen scenarios, twenty-two expanded tests — inference
of the kind and title from text, never naming a passage the model was not shown, the glossary's two forms, a class's label, the
reviewer's title surviving analysis, the list and detail view, and the backfill.
In `features/interface/publication_details.feature`, `The label is suggested
from the classification for other content` was an `@assumption` that a lesson is
"TEC"; it is now `The label is suggested from the class for other content`,
`@stated`, with one Given saying analysis named the recording the class. Its Then
is unchanged. `A full analysis run` in
`features/analysis/analysis_orchestration.feature` gained a `titling` row, because
the walk now ends there; a table row is not a step. Eighty-three steps were added.

After the two branches met (36 files / 509 / 159 / 664, 2157 steps, recounted),
the owner answered four questions about the titles. On the joined title for a
class held before the service: "Yes, that's fine. We just need to make sure that
displays well in the list view." On "TEC - Topic" as the label style: "Yes". On
meetings and on empty recordings: "If there's a high level identification for a
Members Meeting like 'resignation' that might be helpful to find a specific one.
I would like to deemphasize recordings that are mostly silence or noise (no
identifiable spoken word or music). Show them in the list, but just make them
obviously unimportant and smaller." In `features/analysis/recording_titles.feature`
`A members meeting is named by its topic, never by a person`, `A long title
fits its row at any width` (desktop and phone) and the class-label outline's
`CT-Islam` row were added, and a Rule `A recording of silence or noise is shown,
but plainly unimportant` with `Nothing identifiable was said or played` and
`Silence sits quietly on the list`. A label typed on a Segment not yet approved
was wiped when analysis ran again, found while building titles; the owner's
coordinator asked that analysis never overwrite or drop a label a person typed,
so `A label typed before approval survives analysis` was added. Five scenarios,
one Rule, eight tests, 21 steps.

Later the same day two titles came out wrong on real recordings. A ten-minute
recording after the service was named "Sunday Service": "The 10-04 12:29 is
almost certainly the board being switched off. At about 1.5-2s there's a pop and
then nothing more for over 10m. A 10-12m recording with one piece of short noise
at the beginning is almost certainly always this exact case. The board being
shut off or some other phantom pop triggering a new recording. We should
deemphasize these and effectively archive them from the view. For this effort,
just labeling them 'Silence or noise' is fine." Its one Block was music, which
the silence rule had trusted. And the class-then-service recordings lost the
class most runs, though the joined title was already agreed. In
`features/analysis/recording_titles.feature` the silence Rule gained `The board
switched off after the service` and `Music with nothing said is not silence`; a
Rule `A class held before the service is named with it` was added with `The
joined title does not depend on how the model wrote its title` (three rows),
`The model names only the service, and is asked about the class alone` and `A
few minutes of teaching before the service is not a class`. The Background
already holds a class and then a sermon, so four existing Thens now expect the
joined title (`The kind and the title come from the model's reading of the
text`, both rows of `The glossary gives both forms`, and both backfill
scenarios); their Givens and steps are unchanged. Five scenarios, one Rule,
seven tests, 25 steps.

On 2026-10-26 the owner put the service on the public internet behind Cloudflare
Access, which `interface/authentication.feature` had ruled out ("We can start
with NoAuth"), and kept the tailnet host open because the recordings cannot be
carried through Cloudflare. That feature gained four Rules and sixteen scenarios
(twenty-six tests): a request from outside the tailnet needs a valid sign-in,
the tailnet host is the one exemption, a half-configured check refuses to start,
and who is signed in is shown, remembered and recorded. Its three old Rules
stayed and say what holds when sign-in is not configured. `DOMAIN.md` gained
`User`. Fifty-four steps were added.

Pins are now **36 files / 535 scenarios / 165 rules / 705 collected**, and
`SPEC_STEPS` is 2257.

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
