# Implementation Brief

Everything an agent needs to build and run the spike without supervision, plus
the points where it must stop and ask.

Read `README.md` for why, `corpus.md` for what data exists,
`classification-spec.md` for the task contract, `technology-candidates.md` for
what to try. This file is the how.

---

## Non-negotiables

Violating any of these invalidates the experiment or destroys data. They are not
guidelines.

1. **`~/Desktop/Sermons` is read-only.** It is the only copy of the ground
   truth. Never write, move, rename or delete anything in it. Derive working
   copies elsewhere.
2. **`s3://reformation-recordings/` is read-only.** List and download only.
   Never put, never delete. It is the church's raw archive.
3. **No audio leaves this machine.** Ever, to anything. The control receives
   *transcripts only* — see the control section. This is Q76, and it is a
   constraint on the experiment as much as on production.
4. **Never tune on the held-out set.** See "Held-out discipline" below. This is
   mechanically enforced; do not work around it.
5. **Do not modify `../features/`.** The spec is a separate artifact. Findings
   that contradict it go in `FINDINGS.md` and are raised, not silently applied.
6. **No fine-tuning or training.** 22 recordings is not a training set.
7. **Do not download the whole bucket.** It is 36.6 GB. Fetch named objects only,
   and only when not already available locally.

---

## Environment

Target: this machine — Apple M5 Max, 128 GB, macOS 26. Already present:
`uv 0.11`, `python 3.14`, `ffmpeg 8.1`, `ollama 0.32` (with `qwen3.6:35b-mlx`),
`aws` with profile `nas`, 2.5 TB free.

```bash
cd sermon-processor/experiments
uv init --no-workspace .
uv add numpy scipy soundfile
```

Add per stage, not up front — a failed install of a stage-3 dependency should
not block stage 0.

**Verify before starting:**

```bash
aws --profile nas s3 ls s3://reformation-recordings/ | wc -l   # expect 83
ls ~/Desktop/Sermons/*.flac | wc -l                            # expect 28
ffmpeg -version | head -1
ollama list
```

If any check fails, HALT and report. Do not improvise around missing data.

---

## Layout and CLI contract

Later stages compose with earlier ones, so the interfaces are fixed here rather
than invented as you go.

```
experiments/
  src/
    align.py          # stage 0: ground truth
    transcribe.py     # stage 1/2: audio -> transcript.json
    blocks.py         # pre-splitting for the per-block strategy
    classify.py       # any rung -> blocks.json + segments
    score.py          # blocks/segments + groundtruth -> results.jsonl
    report.py         # results.jsonl -> markdown tables
  prompts/
    whole_transcript.v1.md
    per_block.v1.md
  work/               # gitignored: audio derivatives, caches
  data/
    groundtruth.json
    transcripts/<recording_id>.<asr_config>.json
    blocks/<recording_id>.<config_id>.json
    results.jsonl
  FINDINGS.md
```

Every script: `--help`, exit non-zero on failure, idempotent, and safe to
re-run. Anything expensive is cached (see Determinism).

`recording_id` is the recorder object key stem — `recording_20260823_102952`.
Not the Desktop label. The bucket name is the identity; the Desktop label is
metadata.

`config_id` is a stable slug: `t3-qwen3.6-35b-mlx.perblock.v1`.

---

## Artifact schemas

`transcript.json`:

```json
{ "recording_id": "recording_20260823_102952",
  "asr_config": "whisper-large-v3-turbo+wav2vec2-align",
  "started_at": "2026-08-23T10:29:52-05:00",
  "duration": 6268.95,
  "utterances": [ {"start": 12.44, "end": 18.90, "speaker": "S1",
                   "text": "...", "confidence": 0.93,
                   "words": [{"w":"Good","start":12.44,"end":12.71}]} ],
  "silences": [ {"start": 1544.2, "end": 1562.8} ] }
```

`blocks.json` — exactly the output shape in `classification-spec.md`, plus
`config_id`, `wall_clock_s` and `peak_rss_mb`.

`results.jsonl` — one object per (config, recording):

```json
{ "config_id": "...", "stage": 1, "recording_id": "...", "split": "dev",
  "found": true, "punch_in_error": -0.42, "punch_out_error": 1.10,
  "difficulty_in": "easy", "difficulty_out": "moderate",
  "classification_correct": true, "wall_clock_s": 214.0, "peak_rss_mb": 9100 }
```

Never overwrite `results.jsonl`. Append. It is the experiment's record.

---

## Determinism and caching

- Sampling: temperature 0, greedy, fixed seed where the runtime exposes one.
  Record whatever the runtime actually used.
- Cache key: `sha256(model_id + model_digest + prompt_template_version +
  input_json)`. A cache hit must be free — re-running the full ladder after a
  scoring change should cost nothing.
- Record the exact model digest (`ollama show`), not just the tag. Tags move.
- Log every non-determinism you cannot eliminate, rather than hiding it.

---

## Held-out discipline

An agent optimising a metric will drift onto the test set unless stopped
mechanically. So:

- `score.py` refuses `--split test` unless given `--final`, and every `--final`
  invocation appends to `data/test_access.log` with the timestamp, config_id and
  git commit.
- Each configuration gets **one** test run. If a config is re-run on test after
  any change, that is a new config_id.
- Tuning — prompt edits, keyword lists, thresholds — happens against
  `--split dev` only.
