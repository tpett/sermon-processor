You are naming one audio recording made at a church: the class held in it
before the service. You see only a description of the class, never the audio.

What the class contains, in order (start–end, what kind of speech, and a
one-line summary where there is one; a summary may call the teaching a sermon,
but it is the class):

{blocks}

The recording started on a {weekday} at {start_time} local time. A service
follows the class{passage}.

Names the church uses for its classes and series:

{glossary}

Answer with one JSON object and nothing else:

{"series": "...", "topic": "..."}

- series: the name from the list above of the class or series this class
  belongs to, written in full; null if none fits.
- topic: the subject taught, as short as it can be said: usually one word, a
  plain noun, at most three; never a person's name and never a passage.
