# Open Questions

Updated 2026-08-27, fifth pass. **The spec is functionally complete.** Every
question that shapes behaviour has been answered. What remains is a short tail
of interface conveniences, two technology choices, and the tech-stack
conversation you parked in the first pass.

Question IDs are referenced from comments inside the `.feature` files, so you
can see exactly which scenarios each answer changes.

## Priority scheme

| Priority | Meaning |
| --- | --- |
| **P0** | Blocking. The feature files are *wrong* until this is answered. |
| **P1** | Needed before building. A scenario exists but states a guess. |
| **P2** | Needed eventually. Changes behaviour, not shape. |
| **P3** | Probably skip. Deprioritized by one of your answers. |
| **ANSWERED** | You answered it. Kept for the record and for its consequences. |
| **MEASURED** | Closed by evidence from `~/Desktop/Sermons`. |
| **DEFERRED** | Parked with the tech-stack discussion, at your request. |

**No P0s and no P1s.** 57 of 78 questions are answered, measured or resolved.
Nothing that is still open changes the shape of the system, and every remaining
scenario that rests on a guess says so in a comment.

## What is actually left

Nothing here blocks anything. In rough order of how much they matter:

**Worth deciding when you build the interface**

- **Q29 / Q45 / Q46 / Q43** — small interface and notification behaviours:
  whether a label is required before approval, whether notifications batch,
  whether unapproved recordings get a nudge, and who receives them. All have
  sensible defaults in the spec already.
- **Q26** — the stitched cut preview. Largely superseded: previewing a boundary
  already plays across it. The remaining question is whether you also want to
  hear the two boundaries joined, which is a different thing and probably not.
- **Q47** — fades at the cut points. Assumed a few milliseconds. Only worth
  revisiting if you ever hear a click.

**Technology choices, for the build conversation**

- **Q77** — how the preview audio is made seekable. I have a recommendation.
- **Q13 / Q76** — the local transcription and summarisation models, which your
  spike will settle.
- **Q61 / Q38 / Q53** — stack, deployment, network exposure. Q53 is answered;
  the other two are the conversation you wanted to have after the spec.

**Probably never**

Q6, Q23, Q24, Q28, Q30, Q35, Q39, Q40, Q41, Q44, Q52 and Q78 are all either
answered by a sensible default in the spec or made irrelevant by an earlier
answer. They are recorded so that if one turns out to matter, the reasoning is
already written down.

## Where the remaining risk is

Not in this document. The spec describes behaviour that has never been tested
against real audio, and the two places it is most likely to be wrong are:

1. **Block classification.** Everything downstream depends on correctly typing a
   Block as `sermon`, `prayer`, `scripture_reading` or `communion`. The rules
   read plausibly, but plausible is not measured.
2. **Whether transcript cues survive real recordings.** The cue phrases are
   drawn from your descriptions. Reverb, an unmic'd congregation and 12-15 LU of
   dynamic range may make some of them unrecognisable.

Both are answerable the same way: derive ground truth from the 24 pairs (Q15)
and run `analysis/detection_accuracy.feature`. That is the first thing worth
building, before any interface exists, because it is the only thing that can
tell us whether the analysis design is sound.

---

## What your answers changed

Your response to **Q60** was the most consequential thing in this document. It
revealed three things the feature files do not currently model:

- **A single recording can contain more than one session.** TEC at 9:00 and the
  10:30 service land in one file whenever the gap between them is shorter than
  the recorder's silence threshold. `~/Desktop/Sermons` confirms it:
  `2026-08-02.flac` is 1.4 GB and unpaired, sitting beside two smaller derived
  FLACs (`- Hebrews 11.29-31` and `- TEC - Speech`) that you evidently cut out
  of it by hand.
- **You process more than sermons.** TEC classes, a members meeting, and a
  multi-part class on Islam all have finished MP3s in that folder. The features
  assume every recording is either a sermon or rubbish.
- **The reverse also happens.** `2026-07-18 - CT-Islam` is two FLAC parts and
  one MP3. Two sources became one output.

Your response to **Q58** (option A — stop at the MP3) removed a lot of
speculative scope: podcast metadata, ID3 tags and feed publishing all drop to
P3. Your response to **Q61** parks the whole deployment and tooling group.

The measurements answered several questions outright and turned the audio
questions from open design decisions into confirmations.

---

## Answered

**Q58 — Where does the job actually end?** — **ANSWERED**

> Response: option A, we will not try to do anything beyond hte processing for now.

Consequence: `processing/artifact_downloads.feature` is the finish line. Q31,
Q32, Q41, Q59 and Q62 all drop to P3. No RSS, no host integration, no upload.

**Q60 — What is the current manual process, start to finish?** — **ANSWERED**

> Response: Today, I download the raw FLAC file and manually set the punch-in/punch-out points. I cut the segment to that, run the normalized task, and export the MP3. I do that manually each week.
>
> I can tell which file is the Sunday service because the service starts at 10:30 in the morning, and it is usually timestamped at 10:29:52 or something like that. I can usually tell which of the files is the actual service.
>
> There is usually another one that is the band practicing beforehand. On weeks when we have a theological equipping class (TEC), there is another recording that starts at 9:00. There are times when the TEC and the service end up in the same big file because there has to be a silence gap over a certain threshold for the files to get split. There have been times when I have had to extract the TEC and the sermon from the same recording.
>
> This can happen anytime, and it will be a tricky thing for this to handle automatically. I wonder if the best approach is to detect within an audio file when a long-running speaker is speaking about something, and then break those classifications. Each one within the same audio file gets a punch-in/punch-out, and the human is selecting which one is the sermon. It should be easy to sample that punch-in/punch-out, so a person could tell where this is.
>
> This depends on what tooling is available for giving a deterministic algorithm something to use to view these files and make a decision.

Consequence: answers Q8, Q9 and Q37; raises Q63, Q64, Q65 and Q68. Your
instinct about segmenting into long-form speaker blocks and letting a human
pick is, I think, right — see Q63.

**Q15 — Can I have sample recordings with known-correct punch points?** — **ANSWERED**

> Response: The ~/Desktop/Sermons folder has several weeks of past products. The flac file is the raw and the MP3 file is the edited version. We might be able to derive the punch-in/out if we can find where the mp3 file clip starts within the flac file. I'm not sure how easy that is.

24 usable pairs, April through August 2026. On your sub-question — deriving the
punch points — it is very doable, and there are two independent methods:

- **Audio alignment.** Decode both to low-rate mono and cross-correlate the
  first and last ~30 seconds of the MP3 against the FLAC. Your edit is a plain
  peak-normalized copy (a linear gain — see Q48), so the waveform shape is
  preserved and correlation should lock on hard. Sample-accurate.
- **Transcript alignment.** Transcribe the first and last minute of the MP3,
  find that text in the FLAC's transcript. Slower, but immune to any
  amplitude processing, and it doubles as a test of whether transcript cues can
  find the boundaries unaided.

The MP3 duration is exact, so finding the punch-in gives the punch-out for
free. That is a 24-row ground-truth table, which turns
`analysis/punch_in_detection.feature` and `punch_out_detection.feature` from
guesswork into a measurable target. Say the word and I will build it — but it
is tooling, so I have not started.

**Q61 — What should this be built in, and where does it run?** — **DEFERRED**

> Response: I'm not too worried about this yet. I want to get the spec, the behavior in these feature files correct, and then we can discuss the technology stack.

Consequence: Q13, Q38 and Q53 move to DEFERRED with it.

---

## Answered — the model questions

**Q63 — Does one recording produce many candidate segments, with you picking one?** — **ANSWERED**

