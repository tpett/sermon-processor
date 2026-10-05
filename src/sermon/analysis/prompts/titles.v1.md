You are naming one audio recording made at a church, so a person scanning a list
of recordings can tell what each one is. You see only a description of the
recording, never the audio.

What the recording contains, in order (start–end, what kind of speech or music,
and a one-line summary where there is one):

{blocks}

Teaching found in it:

{segments}

It started on a {weekday} at {start_time} local time and runs {duration}.

The day and the time are evidence, not rules. A Sunday morning service, a class
held before it, a band rehearsing before the service, a members' meeting, a
special service such as Good Friday, and a weekend seminar all happen; weigh the
time against what the contents say.

Names the church uses (always write the full name in the title, never the
acronym):

{glossary}

Answer with one JSON object and nothing else:

{"kind": "...", "title": "...", "series": "...", "topic": "..."}

- kind: exactly one of service, class, special_service, meeting, rehearsal,
  empty, unknown.
- title: short, at most eight words. Never include a date, a day of the month,
  a month or a year. Examples of the style wanted:
  "Sunday Service - <passage>", "Theological Equipping Class - <topic>",
  "Pre-Service Rehearsal", "Members Meeting", "Good Friday Service".
  {passage}
- series: the name of the class or series if the recording is one, written in
  full, otherwise null.
- topic: the subject of the class or series session in one to three words,
  otherwise null.
