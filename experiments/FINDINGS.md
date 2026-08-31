# Findings

Running record. Newest stage last. Anything that contradicts `../features/` is
raised here rather than quietly applied to the spec.

---

## Stage 0 — Ground truth

**Status: complete. Gate 0 passed** — six listening clips confirmed by ear.

### Result

**22 of 22 pairs aligned. Zero exclusions.** Plus the two-level case, giving 24
labelled segments in total. Whole corpus in 83 seconds.

| Measure | Value |
| --- | --- |
| Minimum probe NCC across the corpus | 0.905 |
| Worst disagreement between the three probes | 0.8 ms |
| Pairs excluded by validation | 0 |
| Consistency checks failed | 0 |

Q15 is now closed by demonstration rather than argument. Deriving the punch
points from the existing pairs was not just feasible, it was unambiguous — every
recording aligned with a sharp, unmistakable peak.

### Method

Coarse alignment on a 100 Hz energy envelope over the whole file, then three
independent 60-second fine probes at 20%, 50% and 80% through each MP3, searched
at 1 ms resolution.

Envelope correlation rather than raw waveform, deliberately: the exports are
peak-normalized and may have had compression applied, and an envelope is robust
to both where a raw waveform is not.

The three probes exist to catch a specific failure — an MP3 that is *not* a
contiguous excerpt, because material was cut from the middle or two parts were
joined. If that had happened the probes would disagree. They agreed to within
0.8 ms everywhere, so every published MP3 in the corpus is a single unbroken
span of its source.

### What the ground truth shows

**Punch-in is both the more important cut and the harder one.**

| | easy | moderate | hard |
| --- | --- | --- | --- |
| punch-in | 10 | 13 | 1 |
| punch-out | 21 | 3 | 0 |

Q75 established that punch-in matters more, because more people hear the
beginning than the end. It now turns out punch-in is also where the clean
silence usually is not — 14 of 24 punch-ins have under two seconds of quiet to
land in, against 3 of 24 punch-outs.

That is an unwelcome combination and it is worth designing around. It supports
the cut-difficulty grading already in `punch_in_detection.feature`, and it
raises the value of the 250 ms clearance rule from Q17. It also means the ASR
ladder in Stage 2 should be scored hardest on punch-in timestamp accuracy.

The one `hard` punch-in is `2026-06-28 - Members Meeting`, which is the
untrimmed archive case: its punch-in is 0:00:00, so there is audio at the cut by
definition. That is a degenerate case rather than a difficult one, and the
scorer should exclude untrimmed archives from difficulty statistics.

**The running order holds, and the multi-session recordings are obvious.**

For recordings that start at 10:29–10:30, punch-in falls between 19 and 27
minutes in — announcements, three songs, prayer time and the scripture reading,
exactly as described in Q16. For the seven that start early, punch-in falls
between 35 and 78 minutes in. The wall-clock time of the punch-in is
consistently around 10:50–10:57 regardless of when the recording started, which
is a strong and simple signal the classifier can use.

**Segment lengths: 40:07 to 68:26.** Consistent with the earlier measurement and
with the 30–75 minute warning band in the spec.

### The two-level case

`2026-08-02` resolved cleanly at both levels, and the containment check — that
each published segment sits inside its own session — passed without being
tuned for:

| | start | end |
| --- | --- | --- |
| session: TEC | 0:00:00 | 1:15:35 |
| segment: TEC published | 0:00:01 | 0:57:36 |
| session: service | 1:19:18 | 2:51:30 |
| segment: sermon published | 1:49:36 | 2:40:30 |

The gap between the two sessions is 3:43 — well under the recorder's 600-second
silence timeout, which is exactly why they landed in one file.

That 3:43 gap is a useful number for Q72. It is far longer than a pause between
songs and far shorter than the timeout, so a silence-based splitter tuned
anywhere between roughly 90 seconds and 9 minutes would have separated these two
sessions. The spec's decision to split on speaker change rather than silence
still stands — but this says a silence signal would have worked here too, and
Stage 1 can test both cheaply.

### Negative examples

Three recordings in the folder have no published output and are kept as
negatives: both CT-Islam parts and `2026-08-16 - Member Meeting`. The 57
unpublished recordings in the bucket are a larger negative set, still unsampled.

### Known uncertainty

MP3 encoder delay is roughly 13 ms at 44.1 kHz. `ffmpeg` compensates using the
LAME header, so the derived boundaries should be correct — but if a systematic
offset of about that size ever shows up in Stage 1 results, this is the first
place to look. It is well inside the 100 ms working precision either way.

### Contradictions with the spec

None. One thing worth adding: `analysis/detection_accuracy.feature` should state
that untrimmed archive segments are excluded from cut-difficulty statistics,
since their punch-in is 0:00:00 by definition and grades `hard` for a reason
that has nothing to do with difficulty.

### Artifacts

| Path | What |
| --- | --- |
| `data/groundtruth.json` | 24 segments, boundaries, difficulty, alignment evidence |
| `data/bucket.txt` | Cached bucket listing |
| `src/align.py` | Join, align, validate, derive difficulty |
| `src/audio.py` | Decode, envelope, normalized cross-correlation |
| `src/verify.py` | Consistency checks, summary, listening clips |
| `work/clips/` | Gate 0 listening clips |

Re-run with `.venv/bin/python src/align.py && .venv/bin/python src/verify.py`.
Envelopes are cached, so a re-run after a scoring change takes about a second.

---

## Stage 1 — Reasoning ladder

**Status: in progress.** Harness complete and validated end to end; transcription
complete; T0 baseline scored on dev; LLM rungs pending.

### Transcription

`mlx-whisper` with `whisper-large-v3-turbo`, word timestamps on,
`condition_on_previous_text=False` to avoid the repetition loops long-form
Whisper falls into over music.

**94x realtime** on an idle machine — 37 hours of audio in about 25 minutes.
That collapses to **35x** when an LLM is running on the same GPU, which matters
for how the remaining stages are sequenced: transcription and inference should
not overlap.

### The oracle

Added to the scorer, and it turned out to be the most useful number so far.
For each recording it reports the smallest boundary error achievable given the
transcript that rung was handed — the distance from the true boundary to the
nearest utterance edge or silence edge.

**Median oracle punch-in on dev: 0.10 s. Worst: 1.52 s.**

So the frozen transcript can support a punch-in well inside the tolerance that
matters, on every dev recording. Any punch-in error larger than about 1.5 s is a
reasoning failure, not a transcription failure. That distinction is what makes
the rest of the ladder interpretable, and it is why the oracle is worth the
small amount of code it costs.

### T0 — rules, no model

| split | n | found | ≤5 s | median &#124;in&#124; | median &#124;out&#124; |
| --- | --- | --- | --- | --- | --- |
| dev | 7 | 57% | 14% | 2.14 s | 53.75 s |

Nowhere near target, which settles the cheapest question on the ladder: this
task is not solvable by keyword matching alone.

But the failure is lopsided in a useful way. **Punch-in is often nearly right
and punch-out is usually badly wrong.** On three of seven the rules landed the
punch-in within about a second — 2026-04-12 hit 0.12 s, exactly the oracle —
while the punch-out was 54 s, 293 s and 4 s off respectively.

The cause is visible in the rule: it looks for a communion cue or a closing
"amen" in the trailing fifteen minutes of the teaching block, and both fire
early. Preachers say "amen" mid-sermon, and communion vocabulary appears inside
sermons about communion. Lexical cues alone cannot tell a mid-sermon "amen" from
the closing one, because the difference is structural rather than lexical —
which is precisely the argument for the block model, and precisely what the
higher rungs are being asked to do.

### Ladder

| Rung | Model | Size |
| --- | --- | --- |
| T0 | rules | — |
| T1 | `qwen3:4b` | 2.5 GB |
| T2 | `qwen3:14b` | 9.3 GB |
| T3 | `qwen3.6:35b-mlx` | 21 GB |
| C | frontier, via subagent | — |

### Harness notes worth keeping

**Ollama's `format: json` silently breaks thinking models.** Generation is
constrained from the first token, so the model spends its budget producing
reasoning that the grammar discards, and returns an empty string. `think: false`
plus `format: json` works, but disables the reasoning the small rungs most need.

**CORRECTION (2026-08-29, adversarial review).** The above describes an
intention, not what ran. `classify.py` supports `--think`, and `run_ladder.sh`
never passes it — no file in `data/blocks/` carries the `.think` marker. **Every
scored local rung ran with thinking disabled and `format: json` on**, which is
precisely the mode this note identifies as the handicap. The frontier control,
run as a subagent, reasoned freely. The ladder as measured is therefore biased
*against* the local models, and the "fairer test" claim is false as written.

**Boundaries are snapped to the nearest speech edge**, uniformly across rungs.
Without it we would be measuring each model's willingness to copy timestamps
accurately rather than its understanding of the recording, and the oracle
already bounds what snapping can achieve.

**Segments are derived deterministically from blocks** for every rung, using the
extension rule. The rule is given rather than discovered (classification-spec.md),
so deriving it centrally isolates what is actually under test: whether a
technology can identify the anatomy of a service.

### The whole-transcript strategy is beyond a 4B model, in both directions

Measured on an idle GPU, one dev recording, a 22,222-token prompt:

| Mode | Result |
| --- | --- |
| thinking on | 8,192 output tokens spent entirely on reasoning (25k chars), answer never reached, 287 s |
| thinking off, `format: json` | 834 s, output truncated mid-object, failed all three parse attempts |
| **per-block** | **6.3 s, valid output, usable segment** |

