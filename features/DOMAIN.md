# Domain model

Written 2026-09-17, after the three concept-level passes. This is the second half
of "the spec", and the half that was missing: the feature files say what the
system *does*, and nothing said what it *holds*.

**Every field below is here because a scenario needs it.** Where a scenario
requires something this model cannot express, that is a defect in one of them —
the citation is given so it can be checked. Nothing is here speculatively, and
nothing is here because a framework would want it.

This is deliberately framework-agnostic. No table names, no ORM, no column
types beyond what the behaviour forces. The point is to be able to *choose* a
framework against a known shape.

---

## Entities at a glance

```
Recording ──1:N──▶ Block
    │                 │
    │                 │ seeds (teaching Blocks only)
    │                 ▼
    ├────1:N────▶ Segment ──1:1──▶ Proposal
    │                 │
    │                 └──1:N──▶ Artifact  (a render; a re-cut adds another)
    │
    ├────1:N────▶ Artifact       (transcript, waveform, preview, source FLAC)
    └────1:N────▶ Job

SpeakerProfile ──N:M──▶ Block   (a voice recognised in a span)
```

Five nouns the reviewer names, plus two the system needs: `Job` and
`SpeakerProfile`.

---

## Recording

One source audio file from the recorder. The unit of ingestion.

| Field | Why it exists |
| --- | --- |
| `object_key` | The join back to the object store. Reconciliation matches on it, and matches only keys never seen before — which is what made the `discovered` deadlock possible (`ingestion/recording_download.feature`). |
| `recording_id` | Derived from the key (`recording_20260913_090014`). Stable, and the only identifier that survives a re-download. |
| `started_at` | Parsed from the filename, not from file mtime. Load-bearing: the 10:50–10:57 wall-clock band is a confidence input, and grouping same-day recordings needs it (`analysis/block_classification.feature`). |
| `duration_seconds` | From the probe stage. |
| `size_bytes` | Needed before download to check free disk. |
| `channels`, `sample_rate`, `bits_per_raw_sample` | Reported on the detail view. **32-bit, not 24** — the spec said 24 in five places and was wrong. |
| `state` | One of eleven. See the lifecycle in `README.md`; every state's exits are tabulated there. |
| `kind` | `service`, `class`, `special_service`, `meeting`, `rehearsal`, `empty`, `unknown`. Descriptive only — it changes no processing. |
| `local_path` | Null until downloaded, and null again if local audio is reclaimed. The source in the object store is the durable copy. |
| `checksum` | The download must hash identically to the object (`recording_download.feature`). |
| `dynamic_range_db`, `active_fraction`, `longest_active_seconds` | The emptiness gate. Measured separation is three orders of magnitude — 3.6–6.6 dB for an empty room against 59–74 dB for anything publishable — so these are stored, not just thresholded and forgotten. |
| `waiting_since` | When a Recording has been stuck in `discovered` for want of disk. Required to retry oldest-first and to escalate after a day. |
| `skip_reason` | Why an object was not ingested at all, when that happens. Must be visible rather than silent (`s3_reconciliation.feature`). |

**Not stored:** any notion of "needs attention" as a field. It is derived from
state, Segment dispositions and confidence. Storing it means two sources of truth
for the one thing the reviewer looks at first.

---

## Block

A contiguous span attributed to one speaker doing one thing. Machine-produced,
never published alone.

| Field | Why it exists |
| --- | --- |
| `recording_id` | |
| `start_seconds`, `end_seconds` | Absolute against the source. Blocks are contiguous and cover `[0, duration]`. |
| `type` | The eleven-value closed set in `README.md`. |
| `classification_confidence` | `high` / `medium` / `low`, **derived** — see `analysis/analysis_confidence.feature`. Never a model's self-report. |
| `self_reported_confidence` | Stored for diagnosis, never shown, never thresholded. It is a constant at 0.95 and the spec says so explicitly. |
| `evidence` | Human-readable, with a timecode. The reviewer sees this instead of a score. |
| `summary` | One line, so a Block can be judged without listening. |
| `cue_start_seconds`, `cue_end_seconds` | The excerpt the Preview button plays. |
| `retyped_by_human` | A reviewer can retype a Block, which re-runs Segment proposal. Must be distinguishable from a machine type, or the next re-analysis silently reverts the correction. |

**Ordering matters and is not incidental.** Consecutive Blocks of one type are
one Block for seeding purposes. Storing them separately is fine; seeding over
runs rather than rows is required (the 2026-09-13 bug).

---

## Segment

A publishable or archivable span. The unit of work — what a reviewer approves
and what renders.

