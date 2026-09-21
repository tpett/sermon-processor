## The branch's real state (2026-09-21)

`tests/test_spec.py` reports **308 of 604 scenarios passing**, 288 failing as
undefined, 1 failing on the diarization contradiction, 7 `@deferred`.

It briefly reported 596 passing. That was not true: 534 of 1,641 step definitions
asserted nothing — empty `Then`s, `Then`s that ran code and never checked it,
`assert True`, `x or True`, and `assert <name taken from the Gherkin>`. 233 of 456
scenarios rested on one, and 143 had no surviving `Then` at all. Those definitions
are gone, so the scenarios fail as undefined: **not implemented, rather than
falsely implemented.**

`tests/step_integrity.py` now makes that impossible to repeat. Every `Then` must
assert; every `When` must act; an empty `Given` must be enumerated with a reason;
assertions that cannot fail are refused; `skip`/`xfail` are banned in any step; a
bare `@step` is refused so the `Then` rule cannot be dodged by re-decorating; and
the static read is cross-checked against what pytest_bdd actually registered.
Run it with `.venv/bin/python tests/step_integrity.py`; `tests/step_integrity_report.md`
is regenerated and a test fails if it drifts.

**The hole it cannot close**, and the reason `sp-dzc` exists: a `Given` that
fabricates into a `target_fixture` and a `Then` that reads that fabrication is a
closed circuit with no product code in it. `interface/waveform_steps.py` had
exactly that shape. Mutation is the only backstop — weaken what a step claims to
cover and confirm the scenario fails.

Survivors by subsystem: analysis 164, interface 78, ingestion 24, operations 18,
notifications 14, **processing 7**. Processing is the thinnest and the number to
distrust next.

# Where this project stands

Last updated 2026-09-20. Read this first; it is the handoff.

**The specification is done for v1, and the stack is chosen. See
[ARCHITECTURE.md](ARCHITECTURE.md).**

Python throughout: the existing pipeline extracted into a package, Flask as a
thin API, a `Job` table rather than a broker, SQLite and files, a vanilla
ES-modules client, and `pytest-bdd` running the 460 Gherkin scenarios from
`features/` (604 tests once Outlines expand). Reasoning stays on mac-m1 over
HTTP.

Work is on `tpett/ai/v1-build`. Do not merge to `master` from this handoff.
Beads (`bd`) is the ledger; it was behind the code until 2026-09-20 — read
comments on `sp-3wf` / `sp-b41` rather than `bd ready` for what actually landed.

## What exists

The three-click week is a real path on this branch: webhook → download (with
retry) → analyze → HTML list/detail → publication label → approve → named MP3.
`tests/test_three_click_week.py` asserts the file, size, and ID3/MPEG headers.

| | |
| --- | --- |
| `features/` | 34 Gherkin feature files, the behaviour specification |
| `src/sermon/` | Application: store, jobs, analysis stages, Flask, vanilla client |
| `src/sermon/pipeline/` | Extracted spike library — frozen unless instruments run |
| Ingestion Gherkin | 38 passed (`pytest tests/test_spec.py -m ingestion`) |
| Analysis Gherkin | 285 passed, 5 skipped, 1 failed of 291 (`-m analysis`) |
| Processing / interface / notifications / ops | remaining edge Gherkin now green except the analysis diarization contradiction |
| `experiments/` | Frozen spike. Do not refactor it or hold it to TDD. |
| `experiments/FINDINGS.md` | Every number in the spec traces here. |
| `~/Desktop/Sermons` | Ground truth. Read-only except adding new source/edit pairs. |

The one remaining analysis failure is a spec contradiction, not missing code:
`analysis_orchestration.feature` lists diarization as a stage whose permanent
failure puts the Recording in `analysis_failed`; `speaker_diarization.feature`
and `blocking.feature` say Analysis continues without speaker evidence.
Implementation follows the continue path.

**Not done.** Most of `features/processing`, `features/interface` beyond the
review happy-path, phone, waveform editor, 2-year retention, and the
`@deferred` scenarios. Measured loudness on a render (`sp-xx2`) and a discard
reason (`sp-9w3`) are still missing fields. Per-Rule bead decomposition
(`sp-3wf.1` and siblings) was skipped; work went against the suite.

Derived data (transcripts, diarization, blocks, audio) is gitignored and
reproducible from `experiments/src` plus the sources in `~/Desktop/Sermons`.

## What the spike established

- **A 21 GB local model matches a frontier control at finding the sermon.**
  Held on three independent evaluation splits. Hand-tuned rules did not — they
  collapsed from a 3.8 s median error to 221 s on unseen data.
- **One loudness operation replaces normalize-then-compress.** Week-to-week
  spread falls from 4.6 LU to 0.6 LU; loudness range from 12–15 LU to 6.7–8.3.
- **A 2.5 GB model is enough for summaries and preview excerpts** — 0.8 s per
  block — though it is useless for choosing which block is the sermon.
- **Model self-reported confidence is a constant** (0.95 on a correct answer and
  on a 659 s error alike). **Cross-model agreement is the real signal.**
