@analysis
Feature: Proposal confidence and evidence
  In order to know which segments need careful review
  As a reviewer
  I want every proposal to explain itself and score itself

  Confidence is per Segment, and has two parts: how sure we are about *what
  this is* (classification) and how sure we are about *where it starts and
  ends* (boundaries). A Segment can be confidently a sermon with badly guessed
  boundaries, or vice versa, and the reviewer needs to know which.

  **Confidence is computed, never reported.** This is the whole of it, and the
  rest of this file follows from it. A language model asked how confident it is
  answers 0.95 — on a correct boundary and on one wrong by 659 seconds, in the
  same run. It is a constant. So confidence here is *derived* from things that
  can be checked independently of the model that produced the answer, and the
  three levels are `high`, `medium` and `low` rather than a number, because a
  number implies a precision none of these inputs have.

  The inputs, and what each one can tell you:

  | Input | Available always? | Bears on |
  | --- | --- | --- |
  | cut difficulty — quiet around the boundary | yes, computed from the envelope | boundaries |
  | leading silence after the punch-in | yes | boundaries |
  | expected cue found (reading before, amen/communion after) | yes | both |
  | position in the expected running order | yes | classification |
  | Segment length against the usual 30–75 minute band | yes | classification |
  | wall-clock start against the usual 10:50–10:57 band | yes, for a Sunday service | classification |
  | a known speaker matched | only if voice profiles exist | classification |
  | **agreement with a second, independent analysis** | **only if one is run — see the last Rule** | both |

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

    @happy-path @measured
    Scenario: A model's own confidence number is not used for anything
      # Measured: models report 0.95 on essentially every segment, including one
      # whose punch-in was wrong by 659 seconds and a correct one in the same
      # run. It is a constant and carries no information.
      Then no reviewer-facing behaviour depends on a confidence value the model
        reported about itself
      And a self-reported confidence may be stored for diagnosis
      And it is never shown to a reviewer as a quality signal

    @happy-path @measured
    Scenario Outline: Agreement between two independent analyses is the signal
      # Measured: across the corpus the failures are the cases where two
      # analyses disagreed with each other or with the human. Agreement needs no
      # calibration — only a second run.
      #
      # Honest about the evidence: the *ladder's* control was genuinely
      # independent (a separate model in a separate context) and that is what
      # this rests on. The three blind runs reported "both models agreed" where
      # the second reading was the orchestrating agent, not an independent
      # system — see the correction at the end of experiments/FINDINGS.md. The
      # signal is real; two of the four data points for it are weaker than they
      # were written up as.
      Given a second, independent analysis of the same Recording
      And the two proposed punch-ins differ by <gap>
      Then the Segment is shown as "<badge>"

      Examples:
        | gap    | badge           |
        | 0.2 s  | Looks good      |
        | 3 s    | Worth a listen  |
        | 45 s   | Needs attention |
        | no second segment proposed | Needs attention |

    @happy-path @measured
    Scenario: Cut difficulty is the second half of the signal
      # Already computed on every boundary from the silence around it, and worth
      # surfacing: a cut with no quiet to land in is one a human should see even
      # when the models agree.
      Given the punch-in is graded "hard"
      Then the Segment is shown as needing attention regardless of agreement
      And the reason is stated, for example "no clean cut point at the punch-in"

    @happy-path
    Scenario: What a reviewer is told, in order of usefulness
      Then the Segment carries, most useful first:
        | signal                                              |
        | whether a second analysis agrees, and by how much   |
        | whether either boundary is a hard cut               |
        | the evidence behind the classification              |
        | how the segment length compares to the usual range  |

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

  Rule: A second opinion is what makes agreement available

    @happy-path @needs-decision
    Scenario: Whether to run a second analysis at all
      # **Open decision.** Agreement is the strongest confidence signal measured,
      # and it is the only one that needs something the pipeline does not
      # currently do: a second pass with a different model.
      #
      # The cost is concrete. The model host holds `qwen3.6:35b-mlx` (23.6 GB)
      # and `qwq:32b` (19.9 GB). Loading both at once is 43 GB of 64 GB on a
      # machine that is also a working dev box; loading them in turn costs about
      # 19 seconds per swap plus a second full classification pass — on the order
      # of a minute or two for a three-hour recording, once a week.
      #
      # Against that: without it, boundary confidence rests on cut difficulty and
      # cue presence alone, and the "hard cut, check this one" behaviour this
      # spec asks for gets materially weaker.
      Given a Recording has been analysed once
      When a second analysis is configured
      Then it uses a different model from the first
      And it reads the same transcript, so only the reasoning differs
      And its result is used for agreement only, never as the proposal

    @edge-case
    Scenario: No second opinion is configured
      # Must degrade, not break. This is the default until the decision above is
      # made, and it is also what happens whenever the second model is
      # unavailable.
      Given no second analysis is configured
      When scoring runs
      Then confidence is computed from the remaining inputs
      And the reviewer is not shown an agreement badge
      And the absence is stated rather than shown as agreement

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