Prefill was never the constraint — 22,222 tokens in 0.1 s, about 156k tokens/s.
It is generation that defeats the small model: it cannot produce a long
structured document without either thinking past its budget or looping.

The per-block strategy is roughly **130x faster** here and is the difference
between a rung that works and one that does not. That was the hypothesis it was
put on the ladder to test, and at the small end the answer is unambiguous.

### Two harness bugs found before they could corrupt results

**A filled JSON example in the prompt is not neutral.** The v1 prompt showed the
output shape with plausible example values. `qwen3:4b` returned them verbatim —
`start: 0.0, end: 261.0, "announcements"`, `punch_in: 1946.0` — which are exactly
the numbers written as illustration. Any rung doing this would have been scored
on how well an invented example happened to match reality. Both prompts are now
v2: the schema is described in prose, with no copyable values and an explicit
instruction not to reuse numbers from the instructions.

**Classification and boundary refinement have to be separate stages.** The first
version derived segments straight from block edges. In the per-block strategy
those edges come from a deterministic pre-splitter, so every rung inherited the
same boundaries and the models were contributing nothing to precision — median
punch-out error 245.64 s, identical across three different models.

Refinement is now a shared downstream stage applied identically to every rung
(`segments.refine_in` / `refine_out`), which is what the spec describes and what
makes the ladder measure reasoning rather than pre-splitter granularity. Median
punch-out error fell from 245.64 s to 1.40 s.

**And the refinement rule itself was wrong.** It scanned forward for the first
communion word in the closing stretch, which fires on preachers saying "amen"
mid-sermon and on sermons that mention communion. Searching backwards for the
*last* amen — matching the editorial rule in Q19 — took median punch-out error
from 4.32 s to 1.40 s and roughly tripled the within-5 s rate across every rung.
Notably the same bug was suppressing T0, so it was a harness fault throughout
rather than a model one.

### Dev results — complete ladder

Development split, 8 recordings. Shared refinement applied; segments derived by
the given rule. `≤t` means punch-in *and* punch-out both within t.

| Rung | strategy | found | ≤2 s | ≤5 s | med &#124;in&#124; | med &#124;out&#124; | s/recording |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T0 rules | — | 57% | 14% | **43%** | 2.14 s | 2.21 s | 0.0 |
| T1 `qwen3:4b` | per-block | 75% | 12% | 38% | 6.31 s | 2.21 s | 4–20 |
| T2 `qwen3:14b` | per-block | 62% | 12% | 38% | 2.14 s | 1.40 s | 15–60 |
| T3 `qwen3.6:35b` | per-block | 62% | 12% | 38% | 2.14 s | 1.40 s | 8–32 |
| T2 `qwen3:14b` | whole | 62% | 12% | 25% | 4.64 s | 37.49 s | 86–1148 |
| T3 `qwen3.6:35b` | whole | **88%** | 0% | 25% | 5.08 s | 1.40 s | 21–66 |
| oracle | — | — | — | — | 0.12 s | 0.72 s | — |

**Nothing reaches the 80% no-edit target.** The best within-5 s figure on the
ladder is the rules rung at 43%, and it gets there on only 57% of recordings.

Three things are visible, and the third is the uncomfortable one.

**T3 on the whole transcript is clearly the best at the actual task.** 88%
`found` against 62–75% for everything else — it identifies which block is the
sermon far more reliably. It is also fast: 21–66 s per recording, against
86–1148 s for the 14B on the same strategy, because it runs as MLX rather than
GGUF. Model size and runtime do not move together here.

**Strategy interacts with size, strongly.** The whole-transcript strategy is
unusable at 4B, mediocre at 14B (which emitted 42 and 90 blocks on two
recordings — runaway generation), and best-in-class at 35B. Per-block is the
opposite: it rescues the small model and slightly *hurts* the large one, because
it caps what the model can see. There is no single winning strategy, which was
not the expected result.

**So far the refinement stage has mattered more than the model.** Fixing the
punch-out rule moved every rung further than the gap between a 4B and a 35B.
That is worth stating plainly: on this evidence the editorial rules are carrying
more weight than the reasoning, and the model is mostly being asked to answer
one question — *which block is the sermon* — that the rules cannot answer.

### A tuning attempt that failed, recorded

Since T3-whole loses on punch-in precision to its own block edges, I widened
refinement to look 90 s before the block start and to search the whole span for
the scripture cue. **Median punch-in error went from 2.14 s to 65.06 s.**

Two separate causes, both instructive. Searching the whole span finds preachers
*quoting* scripture mid-sermon and jumps the punch-in past it — the cue is only
meaningful near the block start, so it is now bounded to a 240 s window. And any
lookback at all lets the punch-in drift earlier than the true opening, so it is
disabled outright. Both are recorded in the code with the numbers, so nobody
tries them again.

The bounded cue window did help the small model: T1 per-block median punch-in
fell from 261 s to 6.31 s.

### The control, and what it settles

Run as eight subagents, one per recording, transcript only, no audio, using the
identical prompt and the identical downstream refinement. About 62k *characters* per recording — roughly 17-20k tokens, well inside the
local models' 40,960-token context, so no rung was truncated. (An earlier version
of this line said "62k tokens", conflating characters with tokens and
overstating the control's input by about 3.5x.)

| Rung | strategy | found | ≤2 s | ≤5 s | med &#124;in&#124; | med &#124;out&#124; |
| --- | --- | --- | --- | --- | --- | --- |
| T0 rules | — | 57% | 14% | 43% | 2.14 s | 2.21 s |
| T1 `qwen3:4b` | per-block | 75% | 12% | 38% | 6.31 s | 2.21 s |
| T2 `qwen3:14b` | per-block | 62% | 12% | 38% | 2.14 s | 1.40 s |
| T3 `qwen3.6:35b` | per-block | 62% | 12% | 38% | 2.14 s | 1.40 s |
| T2 `qwen3:14b` | whole | 62% | 12% | 25% | 4.64 s | 37.49 s |
| **T3 `qwen3.6:35b`** | **whole** | **88%** | 0% | 25% | 5.08 s | 1.40 s |
| **C frontier** | **whole** | **88%** | 25% | 50% | 4.64 s | 1.24 s |
| oracle | — | — | — | — | 0.12 s | 0.72 s |

**The local 35B matches the frontier control on the hard part.** Identical
`found` — 88% — and near-identical medians (5.08 s vs 4.64 s punch-in, 1.40 s vs
1.24 s punch-out). The gap is consistency rather than capability: the control is
within 5 s on 50% of recordings against T3-local's 25%.

That is a direct answer to Q13/Q76 for the reasoning stage. A 21 GB model
running locally on hardware you already own does the actual job — deciding which
block is the sermon — as well as a frontier model does. Nothing in this result
argues for paying for an API.

### The real ceiling is not the model

The control, per recording:

| Recording | punch-in error | punch-out error |
| --- | --- | --- |
| 2026-04-12 | +5.08 s | −2.21 s |
| 2026-05-03 TEC | +124.13 s | −0.77 s |
| 2026-05-10 | −0.10 s | −1.24 s |
| 2026-05-31 | +1.37 s | −1.62 s |
| 2026-06-14 | +6.31 s | −0.48 s |
| 2026-06-28 Members Meeting | not found | — |
| 2026-07-12 | −2.14 s | −1.40 s |
| 2026-08-09 | −4.64 s | −1.16 s |

**Every punch-out the control found is within 2.21 s, median 1.24 s.** That
problem is effectively solved by the shared refinement stage once the right
block is identified.

**Punch-in is the entire remaining gap.** If punch-in matched punch-out's
accuracy, the control would score ≈88% within 5 s — at or above the target from
Q75 — rather than 50%. The errors are also mostly *late* (+5.08, +1.37, +6.31,
+124), which points at a specific mechanism: `refine_in` takes the first
utterance at or after the block start, so a model whose block begins slightly
after the true opening can never be recovered, while one that begins early is
pulled back by the scripture cue.

And the oracle is 0.12 s. The transcript contains the right answer; nothing in
the pipeline is reaching for it.

**So the highest-value work is not a bigger model.** It is punch-in refinement —
and it would lift every rung on the ladder at once, including the free one.
That reframes what Stage 2 should prioritise: the ASR ladder should be scored on
punch-in timestamp accuracy above everything else, because that is the metric now
binding the whole system.

### Where the failures actually are

Two recordings account for most of the remaining damage, and neither is an
ordinary Sunday:

- **2026-05-03 TEC** — every rung including the control puts the punch-in about
  two minutes late. It is a class, not a service, so the scripture-reading cue
  that anchors a sermon punch-in is absent.
- **2026-06-28 Members Meeting** — no rung proposes a segment, and the control
  explicitly declined to. The truth is the whole untrimmed file, published as an
  archive. Arguably every rung is behaving correctly here and the scorer is
  wrong to count it as a miss: an archive has no punch points to find. This
  should be scored separately, as `classification-spec.md` already hints for
  cut-difficulty.

---

## Stage 3 (brought forward) — do extra features let a smaller model work?

The question: add speaker diarization, speaker-change detection and music/speech
separation alongside the transcript, so the model is handed structure instead of
having to infer it — and can therefore be smaller.

Run offline via `sherpa-onnx` (pyannote segmentation + NeMo TitaNet embeddings),
no HuggingFace token, no hosted service. **38x realtime**, about 2.5 minutes per
recording.

### Correcting something I said too early

On the first recording I measured the nearest speaker-change boundary at 0.22 s
from the true punch-in and called it decisive against "a current best of 2–5 s".
That comparison was wrong: it put diarization's *oracle* against the pipeline's
*achieved* error. The right comparison is oracle against oracle, and across all
eight dev recordings:

