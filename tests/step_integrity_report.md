# Step integrity

Regenerate with `.venv/bin/python tests/step_integrity.py`. Hand edits are lost.

## What the guard found

- 1261 step definitions read from `tests/steps`
- 0 condemned
- 0 of 462 non-deferred scenarios rest on at least one condemned step
- 0 of 603 expanded scenario tests likewise
- 0 scenarios whose every Then is condemned, so nothing they claim is checked
- 0 scenarios whose every step outside the Background is condemned
- 0 scenarios whose every step, Background included, is condemned
- 48 Gherkin steps matched more than one definition
- 389 Gherkin steps matched no definition

## Faults by kind

| fault | count |
| --- | --- |
| a Then with an empty body | 0 |
| a Then whose body never asserts | 0 |
| an interface Then that reads the view model rather than the rendered page | 0 |
| an assertion that cannot fail | 0 |
| a boolean operand of True, which neutralises what it joins | 0 |
| a When with an empty body | 0 |
| a When whose body never acts | 0 |
| an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate | 0 |
| a step that skips or xfails instead of running | 0 |
| a step name the guard cannot read from the source | 0 |
| a step decorator that declares no Given, When or Then | 0 |

## Modules

| module | definitions | condemned | verdict |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py` | 61 | 0 | sound |
| `tests/steps/analysis/audio_probe_steps.py` | 45 | 0 | sound |
| `tests/steps/analysis/domain_steps.py` | 208 | 0 | sound |
| `tests/steps/analysis/preview_audio_steps.py` | 31 | 0 | sound |
| `tests/steps/analysis/remaining_analysis_steps.py` | 198 | 0 | sound |
| `tests/steps/analysis/waveform_generation_steps.py` | 14 | 0 | sound |
| `tests/steps/catch_all_thens.py` (named) | 3 | 0 | sound |
| `tests/steps/discovery_steps.py` | 2 | 0 | sound |
| `tests/steps/ingestion/recording_download_steps.py` | 42 | 0 | sound |
| `tests/steps/ingestion/s3_reconciliation_steps.py` | 37 | 0 | sound |
| `tests/steps/ingestion/webhook_notification_steps.py` | 34 | 0 | sound |
| `tests/steps/interface/approval_steps.py` | 48 | 0 | sound |
| `tests/steps/interface/authentication_steps.py` | 8 | 0 | sound |
| `tests/steps/interface/cut_light_steps.py` | 4 | 0 | sound |
| `tests/steps/interface/discarding_steps.py` | 20 | 0 | sound |
| `tests/steps/interface/playback_steps.py` | 10 | 0 | sound |
| `tests/steps/interface/publication_details_steps.py` | 10 | 0 | sound |
| `tests/steps/interface/punch_nudge_steps.py` | 17 | 0 | sound |
| `tests/steps/interface/punch_point_adjustment_steps.py` | 39 | 0 | sound |
| `tests/steps/interface/recording_detail_steps.py` | 25 | 0 | sound |
| `tests/steps/interface/recording_list_steps.py` | 36 | 0 | sound |
| `tests/steps/interface/segment_review_steps.py` | 37 | 0 | sound |
| `tests/steps/interface/waveform_steps.py` | 88 | 0 | sound |
| `tests/steps/last_fourteen.py` (named) | 10 | 0 | sound |
| `tests/steps/nested/discovery_steps.py` | 1 | 0 | sound |
| `tests/steps/notifications/analysis_notification_steps.py` | 23 | 0 | sound |
| `tests/steps/notifications/notification_steps.py` | 8 | 0 | sound |
| `tests/steps/operations/health_steps.py` | 17 | 0 | sound |
| `tests/steps/operations/job_queue_steps.py` | 14 | 0 | sound |
| `tests/steps/processing/artifact_downloads_steps.py` | 26 | 0 | sound |
| `tests/steps/processing/processing_orchestration_steps.py` | 15 | 0 | sound |
| `tests/steps/remaining_steps.py` (named) | 130 | 0 | sound |

## Condemned outside the six named files

0 definitions.

| location | kind | step | faults |
| --- | --- | --- | --- |

## Every condemned definition

| location | kind | step | faults |
| --- | --- | --- | --- |

## Scenarios whose every Then is condemned

| feature | line | scenario |
| --- | --- | --- |

## Gherkin steps the guard could not match

- `analysis/analysis_confidence.feature:138 then exactly one analysis informs the Proposal`
- `analysis/analysis_confidence.feature:139 then confidence is computed from these inputs only:`
- `analysis/analysis_confidence.feature:147 then no agreement badge is shown`
- `analysis/analysis_confidence.feature:156 then cut difficulty remains the signal that asks for a listen`
- `analysis/analysis_confidence.feature:183 then the affected confidence is reduced`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "block types" was unavailable`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "closing prayer" was unavailable`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "communion cue" was unavailable`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "recording start time" was unavailable`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "scripture reading" was unavailable`
- `analysis/analysis_confidence.feature:184 then the evidence list states that "speaker spans" was unavailable`
- `analysis/analysis_confidence.feature:219 then it is never treated as evidence that the output is correct`
- `analysis/analysis_confidence.feature:220 then correctness is established by the accuracy suite instead`
- `analysis/analysis_confidence.feature:65 then a self-reported confidence may be stored for diagnosis`
- `analysis/analysis_confidence.feature:66 then it is never shown to a reviewer as a quality signal`
- `analysis/analysis_orchestration.feature:109 then they can be revisited and approved months later`
- `analysis/analysis_orchestration.feature:163 then the stage is retried`
- `analysis/audio_probe.feature:122 then a reviewer can restore it for analysis if the machine was wrong`
- `analysis/block_classification.feature:154 then that shape counts as evidence for "qa"`
- `analysis/block_classification.feature:165 then the evidence includes "sustained single-speaker teaching"`
- `analysis/block_classification.feature:166 then the evidence includes "follows a scripture reading"`
- `analysis/block_classification.feature:173 then the confidence that the Block is teaching is increased`
- `analysis/block_classification.feature:174 then the evidence names the matched speaker`
- `analysis/block_classification.feature:21 then a Block may be typed "announcements" meaning "welcome, notices, housekeeping"`
- `analysis/block_classification.feature:21 then a Block may be typed "communion" meaning "the invitation to and serving of communion"`
- `analysis/block_classification.feature:21 then a Block may be typed "lesson" meaning "a class session: teaching, usually followed by questions"`
- `analysis/block_classification.feature:21 then a Block may be typed "music" meaning "congregational singing or instrumental"`
- `analysis/block_classification.feature:21 then a Block may be typed "other" meaning "speech that is none of the above"`
- `analysis/block_classification.feature:21 then a Block may be typed "prayer" meaning "someone praying aloud; may contain long silence"`
- `analysis/block_classification.feature:21 then a Block may be typed "qa" meaning "audience questions; short alternating turns"`
- `analysis/block_classification.feature:21 then a Block may be typed "rehearsal" meaning "playing, stopping, restarting — a run-through, not a performance"`
- `analysis/block_classification.feature:21 then a Block may be typed "scripture_reading" meaning "a passage being read, usually announced by reference"`
- `analysis/block_classification.feature:21 then a Block may be typed "seminar" meaning "a session of a multi-part course"`
- `analysis/block_classification.feature:21 then a Block may be typed "sermon" meaning "the Sunday message"`
- `analysis/block_classification.feature:217 then each Block gains confidence from its position in the order`
- `analysis/block_classification.feature:227 then it is classified on its own evidence`
- `analysis/block_classification.feature:237 then that following Block is strong evidence for "sermon"`
- `analysis/block_classification.feature:238 then the punch-in falls at the start of it`
- `analysis/block_classification.feature:248 then the silence does not create a Block boundary`
- `analysis/block_classification.feature:280 then that counts as evidence for "rehearsal"`
- `analysis/block_classification.feature:303 then its teaching Blocks are typed "other"`
- `analysis/block_classification.feature:303 then its teaching Blocks are typed "rehearsal"`
- `analysis/block_classification.feature:303 then its teaching Blocks are typed "seminar"`
- `analysis/block_classification.feature:303 then its teaching Blocks are typed "sermon"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "a Good Friday service" rather than as "other"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "a Saturday worship and prayer gathering" rather than as "other"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "a members' meeting" rather than as "other"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "a seminar day with several sessions" rather than as "other"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "an ordinary Sunday" rather than as "other"`
- `analysis/block_classification.feature:304 then the Recording is summarised as "band practice, start to finish" rather than as "other"`
- `analysis/block_classification.feature:318 then a Segment is proposed for each sustained teaching Block`
- `analysis/block_classification.feature:319 then the reviewer decides what to publish, as with any other Recording`
- `analysis/block_classification.feature:330 then each is reviewed on its own`
- `analysis/block_classification.feature:331 then the interface shows them grouped by day`
- `analysis/block_classification.feature:332 then the reviewer is told they may be parts of one event`
- `analysis/block_classification.feature:341 then Segment proposal runs again for the affected Blocks`
- `analysis/block_classification.feature:342 then any boundary the reviewer set by hand is preserved`
- `analysis/block_classification.feature:363 then it is flagged as needing the reviewer to look at it`
- `analysis/block_classification.feature:364 then the evidence states which corroboration was missing`
- `analysis/block_classification.feature:373 then a Segment is still seeded on it`
- `analysis/block_classification.feature:380 then the Block is flagged as possibly containing more than one type`
- `analysis/block_classification.feature:74 given a Recording containing a normal Sunday service`
- `analysis/block_classification.feature:90 then each carries the evidence that produced it`
- `analysis/detection_accuracy.feature:109 then for each pair it reports:`
- `analysis/detection_accuracy.feature:117 then it reports the proportion approved with no edit`
- `analysis/detection_accuracy.feature:118 then it reports the median and worst-case error, split by difficulty`
- `analysis/detection_accuracy.feature:122 then the corpus includes sermons and class sessions`
- `analysis/detection_accuracy.feature:123 then accuracy is reported separately for each classification`
- `analysis/detection_accuracy.feature:135 then the headline measure is the proportion of Segments approved with no boundary edit`
- `analysis/detection_accuracy.feature:136 then it is reported alongside the raw error figures, not replaced by them`
- `analysis/detection_accuracy.feature:156 then the suite is a regression instrument, not an acceptance test`
- `analysis/detection_accuracy.feature:157 then a change that worsens the error distribution is reported as a regression`
- `analysis/detection_accuracy.feature:158 then no configuration is rejected for missing a fixed tolerance`
- `analysis/detection_accuracy.feature:159 then the reviewer's correction, not the tolerance, is what guarantees the cut`
- `analysis/detection_accuracy.feature:183 then punch-in error is reported with its sign, never as an absolute value`
- `analysis/detection_accuracy.feature:184 then late punch-ins are reported separately from early ones`
- `analysis/detection_accuracy.feature:192 then the punch-in error is weighted more heavily in the headline score`
- `analysis/detection_accuracy.feature:193 then both are still reported separately`
- `analysis/detection_accuracy.feature:201 then each pair is graded against the difficulty of its own transition`
- `analysis/detection_accuracy.feature:202 then results are reported separately for easy and hard cuts`
- `analysis/detection_accuracy.feature:203 then a poor result on a hard cut is not treated the same as one on an easy cut`
- `analysis/detection_accuracy.feature:223 then each boundary's difficulty comes from the audio around the human cut`
- `analysis/detection_accuracy.feature:224 then a configuration cannot change the difficulty of anything it is scored on`
- `analysis/detection_accuracy.feature:229 then the suite does not require the machine to match the human exactly`
- `analysis/detection_accuracy.feature:230 then it requires that the Segment was flagged as needing attention`
- `analysis/detection_accuracy.feature:239 then the result is graded as needing correction`
- `analysis/detection_accuracy.feature:240 then it does not count toward the no-edit proportion`
- `analysis/detection_accuracy.feature:248 then the change in median and worst-case error is reported`
- `analysis/detection_accuracy.feature:249 then a change that improves the median but worsens the worst case is visible as such`
- `analysis/detection_accuracy.feature:254 then that recording and the approved boundaries can be added to the corpus`
- `analysis/detection_accuracy.feature:255 then the corpus grows without anyone hand-labelling anything`
- `analysis/detection_accuracy.feature:265 then it counts toward the proportion approved with no edit`
- `analysis/detection_accuracy.feature:266 then it does not become a labelled example`
- `analysis/detection_accuracy.feature:272 then it reports that it was skipped`
- `analysis/detection_accuracy.feature:273 then it does not report a pass`
- `analysis/detection_accuracy.feature:81 then a legitimate untrimmed archive is flagged the same way`
- `analysis/punch_in_detection.feature:107 then the punch-in is placed immediately before "good morning"`
- `analysis/punch_in_detection.feature:114 then the punch-in is placed immediately before that phrase`
- `analysis/punch_in_detection.feature:115 then that counts as evidence for the punch-in`
- `analysis/punch_in_detection.feature:130 then the punch-in is still placed before the first words`
- `analysis/punch_in_detection.feature:140 then the punch-in is moved to the nearest preceding silence`
- `analysis/punch_in_detection.feature:44 then the punch-in is placed at least 250 ms away from the nearest audible sound`
- `analysis/punch_in_detection.feature:45 then the resulting transition sounds natural rather than abrupt`
- `analysis/punch_in_detection.feature:60 then the reviewer can move it in steps as small as 100 ms`
- `analysis/punch_in_detection.feature:73 then the grade is shown to the reviewer`
- `analysis/punch_in_detection.feature:95 then no flag is raised`
- `analysis/punch_in_detection.feature:96 then the reviewer is expected to confirm it with a single preview`
- `analysis/punch_out_detection.feature:107 then the punch-out is moved to after the word ends`
- `analysis/punch_out_detection.feature:108 then the final word is complete in the output`
- `analysis/punch_out_detection.feature:121 then the refinement is rejected`
- `analysis/punch_out_detection.feature:52 then a margin is left so that no part of the next Block is audible`
- `analysis/punch_out_detection.feature:78 then the punch-out is placed at least 250 ms away from the nearest audible sound`
- `analysis/punch_out_detection.feature:79 then the resulting ending sounds natural rather than clipped`
- `analysis/punch_out_detection.feature:85 then the punch-out is placed at the quietest available point`
- `analysis/punch_out_detection.feature:98 then a hard punch-out is flagged for review`
- `analysis/punch_out_detection.feature:99 then a hard punch-out is treated as less urgent than a hard punch-in`
- `analysis/segment_proposal.feature:123 then the proposal is treated as implausible`
- `analysis/segment_proposal.feature:152 then the refinement rules are applied instead`
- `analysis/segment_proposal.feature:153 then the Segment records that its boundaries came from the rules`
- `analysis/segment_proposal.feature:161 then the punch-in does not fall inside a word`
- `analysis/segment_proposal.feature:162 then the punch-out does not fall inside a word`
- `analysis/segment_proposal.feature:169 then every Segment records whether its boundaries were proposed or refined`
- `analysis/segment_proposal.feature:170 then that is visible in the processing log`
- `analysis/segment_proposal.feature:185 then the overlap is resolved before the Proposal is offered`
- `analysis/segment_proposal.feature:186 then no two Segments share any audio`
- `analysis/segment_proposal.feature:89 then the Segment ends at the end of the sermon Block`
- `analysis/segment_proposal.feature:90 then the later prayer is not included`
- `analysis/speaker_diarization.feature:107 then no speaker change is detected at the sermon start`
- `analysis/speaker_diarization.feature:108 then boundary detection must fall back to other evidence`
- `analysis/speaker_diarization.feature:115 then boundary detection continues using transcript evidence alone`
- `analysis/speaker_diarization.feature:116 then the Proposal is marked as "no speaker evidence"`
- `analysis/speaker_diarization.feature:44 then it is combined with duration before a Segment is proposed`
- `analysis/speaker_diarization.feature:85 then classification does not penalise it for being an unknown voice`
- `analysis/summarization.feature:106 then no cue excerpt begins or ends inside a silence`
- `analysis/summarization.feature:107 then no cue excerpt is chosen from a span with no speech`
- `analysis/summarization.feature:119 then no third-party API is called`
- `analysis/summarization.feature:134 then summaries are produced at whatever quality that model gives`
- `analysis/summarization.feature:135 then the system does not fall back to a hosted service to improve them`
- `analysis/summarization.feature:141 then summaries fall back to heuristics drawn from the transcript`
- `analysis/summarization.feature:142 then the reviewer is told the summaries are heuristic`
- `analysis/summarization.feature:155 then Blocks are labelled by type alone`
- `analysis/summarization.feature:168 then no boundary, classification or disposition depends on a summary`
- `analysis/summarization.feature:169 then a wrong summary can mislead a reviewer but cannot produce a wrong file`
- `analysis/summarization.feature:31 then each proposed Segment carries its own summary`
- `analysis/summarization.feature:32 then the summary is shown beside it in the review interface`
- `analysis/summarization.feature:33 then it is shown in the notification`
- `analysis/summarization.feature:60 then the model returns the exact words of the recognisable moment`
- `analysis/summarization.feature:62 then the excerpt's timing comes from the transcript, never from the model`
- `analysis/summarization.feature:69 then the failure is counted, so a model that drifts is visible`
- `analysis/summarization.feature:77 then the excerpt is between 3 and 10 seconds long`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the first question asked"`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the invitation itself"`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the most content-bearing notice"`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the opening sentences"`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the opening sentences, or the stated main point"`
- `analysis/summarization.feature:92 then the cue excerpt is chosen from "the passage announcement"`
- `ingestion/s3_reconciliation.feature:64 then the next scheduled scan runs normally`
- `ingestion/webhook_notification.feature:112 given the Sermon Processor is unreachable`
- `ingestion/webhook_notification.feature:113 when the Recorder attempts to deliver a webhook`
- `ingestion/webhook_notification.feature:114 then the Recorder retries with exponential backoff`
- `ingestion/webhook_notification.feature:115 then after the retry budget is exhausted the Recorder records a delivery failure`
- `ingestion/webhook_notification.feature:116 then the Recording is still ingested later by S3 reconciliation`
- `ingestion/webhook_notification.feature:76 then a Recording is uniquely identified by its bucket and object key`
- `ingestion/webhook_notification.feature:77 then the same key always refers to the same audio`
- `interface/discarding_recordings.feature:106 then I do not have to discard it for the queue to stay clean`
- `interface/discarding_recordings.feature:107 then it remains available if I ever want it`
- `interface/discarding_recordings.feature:115 then it is flagged "no substantive content" and marked ignored`
- `interface/discarding_recordings.feature:116 then it never appears as work`
- `interface/discarding_recordings.feature:117 then I can still find and restore it if the machine was wrong`
- `interface/publication_details.feature:107 then the stored details are updated`
- `interface/publication_details.feature:108 then the downloadable file is renamed`
- `interface/publication_details.feature:109 then the audio is not re-encoded`
- `interface/publication_details.feature:52 given its transcript contains "turn with me to Hebrews chapter 12"`
- `interface/publication_details.feature:54 then the label is suggested as "Hebrews 12"`
- `interface/publication_details.feature:55 then I can correct it before approving`
- `interface/publication_details.feature:61 then the label is suggested as "TEC"`
- `interface/publication_details.feature:62 then I can correct it before approving`
- `interface/publication_details.feature:68 then each carries its own label`
- `interface/publication_details.feature:69 then the two output files do not collide`
- `interface/publication_details.feature:77 then the output file is named from the recording date`
- `interface/publication_details.feature:78 then I am not prompted for anything else`
- `interface/publication_details.feature:87 then I can change the label or confirm that this replaces the previous file`
- `interface/punch_point_adjustment.feature:118 then the punch-in moves to the nearest silence gap boundary`
- `interface/punch_point_adjustment.feature:119 then the amount it moved is shown`
- `interface/punch_point_adjustment.feature:135 then I am warned that the cut is too close to the audio`
- `interface/punch_point_adjustment.feature:136 then I am offered the nearest point with a 250 ms margin`
- `interface/punch_point_adjustment.feature:137 then I can override the warning if I mean it`
- `interface/punch_point_adjustment.feature:149 given the teaching begins with "good morning"`
- `interface/punch_point_adjustment.feature:151 then the punch-in lands immediately before "good morning"`
- `interface/recording_detail.feature:62 when I expand the processing log`
- `interface/recording_detail.feature:63 then I see each state transition with its timestamp`
- `interface/recording_detail.feature:64 then I see each job attempt, including retries and failures`
- `interface/recording_detail.feature:65 then I see who performed each human action, against which Segment`
- `interface/recording_list.feature:96 then I can search by date, by classification, and by what was said`
- `interface/segment_review.feature:125 then approving is available without any further step`
- `interface/segment_review.feature:126 then boundary editing is available but not required`
- `interface/segment_review.feature:148 when I press Preview on a Block`
- `interface/segment_review.feature:149 then playback starts at that Block's cue excerpt`
- `interface/segment_review.feature:150 then it stops at the end of the excerpt`
- `interface/segment_review.feature:151 then a few seconds is enough for me to recognise what the Block is`
- `interface/segment_review.feature:155 when I press Preview on a Segment`
- `interface/segment_review.feature:156 then playback starts at the cue excerpt of its seeding Block`
- `interface/segment_review.feature:157 then I can tell whether this is the message I meant to publish`
- `interface/segment_review.feature:161 when I choose to start playback at a specific Block`
- `interface/segment_review.feature:162 then playback seeks there rather than to the cue excerpt`
- `interface/segment_review.feature:167 then all Blocks are drawn on a single waveform of the whole Recording`
- `interface/segment_review.feature:168 then each is coloured by its type`
- `interface/segment_review.feature:169 then proposed Segments are drawn as spans above the Blocks they cover`
- `interface/segment_review.feature:170 then clicking one selects it for review`
- `interface/segment_review.feature:175 then the Segment most likely to be the sermon is expanded by default`
- `interface/segment_review.feature:176 then the others are collapsed but visible`
- `interface/segment_review.feature:180 given I have selected a Segment`
- `interface/segment_review.feature:181 when I read the transcript`
- `interface/segment_review.feature:182 then I see the transcript for that Segment`
- `interface/segment_review.feature:183 then I can expand to the full Recording transcript if I want it`
- `interface/segment_review.feature:197 then I am told which enrolled voice is teaching, and how confidently`
- `interface/segment_review.feature:198 then an unrecognised voice is shown as "not a known voice"`
- `interface/segment_review.feature:202 given a Segment whose teaching voice matches no enrolled profile`
- `interface/segment_review.feature:203 given its intent is "publish"`
- `interface/segment_review.feature:205 then I am asked to confirm that this recording may be distributed`
- `interface/segment_review.feature:206 then the confirmation is recorded with the approval`
- `interface/segment_review.feature:215 when I confirm or correct who was preaching`
- `interface/segment_review.feature:216 then that Segment strengthens or creates that speaker's profile`
- `interface/segment_review.feature:217 then no separate enrolment session is ever required`
- `interface/segment_review.feature:233 then it still appears as needing attention`
- `interface/segment_review.feature:234 then I am not forced to disposition everything in one sitting`
- `interface/segment_review.feature:238 given a Recording in "awaiting_review" containing 0 Segments`
- `interface/segment_review.feature:240 then I am told nothing was detected`
- `interface/segment_review.feature:241 then I can create a Segment by hand`
- `interface/segment_review.feature:242 then I can discard the Recording in one action`
- `interface/segment_review.feature:252 given a Segment whose cuts are both graded "easy"`
- `interface/segment_review.feature:253 when I open the notification`
- `interface/segment_review.feature:254 then I can read the summary`
- `interface/segment_review.feature:255 then I can preview the punch-in and the punch-out`
- `interface/segment_review.feature:256 then I can approve`
- `interface/segment_review.feature:257 then the whole flow works without a waveform`
- `interface/segment_review.feature:264 then I am told it needs an adjustment better made at a desk`
- `interface/segment_review.feature:265 then I can still skip it, or approve it as-is if I choose to`
- `interface/segment_review.feature:266 then I am not offered a cramped editing surface`
- `interface/segment_review.feature:271 then the waveform, zooming, word alignment and nudge controls are all available`
- `interface/segment_review.feature:276 when a Segment is complete`
- `interface/segment_review.feature:277 then I can download the MP3`
- `interface/segment_review.feature:94 given Segment 1 was skipped on "2026-08-16"`
- `interface/segment_review.feature:95 when I open the Recording on "2026-11-04" and approve Segment 1`
- `interface/segment_review.feature:96 then it is processed using its stored boundaries`
- `interface/segment_review.feature:97 then Analysis does not need to run again`
- `interface/segment_review.feature:98 then the resulting MP3 is identical to what it would have been in August`
- `interface/waveform_review.feature:269 given the configured model endpoint does not answer`
- `interface/waveform_review.feature:270 then reviewing, adjusting and approving continue to work`
- `interface/waveform_review.feature:271 then only the actions that need a model are shown as unavailable`
- `interface/waveform_review.feature:272 then the reason names the endpoint rather than blaming the Recording`
- `notifications/approval_notifications.feature:171 then no further notifications are sent to them`
- `notifications/approval_notifications.feature:172 then recordings still appear in the recordings list`
- `notifications/approval_notifications.feature:37 given no delivery channel is configured`
- `notifications/approval_notifications.feature:41 then nothing fails`
- `notifications/approval_notifications.feature:46 then delivering a Notification is separate from creating one`
- `notifications/approval_notifications.feature:47 then adding or changing a channel does not change when Notifications are raised`
- `notifications/approval_notifications.feature:48 then the same Notification can be delivered by more than one channel`
- `notifications/approval_notifications.feature:52 when I open the interface`
- `notifications/approval_notifications.feature:53 then I see the Notifications raised for me`
- `notifications/approval_notifications.feature:83 then it states why confidence is low`
- `operations/storage_and_retention.feature:18 then its "Segment boundaries" is still available`
- `operations/storage_and_retention.feature:18 then its "rendered MP3" is still available`
- `operations/storage_and_retention.feature:18 then its "source FLAC" is still available`
- `operations/storage_and_retention.feature:18 then its "speaker spans and Blocks" is still available`
- `operations/storage_and_retention.feature:18 then its "transcript" is still available`
- `operations/storage_and_retention.feature:18 then its "waveform peaks" is still available`
- `operations/storage_and_retention.feature:31 given a Segment was skipped 2 years ago`
- `operations/storage_and_retention.feature:33 then the source is still available`
- `operations/storage_and_retention.feature:34 then the Segment renders from its stored boundaries`
- `operations/storage_and_retention.feature:40 given a Segment has been re-rendered`
- `operations/storage_and_retention.feature:41 then only the current MP3 is stored`
- `operations/storage_and_retention.feature:42 then the settings needed to reproduce the previous one are retained`
- `operations/storage_and_retention.feature:48 then source FLACs, rendered MP3s and analysis artifacts are written to long-lived storage`
- `operations/storage_and_retention.feature:49 then local scratch holds only what a running job needs`
- `operations/storage_and_retention.feature:53 given a processing job has finished`
- `operations/storage_and_retention.feature:54 then its intermediate files are removed from scratch`
- `operations/storage_and_retention.feature:55 then the artifacts it produced are not`
- `operations/storage_and_retention.feature:59 given a Recording is downloading, analyzing, or has a Segment processing`
- `operations/storage_and_retention.feature:60 when scratch is reclaimed`
- `operations/storage_and_retention.feature:61 then its working files are retained`
- `operations/storage_and_retention.feature:83 when any cleanup runs`
- `operations/storage_and_retention.feature:84 then no source object is deleted`
- `operations/system_health.feature:58 given a Recording is in state "analysis_failed"`
- `operations/system_health.feature:59 when I open its processing log`
- `operations/system_health.feature:60 then I see every job attempt with its timestamp, duration and error`
- `operations/system_health.feature:61 then I can correlate an entry to the application logs`
- `processing/artifact_downloads.feature:42 then I can download "the transcript as plain text"`
- `processing/artifact_downloads.feature:42 then I can download "the transcript with timecodes"`
- `processing/artifact_downloads.feature:52 then I can read its transcript without downloading anything`
- `processing/artifact_downloads.feature:53 then the transcript covers the approved span`
- `processing/artifact_downloads.feature:54 then I can expand to the full Recording transcript`
- `processing/audio_rendering.feature:102 given the Segment contains passages 18 dB quieter than the loudest passage`
- `processing/audio_rendering.feature:104 then the quiet passages are audible at a normal listening volume`
- `processing/audio_rendering.feature:105 then the loudest passages are not clipped`
- `processing/audio_rendering.feature:106 then no separate compression stage is applied`
- `processing/audio_rendering.feature:110 then there is one set of loudness settings, not a normalize toggle and a compress toggle`
- `processing/audio_rendering.feature:111 then the settings used are recorded on every rendered Segment`
- `processing/audio_rendering.feature:112 then changing them is what makes a re-render meaningful`
- `processing/audio_rendering.feature:120 then the output is brought down to the target loudness and peak ceiling`
- `processing/audio_rendering.feature:121 then no attempt is made to reconstruct the clipped peaks`
- `processing/audio_rendering.feature:128 then the output reaches the target loudness`
- `processing/audio_rendering.feature:129 then the noise floor is not raised to a distracting level`
- `processing/audio_rendering.feature:149 then the output is an MP3`
- `processing/audio_rendering.feature:15 given channel 2 of the source is silent`
- `processing/audio_rendering.feature:150 then the channel layout is mono`
- `processing/audio_rendering.feature:151 then the sample rate is 44100 Hz`
- `processing/audio_rendering.feature:152 then the bitrate is variable, averaging between 96 and 108 kbps`
- `processing/audio_rendering.feature:156 given the Segment is 43 minutes long`
- `processing/audio_rendering.feature:158 then the resulting MP3 is between 25 MB and 40 MB`
- `processing/audio_rendering.feature:162 then bitrate, channel layout and sample rate are configuration, not code`
- `processing/audio_rendering.feature:163 then changing them is a re-render, never a re-analysis`
- `processing/audio_rendering.feature:172 then the full span is converted without trimming refinement`
- `processing/audio_rendering.feature:173 then channel 1 extraction is still applied`
- `processing/audio_rendering.feature:174 then loudness normalization is still applied`
- `processing/audio_rendering.feature:175 then the same single loudness treatment is applied`
- `processing/audio_rendering.feature:185 given a Segment rendered under the current loudness target`
- `processing/audio_rendering.feature:186 given earlier published files sit 7 to 11 LU quieter`
- `processing/audio_rendering.feature:187 then the difference is stated to the reviewer once, not on every render`
- `processing/audio_rendering.feature:192 given past Segments with stored boundaries`
- `processing/audio_rendering.feature:193 when an operator re-renders the archive`
- `processing/audio_rendering.feature:194 then each is re-rendered from its stored boundaries under the current target`
- `processing/audio_rendering.feature:195 then any whose source is no longer available fails individually and is reported`
- `processing/audio_rendering.feature:196 then the reviewer is not asked to approve anything again`
- `processing/audio_rendering.feature:202 given a Segment has been rendered`
- `processing/audio_rendering.feature:203 when it is rendered again with identical settings`
- `processing/audio_rendering.feature:204 then the output is byte-identical apart from embedded timestamps`
- `processing/audio_rendering.feature:205 then the recorded render settings are unchanged`
- `processing/audio_rendering.feature:24 then the output takes channel 1 only`
- `processing/audio_rendering.feature:25 then channel 2 is discarded without being mixed in`
- `processing/audio_rendering.feature:26 then the output level matches channel 1's level, not half of it`
- `processing/audio_rendering.feature:27 then the output is mono`
- `processing/audio_rendering.feature:31 given the probe flagged the Recording "unexpected stereo content"`
- `processing/audio_rendering.feature:33 then the render does not start automatically`
- `processing/audio_rendering.feature:34 then the reviewer is asked how the channels should be treated`
- `processing/audio_rendering.feature:44 then the output duration matches the approved span within 100 ms`
- `processing/audio_rendering.feature:45 then the trim is sample-accurate rather than snapped to a frame boundary`
- `processing/audio_rendering.feature:51 then a short fade-in is applied at the start`
- `processing/audio_rendering.feature:52 then a short fade-out is applied at the end`
- `processing/audio_rendering.feature:53 then neither fade is long enough to swallow a spoken word`
- `processing/audio_rendering.feature:77 then the output true peak, measured on the decoded MP3, does not exceed "-0.5 dBTP"`
- `processing/audio_rendering.feature:78 then the measured input and output loudness are recorded on the Segment`
- `processing/audio_rendering.feature:82 given two Segments whose sources differ in loudness by 8 LU`
- `processing/audio_rendering.feature:83 when both are rendered`
- `processing/audio_rendering.feature:84 then their output integrated loudness values are within 1 LU of each other`
- `processing/audio_rendering.feature:90 given the Segment contains one isolated peak 12 dB above the speech level`
- `processing/audio_rendering.feature:92 then the output integrated loudness still meets the target`
- `processing/audio_rendering.feature:93 then the isolated peak is limited rather than allowed to set the level`
- `processing/processing_orchestration.feature:101 when the system comes back up`
- `processing/processing_orchestration.feature:103 then processing is restarted from the beginning`
- `processing/processing_orchestration.feature:104 then no partial artifact is exposed as a download`
- `processing/processing_orchestration.feature:42 then a failure in one does not affect the other`
- `processing/processing_orchestration.feature:47 then the reviewer can continue working with other Recordings and Segments`
- `processing/processing_orchestration.feature:58 then partial output is cleaned up`
- `processing/processing_orchestration.feature:59 then a reviewer can retry processing without re-approving`
- `processing/processing_orchestration.feature:71 then the step is retried`
- `processing/processing_orchestration.feature:78 then the source is re-downloaded from the object store first`
- `processing/processing_orchestration.feature:79 then processing continues normally`
- `processing/processing_orchestration.feature:96 then a storage alert is raised`
- `processing/reprocessing.feature:19 then it enters "recut"`
- `processing/reprocessing.feature:20 then the previously approved boundaries are shown as the starting point`
- `processing/reprocessing.feature:21 then the existing MP3 remains downloadable until a new one replaces it`
- `processing/reprocessing.feature:27 then it is processed again`
- `processing/reprocessing.feature:28 then the new MP3 replaces the previous one`
- `processing/reprocessing.feature:29 then the previous cut's boundaries are retained in the history`
- `processing/reprocessing.feature:34 then the original FLAC is unchanged`
- `processing/reprocessing.feature:35 then it is still downloadable`
- `processing/reprocessing.feature:41 then the other Segment stays "complete"`
- `processing/reprocessing.feature:42 then its MP3 is untouched`
- `processing/reprocessing.feature:48 given the loudness target has been changed in configuration`
- `processing/reprocessing.feature:49 when an operator re-renders the Segment`
- `processing/reprocessing.feature:50 then the boundaries are unchanged`
- `processing/reprocessing.feature:51 then a new MP3 is produced with the new settings`
- `processing/reprocessing.feature:52 then the render settings used are recorded`
- `processing/reprocessing.feature:59 when an operator re-renders them all`
- `processing/reprocessing.feature:60 then each is re-rendered from its stored boundaries`
- `processing/reprocessing.feature:61 then no reviewer input is required`
- `processing/reprocessing.feature:62 then any whose source is no longer available fails individually and is reported`
- `processing/reprocessing.feature:67 when the change is saved`
- `processing/reprocessing.feature:68 then the MP3 audio is not re-encoded`
- `processing/reprocessing.feature:69 then the downloadable filename reflects the corrected label`
- `processing/reprocessing.feature:79 then only the most recent MP3 is stored`
- `processing/reprocessing.feature:80 then the earlier render is deleted`
- `processing/reprocessing.feature:85 when I view its history`
- `processing/reprocessing.feature:86 then I see each set of boundaries with who approved them and when`
- `processing/reprocessing.feature:87 then I see the loudness and encoding settings used for each render`
- `processing/reprocessing.feature:88 then any past render could be reproduced from that record and the source`
- `processing/reprocessing.feature:92 then the interface does not offer to restore an earlier render`
- `processing/reprocessing.feature:93 then the stored history is what makes adding that later possible`