> RESPONSE: I like the Segment model where multiple speakings can be extracted from the same recording. The user will determine which ones he wants to keep and which to leave. The metadata will be stored in the database for what was detected so the user could always return later to extract a piece he passed over previously.

Built. The Segment model is now the spine of the spec — see the revised
`README.md` for the two state machines, and `analysis/blocking.feature`,
`analysis/segment_proposal.feature` and `interface/segment_review.feature` for the behaviour.

The "return later" requirement turned out to be load-bearing. It means a
skipped Segment keeps its boundaries, classification, evidence and transcript
indefinitely, and that approving it months later must not require re-running
Analysis. That in turn puts a hard requirement on retention — see Q71 and Q56.

**Q64 — Is this tool for sermons, or for anything you publish?** — **ANSWERED**

> RESPONSE: Anything I want to publish. Sermons is the primary use case, but lessons (from TEC), and seminars are also included. The member meeting case was merely for archival purposes so I just saved the whole file without editing. We do not publish this.

Built as two separate concepts, because your answer contained two:

- **Classification** — what a Segment *is*: `sermon`, `lesson`, `seminar`,
  `meeting`, `music`, `other`. See `analysis/block_classification.feature`.
  Classification selects which boundary rules run.
- **Intent** — why it is being rendered: `publish` or `archive`. The members
  meeting is the archive case: whole file, boundaries barely matter, never
  distributed.

The name "Sermon Processor" is now slightly wrong, but I have left it alone.

**Q65 — Do multiple source files ever need to become one output?** — **ANSWERED, out of scope**

> RESPONSE: Not today. That's an editorial decision though so it could be possible in the future, but I think it is acceptable for this system to not handle that directly. The user could just download the pieces and compose them manually.

No concatenation. Each Segment renders to its own file; two-part material is
downloaded and joined by hand. Nothing was added to the spec.

**Q66 — The right channel is dead. Confirm I should use the left only.** — **ANSWERED**

> RESPONSE: Yes, I did forget to mention that I always split the track to mono and delete the silent channel, so I end up exporting a mono audio file in the end. Our recorder receives a mono signal into a stereo recorder.

Built as an explicit **extract**, never a downmix — see the first rule in
`processing/audio_rendering.feature`. The probe stage now measures each channel
separately and records which one carries signal, so the render never has to
assume.

I added one scenario you did not ask for: if both channels ever *do* carry
signal, the render stops and asks rather than guessing. A changed cable or an
edited recorder config would produce that, and a silent 6 dB error is much
worse than a question.

Worth doing separately: the recorder is capturing stereo when its own config
template defaults to `channels: 1`. Fixing that halves your file sizes and
removes this whole class of problem at the source.

**Q67 — Your source recordings are clipping.** — **ANSWERED, hardware**

> RESPONSE: I'm aware, I need to adjust the input volume on the physical A2D unit.

Out of the Processor's hands. The spec now *reports* it rather than trying to
repair it: the probe flags "source clipping detected", the flag shows on the
detail view, and the render notes it on the Segment. Files already recorded
still have to render, so the render brings them down to the peak ceiling and
makes no attempt to reconstruct what was lost.

**Q68 — Is "convert the whole file, no trimming" a supported mode?** — **ANSWERED**

> RESPONSE: This does happen, but as I mentioned above, it's really just about archival. So the start/end points really don't matter as it's just for posterity and internal use not public consumption.

Built as intent `archive`. "Archive whole recording" is a one-click action on
the Recording detail view: it creates a Segment spanning the entire file,
skips boundary refinement, requires no label, and names the output from the
date alone. Channel extraction and loudness normalization still apply — there
is no reason for the archive copy to be unlistenable.

---

## New questions raised by those answers

**Q69 — Who decides publish versus archive?** — **ANSWERED**

The spec currently infers it: `meeting` defaults to `archive`, everything else
defaults to `publish`, and the reviewer can override. Is that right? Concretely:
would you ever archive a sermon without publishing it — a guest speaker who
asked not to be distributed, a recording too poor to release — and would you
ever publish a members meeting?

> RESPONSE: This should be editable by the human user. In general, sermons will always be published, but I cannot anticipate every eventuality. Keeping this human gated is the best call.


**Consequence.** Intent is prefilled from the classification but never applied
without a human approving it, and there is an explicit scenario asserting that
nothing is ever published on classification alone. Both directions work:
archiving a sermon you do not want distributed, and publishing something that
defaulted to archive.

**Q70 — Is the running order reliable?** — **ANSWERED, and it reshaped the model**

When one file holds the 9:00 class and the 10:30 service, is the earlier
Segment always the class and the later one always the service? If so, position
becomes a usable classification signal on top of the start-time signal. If the
order can vary, I will not lean on it.

> RESPONSE: In the case of a TEC Sunday, yes it will always work that way. As much as possible, let's try to find a generic solution for these problems, rather than overfitting the solution to the current workflow. I prefer to keep this generic.
For instance, if we had the ability to:
> - Just detect spoken word in a recording by a given speaker, and find the punch-in and punch-out points for that.
> - Find an appropriate ending for certain types of messages, for example, when the regular sermon and the communion piece need to be cut out.
There's also another example with the TEC class, because they usually end with a Q&A section that we cut out. Often, parts of that aren't something we want to publish from a content perspective, and it's very difficult to hear the questions because the audience isn't mic'd. Only the speaker is, so we usually just cut that out completely.
> It might be worth exploring how we can use a lightweight local model to summarize the spoken-word segments. Anything that can help the human quickly make decisions without having to listen to large pieces of the recording is worth it for this tool. We don't need to completely automate the process. I just want to automate as much of it as we can without sacrificing the quality of the output product. 


**Consequence — this changed the model again.** You asked for a generic
solution rather than one overfitted to the current running order, and then
described exactly what a generic one looks like: split on speaker change,
classify each piece, and let the boundary rules work on those classifications.

So there are now two levels. **Blocks** are the anatomy of a recording —
`announcements`, `music`, `prayer`, `scripture_reading`, `sermon`, `lesson`,
`communion`, `qa`, `other`. **Segments** are what gets published, built from
Blocks by one rule that covers both cases you named:

> seed on a teaching Block, extend forward through an immediately following
> prayer Block, stop before whatever comes next.

On a Sunday "whatever comes next" is communion. On a class Sunday it is Q&A.
Neither is named in the rule. See `analysis/blocking.feature`,
`analysis/block_classification.feature` and `analysis/segment_proposal.feature`.

This made the boundary detection *shorter*, not longer. The spoken cues are now
inputs to classifying a Block rather than rules for placing a cut, so
`punch_in_detection.feature` and `punch_out_detection.feature` shrank to what
they should always have been: where exactly inside the run-up does the cut fall.

**Q71 — What is the real promise behind "return later"?** — **ANSWERED**

You want to be able to come back for a Segment you passed over. Two things have
to be true for that to work, and I can only guarantee one of them:

- The Segment's boundaries and metadata survive. That is in the spec and is
  easy.
- **The source audio still exists.** That is not in my control. If
  `s3.home.tpett.me` drops the FLAC after some retention window, a Segment
  skipped in August becomes unextractable in November, and the promise
  quietly breaks.

So: how long is the source retained, and how long do you actually expect to be
able to reach back? If the answer is "forever", that is 46 GB every five
months and worth saying out loud now. This is the same underlying question as
Q56, which is why I promoted it.

> RESPONSE: We do not currently have any cleanup of the recordings there. As it stands, they are stored indefinitely, so this isn't something that needs to be a concern for this tool. 


