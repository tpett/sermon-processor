@analysis @happy-path
Feature: Refining a segment's punch-out
  In order for the file to end cleanly on the last words
  As the Sermon Processor
  I want the punch-out placed precisely at the end of the teaching

  Segment proposal already decided *which* Block the Segment ends on — normally
  the closing prayer. This stage decides exactly where inside the tail of that
  Block the cut falls.

  All timecodes are absolute against the source Recording.

  Background:
    Given a Segment classified "sermon" ending on a prayer Block
    And the last word of that Block is spoken at "1:14:48.900"
    And the next Block begins at "1:14:55.000"

  Rule: The punch-out sits just after the last word

    @happy-path @measured
    Scenario: The tail is minimal
      # Confirmed: "the punch-out silence lead-out is really much less
      # important. If it cuts immediately after the last word, I do not think
      # anyone is going to notice."
      When punch-out refinement runs
      Then the punch-out is placed at or shortly after "1:14:48.900"
      And the tail does not exceed 0.5 seconds
      And no audio from the following Block is included

    @happy-path @measured
    Scenario: The cut lands after the amen and before what follows
      # Confirmed: "We cut after the amen of the prayer and before the pitch to
      # communion."
      Given the prayer ends with "in Jesus name we pray, amen" at "1:14:48.900"
      And a communion Block begins at "1:14:55.000"
      When punch-out refinement runs
      Then the punch-out falls between "1:14:48.900" and "1:14:55.000"
      And the evidence records "after the closing amen, before communion"

    @happy-path @measured
    Scenario: The same rule at the end of a class
      Given the Segment is classified "lesson"
      And the prayer ends at "1:03:52.400"
      And a qa Block begins at "1:03:58.000"
      When punch-out refinement runs
      Then the punch-out falls between "1:03:52.400" and "1:03:58.000"
      And the Q&A is excluded

  Rule: The cut is kept clear of noise

    @happy-path @measured
    Scenario: A quiet margin around the cut
      When punch-out refinement runs
      Then the punch-out is placed at least 250 ms away from the nearest audible sound
      And the resulting ending sounds natural rather than clipped

    @happy-path
    Scenario: No quiet margin is available
      Given the next Block begins immediately with no quiet between
      When punch-out refinement runs
      Then the punch-out is placed at the quietest available point
      And the Segment is flagged "no clean cut point found at punch-out"
      And the reviewer is prompted to place it by hand

  Rule: The machine says how confident it is in the cut itself

    @happy-path
    Scenario: Cut difficulty is assessed at the punch-out too
      # Same grading as the punch-in, but the stakes are lower — confirmed:
      # "the punch in is more important than the punch out. More people listen
      # to the beginning than to the end."
      When punch-out refinement runs
      Then the cut is graded "easy" or "hard" on the same basis as the punch-in
      And a hard punch-out is flagged for review
      And a hard punch-out is treated as less urgent than a hard punch-in

  Rule: The punch-out never clips the last word

    @happy-path
    Scenario: A candidate falling mid-word is moved
      Given a candidate falls at "1:14:48.400" during the final word
      When punch-out refinement runs
      Then the punch-out is moved to after the word ends
      And the final word is complete in the output

    @edge-case
    Scenario: The recording stops before the teaching ends
      Given the Recording ends at "1:05:00" while the preacher is still speaking
      When punch-out refinement runs
      Then the punch-out is placed at the end of the Recording
      And the Segment is flagged "recording may have stopped early"

    @edge-case
    Scenario: The punch-out would land before the punch-in
      Given refinement would produce a punch-out earlier than the punch-in
      When punch-out refinement runs
      Then the refinement is rejected
      And the punch-out falls back to the end of the seeding Block
      And the Proposal confidence is reduced
