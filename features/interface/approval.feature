@interface @happy-path
Feature: Approving a segment
  In order to produce the file I am going to publish
  As a reviewer
  I want to approve a Segment's boundaries and hand off to processing

  Background:
    Given I am on the tailnet
    And a Recording in state "awaiting_review"
    And a Segment classified "sermon" with punch-in "2:00:20" and punch-out "2:43:32"

  Rule: Approval locks the boundaries and starts processing

    @happy-path
    Scenario: Approving the machine's proposal unchanged
      When I approve the Segment
      Then the Segment enters "approved"
      And a processing job is queued for that Segment
      And the approval records me as the approver and the time of approval
      And the approved punch-in and punch-out are recorded as "2:00:20" and "2:43:32"

    @happy-path
    Scenario: Approving after adjusting
      Given I adjusted the punch-in to "2:00:16.500"
      When I approve the Segment
      Then the approved punch-in is "2:00:16.500"
      And both the machine proposal and my adjustment are retained in the history

    @happy-path
    Scenario: The boundaries cannot be changed while processing
      Given I have approved the Segment
      When I open it
      Then the boundary controls are read-only
      And I see that processing is in progress

    @happy-path
    Scenario: Watching processing progress
      Given I have approved the Segment
      When processing is running
      Then I see the current processing step
      And I see an indication of progress
      And other Segments in the same Recording remain fully editable

  Rule: Approval requires the segment to be ready

    @edge-case
    Scenario Outline: Approving from a state that does not allow it
      Given the Segment is in state "<state>"
      When I attempt to approve it
      Then the approval is rejected
      And I am told the Segment is not ready for approval

      Examples:
        | state      |
        | processing |
        | approved   |

    @happy-path
    Scenario: Approving a previously skipped segment
      Given the Segment is in state "skipped"
      When I approve it
      Then it enters "approved" and is queued for processing
      And no re-analysis is required

    @edge-case
    Scenario: Approving a segment someone else already approved
      Given another reviewer approved the Segment a moment ago
      When I attempt to approve it
      Then I am told it has already been approved
      And no second processing job is queued

    @happy-path @measured
    Scenario: A publication label is required before publishing
      # Every finished file in ~/Desktop/Sermons is named "YYYY-MM-DD - Label".
      # The label is the only thing typed by hand, so it is the only requirement.
      Given the Segment's intent is "publish"
      And no publication label has been entered
      When I approve the Segment
      Then I am prompted for the label
      And the approval does not proceed until it is supplied

    @happy-path
    Scenario: An archival segment needs no label
      Given the Segment's intent is "archive"
      When I approve the Segment
      Then no label is required
      And the output is named from the recording date alone

  Rule: Publish or archive is always a human decision

    @happy-path
    Scenario: Intent is suggested but never assumed
      # Q69 — "This should be editable by the human user. In general, sermons
      # will always be published, but I cannot anticipate every eventuality.
      # Keeping this human gated is the best call."
      Given the Segment is classified "sermon"
      When I open it
      Then the intent is prefilled as "publish"
      And I can change it to "archive" before approving
      And the intent I approved with is recorded

    @happy-path
    Scenario: Archiving a sermon without publishing it
      Given a guest preacher asked not to be distributed
      When I set the intent to "archive" and approve
      Then the Segment renders as an archive copy
      And it is not presented as a published product

    @happy-path
    Scenario: Publishing something that defaulted to archive
      # `meeting` Segments exist only because a reviewer archived a whole
      # Recording (see interface/recording_detail.feature). Their intent
      # defaults to archive, and this is the path back out of that default.
      Given the Segment is classified "meeting"
      When I change the intent to "publish" and approve
      Then the Segment renders with the full publication treatment
      And I am asked for a label

    @happy-path
    Scenario: Nothing renders without an explicit approval
      Then no Segment is ever rendered without a human approving it
      And no Segment is ever published on classification alone

  Rule: An approval can be undone before processing finishes

    @edge-case
    Scenario: Cancelling processing
      # Q30 — low priority, but cheap here because Segments are independent.
      Given I approved the Segment and processing has started
      When I cancel processing
      Then the processing job stops
      And the Segment returns to "proposed"
      And any partial output is discarded
