@analysis @happy-path
Feature: Proposing publishable segments
  In order to be offered the thing I actually publish
  As a reviewer
  I want the machine to build Segments out of the Blocks it found

  A Segment is seeded on a teaching Block and extended through what belongs with
  it. One rule covers both kinds of service:

      seed on a teaching Block (sermon or lesson)
      extend forward through an immediately following prayer Block
      stop before whatever comes next

  On a Sunday, "whatever comes next" is communion. On a class Sunday it is Q&A.
  Neither is named in the rule, which is the point.

  Background:
    Given a Recording divided into classified Blocks

  Rule: Teaching blocks seed segments

    @happy-path
    Scenario: A normal Sunday
      Given the Blocks are:
        | start   | end     | type              |
        | 0:00:00 | 0:04:00 | announcements     |
        | 0:04:00 | 0:04:30 | prayer            |
        | 0:04:30 | 0:24:00 | music             |
        | 0:24:00 | 0:26:10 | prayer            |
        | 0:26:10 | 0:31:40 | scripture_reading |
        | 0:31:40 | 1:12:40 | sermon            |
        | 1:12:40 | 1:14:52 | prayer            |
        | 1:14:52 | 1:20:00 | communion         |
        | 1:20:00 | 1:26:00 | music             |
        | 1:26:00 | 1:30:12 | prayer            |
      When segment proposal runs
      Then 1 Segment is proposed
      And it spans "0:31:40" to "1:14:52"
      And it is classified "sermon"
      And the evidence records "seeded on the sermon block"
      And the evidence records "extended through the closing prayer"
      And the evidence records "stopped before communion"

    @happy-path @measured
    Scenario: A class Sunday
      # Confirmed: the class ends with a prayer, then goes into Q&A which is
      # never published.
      Given the Blocks are:
        | start   | end     | type    |
        | 0:04:10 | 1:01:20 | lesson  |
        | 1:01:20 | 1:03:55 | prayer  |
        | 1:03:55 | 1:22:00 | qa      |
      When segment proposal runs
      Then 1 Segment is proposed
      And it spans "0:04:10" to "1:03:55"
      And it is classified "lesson"
      And the Q&A is excluded

    @happy-path
    Scenario: A file containing both a class and a service
      Given the Recording contains a lesson Block and a sermon Block
      When segment proposal runs
      Then 2 Segments are proposed
      And each is independently classified, dispositionable and renderable
      And approving one does not affect the other

    @happy-path
    Scenario: No teaching block means no segment
      Given the Recording contains only announcements and music Blocks
      When segment proposal runs
      Then 0 Segments are proposed
      And the Recording is summarised as "nothing to publish"
      And no notification is sent

  Rule: Extension only takes what belongs

    @happy-path @measured
    Scenario: The closing prayer is included
      # Confirmed: "the closing prayer at the end of the sermon is part of the
      # sermon. Right after that is the pitch to communion."
      Given a sermon Block is immediately followed by a prayer Block
      When segment proposal runs
      Then the prayer is included in the Segment

    @happy-path
    Scenario: A prayer that does not immediately follow is not included
      Given a sermon Block is followed by a music Block and then a prayer Block
      When segment proposal runs
      Then the Segment ends at the end of the sermon Block
      And the later prayer is not included

    @happy-path
    Scenario Outline: What stops the extension
      Given a sermon Block followed by a prayer Block followed by a "<next>" Block
      When segment proposal runs
      Then the Segment ends at the end of the prayer Block

      Examples:
        | next          |
        | communion     |
        | music         |
        | announcements |
        | qa            |
        | other         |

    @happy-path
    Scenario: An opening prayer is not swallowed
      Given a prayer Block immediately precedes the sermon Block
      When segment proposal runs
      Then the Segment starts at the sermon Block, not at the prayer
      # Extension runs forward only. The prayer before the sermon belongs to the
      # service, not to the message.

  Rule: Segments never overlap and always sit inside the recording

    @edge-case
    Scenario: Two teaching blocks adjacent to each other
      Given two teaching Blocks are adjacent with no intervening Block
      When segment proposal runs
      Then they are proposed as one Segment
      And the reviewer can split it if they were genuinely two messages

    @edge-case
    Scenario: A proposed segment would overlap its neighbour
      When segment proposal produces spans that would overlap
      Then the overlap is resolved before the Proposal is offered
      And no two Segments share any audio

  Rule: The reviewer has the last word

    @happy-path
    Scenario: Creating a segment by hand
      Given 0 Segments were proposed
      When the reviewer draws a Segment from "0:20:00" to "1:05:00"
      Then a Segment exists with those boundaries
      And it can be classified and approved like any other

    @happy-path
    Scenario: Splitting a proposed segment
      When the reviewer splits a Segment at "1:15:00"
      Then 2 Segments exist
      And each can be classified, adjusted and dispositioned independently

    @happy-path
    Scenario: Merging two proposed segments
      When the reviewer merges two adjacent Segments
      Then 1 Segment exists spanning from the first punch-in to the last punch-out

    @happy-path @measured
    Scenario Outline: Segment length is sanity-checked
      # Published lengths measured across 24 recordings: 40-68 minutes.
      # Confirmed warning band: 30-75 minutes. A warning, never a rejection.
      Given a proposed Segment is <length> long
      When segment proposal runs
      Then the Segment is <outcome>

      Examples:
        | length  | outcome                                            |
        | 0:04:00 | flagged "length outside expected range"             |
        | 0:22:00 | flagged "length outside expected range"             |
        | 0:48:00 | not flagged                                        |
        | 1:02:00 | not flagged                                        |
        | 1:40:00 | flagged "length outside expected range"             |
