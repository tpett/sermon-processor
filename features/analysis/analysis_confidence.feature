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
  | ~~agreement with a second, independent analysis~~ | **not in v1** — see the last Rule | both |

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
      Given a Recording divided into a lesson Block and a qa Block
      When block classification runs once with the model reporting 0.95 and once reporting 0.10
      Then no reviewer-facing behaviour depends on a model's self-reported confidence
      And a self-reported confidence may be stored for diagnosis
      And it is never shown to a reviewer as a quality signal

    @deferred @measured
    Scenario Outline: Agreement between two independent analyses is the signal
      # **Not in v1** (2026-09-18): "we can always refine the process later. I
      # think what we have is good enough for v1."
      #
      # Kept in full because the evidence for it is the strongest in the project
      # and a later reader should not have to rediscover it. See also the
      # 2026-09-17 engine trace: of eight recordings, the one whose final cut
      # differed materially was a 19.6 s disagreement between two runs on nearly
      # identical transcripts -- precisely what this badge would have caught, and
      # precisely what v1 will not catch.
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
      # Already computed on every boundary from the silence around it, and in v1
      # it is the *primary* signal rather than the second half of one -- with no
      # agreement badge, a cut with no quiet to land in is the main thing that
      # asks a reviewer to listen.
      Given the punch-in is graded "hard"
      Then the Segment is shown as needing attention
      And the reason is stated, for example "no clean cut point at the punch-in"

    @happy-path
    Scenario: What a reviewer is told, in order of usefulness
      Then the Segment carries, most useful first:
        | signal                                              |
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

  Rule: v1 runs one analysis, and says so

    @happy-path
    Scenario: One analysis is the v1 behaviour, not a degraded mode
      # Settled 2026-09-18. What was written as a fallback is now the whole of
      # it, so it has to read as a complete design rather than as something
      # missing.
      Given a Recording has been analysed
      Then exactly one analysis informs the Proposal
      And confidence is computed from these inputs only:
        | input                            |
        | cut difficulty                   |
        | leading silence                  |
        | cue presence                     |
        | position in the running order     |
        | the length band                  |
        | the start-time band              |
      And no agreement badge is shown
      And nothing implies a second opinion was sought and agreed

    @happy-path
    Scenario: What the reviewer loses, stated where they can see it
      # The honest consequence. Without agreement a confidently wrong boundary
      # looks exactly like a confidently right one -- the 19.6 s case had nothing
      # distinguishing it from the six that were correct.
      Then the Segment does not claim more certainty than one analysis supports
      And cut difficulty remains the signal that asks for a listen

    @deferred
    Scenario: Adding a second opinion later changes scoring, not the pipeline
      # Why this is safe to leave out of v1: the second analysis reads the same
      # frozen transcript and only the reasoning differs, so it is an added stage
      # rather than a change to any existing one. Nothing in v1 needs to be built
      # differently to accommodate it.
      #
      # The cost, recorded so it does not need re-deriving: the model host holds
      # `qwen3.6:35b-mlx` (23.6 GB) and `qwq:32b` (19.9 GB). Both resident is
      # 43 GB of 64 GB on a machine that is also a working dev box; in turn it is
      # about 19 seconds per swap plus a second classification pass — a minute or
      # two for a three-hour recording, once a week.
      Given a second analysis is added after v1
      Then it uses a different model from the first
      And it reads the same transcript, so only the reasoning differs
      And its result is used for agreement only, never as the proposal
      And no existing stage changes

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
