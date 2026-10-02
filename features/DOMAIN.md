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
    ├────1:N────▶ Notification   (its Segment too, or neither when the system is the subject)
    ├────1:N────▶ LogEntry       (the processing log, one entry per thing that happened)
    └────1:N────▶ CorpusPair     (a source paired with one published edit)

SpeakerProfile ──N:M──▶ Block   (a voice recognised in a span, and how strongly)
SpeakerProfile ──1:N──▶ Segment (the voice a human confirmed was preaching)
SpeakerProfile ──N:M──▶ Segment (the Segments that enrolled the voice)

SkippedObject                   (an object the reconciliation scan did not ingest)
Discovery                       (a webhook received or a scan run, and what it found)
Reviewer                        (the actor seam; whether they receive notifications)
```

Five nouns the reviewer names, plus eight the system needs: `Job`,
`Notification`, `LogEntry`, `SpeakerProfile`, `SkippedObject`, `Discovery`,
`CorpusPair` and `Reviewer`.

---

## Recording

One source audio file from the recorder. The unit of ingestion.

| Field | Why it exists |
| --- | --- |
| `object_key` | The join back to the object store. Reconciliation matches on it, and matches only keys never seen before — which is what made the `discovered` deadlock possible (`ingestion/recording_download.feature`). |
| `recording_id` | Derived from the key (`recording_20260913_090014`). Stable, and the only identifier that survives a re-download. |
| `started_at` | Parsed from the filename wherever the key gives one, with `started_at_source` saying when it could not. Load-bearing: the 10:50–10:57 wall-clock band is a confidence input, and grouping same-day recordings needs it (`analysis/block_classification.feature`). |
| `started_at_source` | `key` or `last_modified`. The key is the primary path and always present; the fallback is an upload time, so a Recording cannot be scored on the 10:50–10:57 band without knowing which it was (`ingestion/recording_download.feature`). The sidecar's `recorded_at` and the webhook's are not a third and fourth value: each carries the recorded time the key already gives, and "the key is the source of truth and a sidecar … is an enrichment" settles a disagreement in the key's favour (`ingestion/recording_download.feature`, `ingestion/webhook_notification.feature`). Only the upload-time fallback changes what the band may be scored against, which is the one distinction this field draws. Never null; an unrecorded provenance is the same hole. |
| `duration_seconds` | From the probe stage. |
| `size_bytes` | Needed before download to check free disk. |
| `capture_device` | Which recorder produced it, shown as `Device` on the detail view (`interface/recording_detail.feature`). The host's identity rather than the ALSA device string the sidecar carries, and nullable because the recorder has no host field to send yet (`ingestion/webhook_notification.feature`). |
| `channels`, `sample_rate`, `bits_per_raw_sample` | Reported on the detail view. **32-bit, not 24** — the spec said 24 in five places and was wrong. |
| `channel_levels[]` | Each entry: `channel` and `rms_db`. "The Recording records a per-channel RMS level" — channel 1 at −21.3 dB against channel 2 at the −90.4 dB noise floor is what identifies the dead channel, and both are needed to tell that case from two channels carrying signal (`analysis/audio_probe.feature`). |
| `mono_source` | Which channel or mix the render must take: "the Recording records that the render should use channel 1 only" (`analysis/audio_probe.feature`). Deliberately not a closed set — the scenarios name that one value and declare no vocabulary for the reviewer's answer when both channels carry signal. |
| `mono_source_confirmed` | A Recording flagged "unexpected stereo content" does not render until a human answers how to mix it (`processing/audio_rendering.feature`), and that answer has to outlive a re-probe which would otherwise recompute `mono_source` over it. Null until the question is asked, written the way `Segment.distribution_confirmed` is. |
| `state` | One of ten. See the lifecycle in `README.md`; every state's exits are tabulated there. |
| `kind` | `service`, `class`, `special_service`, `meeting`, `rehearsal`, `empty`, `unknown`. Descriptive only — it changes no processing. |
| `local_path` | Null until downloaded, and null again if local audio is reclaimed. The source in the object store is the durable copy. |
| `checksum` | The download must hash identically to the object (`recording_download.feature`). |
| `sidecar_present` | "The missing sidecar is noted on the Recording" (`ingestion/recording_download.feature`), which `started_at_source` does not say — the key supplies the start time whether a sidecar exists or not. Null until the download looks, and not a warning, because no object in the bucket has one. |
| `integrated_loudness_lufs`, `true_peak_dbtp`, `loudness_range_lu` | What the probe measured of the source, and the input the render normalizes from in one pass (`analysis/audio_probe.feature`, `processing/audio_rendering.feature`). `dynamic_range_db` is the emptiness metric on another scale, and `Artifact.render_settings` is the render's target rather than the measurement — what the render achieved is on the Artifact beside it. |
| `dynamic_range_db`, `active_fraction`, `longest_active_seconds` | The emptiness gate. Measured separation is three orders of magnitude — 3.6–6.6 dB for an empty room against 59–74 dB for anything publishable — so these are stored, not just thresholded and forgotten. |
| `waiting_since` | When a Recording has been stuck in `discovered` for want of disk. Required to retry oldest-first and to escalate after a day. |
| `warnings[]` | `damaged container`, `source clipping detected`, `sidecar disagrees with the audio`, `unexpected stereo content`, `unexpected language`, `low transcript quality`, `source no longer available`. Seven, several at once and none of them a state (`analysis/audio_probe.feature`, `analysis/transcription.feature`, `operations/storage_and_retention.feature`). |
| `skip_reason` | **Fate open; `sp-8eh` owns it.** Nothing skips a *Recording* — all four skip reasons are `SkippedObject`'s. The flag half of the two characters four scenarios gave this field is now `warnings[]`'s, leaving the failure reason (`ingestion/recording_download.feature`, `interface/recording_detail.feature`) for the bead owning it to settle. |

**A warning is a named value, not a column each.** The probe raises its own and
transcription later raises another on the same Recording, so the set has to hold
several and each new condition must not be a new column. It is closed rather than
open because later behaviour reads the names — the render refuses to run on
`unexpected stereo content` (`processing/audio_rendering.feature`) and the detail
view explains `source clipping detected` specifically
(`interface/recording_detail.feature`) — so a typo would silently disable a gate.
`Notification.kind` and `LogEntry.kind` stay open because nothing branches on
them. `sidecar disagrees with the audio` is the one value the Gherkin describes
without quoting, and takes the wording of its scenario's title. It is a set, so
one warning cannot be raised twice on one Recording; `channel_levels[]` and
`speaker_matches[]` are ordered lists of measurements and are not deduplicated.

**Four more of the conditions a scenario flags on a Recording are derivable, and
are not stored.** `no substantive content` and `no audio content` are what
`dynamic_range_db` and `active_fraction` already say, and `suspiciously short` and
`suspiciously long` are `duration_seconds` against the observed 37–203 minute
range (`analysis/audio_probe.feature`).

**A warning is not a state, and the Segment side of one is a query.** Nothing
about `source no longer available` moves the Recording — its scenario names no
transition and leaves the Recording's skipped Segments skipped, so a `reviewed`
Recording is inferred to stay `reviewed` — and "its skipped Segments are marked as
no longer extractable" (`operations/storage_and_retention.feature`) is the skipped
Segments of a Recording carrying that warning. A second field on every Segment
would have to be maintained on each one and could disagree with the Recording.

**The probed codec is not stored.** `analysis/audio_probe.feature` lists it among
the probe's outputs and the detail view's `Format` line reads it, but it is `flac`
on all 85 objects in the bucket, the key's extension already carries it, and
`Artifact.kind` names the retained source `source_flac`. A second copy of the
container's own name could only ever disagree with the file.

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
| `possibly_multiple_types` | A Block running a scripture reading into teaching is flagged as possibly more than one type, and the split affordance keys on that assertion rather than on `evidence[]` free text (`analysis/block_classification.feature`). A boolean, held the way `retyped_by_human` is: one condition, quoted as no string. |
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
| `seed_block_id` | Which teaching Block it grew from. Null for a `meeting` or hand-drawn Segment: a human creates a `meeting` Segment by archiving a whole Recording, and a reviewer draws a Segment by hand. |
| `classification` | `sermon`, `lesson`, `seminar`, or `meeting`. **Not the Block vocabulary.** |
| `span_start_seconds`, `span_end_seconds` | The Segment's own outer bounds, which the punch points sit inside: a reviewer extends the start, "the Segment's span grows", and the punch-in may sit anywhere in the new span (`interface/punch_point_adjustment.feature`), and the detail view lists a span and a pair of boundaries per Segment (`interface/recording_detail.feature`). Not derivable from `seed_block_id`: extending would rewrite a machine-produced Block, and a `meeting` or hand-drawn Segment has no seed Block. |
| `punch_in_seconds`, `punch_out_seconds` | The current boundaries, machine or human. The machine's original is not a second pair here: the reviewer can revert to the proposal after adjusting (`interface/punch_point_adjustment.feature`) by reading the cuts the `LogEntry` naming that Proposal carries. |
| `state` | `proposed`, `approved`, `skipped`, `processing`, `processing_failed`, `complete`, `recut`. |
| `intent` | `publish` or `archive`. Always confirmed by a human, never assumed. |
| `disposition_at` | When it was approved or skipped. A skipped Segment must be findable years later. |
| `distribution_confirmed` | A Segment whose teaching voice matches no enrolled profile is confirmed as distributable before it is published, and the confirmation is recorded with the approval (`interface/segment_review.feature`). Null until the question is asked, so a confirmation nobody was asked for stays distinguishable from one that was declined. |
| `confirmed_speaker_profile_id` | Who a human said was preaching, confirming the machine's match or correcting it (`interface/segment_review.feature`). Only `similarity` on the seeding Block is stored otherwise, so without this the next re-analysis reverts the correction — the failure `Block.retyped_by_human` exists to prevent — and the confirmation that enrols the voice has nothing to enrol from. `distribution_confirmed` is the consent half of the same rule; this is the identity half. |
| `boundary_source` | `model`, `refined`, `model-in/refined-out`, or `human`. Where the current boundaries came from: "every Segment records whether its boundaries were proposed or refined" (`analysis/segment_proposal.feature`). Already produced by the pipeline. |
| `summary` | Its own one line, shown beside it in review and again in the notification (`analysis/summarization.feature`). `Notification.summary` is composed delivery text, and the Block summaries beneath a Segment do not compose into one. Null until summarization runs. |
| `leading_silence_seconds` | Checked against the 1.0 s cap. Computable on any proposal without ground truth, which is what makes it the one hard boundary rule. |
| `warnings[]` | `check the opening`, `no clean cut point found at punch-in`, `no clean cut point found at punch-out`, `boundary is not acceptable`, `source was very quiet`. Five named conditions, held the way `Recording.warnings[]` is and for the same reasons (`analysis/punch_in_detection.feature`, `analysis/punch_out_detection.feature`, `analysis/segment_proposal.feature`, `processing/audio_rendering.feature`). |
| `publication_date` | Half of the name every finished file carries, `YYYY-MM-DD - Label` (`interface/publication_details.feature`). "The date defaults from the recording" and "I can change it", so the default is placed at approval from the Recording's start wherever the reviewer entered none, and a published Segment is never in no period. Null while a Segment is still proposed, which is most of its life: it is proposed long before it is published (reasoning, not quoted). |
| `label` | The other half. Summarization suggests it from the summary; the reviewer can correct it. Null until entered, and null for good on an `archive` Segment, which is named from the date alone. |

**Four of the conditions a scenario flags on a Segment are derivable, and are not
stored.** `length outside expected range` is the distance between the boundaries,
`recording may have started late` and `stopped early` are a boundary at 0 or at
the Recording's duration, and "the source was clipped"
(`processing/audio_rendering.feature`) is `source clipping detected` on the
Segment's Recording. The Proposal's `hard` difficulty is **not** among them: it
also grades noise near the cut and music under the first words, so a cut that did
have its 250 ms of quiet can be `hard`, and all `hard` derives is the unquoted
flag that the cut needs a human. `no clean cut point found at punch-in` and its
punch-out twin are raised by that one missing margin and by nothing else, which
is the reason a reviewer is shown. The other three stored values are a false
start, an invariant that could not be satisfied, and a source quiet enough to
need saying. `boundary is not acceptable` is the one value the Gherkin describes
without quoting.

**A span is not a second name for the punch points.** A proposed Segment's span
is detected and normally wider than its cuts (`interface/recording_detail.feature`).
A merge and a hand-drawn Segment start coincident — one "spanning from the first
punch-in to the last punch-out" (`analysis/segment_proposal.feature`) — and part
as soon as a reviewer extends the span or moves a boundary inside it.

**Neither rejection is stored as a constraint.** "The boundary must fall within
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
| `punch_in_grade`, `punch_out_grade` | `easy` / `moderate` / `hard`, from the quiet around the cut the machine proposed. The grade is shown to the reviewer (`analysis/punch_in_detection.feature`, `analysis/punch_out_detection.feature`). |
| `agreement_gap_seconds` | Distance to a second analysis's punch-in. Null in v1 because one analysis is the whole design; a second opinion is deferred, not open. The absence must be stated rather than shown as agreement. |
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
| `render_settings` | Loudness target, true peak, LAME quality, the tail applied, and which source channel was taken. Required so a previous render can be reproduced (`storage_and_retention.feature`) and so a re-render is comparable. |
| `input_loudness_lufs`, `output_loudness_lufs`, `output_true_peak_dbtp` | "the measured input and output loudness are recorded on the Segment" (`processing/audio_rendering.feature`). Separate from `render_settings`, which holds what the render asked for: the request and the achievement are different numbers, and the difference is the only thing that shows an off-target render after the fact. The true peak is here for the same reason — its ceiling is the one target nobody can hear. |
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
| `recording_id`, `segment_id` | The subject — "the Recording or Segment it concerns", and neither when it is the system itself. Written the way `Artifact` writes it, Segment-scoped when the notification links to a Segment and Recording-scoped otherwise, rather than as one polymorphic reference: every Segment has a Recording, and "which Sunday was I never told about?" is the question this record exists to answer. |
| `kind` | Why it was raised. Deliberately not a closed set — the scenarios raise notifications for many different reasons and declare a vocabulary for none of them, so naming one here would be inventing spec rather than recording it. |
| `recipient` | Who it is for. There is one reviewer and no accounts (`interface/authentication.feature`), so this is the same actor seam every human action is recorded against, not a reference to a person the system stores. `Reviewer` is identified by this string and looked up on it at send time; it is not a foreign key. |
| `summary` | What it says, in plain text. It states the recording date and the proposed length, and names each session when a Recording held more than one — so it is composed when the Notification is raised, not when a channel renders it. |
| `created_at` | When it was raised. The reminder for a Segment left undispositioned for 3 days is measured from it. |
| `state` | `pending`, `delivered`, `failed` or `suppressed`. A Recording that produced nothing publishable is recorded as `suppressed` rather than not recorded at all, which is what makes "why was I not told about that Sunday?" answerable without reading logs. |

**A system-scoped alert names neither.** Scratch space exhausted and the array at
90% raise an alert about the system, with no Recording to hang it on
(`operations/storage_and_retention.feature`). Raising a record and delivering it
are already separate here, and every other field applies unchanged, so the
subject is nullable rather than there being a second entity that repeats all six.
A notification naming a Segment must name that Segment's Recording, and the table
refuses one that does not: a nullable subject otherwise rests on every caller
remembering, and the one that forgets is both missing from "which Sunday was I
never told about?" and sitting in the system-alert bucket pretending to be an
alert. Naming neither stays unconstrained, because that *is* the system alert and
`kind` is open — nothing in the row tells an alert from an omission.

**Not stored:** delivery attempts, per-channel results, retry counts. The channel
is undecided, the same Notification may be delivered by more than one of them,
and no scenario gives those fields — so a retry belongs to the delivery
behaviour rather than to this record. Nor the grouping that batches several into
one delivered message: three Recordings finishing within five minutes reach the
reviewer once (`approval_notifications.feature`), and each still raises its own
record, so `recipient`, `created_at` and `state` are what a batching delivery
reads. Nor does a reviewer's opting out live here: that is
`Reviewer.receives_notifications`, honoured when a Notification is sent rather
than when it is created.

---

## Reviewer

The actor the system notifies. There is one, and there are no accounts
(`interface/authentication.feature`). The identity is the actor seam, not a
generated key: adding real accounts changes who that actor is and does not
change what is recorded against it. It is not a person the system stores —
`SpeakerProfile` remains the one place that does.

| Field | Why it exists |
| --- | --- |
| `actor` | The seam `Notification.recipient` and `LogEntry.actor` name. `"reviewer"` until there are accounts. Identity, so a Notification does not hold a foreign key to a person the system stores. |
| `receives_notifications` | "a reviewer is configured to receive notifications" and "When a reviewer disables notifications" (`notifications/approval_notifications.feature`). Honouring it is send-time behaviour: opting out does not stop a Notification being created, and recordings still appear in the list. |

**Opting out is not a Notification state.** `suppressed` is "nothing publishable";
a reviewer who has turned notifications off still has records created, they are
just not sent.

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
| `actor` | "Who performed each human action". Null on a machine entry, which is what tells the two apart. The same actor seam `Notification.recipient` and `Reviewer.actor` name — there are no accounts (`interface/authentication.feature`). |
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
| `enrolled_from[]` | Which Segments contributed. Needed to un-enrol. |
| `confirmed_by_human` | An unrecognised voice requires confirmation before publishing, and confirming enrols. A profile built by confirmation is not the same as one guessed. Which Segment's voice a human attested to is `Segment.confirmed_speaker_profile_id`. |

**This entity is the one place the system stores something about a person.** It
exists deliberately and narrowly, and it reopens "nothing more is collected" —
flagged as an open decision, not settled here.

---

## SkippedObject

An object the reconciliation scan decided not to ingest. Not a Recording state:
`recording_id` is derived from the key and `started_at` parsed out of it, so
three of the four reasons leave nothing a Recording could be built from.

| Field | Why it exists |
| --- | --- |
| `object_key` | What was skipped, and the identity. An operator sees every object ever skipped, which is a list of objects rather than one of scans, so a later scan corrects the record instead of adding one. |
| `reason` | `recorder clock not set`, `key does not match the pattern`, `not an audio object`, `before the ingest cutoff` — the four the outline names (`ingestion/s3_reconciliation.feature`). |

**A manually ingested object keeps its row.** `before the ingest cutoff` is the
one reason a Recording can still be made from the key, on demand, which is how the
accuracy corpus is loaded (`s3_reconciliation.feature`). Nothing clears the row,
and that is accepted: the list answers what the *scan* dropped, no scenario reads
it to decide anything, and the operator reading it is the one who forced the
ingestion.

**Not stored:** when it was skipped, or which scan skipped it. "Nothing is
dropped without being counted" asks what was dropped and why; no scenario reads
a time off this record, and no alert is raised from it.

---

## Discovery

One occasion on which the Processor learned what the bucket holds — a webhook it
was sent, or a scan it ran. One entity rather than two because the health view
renders them as one thing: when the last of each happened, and how many
recordings each discovered (`operations/system_health.feature`).

| Field | Why it exists |
| --- | --- |
| `kind` | `webhook` or `scan`. Which of the two the health view is showing the last of, and the reason one record serves both. |
| `occurred_at` | "When the last webhook was received" and "when the last reconciliation scan ran". An instant, so records written in different offsets still order against each other. |
| `discovered_count` | "How many recordings each discovered". Nothing on a Recording names its discoverer and a re-scan finds nothing new, so the count cannot be derived back. |
| `failure` | `transient` or `credentials`, null when nothing went wrong. A 403 is surfaced as a credential problem rather than burning the retry budget as though it were transient (`ingestion/s3_reconciliation.feature`). A scan's alone, and it holds `discovered_count` at zero. |
| `event` | The webhook's own `event` field: "the ignored event type is logged" for one the Processor does not handle (`ingestion/webhook_notification.feature`). Open, since the point is a type it has no vocabulary for. Null on a scan. |

**Each kind admits only its own fields, and the table says so.** `failure` is a
scan's and `event` a webhook's, so neither stores on the other kind, and a
`failure` pins `discovered_count` to zero — both failing-scan scenarios end with
no Recording created and none changed. Serving two kinds from one entity is only
safe while the combinations neither kind can mean are refused. Nothing else bounds
`discovered_count`; no scenario does.

**A failed scan is not an alert.** Both failure scenarios ask only that it be
surfaced on the system health view, and the skipped-object Rule says explicitly
that no alert is raised — so nothing here raises a `Notification`.

**Not stored:** which Recordings a discovery produced. No scenario reads a
Recording's discoverer, and the count is what the view shows.

---

## CorpusPair

One source recording paired with one published edit, and the ground truth
derived from that pair. An application record, not an experiments artefact:
`experiments/` is frozen, a reviewer-adjusted Segment becomes a labelled pair
in ordinary use, and a hardcoded filename set in spike code is the standing
trap where the corpus starts grading itself
(`analysis/detection_accuracy.feature`).

| Field | Why it exists |
| --- | --- |
| `recording_id` | The source. One Recording can yield two published outputs, so the pair is not identified by this alone (`analysis/detection_accuracy.feature`). |
| `classification` | `sermon`, `lesson`, `seminar`, or `meeting`. The corpus includes sermons and class sessions, and accuracy is reported separately for each classification (`analysis/detection_accuracy.feature`). |
| `alignment` | `aligned`, `cannot be aligned`, or `not a contiguous excerpt`, null when the published output is one the system produced itself. A pair that cannot be aligned is excluded from the corpus and the exclusion is reported rather than silently dropped (`analysis/detection_accuracy.feature`). |
| `punch_in_seconds`, `punch_out_seconds` | The derived boundaries, stored as the expected answer for that pair. Punch-in is the intercept of the fit, not the middle of it; punch-out accounts for the drift across the segment (`analysis/detection_accuracy.feature`). Only an `aligned` human pair has them. |
| `drift_ppm` | The slope of the fit, in parts per million. Measured rather than averaged away (`analysis/detection_accuracy.feature`). Null when there are no boundaries. |
| `punch_in_difficulty`, `punch_out_difficulty` | `easy` / `moderate` / `hard`, graded from the audio around the human cut, never by the system. A configuration cannot change the difficulty of anything it is scored on (`analysis/detection_accuracy.feature`). Null when there are no boundaries. |
| `covers_more_than_95_percent` | A published output covering more than 95% of its source is flagged rather than silently accepted, and excluded from boundary statistics; a legitimate untrimmed archive is flagged the same way (`analysis/detection_accuracy.feature`). |
| `provenance` | `human` or `machine`. Whether the published output is a human edit or one the system produced itself. Stored, not inferred later from the audio (`analysis/detection_accuracy.feature`). |

**Classification is stored because a pair can exist without a Segment.** The
historical source/edit files join the corpus without a review, and one
Recording can yield a class and a sermon, so neither `Segment.classification`
nor `Recording.kind` can be the join. The closed set is the one
`Segment.classification` already uses.

**A later labelling of the same standing corrects the record instead of adding
one.** One Recording can yield a class and a sermon, and a machine cut is a
different record from a human pair of that classification, so the pair is
identified by recording, classification and provenance together.

**A correction writes only what it measured.** The newest labelling of a
standing sets the boundaries and the alignment verdict it carries, and
`drift_ppm` and the two difficulties keep the values already on the record
wherever that labelling has none — an approval reads no audio and cannot know
them, so replacing them with nulls would destroy a measurement rather than
correct one (reasoning, not quoted). A boundary's difficulty is dropped when
that boundary moves, because a difficulty grades one cut instant and not the
pair.

**A refusal is a verdict, not an absence, so it replaces the record.** `cannot
be aligned` and `not a contiguous excerpt` say that this pair has no
trustworthy answer, and the table above admits no row holding both a refusal
and an expected answer. So a refusal clears boundaries an approval had
recorded — loudly, since the refusal names the gate that failed and is reported
rather than silent — and the reviewer puts them back by approving again. A pair
whose boundaries are stale is worse than a pair with none, because a row that
is silently wrong poisons every later measurement (reasoning, not quoted).

**Three standings, ranked by how strong the evidence is.** A human edit made
with no proposal to react to is the strongest, and carries the most information:
a measured intercept, a fitted `drift_ppm`, and both difficulties graded from
the audio. A boundary the reviewer adjusted in the app is next — the reviewer
chose where the cut belongs, so it is a labelled example, but no audio was read
and it carries none of the measured fields. An approval the reviewer did not
touch is the weakest: it says only that the machine was good enough to accept,
so it is recorded as published, counted toward the proportion approved with no
edit, and never a labelled example (`analysis/detection_accuracy.feature`). The
first two share one standing, `provenance` `human`, because both are human edits
of the same pair and one row per pair is what stops a pair being graded twice
(reasoning, not quoted).

**Each kind of exclusion is its own field, not one flag.** Alignment failure
drops the pair from the corpus and is reported; covering more than 95% of the
source flags it and drops it from boundary statistics; a machine cut is
recorded as published, dropped from ground truth, and identified by
`provenance`.

**An aligned pair admits the expected answer, and the table says so.**
Boundaries, the drift fit and the difficulties are an `aligned` human pair's;
`alignment` is a human edit's. A machine cut carries none of them — its
provenance is stored so it is not inferred later from the audio.

**Not stored:** whether the pair is "in the corpus", "in ground truth" or "in
boundary statistics" as flags of their own — those are `alignment`,
`provenance` and `covers_more_than_95_percent`. Nor the intercept as a second
copy of punch-in, nor an averaged offset in place of the fit. Nor the published
output's path: the expected answer is the boundaries. Nor the filenames in
`align.MACHINE_CUT_MP3S` (the entity can hold provenance; copying those three
into production is a later bead). Nor which Segment a new pair was copied from.
Nor the suite's median and worst-case error; this is the corpus, not a run of
it. An untouched approval is a `machine` pair, not a labelled example.

---

## What this model deliberately does not decide

- **Storage engine.** Nothing above needs more than rows and a blob store.
  Whether that is Postgres, SQLite or files is a framework question, and the
  point of writing this first was to be able to answer it on evidence.
