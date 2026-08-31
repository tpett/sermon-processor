You are helping a church editor review a recording quickly, without listening to
it. Below is the transcript of one block of a recording — one person doing one
thing.

Write two things.

1. A one-line summary of what happens in this block. Concrete and specific: name
   the passage, the topic, the notice, whatever it actually is. Under 15 words.
   Write it for someone deciding whether this is the part they want to publish.

2. The single most recognisable moment in this block — the few seconds that would
   let a person hear it and instantly know what this block is. Prefer a sentence
   that names the subject, announces the passage, or states the main point. Avoid
   greetings, throat-clearing, filler, and anything that could belong to any block.

Return only JSON, no commentary. Two keys:

- `summary`: the one-line summary
- `cue_quote`: the exact words of the recognisable moment, copied verbatim from
  the transcript below. Between 5 and 30 words. It must appear in the transcript
  word for word so it can be located.

Block runs from {block_start} to {block_end} ({block_minutes} minutes).

Transcript:

{block_text}
