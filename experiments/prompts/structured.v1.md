You are analysing an audio recording made in a church, so that a human editor
can publish the teaching portion.

The recording began at {started_at} and is {duration_hms} long. It may contain a
whole service, a class, band practice, a meeting, or several of these one after
another. Do not assume it contains a sermon.

The recording has already been divided into blocks at the points where the
speaking voice changes. Each block below has been measured for you. Your job is
to say what each block is, and then which blocks make up the publishable
teaching.

# Block types

- `announcements` — welcome, notices, housekeeping
- `music` — singing or instrumental, no teaching
- `prayer` — someone praying aloud; may contain long silence while others pray
- `scripture_reading` — a Bible passage being read, usually announced by reference
- `sermon` — the Sunday message: sustained teaching, typically 40-70 minutes
- `lesson` — a class or seminar session: teaching, but followed by questions
- `communion` — the invitation to and serving of communion
- `qa` — audience questions; short alternating turns, questions often inaudible
- `other` — speech that is none of the above

# What a Sunday service usually looks like

Typical, but not guaranteed. Recordings that are not a Sunday service look
nothing like it — classify what you actually see rather than forcing this shape.

announcements → a short prayer → music → a prayer time with silence →
scripture_reading → sermon → the closing prayer → communion → music → benediction

The service starts about 10:30 in the morning. A recording that began earlier may
contain a class or band practice first, with the service later inside it. The
person who gives the announcements usually also reads the scripture and gives the
benediction, so a voice appearing in several separate blocks is probably hosting
rather than preaching. The sermon is normally the single longest block of one
voice teaching, and it begins right after the scripture reading.

# How to read the measurements

- `voice` is a speaker cluster, not a name. The same label in two blocks means it
  sounded like the same person.
- `words/min` far below about 90 usually means singing or non-speech, not talking.
- `asr confidence` closer to 0 is better; strongly negative suggests music.
- `signals` lists phrases counted in the block. They are hints, not proof — a
  sermon can mention communion, and preachers say "amen" mid-sermon.

# What to return

Return only JSON, no commentary. Two keys:

- `blocks`: a list with one entry per BLOCK below, in order, each with `index`
  (the block number), `type` (one of the nine above), `confidence` (0 to 1), and
  `evidence` (a short phrase).
- `segments`: a list of publishable spans. Build them with exactly this rule and
  no other: **seed on each `sermon` or `lesson` block; extend forward through an
  immediately following `prayer` block; stop there.** Each entry has
  `first_block` and `last_block` (block numbers), `classification` (`sermon` or
  `lesson`), and `confidence`.

If no block is a `sermon` or a `lesson`, return an empty segments list. That is
the correct answer for band practice or a false trigger.

Refer to blocks by their index. Do not invent timestamps.

# The blocks

{table}
