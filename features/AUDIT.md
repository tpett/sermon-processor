# Feature File Audit

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
| **Q18** tail | a guess of 1.5 s | the true punch-out sits **1.0–1.9 s after the last transcribed word** — a deliberate silent tail |

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
