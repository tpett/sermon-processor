# Step integrity

Regenerate with `.venv/bin/python tests/step_integrity.py`. Hand edits are lost.

## What the guard found

- 1641 step definitions read from `tests/steps`
- 534 condemned
- 233 of 456 non-deferred scenarios rest on at least one condemned step
- 291 of 597 expanded scenario tests likewise
- 143 scenarios whose every Then is condemned, so nothing they claim is checked
- 46 scenarios whose every step outside the Background is condemned
- 6 scenarios whose every step, Background included, is condemned
- 57 Gherkin steps matched more than one definition
- 0 Gherkin steps matched no definition

## Faults by kind

| fault | count |
| --- | --- |
| a Then with an empty body | 275 |
| a Then whose body never asserts | 67 |
| an assertion that cannot fail | 107 |
| a boolean operand of True, which neutralises what it joins | 21 |
| a When with an empty body | 36 |
| a When whose body never acts | 6 |
| an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate | 41 |
| a step that skips or xfails instead of running | 0 |
| a step name the guard cannot read from the source | 0 |
| a step decorator that declares no Given, When or Then | 0 |

## Modules

| module | definitions | condemned | verdict |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py` | 63 | 2 | partly condemned |
| `tests/steps/analysis/audio_probe_steps.py` | 46 | 1 | partly condemned |
| `tests/steps/analysis/domain_steps.py` | 221 | 16 | partly condemned |
| `tests/steps/analysis/preview_audio_steps.py` | 31 | 2 | partly condemned |
| `tests/steps/analysis/remaining_analysis_steps.py` | 335 | 137 | partly condemned |
| `tests/steps/analysis/waveform_generation_steps.py` | 14 | 0 | sound |
| `tests/steps/catch_all_thens.py` (named) | 96 | 93 | partly condemned |
| `tests/steps/discovery_steps.py` | 2 | 0 | sound |
| `tests/steps/generated_remaining.py` (named) | 68 | 68 | wholly condemned |
| `tests/steps/generated_remaining2.py` (named) | 42 | 42 | wholly condemned |
| `tests/steps/generated_remaining3.py` (named) | 25 | 25 | wholly condemned |
| `tests/steps/ingestion/recording_download_steps.py` | 42 | 0 | sound |
| `tests/steps/ingestion/s3_reconciliation_steps.py` | 31 | 1 | partly condemned |
| `tests/steps/ingestion/webhook_notification_steps.py` | 42 | 8 | partly condemned |
| `tests/steps/interface/approval_steps.py` | 45 | 2 | partly condemned |
| `tests/steps/interface/authentication_steps.py` | 8 | 0 | sound |
| `tests/steps/interface/discarding_steps.py` | 20 | 2 | partly condemned |
| `tests/steps/interface/publication_details_steps.py` | 10 | 0 | sound |
| `tests/steps/interface/punch_nudge_steps.py` | 7 | 0 | sound |
| `tests/steps/interface/punch_point_adjustment_steps.py` | 8 | 0 | sound |
| `tests/steps/interface/recording_detail_steps.py` | 20 | 6 | partly condemned |
| `tests/steps/interface/recording_list_steps.py` | 37 | 2 | partly condemned |
| `tests/steps/interface/segment_review_steps.py` | 19 | 0 | sound |
| `tests/steps/interface/waveform_steps.py` | 63 | 16 | partly condemned |
| `tests/steps/last_fourteen.py` (named) | 24 | 13 | partly condemned |
| `tests/steps/nested/discovery_steps.py` | 1 | 0 | sound |
| `tests/steps/notifications/analysis_notification_steps.py` | 24 | 1 | partly condemned |
| `tests/steps/notifications/notification_steps.py` | 15 | 7 | partly condemned |
| `tests/steps/operations/health_steps.py` | 17 | 0 | sound |
| `tests/steps/operations/job_queue_steps.py` | 14 | 1 | partly condemned |
| `tests/steps/processing/artifact_downloads_steps.py` | 19 | 4 | partly condemned |
| `tests/steps/processing/processing_orchestration_steps.py` | 17 | 2 | partly condemned |
| `tests/steps/remaining_steps.py` (named) | 215 | 83 | partly condemned |

## Condemned outside the six named files

210 definitions.

| location | kind | step | faults |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py:333` | then | `they can be revisited and approved months later` | a Then whose body never asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:469` | then | `the stage is retried` | a Then whose body never asserts |
| `tests/steps/analysis/audio_probe_steps.py:281` | then | `a reviewer can restore it for analysis if the machine was wrong` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:233` | then | `no audio leaves the local network` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:278` | then | `the stage is retried with backoff` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:377` | then | `it is combined with duration before a Segment is proposed` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:495` | then | `classification does not penalise it for being an unknown voice` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:922` | then | `a Block may be typed "{block_type}" meaning "{meaning}"` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:968` | given | `a Recording containing a normal Sunday service` | a boolean operand of True, which neutralises what it joins |
| `tests/steps/analysis/domain_steps.py:1120` | then | `each proposed Segment carries its own summary` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1128` | then | `the summary is shown beside it in the review interface` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1133` | then | `it is shown in the notification` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1190` | then | `the reviewer can correct it` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1196` | then | `the model returns the exact words of the recognisable moment` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1207` | then | `the excerpt's timing comes from the transcript, never from the model` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1228` | then | `the failure is counted, so a model that drifts is visible` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1311` | then | `the punch-in is placed at least 250 ms away from the nearest audible sound` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1316` | then | `the resulting transition sounds natural rather than abrupt` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1357` | then | `the reviewer can move it in steps as small as 100 ms` | an assertion that cannot fail |
| `tests/steps/analysis/preview_audio_steps.py:81` | then | `playback begins within 2 seconds` | a Then with an empty body |
| `tests/steps/analysis/preview_audio_steps.py:86` | then | `the earlier part of the recording is never downloaded` | a Then with an empty body |
| `tests/steps/analysis/remaining_analysis_steps.py:720` | then | `the suite is a regression instrument, not an acceptance test` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:745` | then | `the punch-out is placed at least 250 ms away from the nearest audible sound` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:750` | then | `the headline measure is the proportion of Segments approved with no boundary edit` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:787` | then | `the corpus includes sermons and class sessions` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:793` | then | `punch-in error is reported with its sign, never as an absolute value` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:809` | then | `no cue excerpt begins or ends inside a silence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:814` | then | `no boundary, classification or disposition depends on a summary` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:819` | then | `every Segment records whether its boundaries were proposed or refined` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:872` | then | `each carries the evidence that produced it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:926` | then | `downstream Segment proposal uses the reviewer's type` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:982` | then | `the reviewer can merge two adjacent Segments` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:987` | then | `the reviewer can draw a Segment by hand` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:992` | then | `the resulting Segment is indistinguishable from a machine-proposed one` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1010` | then | `a reviewable Segment is still proposed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1015` | then | `the reviewer can still approve a cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1020` | then | `the first words of the teaching are not clipped` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1025` | then | `starting a little early is preferred to clipping` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1036` | then | `the Segment is flagged that the opening was missed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1042` | then | `the reviewer is warned the opening was not captured` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1054` | then | `the Segment is flagged that the ending was missed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1065` | then | `the failure is recorded` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1070` | then | `the candidate is moved to the nearest word boundary` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1081` | then | `the reviewer is told Analysis ran once` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1086` | then | `they are told a second opinion is not in this version` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1091` | then | `the list row for the Recording shows the best Segment's confidence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1098` | then | `a Recording with no Segments shows as having nothing to publish` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1103` | then | `the reviewer is not asked to treat the number as a quality score` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1160` | then | `a change that worsens the error distribution is reported as a regression` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1171` | then | `a Segment is proposed for each sustained teaching Block` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1176` | then | `a Segment is still seeded on it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1181` | then | `a self-reported confidence may be stored for diagnosis` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1186` | then | `accuracy is reported separately for each classification` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1191` | then | `correctness is established by the accuracy suite instead` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1196` | then | `cut difficulty remains the signal that asks for a listen` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1201` | then | `each Block gains confidence from its position in the order` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1206` | then | `each boundary's difficulty comes from the audio around the human cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1211` | then | `each pair is graded against the difficulty of its own transition` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1216` | then | `exactly one analysis informs the Proposal` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1221` | then | `for each pair it reports:` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1226` | then | `its teaching Blocks are typed "{block_type}"` | a boolean operand of True, which neutralises what it joins |
| `tests/steps/analysis/remaining_analysis_steps.py:1235` | then | `late punch-ins are reported separately from early ones` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1240` | then | `starting shortly after the usual service time counts as evidence for teaching` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1245` | then | `that counts as evidence for "rehearsal"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1250` | then | `that following Block is strong evidence for "sermon"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1255` | then | `that recording and the approved boundaries can be added to the corpus` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1272` | then | `the confidence that the Block is teaching is increased` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1278` | then | `the Segment ends at the end of the sermon Block` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1296` | then | `the suite does not require the machine to match the human exactly` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1331` | then | `the Recording is summarised as "{summary}" rather than as "{other}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1337` | then | `the Recording is summarised as "{summary}" rather than as a list of Block types` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1343` | then | `the cue excerpt is chosen from "{source}"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1348` | then | `a hard punch-out is flagged for review` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1354` | then | `a legitimate untrimmed archive is flagged the same way` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1359` | then | `a margin is left so that no part of the next Block is audible` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1364` | then | `a wrong summary can mislead a reviewer but cannot produce a wrong file` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1369` | then | `boundary detection continues using transcript evidence alone` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1374` | then | `confidence is computed from these inputs only:` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1379` | then | `each is reviewed on its own` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1384` | then | `it counts toward the proportion approved with no edit` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1389` | then | `it is never shown to a reviewer as a quality signal` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1394` | then | `it is never treated as evidence that the output is correct` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1399` | then | `it is reported alongside the raw error figures, not instead of them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1409` | then | `it reports that it was skipped` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1414` | then | `it reports the proportion approved with no edit` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1419` | then | `it requires that the Segment was flagged as needing attention` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1431` | then | `no configuration is rejected for missing a fixed tolerance` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1436` | then | `no cue excerpt is chosen from a span with no speech` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1441` | then | `no flag is raised` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1446` | then | `no speaker change is detected at the sermon start` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1451` | then | `no third-party API is called` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1456` | then | `results are reported separately for easy and hard cuts` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1461` | then | `Segment proposal runs again for the affected Blocks` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1466` | then | `summaries are produced at whatever quality that model gives` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1471` | then | `summaries fall back to heuristics drawn from the transcript` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1476` | then | `that is visible in the processing log` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1481` | then | `that shape counts as evidence for "qa"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1486` | then | `the affected confidence is reduced` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1491` | then | `the corpus grows without anyone hand-labelling anything` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1496` | then | `the evidence includes "sustained single-speaker teaching"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1501` | then | `the evidence names the matched speaker` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1506` | then | `the excerpt is between 3 and 10 seconds long` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1511` | then | `the grade is shown to the reviewer` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1516` | then | `the later prayer is not included` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1521` | then | `the overlap is resolved before the Proposal is offered` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1526` | then | `the proposal is treated as implausible` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1531` | then | `the punch-in does not fall inside a word` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1536` | then | `the punch-in error is weighted more heavily in the headline figure` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1541` | then | `the punch-in falls at the start of it` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1546` | then | `the punch-in is moved to the nearest preceding silence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1551` | then | `the punch-in is placed immediately before "{phrase}"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1556` | then | `the punch-in is placed immediately before that phrase` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1561` | then | `the punch-in is still placed before the first words` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1566` | then | `the punch-out is moved to after the word ends` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1571` | then | `the punch-out is placed at the quietest available point` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1576` | then | `the reason is stated, for example "no clean cut point at the punch-out"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1581` | then | `the refinement is rejected` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1586` | then | `the refinement rules are applied instead` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1591` | then | `the result is graded as needing correction` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1596` | then | `the resulting ending sounds natural rather than clipped` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1601` | then | `the reviewer decides what to publish, as with any other Recording` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1606` | then | `any boundary the reviewer set by hand is preserved` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1612` | then | `it is flagged as needing the reviewer to look at it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1618` | then | `the evidence states which corroboration was missing` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1623` | then | `the Block is flagged as possibly containing more than one type` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1643` | then | `the interface shows them grouped by day` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1650` | then | `the reviewer is told they may be parts of one event` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1655` | then | `it is flagged "{flag}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1671` | then | `it is classified on its own evidence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1686` | then | `a configuration cannot change the difficulty of anything it is scored on` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1691` | then | `a hard punch-out is treated as less urgent than a hard punch-in` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1696` | then | `a poor result on a hard cut is not treated the same as one on an easy cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1701` | then | `boundary detection must fall back to other evidence` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1706` | then | `it does not become a labelled example` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1711` | then | `it does not count toward the no-edit proportion` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1716` | then | `it does not report a pass` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1721` | then | `it is chosen to be immediately recognisable rather than simply the first seconds` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1726` | then | `it reports the median and worst-case error, split by difficulty` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1745` | then | `no agreement badge is shown` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1750` | then | `no two Segments share any audio` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1762` | then | `that counts as evidence for the punch-in` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1767` | then | `the evidence includes "{text}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1772` | then | `the evidence list states that "{name}" was unavailable` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1777` | then | `the final word is complete in the output` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1782` | then | `the Proposal is marked as "no speaker evidence"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1787` | then | `the punch-out does not fall inside a word` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1808` | then | `the reviewer is expected to confirm it with a single preview` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1813` | then | `the reviewer is told the summaries are heuristic` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1818` | then | `the reviewer's correction, not the tolerance, is what guarantees the cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1828` | then | `the Segment records that its boundaries came from the rules` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1833` | then | `the silence does not create a Block boundary` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1838` | then | `the system does not fall back to a hosted service to improve them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1965` | then | `it is reported alongside the raw error figures, not replaced by them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1986` | then | `the punch-in error is weighted more heavily in the headline score` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1991` | then | `both are still reported separately` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1996` | then | `the change in median and worst-case error is reported` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:2001` | then | `a change that improves the median but worsens the worst case is visible as such` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:2173` | then | `Blocks are labelled by type alone` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/ingestion/s3_reconciliation_steps.py:145` | then | `the next scheduled scan runs normally` | a Then whose body never asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:177` | then | `a Recording is uniquely identified by its bucket and object key` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:182` | then | `the same key always refers to the same audio` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:235` | given | `the Sermon Processor is unreachable` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/ingestion/webhook_notification_steps.py:240` | when | `the Recorder attempts to deliver a webhook` | a When with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:245` | then | `the Recorder retries with exponential backoff` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:250` | then | `after the retry budget is exhausted the Recorder records a delivery failure` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:255` | then | `the Recording is still ingested later by S3 reconciliation` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:270` | given | `it contains a bucket "{bucket}"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/approval_steps.py:245` | then | `I can change it to "archive" before approving` | a Then whose body never asserts |
| `tests/steps/interface/approval_steps.py:263` | then | `no Segment is ever published on classification alone` | a Then with an empty body |
| `tests/steps/interface/discarding_steps.py:204` | then | `its Segments are intact` | a Then whose body never asserts |
| `tests/steps/interface/discarding_steps.py:209` | then | `the source object in the object store is untouched` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:97` | then | `I see:` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/recording_detail_steps.py:120` | then | `it explains that this originates at the recorder and cannot be repaired here` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:147` | then | `I see which stages have completed` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:157` | then | `I see the failure reason` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/recording_detail_steps.py:162` | then | `I can retry Analysis` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:167` | then | `I can create a Segment by hand instead` | a Then with an empty body |
| `tests/steps/interface/recording_list_steps.py:234` | then | `I can search by date, by classification, and by what was said` | a Then with an empty body |
| `tests/steps/interface/recording_list_steps.py:323` | then | `the page loads in under 2 seconds` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:179` | then | `hovering a marker describes the evidence` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:184` | then | `clicking a marker seeks the player to that point` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:195` | then | `each speaker span is coloured by speaker` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:225` | when | `I choose to preview the punch-in` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:249` | when | `I choose to preview the cut` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:279` | then | `only the region being played is fetched` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:284` | then | `playback begins within 2 seconds of pressing play` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:289` | when | `I zoom the detail view into the punch-in` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:309` | when | `I click a point on the overview` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:357` | when | `I zoom in around a boundary` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:362` | then | `a {amount} gap is {pixels} of the detail view` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/waveform_steps.py:367` | then | `that is "{feel}"` | an assertion that cannot fail |
| `tests/steps/interface/waveform_steps.py:430` | given | `the teaching begins with "good morning"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:435` | given | `the opening contains a throat-clear before the first real words` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:440` | given | `I am viewing the whole recording at overview resolution` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:468` | when | `I try to set a span shorter than 1 second` | a When whose body never acts |
| `tests/steps/notifications/analysis_notification_steps.py:225` | then | `it states why confidence is low` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:14` | given | `no delivery channel is configured` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/notifications/notification_steps.py:100` | then | `nothing fails` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:105` | then | `delivering a Notification is separate from creating one` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:110` | then | `adding or changing a channel does not change when Notifications are raised` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:115` | then | `the same Notification can be delivered by more than one channel` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:120` | when | `I open the interface` | a When with an empty body |
| `tests/steps/notifications/notification_steps.py:125` | then | `I see the Notifications raised for me` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/operations/job_queue_steps.py:196` | when | `the application restarts` | a When with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:151` | then | `I can download "{artifact}"` | an assertion that cannot fail |
| `tests/steps/processing/artifact_downloads_steps.py:156` | then | `I can read its transcript without downloading anything` | a Then with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:161` | then | `the transcript covers the approved span` | a Then with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:166` | then | `I can expand to the full Recording transcript` | a Then with an empty body |
| `tests/steps/processing/processing_orchestration_steps.py:177` | then | `a failure in one does not affect the other` | a Then with an empty body |
| `tests/steps/processing/processing_orchestration_steps.py:182` | then | `the reviewer can continue working with other Recordings and Segments` | a Then with an empty body |

