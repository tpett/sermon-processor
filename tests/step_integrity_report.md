# Step integrity

Regenerate with `.venv/bin/python tests/step_integrity.py`. Hand edits are lost.

## What the guard found

- 1325 step definitions read from `tests/steps`
- 255 condemned
- 172 of 464 non-deferred scenarios rest on at least one condemned step
- 236 of 607 expanded scenario tests likewise
- 76 scenarios whose every Then is condemned, so nothing they claim is checked
- 13 scenarios whose every step outside the Background is condemned
- 0 scenarios whose every step, Background included, is condemned
- 48 Gherkin steps matched more than one definition
- 330 Gherkin steps matched no definition

## Faults by kind

| fault | count |
| --- | --- |
| a Then with an empty body | 0 |
| a Then whose body never asserts | 0 |
| an interface Then that reads the view model rather than the rendered page | 0 |
| an assertion that cannot fail | 1 |
| a boolean operand of True, which neutralises what it joins | 0 |
| a Then whose every assertion only checks that some row exists | 92 |
| an assertion that any existing row satisfies | 16 |
| an assertion operand that some scenario's own arguments make true | 7 |
| a Then with a path through it that asserts nothing | 33 |
| an assertion that compares a value with itself | 2 |
| a Then that constructs and invokes a unit of the system | 43 |
| a Then that writes to the store | 82 |
| a Then that asserts on a flag a Given or Then put on the store, or one nothing sets | 32 |
| a Then that asserts word for word what another Then in its scenario asserts | 28 |
| a When with an empty body | 0 |
| a When whose body never acts | 0 |
| a When that writes the outcome itself instead of invoking the system | 18 |
| an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate | 0 |
| a step that skips or xfails instead of running | 0 |
| a step name the guard cannot read from the source | 0 |
| a step decorator that declares no Given, When or Then | 0 |

## Modules

