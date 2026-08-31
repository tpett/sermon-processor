# Sermon Processor — Feature Specifications

These are executable-style specifications written in Gherkin. Nothing has been
built yet. The point of this folder is to pin down *what the system does*
before anyone argues about *how it does it*.

Every scenario here should be readable by a non-programmer. Where the source
README left a hole, the scenario states an explicit assumption in a comment
tagged with a question ID (e.g. `# Q7`) that maps to [QUESTIONS.md](QUESTIONS.md).
Those are the places where the spec is a guess, not a decision.

> **Revised 2026-08-26.** The original spec assumed one recording contained one
> sermon. It does not. A single file can hold a 9:00 class and the 10:30
> service, and the tool is used for anything worth publishing, not sermons
> alone. The **Segment** model below replaces the old one-cut-per-recording
> shape. See Q63 and Q64 in QUESTIONS.md for the reasoning.

## Ubiquitous language

| Term | Meaning |
| --- | --- |
| **Recording** | One source audio file produced by the Raspberry Pi recorder — a FLAC plus its `.meta.json` sidecar. The unit of *ingestion*. |
| **Recorder** | The existing `audio-recorder` application running on the Pi. |
| **Object store** | The Garage S3 instance on the homelab tailnet that the Recorder uploads to. |
| **Ingestion** | Learning that a Recording exists and pulling it local. |
| **Analysis** | Everything the machine does unattended: probing, transcribing, blocking, classifying, summarising and proposing Segments. |
| **Block** | A contiguous span of the Recording attributed to one speaker doing one thing. The *anatomy* of a service: announcements, singing, a prayer, a scripture reading, the sermon. Machine-produced, never published on its own. |
| **Block type** | What a Block is: `announcements`, `music`, `prayer`, `scripture_reading`, `sermon`, `lesson`, `communion`, `qa`, `other`. |
| **Segment** | A publishable or archivable span, built from one or more adjacent Blocks, with a refined punch-in and punch-out. The unit of *work* — this is what a reviewer approves and what renders to a file. |
| **Punch-in** | Where a Segment starts, in seconds from the beginning of the source file. |
| **Punch-out** | Where a Segment ends, in seconds from the beginning of the source file. |
| **Proposal** | A Segment's boundaries, its classification, its confidence and the evidence behind it. |
| **Evidence** | A human-readable reason the machine drew a boundary or chose a classification — a speaker change, a matched phrase, a start time. |
| **Summary** | A one-line machine description of what a Block or Segment contains, so a reviewer can decide without listening. |
| **Cue excerpt** | The few seconds of a Block most likely to let a human recognise it instantly. What the Preview button plays. |
| **Disposition** | What the reviewer decides about a Segment: **approve** it (render it) or **skip** it (leave it, retained and revisitable). |
| **Intent** | Why a Segment is being rendered: `publish` or `archive`. Always confirmed by a human, never assumed. |
| **Processing** | Rendering an approved Segment into a distributable artifact. |
| **Artifact** | Any output file derived from a Recording — a rendered MP3, the waveform peaks, the transcript, the retained FLAC. |

### Blocks and Segments — why two levels

A Recording is whatever the recorder produced. It is not a meaningful unit of
content, and on a class Sunday it holds two things worth publishing.

**Blocks** are the anatomy. The recording is divided wherever the speaker or the
activity changes, and each piece is classified. A normal Sunday looks roughly
like:

```
announcements │ music │ scripture_reading │ prayer │ sermon │ prayer │ communion │ music
```

**Segments** are what gets published. A Segment is built by seeding on a
teaching Block and extending it through what belongs with it. The sermon Segment
is `sermon` plus its trailing `prayer`, stopping before `communion`. The class
Segment is `lesson` plus its trailing `prayer`, stopping before `qa`. One rule,
two kinds of service — a generic solution rather than a pattern match on this
year's running order.

This is why the boundary rules are short. Punch-in and punch-out mostly *fall
out* of the block classification rather than being detected separately. The
spoken cues — "turn with me to Romans", "amen", the communion invitation, "are
there any questions" — are inputs to **classifying a Block**, not rules for
placing a boundary.

**Nothing detected is thrown away.** A Segment the reviewer skips keeps its
boundaries, classification, summary and evidence indefinitely, so a piece passed
over in August can be extracted in November without re-analysing. The object
store keeps sources indefinitely, so that promise holds (Q71).

## Timecode conventions

- Internally, all timecodes are **seconds from the start of the source
  Recording**, stored as a float with millisecond precision (`1234.567`).
  Segment boundaries are absolute against the source file, never relative to
  the Segment.
- The interface displays them as `H:MM:SS.mmm`.
- Scenarios written in `H:MM:SS` form are shorthand for the same value with
  `.000` milliseconds.

