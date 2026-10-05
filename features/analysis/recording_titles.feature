@analysis
Feature: Naming what a recording is
  In order to know what a recording is without working it out from its date
  As a reviewer
  I want every recording named, with its kind beside the date and time

  The owner, 2026-10-05, asked for titles such as "Pre-Service Rehearsal",
  "Theological Equipping Class - Giving" and "Sunday Service - Hebrews 13:1-6",
  with the date kept on every row and never repeated in the title: "Sunday
  Service - Hebrews 13:1-6 would be more indicative when the date is already
  there." On names: "CT is Culture and Theology. I think for the title,
  spelling it out looks nicer, for more concise parts of the view, using the
  acronym is preferred." TEC is the Theological Equipping Class. A class's
  topic feeds the suggested label the way scripture does for a sermon, and
  "for the scripture we sub `:` for `.` since some of the platforms we use
  reject `:` in filenames."

  The model is shown text and nothing else: the Blocks with their summaries,
  the teaching Segments with any passage already suggested, the weekday and the
  local start time. Never the audio, and never the date. The day and the time
  are evidence for the model to weigh, not a schedule the system applies.

  Background:
    Given a Recording started on a Sunday at 09:00 holding a class and then a sermon on "Hebrews 12.25-29"

  Rule: Analysis names the recording and says what kind it is

    @happy-path @stated
    Scenario: The kind and the title come from the model's reading of the text
      Given the model will name it kind "class", title "TEC - Giving", series "TEC" and topic "Giving"
      When the Recording is analysed
      Then the Recording kind is "class"
      And the Recording is titled "Theological Equipping Class - Giving"
      And the model was shown "Sunday at 09:00" and the passage "Hebrews 12:25-29"
      And the model was shown no audio and no date

    @happy-path @stated
    Scenario Outline: A title never repeats the date
      Given the model will name it kind "service" and title "<said>"
      When the Recording is analysed
      Then the Recording is titled "<title>"

      Examples:
        | said                                       | title                            |
        | Sunday Service - September 13, 2026        | Sunday Service                   |
        | 2026-09-13 Sunday Service - Hebrews 13:1-6 | Sunday Service - Hebrews 13:1-6  |

    @edge-case
    Scenario: A kind outside the vocabulary is unknown
      Given the model will name it kind "worship night" and title "Prayer Night"
      When the Recording is analysed
      Then the Recording kind is "unknown"
      And the Recording is titled "Prayer Night"

    @edge-case
    Scenario: Naming fails and analysis carries on
      # The title is a convenience, like a block summary; losing it must not
      # cost the reviewer the Segments.
      Given the model cannot be reached when the recording is named
      When the Recording is analysed
      Then the Recording is awaiting review with its Segments proposed
      And the Recording has no title
      And the failure to name it is in the processing log

  Rule: A name is spelled out in a title and abbreviated where space is short

    @happy-path @stated
    Scenario Outline: The glossary gives both forms
      # The glossary is a short list of acronyms and the names they stand for,
      # kept with the Processor's configuration and added to by hand.
      Given the model will name it kind "class", title "<said>", series "<series>" and topic "<topic>"
      When the Recording is analysed
      Then its row on the recordings list shows the title "<title>" beside the date and time
      And its row is tagged "<tag>"

      Examples:
        | said         | series               | topic  | title                                | tag |
        | TEC - Giving | TEC                  | Giving | Theological Equipping Class - Giving | TEC |
        | CT - Islam   | Culture and Theology | Islam  | Culture and Theology - Islam         | CT  |

  Rule: A class is labelled from its name and topic, as a sermon is from its passage

    @happy-path @stated
    Scenario Outline: The suggested label for a class
      # The owner's own files: "TEC - Forgiveness", "TEC - Conflict", "TEC -
      # Speech", "TEC - Giving", and "TEC" alone twice. "CT-Islam" is the one
      # written without spaces; the dominant form is followed.
      Given the model will name it kind "class", title "<said>", series "<series>" and topic "<topic>"
      When the Recording is analysed
      Then the class's suggested label is "<label>"
      And the sermon's suggested label is still "Hebrews 12.25-29"

      Examples:
        | said                | series                      | topic         | label               |
        | TEC - Giving        | Theological Equipping Class | Giving        | TEC - Giving        |
        | CT - Islam          | CT                          | Islam         | CT - Islam          |
        | TEC                 | TEC                         |               | TEC                 |
        | TEC - Romans 8:1-11 | TEC                         | Romans 8:1-11 | TEC - Romans 8.1-11 |

    @happy-path @stated
    Scenario: A passage is written with a colon in the title and a dot in the label
      Given the model will name it kind "service" and title "Sunday Service - Hebrews 12.25-29"
      When the Recording is analysed
      Then the Recording is titled "Sunday Service - Hebrews 12:25-29"
      And the sermon's suggested label is still "Hebrews 12.25-29"

    @edge-case @stated
    Scenario: A label already given is kept
      Given the class was approved with the label "TEC - Generosity"
      And the model will name it kind "class", title "TEC - Giving", series "TEC" and topic "Giving"
      When the Recording is analysed
      Then the class's suggested label is "TEC - Generosity"

  Rule: A title the reviewer writes is theirs

    @happy-path @stated
    Scenario: Renaming a recording
      Given analysis named the Recording "Sunday Service - Hebrews 12:25-29" as a "service"
      When I rename it "Baptism Sunday - Hebrews 12:25-29" on its detail page
      Then the detail page heading shows "Baptism Sunday - Hebrews 12:25-29" and the date and time
      And the rename is in the processing log as the reviewer's

    @edge-case @stated
    Scenario: Analysing again keeps the reviewer's title
      Given I renamed the Recording "Baptism Sunday"
      And the model will name it kind "service" and title "Sunday Service"
      When the Recording is analysed
      Then the Recording is titled "Baptism Sunday"
      And the Recording kind is "service"

    @edge-case
    Scenario: A title cannot be emptied
      Given I renamed the Recording "Baptism Sunday"
      When I rename it "" on its detail page
      Then I am told a title cannot be empty
      And the Recording is titled "Baptism Sunday"

  Rule: The list and the detail view lead with the title

    @happy-path @stated
    Scenario: A named recording on the list
      Given analysis named the Recording "Theological Equipping Class - Giving" as a "class" in the series "Theological Equipping Class"
      When I visit the recordings list
      Then its row on the recordings list shows the title "Theological Equipping Class - Giving" beside the date and time
      And its row is tagged "TEC"

    @edge-case
    Scenario: A recording nobody has named
      When I visit the recordings list
      Then its row shows the date and time and no title
      And its detail page heading is the date and time alone

    @happy-path
    Scenario: Narrowing the list to one kind
      Given analysis named the Recording "Theological Equipping Class - Giving" as a "class" in the series "Theological Equipping Class"
      And another Recording that analysis named "Pre-Service Rehearsal" as a "rehearsal"
      When I filter the list by the kind "rehearsal"
      Then the list shows "Pre-Service Rehearsal" and not "Theological Equipping Class - Giving"

  Rule: Recordings analysed before naming existed can be named afterwards

    @happy-path
    Scenario: Previewing the names without writing them
      # Reads the Blocks, summaries and Segments already stored. No audio, no
      # transcript and no re-analysis.
      Given the Recording was analysed before recordings were named and its audio is not on this machine
      And the model will name it kind "class", title "TEC - Giving", series "TEC" and topic "Giving"
      When the naming backfill runs as a dry run
      Then it prints the title "Theological Equipping Class - Giving" and the kind "class" for the Recording
      And it prints the suggested label "TEC - Giving" for the class
      And the Recording has no title
      And the class has no label

    @happy-path
    Scenario: Naming them
      Given the Recording was analysed before recordings were named and its audio is not on this machine
      And the model will name it kind "class", title "TEC - Giving", series "TEC" and topic "Giving"
      When the naming backfill runs
      Then the Recording is titled "Theological Equipping Class - Giving"
      And the Recording kind is "class"
      And the class's suggested label is "TEC - Giving"

    @edge-case
    Scenario: The backfill keeps the reviewer's title
      Given the Recording was analysed before recordings were named and its audio is not on this machine
      And I renamed the Recording "Baptism Sunday"
      And the model will name it kind "class", title "TEC - Giving", series "TEC" and topic "Giving"
      When the naming backfill runs
      Then the Recording is titled "Baptism Sunday"
      And it reports that the reviewer's title was kept
