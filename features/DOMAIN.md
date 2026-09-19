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
    ├────1:N────▶ Segment ──1:N──▶ Proposal  (a re-run adds another; the old one stays)
    │                 │
    │                 └──1:N──▶ Artifact  (a render; a re-cut adds another)
    │
    ├────1:N────▶ Artifact       (envelope, transcript, waveform, preview, source FLAC)
    ├────1:N────▶ Job
    ├────1:N────▶ Notification   (naming its Segment too, when it concerns one)
    └────1:N────▶ LogEntry       (the processing log, one entry per thing that happened)

SpeakerProfile ──N:M──▶ Block   (a voice recognised in a span, and how strongly)
```

Five nouns the reviewer names, plus four the system needs: `Job`,
`Notification`, `LogEntry` and `SpeakerProfile`.

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
| `state` | One of ten. See the lifecycle in `README.md`; every state's exits are tabulated there. |
| `kind` | `service`, `class`, `special_service`, `meeting`, `rehearsal`, `empty`, `unknown`. Descriptive only — it changes no processing. |
| `channel_levels[]` | Each entry: `channel` and `rms_db`. "The Recording records a per-channel RMS level" — channel 1 at −21.3 dB against channel 2 at the −90.4 dB noise floor is what identifies the dead channel, and both are needed to tell that case from two channels carrying signal (`analysis/audio_probe.feature`). |
| `mono_source` | Which channel or mix the render must take: "the Recording records that the render should use channel 1 only" (`analysis/audio_probe.feature`). Deliberately not a closed set — the scenarios name that one value and declare no vocabulary for the reviewer's answer when both channels carry signal. |
| `mono_source_confirmed` | A Recording flagged "unexpected stereo content" does not render until a human answers how to mix it (`processing/audio_rendering.feature`), and that answer has to outlive a re-probe which would otherwise recompute `mono_source` over it. Null until the question is asked, written the way `Segment.distribution_confirmed` is. |
| `local_path` | Null until downloaded, and null again if local audio is reclaimed. The source in the object store is the durable copy. |
| `checksum` | The download must hash identically to the object (`recording_download.feature`). |
| `integrated_loudness_lufs`, `true_peak_dbtp`, `loudness_range_lu` | What the probe measured of the source, and the input the render normalizes from in one pass (`analysis/audio_probe.feature`, `processing/audio_rendering.feature`). `dynamic_range_db` is the emptiness metric on another scale, and `Artifact.render_settings` is the render's target rather than the measurement. |
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
| `speaker_matches[]` | Each entry: `speaker_profile_id` and `similarity`. The reviewer is told which enrolled voice is teaching **and how confidently** (`interface/segment_review.feature`), which a bare link to a profile cannot carry. Named `similarity` rather than a confidence because it is the measured quantity — 0.92–0.95 on the preacher's teaching Block against 0.16–0.48 on music and announcements (`analysis/speaker_diarization.feature`) — and confidence in this model is always a derived level. Ordered, because the ranking is the signal and the runner-up is reliably communion. |

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
| `span_start_seconds`, `span_end_seconds` | The Segment's own outer bounds, which the punch points sit inside: a reviewer extends the start and "the Segment's span grows" while the punch-in stays where it was (`interface/punch_point_adjustment.feature`), and the detail view lists a span and a pair of boundaries per Segment (`interface/recording_detail.feature`). Not derivable from `seed_block_id`: extending would rewrite a machine-produced Block, and a `meeting` or hand-drawn Segment has no seed Block. |
| `punch_in_seconds`, `punch_out_seconds` | The current boundaries, machine or human. The machine's original is not a second pair here: the reviewer can revert to the proposal after adjusting (`interface/punch_point_adjustment.feature`) by reading the cuts the `LogEntry` naming that Proposal carries. |
| `state` | `proposed`, `approved`, `skipped`, `processing`, `processing_failed`, `complete`, `recut`. |
| `intent` | `publish` or `archive`. Always confirmed by a human, never assumed. |
| `disposition_at` | When it was approved or skipped. A skipped Segment must be findable years later. |
| `distribution_confirmed` | A Segment whose teaching voice matches no enrolled profile is confirmed as distributable before it is published, and the confirmation is recorded with the approval (`interface/segment_review.feature`). Null until the question is asked, so a confirmation nobody was asked for stays distinguishable from one that was declined. |
| `boundary_source` | `model`, `refined`, `model-in/refined-out`, or `human`. Where the current boundaries came from: "every Segment records whether its boundaries were proposed or refined" (`analysis/segment_proposal.feature`). Already produced by the pipeline. |
| `summary` | Its own one line, shown beside it in review and again in the notification (`analysis/summarization.feature`). `Notification.summary` is composed delivery text, and the Block summaries beneath a Segment do not compose into one. Null until summarization runs. |
| `leading_silence_seconds` | Checked against the 1.0 s cap. Computable on any proposal without ground truth, which is what makes it the one hard boundary rule. |
| `publication_date` | Half of the name every finished file carries, `YYYY-MM-DD - Label` (`interface/publication_details.feature`). Prefilled from the Recording's start and changeable from there. Null until entered: it is required to publish, and a Segment is proposed long before it is published. |
| `label` | The other half, and the only part a human writes. Null until entered, and null for good on an `archive` Segment, which is named from the date alone. |

**A span is not a second name for the punch points.** They coincide when a
Segment is first made — a merge produces one "spanning from the first punch-in to
the last punch-out" (`analysis/segment_proposal.feature`) — and they part as soon
as a reviewer extends the span or moves a boundary inside it.

**Neither rejection is a property of the row.** "The boundary must fall within
the Segment" compares two of a Segment's own values and is the kind of sanity
constraint the store still owes everything else it holds; "rejected if it would
overlap the neighbouring Segment" compares two Segments, so it can only belong to
the adjustment behaviour, next to the message the reviewer is shown.

---

## Proposal

Why the machine thinks what it thinks. Several per Segment: a re-run adds one
and supersedes the one before it rather than overwriting it.

| Field | Why it exists |
| --- | --- |
| `segment_id` | |
| `classification_confidence`, `boundary_confidence` | Separate, because a Segment can be confidently a sermon with badly guessed boundaries. Both derived. |
| `evidence[]` | Each entry: `timecode`, `finding`, `implies`. Rendered as a table for the reviewer. |
| `punch_in_difficulty`, `punch_out_difficulty` | `easy` / `moderate` / `hard`, from the quiet around the cut. **Graded from the ground truth where it exists, never by the configuration being measured** — otherwise the headline can be raised by grading more cuts hard. |
| `agreement_gap_seconds` | Distance to a second analysis's punch-in, if one ran. Null when no second opinion is configured, and the absence must be stated rather than shown as agreement. |
| `missing_evidence[]` | What was unavailable. Lowers confidence rather than blocking the Proposal. |
| `punch_in_candidates[]` | Each entry: `timecode` and `considered_because`. "Analysis recorded an alternative punch-in candidate" whose evidence panel "shows why that candidate was considered" (`interface/punch_point_adjustment.feature`) — a bare timecode cannot. Ordered by rank. |
| `superseded_by` | Re-running Analysis keeps the previous Proposals in the Recording's history, and where a reviewer has already edited a Segment the fresh machine proposal is shown *alongside* their work rather than over it (`analysis/analysis_orchestration.feature`, `interface/punch_point_adjustment.feature`). Two Proposals for one Segment therefore have to exist at once, which a 1:1 cannot do, and which of them is current has to be a stored fact. Written the way `Artifact.superseded_by` already is. |

**A candidate is not an `evidence[]` entry**, though it borrows the shape: most
evidence is not a boundary, and `implies` has nothing to say about a candidate.
Only punch-in has one, because only punch-in has a scenario.

**Its cuts are not here.** A `LogEntry` naming this Proposal carries them, so the
machine's boundary sets and the reviewer's sit in one ordered history instead of
two (`processing/reprocessing.feature`). Nor are they copied onto the Segment:
reverting reads the entries naming the Proposal that is not yet superseded, which
is one query rather than a second copy of the cuts that can drift from the
history and that nothing would detect had drifted.

---

## Artifact

Any output file derived from a Recording. Nothing is pruned on a schedule; a
two-year-old Recording still has all of these.

| Field | Why it exists |
| --- | --- |
| `recording_id`, `segment_id` | Segment-scoped for a render, Recording-scoped for the rest. |
| `kind` | `source_flac`, `envelope`, `rendered_mp3`, `transcript`, `waveform_peaks`, `preview`, `diarization`. The envelope is the first stage's output and every later stage reads it, so keeping it is what lets a resumed run leave the cached stages alone and a false trigger cost no GPU time (`analysis/analysis_orchestration.feature`, `analysis/audio_probe.feature`). |
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

## Notification

A record that something happened which a reviewer should know about. It exists
whether or not any channel is configured, and delivering it is a separate act
from raising it (`notifications/approval_notifications.feature`).

| Field | Why it exists |
| --- | --- |
| `recording_id`, `segment_id` | The subject — "the Recording or Segment it concerns". Written the way `Artifact` writes it, Segment-scoped when the notification links to a Segment and Recording-scoped otherwise, rather than as one polymorphic reference: every Segment has a Recording, and "which Sunday was I never told about?" is the question this record exists to answer. |
| `kind` | Why it was raised. Deliberately not a closed set — the scenarios raise notifications for many different reasons and declare a vocabulary for none of them, so naming one here would be inventing spec rather than recording it. |
| `recipient` | Who it is for. There is one reviewer and no accounts (`interface/authentication.feature`), so this is the same actor seam every human action is recorded against, not a reference to a person the system stores. |
| `summary` | What it says, in plain text. It states the recording date and the proposed length, and names each session when a Recording held more than one — so it is composed when the Notification is raised, not when a channel renders it. |
| `created_at` | When it was raised. The reminder for a Segment left undispositioned for 3 days is measured from it. |
| `state` | `pending`, `delivered`, `failed` or `suppressed`. A Recording that produced nothing publishable is recorded as `suppressed` rather than not recorded at all, which is what makes "why was I not told about that Sunday?" answerable without reading logs. |

**Not stored:** delivery attempts, per-channel results, retry counts. The channel
is undecided, the same Notification may be delivered by more than one of them,
and no scenario gives those fields — so a retry belongs to the delivery
behaviour rather than to this record. Nor the grouping that batches several into
one delivered message: three Recordings finishing within five minutes reach the
reviewer once (`approval_notifications.feature`), and each still raises its own
record, so `recipient`, `created_at` and `state` are what a batching delivery
reads. Nor does a reviewer's opting out live here: that is a property of the
reviewer, and nothing yet models one.

---

## LogEntry

One thing that happened to a Recording, in the order it happened. This is one
entity rather than three because `interface/recording_detail.feature` renders
state transitions, job attempts and human actions as a single list in time
order, and three tables cannot be ordered by one query.

| Field | Why it exists |
| --- | --- |
| `recording_id` | Whose log it is: "I open **its** processing log" (`operations/system_health.feature`). |
| `segment_id` | "Who performed each human action, **against which Segment**". Null for an entry about the whole Recording, written the way `Artifact` and `Notification` write it. |
| `job_id` | Which job an attempt was of, so the entry does not repeat what `Job.kind` already says. |
| `proposal_id` | Which Proposal the machine's cuts belonged to. Without it a superseded Proposal keeps its reasoning and not its cuts, and re-running Analysis "keeps the previous Proposals in the Recording's history". |
| `artifact_id` | Which render a set of boundaries produced. "Any past render could be reproduced from that record and the source" needs the cuts paired to the render's settings, not two lists assumed to be in step. |
| `kind` | What happened. Deliberately not a closed set: the scenarios log transitions, attempts, approvals, adjustments and reverts and declare a vocabulary for none of them — `Notification.kind` is open for the same reason. |
| `occurred_at` | "Each state transition **with its timestamp**". The log's order, so entries are ordered on it rather than on the identity, which only breaks a tie. An instant, not a local reading: two entries written in different offsets still order against each other, so a moment without one is refused rather than stored. |
| `correlation_id` | "I can correlate an entry to the application logs". Required on every entry: an identifier that may be absent is the same as no identifier. |
| `actor` | "Who performed each human action". Null on a machine entry, which is what tells the two apart. The same actor seam `Notification.recipient` names — there are no accounts (`interface/authentication.feature`). |
| `entered_state` | "Each state transition with its timestamp". One of the Recording's ten states or the Segment's seven; the two sets are disjoint, so one column holds either and `segment_id` says whose. |
| `duration_seconds`, `error` | "Every job attempt with its timestamp, duration and error". `error` is null on an attempt that succeeded. |
| `punch_in_seconds`, `punch_out_seconds` | "Each set of boundaries with who approved them and when" (`processing/reprocessing.feature`), a discarded adjustment included. Read with `actor` and `occurred_at`, which are what make it a set of boundaries *with* an approver. |
| `boundary_source` | Which path produced *this* set — "and that is visible in the processing log" (`analysis/segment_proposal.feature`). The same four values `Segment.boundary_source` takes, recorded per set because the Segment holds only the current one, and attributing a regression to a path means reading the cuts that came from it. |

**Not stored:** `from_state`. The state a transition left is the previous entry's
`entered_state` for the same subject, and every transition is logged, so storing
it would be a second source of truth. Nor the attempt ordinal, which is the
position of that job's attempt entries. `Job.attempts` stays, because the retry
budget is read before the attempt it authorises is logged.

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