| Field | Why it exists |
| --- | --- |
| `recording_id` | |
| `seed_block_id` | Which teaching Block it grew from. Null only for a `meeting` Segment, which a human creates by archiving a whole Recording. |
| `classification` | `sermon`, `lesson`, `seminar`, or `meeting`. **Not the Block vocabulary.** |
| `punch_in_seconds`, `punch_out_seconds` | The current boundaries, machine or human. |
| `proposed_punch_in`, `proposed_punch_out` | The machine's original. Required: the reviewer can revert to the proposal after adjusting (`interface/punch_point_adjustment.feature`), which is impossible if adjustment overwrites. |
| `state` | `proposed`, `approved`, `skipped`, `processing`, `processing_failed`, `complete`, `recut`. |
| `intent` | `publish` or `archive`. Always confirmed by a human, never assumed. |
| `disposition_at` | When it was approved or skipped. A skipped Segment must be findable years later. |
| `boundary_source` | `model`, `refined`, `model-in/refined-out`, or `human`. Already produced by the pipeline and worth keeping: it is how a regression gets attributed. |
| `leading_silence_seconds` | Checked against the 1.0 s cap. Computable on any proposal without ground truth, which is what makes it the one hard boundary rule. |

---

## Proposal

Why the machine thinks what it thinks. One per Segment, replaced when analysis
re-runs.

| Field | Why it exists |
| --- | --- |
| `segment_id` | |
| `classification_confidence`, `boundary_confidence` | Separate, because a Segment can be confidently a sermon with badly guessed boundaries. Both derived. |
| `evidence[]` | Each entry: `timecode`, `finding`, `implies`. Rendered as a table for the reviewer. |
| `punch_in_difficulty`, `punch_out_difficulty` | `easy` / `moderate` / `hard`, from the quiet around the cut. **Graded from the ground truth where it exists, never by the configuration being measured** — otherwise the headline can be raised by grading more cuts hard. |
| `agreement_gap_seconds` | Distance to a second analysis's punch-in, if one ran. Null when no second opinion is configured, and the absence must be stated rather than shown as agreement. |
| `missing_evidence[]` | What was unavailable. Lowers confidence rather than blocking the Proposal. |

---

## Artifact

Any output file derived from a Recording. Nothing is pruned on a schedule; a
two-year-old Recording still has all of these.

| Field | Why it exists |
| --- | --- |
| `recording_id`, `segment_id` | Segment-scoped for a render, Recording-scoped for the rest. |
| `kind` | `source_flac`, `rendered_mp3`, `transcript`, `waveform_peaks`, `preview`, `diarization`. |
| `path`, `size_bytes`, `checksum` | |
| `render_settings` | Loudness target, true peak, LAME quality, the tail applied. Required so a previous render can be reproduced (`storage_and_retention.feature`) and so a re-render is comparable. |
| `superseded_by` | A re-cut produces a new MP3; the old one survives until the new one succeeds. That is what makes `recut` a distinct state. |
| `asr_config` | Which engine and settings produced a transcript. **Newly load-bearing**: production must run a non-mlx engine, and a transcript's provenance decides whether a stored boundary is comparable. |

---

## Job

| Field | Why it exists |
| --- | --- |
| `recording_id`, `segment_id` | |
| `kind` | `download`, `analyze`, `render`. |
| `state` | `queued`, `running`, `succeeded`, `failed`, `cancelled`. |
| `attempts`, `max_attempts` | Retries with backoff; stops and reports rather than looping. |
| `dedupe_key` | Enqueuing analysis twice for one Recording must run it once. |
| `last_error`, `failed_permanently` | A non-decodable file must not consume the whole retry budget. |
| `queued_at`, `started_at` | The health view shows how long the oldest queued job has waited. |

**Stages within analysis are cached individually**, keyed on the Recording and
the stage's own inputs, so a failure late in the pipeline does not re-transcribe
three hours of audio. That caching is not a Job; it is Artifact reuse.

---

## SpeakerProfile

| Field | Why it exists |
| --- | --- |
| `name` | Shown before publishing, which is the only defence against publishing a guest who asked not to be. |
| `embedding` | Enrolled from already-published sermons — no separate enrolment session. |
| `enrolled_from[]` | Which Recordings contributed. Needed to un-enrol. |
| `confirmed_by_human` | An unrecognised voice requires confirmation before publishing, and confirming enrols. A profile built by confirmation is not the same as one guessed. |

**This entity is the one place the system stores something about a person.** It
exists deliberately and narrowly, and it reopens "nothing more is collected" —
flagged as an open decision, not settled here.

---

## What this model deliberately does not decide

- **Storage engine.** Nothing above needs more than rows and a blob store.
  Whether that is Postgres, SQLite or files is a framework question, and the
  point of writing this first was to be able to answer it on evidence.
- **Whether a second analysis runs.** `agreement_gap_seconds` is nullable
  because that decision is open (`analysis/analysis_confidence.feature`).
- **Whether local audio is ever reclaimed.** `local_path` is nullable and the
  object store is durable, so both answers fit. Q34 is open.
- **Hard delete.** The last `@needs-decision` in the spec.
