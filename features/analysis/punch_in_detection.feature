@analysis @happy-path
Feature: Refining a segment's punch-in
  In order for the file to start cleanly on the first words
  As the Sermon Processor
  I want the punch-in placed precisely at the start of the teaching

  Segment proposal already decided *which* Block the Segment starts on. This
  stage decides exactly *where* inside the run-up to that Block the cut falls.

  All timecodes are absolute against the source Recording.

  Background:
    Given a Segment classified "sermon" seeded on a Block beginning at "0:31:40"
    And the previous Block ends at "0:31:40"

  Rule: The punch-in sits just before the first word

    @happy-path @measured
    Scenario: A short lead-in is included
      # Confirmed: "One second is perfect. If it is too much more than that,
      # people might wonder if the playback is working."
      Given the first word of the Block begins at "0:31:41.500"
      When punch-in refinement runs
      Then the punch-in is placed at "0:31:40.500"
      And the lead-in never exceeds 1.0 second

    @happy-path
    Scenario: The lead-in is shortened rather than crossing into the previous block
      Given the first word begins at "0:31:40.300"
      And the previous Block has audible speech up to "0:31:40.000"
      When punch-in refinement runs
      Then the punch-in is placed after "0:31:40.000"
      And the lead-in is shorter than 1.0 second
      And no audio from the previous Block is included

  Rule: The cut is kept clear of noise

    @happy-path @stated
    Scenario: A quiet margin around the cut
      # Confirmed: "we need to make sure the edit is far away from any noise.
      # By far away, I mean probably even 250 ms. That way, the transition
      # sounds natural."
      When punch-in refinement runs
      Then the punch-in is placed at least 250 ms away from the nearest audible sound
      And the resulting transition sounds natural rather than abrupt

    @happy-path
    Scenario: No quiet margin is available
      Given there is no 250 ms of quiet anywhere in the run-up to the first word
      When punch-in refinement runs
      Then the punch-in is placed at the quietest available point
      And the Segment is flagged "no clean cut point found at punch-in"
      And the reviewer is prompted to place it by hand

    @happy-path
    Scenario: Placement is accurate to 100 ms
      # Confirmed: 100 ms is the working precision.
      When punch-in refinement runs
      Then the punch-in is expressed to millisecond precision
      And the reviewer can move it in steps as small as 100 ms

  Rule: The machine says how confident it is in the cut itself

    @happy-path @measured
    Scenario Outline: Cut difficulty is assessed and recorded
      # Q75 — the error a reviewer will tolerate is not a fixed number of
      # milliseconds; it depends on how hard the transition is. Some cuts are
      # trivially clean. Others sit next to noise or feedback and a human has to
      # place them. The machine should say which kind it just made.
      Given the audio around the chosen punch-in is "<condition>"
      When punch-in refinement runs
      Then the cut is graded "<difficulty>"
      And the grade is shown to the reviewer

      Examples:
        | condition                                         | difficulty |
        | 10 seconds of clean silence before the first word | easy       |
        | 2 seconds of clean silence                        | easy       |
        | between 250 ms and 2 s of quiet                   | moderate   |
        | under 250 ms of quiet, words either side          | hard       |
        | audible noise or feedback near the cut point      | hard       |
        | music fading under the first words                | hard       |

    @happy-path
    Scenario: A hard cut asks for a human
      Given the cut is graded "hard"
      When the Segment is offered for review
      Then it is flagged as needing the punch-in checked by hand
      And the reason is stated, for example "noise near the cut point"
      # Getting a hard cut wrong is acceptable. Getting it wrong quietly is not.

    @happy-path
    Scenario: An easy cut is expected to be right
      Given the cut is graded "easy"
      Then no flag is raised
      And the reviewer is expected to confirm it with a single preview

  Rule: Familiar openings are good cut points

    @happy-path @measured
    Scenario: The regular greeting
      # Confirmed: "Our primary teacher usually starts the message with
      # 'good morning', and that is usually a good cut point. I usually punch in
      # right before that."
      Given the first words of the Block are "good morning"
      When punch-in refinement runs
      Then the punch-in is placed immediately before "good morning"
      And the evidence records "starts on the usual greeting"

    @happy-path
    Scenario Outline: Other common openings
      Given the first words of the Block are "<phrase>"
      When punch-in refinement runs
      Then the punch-in is placed immediately before that phrase
      And that counts as evidence for the punch-in

      Examples:
        | phrase                                        |
        | good morning                                  |
        | if you have your bibles open, turn with me    |
        | I want to pick up where we left off last week |
        | let me pray for us before we begin            |

    @happy-path
    Scenario: An unnatural opening is left for the human
      # Confirmed: sometimes the natural opening is skipped by hand. The engine
      # does not need to decide this, only make it easy to change.
      Given the Block opens with a false start or a throat-clear
      When punch-in refinement runs
      Then the punch-in is still placed before the first words
      And the Segment is flagged "check the opening"
      And an alternative punch-in after the false start is offered as a candidate

  Rule: The punch-in never clips a word

    @happy-path
    Scenario: A candidate falling mid-word is moved
      Given a candidate falls at "0:31:41.200" during a word
      When punch-in refinement runs
      Then the punch-in is moved to the nearest preceding silence
      And no word is cut off

    @edge-case
    Scenario: The Segment starts at the very beginning of the recording
      Given the Recording began while the preacher was already speaking
      And the Segment starts at "0:00:00"
      When punch-in refinement runs
      Then the punch-in is "0:00:00"
      And no lead-in is applied
      And the Segment is flagged "recording may have started late"
