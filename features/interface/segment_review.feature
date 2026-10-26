@interface @happy-path
Feature: Reviewing the segments in a recording
  In order to publish the sermon and leave the rest
  As a reviewer
  I want to decide what happens to each session found in a recording

  A Recording may hold a class and a service. I want to approve the one I am
  publishing, leave the other alone, and know that leaving it alone does not
  mean losing it.

  This Background is the real shape of 2026-09-13: a class, its Q&A, and the
  service, in one three-hour file. The singing between them is Blocks, not a
  Segment — only teaching Blocks seed Segments (features/README.md, "The three
  vocabularies"). An earlier version of this Background had a third Segment
  classified `music`, which cannot exist.

  Background:
    Given a Recording in state "awaiting_review" containing 2 Segments:
      | # | classification | boundaries        | confidence |
      | 1 | lesson         | 0:00:01 – 0:58:17 | high       |
      | 2 | sermon         | 1:56:07 – 2:45:10 | high       |
    And its remaining Blocks are music, prayer, qa and communion

  Rule: Revisiting a Segment reopens its Recording

    @happy-path
    Scenario: A skipped Segment is revisited months later
      # The README has always promised this ("a piece passed over in August can
      # be extracted in November") but no scenario said what it does to the
      # Recording, which had reached "reviewed" precisely because everything was
      # dispositioned. It cannot stay there.
      Given a Recording in state "reviewed"
      And one of its Segments was skipped
      When I revisit that Segment
      Then the Segment returns to "proposed"
      And the Recording returns to "awaiting_review"
      And its boundaries, classification, summary and evidence are unchanged
      And no re-analysis is needed

    @happy-path
    Scenario: The Recording settles again once it is dispositioned
      Given a Recording returned to "awaiting_review" by a revisit
      When I dispose of that Segment
      Then the Recording returns to "reviewed"

  Rule: The reviewer has the last word on what a Segment is

    @happy-path
    Scenario: Correcting what the machine decided a Segment is
      # The classification is not only a label: it picks the intent a Segment is
      # approved with, so one called anything but a sermon defaults to archive
      # rather than publish. Before this the reviewer had no way to correct it.
      Given a proposed Segment classified "sermon"
      When I reclassify it as "lesson"
      Then the Segment is classified "lesson"
      And the change is recorded against the Segment
      And its boundaries are unchanged

    @edge-case
    Scenario: A Segment that has been approved keeps its classification
      Given a rendered Segment classified "sermon"
      When I try to reclassify it
      Then the classification is unchanged
      And I am told it can no longer be reclassified

  Rule: Each segment is dispositioned independently

    @happy-path
    Scenario: Approving one segment and skipping the rest
      When I approve Segment 2
      And I skip Segment 1
      Then Segment 2 enters "approved" and is queued for processing
      And Segment 1 enters "skipped"
      And the Recording enters "reviewed"
      And exactly one MP3 will be produced

    @happy-path
    Scenario: Approving two segments from one recording
      When I approve Segment 1
      And I approve Segment 2
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
      Given I approved Segment 2 a moment ago
      When I revert it to proposed
      Then the queued processing job is cancelled
      And the Segment returns to "proposed"

  Rule: The ordinary week is three clicks

    @happy-path @measured @stated
    Scenario: Preview the cut, then approve
      # Q75 — this is the workflow the whole system is aiming at: "if we can get
      # this to work 80% of the time, then it is just: hit play to preview the
      # punch-in, hit play to preview the punch-out, approve, and we are done."
      #
      # The two auditions became one: "My most common workflow when I come in
      # here is that I hit Preview the whole cut. That's the button I hit first.
      # If everything looks good, I hit Approve and Render." -- the owner,
      # 2026-10-26. The preview plays every seam of the cut in turn.
      Given a Segment classified "sermon" whose cuts are both graded "easy"
      When I choose to preview the cut
      And I approve
      Then the Segment is queued for processing
      And I did not have to open the waveform editor

    @happy-path @stated
    Scenario: Previewing the whole cut is the primary control
      When I open a proposed Segment
      Then previewing the whole cut is the most prominent action
      And approving is available without any further step
      And boundary editing is available but not required

    @happy-path
    Scenario: A hard cut interrupts the three-click path
      Given a Segment whose punch-in is graded "hard"
      When I open a proposed Segment
      Then I am told the punch-in needs checking and why
      And the page is ready to edit the cut
      And the waveform editor is opened ready for the adjustment

  Rule: Reviewing comes first, and editing is one switch away

    # "We can almost hide all the editing stuff unless I need to edit, and I can
    # switch to editing mode." -- the owner, 2026-10-26, after "The current
    # version of the UI for this app is pretty busy and distracts from the main
    # things: audio editing, approval, viewing the service order, and things like
    # that." A seam is a place the published audio jumps: the punch-in, the join
    # across each removed span, and the punch-out.

    @happy-path @stated
    Scenario: A Segment opens ready to review
      When I open a proposed Segment
      Then the page is ready to review the cut
      And the whole recording is shown with the Segment marked on it
      And each seam of the cut has a card with the words either side and a control to hear just that seam
      And the detail waveform, zoom, nudges, boundary timecodes and removal marking are not offered

    @happy-path @stated
    Scenario: Switching to editing
      When I open a proposed Segment
      And I switch to editing the cut
      Then the page is ready to edit the cut
      And the detail waveform, zoom, nudges, boundary timecodes and removal marking are offered
      And approving waits until I am done editing

    @happy-path
    Scenario: Editing can be asked for by address
      # A reload mid-edit, or a link to the editor at a zoom, lands in the editor
      # rather than back at the review.
      When I open a proposed Segment's editor by its address
      Then the page is ready to edit the cut

    @happy-path @stated
    Scenario: The cut can be heard without leaving the editor
      # "In editing mode, it would still be good to be able to preview the cuts
      # before marking editing as done, so you do not have to jump back into the
      # editor if it's not quite right." -- the owner, 2026-10-26.
      When I open a proposed Segment
      And I switch to editing the cut
      Then previewing the whole cut and hearing each seam are offered beside the editor

    @happy-path
    Scenario: Finishing editing returns to the review
      When I open a proposed Segment
      And I switch to editing the cut
      And I finish editing
      Then the page is ready to review the cut
      And approving is available without any further step

    @happy-path @stated
    Scenario: The service order sits beside the cut while reviewing and while editing
      When I open a proposed Segment
      Then the service order is shown beside the cut
      When I switch to editing the cut
      Then the service order is shown beside the cut

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

  Rule: I am told whose voice this is before I publish it

    @happy-path @measured
    Scenario: The speaker is identified on the Segment
      # This is the one place the system can cause real harm: a guest preacher
      # who asked not to be distributed, approved ten days later by a reviewer
      # who has forgotten. The safeguard was a memory the spec declined to store.
      #
      # Identification costs about a second per block and was measured at 4 of 4,
      # leave-one-out (speaker_diarization.feature). It exists; it was simply
      # never surfaced.
      When I open a proposed Segment
      Then I am told which enrolled voice is teaching, and how confidently
      And an unrecognised voice is shown as "not a known voice"

    @happy-path @policy
    Scenario: An unrecognised voice is confirmed before it is published
      Given a Segment whose teaching voice matches no enrolled profile
      And its intent is "publish"
      When I approve it
      Then I am asked to confirm that this recording may be distributed
      And the confirmation is recorded with the approval
      # Not a block — a guest preacher is normal. It is one deliberate step in
      # front of the only irreversible mistake this system enables.

    @happy-path
    Scenario: Confirming who preached enrols them
      # This is what makes the voice library self-maintaining, and it is the only
      # thing publication_details.feature's "nothing more is collected" rule has
      # to give ground on.
      When I confirm or correct who was preaching
      Then that Segment strengthens or creates that speaker's profile
      And no separate enrolment session is ever required

  Rule: Nothing is published by accident

    @happy-path
    Scenario: Music is never a publication candidate, because it is never a Segment
      # It is not filtered out of a list of candidates — it never enters one.
      When I open the Recording detail view
      Then the music Blocks are shown in the anatomy of the Recording
      And no Segment was proposed for them
      And nothing offers them for publication

    @edge-case
    Scenario: Leaving a recording part-reviewed
      When I approve Segment 2 and leave Segment 1 alone
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

  Rule: A phone gets the full editor, reflowed to fit

    @happy-path @measured
    Scenario: The ordinary week works on a phone
      # Q25 — confirmed: "Primarily desktop, though a usable mobile interface
      # would be nice... We should be able to do a basic check and approval on
      # mobile. If there are complex edits... those can be desktop only."
      Given I am using a phone
      And a Segment whose cuts are both graded "easy"
      When I open the notification
      Then I can read the summary
      And I can preview the whole cut
      And I can approve
      And the whole flow works without opening the editor

    @happy-path @stated
    Scenario: A segment needing real editing can be edited on a phone
      # "Mobile is good enough as is." -- the owner, 2026-10-03, of the page as
      # shipped: a phone is offered the same editor as a desk, reflowed to its
      # width. That replaces Q25's "complex edits... can be desktop only", which
      # had been specified as a "better made at a desk" message and no editor.
      Given I am using a phone
      And a Segment whose punch-in is graded "hard"
      When I open it
      Then the waveform and the nudge controls are offered
      And the page fits the phone's width without scrolling sideways
      When I finish editing
      Then I can still skip it, or approve it as-is if I choose to

    @happy-path
    Scenario: Desktop carries the full editor
      Given I am using a desktop browser
      When I open a proposed Segment
      And I switch to editing the cut
      Then the waveform, zooming, word alignment and nudge controls are all available

    @happy-path
    Scenario: Downloading works everywhere
      Given I am using a phone
      When a Segment is complete
      Then I can download the MP3