- **On three blind recordings, three weeks running, the pipeline produced a cut
  the reviewer approved by ear** — 08-30, 09-06 (published unedited) and 09-13.
  A second reading of each transcript agreed to within 0.21 s, 0.04 s and 0.02 s
  on the punch-in. **That second reading was not an independent control** — see
  the correction at the end of FINDINGS — so the reviewer's confirmation is the
  load-bearing evidence, not the agreement. Rehearsals and empty rooms were
  declined every time.
- **A class and a service in one three-hour recording produced both Segments
  correctly** (2026-09-13), once two bugs that only this shape could expose were
  fixed. It is the only recording shape the corpus has seen just three times.
- **The emptiness gate works unsupervised.** It rejected a 10.9-minute empty-room
  recording (3.7 dB dynamic range) before any expensive stage ran.
- Diarization helps *selection*, not *precision*. Its edges were the worst
  boundary source measured.

## What is not established

- **Nothing has run on the deployment box.** Every timing is a 128 GB M5 Max with
  Apple-Silicon-only tooling. The homelab server has little GPU.
- **`no_edit@1s` is 0% on held-out for every configuration**, including the
  frontier control. At 5 s the best is 71%.
- **There is no clean evaluation data left.** dev (8) is tuned to exhaustion;
  held-out (now 19, having absorbed 2026-08-30) has been scored twice — once on
  2026-08-29 and again on 2026-09-07 for the punch-out tail — and fresh (6) once.
  Further tuning needs new recordings or k-fold across all 33.
- Classes are the weak spot: every configuration runs 60–90 s late on them. The
  2026-09-13 class was an exception (punch-in at 0:00), but it opens directly on
  "welcome to our theological equipping class" where 08-02 opens with several
  minutes of gathering — an easier instance, not a solved problem.

## Decisions — all settled

Nothing in `features/` carries `@needs-decision` any more. Four scenarios carry
`@deferred`: specified, understood, and deliberately out of v1.

| | |
| --- | --- |
| The acceptance bar | **There isn't one.** The suite is a regression instrument; a human approves every cut. A 1.0 s leading-silence cap and signed punch-in error became assertable in its place. |
| Authentication | **None.** The tailnet is the perimeter, as it already is for the recorder and the object store. |
| The punch-out tail | **1.5 s**, chosen by ear against 0.0 s and 3.5 s. |
| A second opinion | **Not in v1.** "We can always refine the process later." |
| Hard delete | **Not in v1.** `discarded` keeps everything; the source object is never touched. |
| Playback speed | **Not in v1.** Single-speed playback. |
| Speaker capture at approval | Specified in `segment_review.feature`; it is how a guest who asked not to be published is caught. |
| Special services | A **Recording kind**, not a Block type. Settled by the vocabulary pass. |
| The back catalogue | New output is 7–11 LU louder than the archive. Re-render or accept the step change — a publishing question, not a build one. |
| The loudness itself | `experiments/work/ab/` holds four A/B clips, still unheard. |

**What deferring the second opinion costs, stated once so it is not a surprise.**
Cross-run agreement was the strongest confidence signal measured, and the
2026-09-17 engine trace showed why: of eight recordings, the one whose final cut
differed materially was a 19.6 s disagreement between two runs on near-identical
transcripts. Nothing distinguished it from the six that were right. In v1, cut
difficulty is the signal that asks the reviewer to listen, and a confidently
wrong boundary looks like a confidently right one. It is safe to add later — the
second analysis reads the same frozen transcript, so it is an added stage rather
than a change to an existing one.

## Where things run — settled 2026-09-17

```
app server (linux, docker, little GPU)        mac-m1 (M1 Max, 64 GB)
  ingest, envelope, probe, waveform             ollama 0.34.0
  preview, TRANSCRIPTION, DIARIZATION   ──API──▶ qwen3.6:35b-mlx  (classification)
  segment derivation, render                    qwen3:4b          (summaries, to pull)
```

- **HTTP only.** The app holds no credentials for mac-m1 and never opens a shell
  on it. `analysis_orchestration.feature` asserts this.
- **mac-m1 serves ollama and nothing else.** It is also the owner's active dev
  machine. `OLLAMA_HOST=0.0.0.0:11434` is set in
  `~/Library/LaunchAgents/sh.brew.ollama.plist` (backed up beside it), and the
  macOS firewall allows the binary at
  `/opt/homebrew/Cellar/ollama/**0.34.0**/libexec/ollama` — **a version-pinned
  path that a `brew upgrade` will invalidate, silently.** Connections then hang
  rather than refuse.
- **Transcription cannot be delegated to ollama.** Its
  `/v1/audio/transcriptions` endpoint exists but has no model behind it, on
  0.32.15 and 0.34.0 alike.

### Verified 2026-09-17 against the real production box

`nas` is an **AMD Ryzen 7 9700X** (8C/16T, x86_64), 30 GiB RAM with ~19 GiB
available, Arch + Docker on ZFS. **No GPU of any kind** — nothing in
`homelab/docs` or any compose file references one.

- **`nas` reaches mac-m1's ollama**: `curl http://100.88.211.71:11434/api/version`
  → `{"version":"0.34.0"}`.
