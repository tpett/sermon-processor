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
| **Block type** | What a Block is. One closed vocabulary — see [The three vocabularies](#the-three-vocabularies) below. |
| **Segment** | A publishable or archivable span, built from one or more adjacent Blocks, with a refined punch-in and punch-out. The unit of *work* — this is what a reviewer approves and what renders to a file. |
| **Segment classification** | What a Segment is. **Not the same vocabulary as Block type** — see below. |
| **Recording kind** | What a whole Recording turned out to be. A third vocabulary again, and the one most often confused with the other two. |
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

### The three vocabularies

Reconciled 2026-09-17. Three different things were being named out of one list,
which is why the spec disagreed with itself in four places and asserted Segments
that cannot exist.

**1. Block type** — what one span of audio *is*. Closed set, assigned by
classification, never by a human action:

| Block type | Teaching? | Meaning |
| --- | --- | --- |
| `announcements` | | welcome, notices, housekeeping |
| `music` | | congregational singing or instrumental |
| `prayer` | | someone praying aloud; may contain long silence |
| `scripture_reading` | | a passage being read, usually announced by reference |
| `sermon` | **yes** | the Sunday message |
| `lesson` | **yes** | a class session: teaching, usually followed by questions |
| `seminar` | **yes** | a session of a multi-part course |
| `communion` | | the invitation to and serving of communion |
| `qa` | | audience questions; short alternating turns |
| `rehearsal` | | playing, stopping, restarting — a run-through, not a performance |
| `other` | | speech that is none of the above |

**2. Segment classification** — what a publishable unit *is*. A Segment takes
the type of the teaching Block it seeded on, so only the three teaching types
appear here, plus one that no classifier produces:

| Segment classification | Where it comes from |
| --- | --- |
| `sermon` | seeded on a `sermon` Block |
| `lesson` | seeded on a `lesson` Block |
| `seminar` | seeded on a `seminar` Block |
| `meeting` | **a human action, not classification** — "archive the whole recording" creates one Segment spanning everything |

There is no `music` Segment, no `prayer` Segment and no `other` Segment. A
Recording whose Blocks are all `music` produces **no Segments at all**, and that
is the correct outcome — not a Segment classified `music`. Anything asserting
otherwise is a spec bug.

**3. Recording kind** — what the whole file turned out to be. Descriptive, for
the reviewer's benefit; it changes no processing:

| Recording kind | Meaning |
| --- | --- |
| `service` | an ordinary Sunday |
| `class` | a teaching session, with or without a service attached |
| `special_service` | Good Friday, a prayer gathering, a seminar day — not an ordinary Sunday |
| `meeting` | a members' or business meeting |
| `rehearsal` | band practice or a sound check, start to finish |
| `empty` | the recorder triggered on nothing |
| `unknown` | none of the above fits |

`special_service` and `rehearsal` were previously listed as Block types. They are
not: a Good Friday service *contains* announcements, music, readings and
teaching Blocks. What is special is the service, not any span inside it.
`rehearsal` stays in both lists deliberately — a whole recording can be a
rehearsal, and a run-through can also sit inside a service recording, as on
2026-09-13.

### The seed rule

One rule, stated once, and everything about Segment boundaries follows from it:

> **Seed on each teaching Block** (`sermon`, `lesson`, `seminar`).
> **Extend forward through an immediately following `prayer` Block.** Stop there.
> A `lesson` or `seminar` additionally extends *backwards* through any
> `announcements`, `prayer` or `other` Blocks that lead into it, because a class
> is published from its beginning.

Consecutive Blocks of the same type are one Block for this purpose — a class the
classifier happened to split in two is still one class. (Learned the hard way:
without that, 2026-09-13 produced a 1.7-minute Segment from the first fragment of
its class.)

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

Measured from 33 real recordings in `~/Desktop/Sermons`, March–August 2026,
as recorded in `../experiments/data/groundtruth.json`. Regenerate this table from
that file rather than editing it by hand.
Scenarios rely on these, so they are recorded here rather than rediscovered.

| Property | Value |
| --- | --- |
| Container / codec | FLAC |
| Sample rate | 44,100 Hz |
| Channels | **2, but only channel 1 carries signal.** Channel 2 sits at the -90 dB noise floor in every sample. A mono source is being fed into a stereo recorder. |
| Bit depth | 32-bit container |
| Source duration | 37 – 203 minutes across 33 recordings |
| Source integrated loudness | around -19 to -20 LUFS, consistent week to week |
| Source true peak | 0.0 – 0.9 dBFS — **the source clips.** Known, being fixed at the hardware (Q67). |
| Output format | mono MP3, 44.1 kHz, VBR averaging ~100 kbps |
| Published segment length | 40 – 68 minutes (31 labelled segments) |

The render **takes channel 1 and discards channel 2**. It must never average
the two, which would cost 6 dB and fold in the dead channel's noise.

## Lifecycle

Two state machines: one for the Recording, one for each Segment. Redrawn
2026-09-17 — the previous diagrams were missing four states and five
transitions that features already asserted, and one state had no way out.

### Recording

```
                     ┌──────────────┐
    webhook / scan ─▶│  discovered  │◀──── retry when disk frees up
                     └──┬────────┬──┘      (reconciliation will NOT
              download  │        │          re-queue it: it only creates
                        │        │          Recordings for unseen keys)
                        ▼        │ no local disk
                 ┌──────────────┐│
                 │ downloading  │┘
                 └──┬────────┬──┘
                    │        │ retry budget exhausted
                    │        ▼
                    │  ┌────────────────┐  operator retries
                    │  │ ingest_failed  │──────────────┐
                    │  └────────────────┘              │
                    ▼                                  │
             ┌──────────────┐◀─────────────────────────┘
             │  downloaded  │
             └──────┬───────┘
                    ▼
             ┌──────────────┐  nothing substantive   ┌───────────┐
             │  analyzing   │──────────────────────▶ │  ignored  │
             └──┬────────┬──┘  (probe stage, no      └─────┬─────┘
                │        │      human asked)               │ reviewer
                │        │ analysis fails                  │ restores
                │        ▼                                 │
                │ ┌──────────────────┐                     │
                │ │ analysis_failed  │───────┐             │
                │ └──────────────────┘       │ segment     │
                ▼                            │ by hand     │
        ┌──────────────────┐◀────────────────┘             │
        │ awaiting_review  │◀──────────────────────────────┘
        └──────┬───────────┘
               │ every Segment dispositioned
               ▼
        ┌──────────────┐  a skipped Segment is revisited
        │   reviewed   │──────────────────────────────┐
        └──────────────┘◀─────────────────────────────┘
                          (back to awaiting_review)

    any state ─────────▶ ┌──────────────┐
                         │  discarded   │   the whole file is rubbish
                         └──────────────┘
```

**`ignored` is not `discarded`.** `ignored` is the machine's own call on a
Recording with no substantive content — no human is asked, no notification is
sent, and it stays out of the default list but remains findable and restorable.
`discarded` is a human throwing something away. Conflating them would mean either
pestering the reviewer about every false trigger or silently destroying real
recordings.

**`discovered` has two exits, and it needs both.** A Recording that cannot be
downloaded for want of disk stays in `discovered` and raises a storage alert —
but reconciliation only creates Recordings for object keys it has *never seen*,
so it will never be picked up again by a scan. Something has to retry it when
space frees up. This was a dead end in the previous diagram and is the one
genuine deadlock the redraw found.

**`reviewed` is not terminal**, and now says how it is left: revisiting a skipped
Segment returns the Recording to `awaiting_review`.

### Segment

```
                    ┌────────────┐
      analysis ────▶│  proposed  │◀──────────────────────┐
                    └──┬──────┬──┘                       │
             approve   │      │   skip                    │ revert,
                       ▼      ▼                           │ or cancel
             ┌────────────┐  ┌───────────┐                │ processing
             │  approved  │  │  skipped  │──┐             │
             └─────┬──────┘  └───────────┘  │ revisit,    │
                   │  ▲            ▲        │ any time    │
                   │  └────────────┴────────┘             │
                   ▼                                      │
            ┌────────────┐                                │
            │ processing │────────────────────────────────┘
            └──┬──────┬──┘
               │      │ render fails    ┌────────────────────┐
               │      └───────────────▶ │ processing_failed  │──┐
               │                        └────────────────────┘  │ retry
               ▼                                                │
         ┌───────────┐                                          │
         │ complete  │◀─────────────────────────────────────────┘
         └─────┬─────┘
               │ re-cut
               ▼
         ┌───────────┐  adjust and re-approve
         │   recut   │────────────────────────▶ processing
         └───────────┘
```

**`recut` is a state, not a loop.** A re-cut Segment still has a finished
artifact and a published file behind it, which is exactly what distinguishes it
from `proposed` — the old artifact stays until the new one succeeds.

**Three ways back to `proposed`**, all asserted by features and none previously
drawn: reverting an approval before processing starts, cancelling processing
mid-render (partial output discarded), and reverting adjusted boundaries to the
machine proposal.

### Every state, and how it is left

| State | Of | Exits |
| --- | --- | --- |
| `discovered` | Recording | `downloading`; stays put with an alert if disk is short, and needs an explicit retry |
| `downloading` | Recording | `downloaded`, or `ingest_failed` when the retry budget runs out |
| `ingest_failed` | Recording | `downloaded` on an operator retry |
| `downloaded` | Recording | `analyzing` |
| `analyzing` | Recording | `awaiting_review`, `analysis_failed`, or `ignored` |
| `analysis_failed` | Recording | `awaiting_review` if a human segments it by hand |
| `ignored` | Recording | `awaiting_review` if a reviewer restores it |
| `awaiting_review` | Recording | `reviewed` once every Segment is dispositioned |
| `reviewed` | Recording | back to `awaiting_review` when a skipped Segment is revisited |
| `discarded` | Recording | terminal, reachable from any state |
| `proposed` | Segment | `approved` or `skipped` |
| `approved` | Segment | `processing`, or back to `proposed` on revert |
| `skipped` | Segment | `proposed` when revisited |
| `processing` | Segment | `complete`, `processing_failed`, or `proposed` if cancelled |
| `processing_failed` | Segment | `processing` on retry |
| `complete` | Segment | `recut` |
| `recut` | Segment | `processing` once boundaries are adjusted and re-approved |

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
| `@measured` | A number here came from the corpus. The comment names what was measured and over how many recordings. |
| `@stated` | The owner said this in QUESTIONS.md. A preference, not an observation — and the corpus sometimes disagrees with it. |
| `@policy` | A decision about how the system should behave. Nothing measured it and nothing could. |
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
