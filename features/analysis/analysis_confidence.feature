@analysis
Feature: Proposal confidence and evidence
  In order to know which segments need careful review
  As a reviewer
  I want every proposal to explain itself and score itself

  Confidence is per Segment, and has two parts: how sure we are about *what
  this is* (classification) and how sure we are about *where it starts and
  ends* (boundaries). A Segment can be confidently a sermon with badly guessed
  boundaries, or vice versa, and the reviewer needs to know which.

  Background:
    Given a Recording with classified Blocks and proposed Segments

  Rule: Every Segment carries a confidence and its supporting evidence

    @happy-path
    Scenario: A high-confidence proposal
      Given a Segment starting at the expected Sunday service time
      And its punch-in is supported by a speaker change after a scripture reading
      And its punch-out is supported by a closing prayer followed by a communion invitation
      And the resulting span is 48 minutes
      When scoring runs
      Then the Segment's classification confidence is "high"
      And its boundary confidence is "high"
      And the evidence list is shown on the Segment
      And each piece of evidence links to its timecode

    @happy-path
    Scenario: Confident about what it is, unsure where it ends
      Given a Segment starting at the expected Sunday service time
      And it contains no closing prayer or communion cue
      When scoring runs
      Then the classification confidence is "high"
      And the boundary confidence is "low"
      And the reviewer is prompted to check the punch-out specifically

    @happy-path
    Scenario Outline: Confidence bands drive how the reviewer is prompted
      Given the computed boundary confidence is <score>
      When scoring runs
      Then the confidence band is "<band>"
      And the Segment is shown as "<badge>"

      Examples:
        | score | band   | badge                |
        | 0.92  | high   | Looks good           |
        | 0.65  | medium | Worth a listen       |
        | 0.31  | low    | Needs attention      |
        | 0.00  | none   | Boundaries not found |

    @happy-path
    Scenario: Evidence is human readable
      When scoring runs
      Then each evidence entry states what was found, where, and what it implies, for example:
        | timecode | finding                                          | implies         |
        | 1:28:44  | segment starts at 10:28:44 AM on a Sunday        | is the service  |
        | 1:54:50  | scripture reading cue: "turn with me to Romans"  | pre-sermon      |
        | 2:00:20  | speaker change to a new voice                    | punch-in        |
        | 2:43:28  | closing prayer ends with "amen"                  | punch-out       |
        | 2:43:35  | communion invitation begins                      | post-sermon     |

  Rule: Missing evidence lowers confidence rather than blocking the Proposal

    @edge-case
    Scenario Outline: Degrading gracefully
      Given "<missing>" evidence is unavailable
      When scoring runs
      Then a Proposal is still produced for every Segment
      And the affected confidence is reduced
      And the evidence list states that "<missing>" was unavailable

      Examples:
        | missing            |
        | speaker spans      |
        | block types        |
        | scripture reading  |
        | communion cue      |
        | closing prayer     |
        | recording start time |

  Rule: The recording as a whole is summarised for the list

    @happy-path
    Scenario: A recording's headline state comes from its best segment
      Given a Recording whose Blocks include music, a lesson and a sermon
      And 2 Segments were proposed, classified "lesson" and "sermon"
      When scoring runs
      Then the Recording is summarised as containing a sermon
      And the recordings list shows the sermon Segment's confidence
      And the other Segments and all Blocks are visible on the detail view

    @happy-path
    Scenario: A recording with nothing publishable
      Given a Recording whose Blocks are all typed "music"
      And no Segment was proposed
      When scoring runs
      Then the Recording is summarised as "nothing to publish"
      And it is not shown as needing attention

  Rule: Accuracy is measured against real recordings, not self-reported

    @happy-path
    Scenario: Confidence is a reviewer aid, not a quality claim
      Then a confidence band tells the reviewer where to look first
      And it is never treated as evidence that the output is correct
      And correctness is established by the accuracy suite instead
      # Q22 — confirmed: "we should be able to construct a pretty decent
      # practical behavior test with actual files and see that the output is
      # close enough to what was done by a human." See
      # analysis/detection_accuracy.feature.
