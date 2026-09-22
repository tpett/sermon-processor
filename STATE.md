## SLICE 3.1 — the machine proposes, and the error is measured (2026-09-22)

`sermon-propose <recording-id> --corpus <experiments/data> --summaries none` drives
the real pipeline from a stored transcript through `qwen3.6:35b-mlx` on mac-m1 and
prints the signed error against `groundtruth.json`. No test flag in the path.

**It reproduces `FINDINGS.md`'s `u3` row cell for cell** on the eight dev
recordings: found 100%, both boundaries within 1 s 12%, 2 s 25%, 5 s 62%, median
punch-in **2.20 s**, median punch-out **0.30 s**. Six of eight punch-ins match the
stored `u3` artefact to the millisecond.

### The finding that matters more than the number

**The classifier is not reproducible.** Three runs of an identical command on
`recording_20260510_102947` — same stored transcript, same prompt, `temperature 0`,
`seed 0` — verified by hand:

```
run a   punch-in 1562.700   error -73.196 s
run b   punch-in 1635.800   error  -0.096 s
run c   punch-in 1562.700   error -73.196 s
```

The model returns a different block table for byte-identical input — 13 blocks with
the sermon at 1635.8 s, or 12 with it at 1562.7 s. Across all eight, a second pass
gave found 88% and median punch-in 4.64 s against the first pass's 100% and 2.20 s.

**That spread is as large as the gaps `FINDINGS` uses to rank configurations**
(`u3` 2.20 s, `T0 rules` 3.76 s, `C frontier` 4.64 s), so the ranking may not be a
ranking — and the 19.6 s mlx-versus-faster-whisper divergence attributed to the
transcript engine is plausibly the same phenomenon. Filed P0. Do **not** re-run the
held-out split to chase it; `test_access.log` records one shot per configuration.

### State of the suite

`tests/test_spec.py` **247 passed / 350 failed / 7 skipped**, down from 305 passed.
**58 scenarios went red, 0 became passing, 0 errored.** Their Givens injected a test
hook or relied on a fabricated transcript; `TranscribesRecording` now raises rather
than inventing one, so runs stop before the stage the Then asserts on. The remaining
work is mechanical: stage a real transcript in those Givens.

31 reads and 6 writes of test-injected store attributes are gone from
`src/sermon/analysis/` and `jobs/analyzes_recording.py`, with an AST guard that
fails on any return, by attribute access or `getattr`. **Three remain** in modules
this slice did not own — `discards_recording.py`, `sends_notification.py`,
`runs_queued_jobs.py` — filed P2.

### Provisional and absent

- **Cut difficulty is a proxy.** The corpus grades from the audio envelope; this
  path has no audio, so `grades_cut` measures inter-utterance quiet. The CLI prints
  the corpus label beside it so disagreement is visible.
- **No cue-based fallback classification.** `_type_from_transcript` was not ported —
  its `LESSON_LEAD_IN` could move a derived punch-in, and the rules rung is the one
  `FINDINGS` records collapsing on held-out data (3.76 → 221.14 s).
- **Diarization has no producer**; it reads a stored artefact or raises. `FINDINGS`
  records it reaching scored output only via the `structured` strategy, unused here.
- **The Members Meeting is still wrong.** Run 1 proposed 2628 s against a 3594 s
  human segment (−965 s); run 2 did not overlap the truth at all. `FINDINGS` says
  only the frontier control declined it correctly. `discarding_recordings.feature`
  and `approval_notifications.feature` both assume nothing-publishable means no work
  and no notification, and on this evidence they will not hold.

## SLICE 2 is done — a publishable MP3 from real audio (2026-09-21)

Verified on `recording_20260913_090014`, the 3h 3m class-plus-service recording,
cut at the sermon boundaries `segment_review.feature` gives for that date.
**The human listened: "sounds good and the cut points are solid."**

