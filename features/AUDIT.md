# Feature File Audit

**Status: A and B applied, C and D applied. E is open and needs your answers.**
See the commit "Reconcile the specification with what the spike measured".

Written 2026-08-30, after the spike. These files were authored before anything
had met real audio. Six weeks of measurement later, some of what they assert is
wrong, some rests on signals that turned out not to exist, and the corpus
surfaced cases they have no scenario for.

Ordered by consequence. Each entry says what the file claims, what was measured,
and what should change.

---

## A. Contradicted — the spec asserts something the measurement disproved

### A1. Confidence bands rest on a signal that is a constant
`analysis/analysis_confidence.feature`

The file builds the reviewer's whole triage experience on a numeric confidence:
bands at 0.92 / 0.65 / 0.31 mapping to "Looks good" / "Worth a listen" / "Needs
attention", and a rule that low confidence prompts the reviewer differently.

**Measured: model-reported confidence is 0.95 on essentially everything** —
including a segment whose punch-in was wrong by 659 seconds, and a correct one,
in the same run. It carries no information.

Two signals that *do* work were found instead:

- **Cross-model agreement.** On the blind recording two independent models chose
  the identical punch-in to the sample, and the cut was right. Across the whole
  project, failures have been cases where models disagreed with each other or
  with the truth.
- **Cut difficulty**, already computed and stored on every boundary from the
  silence around it, and never used in any reporting.

**Change:** replace the numeric bands with agreement-and-difficulty. The
reviewer-facing behaviour the file describes is right; the thing it keys off is
not.

### A2. Boundary refinement is described as authoritative. It should be a fallback.
`analysis/punch_in_detection.feature`, `punch_out_detection.feature`,
`segment_proposal.feature`

Throughout, the model proposes a rough span and the refinement rules determine
the boundary. Nothing in any file describes the model's own boundary as the
answer.

**Measured, on the frontier control:**

| | refined by the rules | the model's own |
| --- | --- | --- |
| median punch-in | 4.64 s | **2.18 s** |
| median punch-out | 1.24 s | **0.78 s** |

On one recording the model was **0.08 s** from the human cut and refinement moved
it five seconds away. The rules earn their place in exactly two situations: a
class, where they turned +118 s into −5 s, and one recording where the model was
badly wrong.

**Change:** the model's boundary leads; refinement runs only when that answer is
implausible. This is already how the harness works and the spec has never said it.

### A3. Speaker change is a good signal and a poor boundary
`analysis/blocking.feature`

The file makes speaker change the primary mechanism for drawing block edges.

**Measured — distance from the nearest proposed edge to the true punch-in:**

| Blocking source | median | within 5 s |
| --- | --- | --- |
| a model reading the transcript | 1.8 s | 6/8 |
| **diarization edges** | **8.5 s** | **1/8** |

Diarization was the *worst* boundary source tested. It is excellent at saying
*that* the speaker changed and unreliable about *when*. Two further facts belong
in the file: the clusterer returns 12–27 speakers for a service with four unless
the merge threshold is raised, and block assembly needs iterative smoothing or a
preacher's short opening turns get absorbed backwards into the scripture reading,
moving the edge 40 s.

**Change:** speaker change informs *which* block is which; the transcript
determines *where* the edge falls.

### A4. The emptiness threshold was guessed and the guess is the wrong measure
`analysis/audio_probe.feature`, `interface/discarding_recordings.feature`

The files test "proportion above the noise floor", flagged `@assumption` with a
note that the corpus had no examples.

**Measured on six real false triggers pulled from the bucket:**

| | dynamic range | active |
| --- | --- | --- |
| false triggers | **3.6 – 3.9 dB** | 0.0 – 0.2% |
| real recordings | **52 – 79 dB** | 65 – 85% |

**Dynamic range alone separates them, by three orders of magnitude.** No tuning,
no threshold to argue about, and it runs on the envelope already computed for the
waveform — before transcription, so a false trigger costs no GPU time.

**Change:** state the rule as dynamic range, and drop the `@assumption` tag. Q78
is answered.

### A5. The sidecar does not exist
`ingestion/recording_download.feature`, `webhook_notification.feature`

The download feature is written around fetching a `.meta.json` sidecar, with
"sidecar missing" as an edge case.

