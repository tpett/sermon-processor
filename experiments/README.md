# The Experiment

**Question:** what is the cheapest thing that finds the sermon as well as a
human does, and can we run it locally?

The spec (`../features/`) describes behaviour that has never met real audio. Two
parts of it are most likely to be wrong: whether a machine can reliably tell a
`prayer` block from a `sermon` block, and whether the spoken cues survive a
reverberant room and an unmic'd congregation. Everything else in the design
rests on those two things working.

This experiment answers them before anyone writes application code.

## Design principles

**Ground truth is free.** 22 recordings already have a human-made answer sitting
next to them. Aligning each MP3 inside its source FLAC recovers the punch-in and
punch-out you chose by hand. Nothing needs labelling for the primary metric,
which means the experiment can be re-run automatically after every change.

**Change one thing at a time.** The pipeline is ASR → speaker attribution →
blocking → classification → boundaries. Swapping several at once produces a
number nobody can interpret. So the reasoning ladder runs on a *fixed*
transcript, and the ASR ladder runs with *fixed* reasoning.

**A frontier model is the control, not the goal.** It establishes the ceiling
and tells us whether a gap is the local model's fault or the task being hard.
It never ships (Q76).

**Measure the curve, not a winner.** The output is a quality-versus-cost curve
across model sizes, so the deployment decision can be made against the real
hardware rather than guessed at now.

## What the bucket changed

Listing `s3://reformation-recordings/` after this design was first written
corrected one assumption and added a resource. Both are in `corpus.md`; the
short version:

- **Seven of 23 corpus recordings contain more than one session**, not one as I
  first thought. They start between 08:19 and 09:59 and run long, so the service
  sits somewhere inside them. This makes the corpus a better test of the Block
  model than expected, and it confirms that wall-clock time must be applied to
  Blocks rather than to Recordings.
- **57 unpublished recordings** exist in the bucket with no edit beside them.
  They are the only material available for testing that the pipeline does *not*
  invent work where there is none — a failure mode the 22 pairs cannot detect.

## Stages

### Stage 0 — Ground truth

No models. Prerequisite for everything else, and independently valuable: it
settles Q15.

First, join every Desktop FLAC to its bucket object by exact byte size. The
Desktop copies are renamed, and the bucket keeps the recorder's names — which
carry the wall-clock start time that the renaming destroyed. Start time is one of
the strongest classification signals in the spec, so this has to happen before
anything else.

Then, for each of the 22 pairs, find where the MP3 sits inside the FLAC.

The MP3 is a peak-normalized copy of a subrange of channel 1 — a linear gain, so
waveform shape is preserved and correlation locks on hard. Coarse-to-fine keeps
it cheap:

1. Decode both to mono 16 kHz. Take channel 1 of the FLAC only.
2. Build a short-term energy envelope at 100 Hz for each.
3. Normalized cross-correlation of the envelopes via FFT. 3 hours at 100 Hz is a
   million samples — milliseconds of compute. This gives the offset to within a
   few tens of milliseconds.
4. Refine at 16 kHz inside a ±1 s window around that peak.
5. `punch_in` = offset. `punch_out` = offset + MP3 duration.

Validation, because a silently wrong ground truth would poison every later
result:

- The correlation peak must be sharply higher than the runner-up. A flat or
  ambiguous peak means the pair is excluded and reported, never guessed.
- `offset + mp3_duration` must fall inside the FLAC.
- Spot-check: cut the FLAC at the derived boundaries, re-encode, and confirm it
  correlates with the MP3 near-perfectly.
- Eyeball three of them by ear.

Then do the same for `2026-08-02.flac`, aligning both 16-bit extractions and
both MP3s inside the parent, producing the only two-level labelled example we
have.

Also derived here, automatically: the **cut difficulty** of every true boundary,
from the silence around it. That is what lets later stages report failures
honestly instead of averaging them away.

**Output:** `groundtruth.json`, 22 recordings plus the two-level case, each
carrying its true start time, boundaries and per-boundary cut difficulty.

### Stage 1 — The reasoning ladder

The main experiment. Fix the transcript; vary the thinking.

Transcribe every recording once with the best local ASR available, with forced
alignment. Freeze those transcripts. Then run every rung of the ladder — rules,
4B, 14B, 35B, 70B-class, frontier — over the identical input, in both prompting
strategies (whole-transcript and per-block).

Tune on the 8 development recordings. Run the 14 held-out ones once per
configuration, and report.

**Answers:** Where does the curve flatten? Is the gap to the control a model-size
problem or a prompting problem? Can rules alone get close?

### Stage 2 — The ASR ladder

Fix the reasoning at the cheapest rung that matched the control. Vary the ASR
from tiny to large, with and without forced alignment.

The metric is not word error rate. It is:

- **Cue recall** — was "amen", "good morning", the communion invitation, "are
  there any questions" transcribed at all?
- **Cue timestamp error** — how far off was it?
- **Downstream boundary error** — the only thing that actually matters.

**Answers:** How small can the ASR go before cues start disappearing? Is forced
alignment necessary, or is it cheaper to run a bigger model?

### Stage 3 — Is diarization needed?

Ablation. Take the winning configuration and run it three ways: full
diarization, speaker verification against enrolled profiles only, and no speaker
information at all (`speaker: null` throughout).

**Answers:** whether the fiddliest, most GPU-hungry stage in the pipeline earns
its place. A "no" here is worth more than a few points of accuracy elsewhere.

### Stage 4 — Cost and latency

For every configuration that reached target: wall clock per recording, peak
memory, model footprint on disk. Measured on this machine, then extrapolated to
the deployment box.

A 90-minute recording processed in 20 minutes is fine — this runs on a Sunday
afternoon and nobody is waiting. That generous budget is itself a finding, since
it means the slowest acceptable option may well be the cheapest to deploy.

**Answers:** what actually runs on the homelab box, and whether a model host on
the tailnet is needed at all.

## What we will know at the end

- Whether the analysis design in `../features/` is sound, or needs rethinking.
- The smallest local model that matches a frontier model on this task.
- Whether diarization, forced alignment and a music classifier are each worth
  deploying, individually.
- A defensible answer to Q13 and Q76, from measurement rather than instinct.
- A regression suite that already exists, so every later change can be scored.

That last one matters more than it sounds. Stage 0 and the scoring harness *are*
`analysis/detection_accuracy.feature`. Building the experiment builds the test
suite, and it keeps working for as long as the project does.

## What could go wrong

**The alignment fails on some pairs.** Most likely if any MP3 was processed in a
way that is not a linear gain. Mitigation: excluded pairs are reported, and a
transcript-based alignment is the fallback since it is immune to amplitude
processing.

**The frontier control does poorly.** The most informative bad outcome. It would
mean the task is harder than the spec assumes — probably that the transcript
alone is insufficient and audio features are doing more work than expected. That
finding would change the design, and it is much better to have it now.

**22 recordings is a small corpus.** Real, and unfixable. The development split
guards against the worst of it, and results should be read as directional rather
than precise. The corpus grows by one every week regardless.

**Everything works and the answer is boring.** Entirely possible — the rules-only
rung may land close enough that the whole model question evaporates. That would
be the best outcome available, and it is why T0 is on the ladder.

## Files

| File | What it holds |
| --- | --- |
| `corpus.md` | The data: Desktop pairs, the raw bucket, the negative set, the split |
| `classification-spec.md` | The task contract: input, output, labels, scoring |
| `technology-candidates.md` | Candidates per stage, and what each rung is for |
| `AGENT-BRIEF.md` | How to build and run it: fences, contracts, gates, decision rules |