```
fetch   1456376029 bytes, 10990.0 s, 2ch 44100 Hz, -22.6 LUFS, 0.4 dBTP, 18.6 LU
        channel 1 -25.8 dB RMS, channel 2 -90.4 dB  ->  signal on channel 1
        warning: source clipping detected
render  2026-09-13 - Hebrews 12.25-29.mp3   38,556,488 bytes over 2943.0 s
        -17.6 LUFS, -1.0 dBTP, 104 kbps, mono 44100 Hz    on target, exit 0
store   Artifact  input -22.75 LUFS, output -17.6 LUFS, peak -1.0 dBTP
        Segment   sermon 6967.0 -> 9910.0, label, date, boundary_source=human
```

Two spec behaviours fired on real material for the first time: the **dead second
channel** was detected and channel 1 chosen rather than averaged (which would have
cost 6 dB), and **`source clipping detected`** came from a measured 0.4 dBTP rather
than from a test flag.

**Commands.** `sermon-fetch <recording-id>` then
`sermon-render <recording-id> --from 1:56:07 --to 2:45:10 --label "..." --date YYYY-MM-DD`.
Run from the directory holding `.env`. An off-target render exits 1 — that alarm is
the guarantee that the manual process, which once shipped a file 9 LU quiet, lacked.

**Loudness is 6-11 LU louder than the back catalogue** (-17.6 against -23.9 to
-28.5). `FINDINGS.md` predicted new files would be dramatically louder; the human
has now heard one and approved it, so that question is settled.

### Two defects this slice found, neither visible to the suite

**A stale schema was accepted silently and failed after 49 minutes of ffmpeg.**
`opens_store` now compares `PRAGMA table_info` against the columns the entities
declare and refuses at open, naming what differs in both directions. No migration
machinery — `sermon-reconcile` rebuilds every row in seconds. This had been filed
as a speculative P3 in the backlog and was the first thing to break.

**`audio_rendering.feature` asserted a true-peak ceiling no render has ever met.**
Ours measured -0.98 dBTP; the six validated renders measured -1.1, -0.8, -1.0,
-0.8, -0.6, -0.7, and the hand-made back catalogue was mostly above -1.5 too.
-1.5 is what loudnorm is **asked** for pre-encode; LAME's lossy reconstruction
overshoots. The spec documents this distinction correctly one scenario earlier for
loudness and had it wrong here. It now asserts **-0.5 dBTP measured on the decoded
MP3** and says which signal it means; `renders_mp3`'s own verdict was aligned to
match. **`TARGET_TP` stays -1.5** — do not "fix" it.

`audio_rendering.feature`'s 20 scenarios remain red. Its Background fixes punch
points at 2:00:20-2:43:32, so honest step definitions need a 2h43m source rendered
per scenario. That is a bead of its own; the code satisfies the feature as a
specification, and the numbers are properties of real programme material rather
than of synthetic audio.

## SLICE 2 is done — a cut by hand renders (2026-09-21)

**There is a playable MP3, cut at boundaries a human chose.** Verified end to end
with no bucket involved, against a locally generated 31-minute stereo FLAC with a
dead channel:

```
$ sermon-fetch recording_20260823_103015
recordings/recording_20260823_103015.flac -> recordings/recording_20260823_103015.flac
116135338 bytes, 1900.0 s, 2 channels at 44100 Hz
-29.8 LUFS integrated, -14.9 dBTP true peak, 1.8 LU range
channel 1: -29.286828 dB RMS
channel 2: -120.0 dB RMS
signal on channel 1

$ sermon-render recording_20260823_103015 --from 0:02:00 --to 0:28:30 \
      --label "Hebrews 12.4-11" --date 2026-08-23
2026-08-23 - Hebrews 12.4-11.mp3 -> .../data/2026-08-23 - Hebrews 12.4-11.mp3
17798148 bytes over 1590.0 s
-16.0 LUFS integrated, -1.4 dBTP true peak, 89 kbps, 1 channel at 44100 Hz
input was -29.84 LUFS
off target: true peak -1.4 dBTP exceeds -1.5
off target: bitrate 89 kbps is outside 96-108
```

Probe 7 s, a 26.5-minute cut in 40 s, peak RSS 78 MB against a 116 MB source.
**Both off-target lines are the synthetic source, not the chain** — narrow-band
synthesised speech encodes below 96 kbps and overshoots the ceiling by 0.1 dB on
this material; the same command on a 3-minute span of the same file landed the
true peak at exactly -1.5. The real corpus measured 96-108 kbps. That is the
point of printing them: the command exits non-zero rather than looking like a
success, which is the failure the manual process had.

