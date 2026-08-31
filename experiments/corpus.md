# The Corpus

Everything in `~/Desktop/Sermons`, sorted into what it is actually good for.
22 GB, 28 FLAC files, April–August 2026.

Bit depth cleanly separates recorder output from files that had already been
cut by hand: **the recorder writes 32-bit FLAC**, and anything at 16-bit is a
derived extraction. That distinction matters — an experiment that runs on
already-cut audio is measuring nothing.

## Primary corpus — 22 recordings

Original recorder output with a published MP3. Boundary ground truth is
derivable automatically by aligning each MP3 within its FLAC.

| Date | Label | Source (s) | Output (s) | Kind |
| --- | --- | --- | --- | --- |
| 2026-04-12 | John 18.1-12 | 6353 | 2862 | sermon |
| 2026-04-26 | Hebrews 10.5-10 | 9302 | 3221 | sermon |
| 2026-05-03 | Hebrews 10.11-18 | 5787 | 3056 | sermon |
| 2026-05-03 | TEC | 4452 | 3573 | lesson |
| 2026-05-10 | Hebrews 10.19-25 | 6338 | 3385 | sermon |
| 2026-05-17 | Hebrews 10.26-31 | 5601 | 3048 | sermon |
| 2026-05-24 | Romans 6.1-4 | 4727 | 2407 | sermon |
| 2026-05-31 | Hebrews 10.32-39 | 6476 | 3668 | sermon |
| 2026-06-07 | Hebrews 11.1-3 | 5804 | 3355 | sermon |
| 2026-06-07 | TEC - Conflict | 6807 | 4106 | lesson |
| 2026-06-14 | Hebrews 11.4-7 | 8354 | 3006 | sermon |
| 2026-06-21 | 2 Peter 1.3-8 | 8034 | 2751 | sermon |
| 2026-06-28 | Hebrews 11.8-12 | 5868 | 2995 | sermon |
| 2026-06-28 | Members Meeting | 3595 | 3595 | archive, untrimmed |
| 2026-07-05 | Hebrews 11.13-16 | 5134 | 2737 | sermon |
| 2026-07-05 | TEC | 6836 | 3302 | lesson |
| 2026-07-12 | Hebrews 11.17-22 | 5392 | 3076 | sermon |
| 2026-07-19 | Mark 14.60-64 | 8237 | 2427 | sermon |
| 2026-07-26 | Hebrews 11.23-28 | 6262 | 3519 | sermon |
| 2026-08-09 | Hebrews 11.32-40 | 6250 | 3245 | sermon |
| 2026-08-16 | Hebrews 12.1-3 | 5664 | 2983 | sermon |
| 2026-08-23 | Hebrews 12.4-11 | 6269 | 3483 | sermon |

18 sermons, 3 lessons, 1 untrimmed archive. Sources run 79–155 minutes,
outputs 40–68 minutes.

## The two-level case — 1 recording, sessions and segments both labelled

`2026-08-02.flac` is 3h00 of recorder output with **no MP3 of its own**, sitting
beside two 16-bit extractions that came out of it:

| File | Bits | Duration | What it is |
| --- | --- | --- | --- |
| `2026-08-02.flac` | 32 | 10803 s | the recording, containing a class and the service |
| `2026-08-02 - TEC - Speech.flac` | 16 | 4535 s | the class, extracted by hand |
| `2026-08-02 - Hebrews 11.29-31.flac` | 16 | 5532 s | the service, extracted by hand |
| `2026-08-02 - TEC - Speech.mp3` | — | 3455 s | the published class |
| `2026-08-02 - Hebrews 11.29-31.mp3` | — | 3054 s | the published sermon |

This is the only file with two published outputs. Aligning the two
extractions inside the parent gives **session boundaries**; aligning the two
MP3s gives **two punch-in/punch-out pairs**. That is a fully labelled example of
the exact model the spec is built on — Blocks inside a Recording, Segments
inside those — and it arrived for free because of how the work was done by hand.

The two 16-bit extractions are excluded from the primary corpus. They are
already-cut audio and would flatter any result run against them.

## Negative example — 1 recording

`2026-08-16 - Member Meeting.flac`, 32-bit, 4290 s, never published. Useful for
checking that the pipeline does not invent a publishable Segment where none was
wanted.

## Held out as a hard case — 2 files

`2026-07-18 - CT-Islam-part1.flac` (6495 s) and `-part2.flac` (8100 s) produced
one 9705 s MP3. The parts sum to 14595 s, so material was cut from each and the
remainder joined. Q65 put joining out of scope, so this is not a target — but it
is worth keeping as a case that should be *recognised as unusual* rather than
silently mangled.

## The raw bucket — 83 objects, 36.6 GB

`s3://reformation-recordings/` (AWS profile `nas`) is what the recorder uploads.
Two things about it change the design.

**Every corpus recording joins back to its original by exact byte size.** The
files on the Desktop are renamed copies; the bucket keeps the recorder's names,
which carry the wall-clock start time. 26 of 28 Desktop FLACs match exactly one
bucket object. The two that do not are precisely the 16-bit extractions, which
independently confirms the bit-depth split above.

