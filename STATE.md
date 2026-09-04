# Where this project stands

Last updated 2026-09-04. Read this first; it is the handoff.

## What exists

**Nothing is built.** There is a specification, an experiment that tested whether
the specification is buildable, and a corpus of real recordings with ground truth.
No application code.

| | |
| --- | --- |
| `features/` | 34 Gherkin feature files, the behaviour specification |
| `features/QUESTIONS.md` | 78 design questions and the owner's answers — the source of most decisions |
| `features/AUDIT.md` | Two rounds of reconciling the spec against measurement. **Section E and the second-pass list are the open decisions.** |
| `experiments/` | The spike: alignment, transcription, diarization, classification, rendering |
| `experiments/FINDINGS.md` | The running record. Every number in the spec traces here. |
| `experiments/data/groundtruth.json` | 33 recordings, 31 labelled segments. The yardstick. |

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
- **On a blind recording, both models landed within 0.21 s of the human punch-in**
  and both correctly declined the band rehearsal beside it.
- Diarization helps *selection*, not *precision*. Its edges were the worst
  boundary source measured.

## What is not established

- **Nothing has run on the deployment box.** Every timing is a 128 GB M5 Max with
  Apple-Silicon-only tooling. The homelab server has little GPU.
- **`no_edit@1s` is 0% on held-out for every configuration**, including the
  frontier control. At 5 s the best is 71%.
- **There is no clean evaluation data left.** dev (8) is tuned to exhaustion,
  held-out (14) and fresh (6) are each spent once. Further tuning needs new
  recordings or k-fold across all 33.
- Classes are the weak spot: every configuration runs 60–90 s late on them.

## Open decisions — nothing proceeds far without these

1. **The acceptance bar.** `no_edit@1s ≥ 80%` is unreachable. Is the bar 1 second
   always, or 1 second on clean cuts with honest flagging on hard ones? This
   blocks `detection_accuracy.feature` from working as a regression gate.
2. **Authentication.** `authentication.feature` is `@needs-decision` throughout
   while every other interface file assumes a signed-in reviewer. Blocks the
   interface entirely.
3. **The punch-out tail.** Stated preference (cut immediately after the last
   word) contradicts measured behaviour (a deliberate 1.0–1.9 s silent tail on
   22 of 24 segments). Which wins?
4. **Speaker capture at approval.** Surfacing who preached is the only defence
   against publishing a guest who asked not to be. It reopens "nothing more is
   collected".
5. **Special services.** Good Friday and a Saturday prayer gathering currently
   land in `other`. Own types, or `other` plus a good summary?
6. **The back catalogue.** New output is 7–11 LU louder than everything published.
   Re-render the archive, or accept the step change?
7. **The loudness itself.** `experiments/work/ab/` holds four A/B clips, unheard.
   A is the new pipeline, B is the hand-made one.

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
  bucket join, which matches by size.
- **The recorder's first upload is 11 March 2026.** Anything older has no source.
- **The pre-S3 archive is already-edited** — lossless copies of just the message.
  As ground truth they would teach that a sermon starts at the beginning of its
  file. `verify.py` fails on any recording whose output covers >95% of its source.
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