**`0:00:00` on the detail page is fixed.** Nothing had ever probed a recording;
`MeasuresRecordingAudio` now does, reusing the validated `probe_format` and
`probe_loudness` unchanged and adding one `astats` pass for the per-channel RMS
that decides which channel carries signal.

**The fetch never buffers a recording.** `FetchesBucketObject` reads one named
object in 8 MiB chunks straight into the destination file, digesting as it goes,
and `DownloadsRecording` hands it the destination rather than taking bytes back.
There is still no write path: the AST guard that pinned `get_paginator` as the
only method asked of the client now admits `get_object` beside it and nothing
else, and the write-operation guard is untouched.

**What the render actually guarantees.** One channel taken, never downmixed, at
the channel the probe named; the approved span within 100 ms; one loudness stage
that measures then corrects with no separate compression; short fades both ends;
`-q:a 3` VBR; mono 44.1 kHz; the filename from `names_rendered_mp3`; and the
measured input loudness, output loudness and output true peak recorded on the
Artifact beside the settings the render was given.

**What it does not guarantee, honestly.** `-17 LUFS within 1 LU` and
`96-108 kbps` are properties of real programme material, not of the chain: the
achieved loudness is `-1.5 - crest factor` whenever loudnorm falls back to
dynamic mode, so a synthetic source lands wherever its crest factor puts it. The
suite therefore asserts the mechanism and the render's own verdict on itself; the
numbers are verified by running the command on a real recording. Nothing in
`tests/` needs the bucket or the tailnet.

**Two hooks removed, and no scenario changed verdict.** `renders_segment` no
longer sets `store._source_was_clipped` and `records_publication_details` no
longer sets `store._filename_collision`. The clipping step now asserts the
Recording's own warning; the collision step asserts the refusal the caller
actually caught, through a `target_fixture` rather than a flag on the store. Both
scenarios were already red and stay red for their real reasons — the clipping one
needs a Segment-level record the vocabulary does not hold yet.

**`audio_rendering.feature` is still entirely red, all 20 scenarios, exactly as
it was.** Its Background fixes punch points at 2:00:20 and 2:43:32, so
implementing it honestly needs a 2h43m source generated and a 43-minute span
rendered per scenario. That is a bead of its own, not a side effect of this one.
The feature was read as the specification for the code, which is what the
implementation satisfies.

## SLICE 1 is done — the corpus is visible (2026-09-21)

`sermon-reconcile` then `sermon-serve`, against the real bucket:

- **93 recordings discovered, 0 skipped**, all in `discovered`, all
  `started_at_source='key'`, 2026-03-11 .. 2026-09-20 — matching the bucket exactly.
- The list page renders real dates newest first, paginated at 50, which
  `recording_list.feature` requires. Detail pages return 200.
- Durations show `0:00:00` because nothing has probed yet. Honest, not a defect.

**The object store is `s3.home.tpett.me`, path-style, region `garage`.**
`garage.home.tpett.me` fronts a Garage endpoint that rejects S3 API routes, and
virtual-host addressing cannot work — Caddy serves no wildcard certificate.
Credentials live in a gitignored 0600 `.env`; `data/` is gitignored too.

**The bucket holds 93 objects, 39.1 GiB, every one a `.flac`, and no sidecars at
all.** Three consequences: `recording_download.feature`'s preamble says 85 objects
and is stale; every start time therefore comes from the key, which is what
`started_at_source` exists to record; and no real key exercises the
"key does not match the pattern" skip reason, so that branch needs a unit test.

**Two defects only running it could find.** `creates_app` defaulted its object
store to the in-memory `FetchesObject` test double — the fake was the shipped
production default. And `sermon-serve` returned 500 on every page from SQLite
objects crossing threads, invisible to the entire suite because `test_client`
runs in-thread: a green suite against an app no browser could load. This is the
case for the slice rule — done means an artifact inspected outside the test suite.

Three scenarios went red when this slice's four test hooks were removed, and stay
red honestly: the health view never measured disk. One was deliberately left
failing rather than made green while half its chain is still hook-driven in a
module slice 1 does not own.

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