| module | definitions | condemned | verdict |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py` | 61 | 19 | partly condemned |
| `tests/steps/analysis/approval_rate_steps.py` | 4 | 2 | partly condemned |
| `tests/steps/analysis/audio_probe_steps.py` | 45 | 3 | partly condemned |
| `tests/steps/analysis/domain_steps.py` | 209 | 75 | partly condemned |
| `tests/steps/analysis/preview_audio_steps.py` | 31 | 5 | partly condemned |
| `tests/steps/analysis/remaining_analysis_steps.py` | 200 | 82 | partly condemned |
| `tests/steps/analysis/waveform_generation_steps.py` | 14 | 1 | partly condemned |
| `tests/steps/catch_all_thens.py` (named) | 3 | 1 | partly condemned |
| `tests/steps/discovery_steps.py` | 2 | 0 | sound |
| `tests/steps/ingestion/recording_download_steps.py` | 42 | 4 | partly condemned |
| `tests/steps/ingestion/s3_reconciliation_steps.py` | 37 | 3 | partly condemned |
| `tests/steps/ingestion/webhook_notification_steps.py` | 42 | 5 | partly condemned |
| `tests/steps/interface/approval_steps.py` | 48 | 4 | partly condemned |
| `tests/steps/interface/authentication_steps.py` | 8 | 1 | partly condemned |
| `tests/steps/interface/cut_light_steps.py` | 4 | 0 | sound |
| `tests/steps/interface/discarding_steps.py` | 20 | 1 | partly condemned |
| `tests/steps/interface/playback_steps.py` | 10 | 0 | sound |
| `tests/steps/interface/publication_details_steps.py` | 10 | 3 | partly condemned |
| `tests/steps/interface/punch_nudge_steps.py` | 17 | 0 | sound |
| `tests/steps/interface/punch_point_adjustment_steps.py` | 41 | 1 | partly condemned |
| `tests/steps/interface/recording_detail_steps.py` | 25 | 1 | partly condemned |
| `tests/steps/interface/recording_list_steps.py` | 36 | 1 | partly condemned |
| `tests/steps/interface/segment_review_steps.py` | 37 | 0 | sound |
| `tests/steps/interface/waveform_steps.py` | 103 | 5 | partly condemned |
| `tests/steps/last_fourteen.py` (named) | 10 | 1 | partly condemned |
| `tests/steps/nested/discovery_steps.py` | 1 | 0 | sound |
| `tests/steps/notifications/analysis_notification_steps.py` | 23 | 2 | partly condemned |
| `tests/steps/notifications/notification_steps.py` | 8 | 5 | partly condemned |
| `tests/steps/operations/health_steps.py` | 17 | 3 | partly condemned |
| `tests/steps/operations/job_queue_steps.py` | 14 | 3 | partly condemned |
| `tests/steps/processing/artifact_downloads_steps.py` | 25 | 1 | partly condemned |
| `tests/steps/processing/audio_rendering_steps.py` | 48 | 0 | sound |
| `tests/steps/processing/processing_orchestration_steps.py` | 15 | 2 | partly condemned |
| `tests/steps/remaining_steps.py` (named) | 115 | 21 | partly condemned |

## Condemned outside the six named files

232 definitions.

| location | kind | step | faults |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py:160` | then | `approving one does not affect the other` | a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:205` | then | `transcription runs wherever the application itself runs` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:241` | then | `the stages already cached are not recomputed` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:257` | then | `the transcript is retrievable for the Recording` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:262` | then | `the speaker spans, Blocks and their classifications are retrievable` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:268` | then | `the waveform peak data is retrievable for the Recording` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:273` | then | `every Segment's boundaries and classification are stored` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/analysis_orchestration_steps.py:280` | then | `re-running only the "{later}" stage does not re-run "{earlier}"` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:360` | then | `the cached transcript and diarization are reused` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:366` | then | `fresh Segments and Proposals replace the previous ones` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:388` | then | `that Segment's boundaries are preserved` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/analysis_orchestration_steps.py:394` | then | `the new machine proposal is shown alongside it as a suggestion` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:399` | then | `Segments the reviewer never touched are replaced normally` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/analysis_orchestration_steps.py:418` | then | `that Segment and its artifact are left alone` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:423` | then | `only undispositioned Segments are replaced` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:445` | then | `other Recordings continue to be analysed` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:506` | then | `the stage is cancelled` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:519` | then | `the local FLAC is unchanged` | a Then with a path through it that asserts nothing; an assertion that compares a value with itself |
| `tests/steps/analysis/analysis_orchestration_steps.py:529` | then | `every derived artifact is written to a separate location` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/approval_rate_steps.py:104` | then | `the headline measure is the proportion of a period's published Segments approved with no boundary edit` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/approval_rate_steps.py:114` | then | `it is reported alongside the raw error figures, not replaced by them` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/audio_probe_steps.py:263` | then | `it does not appear in the default list` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/audio_probe_steps.py:269` | then | `it does not count as needing attention` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/audio_probe_steps.py:275` | then | `a reviewer can find it by filtering for ignored recordings` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/domain_steps.py:93` | then | `a transcript is produced covering the full duration` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:101` | then | `every utterance has a start time and an end time` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:107` | then | `every word has a start time` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:113` | then | `each utterance carries a recognition confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:119` | then | `the transcript is stored as an artifact of the Recording` | a Then whose every assertion only checks that some row exists; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:135` | then | `clicking an utterance seeks the player to that timecode` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:162` | then | `the singing produces low-confidence or empty utterances` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:170` | then | `those regions are marked as "likely music" rather than treated as speech` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:192` | then | `no utterances are produced for that span` | a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:199` | then | `the span is recorded as a silence gap with its start and end times` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:210` | then | `the transcript is still produced` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:215` | then | `the average confidence for the affected region is recorded` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:221` | then | `the Recording is flagged "{flag}" when the transcript is measurably poor` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:233` | then | `Analysis continues with low confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:240` | then | `no third-party transcription API is called` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:254` | then | `it calls that machine rather than a hosted service` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:262` | then | `the recording is transcribed in chunks` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:270` | then | `chunk boundaries do not lose or duplicate words` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:284` | then | `timestamps remain absolute against the source file` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:317` | then | `the reviewer can still set boundaries manually` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:347` | then | `a profile is enrolled from each without a separate enrolment session` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:373` | when | `blocks are scored against that profile` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/domain_steps.py:415` | then | `the recording is divided into contiguous speaker segments` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:421` | then | `each segment has a start time, an end time and a speaker label` | a Then with a path through it that asserts nothing; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:428` | then | `the labels are stable within the recording` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:434` | then | `each segment carries a confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:439` | then | `every transcript utterance is attributed to a speaker segment` | a Then with a path through it that asserts nothing; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:448` | then | `the reviewer can see who is speaking beside each utterance in the transcript view` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:459` | then | `spans matching that profile are labelled with that preacher` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:465` | then | `spans that match no known profile keep generic labels` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:495` | then | `that Segment can be used to enrol or strengthen that speaker's profile` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/domain_steps.py:517` | then | `the span keeps a generic label` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:538` | then | `the overlapping span is marked as overlapping speech` | a Then that writes to the store; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:543` | then | `it is not treated as a clean speaker change` | a Then that writes to the store; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:559` | then | `the singing is not emitted as a speaker change` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:565` | then | `the span is labelled as non-speech` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:640` | then | `it reports a number of speakers in the same order as reality` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:646` | then | `a single speaker is not split across labels within one block` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:675` | then | `only into the larger neighbour when neither shares it` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:680` | then | `absorbing them never moves a boundary across a change of voice` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:705` | then | `a Block is produced for each contiguous speaker span` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:710` | then | `every Block has a start time, an end time and a speaker label` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/domain_steps.py:717` | then | `the Blocks cover the whole Recording with no gaps and no overlaps` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/domain_steps.py:771` | then | `Blocks are produced across the whole Recording` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:781` | then | `the boundary between them falls out of the ordinary speaker changes` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:811` | then | `the silence is recorded as a pause within the Block` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:816` | then | `every silence gap longer than 2 seconds is recorded with its start and end` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:823` | then | `those gaps are available for snapping a boundary later` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:851` | then | `it becomes a Block of its own` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:876` | then | `the Block records that it contains multiple speakers` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:887` | then | `Blocks are produced from transcript structure and silence alone` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:892` | then | `each Block is marked as having no speaker attribution` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:897` | then | `downstream confidence is reduced` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:985` | then | `the Blocks are typed in order:` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1097` | then | `the Recording is summarised as "nothing to publish"` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1171` | then | `the reviewer can correct it` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:1184` | then | `those words are located in the word-level transcript` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1195` | then | `no cue excerpt is stored for that Block` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1200` | then | `the Block falls back to its first few seconds` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1258` | then | `the lead-in never exceeds 1.0 second` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1270` | then | `the lead-in is shorter than 1.0 second` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1277` | then | `no audio from the previous Block is included` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1288` | then | `the punch-in is placed at the quietest available point` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:1293` | then | `the Segment is flagged "{warning}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1308` | then | `the reviewer is prompted to place it by hand` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1352` | then | `the punch-out is placed 1.5 seconds after the last word` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1362` | then | `the whole of the last word is audible, decay included` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1367` | then | `the tail stops before any sound belonging to what follows` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1373` | then | `no audio from the following Block is included` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1532` | then | `the punch-in is that offset` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1537` | then | `the punch-out is that offset plus the MP3 duration` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1600` | then | `the punch-in is the intercept of the fit, not the middle of it` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1662` | then | `it is flagged rather than silently accepted` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1667` | then | `it is excluded from boundary statistics` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1676` | then | `a legitimate untrimmed archive is flagged the same way` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:75` | then | `the preview is never offered as a download` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:226` | then | `the preview is a constant-bitrate file` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:298` | then | `the transcript, summaries and waveform are still usable` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/preview_audio_steps.py:304` | then | `boundaries can still be adjusted and approved` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/preview_audio_steps.py:328` | then | `no reviewer ever hears audio from a different Recording` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:674` | when | `the accuracy suite runs over the corpus` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:717` | then | `the Segment does not claim more certainty than one analysis supports` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:723` | then | `the Segment carries, most useful first:` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:730` | then | `the punch-out is placed before the next Block begins` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:746` | then | `the cut is graded "{grade}"` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:769` | then | `no transcript leaves the local network` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:774` | then | `no reviewer-facing behaviour depends on a model's self-reported confidence` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:780` | then | `each type carries a confidence derived from evidence, not self-reported` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:786` | then | `each spoken Block carries a cue excerpt with a start and end time` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:793` | then | `each evidence entry states what was found, where, and what it implies, for example:` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:799` | then | `a confidence band tells the reviewer where to look first` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:805` | then | `the Block is typed "{block_type}"` | an assertion operand that some scenario's own arguments make true; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:812` | then | `it is typed from those cues` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:817` | then | `it is classified as a Recording of kind "{kind}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:822` | then | `it is not a Block type` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:827` | then | `the Block is not split` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:832` | then | `the reviewer is prompted to listen` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:837` | then | `a Segment is still proposed from it` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; an assertion operand that some scenario's own arguments make true; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:843` | then | `the reviewer is told the classification is uncertain` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:848` | then | `both types are recorded` | an assertion that cannot fail; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:855` | then | `the reviewer can pick which one to keep` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:860` | when | `the reviewer retypes it as "{block_type}"` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:866` | then | `the Block is "{block_type}"` | an assertion operand that some scenario's own arguments make true |
| `tests/steps/analysis/remaining_analysis_steps.py:871` | then | `the machine's original type is retained beside it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:876` | then | `the prayer is included in the Segment` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:891` | then | `the Segment stops before the "{block_type}" Block` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:899` | then | `the two teaching Blocks remain two Segments` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:910` | then | `the later Segment starts where the earlier one ends` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:917` | then | `the reviewer is asked to confirm or correct the span` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:922` | then | `the reviewer can split a Segment` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:927` | then | `it is marked as having no speaker attribution` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:932` | then | `the Recording kind is "{kind}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:940` | then | `the punch-in is placed at the start of the Recording` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:946` | then | `the punch-out is placed at the end of the Recording` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:953` | then | `the punch-in is left in place` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:958` | then | `the word is not split` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1005` | when | `the accuracy suite runs` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1015` | then | `a Proposal is still produced for every Segment` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1021` | then | `the Block keeps the type the classifier gave it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1026` | then | `the Block type is updated` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1031` | then | `the Segment is shown as needing attention` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1036` | then | `the Segment starts at the sermon Block, not at the prayer` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1044` | then | `the teaching Block is typed "lesson" rather than "sermon"` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1051` | then | `the transition is graded "{grade}"` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1074` | then | `it is shown as needing attention` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:1079` | then | `its classification confidence is "{level}"` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1086` | then | `the reviewer can split it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1091` | then | `the Segment ends at the end of the prayer Block` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1100` | then | `it is accepted without warning` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1105` | then | `the Segment is accepted without warning` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1119` | then | `its Blocks are typed "rehearsal", not "music"` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:1128` | then | `its boundaries are used as proposed` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1133` | then | `no word is cut off` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1138` | then | `the punch-out falls back to the end of the seeding Block` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1154` | then | `the Segment is not flagged` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1164` | when | `the accuracy suite runs before and after` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1175` | when | `the reviewer presses Preview on that Block` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1182` | when | `the Segment is offered for review` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1211` | then | `the simpler structure makes the boundaries easier, not harder` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1229` | then | `a Block from that speaker is less likely to be typed "sermon"` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1234` | then | `this is evidence only, since the preacher occasionally gives the benediction` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1239` | then | `no Segment is proposed` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1245` | then | `the Recording is shown as needing no attention` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1280` | then | `a proposal exceeding it is flagged to the reviewer before approval` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1293` | then | `nothing implies a second opinion was sought and agreed` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:1299` | then | `the recordings list shows the sermon Segment's confidence` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1307` | then | `the other Segments and all Blocks are visible on the detail view` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1314` | then | `it is not shown as needing attention` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1331` | then | `the boundary invariants below are still enforced` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1336` | then | `neither boundary sits within 250 ms of audible sound where quiet exists` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1341` | then | `the lead-in before the first word does not exceed 1.0 second` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:1348` | then | `a boundary that cannot satisfy these is flagged rather than moved silently` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1353` | then | `the reviewer can split it if they were genuinely two messages` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1367` | then | `it can be classified and approved like any other` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1384` | then | `the Proposal confidence is reduced` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1397` | then | `the resulting Proposal has reduced confidence` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1405` | then | `its confidence is reduced` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1435` | then | `the reviewer can tell what the Block is without further scrubbing` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1440` | then | `the machine it used is recorded with the summary` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:1447` | then | `Analysis completes without summaries` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1460` | then | `the reviewer is told summaries were unavailable` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1508` | then | `the corpus grows without anyone hand-labelling anything` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/waveform_generation_steps.py:92` | then | `the reviewer can still adjust Segment boundaries using playback and the transcript` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/recording_download_steps.py:209` | then | `the download is discarded` | a Then with a path through it that asserts nothing |
| `tests/steps/ingestion/recording_download_steps.py:224` | then | `after the retry budget is exhausted the Recording enters "{state}"` | a Then that constructs and invokes a unit of the system |
| `tests/steps/ingestion/recording_download_steps.py:274` | then | `the Recording stays in "{state}" until the retry budget is exhausted` | a Then that constructs and invokes a unit of the system |
| `tests/steps/ingestion/recording_download_steps.py:410` | then | `no process rewrites the local FLAC at any later point` | an assertion that compares a value with itself |
| `tests/steps/ingestion/s3_reconciliation_steps.py:100` | then | `the sidecar metadata file is associated with its parent recording if one exists` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/ingestion/s3_reconciliation_steps.py:165` | then | `an operator can see every object the Processor has ever skipped` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/s3_reconciliation_steps.py:225` | then | `this is how the sample corpus is loaded for the accuracy suite` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:160` | then | `no duplicate Recording is created` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:195` | then | `whichever arrived first owns the Recording` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:263` | then | `the download is queued anyway` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:301` | then | `a Recording is created for it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:306` | then | `it is queued for download` | a Then whose every assertion only checks that some row exists |
| `tests/steps/interface/approval_steps.py:135` | when | `processing is running` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/approval_steps.py:220` | then | `the output is named from the recording date alone` | a Then that writes to the store |
| `tests/steps/interface/approval_steps.py:258` | then | `no Segment is ever rendered without a human approving it` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/approval_steps.py:324` | then | `no Segment is ever published on classification alone` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/authentication_steps.py:66` | when | `a Recording is approved` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/discarding_steps.py:218` | then | `the Recording's record and analysis artifacts are retained` | a Then whose every assertion only checks that some row exists |
| `tests/steps/interface/publication_details_steps.py:55` | then | `the details are saved with the Segment` | a Then that writes to the store |
| `tests/steps/interface/publication_details_steps.py:72` | then | `I can change it` | a Then that writes to the store |
| `tests/steps/interface/publication_details_steps.py:91` | when | `the Segment is processed` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/punch_point_adjustment_steps.py:150` | then | `the change is rejected if it would overlap the neighbouring Segment` | a Then that writes to the store |
| `tests/steps/interface/recording_detail_steps.py:83` | then | `I see:` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/recording_list_steps.py:243` | then | `I see only recordings containing a Segment classified "{classification}"` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:571` | then | `100 ms is {pixels}` | a Then that constructs and invokes a unit of the system |
| `tests/steps/interface/waveform_steps.py:576` | then | `placing a boundary to 100 ms is {verdict}` | a Then that constructs and invokes a unit of the system |
| `tests/steps/interface/waveform_steps.py:741` | then | `clicking a word places the boundary at that word` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:787` | then | `I can drop a boundary into one with a single click` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:841` | then | `neither boundary has moved` | a Then with a path through it that asserts nothing |
| `tests/steps/notifications/analysis_notification_steps.py:186` | then | `the notification links directly to that Segment` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/notifications/analysis_notification_steps.py:220` | then | `the notification says the proposal needs careful review` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:50` | then | `the Notification exists whether or not any channel is configured` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:55` | when | `a Notification is created` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/notifications/notification_steps.py:82` | then | `it is recorded and left undelivered` | a Then that constructs and invokes a unit of the system |
| `tests/steps/notifications/notification_steps.py:90` | then | `it is visible in the interface` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:95` | then | `I can see which were delivered and which were not` | a Then with a path through it that asserts nothing |
| `tests/steps/operations/health_steps.py:28` | then | `I see the status of:` | a Then with a path through it that asserts nothing |
| `tests/steps/operations/health_steps.py:70` | then | `no alert is raised` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/operations/health_steps.py:77` | then | `no notification is sent` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/operations/job_queue_steps.py:152` | then | `a job is enqueued` | a Then whose every assertion only checks that some row exists |
| `tests/steps/operations/job_queue_steps.py:209` | then | `the queued jobs still run` | a Then that writes to the store |
| `tests/steps/operations/job_queue_steps.py:302` | then | `it is retried with increasing delay between attempts` | a Then that constructs and invokes a unit of the system |
| `tests/steps/processing/artifact_downloads_steps.py:288` | then | `the download continues from where it stopped` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/processing/processing_orchestration_steps.py:169` | then | `each produces its own MP3` | a Then whose every assertion only checks that some row exists |
| `tests/steps/processing/processing_orchestration_steps.py:205` | then | `the reviewer is notified` | a Then whose every assertion only checks that some row exists |

## Every condemned definition

| location | kind | step | faults |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py:160` | then | `approving one does not affect the other` | a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:205` | then | `transcription runs wherever the application itself runs` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:241` | then | `the stages already cached are not recomputed` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:257` | then | `the transcript is retrievable for the Recording` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:262` | then | `the speaker spans, Blocks and their classifications are retrievable` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:268` | then | `the waveform peak data is retrievable for the Recording` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:273` | then | `every Segment's boundaries and classification are stored` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/analysis_orchestration_steps.py:280` | then | `re-running only the "{later}" stage does not re-run "{earlier}"` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/analysis_orchestration_steps.py:360` | then | `the cached transcript and diarization are reused` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:366` | then | `fresh Segments and Proposals replace the previous ones` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:388` | then | `that Segment's boundaries are preserved` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/analysis_orchestration_steps.py:394` | then | `the new machine proposal is shown alongside it as a suggestion` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:399` | then | `Segments the reviewer never touched are replaced normally` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/analysis_orchestration_steps.py:418` | then | `that Segment and its artifact are left alone` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:423` | then | `only undispositioned Segments are replaced` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:445` | then | `other Recordings continue to be analysed` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:506` | then | `the stage is cancelled` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/analysis_orchestration_steps.py:519` | then | `the local FLAC is unchanged` | a Then with a path through it that asserts nothing; an assertion that compares a value with itself |
| `tests/steps/analysis/analysis_orchestration_steps.py:529` | then | `every derived artifact is written to a separate location` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/approval_rate_steps.py:104` | then | `the headline measure is the proportion of a period's published Segments approved with no boundary edit` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/approval_rate_steps.py:114` | then | `it is reported alongside the raw error figures, not replaced by them` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/audio_probe_steps.py:263` | then | `it does not appear in the default list` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/audio_probe_steps.py:269` | then | `it does not count as needing attention` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/audio_probe_steps.py:275` | then | `a reviewer can find it by filtering for ignored recordings` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/domain_steps.py:93` | then | `a transcript is produced covering the full duration` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:101` | then | `every utterance has a start time and an end time` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:107` | then | `every word has a start time` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:113` | then | `each utterance carries a recognition confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:119` | then | `the transcript is stored as an artifact of the Recording` | a Then whose every assertion only checks that some row exists; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:135` | then | `clicking an utterance seeks the player to that timecode` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:162` | then | `the singing produces low-confidence or empty utterances` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:170` | then | `those regions are marked as "likely music" rather than treated as speech` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:192` | then | `no utterances are produced for that span` | a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:199` | then | `the span is recorded as a silence gap with its start and end times` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:210` | then | `the transcript is still produced` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:215` | then | `the average confidence for the affected region is recorded` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:221` | then | `the Recording is flagged "{flag}" when the transcript is measurably poor` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:233` | then | `Analysis continues with low confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:240` | then | `no third-party transcription API is called` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:254` | then | `it calls that machine rather than a hosted service` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:262` | then | `the recording is transcribed in chunks` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:270` | then | `chunk boundaries do not lose or duplicate words` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:284` | then | `timestamps remain absolute against the source file` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:317` | then | `the reviewer can still set boundaries manually` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:347` | then | `a profile is enrolled from each without a separate enrolment session` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:373` | when | `blocks are scored against that profile` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/domain_steps.py:415` | then | `the recording is divided into contiguous speaker segments` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:421` | then | `each segment has a start time, an end time and a speaker label` | a Then with a path through it that asserts nothing; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:428` | then | `the labels are stable within the recording` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:434` | then | `each segment carries a confidence` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:439` | then | `every transcript utterance is attributed to a speaker segment` | a Then with a path through it that asserts nothing; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:448` | then | `the reviewer can see who is speaking beside each utterance in the transcript view` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:459` | then | `spans matching that profile are labelled with that preacher` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:465` | then | `spans that match no known profile keep generic labels` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:495` | then | `that Segment can be used to enrol or strengthen that speaker's profile` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/domain_steps.py:517` | then | `the span keeps a generic label` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:538` | then | `the overlapping span is marked as overlapping speech` | a Then that writes to the store; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:543` | then | `it is not treated as a clean speaker change` | a Then that writes to the store; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:559` | then | `the singing is not emitted as a speaker change` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:565` | then | `the span is labelled as non-speech` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:640` | then | `it reports a number of speakers in the same order as reality` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:646` | then | `a single speaker is not split across labels within one block` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:675` | then | `only into the larger neighbour when neither shares it` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:680` | then | `absorbing them never moves a boundary across a change of voice` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:705` | then | `a Block is produced for each contiguous speaker span` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:710` | then | `every Block has a start time, an end time and a speaker label` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/domain_steps.py:717` | then | `the Blocks cover the whole Recording with no gaps and no overlaps` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/domain_steps.py:771` | then | `Blocks are produced across the whole Recording` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:781` | then | `the boundary between them falls out of the ordinary speaker changes` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:811` | then | `the silence is recorded as a pause within the Block` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:816` | then | `every silence gap longer than 2 seconds is recorded with its start and end` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:823` | then | `those gaps are available for snapping a boundary later` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:851` | then | `it becomes a Block of its own` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:876` | then | `the Block records that it contains multiple speakers` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:887` | then | `Blocks are produced from transcript structure and silence alone` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:892` | then | `each Block is marked as having no speaker attribution` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:897` | then | `downstream confidence is reduced` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:985` | then | `the Blocks are typed in order:` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1097` | then | `the Recording is summarised as "nothing to publish"` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1171` | then | `the reviewer can correct it` | a Then that writes to the store |
| `tests/steps/analysis/domain_steps.py:1184` | then | `those words are located in the word-level transcript` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1195` | then | `no cue excerpt is stored for that Block` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1200` | then | `the Block falls back to its first few seconds` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1258` | then | `the lead-in never exceeds 1.0 second` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1270` | then | `the lead-in is shorter than 1.0 second` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1277` | then | `no audio from the previous Block is included` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1288` | then | `the punch-in is placed at the quietest available point` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/domain_steps.py:1293` | then | `the Segment is flagged "{warning}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1308` | then | `the reviewer is prompted to place it by hand` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/domain_steps.py:1352` | then | `the punch-out is placed 1.5 seconds after the last word` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1362` | then | `the whole of the last word is audible, decay included` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1367` | then | `the tail stops before any sound belonging to what follows` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1373` | then | `no audio from the following Block is included` | a Then with a path through it that asserts nothing; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1532` | then | `the punch-in is that offset` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1537` | then | `the punch-out is that offset plus the MP3 duration` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1600` | then | `the punch-in is the intercept of the fit, not the middle of it` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/domain_steps.py:1662` | then | `it is flagged rather than silently accepted` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1667` | then | `it is excluded from boundary statistics` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/domain_steps.py:1676` | then | `a legitimate untrimmed archive is flagged the same way` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:75` | then | `the preview is never offered as a download` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:226` | then | `the preview is a constant-bitrate file` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/preview_audio_steps.py:298` | then | `the transcript, summaries and waveform are still usable` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/preview_audio_steps.py:304` | then | `boundaries can still be adjusted and approved` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/preview_audio_steps.py:328` | then | `no reviewer ever hears audio from a different Recording` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:674` | when | `the accuracy suite runs over the corpus` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:717` | then | `the Segment does not claim more certainty than one analysis supports` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:723` | then | `the Segment carries, most useful first:` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:730` | then | `the punch-out is placed before the next Block begins` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:746` | then | `the cut is graded "{grade}"` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:769` | then | `no transcript leaves the local network` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:774` | then | `no reviewer-facing behaviour depends on a model's self-reported confidence` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:780` | then | `each type carries a confidence derived from evidence, not self-reported` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:786` | then | `each spoken Block carries a cue excerpt with a start and end time` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:793` | then | `each evidence entry states what was found, where, and what it implies, for example:` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:799` | then | `a confidence band tells the reviewer where to look first` | a Then whose every assertion only checks that some row exists; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:805` | then | `the Block is typed "{block_type}"` | an assertion operand that some scenario's own arguments make true; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:812` | then | `it is typed from those cues` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:817` | then | `it is classified as a Recording of kind "{kind}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:822` | then | `it is not a Block type` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:827` | then | `the Block is not split` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:832` | then | `the reviewer is prompted to listen` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:837` | then | `a Segment is still proposed from it` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; an assertion operand that some scenario's own arguments make true; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:843` | then | `the reviewer is told the classification is uncertain` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:848` | then | `both types are recorded` | an assertion that cannot fail; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:855` | then | `the reviewer can pick which one to keep` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:860` | when | `the reviewer retypes it as "{block_type}"` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:866` | then | `the Block is "{block_type}"` | an assertion operand that some scenario's own arguments make true |
| `tests/steps/analysis/remaining_analysis_steps.py:871` | then | `the machine's original type is retained beside it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:876` | then | `the prayer is included in the Segment` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:891` | then | `the Segment stops before the "{block_type}" Block` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:899` | then | `the two teaching Blocks remain two Segments` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:910` | then | `the later Segment starts where the earlier one ends` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:917` | then | `the reviewer is asked to confirm or correct the span` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:922` | then | `the reviewer can split a Segment` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:927` | then | `it is marked as having no speaker attribution` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:932` | then | `the Recording kind is "{kind}"` | an assertion operand that some scenario's own arguments make true; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:940` | then | `the punch-in is placed at the start of the Recording` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:946` | then | `the punch-out is placed at the end of the Recording` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:953` | then | `the punch-in is left in place` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:958` | then | `the word is not split` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1005` | when | `the accuracy suite runs` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1015` | then | `a Proposal is still produced for every Segment` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1021` | then | `the Block keeps the type the classifier gave it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1026` | then | `the Block type is updated` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1031` | then | `the Segment is shown as needing attention` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1036` | then | `the Segment starts at the sermon Block, not at the prayer` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1044` | then | `the teaching Block is typed "lesson" rather than "sermon"` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1051` | then | `the transition is graded "{grade}"` | a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1074` | then | `it is shown as needing attention` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/analysis/remaining_analysis_steps.py:1079` | then | `its classification confidence is "{level}"` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1086` | then | `the reviewer can split it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1091` | then | `the Segment ends at the end of the prayer Block` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1100` | then | `it is accepted without warning` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1105` | then | `the Segment is accepted without warning` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1119` | then | `its Blocks are typed "rehearsal", not "music"` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:1128` | then | `its boundaries are used as proposed` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1133` | then | `no word is cut off` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1138` | then | `the punch-out falls back to the end of the seeding Block` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1154` | then | `the Segment is not flagged` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1164` | when | `the accuracy suite runs before and after` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1175` | when | `the reviewer presses Preview on that Block` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1182` | when | `the Segment is offered for review` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1211` | then | `the simpler structure makes the boundaries easier, not harder` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1229` | then | `a Block from that speaker is less likely to be typed "sermon"` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1234` | then | `this is evidence only, since the preacher occasionally gives the benediction` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1239` | then | `no Segment is proposed` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1245` | then | `the Recording is shown as needing no attention` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1280` | then | `a proposal exceeding it is flagged to the reviewer before approval` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1293` | then | `nothing implies a second opinion was sought and agreed` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:1299` | then | `the recordings list shows the sermon Segment's confidence` | a Then that constructs and invokes a unit of the system |
| `tests/steps/analysis/remaining_analysis_steps.py:1307` | then | `the other Segments and all Blocks are visible on the detail view` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1314` | then | `it is not shown as needing attention` | a Then with a path through it that asserts nothing; a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1331` | then | `the boundary invariants below are still enforced` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1336` | then | `neither boundary sits within 250 ms of audible sound where quiet exists` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1341` | then | `the lead-in before the first word does not exceed 1.0 second` | a Then with a path through it that asserts nothing |
| `tests/steps/analysis/remaining_analysis_steps.py:1348` | then | `a boundary that cannot satisfy these is flagged rather than moved silently` | a Then whose every assertion only checks that some row exists; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1353` | then | `the reviewer can split it if they were genuinely two messages` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1367` | then | `it can be classified and approved like any other` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1384` | then | `the Proposal confidence is reduced` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1397` | then | `the resulting Proposal has reduced confidence` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1405` | then | `its confidence is reduced` | a Then that constructs and invokes a unit of the system; a Then that writes to the store |
| `tests/steps/analysis/remaining_analysis_steps.py:1435` | then | `the reviewer can tell what the Block is without further scrubbing` | a Then whose every assertion only checks that some row exists |
| `tests/steps/analysis/remaining_analysis_steps.py:1440` | then | `the machine it used is recorded with the summary` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/remaining_analysis_steps.py:1447` | then | `Analysis completes without summaries` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1460` | then | `the reviewer is told summaries were unavailable` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1508` | then | `the corpus grows without anyone hand-labelling anything` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/analysis/waveform_generation_steps.py:92` | then | `the reviewer can still adjust Segment boundaries using playback and the transcript` | a Then whose every assertion only checks that some row exists |
| `tests/steps/catch_all_thens.py:4` | then | `the Segment stays in "proposed"` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/recording_download_steps.py:209` | then | `the download is discarded` | a Then with a path through it that asserts nothing |
| `tests/steps/ingestion/recording_download_steps.py:224` | then | `after the retry budget is exhausted the Recording enters "{state}"` | a Then that constructs and invokes a unit of the system |
| `tests/steps/ingestion/recording_download_steps.py:274` | then | `the Recording stays in "{state}" until the retry budget is exhausted` | a Then that constructs and invokes a unit of the system |
| `tests/steps/ingestion/recording_download_steps.py:410` | then | `no process rewrites the local FLAC at any later point` | an assertion that compares a value with itself |
| `tests/steps/ingestion/s3_reconciliation_steps.py:100` | then | `the sidecar metadata file is associated with its parent recording if one exists` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/ingestion/s3_reconciliation_steps.py:165` | then | `an operator can see every object the Processor has ever skipped` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/s3_reconciliation_steps.py:225` | then | `this is how the sample corpus is loaded for the accuracy suite` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:160` | then | `no duplicate Recording is created` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:195` | then | `whichever arrived first owns the Recording` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:263` | then | `the download is queued anyway` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:301` | then | `a Recording is created for it` | a Then whose every assertion only checks that some row exists |
| `tests/steps/ingestion/webhook_notification_steps.py:306` | then | `it is queued for download` | a Then whose every assertion only checks that some row exists |
| `tests/steps/interface/approval_steps.py:135` | when | `processing is running` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/approval_steps.py:220` | then | `the output is named from the recording date alone` | a Then that writes to the store |
| `tests/steps/interface/approval_steps.py:258` | then | `no Segment is ever rendered without a human approving it` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/approval_steps.py:324` | then | `no Segment is ever published on classification alone` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/authentication_steps.py:66` | when | `a Recording is approved` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/discarding_steps.py:218` | then | `the Recording's record and analysis artifacts are retained` | a Then whose every assertion only checks that some row exists |
| `tests/steps/interface/publication_details_steps.py:55` | then | `the details are saved with the Segment` | a Then that writes to the store |
| `tests/steps/interface/publication_details_steps.py:72` | then | `I can change it` | a Then that writes to the store |
| `tests/steps/interface/publication_details_steps.py:91` | when | `the Segment is processed` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/interface/punch_point_adjustment_steps.py:150` | then | `the change is rejected if it would overlap the neighbouring Segment` | a Then that writes to the store |
| `tests/steps/interface/recording_detail_steps.py:83` | then | `I see:` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/recording_list_steps.py:243` | then | `I see only recordings containing a Segment classified "{classification}"` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:571` | then | `100 ms is {pixels}` | a Then that constructs and invokes a unit of the system |
| `tests/steps/interface/waveform_steps.py:576` | then | `placing a boundary to 100 ms is {verdict}` | a Then that constructs and invokes a unit of the system |
| `tests/steps/interface/waveform_steps.py:741` | then | `clicking a word places the boundary at that word` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:787` | then | `I can drop a boundary into one with a single click` | a Then with a path through it that asserts nothing |
| `tests/steps/interface/waveform_steps.py:841` | then | `neither boundary has moved` | a Then with a path through it that asserts nothing |
| `tests/steps/last_fourteen.py:51` | when | `I revisit that Segment` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/notifications/analysis_notification_steps.py:186` | then | `the notification links directly to that Segment` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/notifications/analysis_notification_steps.py:220` | then | `the notification says the proposal needs careful review` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:50` | then | `the Notification exists whether or not any channel is configured` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:55` | when | `a Notification is created` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/notifications/notification_steps.py:82` | then | `it is recorded and left undelivered` | a Then that constructs and invokes a unit of the system |
| `tests/steps/notifications/notification_steps.py:90` | then | `it is visible in the interface` | a Then whose every assertion only checks that some row exists |
| `tests/steps/notifications/notification_steps.py:95` | then | `I can see which were delivered and which were not` | a Then with a path through it that asserts nothing |
| `tests/steps/operations/health_steps.py:28` | then | `I see the status of:` | a Then with a path through it that asserts nothing |
| `tests/steps/operations/health_steps.py:70` | then | `no alert is raised` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/operations/health_steps.py:77` | then | `no notification is sent` | a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/operations/job_queue_steps.py:152` | then | `a job is enqueued` | a Then whose every assertion only checks that some row exists |
| `tests/steps/operations/job_queue_steps.py:209` | then | `the queued jobs still run` | a Then that writes to the store |
| `tests/steps/operations/job_queue_steps.py:302` | then | `it is retried with increasing delay between attempts` | a Then that constructs and invokes a unit of the system |
| `tests/steps/processing/artifact_downloads_steps.py:288` | then | `the download continues from where it stopped` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/processing/processing_orchestration_steps.py:169` | then | `each produces its own MP3` | a Then whose every assertion only checks that some row exists |
| `tests/steps/processing/processing_orchestration_steps.py:205` | then | `the reviewer is notified` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:63` | when | `I open a proposed Segment` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:186` | when | `a reviewer disables notifications` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:278` | when | `I choose to re-cut the Segment` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:377` | then | `100 ms is {pixels}` | an assertion operand that some scenario's own arguments make true |
| `tests/steps/remaining_steps.py:397` | then | `the failure names the step "{step}" and its error` | a Then whose every assertion only checks that some row exists; an assertion that any existing row satisfies |
| `tests/steps/remaining_steps.py:403` | then | `processing completes normally` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:423` | then | `the Segment stays in "approved" pending space` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:443` | when | `it is ingested` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:470` | then | `it survives me reloading the page` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:523` | when | `I correct the label to "{label}"` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:529` | when | `I re-cut this Segment` | a When that writes the outcome itself instead of invoking the system |
| `tests/steps/remaining_steps.py:551` | then | `adding real accounts changes who that actor is` | a Then that writes to the store; a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/remaining_steps.py:557` | then | `it does not change what is recorded against it` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets; a Then that asserts word for word what another Then in its scenario asserts |
| `tests/steps/remaining_steps.py:599` | then | `I am warned that it contains a published segment` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/remaining_steps.py:604` | then | `the discard proceeds only if I confirm` | a Then that constructs and invokes a unit of the system |
| `tests/steps/remaining_steps.py:610` | then | `the rendered MP3 remains downloadable` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:845` | then | `delivery is retried` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/remaining_steps.py:986` | then | `no more than the configured number of analysis jobs run concurrently` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/remaining_steps.py:1005` | then | `new downloads and renders pause` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |
| `tests/steps/remaining_steps.py:1019` | then | `no Recording or Segment state is lost` | a Then whose every assertion only checks that some row exists |
| `tests/steps/remaining_steps.py:1057` | then | `its skipped Segments are marked as no longer extractable` | a Then that asserts on a flag a Given or Then put on the store, or one nothing sets |

