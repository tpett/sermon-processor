@interface @happy-path
Feature: The recording detail view
  In order to understand and act on one recording
  As a reviewer
  I want a page showing its metadata, the segments found inside it, and controls

  Background:
    Given I am on the tailnet
    And a Recording from "2026-08-16 09:00 AM" in state "awaiting_review"
    And it contains 2 Segments:
      | classification | spans             | boundaries        | confidence |
      | lesson         | 0:00:00 – 1:05:20 | 0:04:10 – 1:03:55 | high       |
      | sermon         | 1:28:40 – 3:12:00 | 2:00:20 – 2:43:32 | high       |

  Rule: The detail view explains the recording

    @happy-path @measured
    Scenario: Viewing technical and source metadata
      When I open the Recording detail view
      Then I see:
        | field              | value                                     |
        | Recorded at        | 2026-08-16 09:00 AM                       |
        | Source duration    | 3:12:00                                   |
        | File size          | 1.4 GB                                    |
        | Format             | FLAC 44.1 kHz 32-bit, channel 1 only      |
        | Source object key  | recordings/recording_20260816_090004.flac |
        | Device             | sanctuary-pi-01                           |

    @happy-path
    Scenario: Source warnings are visible
      Given the Recording is flagged "source clipping detected"
      When I open the Recording detail view
      Then I see the clipping warning
      And it explains that this originates at the recorder and cannot be repaired here

    @happy-path
    Scenario: Viewing the segments
      When I open the Recording detail view
      Then I see both Segments listed in the order they occur
      And each shows its classification, its proposed boundaries and its length
      And each shows its confidence
      And each can be opened for review independently

    @happy-path
    Scenario: Viewing progress for a recording still being worked on
      Given the Recording is in state "analyzing"
      When I open the Recording detail view
      Then I see which analysis stage is currently running
      And I see which stages have completed
      And no Segments are shown yet

    @happy-path
    Scenario: Viewing a failure
      Given the Recording is in state "analysis_failed" with reason "transcription timed out"
      When I open the Recording detail view
      Then I see the failure reason
      And I can retry Analysis
      And I can create a Segment by hand instead

    @happy-path
    Scenario: Viewing the processing log
      When I expand the processing log
      Then I see each state transition with its timestamp
      And I see each job attempt, including retries and failures
      And I see who performed each human action, against which Segment

  Rule: Actions available depend on state

    @happy-path
    Scenario Outline: Recording-level actions
      Given the Recording is in state "<state>"
      When I open the Recording detail view
      Then the available recording-level actions are "<actions>"

      Examples:
        | state           | actions                                                       |
        | discovered      | Discard                                                       |
        | analyzing       | Discard                                                       |
        | analysis_failed | Retry analysis, Create segment by hand, Discard               |
        | awaiting_review | Re-run analysis, Split segment, Merge segments, Create segment, Archive whole recording, Discard |
        | reviewed        | Create segment, Archive whole recording, Discard              |
        | discarded       | Restore                                                       |

    @happy-path
    Scenario: Archiving the whole recording without editing it
      # Q68 — the members meeting case: keep it for posterity, boundaries do
      # not matter, never published.
      When I choose to archive the whole recording
      Then a Segment is created spanning the entire Recording
      And it is classified "meeting"
      # The only Segment classification that comes from a human action rather
      # than from a seed Block's type. No classifier ever emits it; see
      # features/README.md, "The three vocabularies".
      And its intent is "archive"
      And it is approved for processing without asking me for boundaries

    @happy-path
    Scenario: The original FLAC is always available
      When I open the Recording detail view
      Then I can download the original FLAC regardless of the Recording's state