**Consequence — the promise is safe.** Because sources are permanent, local
cleanup can be aggressive without risk: the spec now removes local FLACs once a
Recording is fully dispositioned and re-downloads on demand if you come back for
a skipped Segment years later. There is a scenario for exactly that.

I kept one defensive scenario for a source going missing unexpectedly. Nothing
prunes the bucket today, but the failure is silent and would destroy stored work,
so it is worth having a flag for it rather than discovering it on the day.

**Q72 — What are the segmentation thresholds?** — **ANSWERED, and it reshaped the model**

Two numbers I have guessed at, both in the old `analysis/segmentation.feature`:

- **How long a quiet gap separates two sessions?** Currently: gaps under 3
  minutes do not split, gaps over 8 minutes do. The real question is what the
  gap between your 9:00 class and 10:30 service typically looks like — the
  room is not silent between them, so "quiet" may need to mean "no sustained
  single-speaker activity" rather than "silence".
- **How short is too short to be a session?** Currently 12 minutes. Below that
  I assume it is announcements or a false start, not something you would ever
  publish. Your shortest published file is 40 minutes, so there is a lot of
  room here.

The recorder's own `silence_timeout` default is 600 seconds, which is the
threshold that decides whether you get one file or two in the first place.
Knowing its production value would help me set these.

> RESPONSE: This is actually solved by the audio recorder itself, as far as the file breakup is concerned. I would say the best rule of thumb is to separate segments within a given file based on speaker changes.
If we have the ability to tell the difference between:
> - announcements
> - singing
> - a prayer session
> - a scripture reading
> - a sermon
> - any other spoken-word segments
we can classify each one, and that would really help it be useful to the reviewer. Silence is a tell, but there aren't large pieces of silence within a service, in general.


**Consequence — silence is out, speaker change is in.** The original
`segmentation.feature` split on quiet gaps. That was wrong, and your Q20 answer
shows why: there are 15-20 seconds of deliberate silence during the prayer at
the *start* of the sermon. Splitting on silence would have cut the sermon in
half every single week.

`analysis/blocking.feature` now divides on speaker and activity change, and has
an explicit scenario asserting that the prayer pause does **not** create a
boundary. Silence is still recorded — it is what a boundary snaps to — but it
never drives the division.

The block types you listed are exactly the taxonomy in
`analysis/block_classification.feature`. I added `communion` and `qa` because
the punch-out rule needs to know what it is stopping before.

**Q73 — Does the classification taxonomy cover everything?** — **ANSWERED**

Proposed: `sermon`, `lesson`, `seminar`, `meeting`, `music`, `other`. Drawn
from what is in `~/Desktop/Sermons` — sermons, TEC, a members meeting, a
multi-part class on Islam. Is anything missing? Weddings, funerals, guest
speakers, conferences, a Christmas or Good Friday service that does not look
like a normal Sunday?

> RESPONSE: That should be good for now.

**Q74 — How does a TEC lesson actually end?** — **ANSWERED**

The sermon punch-out rules are specific and were given to me: closing prayer,
"amen", communion invitation. I have nothing equivalent for a class, so
`block_classification.feature` currently falls back to "the end of sustained
speech" and openly reports lower confidence.

If a class has a recognisable ending — a closing prayer, a "we'll pick this up
next week", a shift into Q&A you would cut — tell me and lesson detection gets
as good as sermon detection. If not, the fallback stands and you will hand-set
the punch-out on class weeks.

> RESPONSE: Almost always with a Q&A session that we do not include in the published product. The usual pattern is that after the class is complete, there is a prayer, and then out of the prayer we go into Q&A. There'll be something like, "Alright, let's have some questions," or "Are there any questions?" The punch-out should be right before that, right after the "amen" from the prayer. 


**Consequence.** `qa` is now a Block type with its own cues — "are there any
questions", "alright, let us have some questions" — plus a shape signal, since
the audience is unmic'd and their contributions are much quieter than the
speaker's. That quiet back-and-forth is a good signature.

Because the punch-out rule stops before *whatever follows the trailing prayer*,
class detection is now as strong as sermon detection. Same rule, no special
casing. This is also what distinguishes a `lesson` from a `sermon`: a teaching
block followed by prayer and then Q&A is a class.

---

## New questions raised by this round

**Q77 — How should the preview audio be made seekable?** — **P2, a technology choice**

`analysis/preview_audio.feature` requires that the browser can seek without
downloading the whole file, and leaves the mechanism open. Two approaches
satisfy it:

- **Segmented streaming** (HLS or DASH): the preview is cut into short chunks
  with a manifest, and the player fetches only the chunks it needs. Robust, well
  supported, but it is a pipeline and a set of files rather than one file.
- **A single file with byte-range seeking**: a constant-bitrate MP3 or an Opus
  file in an Ogg container, served with range request support, where the player
  can calculate roughly where to jump. Much simpler, slightly less precise
  seeking, and adequate for scrubbing.

My recommendation is the second, on your "not overly complicated" constraint. A
CBR preview at a decent bitrate served over range requests gets you most of the
benefit for a fraction of the machinery, and moving to segmented streaming later
would not change anything else in the spec.

This is a build-time decision rather than a spec question, so it can wait for
the tech stack conversation.

**Q78 — What counts as "no substantive content"?** — **P3**

`audio_probe.feature` flags a Recording as an accidental trigger when less than
some proportion of it sits above the noise floor. I set that at roughly 1%, with
the threshold deliberately biased toward analysing rather than ignoring.

There is nothing to calibrate against — `~/Desktop/Sermons` contains only
recordings you kept, so there are no false triggers in it. If a few turn up in
the bucket, pointing me at them would let me set this from data rather than
instinct. Until then the guess is safe, because being wrong means analysing
something unnecessarily, which now costs nothing.


**Q75 — What boundary error would you accept without reaching for the waveform?** — **ANSWERED, and it reframed the target**

`analysis/detection_accuracy.feature` grades the machine against the 24 pairs,
but I invented the pass mark. My proposal:

| Punch error | Grade |
| --- | --- |
| under 0.5 s | as good as hand-made |
| under 2 s | acceptable, minor nudge |
| under 15 s | needs real correction |
| beyond that | wrong |

What actually matters is the first row: below what error would you just approve
without opening the editor? That number is the target the whole analysis half of
this system is aiming at, and it is worth being honest about rather than letting
me pick it.

A related question: is a punch-in error worse than a punch-out error? Starting
half a second late clips a word and is obvious. Ending half a second late leaves
a moment of room tone that nobody notices. My instinct is that the punch-in
deserves a tighter tolerance, but you are the one who has listened to these.

> RESPONSE: I would confirm that the punch in is more important than the punch out. More people listen to the beginning than to the end. That being said, I do want both to be correct and every segment will be reviewed by a person. The real-time savings here is that if we can get this to work 80% of the time, then it's just:
> 1. Hit play to preview the punch-in.
> 2. Hit play to preview the punch-out.
> 3. Approve, and we're done.
> I do want the tolerance to be tight. I don't think we can say that the punch error has a fixed time length, because it very much depends on how tight the words are or how tight the transition is. Some transitions are very easy: there's 10 seconds of silence, and the first word should be the first part of the recording. You just cut right before that.
> Other times, there's noise, feedback, or something that makes the cut point tougher because you don't want to start with that noise, so you end up having to cut around it. Those are the ones where it might just have to be a person to do it, but being able to find the right point is not always just a time tolerance. Sometimes even a few hundred ms can make a big difference in the quality of the output.


**Consequence — the target is a workflow, not a tolerance.** You are right that
a fixed millisecond threshold is the wrong measure, and the three-click
description is a much better one. Two changes came out of this.

