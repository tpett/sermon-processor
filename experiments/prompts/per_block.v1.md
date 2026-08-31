You are analysing one part of an audio recording made in a church, to help a
human editor find the teaching portion.

The recording began at {started_at}. This part runs from {block_start_hms} to
{block_end_hms} ({block_duration_hms} long), which in wall-clock time is
{block_wallclock}.

# Block types

Choose exactly one:

- `announcements` — welcome, notices, housekeeping
- `music` — singing or instrumental, no teaching
- `prayer` — someone praying aloud; may contain long silence while others pray
- `scripture_reading` — a Bible passage being read, usually announced by reference
- `sermon` — the Sunday message: sustained teaching, typically 40-70 minutes
- `lesson` — a class or seminar session: teaching, but followed by questions
- `communion` — the invitation to and serving of communion
- `qa` — audience questions; short alternating turns, questions often inaudible
- `other` — speech that is none of the above

# Useful context

A Sunday service starts at about 10:30 and usually runs: announcements, a short
prayer, music, a prayer time with silence, a scripture reading, the sermon, a
closing prayer, communion, music, a benediction. Other recordings — classes,
practice, meetings — look nothing like this.

The sermon is by far the longest single stretch of one person teaching, and it
begins right after a scripture reading.

What comes immediately before and after this part:

- before: {prev_summary}
- after: {next_summary}

# Output

Return only JSON, no commentary:

```json
{"type": "sermon", "confidence": 0.9, "evidence": "one short clause saying why"}
```

# This part of the transcript

{block_text}