## Every condemned definition

| location | kind | step | faults |
| --- | --- | --- | --- |
| `tests/steps/analysis/analysis_orchestration_steps.py:333` | then | `they can be revisited and approved months later` | a Then whose body never asserts |
| `tests/steps/analysis/analysis_orchestration_steps.py:469` | then | `the stage is retried` | a Then whose body never asserts |
| `tests/steps/analysis/audio_probe_steps.py:281` | then | `a reviewer can restore it for analysis if the machine was wrong` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:233` | then | `no audio leaves the local network` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:278` | then | `the stage is retried with backoff` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:377` | then | `it is combined with duration before a Segment is proposed` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:495` | then | `classification does not penalise it for being an unknown voice` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:922` | then | `a Block may be typed "{block_type}" meaning "{meaning}"` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:968` | given | `a Recording containing a normal Sunday service` | a boolean operand of True, which neutralises what it joins |
| `tests/steps/analysis/domain_steps.py:1120` | then | `each proposed Segment carries its own summary` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1128` | then | `the summary is shown beside it in the review interface` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1133` | then | `it is shown in the notification` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1190` | then | `the reviewer can correct it` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1196` | then | `the model returns the exact words of the recognisable moment` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1207` | then | `the excerpt's timing comes from the transcript, never from the model` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1228` | then | `the failure is counted, so a model that drifts is visible` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1311` | then | `the punch-in is placed at least 250 ms away from the nearest audible sound` | a Then whose body never asserts |
| `tests/steps/analysis/domain_steps.py:1316` | then | `the resulting transition sounds natural rather than abrupt` | an assertion that cannot fail |
| `tests/steps/analysis/domain_steps.py:1357` | then | `the reviewer can move it in steps as small as 100 ms` | an assertion that cannot fail |
| `tests/steps/analysis/preview_audio_steps.py:81` | then | `playback begins within 2 seconds` | a Then with an empty body |
| `tests/steps/analysis/preview_audio_steps.py:86` | then | `the earlier part of the recording is never downloaded` | a Then with an empty body |
| `tests/steps/analysis/remaining_analysis_steps.py:720` | then | `the suite is a regression instrument, not an acceptance test` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:745` | then | `the punch-out is placed at least 250 ms away from the nearest audible sound` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:750` | then | `the headline measure is the proportion of Segments approved with no boundary edit` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:787` | then | `the corpus includes sermons and class sessions` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:793` | then | `punch-in error is reported with its sign, never as an absolute value` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:809` | then | `no cue excerpt begins or ends inside a silence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:814` | then | `no boundary, classification or disposition depends on a summary` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:819` | then | `every Segment records whether its boundaries were proposed or refined` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:872` | then | `each carries the evidence that produced it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:926` | then | `downstream Segment proposal uses the reviewer's type` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:982` | then | `the reviewer can merge two adjacent Segments` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:987` | then | `the reviewer can draw a Segment by hand` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:992` | then | `the resulting Segment is indistinguishable from a machine-proposed one` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1010` | then | `a reviewable Segment is still proposed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1015` | then | `the reviewer can still approve a cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1020` | then | `the first words of the teaching are not clipped` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1025` | then | `starting a little early is preferred to clipping` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1036` | then | `the Segment is flagged that the opening was missed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1042` | then | `the reviewer is warned the opening was not captured` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1054` | then | `the Segment is flagged that the ending was missed` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1065` | then | `the failure is recorded` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1070` | then | `the candidate is moved to the nearest word boundary` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1081` | then | `the reviewer is told Analysis ran once` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1086` | then | `they are told a second opinion is not in this version` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1091` | then | `the list row for the Recording shows the best Segment's confidence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1098` | then | `a Recording with no Segments shows as having nothing to publish` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1103` | then | `the reviewer is not asked to treat the number as a quality score` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1160` | then | `a change that worsens the error distribution is reported as a regression` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1171` | then | `a Segment is proposed for each sustained teaching Block` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1176` | then | `a Segment is still seeded on it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1181` | then | `a self-reported confidence may be stored for diagnosis` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1186` | then | `accuracy is reported separately for each classification` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1191` | then | `correctness is established by the accuracy suite instead` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1196` | then | `cut difficulty remains the signal that asks for a listen` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1201` | then | `each Block gains confidence from its position in the order` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1206` | then | `each boundary's difficulty comes from the audio around the human cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1211` | then | `each pair is graded against the difficulty of its own transition` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1216` | then | `exactly one analysis informs the Proposal` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1221` | then | `for each pair it reports:` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1226` | then | `its teaching Blocks are typed "{block_type}"` | a boolean operand of True, which neutralises what it joins |
| `tests/steps/analysis/remaining_analysis_steps.py:1235` | then | `late punch-ins are reported separately from early ones` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1240` | then | `starting shortly after the usual service time counts as evidence for teaching` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1245` | then | `that counts as evidence for "rehearsal"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1250` | then | `that following Block is strong evidence for "sermon"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1255` | then | `that recording and the approved boundaries can be added to the corpus` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1272` | then | `the confidence that the Block is teaching is increased` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1278` | then | `the Segment ends at the end of the sermon Block` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1296` | then | `the suite does not require the machine to match the human exactly` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1331` | then | `the Recording is summarised as "{summary}" rather than as "{other}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1337` | then | `the Recording is summarised as "{summary}" rather than as a list of Block types` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1343` | then | `the cue excerpt is chosen from "{source}"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1348` | then | `a hard punch-out is flagged for review` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1354` | then | `a legitimate untrimmed archive is flagged the same way` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1359` | then | `a margin is left so that no part of the next Block is audible` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1364` | then | `a wrong summary can mislead a reviewer but cannot produce a wrong file` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1369` | then | `boundary detection continues using transcript evidence alone` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1374` | then | `confidence is computed from these inputs only:` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1379` | then | `each is reviewed on its own` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1384` | then | `it counts toward the proportion approved with no edit` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1389` | then | `it is never shown to a reviewer as a quality signal` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1394` | then | `it is never treated as evidence that the output is correct` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1399` | then | `it is reported alongside the raw error figures, not instead of them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1409` | then | `it reports that it was skipped` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1414` | then | `it reports the proportion approved with no edit` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1419` | then | `it requires that the Segment was flagged as needing attention` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1431` | then | `no configuration is rejected for missing a fixed tolerance` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1436` | then | `no cue excerpt is chosen from a span with no speech` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1441` | then | `no flag is raised` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1446` | then | `no speaker change is detected at the sermon start` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1451` | then | `no third-party API is called` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1456` | then | `results are reported separately for easy and hard cuts` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1461` | then | `Segment proposal runs again for the affected Blocks` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1466` | then | `summaries are produced at whatever quality that model gives` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1471` | then | `summaries fall back to heuristics drawn from the transcript` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1476` | then | `that is visible in the processing log` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1481` | then | `that shape counts as evidence for "qa"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1486` | then | `the affected confidence is reduced` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1491` | then | `the corpus grows without anyone hand-labelling anything` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1496` | then | `the evidence includes "sustained single-speaker teaching"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1501` | then | `the evidence names the matched speaker` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1506` | then | `the excerpt is between 3 and 10 seconds long` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1511` | then | `the grade is shown to the reviewer` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1516` | then | `the later prayer is not included` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1521` | then | `the overlap is resolved before the Proposal is offered` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1526` | then | `the proposal is treated as implausible` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1531` | then | `the punch-in does not fall inside a word` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1536` | then | `the punch-in error is weighted more heavily in the headline figure` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1541` | then | `the punch-in falls at the start of it` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1546` | then | `the punch-in is moved to the nearest preceding silence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1551` | then | `the punch-in is placed immediately before "{phrase}"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1556` | then | `the punch-in is placed immediately before that phrase` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1561` | then | `the punch-in is still placed before the first words` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1566` | then | `the punch-out is moved to after the word ends` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1571` | then | `the punch-out is placed at the quietest available point` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1576` | then | `the reason is stated, for example "no clean cut point at the punch-out"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1581` | then | `the refinement is rejected` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1586` | then | `the refinement rules are applied instead` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1591` | then | `the result is graded as needing correction` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1596` | then | `the resulting ending sounds natural rather than clipped` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1601` | then | `the reviewer decides what to publish, as with any other Recording` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1606` | then | `any boundary the reviewer set by hand is preserved` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1612` | then | `it is flagged as needing the reviewer to look at it` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1618` | then | `the evidence states which corroboration was missing` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1623` | then | `the Block is flagged as possibly containing more than one type` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1643` | then | `the interface shows them grouped by day` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1650` | then | `the reviewer is told they may be parts of one event` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1655` | then | `it is flagged "{flag}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1671` | then | `it is classified on its own evidence` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1686` | then | `a configuration cannot change the difficulty of anything it is scored on` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1691` | then | `a hard punch-out is treated as less urgent than a hard punch-in` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1696` | then | `a poor result on a hard cut is not treated the same as one on an easy cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1701` | then | `boundary detection must fall back to other evidence` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1706` | then | `it does not become a labelled example` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1711` | then | `it does not count toward the no-edit proportion` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1716` | then | `it does not report a pass` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1721` | then | `it is chosen to be immediately recognisable rather than simply the first seconds` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1726` | then | `it reports the median and worst-case error, split by difficulty` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1745` | then | `no agreement badge is shown` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1750` | then | `no two Segments share any audio` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1762` | then | `that counts as evidence for the punch-in` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1767` | then | `the evidence includes "{text}"` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1772` | then | `the evidence list states that "{name}" was unavailable` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1777` | then | `the final word is complete in the output` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1782` | then | `the Proposal is marked as "no speaker evidence"` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1787` | then | `the punch-out does not fall inside a word` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1808` | then | `the reviewer is expected to confirm it with a single preview` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1813` | then | `the reviewer is told the summaries are heuristic` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1818` | then | `the reviewer's correction, not the tolerance, is what guarantees the cut` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1828` | then | `the Segment records that its boundaries came from the rules` | a Then whose body never asserts |
| `tests/steps/analysis/remaining_analysis_steps.py:1833` | then | `the silence does not create a Block boundary` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1838` | then | `the system does not fall back to a hosted service to improve them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1965` | then | `it is reported alongside the raw error figures, not replaced by them` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1986` | then | `the punch-in error is weighted more heavily in the headline score` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1991` | then | `both are still reported separately` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:1996` | then | `the change in median and worst-case error is reported` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:2001` | then | `a change that improves the median but worsens the worst case is visible as such` | an assertion that cannot fail |
| `tests/steps/analysis/remaining_analysis_steps.py:2173` | then | `Blocks are labelled by type alone` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/catch_all_thens.py:4` | then | `I am told the boundary must fall within the Segment` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:9` | then | `the punch-out is visibly not the focused boundary` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:14` | then | `the punch-out becomes the boundary the keyboard moves` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:19` | then | `the segment length updates to "{length}"` | an assertion that cannot fail |
| `tests/steps/catch_all_thens.py:24` | then | `the amount it moved is shown` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:29` | then | `I am offered the nearest point with a 250 ms margin` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:34` | then | `I can drop a boundary into one with a single click` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:39` | then | `the punch-in lands immediately before "good morning"` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:44` | then | `the adjustment is accepted without warning` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:49` | then | `I can see exactly which word each boundary falls before or after` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:54` | then | `the Block types and summaries are shown instead` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:59` | then | `I am told the punch-out must be after the punch-in` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:64` | then | `I am told the selection is too short` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:69` | then | `I am warned that the length is outside the expected range` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:81` | then | `my discarded adjustment is recorded in the history` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:86` | then | `my adjustment survives` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:91` | then | `the other Segment's boundaries are unchanged` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:96` | then | `I am told the whole span will be kept` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:101` | then | `it is flagged "no substantive content" and marked ignored` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:106` | then | `it is analysed normally` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:111` | then | `the file is streamed` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:116` | then | `the download continues from where it stopped` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:121` | then | `it is fetched from the object store` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:126` | then | `I am told the artifact is unavailable` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:131` | then | `recordings still appear in the recordings list` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:136` | then | `the two output files do not collide` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:141` | then | `the output file is named from the recording date` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:146` | then | `the stored details are updated` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:151` | then | `the previously approved boundaries are shown as the starting point` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:156` | then | `the new MP3 replaces the previous one` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:161` | then | `it is still downloadable` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:166` | then | `the other Segment stays "complete"` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:171` | then | `the boundaries are unchanged` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:176` | then | `I am not prompted for anything else` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:181` | then | `the application does not load the whole file into memory` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:186` | then | `the quiet passages are audible at a normal listening volume` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:191` | then | `the loudest passages are not clipped` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:196` | then | `no separate compression stage is applied` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:201` | then | `their output integrated loudness values are within 1 LU of each other` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:206` | then | `the output integrated loudness still meets the target` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:211` | then | `the isolated peak is limited rather than allowed to set the level` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:216` | then | `the output is brought down to the target loudness and peak ceiling` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:221` | then | `no attempt is made to reconstruct the clipped peaks` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:226` | then | `the Segment records that the source was clipped` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:231` | then | `the output reaches the target loudness` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:236` | then | `the noise floor is not raised to a distracting level` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:241` | then | `the Segment is flagged "source was very quiet"` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:246` | given | `two Segments whose sources differ in loudness by 8 LU` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:251` | when | `both are rendered` | a When with an empty body |
| `tests/steps/catch_all_thens.py:256` | given | `the Segment contains one isolated peak 12 dB above the speech level` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:261` | given | `the Segment contains passages 18 dB quieter than the loudest passage` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:266` | then | `the render does not start automatically` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:271` | then | `the reviewer is asked how the channels should be treated` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:276` | given | `the probe flagged the Recording "unexpected stereo content"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:281` | then | `I see every Block in order with its type and its one-line summary` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/catch_all_thens.py:286` | then | `I can see the whole shape of the service without playing anything` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:291` | when | `I press Preview on a Block` | a When with an empty body |
| `tests/steps/catch_all_thens.py:296` | then | `playback starts at that Block's cue excerpt` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:301` | then | `it stops at the end of the excerpt` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:306` | then | `a few seconds is enough for me to recognise what the Block is` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:311` | when | `I press Preview on a Segment` | a When with an empty body |
| `tests/steps/catch_all_thens.py:316` | then | `playback starts at the cue excerpt of its seeding Block` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:321` | then | `I can tell whether this is the message I meant to publish` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:326` | when | `I choose to start playback at a specific Block` | a When with an empty body |
| `tests/steps/catch_all_thens.py:331` | then | `playback seeks there rather than to the cue excerpt` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:336` | then | `all Blocks are drawn on a single waveform of the whole Recording` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/catch_all_thens.py:341` | then | `each is coloured by its type` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:346` | then | `clicking one selects it for review` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:351` | then | `the Segment most likely to be the sermon is expanded by default` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:356` | given | `I have selected a Segment` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:361` | given | `a Segment whose teaching voice matches no enrolled profile` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:366` | when | `I confirm or correct who was preaching` | a When with an empty body |
| `tests/steps/catch_all_thens.py:371` | then | `the music Blocks are shown in the anatomy of the Recording` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:391` | given | `a Segment was skipped 2 years ago` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:396` | given | `a Segment has been re-rendered` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/catch_all_thens.py:401` | then | `the two previews are the primary controls` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:406` | then | `Approve is the third control` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:411` | then | `the waveform editor is not required` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:416` | then | `I am taken into the waveform editor` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:421` | then | `the three-click controls are not the path` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:426` | then | `Analysis does not need to run again` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:431` | then | `Blocks and Segments are listed with their timecodes instead of drawn` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:436` | then | `I can correlate an entry to the application logs` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:441` | then | `I can discard the Recording in one action` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:446` | then | `I can preview the punch-in and the punch-out` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:451` | then | `I see who performed each human action, against which Segment` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:456` | then | `its intent is "archive"` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:461` | then | `the bitrate is variable, averaging between 96 and 108 kbps` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:466` | then | `the reason names the endpoint rather than blaming the Recording` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:471` | then | `the recorded render settings are unchanged` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:476` | then | `the reviewer is not asked to approve anything again` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:481` | then | `the same single loudness treatment is applied` | a Then with an empty body |
| `tests/steps/catch_all_thens.py:486` | then | `the waveform and the transcript remain usable` | a Then with an empty body |
| `tests/steps/generated_remaining.py:3` | then | `the punch-out is visibly not` | a Then with an empty body |
| `tests/steps/generated_remaining.py:7` | then | `the change is apparent without my having to test it with a nudge` | a Then with an empty body |
| `tests/steps/generated_remaining.py:11` | then | `the punch-out becomes "2:43:30.250"` | a Then with an empty body |
| `tests/steps/generated_remaining.py:15` | then | `I can override the warning if I mean it` | a Then with an empty body |
| `tests/steps/generated_remaining.py:19` | then | `the machine proposal remains available to revert to` | a Then with an empty body |
| `tests/steps/generated_remaining.py:23` | then | `clicking a word places the boundary at that word` | a Then with an empty body |
| `tests/steps/generated_remaining.py:27` | then | `the punch-out remains "2:43:32.000"` | a Then with an empty body |
| `tests/steps/generated_remaining.py:31` | then | `I can approve anyway` | a Then with an empty body |
| `tests/steps/generated_remaining.py:35` | then | `the new machine proposal is offered beside it, not applied over it` | a Then with an empty body |
| `tests/steps/generated_remaining.py:39` | then | `I can still expand the controls and trim it if I want to` | a Then with an empty body |
| `tests/steps/generated_remaining.py:43` | then | `it never appears as work` | a Then with an empty body |
| `tests/steps/generated_remaining.py:47` | then | `the download still succeeds` | a Then with an empty body |
| `tests/steps/generated_remaining.py:51` | then | `I am offered the option to re-process the Segment` | a Then with an empty body |
| `tests/steps/generated_remaining.py:55` | then | `the downloadable file is renamed` | a Then with an empty body |
| `tests/steps/generated_remaining.py:59` | then | `the existing MP3 remains downloadable until a new one replaces it` | a Then with an empty body |
| `tests/steps/generated_remaining.py:63` | then | `the previous cut's boundaries are retained in the history` | a Then with an empty body |
| `tests/steps/generated_remaining.py:67` | then | `its MP3 is untouched` | a Then with an empty body |
| `tests/steps/generated_remaining.py:71` | then | `a new MP3 is produced with the new settings` | a Then with an empty body |
| `tests/steps/generated_remaining.py:75` | then | `each is re-rendered from its stored boundaries` | a Then with an empty body |
| `tests/steps/generated_remaining.py:79` | then | `the MP3 audio is not re-encoded` | a Then with an empty body |
| `tests/steps/generated_remaining.py:83` | then | `the earlier render is deleted` | a Then with an empty body |
| `tests/steps/generated_remaining.py:87` | then | `I see each set of boundaries with who approved them and when` | a Then with an empty body |
| `tests/steps/generated_remaining.py:91` | then | `the interface does not offer to restore an earlier render` | a Then with an empty body |
| `tests/steps/generated_remaining.py:95` | then | `the output is an MP3` | a Then with an empty body |
| `tests/steps/generated_remaining.py:99` | given | `the Segment is 43 minutes long` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:103` | then | `bitrate, channel layout and sample rate are configuration, not code` | a Then with an empty body |
| `tests/steps/generated_remaining.py:107` | then | `the full span is converted without trimming refinement` | a Then with an empty body |
| `tests/steps/generated_remaining.py:111` | given | `a Segment rendered under the current loudness target` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:115` | given | `past Segments with stored boundaries` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:119` | given | `a Segment has been rendered` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:123` | given | `one of its Segments was skipped` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:127` | given | `a Recording returned to "awaiting_review" by a revisit` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:131` | given | `Segment 1 was skipped on "2026-08-16"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:135` | given | `I approved Segment 2 a moment ago` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:139` | then | `previewing the punch-in and previewing the punch-out are the most prominent actions` | a Then with an empty body |
| `tests/steps/generated_remaining.py:143` | then | `I am told the punch-in needs checking and why` | a Then with an empty body |
| `tests/steps/generated_remaining.py:147` | then | `proposed Segments are drawn as spans above the Blocks they cover` | a Then with an empty body |
| `tests/steps/generated_remaining.py:151` | then | `the others are collapsed but visible` | a Then with an empty body |
| `tests/steps/generated_remaining.py:155` | when | `I read the transcript` | a When with an empty body |
| `tests/steps/generated_remaining.py:159` | then | `I am told which enrolled voice is teaching, and how confidently` | a Then with an empty body |
| `tests/steps/generated_remaining.py:163` | given | `its intent is "publish"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:167` | then | `that Segment strengthens or creates that speaker's profile` | a Then with an empty body |
| `tests/steps/generated_remaining.py:171` | then | `no Segment was proposed for them` | a Then with an empty body |
| `tests/steps/generated_remaining.py:175` | then | `the Recording stays in "awaiting_review"` | a Then with an empty body |
| `tests/steps/generated_remaining.py:179` | given | `a Recording in "awaiting_review" containing 0 Segments` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:183` | given | `a Segment whose cuts are both graded "easy"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:187` | then | `I am told it needs an adjustment better made at a desk` | a Then with an empty body |
| `tests/steps/generated_remaining.py:191` | then | `the waveform, zooming, word alignment and nudge controls are all available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:195` | when | `a Segment is complete` | a When with an empty body |
| `tests/steps/generated_remaining.py:199` | given | `the seekable preview has not been rendered` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:203` | given | `the configured model endpoint does not answer` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:207` | given | `the waveform stage failed` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:211` | then | `its "source FLAC" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:215` | then | `its "rendered MP3" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:219` | then | `its "transcript" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:223` | then | `its "speaker spans and Blocks" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:227` | then | `its "Segment boundaries" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:231` | then | `its "waveform peaks" is still available` | a Then with an empty body |
| `tests/steps/generated_remaining.py:235` | when | `a reviewer approves it now` | a When with an empty body |
| `tests/steps/generated_remaining.py:239` | then | `only the current MP3 is stored` | a Then with an empty body |
| `tests/steps/generated_remaining.py:243` | then | `source FLACs, rendered MP3s and analysis artifacts are written to long-lived storage` | a Then with an empty body |
| `tests/steps/generated_remaining.py:247` | given | `a processing job has finished` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:251` | given | `a Recording is downloading, analyzing, or has a Segment processing` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:255` | when | `any cleanup runs` | a When with an empty body |
| `tests/steps/generated_remaining.py:259` | given | `a Recording is in state "analysis_failed"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining.py:263` | when | `I expand the processing log` | a When with an empty body |
| `tests/steps/generated_remaining.py:267` | when | `I choose to archive the whole recording` | a When with an empty body |
| `tests/steps/generated_remaining.py:271` | then | `I can download the original FLAC regardless of the Recording's state` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:3` | then | `the marking survives my scrolling or zooming the waveform` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:7` | then | `I can still find and restore it if the machine was wrong` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:11` | then | `the audio is not re-encoded` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:15` | then | `the render settings used are recorded` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:19` | then | `no reviewer input is required` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:23` | then | `the downloadable filename reflects the corrected label` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:27` | then | `I see the loudness and encoding settings used for each render` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:31` | then | `the stored history is what makes adding that later possible` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:35` | then | `the channel layout is mono` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:39` | then | `the resulting MP3 is between 25 MB and 40 MB` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:43` | then | `changing them is a re-render, never a re-analysis` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:47` | then | `channel 1 extraction is still applied` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:51` | given | `earlier published files sit 7 to 11 LU quieter` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/generated_remaining2.py:55` | when | `an operator re-renders the archive` | a When with an empty body |
| `tests/steps/generated_remaining2.py:59` | when | `it is rendered again with identical settings` | a When with an empty body |
| `tests/steps/generated_remaining2.py:63` | when | `I revisit that Segment` | a When with an empty body |
| `tests/steps/generated_remaining2.py:67` | when | `I dispose of that Segment` | a When with an empty body |
| `tests/steps/generated_remaining2.py:71` | when | `I open the Recording on "2026-11-04" and approve Segment 1` | a When with an empty body |
| `tests/steps/generated_remaining2.py:75` | when | `I revert it to proposed` | a When with an empty body |
| `tests/steps/generated_remaining2.py:79` | then | `approving is available without any further step` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:83` | then | `the waveform editor is opened ready for the adjustment` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:87` | then | `I see the transcript for that Segment` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:91` | then | `an unrecognised voice is shown as "not a known voice"` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:95` | then | `no separate enrolment session is ever required` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:99` | then | `nothing offers them for publication` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:103` | then | `it still appears as needing attention` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:107` | then | `I am told nothing was detected` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:111` | when | `I open the notification` | a When with an empty body |
| `tests/steps/generated_remaining2.py:115` | then | `I can still skip it, or approve it as-is if I choose to` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:119` | then | `I can download the MP3` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:123` | when | `I try to audition the punch-in` | a When with an empty body |
| `tests/steps/generated_remaining2.py:127` | then | `reviewing, adjusting and approving continue to work` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:131` | then | `I am told the waveform could not be generated` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:135` | then | `the source is still available` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:139` | then | `the settings needed to reproduce the previous one are retained` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:143` | then | `local scratch holds only what a running job needs` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:147` | then | `its intermediate files are removed from scratch` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:151` | when | `scratch is reclaimed` | a When with an empty body |
| `tests/steps/generated_remaining2.py:155` | then | `no source object is deleted` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:159` | when | `I open its processing log` | a When with an empty body |
| `tests/steps/generated_remaining2.py:163` | then | `I see each state transition with its timestamp` | a Then with an empty body |
| `tests/steps/generated_remaining2.py:167` | then | `a Segment is created spanning the entire Recording` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:3` | then | `any whose source is no longer available fails individually and is reported` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:7` | then | `any past render could be reproduced from that record and the source` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:11` | then | `the sample rate is 44100 Hz` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:15` | then | `loudness normalization is still applied` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:19` | then | `the difference is stated to the reviewer once, not on every render` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:23` | then | `each is re-rendered from its stored boundaries under the current target` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:27` | then | `the output is byte-identical apart from embedded timestamps` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:31` | then | `the Recording returns to "reviewed"` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:35` | then | `it is processed using its stored boundaries` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:39` | then | `the queued processing job is cancelled` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:43` | then | `boundary editing is available but not required` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:47` | then | `I can expand to the full Recording transcript if I want it` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:51` | then | `I am not forced to disposition everything in one sitting` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:55` | then | `I can create a Segment by hand` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:59` | then | `I can read the summary` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:63` | then | `I am not offered a cramped editing surface` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:67` | then | `I am told the preview is not ready rather than left with a dead control` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:71` | then | `only the actions that need a model are shown as unavailable` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:75` | then | `playback and the transcript are still available` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:79` | then | `the Segment renders from its stored boundaries` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:83` | then | `the artifacts it produced are not` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:87` | then | `its working files are retained` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:91` | then | `I see every job attempt with its timestamp, duration and error` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:95` | then | `I see each job attempt, including retries and failures` | a Then with an empty body |
| `tests/steps/generated_remaining3.py:99` | then | `it is classified "meeting"` | a Then with an empty body |
| `tests/steps/ingestion/s3_reconciliation_steps.py:145` | then | `the next scheduled scan runs normally` | a Then whose body never asserts |
| `tests/steps/ingestion/webhook_notification_steps.py:177` | then | `a Recording is uniquely identified by its bucket and object key` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:182` | then | `the same key always refers to the same audio` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:235` | given | `the Sermon Processor is unreachable` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/ingestion/webhook_notification_steps.py:240` | when | `the Recorder attempts to deliver a webhook` | a When with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:245` | then | `the Recorder retries with exponential backoff` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:250` | then | `after the retry budget is exhausted the Recorder records a delivery failure` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:255` | then | `the Recording is still ingested later by S3 reconciliation` | a Then with an empty body |
| `tests/steps/ingestion/webhook_notification_steps.py:270` | given | `it contains a bucket "{bucket}"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/approval_steps.py:245` | then | `I can change it to "archive" before approving` | a Then whose body never asserts |
| `tests/steps/interface/approval_steps.py:263` | then | `no Segment is ever published on classification alone` | a Then with an empty body |
| `tests/steps/interface/discarding_steps.py:204` | then | `its Segments are intact` | a Then whose body never asserts |
| `tests/steps/interface/discarding_steps.py:209` | then | `the source object in the object store is untouched` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:97` | then | `I see:` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/recording_detail_steps.py:120` | then | `it explains that this originates at the recorder and cannot be repaired here` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:147` | then | `I see which stages have completed` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:157` | then | `I see the failure reason` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/recording_detail_steps.py:162` | then | `I can retry Analysis` | a Then with an empty body |
| `tests/steps/interface/recording_detail_steps.py:167` | then | `I can create a Segment by hand instead` | a Then with an empty body |
| `tests/steps/interface/recording_list_steps.py:234` | then | `I can search by date, by classification, and by what was said` | a Then with an empty body |
| `tests/steps/interface/recording_list_steps.py:323` | then | `the page loads in under 2 seconds` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:179` | then | `hovering a marker describes the evidence` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:184` | then | `clicking a marker seeks the player to that point` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:195` | then | `each speaker span is coloured by speaker` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:225` | when | `I choose to preview the punch-in` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:249` | when | `I choose to preview the cut` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:279` | then | `only the region being played is fetched` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:284` | then | `playback begins within 2 seconds of pressing play` | a Then with an empty body |
| `tests/steps/interface/waveform_steps.py:289` | when | `I zoom the detail view into the punch-in` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:309` | when | `I click a point on the overview` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:357` | when | `I zoom in around a boundary` | a When whose body never acts |
| `tests/steps/interface/waveform_steps.py:362` | then | `a {amount} gap is {pixels} of the detail view` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/interface/waveform_steps.py:367` | then | `that is "{feel}"` | an assertion that cannot fail |
| `tests/steps/interface/waveform_steps.py:430` | given | `the teaching begins with "good morning"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:435` | given | `the opening contains a throat-clear before the first real words` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:440` | given | `I am viewing the whole recording at overview resolution` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/interface/waveform_steps.py:468` | when | `I try to set a span shorter than 1 second` | a When whose body never acts |
| `tests/steps/last_fourteen.py:22` | then | `the resulting MP3 is identical to what it would have been in August` | a Then with an empty body |
| `tests/steps/last_fourteen.py:27` | then | `the whole flow works without a waveform` | a Then with an empty body |
| `tests/steps/last_fourteen.py:32` | then | `the evidence panel shows why that candidate was considered` | a Then with an empty body |
| `tests/steps/last_fourteen.py:37` | then | `I do not have to discard it for the queue to stay clean` | a Then with an empty body |
| `tests/steps/last_fourteen.py:42` | then | `I can approve` | a Then with an empty body |
| `tests/steps/last_fourteen.py:47` | then | `the boundaries can still be adjusted and approved` | a Then with an empty body |
| `tests/steps/last_fourteen.py:52` | then | `I can still adjust and approve boundaries` | a Then with an empty body |
| `tests/steps/last_fourteen.py:57` | then | `it is approved for processing without asking me for boundaries` | a Then with an empty body |
| `tests/steps/last_fourteen.py:62` | then | `the gap is shown as "0.90 s"` | a Then with an empty body |
| `tests/steps/last_fourteen.py:143` | then | `the source is still available` | a Then with an empty body |
| `tests/steps/last_fourteen.py:148` | then | `it remains available if I ever want it` | a Then with an empty body |
| `tests/steps/last_fourteen.py:153` | then | `I am asked to confirm that this recording may be distributed` | a Then with an empty body |
| `tests/steps/last_fourteen.py:158` | then | `the confirmation is recorded with the approval` | a Then with an empty body |
| `tests/steps/notifications/analysis_notification_steps.py:225` | then | `it states why confidence is low` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:14` | given | `no delivery channel is configured` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/notifications/notification_steps.py:100` | then | `nothing fails` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:105` | then | `delivering a Notification is separate from creating one` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:110` | then | `adding or changing a channel does not change when Notifications are raised` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:115` | then | `the same Notification can be delivered by more than one channel` | a Then with an empty body |
| `tests/steps/notifications/notification_steps.py:120` | when | `I open the interface` | a When with an empty body |
| `tests/steps/notifications/notification_steps.py:125` | then | `I see the Notifications raised for me` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/operations/job_queue_steps.py:196` | when | `the application restarts` | a When with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:151` | then | `I can download "{artifact}"` | an assertion that cannot fail |
| `tests/steps/processing/artifact_downloads_steps.py:156` | then | `I can read its transcript without downloading anything` | a Then with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:161` | then | `the transcript covers the approved span` | a Then with an empty body |
| `tests/steps/processing/artifact_downloads_steps.py:166` | then | `I can expand to the full Recording transcript` | a Then with an empty body |
| `tests/steps/processing/processing_orchestration_steps.py:177` | then | `a failure in one does not affect the other` | a Then with an empty body |
| `tests/steps/processing/processing_orchestration_steps.py:182` | then | `the reviewer can continue working with other Recordings and Segments` | a Then with an empty body |
| `tests/steps/remaining_steps.py:43` | given | `channel 2 of the source is silent` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:180` | given | `a download was interrupted at 300 MB` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:191` | given | `the rendered MP3 file cannot be found` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:243` | when | `the system comes back up` | a When with an empty body |
| `tests/steps/remaining_steps.py:248` | given | `its transcript contains "{text}"` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:253` | then | `the label is suggested as "TEC"` | a Then with an empty body |
| `tests/steps/remaining_steps.py:258` | then | `the label is suggested as "{label}"` | an assertion that cannot fail |
| `tests/steps/remaining_steps.py:355` | given | `the loudness target has been changed in configuration` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:392` | then | `the MP3 download is not offered` | a Then with an empty body |
| `tests/steps/remaining_steps.py:412` | when | `I focus the punch-in` | a When with an empty body |
| `tests/steps/remaining_steps.py:417` | given | `the punch-in has focus` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:422` | then | `the available nudge steps are shown alongside the boundary` | a Then with an empty body |
| `tests/steps/remaining_steps.py:432` | given | `the visible window is {window}` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:442` | then | `placing a boundary to 100 ms is {verdict}` | an assertion that cannot fail |
| `tests/steps/remaining_steps.py:452` | then | `the transcript is what I read` | a Then with an empty body |
| `tests/steps/remaining_steps.py:462` | then | `the waveform is what I use` | a Then with an empty body |
| `tests/steps/remaining_steps.py:467` | then | `no words are expected in view at that zoom` | a Then with an empty body |
| `tests/steps/remaining_steps.py:477` | then | `its peak data is fetched per recording rather than inlined in the page` | a Then whose body never asserts |
| `tests/steps/remaining_steps.py:488` | then | `it is served at progressive resolution` | a Then with an empty body |
| `tests/steps/remaining_steps.py:535` | then | `partial output is cleaned up` | a Then with an empty body |
| `tests/steps/remaining_steps.py:540` | then | `a reviewer can retry processing without re-approving` | a Then with an empty body |
| `tests/steps/remaining_steps.py:545` | then | `the step is retried` | a Then with an empty body |
| `tests/steps/remaining_steps.py:555` | then | `the source is re-downloaded from the object store first` | a Then with an empty body |
| `tests/steps/remaining_steps.py:560` | then | `processing continues normally` | a Then with an empty body |
| `tests/steps/remaining_steps.py:585` | then | `a storage alert is raised` | a Then with an empty body |
| `tests/steps/remaining_steps.py:595` | then | `processing is restarted from the beginning` | a Then with an empty body |
| `tests/steps/remaining_steps.py:600` | then | `no partial artifact is exposed as a download` | a Then with an empty body |
| `tests/steps/remaining_steps.py:612` | then | `the processing job stops` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/remaining_steps.py:623` | then | `any partial output is discarded` | a Then with an empty body |
| `tests/steps/remaining_steps.py:628` | then | `I can correct it before approving` | a Then with an empty body |
| `tests/steps/remaining_steps.py:633` | then | `the output takes channel 1 only` | a Then with an empty body |
| `tests/steps/remaining_steps.py:638` | then | `channel 2 is discarded without being mixed in` | a Then with an empty body |
| `tests/steps/remaining_steps.py:643` | then | `the output level matches channel 1's level, not half of it` | a Then with an empty body |
| `tests/steps/remaining_steps.py:648` | then | `the output is mono` | a Then with an empty body |
| `tests/steps/remaining_steps.py:663` | then | `the output duration matches the approved span within 100 ms` | a Then with an empty body |
| `tests/steps/remaining_steps.py:668` | then | `the trim is sample-accurate rather than snapped to a frame boundary` | a Then with an empty body |
| `tests/steps/remaining_steps.py:673` | then | `a short fade-in is applied at the start` | a Then with an empty body |
| `tests/steps/remaining_steps.py:678` | then | `a short fade-out is applied at the end` | a Then with an empty body |
| `tests/steps/remaining_steps.py:683` | then | `neither fade is long enough to swallow a spoken word` | a Then with an empty body |
| `tests/steps/remaining_steps.py:693` | then | `the output true peak does not exceed "{peak}"` | an assertion that cannot fail |
| `tests/steps/remaining_steps.py:698` | then | `the measured input and output loudness are recorded on the Segment` | a Then with an empty body |
| `tests/steps/remaining_steps.py:703` | then | `there is one set of loudness settings, not a normalize toggle and a compress toggle` | a Then with an empty body |
| `tests/steps/remaining_steps.py:708` | then | `the settings used are recorded on every rendered Segment` | a Then with an empty body |
| `tests/steps/remaining_steps.py:713` | then | `changing them is what makes a re-render meaningful` | a Then with an empty body |
| `tests/steps/remaining_steps.py:718` | then | `the change is rejected` | a Then with an empty body |
| `tests/steps/remaining_steps.py:728` | then | `the punch-in is visibly marked as the one the keyboard will move` | a Then with an empty body |
| `tests/steps/remaining_steps.py:733` | when | `I move focus to the punch-out` | a When with an empty body |
| `tests/steps/remaining_steps.py:738` | then | `they read as 50 ms, 0.1 s, 1 s and 10 s` | a Then with an empty body |
| `tests/steps/remaining_steps.py:743` | then | `the highlighted region updates` | a Then with an empty body |
| `tests/steps/remaining_steps.py:763` | then | `the punch-in moves to the nearest silence gap boundary` | a Then with an empty body |
| `tests/steps/remaining_steps.py:768` | then | `I am warned that the cut is too close to the audio` | a Then with an empty body |
| `tests/steps/remaining_steps.py:773` | then | `spans with at least 250 ms of quiet are visually marked` | a Then with an empty body |
| `tests/steps/remaining_steps.py:792` | then | `the transcript words are shown aligned to their position on the waveform` | a Then with an empty body |
| `tests/steps/remaining_steps.py:797` | then | `individual words are not drawn` | a Then with an empty body |
| `tests/steps/remaining_steps.py:802` | then | `the change is accepted` | a Then with an empty body |
| `tests/steps/remaining_steps.py:817` | when | `Analysis is re-run` | a When with an empty body |
| `tests/steps/remaining_steps.py:829` | then | `the boundary controls are collapsed` | a Then with an empty body |
| `tests/steps/remaining_steps.py:847` | when | `my browser resumes it` | a When with an empty body |
| `tests/steps/remaining_steps.py:862` | then | `no further notifications are sent to them` | a Then with an empty body |
| `tests/steps/remaining_steps.py:867` | then | `each carries its own label` | a boolean operand of True, which neutralises what it joins; an assertion that cannot fail |
| `tests/steps/remaining_steps.py:890` | then | `it enters "recut"` | a Then whose body never asserts |
| `tests/steps/remaining_steps.py:896` | then | `it is processed again` | a Then with an empty body |
| `tests/steps/remaining_steps.py:901` | then | `the original FLAC is unchanged` | a Then with an empty body |
| `tests/steps/remaining_steps.py:912` | when | `an operator re-renders the Segment` | a When with an empty body |
| `tests/steps/remaining_steps.py:917` | when | `an operator re-renders them all` | a When with an empty body |
| `tests/steps/remaining_steps.py:922` | when | `the change is saved` | a When with an empty body |
| `tests/steps/remaining_steps.py:927` | then | `only the most recent MP3 is stored` | a Then with an empty body |
| `tests/steps/remaining_steps.py:932` | when | `I view its history` | a When with an empty body |
| `tests/steps/remaining_steps.py:937` | then | `the gap is shown as "0.90 s"` | a Then with an empty body |
| `tests/steps/remaining_steps.py:942` | then | `it is marked as shorter than the 1.5 second tail the editor prefers` | a Then with an empty body |
| `tests/steps/remaining_steps.py:947` | when | `I zoom into the punch-in` | a When with an empty body |
| `tests/steps/remaining_steps.py:952` | then | `the waveform resolution increases` | a Then with an empty body |
| `tests/steps/remaining_steps.py:957` | then | `I can distinguish individual words in the waveform` | a Then with an empty body |
| `tests/steps/remaining_steps.py:962` | then | `I can place a boundary to within 100 ms` | a Then with an empty body |
| `tests/steps/remaining_steps.py:967` | when | `I zoom into a boundary` | a When with an empty body |
| `tests/steps/remaining_steps.py:972` | then | `the transcript words are drawn aligned to the waveform` | a Then with an empty body |
| `tests/steps/remaining_steps.py:977` | then | `I can read exactly what is said either side of the cut` | a Then with an empty body |
| `tests/steps/remaining_steps.py:982` | given | `I have zoomed in` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:987` | when | `I choose to fit the whole recording` | a When with an empty body |
| `tests/steps/remaining_steps.py:992` | then | `the waveform returns to showing the full duration` | a Then with an empty body |
| `tests/steps/remaining_steps.py:997` | then | `all Block bands are visible again` | a Then with an empty body |
| `tests/steps/remaining_steps.py:1002` | given | `the punch-out is {gap} seconds before the next speech` | an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate |
| `tests/steps/remaining_steps.py:1203` | then | `I can change the label or confirm that this replaces the previous file` | a Then whose body never asserts |

## Scenarios whose every Then is condemned

| feature | line | scenario |
| --- | --- | --- |
| `analysis/audio_probe.feature` | 156 | A quiet but real recording is not discarded |
| `analysis/block_classification.feature` | 150 | A Q&A block is recognisable by shape as well as words |
| `analysis/block_classification.feature` | 169 | A known preacher raises confidence |
| `analysis/block_classification.feature` | 316 | A special service still produces a reviewable Segment |
| `analysis/block_classification.feature` | 324 | One event across several recordings |
| `analysis/block_classification.feature` | 18 | The block types we recognise |
| `analysis/block_classification.feature` | 232 | The sermon follows the scripture reading directly |
| `analysis/block_classification.feature` | 277 | What distinguishes rehearsal from a service |
| `analysis/detection_accuracy.feature` | 245 | A detection change is evaluated before it ships |
| `analysis/detection_accuracy.feature` | 234 | A few hundred milliseconds matters on an easy cut |
| `analysis/detection_accuracy.feature` | 178 | Clipping the first word is worse than starting early |
| `analysis/detection_accuracy.feature` | 219 | Difficulty is graded from the ground truth, never by the system |
| `analysis/detection_accuracy.feature` | 227 | Hard cuts are expected to need a human |
| `analysis/detection_accuracy.feature` | 252 | New recordings join the corpus |
| `analysis/detection_accuracy.feature` | 139 | No error figure is a release gate |
| `analysis/detection_accuracy.feature` | 187 | Punch-in errors count for more than punch-out errors |
| `analysis/detection_accuracy.feature` | 196 | Results are stratified by how hard the cut was |
| `analysis/detection_accuracy.feature` | 107 | Running the corpus |
| `analysis/detection_accuracy.feature` | 269 | The corpus is unavailable |
| `analysis/detection_accuracy.feature` | 121 | The suite covers both kinds of content |
| `analysis/detection_accuracy.feature` | 130 | The target is a two-preview approval |
| `analysis/detection_accuracy.feature` | 261 | Untouched approvals are counted, not used as truth |
| `analysis/punch_in_detection.feature` | 39 | A quiet margin around the cut |
| `analysis/punch_in_detection.feature` | 93 | An easy cut is expected to be right |
| `analysis/punch_in_detection.feature` | 111 | Other common openings |
| `analysis/punch_out_detection.feature` | 104 | A candidate falling mid-word is moved |
| `analysis/punch_out_detection.feature` | 76 | A quiet margin around the cut |
| `analysis/segment_proposal.feature` | 86 | A prayer that does not immediately follow is not included |
| `analysis/segment_proposal.feature` | 183 | A proposed segment would overlap its neighbour |
| `analysis/segment_proposal.feature` | 147 | An implausible proposal falls back to the rules |
| `analysis/segment_proposal.feature` | 117 | What makes a proposal implausible |
| `analysis/segment_proposal.feature` | 168 | Where a boundary came from is always recorded |
| `analysis/summarization.feature` | 131 | A weaker model is an acceptable trade |
| `analysis/summarization.feature` | 138 | Heuristics are an acceptable substitute |
| `analysis/summarization.feature` | 167 | Summaries are never authoritative |
| `analysis/summarization.feature` | 104 | The excerpt avoids dead air |
| `analysis/summarization.feature` | 29 | The proposed segment carries a summary too |
| `analysis/summarization.feature` | 89 | What makes a good cue excerpt |
| `ingestion/webhook_notification.feature` | 111 | The Processor is down when the Recorder fires the webhook |
| `ingestion/webhook_notification.feature` | 72 | The object key is the identity |
| `interface/discarding_recordings.feature` | 110 | A false trigger is ignored without asking me |
| `interface/discarding_recordings.feature` | 120 | Duration alone never decides anything |
| `interface/publication_details.feature` | 74 | An archival segment is named from the date |
| `interface/publication_details.feature` | 104 | Renaming after processing |
| `interface/publication_details.feature` | 58 | The label is suggested from the classification for other content |
| `interface/publication_details.feature` | 49 | The label is suggested from the transcript for sermons |
| `interface/publication_details.feature` | 65 | Two segments from one recording get different labels |
| `interface/punch_point_adjustment.feature` | 131 | A quiet margin is enforced as I drag |
| `interface/punch_point_adjustment.feature` | 208 | A zero-length or near-zero-length selection |
| `interface/punch_point_adjustment.feature` | 247 | Adjusting one segment leaves the others alone |
| `interface/punch_point_adjustment.feature` | 255 | An archival segment skips boundary editing |
| `interface/punch_point_adjustment.feature` | 214 | An unusually short or long selection is allowed but warned about |
| `interface/punch_point_adjustment.feature` | 190 | Boundaries outside the Segment |
| `interface/punch_point_adjustment.feature` | 146 | Cutting just before the usual greeting |
| `interface/punch_point_adjustment.feature` | 57 | Moving focus between the two boundaries |
| `interface/punch_point_adjustment.feature` | 166 | Reading the transcript along the timeline |
| `interface/punch_point_adjustment.feature` | 140 | Seeing where the clean cut points are |
| `interface/punch_point_adjustment.feature` | 154 | Skipping a false start by hand |
| `interface/punch_point_adjustment.feature` | 116 | Snapping to the nearest silence |
| `interface/punch_point_adjustment.feature` | 240 | The machine never discards my edits on its own |
| `interface/punch_point_adjustment.feature` | 64 | The nudge steps are stated, not discovered |
| `interface/punch_point_adjustment.feature` | 183 | The punch-out is dragged before the punch-in |
| `interface/punch_point_adjustment.feature` | 80 | Typing an exact timecode |
| `interface/punch_point_adjustment.feature` | 46 | Which boundary the keyboard will move is always apparent |
| `interface/punch_point_adjustment.feature` | 175 | Words are hidden when they would be unreadable |
| `interface/recording_detail.feature` | 85 | Archiving the whole recording without editing it |
| `interface/recording_detail.feature` | 98 | The original FLAC is always available |
| `interface/recording_detail.feature` | 53 | Viewing a failure |
| `interface/recording_detail.feature` | 18 | Viewing technical and source metadata |
| `interface/recording_detail.feature` | 61 | Viewing the processing log |
| `interface/segment_review.feature` | 109 | A hard cut interrupts the three-click path |
| `interface/segment_review.feature` | 217 | A recording where nothing was found |
| `interface/segment_review.feature` | 240 | A segment needing real editing says so on mobile |
| `interface/segment_review.feature` | 181 | An unrecognised voice is confirmed before it is published |
| `interface/segment_review.feature` | 191 | Confirming who preached enrols them |
| `interface/segment_review.feature` | 249 | Desktop carries the full editor |
| `interface/segment_review.feature` | 254 | Downloading works everywhere |
| `interface/segment_review.feature` | 140 | Jumping to a specific spot instead |
| `interface/segment_review.feature` | 210 | Leaving a recording part-reviewed |
| `interface/segment_review.feature` | 202 | Music is never a publication candidate, because it is never a Segment |
| `interface/segment_review.feature` | 134 | Previewing a proposed segment |
| `interface/segment_review.feature` | 124 | Previewing the identifiable moment |
| `interface/segment_review.feature` | 118 | Reading the shape of the service |
| `interface/segment_review.feature` | 73 | Revisiting a segment months later |
| `interface/segment_review.feature` | 145 | Seeing where each segment sits in the recording |
| `interface/segment_review.feature` | 41 | The Recording settles again once it is dispositioned |
| `interface/segment_review.feature` | 153 | The likely sermon is offered first |
| `interface/segment_review.feature` | 227 | The ordinary week works on a phone |
| `interface/segment_review.feature` | 168 | The speaker is identified on the Segment |
| `interface/segment_review.feature` | 159 | The transcript is scoped to the selected segment |
| `interface/segment_review.feature` | 102 | The two previews are the primary controls |
| `interface/waveform_review.feature` | 219 | Peak data is fetched, not embedded |
| `interface/waveform_review.feature` | 180 | Returning to the overview |
| `interface/waveform_review.feature` | 157 | The gap is shown because it is the thing pixels hide |
| `interface/waveform_review.feature` | 239 | The model host is unreachable while I am reviewing |
| `interface/waveform_review.feature` | 231 | The preview audio will not play |
| `interface/waveform_review.feature` | 251 | Waveform data is unavailable |
| `interface/waveform_review.feature` | 208 | Words and waveform serve different steps |
| `interface/waveform_review.feature` | 174 | Words appear beside the waveform when zoomed |
| `interface/waveform_review.feature` | 167 | Zooming into a boundary |
| `notifications/approval_notifications.feature` | 169 | Opting out |
| `notifications/approval_notifications.feature` | 45 | The channel is pluggable |
| `operations/storage_and_retention.feature` | 47 | Long-lived files live on the array |
| `operations/storage_and_retention.feature` | 58 | Nothing in progress is cleaned up |
| `operations/storage_and_retention.feature` | 38 | Only superseded renders are removed |
| `operations/storage_and_retention.feature` | 52 | Scratch is reclaimed after a job |
| `operations/storage_and_retention.feature` | 82 | The processor never deletes a source |
| `operations/storage_and_retention.feature` | 15 | What is retained |
| `operations/system_health.feature` | 57 | Finding out why a recording failed |
| `processing/artifact_downloads.feature` | 102 | An artifact file is missing from storage |
| `processing/artifact_downloads.feature` | 81 | Artifacts that do not exist yet |
| `processing/artifact_downloads.feature` | 73 | Downloads can be resumed |
| `processing/artifact_downloads.feature` | 65 | Large files stream rather than buffer |
| `processing/artifact_downloads.feature` | 95 | The FLAC has been cleaned up locally |
| `processing/artifact_downloads.feature` | 37 | The transcript is downloadable |
| `processing/artifact_downloads.feature` | 50 | The transcript is readable in the interface |
| `processing/audio_rendering.feature` | 83 | A single loud moment does not drag the whole file down |
| `processing/audio_rendering.feature` | 164 | An archival segment is converted, not produced |
| `processing/audio_rendering.feature` | 30 | Both channels carry signal |
| `processing/audio_rendering.feature` | 20 | Channel 1 is extracted, not downmixed |
| `processing/audio_rendering.feature` | 139 | Encoding settings |
| `processing/audio_rendering.feature` | 157 | Encoding settings are configurable in one place |
| `processing/audio_rendering.feature` | 77 | Every week sounds the same |
| `processing/audio_rendering.feature` | 176 | Everything published before is quieter |
| `processing/audio_rendering.feature` | 151 | File size is reasonable |
| `processing/audio_rendering.feature` | 92 | Quiet passages come up without a separate compression step |
| `processing/audio_rendering.feature` | 186 | The archive can be brought into line unattended |
| `processing/audio_rendering.feature` | 48 | The cut does not click or pop |
| `processing/audio_rendering.feature` | 105 | The loudness treatment is a single configured target |
| `processing/audio_rendering.feature` | 197 | The same input produces the same output |
| `processing/audio_rendering.feature` | 111 | The source is already clipping |
| `processing/audio_rendering.feature` | 121 | The source is very quiet |
| `processing/processing_orchestration.feature` | 75 | The source FLAC is no longer on local disk |
| `processing/reprocessing.feature` | 74 | A re-render replaces its predecessor |
| `processing/reprocessing.feature` | 24 | Approving the new cut |
| `processing/reprocessing.feature` | 83 | Every past render remains reproducible |
| `processing/reprocessing.feature` | 14 | Re-cutting |
| `processing/reprocessing.feature` | 38 | Re-cutting one segment leaves its siblings alone |
| `processing/reprocessing.feature` | 47 | Re-rendering after changing render settings |
| `processing/reprocessing.feature` | 55 | Re-rendering the back catalogue after settling the loudness target |
| `processing/reprocessing.feature` | 65 | Renaming without re-rendering |
| `processing/reprocessing.feature` | 91 | Reproducing a past render is not offered as a feature |
| `processing/reprocessing.feature` | 32 | The original FLAC is never affected |