The accuracy suite now leads with **the proportion of Segments approved with no
boundary edit**, targeting 80%, with raw errors reported alongside rather than
instead. Punch-in errors are weighted more heavily than punch-out errors, and
results are stratified by how hard each transition was — a poor result on a cut
sitting next to feedback is not the same failure as one on ten seconds of clean
silence.

More usefully, **cut difficulty is now assessed at render time, not just at test
time.** `punch_in_detection.feature` grades each cut easy or hard from the audio
around it, and a hard cut is flagged with its reason ("noise near the cut
point") so it interrupts the three-click path deliberately. Getting a hard cut
wrong is acceptable; getting it wrong quietly is not. And the three-click path
itself is now an explicit scenario in `interface/segment_review.feature` — the
two previews are the primary controls, and the editor is available but never
required.

**Q76 — Which summariser, and does it stay local?** — **ANSWERED, and it became a constraint**

`analysis/summarization.feature` needs a language model to write the one-line
summaries. You mentioned "a lightweight local model", which I have taken as a
preference rather than a decision, and the spec is written so summaries are
optional and never affect output — so this can be answered late, or answered
with "skip it for v1".

The real question is whether summarising the sermon means sending the
congregation's audio or transcript to a third party. If that matters, local is
not just a performance preference and it should be recorded as a constraint. It
also folds into Q13, the transcription engine, since both are the same trade.

> RESPONSE: I do want this to stay local if possible. We don't have a lot of GPU capability on the server this will be running on, so we might not be able to run a big model. We might have to use more heuristics, or I might need to set up another server for running some olama models that we can use for this service.

> As part of this, we'll do a spike once we know what we need. We can try various things in the form of a throwaway spike just to see how well they perform, and then from that we can decide what technology makes the most sense. There's a lot about this that I just don't know, which is going to require some research.
> 
> We have some options, but from the standpoint of not wanting to pay for API usage to be able to do this stuff, I do want to run it locally. I do have several options: old Mac laptops with good unified memory that we could actually run some decent models on, but I want to do it as lightweight as possible. 


**Consequence — this is now a constraint, not a preference.** Two separate
reasons point the same way: not paying for API usage, and not sending the
congregation's audio to a third party. So both `summarization.feature` and
`transcription.feature` now carry an explicit rule that no audio and no
transcript leaves the local network, and that no hosted service is called even
as a fallback when the local model is weak.

The spec is deliberately written so your spike can land anywhere. A small local
model, a bigger one on a separate box over the tailnet, or no model at all with
heuristic summaries — all three are specified, and none of them changes anything
downstream, because summaries can never affect output.

**This narrows Q13 considerably.** The transcription engine is now a local-only
choice too, which removes the hosted APIs from consideration entirely.

---

## Ingestion

**Q1 — How does the Pi reach the Processor?** — **ANSWERED**
Unchanged, and still needed before `webhook_notification.feature` is buildable.
If both machines are on the same tailnet the HMAC signing scenarios are
arguably ceremony; if the Processor is publicly reachable they matter. Related
to Q38, which is now deferred — but this one is about the webhook contract, not
deployment, so it stays P1.

> RESPONSE: They are on the same tailnet, so we will just hit a web endpoint on the deployment server


**Consequence — a lot of ceremony deleted.** `webhook_notification.feature` lost
its HMAC signing, signature-mismatch and replay-window scenarios. The tailnet is
the boundary. What replaced them, per your Q5 answer, is a proper idempotency
rule: same object key means same Recording, concurrent duplicate webhooks
produce exactly one Recording, and a webhook racing the reconciliation scan does
not double-ingest.

**Q2 — Is S3 upload actually live on the recorder today?** — **ANSWERED**
Still open and still cheap to answer. The root README says S3; the recorder's
`TODO.md` still lists "Add S3 compatible upload method" as unchecked; the code
in `upload-processor.rb` supports it and the config template points at
`https://s3.home.tpett.me`. Which is running right now, and what bucket and
prefix? If it is rsync today, S3 has to land before any of this works.

> RESPONSE: It hits a Garage S3 instance on my homelab. Each are in the same Tailnet so they are accessible.

**Q3 — What can the webhook payload actually contain?** — **ANSWERED, I looked**
The scenarios assume checksum, duration and device id are all available. Worth
confirming before the contract is fixed, but not blocking.

> RESPONSE: You may review what is available in the audio-recorder repository. That would be a better place to look than my memory. 


**Answer, from the recorder source.** The sidecar `.meta.json` written by
`audio-monitor.rb` carries: `timestamp`, `datetime`, `duration`, `format`,
`sample_rate`, `channels`, `threshold_db`, `device`, `version`. The S3 upload
path in `upload-processor.rb` already computes an **MD5** to verify against the
object ETag (SHA256 exists only on the rsync path).

So the webhook can carry object key, bucket, size, MD5, recorded time, duration,
sample rate and channels without any new computation. Two gaps worth knowing:

- **There is no machine identity.** The `device` field is the ALSA device
  string (`hw:2,0`), not a hostname. If you ever run a second recorder, adding a
  host field is a small recorder-side change. The spec treats it as optional.
- **The checksum is MD5, not SHA256.** I changed the scenarios to match rather
  than asking you to add SHA256 for the S3 path.

**Q4 — What does a changed source file mean?** — **ANSWERED, closed**
Almost certainly never happens in your setup. The current re-ingest-and-warn
behaviour is fine.

> RESPONSE: Source files are immutable. They do not change since they are recorded live and then archived. 


**Consequence.** The changed-source scenario is deleted. The spec now states
plainly that a Recording is identified by bucket and object key, and that the
same key always refers to the same audio.

**Q5 — Do you want webhook replay protection?** — **ANSWERED, dropped**
On a private tailnet, probably unnecessary. Defaults to yes in the spec; happy
to drop it.

> RESPONSE: That's fine. We just need to make sure that the handler is item potent so we don't ingest the same file twice. 


**Consequence.** Replay protection dropped. Idempotency is now the rule that
section is built around, including the concurrent-delivery and
webhook-races-the-scan cases.

**Q6 — How long should the reconciliation scan wait before touching a new object?** — **P2**
Only matters if the webhook can fire before the object is readable.

**Q7 — Should old recordings be back-processed?** — **ANSWERED**
Now more interesting than it was: you have an archive going back at least to
April, and Q15's ground-truth extraction will use it. Separately — do you want
the archive *processed*, or only used as test data?

> RESPONSE: Not needed except for testing. Everything in the old recordings list has already been edited and published. 


**Consequence.** The ingest cutoff stands, and manual ingestion is now
explicitly the mechanism for loading the sample corpus into the accuracy suite.

**Q8 — How many recordings arrive per week?** — **ANSWERED**
Band practice, sometimes a 9:00 TEC class, the 10:30 service, occasional
members meetings and special classes. Call it two to four recordings on a
typical Sunday. That is low enough that the concurrency limits in
`operations/job_queue.feature` are not a real constraint.

> RESPONSE: In general, it's just Sunday. Occasionally, there's a Saturday sermon. Once a month, there's the TEC class on a Sunday, which produces two products. 


**Consequence.** Sunday is the norm, with an occasional Saturday sermon and a
monthly class Sunday producing two products. So the day of the week is
**evidence, not a rule** — `block_classification.feature` treats "starts near
the usual service time" as a signal that raises confidence, and explicitly does
not exclude a Block from being a sermon because it fell on the wrong day. That
keeps the Saturday case working without special handling.

**Q9 — Can one service produce more than one file?** — **ANSWERED by Q60**
Yes, in both directions: one file can hold two sessions (TEC + service), and
one session can span two files (CT-Islam). See Q63 and Q65.

---

## Analysis

**Q13 — Which transcription engine?** — **DEFERRED** (was P0)
Parked with Q61. One note for when we pick it up: the 24 sample pairs let us
test whether transcription is needed at all, or whether time-of-day plus
speaker segmentation is enough. That test is worth running before paying for a
transcription pipeline.

**Q16 — Is there an order of service the Processor could read?** — **ANSWERED, and it was worth more than I expected**
Downgraded. Your answer supplied a strong deterministic signal already — the
service starts at 10:30 and the file is stamped around 10:29:52, TEC starts at
9:00. That is most of the value an order-of-service would have provided. Still
worth knowing if Planning Center or similar is in play, but no longer close to
blocking.

> RESPONSE: There is no consistent order of service within a given Sunday service. There is a very consistent order, but the other recordings might be anything, so we need to be able to operate in those as well. If it ends up being helpful, the Sunday service is pretty much always the same, and that is our primary use case.
I have outlined that mostly already in several other places, but I'll go ahead and outline it here.
> 1. A welcome and announcements, ending in a prayer that pitches to a musical worship time. There are usually three songs, and then another speaker comes up, almost always the same person who did the announcements. They pitch to a prayer time, and there will be some silence in there as they allow people to pray. They will end that time in a prayer.
> 2. Scripture reading for the sermon for that day. After the scripture is read, the preacher of the sermon will come up and start the sermon. That's the punch-in point.
> 3. They will speak for usually somewhere around an hour, 50 minutes to an hour. They will pray, and then transition to communion, which is usually only about five minutes or so.
> 4. They will pitch to one more worship song at the end of the service, and the final benediction happens. Usually it's the same person who did announcements and read scripture. Occasionally it's the person who did the sermon, but it can change. That last person will give a closing benediction and prayer, and that's the end of the service.
> That's very consistent from week to week, but the other services are very, very sporadic, and it depends on what they are. In general, on those, it's just all spoken, so the punch-in and out points are usually simpler because there's not a lot of other stuff going on.


**Consequence — the running order is now a scoring prior.** You said you had
outlined it elsewhere, but having the whole sequence written down in one place
is the single most useful thing in this document for the analysis half of the
system. It is now in `analysis/block_classification.feature` as an explicit
expected order, scored as *evidence* and never required — which respects your
Q70 instruction to stay generic, since the other recordings are sporadic and
would fail any rule that demanded this shape.

Three things it corrected outright:

- **I had the order wrong.** My examples ran `scripture_reading → prayer →
  sermon`. It is actually `prayer time (with the silence) → scripture_reading →
  sermon`. The prayer before the sermon belongs to the host's prayer time, not
  to the preacher. Fixed in `block_classification.feature` and
  `segment_proposal.feature`.
- **The recurring host voice is a signal I did not have.** The same person does
  the announcements, comes back before the prayer time, reads scripture and
  usually gives the benediction. A voice appearing in all of those is probably
  hosting, not preaching — evidence against typing their Block as the sermon.
  Kept as evidence only, since you noted the preacher occasionally gives the
  benediction.
- **The sporadic recordings are the easy case, not the hard one.** "It is just
  all spoken, so the punch-in and out points are usually simpler." I had assumed
  the opposite. There is now an explicit scenario asserting that a recording
  which does not match the Sunday shape loses no confidence for it.

One small discrepancy I resolved rather than asking about: your Q20 answer put
the 15-20 seconds of silence "at the beginning of the sermon", and this answer
puts the prayer time with silence before the scripture reading. It changes
nothing, because silence never splits a Block either way — but the spec now
tolerates a long silence in both places.

**Q10 — Do we need a music/speech classifier?** — **ANSWERED, and it grew**

Promoted. Under the Segment model this is not a refinement, it is how band
practice stops demanding a click every week: a Recording whose only Segment is
classified `music` is shown as needing no attention and sends no notification.
That behaviour is specified and depends on the classifier being real.
More valuable than it was. Band practice is a whole recording of music that
should be classified and set aside without a human listening to it, and under
the Q63 Segment model a classifier is how music Segments get filtered out.

> RESPONSE: I believe this could be very useful for making human decisions faster. Even if we don't automatically mark segments, giving a summary or a guess about what they are would be really helpful. It might even be helpful if we have the ability to identify a piece of that segment that's most likely going to be highly identifiable for the human. They can just hit a Preview button that will play just that little segment, or start the playback at a specific spot. That makes it really easy to identify that section.

> This is maybe not critical, but if we end up having to execute a local language model to do some of this, this might be something that's easy to add into the prompt. We could have that as well. 


**Consequence — this became its own feature.** You described three things:
summarise each segment, guess what it is, and pick a short excerpt that lets a
human recognise it instantly. That is `analysis/summarization.feature`.

Every spoken Block gets a one-line summary and a **cue excerpt** of 3-10 seconds
chosen to be recognisable rather than merely first. Preview plays the excerpt.
The reviewer can read the whole shape of a service without playing anything, and
confirm a Segment with a few seconds of audio.

One constraint I wrote in deliberately: **no summary can affect output.** A
wrong summary can mislead you, but it cannot produce a wrong file, because every
boundary and classification derives from the transcript, the speaker spans and
the block types. Summaries are a reading aid and nothing more.

**Q11 — Is the service ever in another language?** — **ANSWERED, closed**
Assumed English-only.

> RESPONSE: English-only

**Q12 — Is a known-voice library worth building?** — **ANSWERED, promoted**
Under the Q63 model this gets more useful, not less: if the Processor knows the
regular preacher's voice it can label which Segment is the sermon rather than
making you check. Is the preaching roster small and stable?

> RESPONSE: Yes, the roster is small. Almost all of them are by one person, with occasional other people mixed in. There are really only a maximum of three or four others who will preach. 


**Consequence — promoted, and cheaper than I thought.** A roster of one primary
plus three or four others is small enough that a voice library is genuinely
maintainable. It is now the strongest single signal for finding the teaching
Block.

I added one thing you did not ask for: profiles can be **enrolled from approved
Segments**, so the library builds itself out of ordinary use rather than
requiring a separate enrolment session. And an unknown voice is explicitly *not*
evidence against teaching — guests are normal.

**Q14 — What happens when Analysis is re-run after a human has edited the boundaries?** — **ANSWERED**
Unchanged. Spec preserves the human edit.

> RESPONSE: Yes, I wouldn't want a processor to lose any human input, but a human could choose to discard edits that they have made. 

**Q17 — How precisely does a reviewer need to place a boundary?** — **ANSWERED**
Spec assumes 100 ms.

> RESPONSE: Yes, 100ms is a good guess. Generally, we need to make sure the edit is far away from any noise. By far away, I mean probably even 250 ms. That way, the transition sounds natural.

> We should avoid starting the recording with any clicks, ums, or other vocal anomalies. Our primary teacher usually starts the message with "good morning," and that's usually a good cut point. I usually punch in right before that. Sometimes, when it's unnatural for one reason or another, I might cut that out and move a little bit ahead of it.

> This is not something the engine needs to be able to do automatically, but it's something a human might choose to do. We need to make it easy to move that punch-in point around. As much as we can, provide waveform visualization that is easy to click or drag to move the punch-in point. If we could even include the words next to the waveform somehow in the visualization, that'd be amazing. That would be nice to have. 


**Consequence.** Three things went into the spec. The 250 ms clearance is now a
rule in both refinement stages and a warning in the editor when you drag closer
than that. "Good morning" is a recognised opening with its own scenario. And the
transcript words are drawn aligned to the waveform when zoomed, so you can see
exactly which word a boundary falls before — you called that a nice-to-have, but
it is cheap next to everything else on that screen and it makes the 250 ms rule
legible instead of magic.

**Q18 — How much lead-in and tail do you want around the sermon?** — **ANSWERED**
Currently up to 1.0 s before the first word and 1.5 s after the last. The Q15
ground-truth extraction will show what you actually do by hand, which may
answer this without you having to think about it.

> RESPOSNE: This feels about right. Lead-in at the beginning of the segment is not super important. One second is perfect. If it's too much more than that, people might wonder if the playback is working, and you don't hear something within the first second. One second is probably the maximum. At the end, the punch-out silence lead-out is really much less important. If it cuts immediately after the last word, I don't think anyone is going to notice. 


**Consequence.** Lead-in capped at 1.0 second, tail capped at 0.5 seconds. I had
guessed 1.5 seconds of tail; your answer says shorter is fine and nobody will
notice an immediate cut, so the asymmetry is now explicit in
`punch_out_detection.feature`.

**Q19 — Is the closing prayer part of the sermon?** — **ANSWERED**
Same — measurable from the samples.

> RESPONSE: Yes, the closing prayer at the end of the sermon is part of the sermon. Right after that is the pitch to communion. We cut after the amen of the prayer and before the pitch to communion. 


**Consequence.** This is now structural rather than a text rule: the Segment is
the teaching Block plus its immediately-following prayer Block, and it stops
before the next Block whatever that is. The "amen" is a cue for classifying the
Block as prayer, not a rule for placing the cut.

**Q20 — Is an altar call or response time part of the sermon?** — **ANSWERED, closed**
May not even happen at your church.

> RESPONSE: No, never. There is a time of prayer at the beginning of the sermon, usually where there might be 15 to 20 seconds of silence while the preacher is giving time for people to pray, but this doesn't need any special handling. 

**Q21 — What is a plausible sermon length?** — **MEASURED**
From the 24 pairs, output durations are:

| Content | Range | Typical |
| --- | --- | --- |
| Sermons (20 files) | 40 – 61 min | ~50 min |
| TEC classes (3 files) | 55 – 68 min | ~59 min |
| Members meeting (1 file) | 60 min, untrimmed | — |

Source recordings run 79 – 155 minutes, so the sermon is roughly 45–60% of the
file. I will change the warning band from the assumed 15–75 to **30–75 minutes**
unless you object. Note this is a *warning* threshold, not a rejection.

> RESPONSE: This looks correct.

**Q22 — Do you want confidence calibration?** — **ANSWERED, replaced**
Nice to have. With one reviewer and one sermon a week it will take a year to
gather meaningful data.

> RESPONSE: I don't think this is necessary. I think, given the local data that we have that have already pointed you to, we should be able to construct a pretty decent practical behavior test with actual files and see that the output is close enough to what was done by a human. 


**Consequence — replaced with a real test.** You are right that calibration was
the weaker idea. `analysis/detection_accuracy.feature` now specifies deriving
ground truth from the 24 FLAC/MP3 pairs by aligning each MP3 within its FLAC,
then reporting per-pair and aggregate punch-in/punch-out error against what you
did by hand.

The nice property: every week of ordinary use adds another labelled pair for
free, because an approved Segment *is* a human-verified answer. The corpus grows
without anyone labelling anything.

This raised Q75 — what error counts as good enough.

---

## Interface

**Q23 — Do you want the list to update live?** — **P3**
Two to four recordings a week, one reviewer. A refresh button is fine.

**Q24 — What do you need to search?** — **P3**
Date filtering is enough for now. Transcript search stays a later luxury.

**Q25 — Will you review on a phone or at a desk?** — **ANSWERED**
Still worth an answer, because it decides how much effort the waveform
interface needs. Under Q63 you may be auditioning several Segments per
recording, which is more comfortable at a desk.


**Consequence — a clean split.** `interface/segment_review.feature` now has a
mobile rule: on a phone you can read the summary, preview both boundaries and
approve, and the whole flow works without a waveform. That is exactly the
three-click path from Q75, which is a nice coincidence — the ordinary week is
the mobile-shaped week.

A Segment whose cut is graded "hard" tells you on mobile that it needs an
adjustment better made at a desk, and offers to skip rather than presenting a
cramped editing surface. Zooming, word alignment and nudge controls are desktop
only. Downloads work everywhere.

**Q26 — Is a stitched cut preview useful?** — **P2, now load-bearing**

Your own words in Q63: "It should be easy to sample that punch-in/punch-out, so
a person could tell where this is." That is this feature, and it is now how you
tell one Segment from another. Specified in `interface/segment_review.feature`.
More useful under the Q63 model, where you are sampling several candidate
Segments to work out which is the sermon. Your own words: "It should be easy to
sample that punch-in/punch-out, so a person could tell where this is." That is
exactly this feature, so I have promoted it in spirit even though it stays P2.

**Q27 — Should the Processor transcode a low-bitrate preview for streaming?** — **ANSWERED, and it grew**

Promoted. Sources are up to 1.4 GB of 24-bit stereo FLAC, and reviewing a
multi-segment recording now means sampling several points across three hours of
audio. Streaming the source directly is not viable.
Streaming a 1 GB 24-bit stereo FLAC to a browser for review is heavy. This
looks more necessary now that I know the real file sizes.

> RESPONSE: This is probably a good idea. If we can make it segmentable, allowing the player in the browser to jump to certain points and only download segments of the file relevant to where they're scrubbed, that would make the response time much faster in the browser. That would be ideal. If there's a format that makes the most sense for that and makes streaming in the browser more capable, then we should explore that as long as it's not overly complicated. Something like that would also allow us to have a higher bit rate without sacrificing response time. 


**Consequence — this became its own feature.** You asked for something better
than "a smaller file": a rendition the browser can seek into without downloading
what comes before. That is `analysis/preview_audio.feature`.

The preview is generated during Analysis, so it exists before anything is
approved. Seeking to 2:14:00 in a three-hour recording fetches only the audio
around that point and starts playing within two seconds. Previewing a cue
excerpt or auditioning a boundary fetches only those few seconds.

Your observation that seekability buys quality back is written in as a scenario
— because playback only ever fetches a region, the preview can use a higher
bitrate than a whole-file download would tolerate.

Two guardrails I added: the preview is never offered as a download, and the
published MP3 is always rendered from the source FLAC and never from the
preview. It would be an easy and invisible mistake to make later.

The exact mechanism is left open as Q77, since "segmented streaming" and
"constant-bitrate with byte-range seeking" both satisfy the spec and your
constraint was that it not be overly complicated.

**Q28 — Can two people review at the same time?** — **P3**
You appear to be the only reviewer. I will drop the conflict-handling scenario
from `punch_point_adjustment.feature` unless you say otherwise.

**Q29 — Is any metadata required before approval?** — **P2**
Reframed by the filename evidence — see Q31 and Q33. The only thing you appear
to need is the scripture reference, because it is in every filename.

**Q30 — Do you want to be able to cancel processing?** — **P3**
Re-cutting afterwards is almost certainly good enough.

**Q31 — Which sermon metadata fields do you need?** — **RESOLVED IN SPEC**

Closed by Q58 plus the filename evidence. `interface/sermon_metadata.feature`
has been replaced by `interface/publication_details.feature`, which collects a
date and a label and nothing else. Reopen this only if you want more.
Heavily downgraded by Q58 and by the filenames. Your actual workflow records
exactly two things: the **date** and the **scripture reference**. No title, no
speaker, no series, no description anywhere in `~/Desktop/Sermons`. I will
reduce the metadata scenarios to date plus a free-text label that defaults to
the scripture reference, unless you tell me you want more.

**Q32 — Confirm the ID3 tag mapping.** — **RESOLVED IN SPEC**

With no podcast host in scope, the spec writes title and date and stops. There
is an explicit scenario asserting nothing more is collected, so this is easy to
reverse if it turns out your player wants tags.
With no podcast host in scope, this is probably not worth doing at all. Do your
current MP3s even carry tags? If your workflow never needed them, the render
can skip tagging entirely.

**Q33 — What should the output file be called?** — **MEASURED**
Your convention is `YYYY-MM-DD - <Label>.mp3`:

```
2026-08-23 - Hebrews 12.4-11.mp3
2026-07-05 - TEC.mp3
2026-06-28 - Members Meeting.mp3
2026-07-18 - CT-Islam.mp3
```

Date, space-hyphen-space, then a human label — usually the scripture reference,
otherwise the name of the thing. I will change
`interface/sermon_metadata.feature` from the slug I invented
(`2026-08-23-the-freedom-of-no-condemnation.mp3`) to match yours. Confirm the
label should default to the scripture reference for sermons.

**Q34 — When a recording is discarded, should its local files be freed?** — **ANSWERED via Q53**


**Answered by Q53.** With 26 TB available, discarding frees nothing because
nothing needs freeing. Local files follow the same "keep it" policy as
everything else.

**Q35 — Do you ever want a hard delete?** — **P3**

**Q36 — Should very short recordings skip analysis?** — **ANSWERED, and it changed shape**
Related to band practice, though practice is long, not short — so this is
really Q10's classifier problem rather than a duration threshold.

> Response: There are likely going to be recordings where a single noise, like a pop from somebody turning the system on or off, might trigger a recording that's 10 minutes long or something. The timeouts are set on the audio recorder, but the substance of the recording will just be a single noise and almost entirely silence. If we can easily classify those and mark them as ignored, that would be good. 


**Consequence — it stopped being about duration.** Your example is the useful
part: a pop from someone switching the system on produces a *ten minute* file
that is almost entirely silence. Duration was never the signal, because the
recorder's silence timeout sets the length. Content is.

`analysis/audio_probe.feature` now tests what proportion of a Recording sits
above the noise floor, flags "no substantive content", stops Analysis after the
probe and marks the Recording ignored **without asking anyone**. Ignored
recordings stay out of the list, raise no notification, and can be found and
restored if the machine got it wrong.

I deliberately set the threshold to err toward analysing: a quiet-but-real
recording with long pauses is analysed normally. Being wrong in that direction
costs a little local compute, which is now free (Q76). Being wrong the other way
loses a recording silently.

The threshold itself is a guess — see Q78. Your sample corpus has no false
triggers in it, so there is nothing to calibrate against yet.

**Q37 — Is there a service time window?** — **ANSWERED via Q8**

The 10:30 service, a 9:00 class monthly, an occasional Saturday sermon. Handled
as evidence rather than as a rule, so the Saturday case needs no special
treatment — see the consequence note under Q8.
The service starts at 10:30 and the file is stamped around 10:29:52. TEC starts
at 9:00. This is now one of the strongest signals in the system: a recording
that starts at 10:29:5x is the service, full stop.

Remaining follow-up: what are the boundaries of the *other* windows? When does
band practice typically start and end? Are members meetings and special classes
predictable at all, or genuinely ad hoc? And is the 10:30 start ever different
— Christmas, Easter, a fifth Sunday?

**Q38 — Is the Processor on a private network or the public internet?** — **DEFERRED**
Parked with Q61.

**Q39 — How many people review, and who are they?** — **P3**
Appears to be you alone.

**Q40 — Do you need a reviewer/admin role distinction?** — **P3**
Almost certainly not.

**Q41 — Do you want shareable download links?** — **P3**
Downgraded by Q58.

---

## Notifications

**Q42 — Which channel?** — **ANSWERED, deferred deliberately**
Still genuinely unanswered and still in the README's flow. With one reviewer
this is a small question — email is the obvious default — but I do not want to
guess. Email, push, SMS, Slack, Discord?

> RESPONSE: I don't think this is a blocking question because I think the medium we choose here is dependent on technology choices. For instance, if we use a web app for this and use a PWA, we can just use push notifications in the PWA. If we do something else, we could always do Slack or email through Amazon SES, or something like that. The fundamental piece is still a notification object that's going to track the actual notification, so I feel like which channel we use is largely irrelevant at this point in the conversation. We can figure this out later. 


**Consequence — you are right, and the spec now says so.** The Notification is
modelled as a record — subject, kind, recipient, summary, state — created
whether or not any channel is configured, and delivery is a separate concern
that can be plugged in later.

This has a practical payoff beyond deferring the decision: **the system is
usable before the channel question is answered.** Notifications are recorded and
visible in the interface from day one, and adding a channel later changes
nothing about when they are raised.

I added one thing you did not ask for. When a Recording produces nothing
publishable, a Notification is still recorded, with state `suppressed`. It costs
nothing and makes "why was I not told about that Sunday?" answerable without
reading logs.

**Q43 — Who gets notified?** — **P2**
Presumably you.

**Q44 — "Processing finished" notification, or only "ready to review"?** — **P3**

**Q45 — Batch or one per recording?** — **P2**
More relevant than it was: two to four recordings can land within minutes of
each other on a Sunday, and under Q63 one recording can yield several Segments.
Batching is probably right.

**Q46 — Do you want a reminder for recordings left unapproved?** — **P2**
The file dates in `~/Desktop/Sermons` suggest this would help. Several MP3s
were created a week or more after the FLAC: `2026-05-31` recorded 31 May,
exported 10 June; `2026-06-21` recorded 21 June, exported 23 June. If sermons
sometimes sit for ten days, a nudge has real value.

---

## Processing

**Q47 — Fades at the cut points?** — **P2**
Assumed yes, a few milliseconds.

**Q48 — Peak normalization or loudness normalization?** — **ANSWERED**

I measured this rather than asking you to recall it. Your finished MP3s:

| Recording | Integrated | True peak | LRA |
| --- | --- | --- | --- |
| 2026-08-23 - Hebrews 12.4-11 | **-20.8 LUFS** | -1.0 dBFS | 14.6 LU |
| 2026-04-12 - John 18.1-12 | **-23.9 LUFS** | -1.2 dBFS | 12.1 LU |
| 2026-06-07 - Hebrews 11.1-3 | **-26.0 LUFS** | -1.2 dBFS | 13.9 LU |
| 2026-05-24 - Romans 6.1-4 | **-29.9 LUFS** | -1.8 dBFS | 13.6 LU |

The peaks confirm peak normalization to roughly -1 dBFS, which is Audacity's
default. But look at the integrated loudness: a **9.1 LU spread** across four
weeks. That is a large, audible difference — a listener who set the volume for
2026-08-23 would find 2026-05-24 close to inaudible in a car.

Now the source files:

| Recording | Source integrated | Output integrated |
| --- | --- | --- |
| 2026-08-23 | -19.1 LUFS | -20.8 LUFS |
| 2026-05-24 | -20.3 LUFS | -29.9 LUFS |

The sources are **1.2 LU apart**. The outputs are **9.1 LU apart**. The current
process is not failing to fix an inconsistency — it is *introducing* one. That
is what peak normalization does: it keys off a single loudest sample, so one
cough, dropped mic or slammed door anywhere in the sermon drags the entire file
down. 2026-05-24 almost certainly has one.

My recommendation is loudness normalization to **-16 LUFS with a -1.5 dBTP
ceiling**. It would make every week sit at the same subjective volume and would
bring your quiet weeks up by 10 dB or more. I would like a yes before I write
it into the spec, because it will make new files noticeably louder than your
back catalogue.

> RESPONSE: I am great with improving the quality here by having a consistent output product with new metrics. The current solution is just a naive "click the normalize button in Audacity" which clearly does not always work well.


**Consequence — settled.** `-16 LUFS` integrated with a `-1.5 dBTP` ceiling.
The `@needs-decision` tag is gone from `audio_rendering.feature`.

One scenario I added on the back of this: the first Segment rendered under the
new target tells the reviewer that output volume has changed relative to earlier
files, and offers to re-render past Segments to match. Your back catalogue sits
between -20.8 and -29.9 LUFS, so new files will be noticeably louder than
everything published before. Worth knowing before someone asks why.

**Q49 — What is the compression actually fixing?** — **ANSWERED, and it collapsed two steps into one**

Your outputs measure **12–15 LU** of loudness range. Spoken-word podcasts
typically land around 7–9 LU. So the finished files still have a wide dynamic
range — the quiet passages really are much quieter than the loud ones, and
whatever compression you are applying is not doing much.

Combined with Q48, I think the answer to "is the compress step necessary" is:
**not in the form you are using it.** Loudness normalization plus a limiter
would do more for consistency than the compressor is currently doing, and would
fix the week-to-week problem the compressor cannot touch.

The one thing I cannot measure is intent. Does the preacher step away from the
mic and go quiet mid-sermon? If yes, gentle compression before the loudness
stage is genuinely worth having. If your worry was only that peaks felt too
hot, normalization plus a limiter replaces both steps and the compressor can
go.

> RESPONSE: At certain points in the past, when we had quiet recordings, the compression seemed to bring up some of the quieter parts. I'm not sure that this is really helpful with the normalized feature. If I think we could consider this as all part of the same operation, we don't need to separate normalize and compress. I think the previous question is talking about whether we handle volume normalization, which is effectively handling what this was doing. 


**Consequence — two steps became one.** You are right that this is the same
concern as Q48, and the spec now reflects that: there is a single loudness stage
that measures, corrects and limits in one pass. The separate "compression
enabled / disabled" toggle is gone.

Your observation about compression bringing up quiet parts is also explained
rather than dismissed. Loudness normalization measures the whole programme
rather than its loudest sample, which is the mechanism that actually raises a
quiet passage — so it does the thing you were reaching for the compressor to do,
and does it more consistently. There is a scenario asserting exactly that.

**Q50 — Confirm MP3 encoding settings.** — **ANSWERED**
Every sermon MP3 in the folder is **mono, 44.1 kHz, VBR averaging 96–108 kbps**.
The members meeting is the one exception at 128 kbps. My guessed spec of 96 kbps
mono 44.1 kHz was close enough; I will change it to VBR targeting ~100 kbps to
match what you already ship. See Q68 on the 128 kbps outlier.

> RESPONSE: Yes, you can see what the files are by measuring them. I'm open to other options if there is a better spoken-word option, but this quality seems to have been totally fine, and the output file size is reasonable. I don't notice any quality difference between the lossless and the MP3, but I'm open to suggestions on other options or conformance to industry standards on spoken word. 


**Consequence — keeping what you have.** Mono, 44.1 kHz, VBR averaging ~100
kbps is a perfectly sane spoken-word setting, comfortably above where mono
speech starts to audibly degrade, and it matches the files you already ship.

For the record, since you asked about industry standards: the one option worth
considering later is dropping to 64 kbps mono, which is common for talk-format
podcasts and would cut file size by roughly a third — a 43-minute sermon would
land around 20 MB instead of 32 MB. Given the homelab has 26 TB and nobody is
paying for bandwidth, that saving buys you nothing right now. I would leave it
alone. Encoding settings are configuration rather than code, so changing your
mind later is a re-render, not a rewrite.

**Q51 — Which artifacts should be downloadable?** — **ANSWERED**
MP3 and original FLAC are confirmed by the README. A plain-text transcript is
the interesting extra — but only if we are transcribing at all, which is now
tied up with Q13.

> RESPONSE: If we end up transcribing the whole segment, I think allowing that to be downloaded and also viewed in the user interface is worth the little bit of time it'll take to wire those up. 


**Consequence.** Both a plain-text and a timecoded transcript are downloadable,
and the transcript is readable in the interface scoped to the approved span,
expandable to the whole Recording. This was already half-built by the review
interface, so it was cheap.

**Q52 — Should previous renders be kept when a recording is re-cut?** — **ANSWERED**

> RESPONSE: This is probably not necessary. I think if we keep all of the metadata that's necessary for regenerating the previous render, then it's just a derivative product that takes up space, so we can remove them. If the user needs to regenerate it, they could either do it, or we would have the information to be able to add that feature later if necessary. 


**Consequence.** Only the current MP3 is stored; a superseded render is deleted.
The boundaries, loudness settings and encoding settings for every past render
are retained, so any of them could be reproduced.

I wrote in one scenario stating that reproducing a past render is deliberately
*not* offered as a feature — the information is kept so that adding it later is
possible, but nothing builds the UI for it now.

---

## Operations

**Q53 — What machine does this run on, and how much disk?** — **ANSWERED**
Parked with Q61. One data point for later: the sample folder is **46 GB for
five months**, and that is only the material you kept. Sources run 300 MB to
1.4 GB each. Storage is not a trivial concern.

> RESPONSE: Runs on a home lab with roughly 26 TB of storage. Storage is not going to be a concern. We'll have an S3-compatible bucket stored on the same array that we'll place long-lived files in, but we'll have scratch space well beyond anything we need for running operations. 


**Consequence — the retention feature got much simpler.** 26 TB against roughly
110 GB a year means storage is genuinely not a constraint, so
`operations/storage_and_retention.feature` was rewritten around keeping things
rather than pruning them. Nothing is removed on a schedule.

The one distinction that survives is **long-lived storage versus scratch**:
sources, MP3s and analysis artifacts go to the array; only what a running job
needs goes to scratch, and scratch is reclaimed when the job finishes. Both are
still monitored, with a threshold that should not fire this decade — it exists
so that if something goes wrong it is visible rather than silent.

This also answers Q34: discarding a Recording frees nothing, because nothing
needs freeing.

**Q54 — How long should recordings stay available from this system?** — **ANSWERED**

> RESPONSE: Indefinitely for now.


**Consequence.** Indefinite retention, which combined with Q53 and Q71 means the
whole retention policy is "keep it". Simple to build and simple to reason about.

**Q55 — Keep transcripts and waveforms indefinitely?** — **ANSWERED**
They are small. Assumed yes.

> RESPONSE: Yes

**Q56 — What is the recorder's retention window?** — **ANSWERED via Q71**

Nothing prunes the bucket; sources are kept indefinitely. This was the risk I
flagged as the most important thing in the last pass, and it turns out not to be
a risk at all.
Promoted. Now that I know sources are up to 1.4 GB and you sometimes take ten
days to get to a sermon, this matters: if the object store drops files before
you have approved them, the Processor loses the source. What is the actual
retention on `s3.home.tpett.me`?

**Q57 — Do you want an alert when no recording arrives?** — **ANSWERED, dropped**
Still cheap insurance against the worst failure mode.

> RESPONSE: Not necessary


**Consequence.** No alert. The health view still shows how long it has been
since the last ingest, so a glance answers the question, but nothing fires and
nobody is notified. I had argued for this one; your call, and it is the cheaper
behaviour.

---

## Scope boundaries

**Q59 — Is there video?** — **ANSWERED, closed**
Downgraded by Q58.

> RESPONSE: As of today, no.

**Q62 — Does anything else need to consume this data?** — **ANSWERED, closed**
Downgraded by Q58.

> RESPONSE: Not today