That join recovers **the start time of every recording**, which the Desktop
filenames had destroyed — and start time is one of the strongest classification
signals in the spec (Q16, Q37). It must be recovered before Stage 1, not after.

**There are no `.meta.json` sidecars in the bucket.** Only `.flac` objects. The
recorder writes a sidecar locally but it is not reaching the object store. So
`recorded_at` comes from the object key (`recording_YYYYMMDD_HHMMSS.flac`), and
the "sidecar missing" path in `ingestion/recording_download.feature` is the
normal path rather than an edge case. Worth confirming separately whether the
sidecar is not created or not uploaded — it is a recorder-side question, and
nothing here depends on the answer.

### Start times, and a correction

| Local label | Start | Src min | |
| --- | --- | --- | --- |
| 2026-04-12 - John 18.1-12 | 10:23:18 | 103 | |
| 2026-04-26 - Hebrews 10.5-10 | 09:35:27 | 154 | **multi-session** |
| 2026-05-03 - TEC | 09:00:12 | 70 | |
| 2026-05-03 - Hebrews 10.11-18 | 10:29:34 | 94 | |
| 2026-05-10 - Hebrews 10.19-25 | 10:29:47 | 102 | |
| 2026-05-17 - Hebrews 10.26-31 | 10:29:03 | 91 | |
| 2026-05-24 - Romans 6.1-4 | 10:29:16 | 78 | |
| 2026-05-31 - Hebrews 10.32-39 | 10:29:25 | 106 | |
| 2026-06-07 - TEC - Conflict | 08:26:24 | 111 | **multi-session** |
| 2026-06-07 - Hebrews 11.1-3 | 10:29:01 | 95 | |
| 2026-06-14 - Hebrews 11.4-7 | 09:41:26 | 139 | **multi-session** |
| 2026-06-21 - 2 Peter 1.3-8 | 09:59:15 | 130 | **multi-session** |
| 2026-06-28 - Hebrews 11.8-12 | 10:29:21 | 98 | |
| 2026-06-28 - Members Meeting | 13:00:14 | 55 | |
| 2026-07-05 - TEC | 08:21:08 | 112 | **multi-session** |
| 2026-07-05 - Hebrews 11.13-16 | 10:30:04 | 84 | |
| 2026-07-12 - Hebrews 11.17-22 | 10:30:00 | 87 | |
| 2026-07-19 - Mark 14.60-64 | 09:38:24 | 138 | **multi-session** |
| 2026-07-26 - Hebrews 11.23-28 | 10:29:57 | 103 | |
| 2026-08-09 - Hebrews 11.32-40 | 10:29:35 | 102 | |
| 2026-08-16 - Hebrews 12.1-3 | 10:30:07 | 93 | |
| 2026-08-16 - Member Meeting | 12:55:12 | 66 | |
| 2026-08-23 - Hebrews 12.4-11 | 10:29:52 | 104 | |

**I was wrong that `2026-08-02` is the only multi-session recording.** Six more
start well before the service and run long enough to contain something else
first — most likely band practice, or a class, that never got a gap long enough
to split the file. That is **7 of 23**, not 1.

This is good news for the experiment and bad news for any design that assumed
one recording is one thing. It also means the wall-clock signal must be applied
**to Blocks, not to Recordings** — a file starting at 09:35 still contains a
10:30 service, just not at its beginning. `block_classification.feature` already
does this correctly; the corpus now proves it was necessary.

`2026-08-02` remains the only recording with two *published* outputs, so it is
still the only two-level labelled example.

## The negative set — 57 recordings, 14.6 GB

Bucket objects with no corresponding edit. Never published, for whatever reason.

| Size band | Count | Likely |
| --- | --- | --- |
| under 50 MB | 1 | false trigger |
| 50–150 MB | 30 | practice, short events, false triggers |
| 150–500 MB | 19 | practice, midweek events |
| over 500 MB | 7 | long recordings nobody published |

38 fall on a Sunday, 19 on other days.

These arrived free and they answer a question the primary corpus cannot: **does
the pipeline invent work that is not there?** A system that scores perfectly on
22 sermons and proposes a confident sermon Segment for every band practice is
not usable. They are also the only available material for Q78, the "no
substantive content" threshold, since the Desktop folder contains nothing that
was ever discarded.

They are unlabelled, and labelling all 57 is not worth it. Sample 12 for the
negative set — the one under 50 MB, six from 50–150 MB, three from 150–500 MB,
two over 500 MB — and have a human spend a few minutes marking each simply as
*publishable* or *not*. That is a binary judgement per recording, not a block
labelling exercise.

## Split

Tuning keyword lists and prompts against all 22 recordings would overfit a very
small corpus. Fixed split, decided now and written down so it cannot drift:

**Development (8)** — tune freely:
2026-04-12, 2026-05-03 TEC, 2026-05-10, 2026-05-31, 2026-06-14,
2026-06-28 Members Meeting, 2026-07-12, 2026-08-09

**Held out (14)** — run once, at the end of each stage, and report:
everything else in the primary corpus.

The development set deliberately contains one lesson and the untrimmed archive
so that both unusual shapes are visible while tuning. Two lessons remain in the
held-out set.

`2026-08-02.flac` belongs to neither. It is scored separately, because it is the
only multi-session example and there is nothing to average it against.
