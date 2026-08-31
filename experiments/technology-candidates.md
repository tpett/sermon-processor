# Technology Candidates

Hardware in play:

- **This machine** — Apple M5 Max, 128 GB unified memory, macOS 26.3. Very
  capable; can run models far larger than the deployment box. `ollama 0.32.15`
  installed with `qwen3.6:35b-mlx` already pulled. `uv`, `ffmpeg 8.1`, Docker.
- **The deployment box** — homelab server, ~26 TB storage, little GPU.
- Possible third machine: an older Mac with unified memory, acting as a model
  host on the tailnet.

That split matters. This machine sets the *ceiling* of what local can do; the
deployment box decides what we can actually run every Sunday. The experiment
measures the curve so that decision is made from data.

Everything below is local-only except the control, per Q76.

---

## Stage: transcription

The requirement is unusual and worth stating plainly: **we do not need a good
transcript. We need the cue phrases transcribed at accurate timestamps.**
Overall word error rate is close to irrelevant. Whether "amen" lands within
200 ms of where it was actually said is what decides a punch-out.

| Candidate | Notes |
| --- | --- |
| `whisper.cpp` large-v3 | Metal-accelerated, no Python. The obvious local baseline. |
| `whisper.cpp` large-v3-turbo | Much faster, small accuracy cost. Likely the sweet spot. |
| `mlx-whisper` | Apple Silicon native, typically fastest on M-series. |
| `distil-whisper` large-v3 | ~6x faster, small WER penalty. Worth a rung on the ladder. |
| `whisper.cpp` medium / small / base | The cheap end. Included to find where cues start breaking. |
| Parakeet TDT (`parakeet-mlx`) | English-only, very fast, strong WER. Different architecture, so a useful check on Whisper-family assumptions. |

**The timestamp problem.** Whisper's native word timestamps are known to be
loose — often hundreds of milliseconds off, which is exactly the precision we
care about. Two mitigations, and testing them is part of Stage 2:

| Candidate | Notes |
| --- | --- |
| WhisperX | Forced-alignment pass with wav2vec2 over Whisper output. The standard fix. |
| `torchaudio` forced alignment | Roll it ourselves against the Whisper transcript. Fewer dependencies. |
| Montreal Forced Aligner | Heavier, very accurate. Probably overkill. |

My expectation, worth disproving: a mid-size Whisper plus forced alignment beats
a large Whisper without it, for our purposes, at lower cost.

## Stage: voice activity and silence

Needed for the `silences` input and for boundary snapping. Cheap and unlikely to
be a differentiator, so pick one and move on.

| Candidate | Notes |
| --- | --- |
| `ffmpeg silencedetect` | Zero dependencies, already installed. Start here. |
| Silero VAD | Tiny ONNX model, more robust to room noise. Upgrade if ffmpeg proves noisy. |

## Stage: music versus speech

Twenty minutes of congregational singing must not be mistaken for teaching.

| Candidate | Notes |
| --- | --- |
| ASR confidence and density | Free — singing produces sparse, low-confidence output. Try first. |
| inaSpeechSegmenter | Purpose-built speech/music segmentation. Small and fast. |
| YAMNet / PANNs | AudioSet classifiers with explicit singing and music classes. Heavier. |

Worth testing whether this stage is needed at all. If the ASR signal alone
separates music from speech, that is one fewer model to deploy.

## Stage: speaker attribution

Two framings, and the cheaper one may be enough.

**Full diarization** — who spoke when, no prior knowledge:

| Candidate | Notes |
| --- | --- |
| `pyannote.audio` 3.1 | Best quality. Needs a HuggingFace token; check the licence terms. |
| `sherpa-onnx` diarization | Fully offline, no token, ONNX. Easier to deploy. |
| NVIDIA NeMo (Sortformer) | Strong, heavier stack. |

**Speaker verification** — is this the known preacher? Per Q12 the roster is one
primary plus three or four others, which makes this a much easier problem than
open diarization:

| Candidate | Notes |
| --- | --- |
| SpeechBrain ECAPA-TDNN | Embeddings plus cosine similarity against enrolled profiles. Simple. |
| WeSpeaker | Similar, strong benchmarks. |
| Resemblyzer | Very simple, older, may be enough. |

**This is the ablation I most want to run.** Diarization is the fiddliest stage
to deploy and the most likely to need a GPU. If time-of-day, the running-order
prior and transcript cues get us to target without it, that is a large
simplification. Stage 3 tests exactly this.

## Stage: block classification

The reasoning ladder. Every rung consumes the same input and emits the same JSON
(see `classification-spec.md`).

| Rung | Candidate | Why it is on the ladder |
| --- | --- | --- |
| T0 | Rules only — keyword patterns, speaker changes, silence, wall-clock time | The floor. If this gets close, no model is needed and the whole question dissolves. |
| T1 | Qwen3-4B / Gemma3-4B / Llama-3.2-3B | Runs on almost anything, including the deployment box CPU. |
| T2 | Qwen3-14B / Gemma3-12B | Comfortable on a modest GPU or an M-series laptop. |
| T3 | `qwen3.6:35b-mlx` (already pulled) / Gemma3-27B | Needs a real machine. Roughly the practical ceiling for a dedicated model host. |
| T4 | A 70B-class or large MoE model | 128 GB can hold it. Included to see whether the curve is still climbing. |
| C | Frontier model via API | The control. Not a deployment candidate (Q76) — the number everything else is measured against. |

### Two prompting strategies, tested separately

This is the variable most likely to decide whether a small model succeeds.

- **Whole transcript.** The model sees the entire service — roughly 12,000 to
  15,000 tokens — and returns all blocks at once. Best global reasoning, since
  the running order is visible. Needs long context and strong instruction
  following.
- **Per candidate block.** Pre-split on speaker change and silence, then ask the
  model to type each block individually, given its text, its neighbours' types
  and the expected Sunday order. Short prompts, trivially parallel, and far
  friendlier to a 4B model. Loses some global consistency.

I expect the per-block strategy to close most of the gap between T1 and T3, and
that finding — if it holds — is worth more than any individual model choice.

## Stage: summarisation

Not on the critical path. Summaries cannot affect output by design, so this is
scored by eye rather than measured, and whichever model wins the classification
ladder can be reused.

---

## The control

A frontier model over the transcript, using the whole-transcript strategy. It
serves three purposes:

1. The quality ceiling. If the control cannot do this reliably, the task is
   harder than the spec assumes and the design needs revisiting before any local
   model is blamed.
2. The bootstrap for Level 2 labels — it proposes blocks, a human corrects.
3. The reference in every results table.

Volume is small: roughly 20k input tokens per recording, 22 recordings, a couple
of runs. Call it under a million tokens for the whole experiment, one-off. That
is a rounding error against the value of knowing where the ceiling is, and it
does not compromise the local-only production constraint — the control never
ships.

## Deliberately excluded

- **Hosted ASR and hosted LLMs in production.** Settled by Q76.
- **Training or fine-tuning anything.** 22 recordings is not a training set. If
  fine-tuning ever becomes interesting it will be after a year of approved
  Segments accumulate, which the spec already provides for.
- **End-to-end audio LLMs.** Interesting, but they collapse the ASR and
  reasoning variables back together, which is the one thing this design is built
  to avoid.
