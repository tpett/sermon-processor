@interface @happy-path
Feature: Reviewing the segments in a recording
  In order to publish the sermon and leave the rest
  As a reviewer
  I want to decide what happens to each session found in a recording

  A Recording may hold a class, a service, and some music. I want to approve the
  one I am publishing, leave the others alone, and know that leaving them alone
  does not mean losing them.

  Background:
    Given I am signed in as a reviewer
    And a Recording in state "awaiting_review" containing 3 Segments:
      | # | classification | boundaries        | confidence |
      | 1 | lesson         | 0:04:10 – 1:03:55 | high       |
      | 2 | music          | 1:28:40 – 1:54:50 | high       |
      | 3 | sermon         | 2:00:20 – 2:43:32 | high       |

  Rule: Each segment is dispositioned independently

    @happy-path
    Scenario: Approving one segment and skipping the rest
      When I approve Segment 3
      And I skip Segment 1
      And I skip Segment 2
      Then Segment 3 enters "approved" and is queued for processing
      And Segments 1 and 2 enter "skipped"
      And the Recording enters "reviewed"
      And exactly one MP3 will be produced

    @happy-path
    Scenario: Approving two segments from one recording
      When I approve Segment 1
      And I approve Segment 3
      And I skip Segment 2
      Then two separate processing jobs are queued
      And two separate MP3s will be produced
      And each carries its own publication details

    @happy-path
    Scenario: Skipping does not delete
      When I skip Segment 1
      Then its boundaries, classification, confidence and evidence remain stored
      And it remains visible on the Recording detail view
      And I can approve it at any point in the future

    @happy-path
    Scenario: Revisiting a segment months later
      Given Segment 1 was skipped on "2026-08-16"
      When I open the Recording on "2026-11-04" and approve Segment 1
      Then it is processed using its stored boundaries
      And Analysis does not need to run again
      And the resulting MP3 is identical to what it would have been in August

    @happy-path
    Scenario: Changing my mind about an approved segment before it renders
      Given I approved Segment 3 a moment ago
      When I revert it to proposed
      Then the queued processing job is cancelled
      And the Segment returns to "proposed"

  Rule: The ordinary week is three clicks

    @happy-path @measured
    Scenario: Preview in, preview out, approve
      # Q75 — this is the workflow the whole system is aiming at: "if we can get
      # this to work 80% of the time, then it is just: hit play to preview the
      # punch-in, hit play to preview the punch-out, approve, and we are done."
      Given a Segment classified "sermon" whose cuts are both graded "easy"
      When I preview the punch-in
      And I preview the punch-out
      And I approve
      Then the Segment is queued for processing
      And I did not have to open the waveform editor

    @happy-path
    Scenario: The two previews are the primary controls
      When I open a proposed Segment
      Then previewing the punch-in and previewing the punch-out are the most prominent actions
      And approving is available without any further step
      And boundary editing is available but not required

    @happy-path
    Scenario: A hard cut interrupts the three-click path
      Given a Segment whose punch-in is graded "hard"
      When I open it
      Then I am told the punch-in needs checking and why
      And the waveform editor is opened ready for the adjustment

  Rule: The reviewer can tell segments apart without listening much

    @happy-path
    Scenario: Reading the shape of the service
      When I open the Recording detail view
      Then I see every Block in order with its type and its one-line summary
      And I can see the whole shape of the service without playing anything

    @happy-path
    Scenario: Previewing the identifiable moment
      # Q10 — "identify a piece of that segment that is most likely going to be
      # highly identifiable for the human. They can just hit a Preview button
      # that will play just that little segment."
      When I press Preview on a Block
      Then playback starts at that Block's cue excerpt
      And it stops at the end of the excerpt
      And a few seconds is enough for me to recognise what the Block is

    @happy-path
    Scenario: Previewing a proposed segment
      When I press Preview on a Segment
      Then playback starts at the cue excerpt of its seeding Block
      And I can tell whether this is the message I meant to publish

    @happy-path
    Scenario: Jumping to a specific spot instead
      When I choose to start playback at a specific Block
      Then playback seeks there rather than to the cue excerpt

    @happy-path
    Scenario: Seeing where each segment sits in the recording
      When I open the Recording detail view
      Then all Blocks are drawn on a single waveform of the whole Recording
      And each is coloured by its type
      And proposed Segments are drawn as spans above the Blocks they cover
      And clicking one selects it for review

    @happy-path
    Scenario: The likely sermon is offered first
      When I open the Recording detail view
      Then the Segment most likely to be the sermon is expanded by default
      And the others are collapsed but visible

    @happy-path
    Scenario: The transcript is scoped to the selected segment
      Given I have selected a Segment
      When I read the transcript
      Then I see the transcript for that Segment
      And I can expand to the full Recording transcript if I want it

  Rule: Nothing is published by accident

    @happy-path
    Scenario: Music is not proposed for publication
      When I open the Recording detail view
      Then Segment 2 is shown but not offered as a publication candidate
      And I can still approve it if I choose to

    @edge-case
    Scenario: Leaving a recording part-reviewed
      When I approve Segment 3 and leave Segments 1 and 2 alone
      Then the Recording stays in "awaiting_review"
      And it still appears as needing attention
      And I am not forced to disposition everything in one sitting

    @edge-case
    Scenario: A recording where nothing was found
      Given a Recording in "awaiting_review" containing 0 Segments
      When I open the Recording detail view
      Then I am told nothing was detected
      And I can create a Segment by hand
      And I can discard the Recording in one action

  Rule: Mobile can check and approve; editing is a desktop job

    @happy-path @measured
    Scenario: The ordinary week works on a phone
      # Q25 — confirmed: "Primarily desktop, though a usable mobile interface
      # would be nice... We should be able to do a basic check and approval on
      # mobile. If there are complex edits... those can be desktop only."
      Given I am using a phone
      And a Segment whose cuts are both graded "easy"
      When I open the notification
      Then I can read the summary
      And I can preview the punch-in and the punch-out
      And I can approve
      And the whole flow works without a waveform

    @happy-path
    Scenario: A segment needing real editing says so on mobile
      Given I am using a phone
      And a Segment whose punch-in is graded "hard"
      When I open it
      Then I am told it needs an adjustment better made at a desk
      And I can still skip it, or approve it as-is if I choose to
      And I am not offered a cramped editing surface

    @happy-path
    Scenario: Desktop carries the full editor
      Given I am using a desktop browser
      Then the waveform, zooming, word alignment and nudge controls are all available

    @happy-path
    Scenario: Downloading works everywhere
      Given I am using a phone
      When a Segment is complete
      Then I can download the MP3