**Measured: there are no sidecars in the bucket at all.** 85 objects, all `.flac`.
The recorder writes one locally; it is not being uploaded. Every field the spec
wanted from it is recoverable from the object key and the audio itself.

Also: the checksum available on the S3 path is **MD5** (the ETag), not SHA256.

**Change:** the object key is the source of truth for recorded time; the sidecar
becomes an optional enrichment, not the primary path. And it is worth telling the
recorder side that the sidecar never arrives.

---

## B. Missing — real cases with no scenario

### B1. Cross-model agreement as the confidence mechanism
Nothing in the spec. See A1. This is the mechanism that makes
`analysis_confidence.feature` implementable at all.

### B2. Clock drift between a source and its export
Three recordings drift **−130 ppm** against their published MP3s — a capture
clock at ~44,094 Hz labelled 44,100. Over a 50-minute sermon that is 0.23 s.

Nothing in the spec anticipates that a source and an edit can run on different
clocks. It matters for `detection_accuracy.feature`, which derives ground truth by
alignment, and for any ingest of archive material.

### B3. Already-edited sources
The pre-S3 archive contains lossless copies of *just the message*. As ground truth
those are actively harmful: punch-in 0, punch-out end, teaching that a sermon
starts at the beginning of its file.

`detection_accuracy.feature` needs a guard: a recording whose published output
covers more than ~95% of its source is either already edited (unusable) or a
legitimate untrimmed archive (usable, but excluded from boundary statistics).

### B4. A damaged container that still decodes
`recording_20260403_123524` returns `N/A` for duration — a damaged FLAC header —
but decodes fine. `audio_probe.feature` covers "not decodable audio" and this is
not that. The ingest path should count samples and flag, not fail.

### B5. Band rehearsal as a first-class thing
`block_classification.feature` has `music`. But **an entire recording of
rehearsal is the largest unpublished category** — 8 of 20 sampled, 20–68 minutes,
63–76 dB, in the same room with the same voices. It is the case most likely to
produce a false positive and it is materially different from "there is singing in
this service".