| Signal | median distance to true punch-in | ≤2 s |
| --- | --- | --- |
| transcript edges | 0.24 s | 100% |
| speaker-change edges | 0.41 s | 62% |
| the union of both | 0.11 s | 100% |

**Diarization does not improve punch-in precision. The boundary was already in
the transcript.** The union is slightly better than either alone and is now what
boundaries snap to, but this is a refinement, not the breakthrough it looked
like for one recording. The gap between a 0.12 s oracle and a 4.64 s achieved
error is refinement logic, not missing signal.

### What the features do buy

A compact input. Instead of 22,000 tokens of raw transcript, the model gets a
measured block table — one row per speaker-bounded block with duration,
wall-clock start, voice label, whether that voice recurs elsewhere, word rate,
ASR confidence, cue-phrase counts, and the opening and closing words. Roughly
1,500 tokens.

| Rung | strategy | found | med &#124;in&#124; | med &#124;out&#124; | s/recording |
| --- | --- | --- | --- | --- | --- |
| T1 `qwen3:4b` | whole | *unusable* | — | — | 834 (failed) |
| T1 `qwen3:4b` | **structured** | **62%** | 33.04 s | 243.72 s | **3–8** |
| T3 `qwen3.6:35b` | whole | 88% | 5.08 s | 1.40 s | 21–66 |
| T3 `qwen3.6:35b` | **structured** | **88%** | 33.04 s | 243.72 s | **3–8** |
| C frontier | whole | 88% | 4.64 s | 1.24 s | — |

**The hypothesis is half right, and the half that is right matters.**

On block *selection* it works exactly as hoped. The 35B on a structured table
reaches the same 88% `found` as the frontier control, in **3–8 seconds instead
of 21–66**, on a prompt an order of magnitude smaller. And the 4B goes from
completely unusable on the raw transcript to 62% — the compact input is what
makes a small model viable at all.

On boundary *precision* it makes things worse, and the reason is structural: a
diarization block is bounded by a change of voice, and the preacher keeps
talking through the communion invitation. So the block runs well past the
editorial cut, and refinement searching that block's tail finds the wrong
"amen" — median punch-out error 243.72 s against 1.40 s for the same model on
the raw transcript.

### The conclusion, which is an architecture rather than a model choice

Selection and refinement want different inputs.

- **Selection** — which block is the sermon — is best served by the compact
  structured table. It is cheap, fast, and lets a much smaller model compete.
- **Refinement** — where exactly the cut falls — must run against the
  transcript, because the editorial boundary is lexical ("after the amen, before
  the pitch to communion") and is invisible to a speaker-change detector.

Feeding diarization blocks into refinement actively hurts. The next
configuration worth running is structured selection followed by transcript-based
refinement over the *selected* span, which nothing has tested yet.

### Cost, for the deployment decision

Diarization costs about 2.5 minutes per recording and 91 MB of models. It buys a
20x smaller prompt and roughly a 5x faster classification, and it is what lets a
2.5 GB model do work that a 21 GB model was needed for. On a homelab box with
little GPU that trade is probably worth making — but on the strength of these
numbers it should be bought for *speed and model size*, not for accuracy.

### A blocking-rule bug this exposed

The first implementation merged same-speaker turns only across gaps under 20 s,
which split one 56-minute sermon into six blocks and dropped `found` to 25–38%.
Diarization also over-clusters — 27 labels on one service — and scatters brief
spurious turns through a long monologue.

Block assembly is now iterative: absorb anything shorter than a plausible
section into its larger neighbour, re-merge neighbours that then agree, repeat
until stable. That took the best block from covering a fragment to covering
90–99% of the sermon, and `found` from 25% to 88%.

This is the spec's own rule (`blocking.feature`: the silent prayer inside the
sermon must not create a boundary) and the corpus proves it matters.

---

## The waveform trick — tested

The editor's own method: the closing prayer is quiet, there is a brief pause,
then the communion pitch comes in much louder, and the transition is visible
enough on a waveform to click straight to.

### The signal is real, and it is the dip

Measured at every true punch-out on dev, against the surrounding speech level:

| Recording | level before | level after | step | **local dip** |
| --- | --- | --- | --- | --- |
| 2026-04-12 | 29.3 | 38.7 | +9.4 | **−23.8** |
| 2026-05-03 TEC | 36.3 | 16.4 | −20.0 | **−28.8** |
| 2026-05-10 | 30.9 | 36.9 | +5.9 | **−24.6** |
| 2026-05-31 | 34.1 | 38.1 | +3.9 | **−25.7** |
| 2026-06-14 | 37.2 | 42.7 | +5.4 | **−26.2** |
| 2026-07-12 | 32.1 | 41.0 | +8.9 | **−22.9** |
| 2026-08-09 | 30.2 | 46.1 | +15.9 | **−19.3** |

The **dip is remarkably consistent** — every sermon lands between −19 and −29 dB
below the surrounding speech, and random points inside a sermon reach only about
+4 dB of step at the 90th percentile. Continuous speech does not go that quiet
for that long, which is exactly why it is visible on a waveform.

The *step* is much less reliable: +3.9 to +15.9 dB on sermons, and −20 dB on the
TEC class, where what follows the prayer is quiet Q&A rather than a loud
communion pitch. So the part of the description that generalises is "the prayer
goes quiet", not "then it gets loud".

### But it does not beat the lexical rule

Two detectors were built and measured.

**Short-window dips**, scored on depth and step: 170–180 candidates in a
15-minute search window — a 15 dB drop is just a gap between sentences — with
the true punch-out ranking about 100th. Useless as a ranking signal.

**Long-window level rise**, looking for sustained quiet followed by sustained
loud: the right region lands in the top 4 with median rank 2, but the transition
itself sits a median **+23 s late**, because the level only rises once communion
speech is properly underway.

Combining them — acoustic step to pick the region, last "amen" inside it to pick
the exact point:

| Method | median &#124;error&#124; | ≤2 s |
| --- | --- | --- |
| acoustic only | 236.07 s | 0/8 |
| acoustic + amen | 1.32 s | 4/6 |
| **lexical only (current rule)** | **1.40 s** | **4/7** |

Statistically indistinguishable from what the pipeline already does. Worse, the
acoustic gate *lost* two recordings the lexical rule got right (2026-04-12,
2026-05-31) by steering the amen search into the wrong window, and it rescued
neither of the two the lexical rule gets wrong.

### Why it works by eye and not in code

A human reads a minute of waveform at once and sees the *shape* — a long quiet
stretch with a pause at the end of it. Both detectors here compress that shape
to a single number at a single instant, which throws away the thing that makes
it recognisable. A detector that scored the duration and flatness of the quiet
stretch, rather than the depth of one dip or the size of one step, might do
better; that has not been tried.

### Where this should be used instead

Not as an automatic punch-out detector. Two better homes for it, both already
called for in the spec:

- **On the reviewer's waveform.** Candidate pauses ranked by depth, drawn as
  markers, so the reviewer can click straight to them the way they do now by
  eye. That is `interface/waveform_review.feature`, and it turns a private trick
  into a feature.
- **As a cut-difficulty measure.** The dip depth at a proposed boundary says
  directly whether there is a clean place to cut. A −24 dB pause is an easy cut;
  no dip at all means the boundary lands in speech and needs a human. That is
  exactly the `easy`/`moderate`/`hard` grading in `punch_in_detection.feature`,
  and this gives it a principled measurement instead of the silence-duration
  proxy currently used.

The measured consistency of the dip — −19 to −29 dB, 7 of 7 — makes it a good
confidence signal even though it is a poor search signal.

---

## Type-conditional heuristics — the answer is "specified, but not implemented"

The question: should we classify the content type and then run different
boundary rules per type?

**The spec already says so.** `block_classification.feature` has a rule titled
"Classification decides which boundary rules run", with a scenario stating that
communion rules must not apply to a lesson. **The harness ignored it.**
`refine_out` ran one rule — find the last "amen" — regardless of whether the
block was a sermon, a lesson or anything else.

### Why one rule cannot work, from the transcripts

Two failures with nothing in common except the anchor:

**2026-06-14** — the closing amen is at 7214.2 s, and the communion talk that
follows *also* contains "Amen", at 7403.8 s. Last-amen-wins takes the later one:
**+189 s**.

**2026-05-31** — the closing prayer ends "...we pray these things with hope and
expectation in Christ's name". **There is no amen at all.** The rule skips 245 s
forward into communion to find one: **+244 s**.

And on the class, the follow-on is Q&A rather than communion, so a
communion-shaped rule has nothing to anchor on: **+322 s**.

### The fix, and what it is worth

Anchor *forward* on what characteristically follows the content type, then step
back to the end of the prayer:

- **sermon** → anchor on the communion invitation
- **lesson** → anchor on the questions
- otherwise → fall back to the last amen

Measured on the true sermon span, so the rule is isolated from block-placement
error:

| Rule | median &#124;error&#124; | ≤2 s | ≤5 s |
| --- | --- | --- | --- |
| last-amen, type-blind | 189.14 s | 3/7 | 3/7 |
| **type-conditional anchor** | **1.24 s** | **6/7** | **7/7** |

Every sermon and the class now land within 5 s, and six of seven within 2 s.

### One distinction that had to be made carefully

The anchor cannot be communion *vocabulary* — a sermon can be about communion,
and one closing prayer here contains "as we come to the table". It has to be the
**invitation** specifically, which turns out to be near-formulaic:

> "well if you're a visitor with us... we invite you to partake of communion"

