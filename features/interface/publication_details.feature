@interface
Feature: Publication details
  In order to end up with a file I can find again
  As a reviewer
  I want to give each published segment a label

  This replaces the speculative metadata screen in the first draft. With nothing
  downstream of the MP3 (Q58), and with every finished file in
  `~/Desktop/Sermons` named `YYYY-MM-DD - Label`, the real requirement is small:
  a human label. The date in the name is the recording's, never typed — "Naming
  is always based on recording date. Publication date is irrelevant other than
  for logging." (the owner, 2026-10-03). Everything else was invented.

  Background:
    Given I am on the tailnet
    And a Recording from "2026-08-23 10:29 AM"
    And a Segment classified "sermon" awaiting approval

  Rule: A published segment needs a label, and is dated by its recording

    @happy-path @measured
    Scenario: Entering publication details
      When I open the Segment
      Then I can enter a publication label
      And I am not asked for a date

    @happy-path @stated
    Scenario: The publication date is the recording's, kept for the log
      When I approve the Segment with the label "Hebrews 12.4-11"
      Then the label "Hebrews 12.4-11" is saved with the Segment
      And the publication date "2026-08-23" is recorded with the Segment
      And the page does not offer to change it

    @edge-case @stated
    Scenario: A publication date never names the file
      # The date can still be written through the publication details request,
      # which is how rows approved before dates were placed were backfilled.
      When the publication details "2026-08-30" and "Hebrews 12.4-11" are recorded for it
      And the Segment is processed
      Then the publication date "2026-08-30" is recorded with the Segment
      And the output file is named "2026-08-23 - Hebrews 12.4-11.mp3"

    @happy-path @measured
    Scenario Outline: The output filename is built from the recording date and the label
      # Matches the existing convention exactly.
      Given the Recording was made on "<date>" and the label is "<label>"
      When the Segment is processed
      Then the output file is named "<filename>"

      Examples:
        | date       | label            | filename                          |
        | 2026-08-23 | Hebrews 12.4-11  | 2026-08-23 - Hebrews 12.4-11.mp3  |
        | 2026-07-05 | TEC              | 2026-07-05 - TEC.mp3              |
        | 2026-07-18 | CT-Islam         | 2026-07-18 - CT-Islam.mp3         |
        | 2026-06-28 | Members Meeting  | 2026-06-28 - Members Meeting.mp3  |

    @happy-path @assumption
    Scenario: The label is suggested from the transcript for sermons
      # Q31 — the label is a scripture reference in 20 of 24 sample files.
      Given the Segment is classified "sermon"
      And its transcript contains "turn with me to Hebrews chapter 12"
      When I open the Segment
      Then the label is suggested as "Hebrews 12"
      And I can correct it before approving

    @happy-path @assumption
    Scenario: The label is suggested from the classification for other content
      Given the Segment is classified "lesson"
      When I open the Segment
      Then the label is suggested as "TEC"
      And I can correct it before approving

    @happy-path
    Scenario: Two segments from one recording get different labels
      Given a Recording containing a "lesson" Segment and a "sermon" Segment
      When I approve both
      Then each carries its own label
      And the two output files do not collide

  Rule: Archival segments need less

    @happy-path
    Scenario: An archival segment is named from the date
      Given a Segment whose intent is "archive"
      When I approve it without entering a label
      Then the output file is named from the recording date
      And I am not prompted for anything else

  Rule: Filenames stay usable

    @edge-case
    Scenario: A label that would collide with an existing file
      Given a file named "2026-08-23 - Hebrews 12.4-11.mp3" already exists
      When I approve another Segment with the same date and label
      Then I am warned about the collision
      And I can change the label or confirm that this replaces the previous file

    @edge-case
    Scenario Outline: Characters that break filenames
      Given the label is "<label>"
      When the Segment is processed
      Then the output filename is "<filename>"

      Examples:
        | label              | filename                              |
        | Romans 8:1-11      | 2026-08-23 - Romans 8.1-11.mp3        |
        | Faith / Works      | 2026-08-23 - Faith - Works.mp3        |
        | "Come and See"     | 2026-08-23 - Come and See.mp3         |

  Rule: Details can be corrected after publishing

    @happy-path
    Scenario: Renaming after processing
      Given a Segment is "complete" with the label "Hebrews 12.4-1"
      When I correct the label to "Hebrews 12.4-11"
      Then the stored details are updated
      And the downloadable file is renamed
      And the audio is not re-encoded

  Rule: Nothing more is collected

    @assumption
    Scenario: No podcast metadata is requested
      # Q31, Q32 — closed by Q58. There is no feed, no host, no episode summary.
      # If tags are ever wanted, this is the scenario to change.
      When I open the Segment
      Then I am not asked to type a speaker name for the filename
      And I am not asked for a series
      And I am not asked for a description
      And no ID3 tags beyond title and date are written to the MP3
