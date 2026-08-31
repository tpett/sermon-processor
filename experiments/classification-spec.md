# The Classification Task

A single, testable contract. Every candidate technology — a regex, a 4B local
model, a frontier model — is handed the same input and must return the same
shape, so results are directly comparable and scoring is automatic.

Deliberately narrower than the full feature spec. This is the smallest task that
still exercises the thing we do not know how to do.

## Input

One JSON document per recording.

```json
{
  "recording_id": "2026-08-23",
  "started_at": "2026-08-23T10:29:52-05:00",
  "duration": 6268.95,
  "utterances": [
    { "start": 12.44, "end": 18.90, "speaker": "S1",
      "text": "Good morning and welcome, it is good to have you with us." }
  ],
  "silences": [ { "start": 1544.2, "end": 1562.8 } ]
}
```

- `utterances` — the transcript, in order, with timestamps in seconds from the
  start of the source file.
- `speaker` — a diarization label, or `null` throughout when the ablation runs
  without diarization. Candidates must tolerate `null`.
- `silences` — every gap over 2 seconds, from VAD. Cheap to produce and
  independent of every other choice, so it is always supplied.

Nothing else. No audio is given to the classifier. That is intentional: it keeps
the reasoning ladder and the ASR ladder independent, so a bad result has one
cause instead of two.

## Output

```json
{
  "blocks": [
    { "start": 0.0, "end": 261.0, "type": "announcements", "confidence": 0.9,
      "evidence": "welcome and notices, one speaker" },
    { "start": 261.0, "end": 1900.0, "type": "music", "confidence": 0.95,
      "evidence": "no coherent speech, repeated passages" },
    { "start": 1900.0, "end": 1946.0, "type": "scripture_reading", "confidence": 0.9,
      "evidence": "announces Hebrews 12 and reads" },
    { "start": 1946.0, "end": 4360.0, "type": "sermon", "confidence": 0.95,
      "evidence": "sustained single-speaker teaching after the reading" },
    { "start": 4360.0, "end": 4492.0, "type": "prayer", "confidence": 0.9,
      "evidence": "closing prayer, ends on amen" },
    { "start": 4492.0, "end": 4800.0, "type": "communion", "confidence": 0.9,
      "evidence": "invitation addressed to visitors" }
  ],
  "segments": [
    { "punch_in": 1946.0, "punch_out": 4492.0, "classification": "sermon",
      "confidence": 0.9 }
  ]
}
```

### Block types

| Type | Definition |
| --- | --- |
| `announcements` | Welcome, notices, housekeeping. |
| `music` | Singing or instrumental. No teaching. |
| `prayer` | Someone praying aloud. May contain long silence. |
| `scripture_reading` | A passage being read, usually announced by reference. |
| `sermon` | The Sunday message. Sustained teaching, follows the reading. |
| `lesson` | A class or seminar session. Teaching, but followed by Q&A. |
| `communion` | The invitation to and serving of communion. |
| `qa` | Audience questions. Short alternating turns, questions often inaudible. |
| `other` | Speech that is none of the above. |

### Rules the output must satisfy

1. Blocks are contiguous and non-overlapping, covering `[0, duration]`.
2. Every block is at least 60 seconds, except where the recording ends.
3. `segments` is derived by one rule, and candidates are expected to apply it:
   **seed on a `sermon` or `lesson` block; extend forward through an
   immediately following `prayer` block; stop there.**
4. `punch_in` and `punch_out` are absolute seconds against the source file.
5. Zero segments is a valid answer, and is correct for band practice or a false
   trigger.

Rule 3 is given rather than discovered. We are testing whether a technology can
identify the *anatomy* of a service. Whether it can also invent the editorial
rule is a different question, and not one worth risking a small model on.

## Scoring

Two levels, and they need different amounts of work to set up.

### Level 1 — Segment boundaries. No labelling required.

Ground truth comes from aligning each published MP3 inside its source FLAC (see
`README.md`, Stage 0). For each recording:

| Measure | Definition |
| --- | --- |
| `found` | A proposed segment overlaps the true segment by more than half its length. |
| `punch_in_error` | Signed seconds. Positive means late — the start is clipped. |
| `punch_out_error` | Signed seconds. Positive means late — extra tail. |
| `no_edit@t` | `found` and both absolute errors within `t`. |
| `classification_correct` | Proposed `sermon` / `lesson` matches. |

Reported as the distribution, plus `no_edit` at 0.25 s, 0.5 s, 1 s, 2 s and 5 s.
A single tolerance would hide the shape, and the shape is the interesting part.

`found` is reported separately from the errors on purpose. Missing the sermon
entirely and being two seconds late are different failures, and averaging them
into one number would disguise the first.

Per Q75, punch-in is weighted above punch-out in any single headline figure, and
results are split by cut difficulty — which is derived automatically from the
silence around the true boundary, not labelled by hand:

| Silence available at the true cut | Difficulty |
| --- | --- |
| 2 s or more of quiet | easy |
| 250 ms to 2 s | moderate |
| under 250 ms, or audible noise within 250 ms | hard |

### Level 2 — Block types. Requires a little labelling.

Level 1 can be gamed: a system could get boundaries right for the wrong reasons
and fall apart on an unusual week. Level 2 checks the reasoning underneath.

Ground truth: **four recordings, hand-labelled** — two sermons, one lesson, and
`2026-08-02.flac`. Roughly 40 blocks in total. The practical way to produce them
is to let the frontier control propose blocks and have a human correct the
boundaries and types, which takes minutes rather than hours.

| Measure | Definition |
| --- | --- |
| `type_accuracy` | Proportion of true blocks whose type is correct, weighted by duration. |
| `boundary_f1` | Block boundaries within 5 s of a true boundary. |
| `confusions` | Which types get mistaken for which. |

The confusion matrix is the point. "Prayer mistaken for sermon" and "communion
mistaken for announcements" have completely different consequences, and only one
of them breaks the output.

## What a good result looks like

The target from Q75 is that 80% of weeks need no boundary edit. Translating that
into this experiment:

- **Necessary**: `found` on 100% of the primary corpus. Never lose the sermon.
- **Target**: `no_edit@1s` on 80% of held-out recordings.
- **Stretch**: `no_edit@0.5s` on 80%.
- **Acceptable**: below those, provided failures land on `hard` cuts and are
  *flagged* — a hard cut the system admits to is a working system, per the spec.