`cues.py` now separates `COMMUNION_INVITATION` from general `COMMUNION`. A second
preacher says "if you're *visiting* with us" rather than "a visitor with us", so
both phrasings are carried. That variant alone was the difference between 6/7
and 7/7.

### Why this was invisible in the aggregate scores

Adding it moved the end-to-end dev numbers barely at all, which is worth
understanding rather than dismissing: when a model places the sermon block
tightly, the block boundary *already* excludes communion, so the search window
never reaches the wrong amen and the type-blind rule survives by luck.

The type-conditional rule matters when block placement is loose — which is the
normal case for every rung below the control, and the case that will dominate in
production. It converts a heuristic that works when everything upstream is
correct into one that is robust when it is not.

### What is still missing

The same treatment for **punch-in**, which remains the binding constraint. The
sermon punch-in anchors on the scripture reading; a class has no scripture
reading, which is exactly why the TEC recording is 110–124 s late on every rung
including the frontier control. A lesson needs its own punch-in anchor, and
nobody has looked at what a class actually opens with.

---

## Type-conditional punch-in — one clear win, one clear dead end

The stated rules, from the editor:

| Type | Punch-in |
| --- | --- |
| sermon | after the scripture reading, almost always at a speaker change |
| lesson (TEC) | the very beginning; sometimes after a "we'll start in a minute" preamble and a pause |
| seminar | the beginning; blocks separated by major silence, joining across a break is a human call |
| meeting | whole file, no punch points |
| anything else | the beginning of the segment; no clear delineation |

### The lesson rule works, exactly

The class opens straight in: "Good morning." at 1.3 s, then "Thanks for coming
this morning to our theological equipping class" at 6.8 s. The human punch-in is
**6.71 s** — the greeting is dropped and the class starts on the next line.

Every rung including the frontier control lands **110–124 s late** here, because
they are all looking for a sermon-shaped opening: they skip the introduction
*and* the opening prayer hunting for a scripture reading that does not exist.

Implementing "a lesson starts at the beginning, minus a separable preamble":

| Rule | error on the TEC class |
| --- | --- |
| sermon rule applied to everything | −5.37 s |
| type-aware, no preamble skip | −5.37 s |
| **type-aware with preamble skip** | **+0.05 s** |

The preamble skip has two clauses, matching the description: if there is a pause
of 20 s or more in the opening lines, start after it; otherwise, if the first
line is a short bare greeting, start on the next one.

**Caveat, stated plainly: there is one lesson in the development split.** Two
more sit in the held-out set and must not be touched. A rule tuned on n=1 is a
hypothesis, not a result, and the preamble clause in particular could easily be
overfitted to this recording's "Good morning."

### The sermon speaker-change rule does not work — three ways

"After the scripture reading, almost always a speaker change" is certainly true
of the audio. It did not survive contact with the data, in three variants:

| Variant | median &#124;error&#124; | ≤5 s |
| --- | --- | --- |
| lexical only (current) | 10.67 s | 3/8 |
| + next raw diarization edge after the reading | 15.24 s | 3/8 |
| + next smoothed block edge after the reading | 14.77 s | 2/8 |
| + bounded lookback for the reading, then next block edge | 42.46 s | 0/6 |

Raw turn edges are too dense to carry information — diarization emits 800 turns
across 27 clusters on a 90 minute service, so "the next speaker change" is just
the next turn boundary, a second or two later. Smoothed block edges are sparse
enough to mean something but too sparse to land on the punch-in, and combined
with a lookback for the reading they produced two catastrophic jumps of about
2,800 s.

The gate is disabled in the pipeline with the reason recorded in the code.

### Why the sermon punch-in is genuinely hard

The scripture reading sits **before** the sermon block, so anchoring on it means
looking backwards past the block boundary — and every attempt at a lookback has
regressed, twice now, in different ways. Meanwhile the oracle says 0.12 s is
available.

That is the honest state: **the information is present, and four different
mechanisms have failed to reach it.** It remains the binding constraint on the
whole system, and it is now clear it will not be solved by another heuristic
tweak. The likelier routes are asking the model for the punch-in directly as a
timestamp rather than deriving it from block edges, or a small purpose-built
classifier over the run-up window.

### Where things stand on dev after all of this

| Rung | strategy | found | ≤5 s | med &#124;in&#124; | med &#124;out&#124; |
| --- | --- | --- | --- | --- | --- |
| T0 rules | — | 71% | 43% | **0.12 s** | 1.40 s |
| T1 `qwen3:4b` | structured | 62% | 0% | 33.04 s | 21.60 s |
| T3 `qwen3.6:35b` | structured | 88% | 0% | 33.04 s | 21.60 s |
| T3 `qwen3.6:35b` | whole | 88% | 25% | 5.08 s | 1.40 s |
| C frontier | whole | 88% | 50% | 4.64 s | 1.24 s |

The type-conditional work lifted the rules rung's `found` from 57% to 71% and
its median punch-in to 0.12 s — the oracle — on the recordings it does find. The
model rungs are unchanged, because their block placement was already doing the
work these rules do.

---

## The segmentation was the problem

Prompted by the observation that reaching backwards from one segment into
another to classify the one you are in is a sign the division itself is wrong.
That was correct, and following it produced the largest improvement of the run.

### The diagnostic

For each source of block boundaries, how far is the nearest proposed boundary
from the true punch-in?

| Blocking source | nearest edge | within 5 s |
| --- | --- | --- |
| model reading the transcript (control) | 1.8 s | 6/8 |
| model reading the transcript (local 35B) | 3.8 s | 5/8 |
| **diarization blocks (mine)** | **8.5 s** | **1/8** |

The diarization blocking was the worst boundary source in the experiment — worse
than a language model eyeballing a transcript. Everything downstream was
compensating for that.

### The diarizer had the boundary; the smoothing threw it away

On 2026-07-12 the raw diarization turn edge sits at 1168.1 s against a true
punch-in of 1167.9 s — **0.22 s**. After block assembly the boundary is at
1208.3 s, **40 s late**. Same story on 2026-05-10: raw edge +3.0 s, assembled
edge +29.8 s.

Root cause, two compounding faults:

1. **Over-clustering.** At the sherpa default threshold the clusterer returned
   12 to 27 "speakers" for a service with about four, and split the preacher
   across two labels — the first 40 s of the sermon under one, the rest under
   another.
2. **Absorption moved boundaries.** A preacher's opening lines come back as
   several short turns. Those fell under the minimum block length and were
   absorbed into the *previous* block — the scripture reading — dragging the
   boundary forward past the punch-in.

Fixing absorption to follow the voice rather than the longer neighbour changed
nothing, because with the preacher split across two labels neither neighbour
shared its voice. The clustering was the real fault.

### The fix, and what it was worth

Raising the clustering merge threshold from 0.7 to 0.9 gives 4–6 speakers
instead of 12–27. On the recording tested first, the block edge went from
+40.40 s to **+0.00 s**.

Across the development split:

| | before | after |
| --- | --- | --- |
| diarization block edge, median | 8.5 s | **3.1 s** |
| within 5 s | 1/8 | **5/8** |

And end to end, on the structured strategy that depends on those blocks:

| Metric | before | after |
| --- | --- | --- |
| found | 88% | 88% |
| ≤5 s | 0% | **38%** |
| median &#124;punch-in&#124; | 33.04 s | **5.37 s** |
| median &#124;punch-out&#124; | 21.60 s | **1.24 s** |

Per recording the local 35B on structured blocks now reads: −19.56, −5.37,
+2.52, +3.65, +6.31, **+0.00**, +659.04 s. Five of seven punch-ins inside 6.5 s,
one exact, one badly wrong block.

### Standings

| Rung | strategy | found | ≤5 s | med &#124;in&#124; | med &#124;out&#124; | s/rec |
| --- | --- | --- | --- | --- | --- | --- |
| T0 rules | — | 71% | 43% | 2.14 s | 1.40 s | 0.0 |
| T1 `qwen3:4b` | structured | 50% | 25% | 19.56 s | 1.62 s | 2–16 |
| **T3 `qwen3.6:35b`** | **structured** | 88% | 38% | 5.37 s | **1.24 s** | **3–10** |
| T3 `qwen3.6:35b` | whole | 88% | 25% | 5.08 s | 1.40 s | 21–66 |
| C frontier | whole | 88% | 50% | 4.64 s | 1.24 s | — |

The structured strategy on a local 35B now sits between the same model on raw
transcript and the frontier control, at **3–10 seconds per recording** and a
prompt an order of magnitude smaller. Its punch-out median matches the control
exactly.

### The lesson worth carrying

Three separate attempts were made to fix punch-in accuracy downstream — a
lookback window, a speaker-change gate, a bounded lookback plus speaker gate —
and all three regressed, one catastrophically. The actual fault was a clustering
parameter two stages upstream, and no amount of downstream heuristic work would
have found it.

The diagnostic that located it was cheap and should have been run first: *is the
boundary we want even being proposed?* If yes, it is a selection problem. If no,
it is a segmentation problem, and nothing downstream can fix it.

---

## Where we stand

Development split, 8 recordings. Held-out set still untouched.

`both` is the no-edit proxy: the segment was found, and *both* boundaries fall
inside the tolerance.

| Config | found | both ≤2 s | both ≤5 s | both ≤10 s |
| --- | --- | --- | --- | --- |
| **C frontier** | 88% | 25% | **50%** | **88%** |
| T3 `qwen3.6:35b` structured | 88% | 12% | 38% | 62% |
| T3 `qwen3.6:35b` whole | 100% | 0% | 25% | 50% |
| T0 rules | 71% | 14% | 43% | 57% |
| T1 `qwen3:4b` structured | 50% | 0% | 25% | 25% |

