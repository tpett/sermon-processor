@analysis @slow
Feature: Measuring detection accuracy against real recordings
  In order to know whether any of this actually works
  As the person who currently does this by hand
  I want the machine's cuts compared to the ones I made myself

  This replaces the confidence-calibration idea, which needed a year of usage to
  say anything. There are already 24 FLAC/MP3 pairs in `~/Desktop/Sermons`
  spanning April to August 2026, where the MP3 is the human-made answer. That is
  a ready-made test set.

  Background:
    Given a corpus of source recordings paired with the human-edited output
    And each pair has a known punch-in and punch-out derived from the pair itself

  Rule: Ground truth is derived from the existing pairs

    @happy-path
    Scenario: Deriving the human punch points
      Given a source FLAC and the MP3 a human produced from it
      When ground truth extraction runs
      Then the offset of the MP3 within the FLAC is determined
      And the punch-in is that offset
      And the punch-out is that offset plus the MP3 duration
      And the derived boundaries are stored as the expected answer for that pair

    @happy-path
    Scenario: Alignment survives the loudness processing
      # The human edit is a peak-normalized copy — a linear gain — so waveform
      # shape is preserved and correlation locks on. Transcript alignment is the
      # fallback if any pair was processed differently.
      Given the MP3 was normalized relative to the source
      When ground truth extraction runs
      Then alignment still succeeds
      And the derived punch-in is accurate to within 100 ms

    @edge-case
    Scenario: A pair that cannot be aligned
      Given alignment fails for a pair
      Then that pair is excluded from the corpus
      And the exclusion is reported rather than silently dropped

  Rule: Accuracy is reported per pair and in aggregate

    @happy-path
    Scenario: Running the corpus
      When the accuracy suite runs over the corpus
      Then for each pair it reports:
        | measure                                          |
        | punch-in error in seconds, signed                |
        | punch-out error in seconds, signed               |
        | the difficulty grade of each transition          |
        | whether the correct Segment was proposed at all  |
        | the proposed classification against the expected |
        | whether a human would have had to edit           |
      And it reports the proportion approved with no edit
      And it reports the median and worst-case error, split by difficulty

    @happy-path
    Scenario: The suite covers both kinds of content
      Then the corpus includes sermons and class sessions
      And accuracy is reported separately for each classification
      # 20 sermons and 3 classes are in the sample set, so class accuracy will
      # be a weaker signal until more accumulate.

  Rule: The measure is whether a human had to intervene

    @happy-path @measured
    Scenario: The target is a two-preview approval
      # Q75 — confirmed: the win is not a tolerance figure, it is the workflow.
      # "if we can get this to work 80% of the time, then it is just: hit play
      # to preview the punch-in, hit play to preview the punch-out, approve,
      # and we are done."
      Then the headline measure is the proportion of Segments approved with no boundary edit
      And the target for that proportion is 80%
      And it is reported alongside the raw error figures, not replaced by them

    @happy-path @measured
    Scenario: Punch-in errors count for more than punch-out errors
      # Confirmed: "the punch in is more important than the punch out. More
      # people listen to the beginning than to the end."
      Given one Segment is 1 second late at the punch-in
      And another is 1 second late at the punch-out
      Then the punch-in error is weighted more heavily in the headline score
      And both are still reported separately

    @happy-path @measured
    Scenario: Results are stratified by how hard the cut was
      # Confirmed: "I do not think we can say that the punch error has a fixed
      # time length, because it very much depends on how tight the words are or
      # how tight the transition is."
      When the accuracy suite runs over the corpus
      Then each pair is graded against the difficulty of its own transition
      And results are reported separately for easy and hard cuts
      And a poor result on a hard cut is not treated the same as one on an easy cut

    @happy-path @measured
    Scenario Outline: What makes a cut easy or hard
      Given the audio around the true cut point is "<condition>"
      Then the transition is graded "<difficulty>"

      Examples:
        | condition                                        | difficulty |
        | 10 seconds of clean silence before the first word | easy       |
        | 2 seconds of clean silence                        | easy       |
        | under 250 ms of quiet, words either side          | hard       |
        | audible noise or feedback near the cut point      | hard       |
        | music fading under the first words                | hard       |

    @happy-path
    Scenario: Hard cuts are expected to need a human
      Given a transition graded "hard"
      Then the suite does not require the machine to match the human exactly
      And it requires that the Segment was flagged as needing attention
      # Getting a hard cut wrong is acceptable. Getting it wrong silently is not.

    @happy-path @measured
    Scenario: A few hundred milliseconds matters on an easy cut
      # Confirmed: "sometimes even a few hundred ms can make a big difference
      # in the quality of the output."
      Given a transition graded "easy"
      And the proposed punch-in is 400 ms later than the human punch-in
      Then the result is graded as needing correction
      And it does not count toward the no-edit proportion

  Rule: The suite is how changes are judged

    @happy-path
    Scenario: A detection change is evaluated before it ships
      Given a change to blocking, classification or boundary refinement
      When the accuracy suite runs before and after
      Then the change in median and worst-case error is reported
      And a change that improves the median but worsens the worst case is visible as such

    @happy-path
    Scenario: New recordings join the corpus
      Given a reviewer approved a Segment after adjusting its boundaries
      Then that recording and the approved boundaries can be added to the corpus
      And the corpus grows without anyone hand-labelling anything
      # Every week of ordinary use produces another test case for free.

    @edge-case
    Scenario: The corpus is unavailable
      Given the sample recordings are not present on the machine
      When the accuracy suite runs
      Then it reports that it was skipped
      And it does not report a pass