## Scenarios whose every Then is condemned

| feature | line | scenario |
| --- | --- | --- |
| `analysis/analysis_confidence.feature` | 60 | A model's own confidence number is not used for anything |
| `analysis/analysis_confidence.feature` | 207 | A recording with nothing publishable |
| `analysis/analysis_confidence.feature` | 217 | Confidence is a reviewer aid, not a quality claim |
| `analysis/analysis_confidence.feature` | 179 | Degrading gracefully |
| `analysis/analysis_confidence.feature` | 120 | Evidence is human readable |
| `analysis/analysis_confidence.feature` | 133 | One analysis is the v1 behaviour, not a degraded mode |
| `analysis/analysis_confidence.feature` | 112 | What a reviewer is told, in order of usefulness |
| `analysis/analysis_confidence.feature` | 151 | What the reviewer loses, stated where they can see it |
| `analysis/analysis_orchestration.feature` | 123 | Analysis is re-run after a reviewer has edited a segment |
| `analysis/analysis_orchestration.feature` | 132 | Analysis is re-run after a segment has been rendered |
| `analysis/analysis_orchestration.feature` | 96 | Stage outputs are retained for the interface and for re-runs |
| `analysis/analysis_orchestration.feature` | 177 | The FLAC is read-only to Analysis |
| `analysis/audio_probe.feature` | 116 | Ignored recordings stay out of the way but remain visible |
| `analysis/block_classification.feature` | 377 | A block that is genuinely two things |
| `analysis/block_classification.feature` | 264 | A whole recording of rehearsal |
| `analysis/block_classification.feature` | 73 | A whole service classified |
| `analysis/block_classification.feature` | 367 | An unsure teaching Block still produces a Segment |
| `analysis/block_classification.feature` | 345 | Classification is unsure |
| `analysis/block_classification.feature` | 122 | Communion cues |
| `analysis/block_classification.feature` | 109 | Prayer cues |
| `analysis/block_classification.feature` | 135 | Q&A cues |
| `analysis/block_classification.feature` | 337 | Retyping a block |
| `analysis/block_classification.feature` | 95 | Scripture reading cues |
| `analysis/block_classification.feature` | 292 | Services with a different shape |
| `analysis/block_classification.feature` | 160 | The sermon is the sustained monologue |
| `analysis/blocking.feature` | 59 | A normal Sunday |
| `analysis/blocking.feature` | 138 | Diarization was unavailable |
| `analysis/blocking.feature` | 106 | Silence is still recorded as evidence |
| `analysis/blocking.feature` | 37 | The clusterer must be constrained or it invents speakers |
| `analysis/blocking.feature` | 114 | Very short spans do not become blocks |
| `analysis/detection_accuracy.feature` | 73 | A lossless copy of just the message |
| `analysis/detection_accuracy.feature` | 130 | The target is a two-preview approval |
| `analysis/detection_accuracy.feature` | 206 | What makes a cut easy or hard |
| `analysis/punch_in_detection.feature` | 137 | A candidate falling mid-word is moved |
| `analysis/punch_in_detection.feature` | 65 | Cut difficulty is assessed and recorded |
| `analysis/punch_in_detection.feature` | 48 | No quiet margin is available |
| `analysis/punch_out_detection.feature` | 46 | A short gap shortens the tail rather than overrunning it |
| `analysis/punch_out_detection.feature` | 82 | No quiet margin is available |
| `analysis/punch_out_detection.feature` | 118 | The punch-out would land before the punch-in |
| `analysis/punch_out_detection.feature` | 111 | The recording stops before the teaching ends |
| `analysis/punch_out_detection.feature` | 21 | The tail matches what the editor actually leaves |
| `analysis/segment_proposal.feature` | 107 | An opening prayer is not swallowed |
| `analysis/segment_proposal.feature` | 209 | Segment length is sanity-checked |
| `analysis/segment_proposal.feature` | 156 | Some properties hold of every cut, whichever path produced it |
| `analysis/segment_proposal.feature` | 78 | The closing prayer is included |
| `analysis/segment_proposal.feature` | 93 | What stops the extension |
| `analysis/speaker_diarization.feature` | 81 | A guest preacher matches nobody |
| `analysis/speaker_diarization.feature` | 49 | A typical service with several voices |
| `analysis/speaker_diarization.feature` | 96 | Congregational singing confuses speaker detection |
| `analysis/speaker_diarization.feature` | 112 | Diarization fails |
| `analysis/speaker_diarization.feature` | 57 | Segments are joined to the transcript |
| `analysis/speaker_diarization.feature` | 63 | The preacher is recognised across weeks |
| `analysis/speaker_diarization.feature` | 103 | The scripture reader and the preacher are the same person |
| `analysis/speaker_diarization.feature` | 89 | Two speakers overlap |
| `analysis/summarization.feature` | 54 | A cue is a verbatim quote, located afterwards |
| `analysis/summarization.feature` | 122 | The model may live on a different machine |
| `analysis/summarization.feature` | 65 | The quote cannot be located |
| `analysis/transcription.feature` | 94 | A very long recording |
| `analysis/transcription.feature` | 50 | Audio conditions that degrade recognition |
| `analysis/transcription.feature` | 43 | Long silences produce no utterances |
| `analysis/transcription.feature` | 35 | Music is transcribed as noise |
| `analysis/transcription.feature` | 86 | The transcription model may live on a different machine |
| `analysis/transcription.feature` | 18 | Transcribing a full service |
| `ingestion/webhook_notification.feature` | 68 | The webhook races the reconciliation scan |
| `interface/approval.feature` | 120 | Nothing renders without an explicit approval |
| `interface/authentication.feature` | 58 | The reviewer identity is a seam, not a constant |
| `interface/discarding_recordings.feature` | 60 | Discarding a recording with a published segment |
| `interface/recording_detail.feature` | 18 | Viewing technical and source metadata |
| `interface/recording_list.feature` | 99 | Filtering by what is inside |
| `interface/waveform_review.feature` | 280 | Precision by window size |
| `notifications/approval_notifications.feature` | 80 | A low-confidence proposal says so |
| `notifications/approval_notifications.feature` | 36 | No channel configured |
| `notifications/approval_notifications.feature` | 51 | Notifications are visible in the interface regardless |
| `operations/system_health.feature` | 10 | Viewing system health |
| `processing/artifact_downloads.feature` | 73 | Downloads can be resumed |
| `processing/processing_orchestration.feature` | 68 | A transient failure is retried |

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
- `analysis/detection_accuracy.feature:117 then the proportion approved with no edit is reported from the approval record, not from this run`
- `analysis/detection_accuracy.feature:118 then it reports the median and worst-case error, split by difficulty`
- `analysis/detection_accuracy.feature:122 then the corpus includes sermons and class sessions`
- `analysis/detection_accuracy.feature:123 then accuracy is reported separately for each classification`
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
- `analysis/detection_accuracy.feature:272 then it reports that it was skipped`
- `analysis/detection_accuracy.feature:273 then it does not report a pass`
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
- `ingestion/webhook_notification.feature:79 then a Recording is uniquely identified by its bucket and object key`
- `ingestion/webhook_notification.feature:80 then the same key always refers to the same audio`
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
- `interface/punch_point_adjustment.feature:129 then the punch-in moves to the nearest silence gap boundary`
- `interface/punch_point_adjustment.feature:130 then the amount it moved is shown`
- `interface/punch_point_adjustment.feature:146 then I am warned that the cut is too close to the audio`
- `interface/punch_point_adjustment.feature:147 then I am offered the nearest point with a 250 ms margin`
- `interface/punch_point_adjustment.feature:148 then I can override the warning if I mean it`
- `interface/punch_point_adjustment.feature:160 given the teaching begins with "good morning"`
- `interface/punch_point_adjustment.feature:162 then the punch-in lands immediately before "good morning"`
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
- `interface/waveform_review.feature:329 given the configured model endpoint does not answer`
- `interface/waveform_review.feature:330 then reviewing, adjusting and approving continue to work`
- `interface/waveform_review.feature:331 then only the actions that need a model are shown as unavailable`
- `interface/waveform_review.feature:332 then the reason names the endpoint rather than blaming the Recording`
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
- `processing/audio_rendering.feature:110 then there is one set of loudness settings, not a normalize toggle and a compress toggle`
- `processing/audio_rendering.feature:111 then the settings used are recorded on every rendered Segment`
- `processing/audio_rendering.feature:112 then changing them is what makes a re-render meaningful`
- `processing/audio_rendering.feature:155 then bitrate, channel layout and sample rate are configuration, not code`
- `processing/audio_rendering.feature:156 then changing them is a re-render, never a re-analysis`
- `processing/audio_rendering.feature:182 given a rendered MP3`
- `processing/audio_rendering.feature:183 when a reviewer listens to it end to end`
- `processing/audio_rendering.feature:184 then the speech is intelligible throughout`
- `processing/audio_rendering.feature:185 then there are no clicks, dropouts or pumping artifacts`
- `processing/audio_rendering.feature:186 then it sits at a comparable volume to other recent sermons`
- `processing/audio_rendering.feature:31 given the probe flagged the Recording "unexpected stereo content"`
- `processing/audio_rendering.feature:33 then the render does not start automatically`
- `processing/audio_rendering.feature:34 then the reviewer is asked how the channels should be treated`
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
- `processing/reprocessing.feature:58 when the change is saved`
- `processing/reprocessing.feature:59 then the MP3 audio is not re-encoded`
- `processing/reprocessing.feature:60 then the downloadable filename reflects the corrected label`
- `processing/reprocessing.feature:70 then only the most recent MP3 is stored`
- `processing/reprocessing.feature:71 then the earlier render is deleted`
- `processing/reprocessing.feature:76 when I view its history`
- `processing/reprocessing.feature:77 then I see each set of boundaries with who approved them and when`
- `processing/reprocessing.feature:78 then I see the loudness and encoding settings used for each render`
- `processing/reprocessing.feature:79 then any past render could be reproduced from that record and the source`
- `processing/reprocessing.feature:83 then the interface does not offer to restore an earlier render`
- `processing/reprocessing.feature:84 then the stored history is what makes adding that later possible`
