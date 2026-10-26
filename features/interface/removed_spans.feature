@interface
Feature: Removing spans from inside a segment
  In order to publish a message without a podium bump, a long silent prayer or a
  seminar's break in it
  As a reviewer
  I want to mark stretches inside a Segment that the published audio leaves out

  A Segment is one continuous stretch from punch-in to punch-out. Sometimes
  something inside it should not ship. The case that prompted this was a sermon
  that opens "Good morning", then a loud bump on the podium, then the message.
  Asked for directly: "Yes, build it — marking spans by hand is enough. This will
  be useful for other things too. Seminars often have large breaks, or there could
  be times when there are long prayer segments with silence that we would want to
  cut out. Having the ability to trim small pieces out of a message is nice. We
  don't need any kind of automation with the detection pipeline right now... just
  being able to do that manually would be good enough."

  So a removed span is only ever marked by a reviewer. Analysis never proposes,
  moves or removes one.

  A removed span runs from a fraction of a second to many minutes, so it is
  marked the two ways a boundary is: from the playhead, when the ear found it, or
  by typing timecodes, when the reviewer already knows the numbers. And, while
  editing, by the way the eye finds it: "Could we make it so you drag over an
  area on the waveform to create a selection, and then click a Remove button? It
  creates a removal that can be removed or reverted if you want." -- the owner,
  2026-10-26. A selection is not yet a removal; Remove makes it one, and putting
  a span back is restoring it.

  Background:
    Given I am on the tailnet
    And a Recording in state "awaiting_review"
    And I have selected a Segment classified "sermon" spanning "1:28:40" to "3:12:00"
    And its punch-in is "2:00:20.000" and punch-out is "2:43:32.000"

  Rule: A removed span is marked by hand

    @happy-path @stated
    Scenario: Removing a bump by typing its timecodes
      When I remove the span from "2:00:21.400" to "2:00:22.100"
      Then the span from "2:00:21.400" to "2:00:22.100" is listed as removed, lasting "0.70 s"
      And the removed span is drawn on the waveform where it falls
      And the segment length reads "0:43:11.30"

    @happy-path
    Scenario: Removing a span from the playhead
      When I play to "2:00:21.400"
      And I mark the start of a removal at the playhead
      And I play to "2:00:22.100"
      And I mark the end of the removal at the playhead
      Then the span from "2:00:21.400" to "2:00:22.100" is listed as removed, lasting "0.70 s"

    @happy-path @stated
    Scenario: Removing a seminar's break
      When I remove the span from "2:10:00.000" to "2:25:30.000"
      Then the span from "2:10:00.000" to "2:25:30.000" is listed as removed, lasting "0:15:30.00"
      And the segment length reads "0:27:42.00"

    @happy-path
    Scenario: Several spans can be removed from one Segment
      When I remove the span from "2:00:21.400" to "2:00:22.100"
      And I remove the span from "2:10:00.000" to "2:25:30.000"
      Then 2 spans are listed as removed, in the order they fall
      And the segment length reads "0:27:41.30"

    @happy-path @stated
    Scenario: Removing a span selected on the waveform
      Given I am editing the cut
      When I drag across the detail view from "2:00:21.400" to "2:00:22.100"
      Then the selection reads "0.70 s" and offers to remove it
      And no span is listed as removed
      And neither boundary has moved
      When I remove the selection
      Then the span from "2:00:21.400" to "2:00:22.100" is listed as removed, lasting "0.70 s"

  Rule: A removed span can be put back

    @happy-path
    Scenario: Restoring a removed span
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      When I restore that span
      Then no span is listed as removed
      And the segment length reads "0:43:12.00"

  Rule: A removed span lies strictly inside the cut and overlaps no other

    @edge-case
    Scenario Outline: A span that cannot be removed
      When I try to remove the span from "<from>" to "<to>"
      Then the change is rejected
      And I am told "<reason>"
      And no span is listed as removed

      Examples:
        | from        | to          | reason                                                   |
        | 2:00:10.000 | 2:00:25.000 | a removed span must lie inside the punch-in and punch-out |
        | 2:43:30.000 | 2:43:40.000 | a removed span must lie inside the punch-in and punch-out |
        | 2:00:20.000 | 2:00:25.000 | a removed span must lie inside the punch-in and punch-out |
        | 2:00:25.000 | 2:00:25.000 | a removed span must have a length                         |
        | 2:00:26.000 | 2:00:25.000 | a removed span must have a length                         |
      # A span starting exactly at the punch-in is a later punch-in, and one
      # ending exactly at the punch-out an earlier punch-out. Moving the boundary
      # says that plainly; a removed span touching it would say it twice.

    @edge-case @policy
    Scenario: Overlapping spans are refused rather than merged
      # Merging would silently change a span the reviewer has already heard the
      # join of. Refusing costs one restore and keeps every span exactly as
      # marked. Spans that merely touch are refused too: nothing would be kept
      # between them.
      Given I have removed the span from "2:10:00.000" to "2:12:00.000"
      When I try to remove the span from "2:11:00.000" to "2:13:00.000"
      Then the change is rejected
      And I am told "it overlaps a span already removed"
      And only the span from "2:10:00.000" to "2:12:00.000" is listed as removed

  Rule: Moving a boundary never strands a removed span

    @edge-case @policy
    Scenario Outline: A boundary cannot be moved onto or past a removed span
      # Nothing here is destructive: dropping or trimming the span to fit would
      # discard the reviewer's work without asking. They restore it first, which
      # is one click and says what they meant.
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      When I try to set the "<boundary>" to "<value>"
      Then the change is rejected
      And I am told "restore the removed span before moving a boundary onto or past it"
      And the span from "2:00:21.400" to "2:00:22.100" is still listed as removed

      Examples:
        | boundary  | value       |
        | punch-in  | 2:00:21.800 |
        | punch-in  | 2:00:30.000 |
        | punch-out | 2:00:21.800 |

    @happy-path
    Scenario: A boundary moves freely when it leaves the removed span inside
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      When I try to set the "punch-in" to "2:00:19.000"
      Then the change is accepted
      And the span from "2:00:21.400" to "2:00:22.100" is still listed as removed

  Rule: Analysis never touches a removed span

    @happy-path
    Scenario: Proposing Segments again keeps the removed spans and the cut around them
      # A Segment holding a removed span is the reviewer's work, as one whose
      # boundaries they moved is: the machine offers a new proposal beside it
      # rather than over it.
      Given the Recording's transcript covers each of its Blocks
      And I have removed the span from "2:00:21.400" to "2:00:22.100"
      When the machine proposes Segments for the Recording again
      Then the span from "2:00:21.400" to "2:00:22.100" is still listed as removed
      And the punch-in and punch-out are still "2:00:20.000" and "2:43:32.000"

  Rule: Removed spans are part of what is approved

    @happy-path
    Scenario: An approved Segment's removed spans are locked
      # The same rule as the boundaries: approval hands the cut to processing,
      # and a span changed after that would render something nobody approved.
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      And I approve the Segment
      When I try to restore that span
      Then the change is rejected
      And I am told "the removed spans cannot be changed once the Segment is approved"
      And the span from "2:00:21.400" to "2:00:22.100" is still listed as removed

    @happy-path
    Scenario: Cancelling processing lets the removed spans change again
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      And I approve the Segment
      And I cancel processing
      When I restore that span
      Then no span is listed as removed

  Rule: Every change to a removed span is on the record

    @happy-path
    Scenario: Removing and restoring are logged
      When I remove the span from "2:00:21.400" to "2:00:22.100"
      And I restore that span
      Then the processing log records the removal and then the restoration, each with who did it and when
      And each entry carries the removed spans in force once it was made

    @happy-path
    Scenario: The approval records the removed spans it approved
      # "Any past render could be reproduced from that record and the source"
      # (processing/reprocessing.feature) needs the spans beside the boundaries.
      Given I have removed the span from "2:00:21.400" to "2:00:22.100"
      When I approve the Segment
      Then the approval in the processing log carries the span from "2:00:21.400" to "2:00:22.100"

  Rule: I can hear the cut as it stands before I approve it

    # "In editing mode, it would still be good to be able to preview the cuts
    # before marking editing as done" -- the owner, 2026-10-26. The preview is of
    # the cut as it stands, so it follows every edit the moment it is made.

    @happy-path @stated
    Scenario: Previewing the cut plays each join in turn
      Given the seekable preview has been rendered
      And I have removed the span from "2:10:00.000" to "2:25:30.000"
      When I choose to preview the cut
      Then the preview of the cut plays, in order:
        | seam    | the 5 seconds before | joined to the 5 seconds after |
        | opening | 2:00:20.000          | 2:00:20.000                   |
        | join    | 2:10:00.000          | 2:25:30.000                   |
        | ending  | 2:43:32.000          | 2:43:32.000                   |

    @happy-path @stated
    Scenario: Previewing the cut follows a boundary I have just moved
      Given the seekable preview has been rendered
      And I have adjusted the punch-in to "2:00:16.500"
      When I choose to preview the cut
      Then the preview of the cut plays, in order:
        | seam    | the 5 seconds before | joined to the 5 seconds after |
        | opening | 2:00:16.500          | 2:00:16.500                   |
        | ending  | 2:43:32.000          | 2:43:32.000                   |

    @happy-path @stated
    Scenario: Each seam can be heard on its own
      Given the seekable preview has been rendered
      And I have removed the span from "2:10:00.000" to "2:25:30.000"
      When I open a proposed Segment
      Then each seam of the cut can be heard on its own, in order:
        | seam    | the 5 seconds before | joined to the 5 seconds after |
        | opening | 2:00:20.000          | 2:00:20.000                   |
        | join    | 2:10:00.000          | 2:25:30.000                   |
        | ending  | 2:43:32.000          | 2:43:32.000                   |

    @happy-path @slow
    Scenario: Hearing a join as it will sound
      # The join is made the way the render makes it, from the source, so what is
      # heard is what will ship — fades and all — rather than the player jumping
      # over the span, which lags by a fraction of a second and would play part
      # of a bump that will not be there.
      Given the source carries a loud moment from "2:13:20.500" lasting 0.3 seconds
      And I have removed the span from "2:13:20.400" to "2:13:21.000"
      When I choose to hear the join across that span
      Then I hear the 5 seconds before the span joined to the 5 seconds after it
      And the loud moment is not in what I hear