Split by boundary, best config:

| | ≤1 s | ≤2 s | ≤5 s | median | oracle |
| --- | --- | --- | --- | --- | --- |
| punch-out | 25% | **75%** | **88%** | **1.24 s** | 0.72 s |
| punch-in | 12% | 25% | 50% | 4.64 s | **0.11 s** |

**Punch-out is effectively finished.** Three quarters of recordings land within
two seconds and the median is 1.24 s, against an oracle of 0.72 s. There is
almost nothing left in it.

**Punch-in is the entire remaining gap**, and it is not a signal problem: the
oracle is 0.11 s and the achieved median is 4.64 s, a factor of forty.

### The lesson lead-in rule

Added last, and it fixed the largest single error on the board. The control
classifies a class correctly — announcements, opening prayer, then the lesson —
and starts the segment at the teaching, 124 s in. Defensible, and not the
convention: a class is published from the beginning, introduction included.

Extending a `lesson` segment backwards through its lead-in blocks took that
recording from **+124.13 s to −5.37 s**, and the control's `both ≤10 s` from 75%
to 88%.

Worth noting which way that went: the local 35B on structured blocks was already
*more correct* on the class than the frontier control, because the diarization
put the whole class in one block and the type rule started it at the top. Domain
convention beat raw capability.

### Honest reading

Against the 80% target from Q75, at a 5 s tolerance we are at **50%** and at a
10 s tolerance **88%**. Which of those is the real number depends on the
question Q75 left open — how much error actually sends a reviewer to the editor —
and the answer is likely between them.

Two of the three remaining punch-in failures are marginal: +5.08 s and +6.31 s,
both just over the line. One recording, the untrimmed Members Meeting, is scored
as a miss and arguably should not be — an archive has no punch points to find.

**n = 8.** Each recording is 12.5 percentage points. Every figure here is
directional, and the held-out fourteen are the real test.

---

## Adversarial review — what did not survive

Three independent reviewers were given the code, the data and the spec, and told
to find reasons not to believe the results. They verified against the artifacts
rather than this document. Most of what follows contradicts something written
above.

### Claims that were wrong

**1. "Punch-out is effectively finished."** Backwards. All 31 matched punch-outs
are *early* — not one late. Sign test p ≈ 4e-9. The cause is editorial: the true
punch-out sits 1.0-1.9 s after the last transcribed word on 22 of 24 ground-truth
segments, and the audio in that gap is below -55 dB. **The editor leaves about
1.3 s of silent tail after the amen**, and `refine_out` returns a word end, so it
can never reach it. A single +1.20 s constant fitted on dev moves held-out
`out<=1s` from 7/14 to 11/14. Essentially all of the reported punch-out error is
one correctable constant.

The oracle comparison that made this look finished was circular: `oracle_out` is
computed over utterance ends, which carry the same offset. Restricted to edges
the pipeline can actually return, the punch-out floor is **1.32 s** against an
achieved 1.24 s — punch-out is already *at* its reachable floor, and the claimed
headroom does not exist.

**2. "The ladder runs with thinking enabled... the fairer test."** False.
`run_ladder.sh` never passes `--think` and no file in `data/blocks/` carries the
marker. **Every scored local rung ran with thinking disabled**, the mode this
document identifies as the handicap, while the frontier control — a subagent —
reasoned freely, could re-read and self-correct, and got no repair budget
recorded. The ladder as measured is biased against the local models.

**3. "The best within-5 s figure on the ladder is the rules rung at 43%."**
The T0 blocks were a stale `.v1` run from a code revision that no longer exists,
scored over 7 dev recordings plus one held-out recording, missing a dev one.
Regenerated on the correct set: **found 75%, <=5 s 38%** — not 71% / 43%. The
control at 50% is the actual leader.

**4. Published medians were the upper median.** `score.py` used
`a[len(a)//2]`, not a median. T1-structured's punch-in was published as 19.56 s;
it is **11.60 s**. Fixed.

**5. The target metric was never reported, and at it nothing works.**
`classification-spec.md` sets the target as `no_edit@1s >= 80%`. This document
reported 2 s, 5 s and 10 s. At 1 s **every config scores 0%**, including the
control. The AGENT-BRIEF decision rule — "within 5 points of the control on
`no_edit@1s`" — is degenerate: everything ties at zero, so "the local 35B matches
the control" was reached by substituting a different metric than the brief
specified, without saying so.

### The finding that reframes the whole experiment

**The refinement stage is making the best configuration worse, and the write-up
blamed the models for it.**

Scoring the frontier control's *own* boundaries — which were recorded all along
in `model_segments` and never scored — against the refined ones:

| | refined | model's own |
| --- | --- | --- |
| median &#124;punch-in&#124; | 4.64 s | **2.18 s** |
| median &#124;punch-out&#124; | 1.24 s | **0.78 s** |

Per recording, what refinement did:

| Recording | punch-in: model → refined | punch-out: model → refined |
| --- | --- | --- |
| 2026-04-12 | **−0.08 s → +5.08 s** | +0.43 → −2.21 |
| 2026-05-03 TEC | **+118.89 s → −5.37 s** | +23.89 → −0.77 |
| 2026-05-10 | −0.10 → −0.10 | +0.68 → −1.24 |
| 2026-05-31 | +1.33 → +1.37 | +0.94 → −1.62 |
| 2026-06-14 | **−14.13 s → −9.19 s** | +0.30 → −0.48 |
| 2026-07-12 | −2.18 → −2.14 | +1.12 → −1.40 |
| 2026-08-09 | −4.64 → −4.64 | +0.78 → −1.16 |

On 2026-04-12 the model was **0.08 s** from the human cut and refinement moved it
five seconds away. Every model punch-out is *positive* — a short tail, which is
the safe direction — and refinement makes every one negative, clipping the last
word.

Refinement earns its place in exactly two cases: the class, where the
type-conditional lesson rule turns +118.89 s into −5.37 s, and 2026-06-14. Those
are the cases where the *model* is wrong. Everywhere else it degrades a better
answer.

So "punch-in is the binding constraint and the models cannot reach it" is
inverted. The frontier model reached it — twice within 0.1 s — and the
post-processing walked it back.

### Dead code that this document credits

`snap()` moves **0 of 137** real boundaries: `refine_in`/`refine_out` already
return transcript edges, so the union-of-edges mechanism described above, and the
table showing 0.11 s for "both", has no effect on any reported number.
`speaker_edges` is computed and never read. The preamble and speaker-change
branches never execute. Diarization reaches scored output *only* through the
structured strategy.

### Corrected standings

Dev, 8 recordings, after fixing the stale T0 run, the median, the unbounded
amen fallback and the `"chapter"` cue.

| Rung | found | @1 s | @2 s | @5 s | med &#124;in&#124; | med &#124;out&#124; |
| --- | --- | --- | --- | --- | --- | --- |
| C frontier | 88% | **0%** | 25% | 50% | 4.64 s | 1.24 s |
| T3 35B whole | 100% | **0%** | 12% | 38% | 4.86 s | 1.42 s |
| T3 35B structured | 88% | **0%** | 12% | 38% | 5.37 s | 1.24 s |
| T0 rules | 75% | **0%** | 12% | 38% | 3.76 s | 1.32 s |
| T1 4B structured | 50% | **0%** | 0% | 25% | 11.60 s | 1.43 s |

`found` at >50% overlap is too lenient to rank on: T3-whole's 100% includes a
−967 s punch-out, while the control's 88% is because it correctly *declined* to
propose a segment on the untrimmed archive.

### A verified bug that dev could not see

`cues.SCRIPTURE` contained the bare token `"chapter"`, and `refine_in` takes the
*last* cue hit in its window. A church preaching expository series says it
constantly mid-sermon. On held-out recordings this produced punch-in errors of
+222.0 s, +205.5 s and +161.7 s. **Dev was completely flat across every window
value from 30 s to 420 s** — it supplied no information for a parameter this
document records as measured. Removing the one string takes held-out from 8/14
to 11/14 and worst error from 222 s to 6.6 s. Removed.

### What the reviewers confirmed as sound

- **Ground truth, empirically.** One reviewer cut the FLAC at the derived
  boundaries and cross-correlated against the MP3: residuals of **0.00 to 1.13
  milliseconds** on punch-in and 0.00 ms on punch-out. No encoder-delay bias, no
  systematic offset. The signed distance to the nearest utterance start is
  median +0.04 s with 8 of 24 negative — unbiased.
- **`results.jsonl` integrity.** All 39 rows recomputed independently from
  `blocks/` and `groundtruth.json`: zero mismatches.
- **No cache staleness.** All blocks and segments match a fresh derivation
  against the current diarization.
- **`blocks_from_diarization` tiles exactly** — no gaps, overlaps, dropped
  utterances, and the smoothing loop provably terminates.
- **The oracle is not trivial**: a random time point is 0.91 s from the nearest
  edge against 0.11 s for a true boundary, so boundaries really do sit on edges.

### Cost of the review

One reviewer used held-out recordings to prove the `"chapter"` finding. Three
held-out recordings (2026-05-03, 2026-06-07, 2026-07-26) should now be treated as
burned for tuning. A held-out recording (2026-05-24) had also been run through T0
during early debugging; that stale run has been deleted.

---

## The held-out run

One shot, logged in `data/test_access.log`. 14 held-out recordings with ground
truth plus 3 negatives, scored with the corrected architecture — the model's own
boundaries where they are plausible against the spec's 30-75 minute band,
refinement as the fallback.