## Source audio facts

Measured from 24 real recordings in `~/Desktop/Sermons`, April–August 2026.
Scenarios rely on these, so they are recorded here rather than rediscovered.

| Property | Value |
| --- | --- |
| Container / codec | FLAC |
| Sample rate | 44,100 Hz |
| Channels | **2, but only channel 1 carries signal.** Channel 2 sits at the -90 dB noise floor in every sample. A mono source is being fed into a stereo recorder. |
| Bit depth | 24-bit |
| Source duration | 79 – 155 minutes |
| Source integrated loudness | around -19 to -20 LUFS, consistent week to week |
| Source true peak | 0.0 – 0.9 dBFS — **the source clips.** Known, being fixed at the hardware (Q67). |
| Output format | mono MP3, 44.1 kHz, VBR averaging ~100 kbps |
| Published segment length | 40 – 68 minutes |

The render **takes channel 1 and discards channel 2**. It must never average
the two, which would cost 6 dB and fold in the dead channel's noise.

## Lifecycle

Two state machines now: one for the Recording, one for each Segment.

### Recording

```
                    ┌──────────────┐
   webhook / scan ─▶│  discovered  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐   download fails N times   ┌────────────────┐
                    │ downloading  │──────────────────────────▶ │ ingest_failed  │
                    └──────┬───────┘                            └────────────────┘
                           ▼
                    ┌──────────────┐
                    │  downloaded  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐   analysis fails           ┌──────────────────┐
                    │  analyzing   │──────────────────────────▶ │ analysis_failed  │
                    └──────┬───────┘                            └────────┬─────────┘
                           ▼                                             │ segment
                    ┌──────────────────┐                                 │ by hand
                    │ awaiting_review  │◀────────────────────────────────┘
                    └──────┬───────────┘
                           │ every Segment dispositioned
                           ▼
                    ┌──────────────┐
                    │   reviewed   │
                    └──────────────┘

   any state ─────▶ ┌──────────────┐  (whole file is rubbish — e.g. band practice)
                    │  discarded   │
                    └──────────────┘
```

`reviewed` is not terminal. Revisiting a skipped Segment is expected and
normal; it changes the Segment's state, not the Recording's.

### Segment

```
                 ┌────────────┐
   analysis ────▶│  proposed  │
                 └──┬──────┬──┘
          approve   │      │   skip
                    ▼      ▼
          ┌────────────┐  ┌───────────┐
          │  approved  │  │  skipped  │──┐
          └─────┬──────┘  └───────────┘  │ revisit, any time later
                ▼              ▲          │
         ┌────────────┐        └──────────┘
         │ processing │
         └──┬──────┬──┘
            │      │ render fails      ┌────────────────────┐
            │      └─────────────────▶ │ processing_failed  │
            ▼                          └────────────────────┘
      ┌───────────┐
      │ complete  │──┐
      └───────────┘  │ re-cut
            ▲        │
            └────────┘
```

## Folder map

| Folder | Covers |
| --- | --- |
| `ingestion/` | Webhook contract, S3 reconciliation, download, idempotency |
| `analysis/` | Probe, transcription, diarization, **blocking**, **block classification**, **summarisation**, Segment proposal, confidence, accuracy regression |
| `interface/` | List, detail, **segment review**, waveform, boundary editing, publication details, approval, discarding, auth |
| `notifications/` | Telling a human there is work waiting |
| `processing/` | ffmpeg render, channel extraction, loudness, artifacts, re-cutting |
| `operations/` | Job queue & retries, storage/retention, health |

## Tag conventions

| Tag | Meaning |
| --- | --- |
| `@ingestion` `@analysis` `@interface` `@processing` `@ops` | Subsystem |
| `@happy-path` | The main flow — build these first |
| `@edge-case` | Real failure modes we know about |
| `@assumption` | Behaviour invented to fill a gap. Confirm before building. |
| `@needs-decision` | Cannot be built until a question in QUESTIONS.md is answered. |
| `@measured` | Behaviour derived from measuring the real recordings, not guessed. |
| `@slow` | Touches real audio processing; will not be a fast unit-level test. |
| `@manual` | Verified by a human, not automatable (audio quality judgements). |
| `@mobile` | Must work on a phone. Everything else may assume a desktop browser. |

## Reading order for a newcomer

1. `ingestion/webhook_notification.feature`
2. `analysis/analysis_orchestration.feature`
3. `analysis/blocking.feature` — **start here to understand the model**
4. `analysis/block_classification.feature`
5. `analysis/segment_proposal.feature`
6. `analysis/summarization.feature`
7. `interface/recording_list.feature` → `segment_review.feature` → `approval.feature`
8. `processing/audio_rendering.feature`
9. `analysis/detection_accuracy.feature` — how we know any of it works