- **So does a container on the `proxy` network**, which is the one that mattered
  and was not obvious — Docker bridge traffic routes out through the host's
  tailscale interface with no extra configuration.
- x86_64 means CTranslate2 and `sherpa-onnx` both have manylinux wheels.

Deployment follows the `workouts` precedent in `~/Source/personal/homelab`:
a config-only `stacks/sermon-processor/` building from `./src`, with
`bin/nas app-deploy` git-archiving this repo's HEAD onto the server. Caddy route
rather than published ports; recordings are large, so a dedicated ZFS dataset
(`zfs create` needs sudo — Travis runs it); Garage credentials via
`bin/nas secrets push`.

### The open risk this creates

Transcription must therefore run in the app container, on Linux, **without mlx**
— and every boundary number in FINDINGS was measured on mlx word timestamps that
punch-ins snap to. faster-whisper or whisper.cpp use the same weights and a
different alignment. **Nothing is known about how far the boundaries move.**
Measuring that is the next task, and it needs no machine but the laptop.

`sherpa-onnx` is not affected — it ships manylinux wheels for x86_64 and aarch64,
so diarization ports unchanged.

## The interface

139 scenarios across 9 files in `features/interface/`. The core claim is the
three-click week — preview the punch-in, preview the punch-out, approve — with
the waveform editor available and not required. A cut graded `hard` deliberately
interrupts that path and opens the editor ready for the adjustment.

`waveform_review.feature` and `punch_point_adjustment.feature` carry the design
the Punch Point Editor spike settled, as prose: two linked views rather than one
zoomable one, zoom as named steps rather than a slider (precision has a cliff —
100 ms is 3.7 px at a thirty-second window and 36.7 px at three seconds), the
transcript belonging to a different step from the waveform, and a readout that
says where the boundaries are and never how right they are.

One thing from that spike is deliberately excluded: it showed each boundary's
distance from the known human cut, which is an instrument for judging the machine
and has no counterpart in use. In production nothing exists to compare against
until the reviewer moves something.

## Work queued, in order

1. **Three concept-level passes** the second audit identified. Each needs one
   sweep across every file, not a patch — patching is what produced the second
   audit round.
   - **Confidence** is still load-bearing in eleven files, including a
     *confidence floor* that would threshold a constant. `classification-spec.md`
     still demands it in the output schema.
   - **The type table.** Block types, Segment classifications, which types seed a
     Segment — specified four ways that disagree. `music` Segments are impossible
     to produce yet three interface Backgrounds depend on them.
   - **The state machines.** `ignored`, `blocked`, `recut`, revert and cancel are
     asserted by features and absent from the README diagrams. Some states have
     no exit: a Recording parked in `discovered` for want of disk is never
     retried, because reconciliation only creates Recordings for keys it has
     never seen.
2. **Run one recording end to end on the homelab box.** Possibly a purchasing
   decision; every performance claim is conditional on it.
3. **Then build.** The technology is de-risked. More tuning against 33 recordings
   produces findings like the `"chapter"` cue bug — invisible on dev, damaging on
   real data. The way to get more data is to run this weekly, where every
   approval becomes a labelled example for free.

## Things that will bite whoever picks this up

- **`~/Desktop/Sermons` is the only copy of the ground truth.** Read-only except
  for adding new source/edit pairs. Two files of identical byte size break the
  bucket join, which matches by size. **As of 2026-09-07 macOS denies this path
  to the agent** ("Operation not permitted" on any read); blind-run sources were
  pulled from S3 into `experiments/work/incoming/` instead, and the 2026-09-06
  `groundtruth.json` entries point there rather than at the Desktop.
- **The recorder's first upload is 11 March 2026.** Anything older has no source.
- **The pre-S3 archive is already-edited** — lossless copies of just the message.
  As ground truth they would teach that a sermon starts at the beginning of its
  file. `verify.py` fails on any recording whose output covers >95% of its source.
- **Some published outputs are machine cuts, not human edits.** 2026-09-06 was
  approved and published exactly as the pipeline produced it. That is a result
  worth having — but aligning it would make the system its own yardstick, so
  `align.MACHINE_CUT_MP3S` excludes it by filename. **Add to that set whenever a
  proposal ships unedited**, or the corpus quietly starts grading itself.
- **Three early recordings run about −130 ppm off** against their exports. Real,
  measured, and corrected by fitting a line through five alignment probes.
- **Everything in the bucket is 32-bit**, not 24. The spec said 24 in five places
  and was wrong.
- `experiments/data/test_access.log` records every held-out scoring run. One shot
  per configuration; honour it.

## Artifacts

Two published pages, both private:

- **Sermon Processor Spike Report** — findings and the decisions
  https://claude.ai/code/artifact/ab2df262-1a76-491d-80d8-10ee8ebe8142
- **Punch Point Editor** — the working waveform interface on real data
  https://claude.ai/code/artifact/af90f496-34e7-442f-b124-6b4df91b0a46

Live watches on both have ended; republishing from a new session needs the URL
passed explicitly or it creates a separate artifact.