| Config | split | n | found | @1 s | @2 s | @5 s | med &#124;in&#124; | med &#124;out&#124; |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C frontier | dev | 8 | 88% | 25% | 38% | 62% | 2.18 s | 0.78 s |
| **C frontier** | **held-out** | **14** | **100%** | 0% | 29% | **71%** | **2.40 s** | 1.48 s |
| T3 35B local | dev | 8 | 100% | 12% | 25% | 50% | 3.76 s | 0.86 s |
| **T3 35B local** | **held-out** | **14** | **100%** | 0% | 14% | **57%** | **2.87 s** | 1.41 s |
| T0 rules | dev | 8 | 75% | 0% | 12% | 38% | 3.76 s | 1.32 s |
| **T0 rules** | **held-out** | **14** | 86% | 0% | **0%** | **7%** | **221.14 s** | 1.56 s |

### The models generalised. The hand-tuned rules did not.

**The frontier control held up and slightly improved** — `found` 88% → 100%,
`@5s` 62% → 71%, median punch-in 2.18 s → 2.40 s. The prompt encodes this
church's running order, and the worry was that it was fitted to the eight
recordings I wrote it while looking at. It was not.

**The local 35B held up too** — `found` 100% on both, `@5s` 50% → 57%, median
punch-in 3.76 s → **2.87 s**, better on unseen data than on the set it was
developed against. The headline claim of the spike — that a 21 GB local model
does this job — survives contact with held-out data.

**The rules rung collapsed.** Median punch-in 3.76 s → **221.14 s**. `@5s` 38% →
**7%**. Nine of fourteen held-out punch-ins are wrong by more than a minute:
+1462.6, +1181.2, +536.7, +303.5, −251.3, −242.7, +199.6, −112.9, −62.3 seconds.

This is the overfitting the adversarial review predicted, isolated cleanly. T0 is
the only rung whose output is *entirely* the hand-tuned pipeline — it has no
model boundaries, so `choose()` always falls back to refinement. Every parameter
tuned across this session lives in that path, and on unseen data it fails
catastrophically while the same refinement code, used as a *fallback* behind a
model, does no harm.

The lesson is sharper than "the rules were overfitted". It is that **~120 free
parameters fitted against 14 labelled numbers produced something that looked
competitive on dev (38% at 5 s, best-in-class median punch-in) and is worthless
off it.** Dev could not see it. Only the held-out set could.

### The negative set, finally measured

| Config | CT-Islam pt1 | CT-Islam pt2 | Member Meeting |
| --- | --- | --- | --- |
| T0 rules | proposed 1 | proposed 1 | proposed 1 |
| T3 35B local | proposed 1 | proposed 1 | proposed 2 |
| **C frontier** | proposed 1 | proposed 1 | **declined** |

Only the frontier control correctly declined the members meeting — a recording
with no teaching in it at all. Both local configurations invented a segment,
and one invented two.

The CT-Islam parts are a scoring artefact rather than a real failure: both are
genuine seminar content that *was* published, just joined by hand into one MP3
(Q65), so proposing a lesson for each is arguably right and the corpus simply
has no per-part ground truth. The members meeting is the real test, and the
local models failed it.

This matters more than it looks. `interface/discarding_recordings.feature` and
`notifications/approval_notifications.feature` both assume a recording with
nothing publishable produces no work and no notification. On this evidence a
local model would put a spurious sermon in the review queue for every members
meeting and every band practice — and 38 of the 57 unpublished bucket recordings
are Sundays in the same room.

### What still fails at the target

`no_edit@1s` is **0% on held-out for every configuration**, including the
control. Median punch-out rose from 0.78 s on dev to 1.48 s, which is the
editorial tail bias reasserting itself on recordings the tail was not fitted to.

So the honest summary: the technology question is answered and the workflow
question is not. A local 35B finds the right sermon in every held-out recording
and lands within 5 seconds on 57% of them. It cannot yet hit 1 second, and it
cannot yet tell when it should stay quiet.

---

## Spike 1 — the render chain

Built `src/render.py`. Channel-1 extraction, two-pass loudnorm, LAME mono, short
fades. Rendered from ground-truth boundaries so the only variable is processing.

| Recording | ours LUFS | peak | LRA | kbps | MB | theirs LUFS | peak | LRA | kbps | MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-12 | −16.8 | −1.1 | **7.1** | 95 | 34.1 | −23.9 | −1.2 | 12.1 | 96 | 34.6 |
| 2026-04-26 | −17.4 | −0.8 | **8.1** | 101 | 40.8 | −26.3 | −1.4 | 14.7 | 104 | 42.2 |
| 2026-05-03 | −17.3 | −1.0 | **8.3** | 98 | 37.8 | −27.7 | −1.4 | 14.8 | 100 | 38.4 |
| 2026-05-03 TEC | −17.4 | −0.8 | 6.7 | — | — | −28.5 | −1.5 | 13.8 | — | — |
| 2026-05-10 | −17.2 | −0.6 | 8.0 | — | — | −26.8 | −2.0 | 14.1 | — | — |
| 2026-05-17 | −17.1 | −0.7 | 8.3 | — | — | −26.3 | −1.5 | 14.2 | — | — |

**Week-to-week loudness spread: 0.6 LU, against 4.6 LU across the same six
hand-made files** (and 9.1 LU across the wider sample measured earlier). The
consistency problem is solved.

**Q49 is answered empirically.** Loudness range fell from 12.1–14.8 LU to
6.7–8.3 LU — into the spoken-word norm — with **no compressor in the chain**.
One loudness operation does what normalize-then-compress was reaching for, which
is what you suspected.

Bitrate and file size now match the hand-made files (95–101 kbps against 96–104;
34–41 MB against 35–42), so a listening comparison has only one variable.

Two things worth knowing. Output lands at −16.8 to −17.4 rather than −16.0:
loudnorm's linear mode holds back to protect the true-peak ceiling. About 1 LU
short of target, consistent, and correctable if it matters. And the output is
**7–11 LU louder than the back catalogue** — new files will be dramatically
louder than anything published before.

A/B excerpts written to `work/ab/` — same 30 seconds from each pipeline, one
mid-sermon and one from a quiet passage.

---

## Spike 2 — waveform with word-aligned transcript

Built as a working page against one real recording (2026-08-23, 104 minutes,
11,630 words, 12 classified blocks) and published as an artifact.

**Precision, measured on an 1100 px canvas:**

| Window | ms per pixel | 100 ms is | words in view |
| --- | --- | --- | --- |
| whole recording (104 min) | 5699 | 0.0 px | 9,683 |
| 5 minutes | 273 | 0.4 px | 718 |
| 30 seconds | 27 | 3.7 px | 48 |
| **3 seconds** | **2.7** | **36.7 px** | 0 |

**A two-stage zoom is necessary and sufficient.** Placing a boundary to 100 ms is
impossible at any whole-recording view and trivial at 3 seconds, where 100 ms is
nearly 37 pixels — comfortably draggable. So the interface needs an overview to
choose a region and a detail view to make the cut, which is what was built.

**The word rail earns its place at 10-60 seconds, not at the cut.** At a 30 second
window 48 words are readable alongside the waveform. At the tightest zoom there
are *zero* words in view — because a good cut lands in silence. So words are for
finding the right moment, and the waveform is for placing it precisely. They
serve different steps rather than the same one.

**One production consequence:** the peaks and words for a single recording are
**2.76 MB**. That is fine embedded in a one-off page and too much to inline in a
real application — peaks will need to be an artifact fetched per recording, at
progressive resolution.

The page also carries a 75-second audio window so playback and the moving
playhead are real rather than mocked. Everything else — drag on the overview to
choose a window, drag the IN/OUT handles, click a word to cut there, arrow keys
to nudge by 100 ms — works on the actual data.

## Spike 3 — seekable streaming

Q27 asked for the player to fetch only the region being scrubbed, "as long as
it's not overly complicated". Two candidates, same 48 kbps mono source:

| | size | build | files |
| --- | --- | --- | --- |
| **A. constant-bitrate MP3 + HTTP range requests** | **37.6 MB** | 18 s | **1** |
| B. HLS segments + manifest | 42.3 MB | 18 s | 627 + manifest |

The question for A is whether a byte offset computed arithmetically actually
lands where you asked. Measured against the source audio by correlation:

| seek to | bytes fetched | % of file | lands at | error |
| --- | --- | --- | --- | --- |
| 10:00 | 0.06 MB | 0.16% | 600.0 s | −0.02 s |
| 30:00 | 0.06 MB | 0.16% | 1800.0 s | +0.00 s |
| 60:00 | 0.06 MB | 0.16% | 3600.0 s | +0.02 s |
| 90:00 | 0.06 MB | 0.16% | 5400.0 s | +0.04 s |
| 100:00 | 0.06 MB | 0.16% | 6000.0 s | +0.04 s |

**Worst seek error 0.04 seconds, fetching 0.16% of the file.** A single CBR MP3
with range request support does everything HLS would, in one file instead of 628,
with no manifest and no packaging step.

It also settles the bitrate question you raised: because playback only ever
fetches the window being played, bitrate barely affects responsiveness. At 96
kbps a 10-second window is still only about 0.12 MB.

**Recommendation: one CBR preview per recording, served with range support.**
The `write_xing 0` flag matters — a VBR file would need its seek index parsed
first, which is exactly the complication you asked to avoid.

---

## Spike 4 — segment summaries and the Preview excerpt

