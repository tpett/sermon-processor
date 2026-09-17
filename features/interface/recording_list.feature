@interface @happy-path
Feature: The recordings list
  In order to see what needs my attention
  As a reviewer
  I want a list of every recording with its status and what was found inside it

  This is the home page. A recording's row summarises the Segments inside it,
  because a Recording is a file and a Segment is the thing I actually care about.

  Background:
    Given I am on the tailnet
    And the following Recordings exist:
      | recorded_at         | duration | state           | segments                        |
      | 2026-08-23 10:29 AM | 1:44:29  | awaiting_review | 1 sermon (high)                 |
      | 2026-08-16 09:00 AM | 3:12:00  | awaiting_review | 1 lesson (high), 1 sermon (high)|
      | 2026-08-16 08:15 AM | 0:52:10  | reviewed        | 1 music                         |
      | 2026-08-09 10:29 AM | 1:44:10  | reviewed        | 1 sermon (complete)             |
      | 2026-08-02 10:30 AM | 1:33:10  | analysis_failed | none                            |
      | 2026-07-26 10:30 AM | 0:04:12  | discarded       | none                            |

  Rule: The list shows what is inside each recording

    @happy-path
    Scenario: Viewing the list
      When I visit the recordings list
      Then I see 5 recordings
      And each row shows the recording date and time
      And each row shows the source duration
      And each row shows the current state
      And each row summarises the Segments found inside it by classification
      And each row shows the confidence of its most publishable Segment

    @happy-path
    Scenario: A recording containing two sessions
      When I visit the recordings list
      Then the row for "2026-08-16 09:00 AM" shows that it contains a lesson and a sermon
      And I can see at a glance that both still need dispositioning

    @happy-path
    Scenario: Recordings needing attention are obvious
      When I visit the recordings list
      Then recordings with undispositioned publishable Segments are visually distinguished
      And recordings in "analysis_failed" are visually distinguished
      And the count of Segments awaiting disposition is shown

    @happy-path
    Scenario: Band practice does not demand attention
      # This used to say the recording "contains only a music Segment", which
      # cannot happen: only teaching Blocks seed Segments, so a rehearsal
      # produces none at all. Measured — on 2026-08-30 and 2026-09-06 both
      # models proposed zero Segments for the band rehearsal, which is the
      # correct behaviour and the thing this scenario should assert.
      Given the recording from "2026-08-16 08:15 AM" has kind "rehearsal"
      And no Segment was proposed for it
      When I visit the recordings list
      Then it is not counted as needing attention
      And it is still visible in the list
      # Q36 — this is how practice stops costing a click every week.

    @happy-path
    Scenario: The newest recording is first
      When I visit the recordings list
      Then the recordings are ordered by recording date, newest first

    @happy-path
    Scenario: Opening a recording
      When I click the row for the recording from "2026-08-23"
      Then I am taken to that Recording's detail view

  Rule: The list can be narrowed

    @happy-path
    Scenario Outline: Filtering
      When I filter the list by "<filter>"
      Then I see only recordings matching "<meaning>"

      Examples:
        | filter              | meaning                                     |
        | Needs attention     | has an undispositioned publishable Segment  |
        | In progress         | analyzing or processing                     |
        | Failed              | analysis_failed or processing_failed         |
        | Published           | has at least one complete Segment           |
        | Nothing to publish  | no publishable Segment was found            |
        | Skipped segments    | has a Segment left for later                |
        | Ignored             | set aside as having no substantive content  |

    @happy-path @measured
    Scenario: Finding a recording by what it was
      # Q63 promises a Segment passed over in August can be extracted in
      # November. At the measured arrival rate — 3.5 recordings a week — that is
      # roughly 900 by year five. Stored and findable are different promises and
      # only the first was ever specified: this list has no search, sorts newest
      # first only, and paginates.
      When I search for "Hebrews 12"
      Then I see recordings whose label or summary matches
      And I can search by date, by classification, and by what was said

    @happy-path @assumption
    Scenario: Filtering by what is inside
      # Useful once there is a year of these: "show me the TEC classes".
      When I filter the list by the classification "lesson"
      Then I see only recordings containing a Segment classified "lesson"

    @happy-path
    Scenario: Discarded recordings are hidden by default
      When I visit the recordings list
      Then the discarded recording from "2026-07-26" is not shown
      And I can reveal it by including discarded recordings in the filter

    @happy-path
    Scenario: Finding something I passed over
      Given the recording from "2026-08-16 09:00 AM" has a skipped "lesson" Segment
      When I filter the list by "Skipped segments"
      Then I see that recording
      And I can open it and approve the skipped Segment
      # Q63 — "so the user could always return later to extract a piece he
      # passed over previously". This is that.

    @edge-case
    Scenario: There are no recordings yet
      Given no Recordings exist
      When I visit the recordings list
      Then I see a message explaining that recordings appear here once the recorder uploads them

    @edge-case
    Scenario: There are hundreds of recordings
      Given 500 Recordings exist
      When I visit the recordings list
      Then the list is paginated
      And the page loads in under 2 seconds