- If the test log shows more than one run per config_id, say so in `FINDINGS.md`.
  A contaminated result reported honestly is worth more than a clean-looking lie.

---

## Stages, with gates

### Stage 0 — ground truth

1. Join Desktop FLACs to bucket keys by exact byte size. Expect 26 unique
   matches, 2 unmatched (the 16-bit extractions). Any other result: HALT.
2. Recover `started_at` from each object key.
3. Align each MP3 inside its FLAC by the coarse-to-fine method in `README.md`.
4. Validate every pair: peak ratio over runner-up, offset plus MP3 duration
   inside the FLAC, and a re-cut round trip that correlates near-perfectly.
   Pairs failing validation are **excluded and listed**, never guessed.
5. Derive `difficulty_in` and `difficulty_out` from silence around each true
   boundary, using the thresholds in `classification-spec.md`.
6. Do the same for `2026-08-02`, aligning both 16-bit extractions and both MP3s
   inside the parent.

**GATE 0 — human required.** Produce three 20-second audio clips cut at derived
boundaries and have a human confirm by ear that they start and end where a human
editor would. Do not proceed to Stage 1 until confirmed. Everything downstream
is measured against this; a silently wrong alignment invalidates the whole
experiment.

### Stage 1 — reasoning ladder

Transcribe every corpus recording once with the strongest local ASR that runs,
with forced alignment. Freeze those transcripts and reuse them for every rung —
this is the whole point of the stage.

Run every rung in `technology-candidates.md`, in both prompting strategies,
against `--split dev`. Then one `--final` run per surviving configuration.

Stop climbing when two consecutive rungs improve `no_edit@1s` by under 3
percentage points on dev, or when the rung matches the control (below).

### Stage 2 — ASR ladder

Fix reasoning at the cheapest rung that matched the control. Vary ASR, with and
without forced alignment. Score cue recall, cue timestamp error, and downstream
boundary error.

### Stage 3 — diarization ablation

Winning configuration, three ways: full diarization, verification against
enrolled profiles, and `speaker: null` throughout.

Use `sherpa-onnx` rather than `pyannote` unless a HuggingFace token is supplied
— pyannote is gated and there is no token on this machine. If the ablation shows
speaker information matters, revisit and ask for a token then.

### Stage 4 — cost and latency

Wall clock and peak RSS are recorded per run throughout, so this is a reporting
step, not a measurement campaign.

---

## The control

There is no `ANTHROPIC_API_KEY` on this machine, and one is not needed. Run the
control by dispatching a subagent per recording with the transcript and
`prompts/whole_transcript.v1.md`, requiring the same JSON output. It is a
frontier model, it is the same task, and it costs nothing extra to arrange.

Send **the transcript only**. Never audio. If a transcript would exceed the
subagent's practical limit, chunk with overlap and record that you did — do not
silently truncate.

The control is a measurement, not a candidate. It never appears in a deployment
recommendation.

---

## Decision rules

Numeric, so no judgement calls are needed mid-run.

- **Matches the control**: `found` = 100% on dev, and `no_edit@1s` within 5
  percentage points of the control's.
- **Meets target**: `found` = 100% on test, and `no_edit@1s` ≥ 80%.
- **Winner**: the cheapest configuration meeting target, where cost is model
  footprint first and wall clock second.
- **Invalid JSON**: retry twice with a repair prompt. Then mark that recording
  `FAILED` for that config and continue. A config failing more than 3 of 22 is
  reported as unusable rather than partially scored.
- **Timeout**: 15 minutes per recording per config. Exceeded, mark `TIMEOUT`.
- **Stage budget**: 6 hours. Exceeded, HALT and report progress.

---

## Failure and escalation

- A missing dependency, a failed check, an ambiguous size join, or a
  validation failure: **HALT and report**. Do not improvise around bad data.
- A single model failing to load: skip that rung, record why, continue.
- Anything that would require modifying the non-negotiables: HALT and ask.

Report a stage that produced a clear negative result as a success. "Diarization
does not help" is a finding worth having.

---

## Reporting

Keep `FINDINGS.md` updated as you go, not at the end. It holds:

1. A results table per stage: config_id, split, `found`%, `no_edit` at 0.25/0.5/1/2/5 s,
   median and worst punch-in and punch-out error, all split by difficulty.
2. The confusion matrix for any config scored at Level 2.
3. Cost per config: model footprint, wall clock per recording, peak RSS.
4. **Surprises.** Anything that contradicts `../features/` or this brief, stated
   plainly, with the evidence.
5. A recommendation, once Stage 4 is done: which configuration, on which
   machine, and what it cannot do.

---

## HALT points needing a human

| When | What is needed | Why it cannot be automated |
| --- | --- | --- |
| After Stage 0 | Confirm three derived boundaries by ear | Everything is measured against this |
| Before Level 2 | Correct ~40 machine-proposed blocks across 4 recordings | Only a human knows what the blocks really were |
| Negative set | Mark 12 sampled bucket recordings publishable or not | Binary judgement, a few minutes |
| Before each `--final` | Confirm the config is frozen | Protects the held-out set |
| Stage 3, if speaker info matters | A HuggingFace token for pyannote | Gated model |

Batch these. Stage 0's gate and the Level 2 labelling can be presented together,
so the human is interrupted once rather than four times.
