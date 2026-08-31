@interface @happy-path
Feature: Adjusting a segment's punch points
  In order to correct the machine's guess
  As a reviewer
  I want to move a Segment's punch-in and punch-out precisely

  Background:
    Given I am signed in as a reviewer
    And a Recording in state "awaiting_review"
    And I have selected a Segment classified "sermon" spanning "1:28:40" to "3:12:00"
    And its punch-in is "2:00:20.000" and punch-out is "2:43:32.000"

  Rule: Boundaries can be moved several ways

    @happy-path
    Scenario: Dragging a boundary on the waveform
      When I drag the punch-in handle to "2:00:16.500"
      Then the punch-in becomes "2:00:16.500"
      And the highlighted region updates
      And the segment length updates to "0:43:15.500"

    @happy-path
    Scenario: Typing an exact timecode
      When I set the punch-out to "2:43:30.250"
      Then the punch-out becomes "2:43:30.250"

    @happy-path
    Scenario Outline: Nudging with keyboard controls
      When I nudge the punch-in <direction> by "<amount>"
      Then the punch-in becomes "<result>"

      Examples:
        | direction | amount | result       |
        | earlier   | 0.1 s  | 2:00:19.900  |
        | earlier   | 1 s    | 2:00:19.000  |
        | later     | 1 s    | 2:00:21.000  |
        | later     | 10 s   | 2:00:30.000  |

    @happy-path
    Scenario: Setting a boundary from the playhead
      When I play to "2:00:18.400"
      And I set the punch-in to the current playhead position
      Then the punch-in becomes "2:00:18.400"

    @happy-path
    Scenario: Setting a boundary from the transcript
      When I choose an utterance that begins at "2:00:20.500"
      And I set the punch-in to the start of that utterance
      Then the punch-in becomes "2:00:20.500"

    @happy-path
    Scenario: Snapping to the nearest silence
      When I ask to snap the punch-in to the nearest silence
      Then the punch-in moves to the nearest silence gap boundary
      And the amount it moved is shown

    @happy-path
    Scenario: Jumping to an alternative candidate
      Given Analysis recorded an alternative punch-in candidate at "1:54:50"
      When I choose that alternative
      Then the punch-in becomes "1:54:50"
      And the evidence panel shows why that candidate was considered

  Rule: The cut must sound natural

    @happy-path @measured
    Scenario: A quiet margin is enforced as I drag
      # Confirmed: "we need to make sure the edit is far away from any noise.
      # By far away, I mean probably even 250 ms."
      When I drag the punch-in to a point 80 ms from audible speech
      Then I am warned that the cut is too close to the audio
      And I am offered the nearest point with a 250 ms margin
      And I can override the warning if I mean it

    @happy-path
    Scenario: Seeing where the clean cut points are
      When I zoom in around a boundary
      Then spans with at least 250 ms of quiet are visually marked
      And I can drop a boundary into one with a single click

    @happy-path @measured
    Scenario: Cutting just before the usual greeting
      # Confirmed: "Our primary teacher usually starts the message with
      # 'good morning', and that is usually a good cut point."
      Given the teaching begins with "good morning"
      When I ask to snap the punch-in to the start of speech
      Then the punch-in lands immediately before "good morning"

    @happy-path
    Scenario: Skipping a false start by hand
      # Confirmed: "Sometimes, when it is unnatural for one reason or another,
      # I might cut that out and move a little bit ahead of it." The engine does
      # not decide this; it just has to be easy.
      Given the opening contains a throat-clear before the first real words
      When I move the punch-in past it
      Then the adjustment is accepted without warning
      And the machine proposal remains available to revert to

  Rule: Words are visible against the waveform

    @happy-path @measured
    Scenario: Reading the transcript along the timeline
      # Confirmed: "If we could even include the words next to the waveform
      # somehow in the visualization, that would be amazing."
      When I zoom in around a boundary
      Then the transcript words are shown aligned to their position on the waveform
      And I can see exactly which word each boundary falls before or after
      And clicking a word places the boundary at that word

    @happy-path
    Scenario: Words are hidden when they would be unreadable
      Given I am viewing the whole recording at overview resolution
      Then individual words are not drawn
      And the Block types and summaries are shown instead

  Rule: Invalid boundaries are prevented

    @edge-case
    Scenario: The punch-out is dragged before the punch-in
      When I try to set the punch-out to "2:00:00"
      Then the change is rejected
      And I am told the punch-out must be after the punch-in
      And the punch-out remains "2:43:32.000"

    @edge-case
    Scenario Outline: Boundaries outside the Segment
      When I try to set the "<boundary>" to "<value>"
      Then the change is rejected
      And I am told the boundary must fall within the Segment

      Examples:
        | boundary  | value       |
        | punch-in  | 1:20:00.000 |
        | punch-out | 3:20:00.000 |

    @happy-path
    Scenario: Extending a Segment beyond its detected span
      When I extend the Segment's own start to "1:26:00"
      Then the Segment's span grows
      And the punch-in may now be placed anywhere within the new span
      And the change is rejected if it would overlap the neighbouring Segment

    @edge-case
    Scenario: A zero-length or near-zero-length selection
      When I try to set a span shorter than 1 second
      Then the change is rejected
      And I am told the selection is too short

    @edge-case @measured
    Scenario: An unusually short or long selection is allowed but warned about
      # Published segments in the sample set run 40-68 minutes.
      When I set a span of 6 minutes
      Then the change is accepted
      And I am warned that the length is outside the expected range
      And I can approve anyway

  Rule: My work is not lost

    @happy-path
    Scenario: Adjustments are saved
      When I adjust the punch-in to "2:00:16.500"
      Then the adjustment is saved without approving
      And it survives me reloading the page
      And the Segment stays in "proposed"

    @happy-path
    Scenario: Reverting to the machine proposal
      # Q14 — confirmed: "I would not want a processor to lose any human input,
      # but a human could choose to discard edits that they have made."
      Given I have adjusted the punch-in to "2:00:16.500"
      When I revert to the proposed boundaries
      Then the punch-in returns to "2:00:20.000"
      And my discarded adjustment is recorded in the history

    @happy-path
    Scenario: The machine never discards my edits on its own
      Given I have adjusted a Segment's boundaries
      When Analysis is re-run
      Then my adjustment survives
      And the new machine proposal is offered beside it, not applied over it

    @happy-path
    Scenario: Adjusting one segment leaves the others alone
      Given the Recording contains another Segment classified "lesson"
      When I adjust this Segment's punch-in
      Then the other Segment's boundaries are unchanged

  Rule: Archival segments do not need this

    @happy-path
    Scenario: An archival segment skips boundary editing
      Given I have selected a Segment whose intent is "archive"
      When I open it
      Then the boundary controls are collapsed
      And I am told the whole span will be kept
      And I can still expand the controls and trim it if I want to
