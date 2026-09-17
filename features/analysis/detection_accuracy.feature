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

  Rule: A source and its edit can run on different clocks

    @edge-case @measured
    Scenario: Linear drift between the recording and the export
      # Measured: three early recordings drift about -130 ppm against their
      # published MP3s — a capture clock at roughly 44,094 Hz labelled 44,100.
      # Across a 50-minute sermon that accumulates to 0.23 s, which is large
      # against the tolerances here. Everything from late March onward is within
      # 0.3 ppm, so it is a property of a recording, not of the room.
      Given a published output that runs at a slightly different rate to its source
      When ground truth extraction runs
      Then the drift is measured rather than averaged away
      And the punch-in is the intercept of the fit, not the middle of it
      And the punch-out accounts for the drift across the segment

    @edge-case @measured
    Scenario: Drift is separated from a real discontinuity
      # Probes taken at several points through the output will disagree both when
      # the clocks differ and when material was cut from the middle. Only the
      # second makes the pair unusable, so the test is the deviation from a
      # straight line, not the raw disagreement.
      Given probes through the output disagree about the offset
      When they fall on a straight line
      Then the pair is usable and the slope is the clock difference
      When they do not fall on a straight line
      Then the pair is excluded as not a contiguous excerpt

  Rule: An already-edited source is not ground truth

    @edge-case @measured
    Scenario: A lossless copy of just the message
      # The archive predating the object store contains lossless copies of only
      # the message. As ground truth these are actively harmful: the punch-in is
      # zero and the punch-out is the end, which would teach that a sermon starts
      # at the beginning of its file.
      Given a Recording whose published output covers more than 95% of its source
      Then it is flagged rather than silently accepted
      And it is excluded from boundary statistics
      And a legitimate untrimmed archive is flagged the same way
      # The two are indistinguishable from the numbers, so a human decides which
      # it is. Every recording in the corpus taken from the object store covers
      # 29% to 80% of its source.

    @edge-case @measured
    Scenario: A published output the system produced itself
      # Happened on 2026-09-06: the reviewer approved the proposal and published
      # it unchanged. The output is a real publication, and it is also byte for
      # byte the system's own answer. Aligning it would score the system against
      # itself and every boundary error would read as zero.
      #
      # This is the failure mode that grows on its own. The better the proposals
      # get, the more often they ship unedited, and the more of the corpus turns
      # into the system's own output -- so accuracy appears to climb while the
      # evidence for it disappears.
      Given a Segment was approved with no boundary adjustment
      And its published output was rendered from the proposed boundaries
      Then the output is recorded as published
      And it is excluded from ground truth
      And its provenance is stored, not inferred later from the audio
      # By the time it is on disk it is indistinguishable from a human edit.

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
      And it is reported alongside the raw error figures, not replaced by them

    @happy-path
    Scenario: No error figure is a release gate
      # Settled 2026-09-16. An earlier version of this scenario set a target of
      # 80% within one second and treated it as a bar to clear. That was wrong
      # in two directions at once.
      #
      # Wrong about the tolerance: "what is acceptable for punch-in/punch-out is
      # very much dependent on each recording... it could be that there's a weird
      # breath or feedback that makes the edit matter down to 200 to 300 ms.
      # That's rare, though. Usually you have a few seconds, and if you make the
      # cut anywhere in there, you're okay." A single number cannot express that,
      # and measured data agrees: held-out punch-in errors are 10 early to 9 late
      # out of 19, and a 3-second early cut and a 3-second clip score identically
      # under a symmetric bar while being nothing alike.
      #
      # Wrong about the role: "it will be approved by a person every time. The
      # model is just taking a guess, and hopefully it's correct. If not, the
      # human will be able to correct the punch-in and punch-out points."
      Then the suite is a regression instrument, not an acceptance test
      And a change that worsens the error distribution is reported as a regression
      And no configuration is rejected for missing a fixed tolerance
      And the reviewer's correction, not the tolerance, is what guarantees the cut

  Rule: One property of the punch-in is not a matter of taste

    @happy-path @measured
    Scenario: Silence before the first word is bounded
      # The one failure the reviewer cannot shrug off, because it reads as a
      # broken file rather than a loose cut: "too much audio silence at the
      # beginning of the recording is not good. People wonder if it's even
      # playing." Q18 put the ceiling at one second.
      #
      # This is checkable without ground truth, on any proposal, which is what
      # makes it useful where the error figures are not.
      Given a proposed Segment
      When the leading silence is measured from the punch-in to the first speech
      Then it is at most 1.0 seconds
      And a proposal exceeding it is flagged to the reviewer before approval

    @edge-case @measured
    Scenario: Clipping the first word is worse than starting early
      # Both are errors; only one destroys content. Held-out on the local model,
      # 6 of 19 punch-ins were late by more than a second -- the failure worth
      # surfacing -- while the worst early miss was 12 seconds and cost nothing
      # but lead-in that the leading-silence rule already bounds.
      Then punch-in error is reported with its sign, never as an absolute value
      And late punch-ins are reported separately from early ones

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

    @happy-path @measured
    Scenario: Difficulty is graded from the ground truth, never by the system
      # Otherwise the headline number can be raised by grading more cuts hard.
      # The grade belongs to the recording, not to the attempt at it.
      Given the accuracy suite runs
      Then each boundary's difficulty comes from the audio around the human cut
      And a configuration cannot change the difficulty of anything it is scored on

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
      # Every week of ordinary use produces another test case for free -- but
      # only where the reviewer actually moved something. An untouched approval
      # carries no independent information about where the boundary belonged.

    @happy-path @measured
    Scenario: Untouched approvals are counted, not used as truth
      # They are the headline measure -- the proportion approved with no edit --
      # so they must be counted. They just cannot also be the yardstick.
      Given a reviewer approved a Segment without adjusting either boundary
      Then it counts toward the proportion approved with no edit
      And it does not become a labelled example

    @edge-case
    Scenario: The corpus is unavailable
      Given the sample recordings are not present on the machine
      When the accuracy suite runs
      Then it reports that it was skipped
      And it does not report a pass
