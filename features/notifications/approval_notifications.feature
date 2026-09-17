@notifications
Feature: Notifying a reviewer
  In order to act on a recording without watching a dashboard
  As a reviewer
  I want to be told when something needs me

  The channel is deliberately not decided here. What matters is the
  **Notification** itself — a record of what happened, who it is for, and
  whether it was delivered. Whether that record is delivered as a push from a
  PWA, an email, or a message into a chat workspace is a technology choice that
  can be made later without touching anything in this file.

  # Q42 — confirmed: "the fundamental piece is still a notification object that
  # is going to track the actual notification, so which channel we use is
  # largely irrelevant at this point."

  Background:
    Given a reviewer is configured to receive notifications

  Rule: A Notification is a record, not a message

    @happy-path @measured
    Scenario: Every notification is recorded before it is sent
      When something happens that a reviewer should know about
      Then a Notification is created with:
        | field      | meaning                                        |
        | subject    | the Recording or Segment it concerns           |
        | kind       | why it was raised                              |
        | recipient  | who it is for                                  |
        | summary    | what it says, in plain text                    |
        | created_at | when it was raised                             |
        | state      | pending, delivered, failed or suppressed       |
      And the Notification exists whether or not any channel is configured

    @happy-path
    Scenario: No channel configured
      Given no delivery channel is configured
      When a Notification is created
      Then it is recorded and left undelivered
      And it is visible in the interface
      And nothing fails
      # The system is usable before the channel question is answered.

    @happy-path
    Scenario: The channel is pluggable
      Then delivering a Notification is separate from creating one
      And adding or changing a channel does not change when Notifications are raised
      And the same Notification can be delivered by more than one channel

    @happy-path
    Scenario: Notifications are visible in the interface regardless
      When I open the interface
      Then I see the Notifications raised for me
      And I can see which were delivered and which were not

  Rule: A reviewer is notified when analysis finds something publishable

    @happy-path
    Scenario: Notification when a sermon is found
      Given a Recording finishes Analysis with a "sermon" Segment at high confidence
      Then the reviewer is notified
      And the notification states the recording date and the proposed segment length
      And the notification links directly to that Segment

    @happy-path
    Scenario: Notification when a recording holds more than one session
      Given a Recording finishes Analysis with a "lesson" Segment and a "sermon" Segment
      Then the reviewer is notified once for the Recording
      And the notification says two sessions were found
      And it names each one's classification and length

    @happy-path
    Scenario: Nothing publishable means no notification
      Given a Recording finishes Analysis with only music Blocks and no Segments
      Then a Notification is recorded as suppressed and nothing is delivered
      And the Recording is still visible in the recordings list
      # Band practice arrives most weeks. It should never interrupt anyone.

    @happy-path
    Scenario: A low-confidence proposal says so
      Given a Recording finishes Analysis with a "sermon" Segment at low confidence
      Then the notification says the proposal needs careful review
      And it states why confidence is low

    @happy-path
    Scenario: A recording with content but no teaching the machine recognised
      # This used to posit a Segment classified "other", which cannot exist --
      # only teaching Blocks seed Segments. The real case is a Recording with
      # substantive speech where nothing was typed as teaching, and it is not
      # hypothetical: the two 2026-07-18 course recordings and the 2026-08-16
      # members' meeting are exactly this.
      #
      # It must not be silent, because the fix is one click away -- retyping a
      # Block re-runs Segment proposal (see analysis/block_classification.feature).
      Given a Recording finishes Analysis with substantive speech
      And no Block was typed as teaching, so no Segment was proposed
      Then the reviewer is notified that content was found but no teaching was identified
      And the notification says the Blocks can be retyped to produce a Segment
      And this is distinguished from a Recording that held nothing at all

    @happy-path
    Scenario: Notification when analysis fails
      Given a Recording enters "analysis_failed"
      Then the reviewer is notified that analysis failed
      And the notification states the failure reason

    @happy-path @assumption
    Scenario: Notification when processing completes
      # Q44 — is "your MP3 is ready" wanted, or is the list enough?
      Given a Segment finishes processing
      Then the reviewer is notified that the artifact is ready
      And the notification links to the download

    @happy-path
    Scenario: Notification when processing fails
      Given a Segment enters "processing_failed"
      Then the reviewer is notified
      And the notification states the failure reason

  Rule: Notifications do not become noise

    @edge-case
    Scenario: Several recordings finish at once
      # A Sunday can produce practice, a class and the service within minutes.
      Given three Recordings finish Analysis within 5 minutes
      Then the reviewer receives one notification covering all three
      And it lists what was found in each

    @edge-case
    Scenario: A recording is re-analysed
      Given a Recording has already notified the reviewer
      When Analysis is re-run and completes again
      Then the reviewer is notified again
      And the notification says it is an updated proposal

    @edge-case @measured
    Scenario: Nothing has been reviewed in a while
      # In the sample set, several sermons were exported a week or more after
      # they were recorded: 2026-05-31 recorded 31 May, exported 10 June.
      Given a Recording has had an undispositioned publishable Segment for 3 days
      Then a reminder is sent to the reviewer

    @edge-case
    Scenario: Skipped segments do not generate reminders
      Given every Segment in a Recording has been approved or skipped
      Then no reminder is sent for that Recording
      And skipped Segments never generate notifications of their own

    @edge-case
    Scenario: Notification delivery fails
      Given the configured channel is unavailable
      When delivery is attempted
      Then delivery is retried
      And the Notification remains recorded with state "failed"
      And the failure is visible on the system health view
      And no Recording or Segment state is affected

    @edge-case
    Scenario: A suppressed notification is still recorded
      Given a Recording produced nothing publishable
      Then a Notification is recorded with state "suppressed"
      And nothing is delivered
      # Keeping the record makes "why was I not told about that Sunday?"
      # answerable without reading logs.

  Rule: Notifications can be turned off

    @happy-path
    Scenario: Opting out
      When a reviewer disables notifications
      Then no further notifications are sent to them
      And recordings still appear in the recordings list