### B6. Services that are not Sunday services
The bucket contains a **Good Friday Tenebrae service** (51 min, "readings, songs
and explanations") and a **Saturday worship and prayer gathering** with sermons
and personal testimonies. Both currently classify as `other`, which tells a
reviewer nothing.

Q73 asked whether the taxonomy covered everything and was answered against a
corpus containing none of these.

### B7. One event, several recordings
Good Friday produced four recordings across a day; the Saturday event produced
four. Every feature file assumes a session lives inside one recording, or that one
recording holds several sessions. Neither covers one session spanning several
recordings — which Q65 put out of scope for *joining*, but the reviewer still has
to understand what they are looking at.

### B8. The back catalogue will not match
New output sits at −17 LUFS; published files run −24 to −29. Every new sermon will
be **7–11 LU louder** than everything before it. `audio_rendering.feature` has a
scenario warning the reviewer, but nothing describes what happens to the archive.

---

## C. Now decidable — the spec left these open and measurement settled them

| Question | The spec says | Measured |
| --- | --- | --- |
| **Q77** preview format | "the mechanism is chosen for simplicity" | CBR MP3 + HTTP range: **0.04 s** worst seek fetching **0.16%** of the file, one file against HLS's 628 |
| **Q78** emptiness | a guessed 1% threshold | dynamic range under 15 dB, three orders of magnitude of separation |
| **Q13 / Q76** models | deferred to a spike | a 21 GB local model matches the frontier control on selection; a **2.5 GB** model is sufficient for summaries and cue excerpts |
| **Q49** compression | "confirm it is not needed" | loudness range 12–15 LU falls to 6.7–8.3 LU with **no compressor** |
| **Q18** tail | ~~a guess of 1.5 s~~ **settled at 1.5 s, 2026-09-07** | the true punch-out sits **1.0–1.9 s after the last transcribed word** — a deliberate silent tail, chosen by ear over 0.0 s and 3.5 s alternatives |

Each of these should move from `@assumption` / `@needs-decision` to a stated,
measured rule with the number in it.

---

## D. Smaller corrections

- `analysis/transcription.feature` flags low quality when average ASR confidence
  is below 0.5. Never validated; the corpus never produced it.
- `punch_in_detection.feature` asserts specific confidence values (0.8, 0.5) that
  are unmeasurable given A1.
- `analysis_orchestration.feature`'s stage list predates the `preview` and
  `summarization` stages, both of which now exist and are validated.
- `waveform_review.feature` should state what the spike measured: a two-stage zoom
  is necessary and sufficient (100 ms is 0.0 px across a whole recording and
  36.7 px at a 3-second window), words are useful at 10–60 s and useless at the
  cut itself, and peaks are ~2.76 MB per recording so they must be fetched rather
  than inlined.
- `summarization.feature` should record the design that made it work: the model
  returns a **verbatim quote**, located afterwards in the word-level transcript.
  Asking a small model for a timestamp does not work; asking it to copy a
  sentence does.
- `speaker_diarization.feature` can now state the measured result: four voices in
  the corpus at 18/2/2/1, enrolment free from approved segments, and the teaching
  block ranked first by voice in 4 of 4 — with the caveat that the runner-up is
  always communion, because the same person delivers it.

---

## E. Questions only you can answer

1. **The acceptance bar.** `classification-spec.md` sets `no_edit@1s ≥ 80%`.
   Nothing reaches it; at 5 s the control reaches 71%. Is the bar 1 second
   always, or 1 second on clean cuts with honest flagging on hard ones?

2. **Special services.** Should a Good Friday service and a Saturday prayer
   gathering get their own types, or is `other` plus a good summary enough? They
   are rare, they look nothing like a Sunday, and you may publish them.

3. **Rehearsals.** Should a recording containing only rehearsal disappear
   entirely, or stay visible under a filter? It is the most common thing the
   recorder captures that you never publish.

4. **The back catalogue.** Re-render the archive to match the new loudness, or
   accept a step change in the middle of the feed?

5. **The loudness itself.** The A/B files in `experiments/work/ab/` are still
   unheard. Everything about the render is measured; whether it *sounds* right is
   not.


---

## What was applied

| | Change | Files |
| --- | --- | --- |
| A1 | Confidence bands replaced by cross-model agreement plus cut difficulty | `analysis_confidence` |
| A2 | The proposed boundary leads; the rules became a fallback | `segment_proposal` |
| A3 | Speaker change says *which* block, the transcript says *where* | `blocking` |
| A4 | Emptiness restated as dynamic range, `@assumption` dropped | `audio_probe`, `discarding_recordings` |
| A5 | The object key became the source of truth; the sidecar an enrichment | `recording_download` |
| B2 | Clock drift measured and corrected, not averaged away | `detection_accuracy` |
| B3 | Guard against already-edited archive sources | `detection_accuracy` |
| B4 | A damaged container that still decodes | `audio_probe` |
| B5 | `rehearsal` added as a block type, distinct from `music` | `block_classification` |
| B6 | `special_service` added for Good Friday and the like | `block_classification` |
| B7 | One event across several recordings | `block_classification` |
| B8 | The back catalogue loudness step, and re-rendering it | `audio_rendering` |
| C | Q77 decided; the tail, the preview format and the models restated as measured | `preview_audio`, `punch_out_detection` |
| D | Zoom behaviour, the verbatim-quote design, the voice library, stage list | `waveform_review`, `summarization`, `speaker_diarization`, `analysis_orchestration` |

Every scenario added carries `@measured` where a number in it came from the
corpus, so a reader can tell an observation from an assumption.

## What was deliberately not applied

The five questions in section E. Each changes behaviour in a way that is a
judgement rather than a measurement, and answering them wrongly would be worse
than leaving them visible.

One further thing left alone: `classification-spec.md` still sets the target at
`no_edit@1s >= 80%`, which nothing reaches. That number should move only once
question E1 is answered, because the answer determines whether it is the right
shape of target at all.


---

# Second pass — two adversarial reviews of the spec itself

Two reviewers, one on internal coherence and one on survival in the real world.
The coherence review's central criticism is correct and worth stating plainly:
**the first audit was applied file-by-file, not concept-by-concept.** Four of its
five fixes landed in one file each while the same concept lived on unfixed in
five to ten others.

## Applied in this pass

| | Finding | Fix |
| --- | --- | --- |
| Contradiction | The punch-out tail was capped at 0.5 s and tagged `@measured`, forbidding the one correction that fixes essentially all measured punch-out error | Cap removed; the disagreement between the owner's stated preference and his own editing behaviour is now stated in the scenario and flagged `@needs-decision` |
| Contradiction | The loudness target asserted −16 LUFS ±1; four of six validated renders land at −16.8 to −17.4 and fail it | Target restated as −17 ±1, matching what the renderer achieves |
| Contradiction | A re-cut Segment returned to `proposed`, where another file refuses to offer its MP3 | Re-cut is now its own state |
| Defect | `seminar` was asserted by a scenario and defined in no type list | Added to the enumeration |
| Defect | Five places said 24-bit. **Every one of the 33 recordings is 32-bit** — including the file one scenario hard-codes and was measured from | Corrected everywhere |
| Defect | Source duration cited as 79–155 minutes; the corpus spans **37–203** | Corrected; the flags now sit outside the observed range instead of inside it |
| Defect | 14 of 31 punch-ins fall between 250 ms and 2 s, a band with no difficulty label | The moderate band restored |
| Hole | The plausibility test used segment length alone — and would not have caught the +118 s class error it cites as its justification | Replaced with five tests including block-edge distance and cross-run disagreement |
| Hole | Boundary invariants (no clipped word, 250 ms clearance, 1 s lead-in) lived inside the refiner, so the fast path skipped them | Lifted onto the accepted cut, whichever path produced it |
| Hole | Stage order had probe before waveform though probe reads the envelope; blocking before classification though blocking needs it; agreement before proposal though agreement compares proposals | Envelope is its own first stage; blocking and classification iterate; agreement moved after refinement |
| Hole | The accuracy suite exempts `hard` cuts and the system grades its own difficulty — the headline could be raised by grading more cuts hard | Difficulty is now graded from the ground truth, never by the configuration under test |
| Hole | The guest-preacher case — the one place this system causes real harm — was guarded by a reviewer's memory | Speaker identity surfaced on the Segment; an unrecognised voice requires confirmation before publishing; confirming enrols |
| Hole | Q63 promises a passed-over Segment is extractable in November. There was no search, and the `Skipped segments` filter was used in one scenario and absent from the filter list | Search added; both filters added |
| Hole | Three silent-drop paths (clock reset, naming change, ingest cutoff) and no 403 handling anywhere | Skipped objects are recorded with a reason and visible; a credential failure is not treated as transient |
| Honesty | `@measured` was carrying interview hedges — "probably even 250 ms" asserted as 250 ms — and pure policy | Split into `@measured`, `@stated` and `@policy`, each defined in README |

## Still outstanding, and why

**Concept-level, not yet done.** The coherence review is right that these need one
pass each across every file rather than a patch:

1. **Confidence.** Eleven files still carry an ordinal or numeric confidence,
   including a *confidence floor* in `block_classification.feature` that would
   threshold a constant. `classification-spec.md`'s output schema still demands
   it. Nothing downstream is safe until confidence has one stated source or is
   removed.
2. **The type table.** Block types, Segment classifications, which types seed a
   Segment, and the mapping between them are specified in four places that
   disagree. `music` Segments are impossible to produce yet three interface
   Backgrounds depend on them.
3. **The state machines.** `ignored`, `blocked`, `recut`, revert and cancel are
   all asserted by feature files and absent from the README diagrams. Several
   states have no exit: a Recording parked in `discovered` for want of disk is
   never retried, and reconciliation will not pick it up again because it has
   been seen.

**Deployment reality.** Every performance figure was measured on a 128 GB M5 Max
using Apple-Silicon-only tooling. The deployment box has little GPU and has never
run any of it. The locality scenarios are now `@policy` rather than `@measured`,
which is honest, but the central technical claim of the whole spike remains
untested on the machine that has to run it.

## The decisions, unchanged and now blocking

E1 (the acceptance bar) blocks `detection_accuracy.feature` from functioning as a
regression gate — it currently reports 0% at its own stated target. Q38/Q39
(authentication) block the interface entirely; `authentication.feature` is the
one file that is `@needs-decision` throughout while every other interface
Background opens by assuming a signed-in reviewer.

Added to the list by this pass:

6. **The punch-out tail.** Your stated preference (cut immediately after the last
   word) and your own editing behaviour (a deliberate 1.0–1.9 s silent tail,
   22 of 24 segments) disagree. Which wins?
7. **Speaker capture at approval.** Surfacing identity means the system stores
   who preached. That reopens "nothing more is collected" — deliberately, because
   it is the only defence against publishing a guest who asked not to be.