Q10/Q70: a summary or guess of what each segment is, plus "a piece of that
segment that's most likely going to be highly identifiable for the human" that
a Preview button plays. Never built until now.

**Design decision that made it work:** the model is never asked for a timestamp.
It returns a *verbatim quote*, which is then located in the word-level transcript
by fuzzy match. Small models are unreliable at emitting times and perfectly good
at copying a sentence, and the words already carry timings.

**`qwen3:4b` — the smallest model on the ladder — is entirely adequate here.**

| | |
| --- | --- |
| blocks summarised | 11 of 11 |
| time per block | **0.8 s** |
| whole recording | **9 s** |
| cue quote located in the transcript | **11 / 11** |

Sample output, unedited:

| Block | Summary | Cue excerpt |
| --- | --- | --- |
| scripture_reading | Hebrews 12:4-11 on discipline as divine fatherhood | *"My son, do not regard lightly the discipline of the Lord..."* |
| sermon | shift from spiritual to corrective discipline, using spanking statistics | *"How many of you were ever spanked by someone other than one of your parents"* |
| communion | communion's introspective focus, urging repentance and self-examination | *"If you've trusted Christ, if you've been obedient to his command to be baptized"* |
| announcements | Spencer Davis, a long-term member, moves near Longview for work | *"Spencer Davis, you want to stand up, Spencer?"* |
| other | Jeff announces Nicene Creed recitation before departure | *"I believe in one God, the Father Almighty, maker of heaven and earth"* |

The summaries are specific rather than generic — they name the passage, the
person, the notice. And the cues are genuinely the recognisable moment: the
scripture cue is the passage itself, the sermon cue is its opening hook, the
communion cue is the invitation.

**This is the opposite of the classification result.** On classification the 4B
was unusable on a whole transcript and mediocre even on structured blocks. On
summarisation it is fast, reliable and good. The two tasks look similar and are
not: classification needs global reasoning over three hours, summarisation needs
local comprehension of one block at a time.

So the deployment picture is a **split**: a larger model for choosing which block
is the sermon, a very small one for describing everything. The small model's work
is also the part that runs on every block of every recording, so putting the
cheap model where the volume is happens to be the right architecture anyway.

One quirk worth knowing: music blocks get summarised as though the lyrics were
prose ("a passage on divine mercy overcoming sin"). Accurate, but it reads oddly
next to the others, and a music block probably wants its label rather than a
summary.

11 cue excerpts rendered to `work/cues/` for listening.

---

## Spike 5 — identifying the preacher, not just diarizing

Q12: one primary preacher plus three or four others. Diarization gives anonymous
labels; identification says *whether this is the regular preacher*, which is the
strongest signal for the thing the local models are weakest at — deciding which
block is the sermon.

**Enrolment is free.** Every ground-truth teaching span is by definition a
labelled sample of whoever preached it, so the voice library builds itself out of
work already done. No enrolment session, no extra recording.

Embedding all 23 teaching spans (NeMo TitaNet, offline, four 20-second excerpts
each averaged so one noisy moment cannot define a voice) and clustering:

| threshold | voices found | cluster sizes |
| --- | --- | --- |
| 0.5 | 3 | 19, 2, 2 |
| **0.6** | **4** | **18, 2, 2, 1** |
| 0.7 | 4 | 18, 2, 2, 1 |
| 0.8 | 5 | 16, 2, 2, 2, 1 |

**Four voices, one of them carrying 18 of 23 spans** — your Q12 answer recovered
from the audio without being told.

### Does it find the sermon?

Leave-one-out, so the recording under test never contributes to the profile it is
scored against. Every block scored against the primary preacher's centroid:

| Recording | top block | similarity | next |
| --- | --- | --- | --- |
| 2026-08-23 | **sermon** | 0.919 | communion 0.838 |
| 2026-05-10 | **sermon** | 0.949 | communion 0.872 |
| 2026-06-14 | **sermon** | 0.923 | communion 0.894 |
| 2026-05-03 TEC | **lesson** | 0.947 | qa 0.809 |

**4 of 4**, and the margin over everything that is not the preacher is large —
music, announcements and non-teaching blocks score 0.16 to 0.48, or negative.

One nuance worth carrying: the runner-up is *always communion*, because the same
person delivers it. The signal identifies "the preacher is talking", not "this is
the sermon". Combined with duration it is decisive — the longest block the
preacher speaks in is the sermon — but on its own it would happily hand you the
communion invitation.

This is a cheap, offline signal that attacks the one weakness the held-out run
exposed, and it costs about a second per block.

---

## Spike 6 — detecting the false triggers

Q36: a pop from someone switching the system on triggers a ten-minute recording
that is almost entirely silence. The corpus had no examples — everything in
`~/Desktop/Sermons` is material that was kept — so the threshold in the spec was
invented. Six real unpublished recordings were pulled from the bucket.

Measured as the proportion of each recording above **its own** noise floor, so
the test separates "a room with something happening in it" from "a room with one
bang in it" rather than keying on absolute level.

| | recording | minutes | active | longest active run | dynamic range |
| --- | --- | --- | --- | --- | --- |
| unpublished | 2026-03-31 21:37 | 10.1 | 0.0% | 0.2 s | 3.7 dB |
| unpublished | 2026-04-03 12:35 | 2.5 | 0.2% | 0.3 s | 3.9 dB |
| unpublished | 2026-04-08 21:03 | 10.4 | 0.0% | 0.2 s | 3.8 dB |
| unpublished | 2026-04-19 12:32 | 10.1 | 0.0% | 0.1 s | 3.7 dB |
| unpublished | 2026-06-18 21:35 | 10.4 | 0.1% | 0.2 s | 3.6 dB |
| unpublished | 2026-08-23 12:20 | 10.1 | 0.0% | 0.1 s | 3.6 dB |
| published | 2026-04-12 | 105.9 | 76.1% | 756 s | 77.8 dB |
| published | 2026-04-26 | 155.0 | 80.6% | 970 s | 60.9 dB |
| published | 2026-05-03 | 96.5 | 85.0% | 668 s | 79.4 dB |
| published | 2026-05-03 TEC | 74.2 | 65.2% | 6.5 s | 52.2 dB |
| published | 2026-05-10 | 105.6 | 82.7% | 871 s | 72.9 dB |

**The separation is not close.** Real recordings are 65–85% active with 52–79 dB
of dynamic range. False triggers are 0.0–0.2% active with **3.6–3.9 dB** — the
sound of a room with nothing in it.

Q78 is answered: **dynamic range alone is a clean discriminator.** Anything under
about 15 dB is an empty room; real content is above 50 dB. The 1% guess in the
spec happens to work, but the gap is three orders of magnitude wide, so the exact
threshold does not matter and the test does not need tuning.

Your description of the failure mode was exact: five of six are almost precisely
ten minutes, consistent with a transient triggering the recorder and the silence
timeout closing it.

**This is free.** It runs on the envelope already computed for the waveform, it
needs no model, and it can run before transcription — so a false trigger costs no
GPU time at all.

One note: `recording_20260403_123524` produced FLAC decode errors partway through
("invalid residual"). It analysed anyway, but a corrupt or truncated upload is a
real case the ingest path should handle rather than crash on.

---

## Corpus expansion — and a clock-drift finding

Five more source recordings pulled from the bucket and paired with edits from the
Sync archive. **The corpus is now 28 recordings with ground truth and 30 labelled
segments**, up from 23 and 24. Zero exclusions.

### Two MP3s had no source, and that is a hard boundary

`2026-03-01` and `2026-03-08` cannot be paired: **the recorder's first upload is
`recording_20260311_210943`**. Nothing before 11 March 2026 exists in the bucket.
Those two edits are still useful for voice enrolment and for harvesting a
preacher's phrasing, but they can never be boundary ground truth.

### A second two-level case, on Easter

`2026-04-05` is a single 203-minute recording starting 08:52 that produced **two**
published outputs — a 59-minute class and a 50-minute sermon. Both aligned
cleanly:

| Output | punch-in | punch-out | NCC |
| --- | --- | --- | --- |
| TEC — Forgiveness | 494.33 | 4008.92 | 0.960 |
| Matthew 12:38-42 | 7565.47 | 10555.08 | 0.934 |

Until now `2026-08-02` was the only recording exercising the
Recording-contains-several-Segments model, and it was never scored. There are now
two, and this one is the commoner shape: straight from source to two MP3s with no
intermediate extraction.

### Three early recordings run on a different clock

Three of the new pairs showed probe disagreement 200x worse than anything in the
corpus. It is not an editing artefact — it is **linear clock drift of about
−130 ppm**:

| Recording | drift | residual from a straight line |
| --- | --- | --- |
| 2026-03-15 | −131.6 ppm | 7 ms |
| 2026-03-22 | −133.1 ppm | 7 ms |
| 2026-04-19 | −157.7 ppm | 33 ms |
| 2026-03-29 | +0.3 ppm | 0 ms |
| everything from May onward | +0.3 ppm | under 1 ms |

−130 ppm is a capture clock running at about **44,094 Hz while labelled 44,100**
— a soundcard timebase error, not a mistake anyone made. Across a 50-minute
sermon it accumulates to 0.23 seconds, which is large against the tolerances this
project cares about.

**The three-probe design existed to catch non-contiguous excerpts and caught this
instead**, which is the better kind of surprise. Alignment now fits a straight
line through five probes rather than taking a median: the intercept is the true
punch-in, the slope is the clock difference, and **the residual from that line is
the real contiguity test**. Drift is linear and correctable; a genuine edit is
not.

That recovered `2026-04-19`, which the previous spread test had excluded outright,
and tightened the other two.

**Worth knowing about the recorder:** the drift is confined to March and one April
recording. `2026-03-29` and everything from May onward is within 0.3 ppm. So
something changed in the capture chain in late March. Nothing needs fixing now,
but if old archive material is ever ingested, the drift is real and the pipeline
now measures it per recording rather than assuming it away.

---

## The fresh split — 6 recordings nothing has ever seen

The five newly paired recordings plus `2026-08-02`, which existed from Stage 0
but had never been scored. **Eight labelled segments, no tuning, no prior run.**

| Config | n | found | @1 s | @2 s | @5 s | med &#124;in&#124; | med &#124;out&#124; |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **C frontier** | 8 | **100%** | 0% | 12% | **62%** | **3.05 s** | 1.21 s |
| **T3 35B local** | 8 | **100%** | 12% | 12% | **62%** | 3.77 s | 2.27 s |
| T0 rules | 8 | 50% | 12% | 12% | 25% | **172.07 s** | 0.96 s |

**The held-out result reproduces.** Both models found every segment in every
recording, at within-5-second rates of 62% against the 71% and 57% measured on
the previous held-out set. Three independent evaluations now agree, on 28
recordings in total.

**The rules collapse reproduces too**, and harder: 50% found, median punch-in
**172 seconds**. That is the third split on which the hand-tuned path has failed
and the models have not.

### The multi-segment model works

This is the first time either two-level recording has been scored, and they are
the only test of the several-Segments-from-one-Recording structure the whole
spec rests on. The control, unprompted about how many to expect:

| Recording | segment | punch-in error | punch-out error |
| --- | --- | --- | --- |
| 2026-04-05 (Easter) | the class | +87.88 s | **+0.38 s** |
| 2026-04-05 (Easter) | the sermon | **−3.77 s** | **+0.02 s** |
| 2026-08-02 | the class | +63.64 s | **+0.65 s** |
| 2026-08-02 | the sermon | **−2.16 s** | **+1.26 s** |

It correctly emitted **two** segments from each three-hour recording, classified
each one, and got every punch-out inside 1.3 seconds — one within 20
milliseconds. The local 35B also found both segments in both recordings.

The structure is not the problem. **Both class punch-ins are late by about a
minute, and for the same reason every rung has been late on a class since the
beginning:** the model starts the segment at the teaching, skipping the
introduction and the opening prayer, because that is where a *sermon* would
start. You told me a class publishes from the very beginning. The lesson lead-in
rule exists for exactly this and only fires when the preceding blocks are typed
as lead-in — here they were not.

That single behaviour accounts for both of the largest errors on the fresh split.
Fixing it is a classification question (what are the blocks before a class?)
rather than a boundary one.

### Corpus status

28 recordings with ground truth, 30 labelled segments, 3 negatives, plus 10
unpublished recordings downloaded for false-positive testing. Every split has now
been used:

| split | n | status |
| --- | --- | --- |
| dev | 8 | tuned against extensively — no longer informative |
| held-out | 14 | spent once, logged |
| fresh | 6 | spent once, logged |

**There is no clean evaluation set left.** Any further tuning needs either new
recordings or a move to k-fold cross-validation across all 28, which reuses the
data honestly instead of pretending a clean split still exists.

---

## What the unpublished recordings actually are

52 of the 83 bucket objects were never edited. The corpus had never looked at
them, so the taxonomy in the spec came entirely from material that was kept.
Twenty were sampled across every cluster in the metadata, transcribed, and given
an **open** question — "say what this is, do not fit it to a category".

**Three groups, and one of them is a genuine gap in the taxonomy.**

### 1. Empty rooms — 7 of 20

Dynamic range 3.6–3.9 dB, almost all exactly ten minutes. Sunday just after noon
and midweek around 21:00. These are the pop-triggers-a-recording case, and the
dynamic-range test catches every one before transcription.

### 2. Band rehearsal and sound check — 8 of 20, and the dangerous category

| | |
| --- | --- |
| duration | 20 – 68 minutes |
| dynamic range | **63 – 76 dB** |
| when | Sunday 07:59–09:39, a Saturday 10:25, a Thursday 20:02 |

**This is the biggest unpublished category and the one that can fool the
system.** Forty to sixty-five minutes of continuous audio, in the same room, with
the same voices, at full dynamic range — indistinguishable from a service on
every cheap signal. The emptiness test cannot touch it. Extrapolating from the
cluster structure, most of the 19 Sunday-09:00 recordings are these.

### 3. Events with no category in the spec — 4 of 20

- **Good Friday Tenebrae service** (2026-04-03 19:00, 51 min) — "readings, songs,
  and explanations". A service, not a Sunday service, with a completely different
  shape. Four recordings across that day.
- **Saturday worship and prayer gathering** (2026-05-09 11:20, 68 min) and an
  **intercessory prayer gathering with sermons and personal testimonies**
  (13:26, 57 min). Four recordings across that Saturday.
- **Members meeting with budget presentation** (2026-03-22 12:50, 48 min) —
  the taxonomy has `meeting`, but marks it archive-only; this one reads as
  something that could be published.

`classification-spec.md` has `sermon`, `lesson`, `seminar`, `meeting`, `music`,
`qa` and `other`. **A Good Friday service and a Saturday prayer gathering fall
into `other`**, which tells a reviewer nothing. Q73 asked whether the taxonomy
covered everything and the answer at the time was "that should be good for now" —
against a corpus that contained none of these.

### The false-positive test, finally run

The survey asked an easy question. The real test is the production prompt — the
one that assumes a sermon might be there and explains how to find it. Given that
prompt, on every unpublished recording with real audio:

**0 of 13 invented a segment.**

Every rehearsal, every sound check, the members meeting and the Good Friday
service were declined. The one segment proposed was on the intercessory prayer
gathering, which the open survey independently judged publishable — so that is
arguably correct rather than a false positive.

This closes the largest untested risk in the project. The concern was that 38 of
the 57 unpublished recordings are Sundays in the same room with the same voices,
and that the wall-clock prior and the running-order prior would all vote for
them. On this sample they do not.

**Caveat:** this is the 35B on the whole-transcript strategy. The earlier held-out
run showed the *local* models inventing a segment for the members meeting where
the control declined, so this result should not be assumed to transfer to a
smaller model or a different strategy.

## The pre-S3 archive is unusable, and the corpus is clean

Clarified: the older FLACs in the Sync archive are not damaged — they are
**already-edited lossless copies of just the message**. As ground truth they
would be actively harmful: punch-in 0, punch-out end, teaching the system that a
sermon starts at the beginning of its file.

Every recording in the corpus was checked for this. Published output as a
fraction of its source:

| | coverage |
| --- | --- |
| 26 sermons and classes | **29% – 80%** |
| 2026-05-03 TEC (highest) | 80.2% |
| 2026-06-28 Members Meeting | **100%** — a legitimate untrimmed archive |

**Nothing in the corpus is an already-edited file**, because everything came from
the S3 bucket, which is genuine recorder output. The risk only exists for the
older archive, which was never used.

`verify.py` now fails on any recording whose output covers more than 95% of its
source. It flags rather than excludes, because a legitimate untrimmed archive
looks identical — and it correctly catches the members meeting today.

---

## The blind run — 2026-08-30

A service recorded the day before, never edited, no ground truth, nothing in the
corpus from that week. The first genuinely end-to-end run: ingest to finished
MP3, no human step.

**Two recordings arrived.** A 37-minute 09:44 and the 105-minute 10:28 service.

| | local 35B | frontier control |
| --- | --- | --- |
| 09:44 rehearsal | 8 blocks, **0 segments** | 3 blocks, **0 segments** |
| service, punch-in | **0:25:33.60** | **0:25:33.60** |
| service, punch-out | 1:20:58.60 | 1:20:55.52 |

**Identical punch-in, to the sample.** They differ by 3.08 s on the punch-out —
the width of a pause. Both silently discarded the rehearsal.

**The reviewer confirmed both boundaries land where he would have cut.**

Block structure matched the described running order, and three independent
signals agreed: the passage is Hebrews 12:12-17, continuing directly from
12:4-11 the previous week; the punch-in falls at 10:54 wall-clock, inside the
10:50-10:57 band every other service lands in; and 55.4 minutes is mid-range for
the corpus.

Output: 55.4 min, 98 kbps mono, −17.2 LUFS, LRA 9.0. The summariser produced all
ten block summaries in 10 seconds on the 2.5 GB model and located every cue
quote, picking *"He started hobbling to the finish in obvious pain"* — the Derek
Redmond illustration — as the sermon's recognisable moment.

### What this establishes, and what it does not

**Establishes:** the pipeline runs unassisted end to end and produced a cut a
human confirms is correct. Every component held simultaneously — ingest,
transcription, blocking, classification, boundary selection, rehearsal
rejection, rendering, summarisation.

**Does not establish a rate.** n = 1. The measured within-5-seconds figures are
57–71%, and this is one draw from that distribution that happened to land well.
It was also an ordinary Sunday — the easy case. Every evaluation so far shows
classes are the weak spot, where every rung including the control has been 60–90
seconds late.

### One finding worth keeping

**Cross-model agreement is a real confidence signal, and self-reported confidence
is not.** The adversarial review showed model confidence sitting at 0.95 on a
+659 s error and on a correct answer alike — a constant. Here two independent
models agreed to the sample on the punch-in and the cut was right.

Across the project the failures have been cases where models disagreed with each
other or with the truth. That makes agreement between a local model and a second
opinion a usable flag for the "hard cut, check this one" behaviour the spec asks
for — and it needs no calibration, just a second run.
