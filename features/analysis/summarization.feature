@analysis
Feature: Summarising blocks and segments
  In order to decide without listening to three hours of audio
  As a reviewer
  I want a one-line description of each block and a few seconds I can play

  This exists to make the human faster, not to replace them. The target is that
  a reviewer can look at a recording they have never heard, understand its shape
  in a few seconds, and confirm the right Segment without scrubbing.

  Background:
    Given a Recording divided into classified Blocks

  Rule: Every spoken block gets a one-line summary

    @happy-path
    Scenario: Summarising a service
      When the summarization stage runs
      Then each spoken Block carries a one-line summary, for example:
        | type              | summary                                                      |
        | announcements     | Welcome, a baptism next Sunday, and the church workday       |
        | scripture_reading | Reading of Hebrews 12:4-11                                   |
        | prayer            | Opening prayer, with a pause for silent prayer               |
        | sermon            | On enduring hardship as discipline, from Hebrews 12          |
        | communion         | Invitation to the table, addressed to visitors               |
      And each summary is short enough to read at a glance

    @happy-path
    Scenario: The proposed segment carries a summary too
      When the summarization stage runs
      Then each proposed Segment carries its own summary
      And the summary is shown beside it in the review interface
      And it is shown in the notification

    @happy-path
    Scenario: Music blocks are not summarised
      Given a Block typed "music" with no speech
      When the summarization stage runs
      Then no summary is attempted for it
      And it is labelled by its type alone

    @happy-path @assumption
    Scenario: A suggested label comes out of the summary
      # The label ends up in the filename, and for sermons it is a scripture
      # reference in 20 of 24 sample files.
      Given a Segment classified "sermon" whose transcript references Hebrews 12
      When the summarization stage runs
      Then "Hebrews 12" is suggested as the publication label
      And the reviewer can correct it

  Rule: The model returns words, never a timestamp

    @happy-path @measured
    Scenario: A cue is a verbatim quote, located afterwards
      # This is what makes a very small model sufficient. Asking a 2.5 GB model
      # for a timestamp does not work; asking it to copy a sentence does, and the
      # words already carry times. Measured: 11 of 11 quotes located, 0.8 s per
      # block, the whole recording in 9 seconds.
      When the summarization stage runs
      Then the model returns the exact words of the recognisable moment
      And those words are located in the word-level transcript
      And the excerpt's timing comes from the transcript, never from the model

    @edge-case
    Scenario: The quote cannot be located
      Given the returned words do not appear in the transcript
      Then no cue excerpt is stored for that Block
      And the Block falls back to its first few seconds
      And the failure is counted, so a model that drifts is visible

  Rule: Every block gets a cue excerpt worth playing

    @happy-path
    Scenario: Choosing the most identifiable few seconds
      When the summarization stage runs
      Then each spoken Block carries a cue excerpt with a start and end time
      And the excerpt is between 3 and 10 seconds long
      And it is chosen to be immediately recognisable rather than simply the first words

    @happy-path
    Scenario: Previewing a block
      Given a Block has a cue excerpt
      When the reviewer presses Preview on that Block
      Then playback starts at the excerpt
      And stops at the end of the excerpt
      And the reviewer can tell what the Block is without further scrubbing

    @happy-path
    Scenario Outline: What makes a good cue excerpt
      Given a Block typed "<type>"
      When the summarization stage runs
      Then the cue excerpt is chosen from "<preferred>"

      Examples:
        | type              | preferred                                        |
        | scripture_reading | the passage announcement                         |
        | sermon            | the opening sentences, or the stated main point  |
        | lesson            | the opening sentences                            |
        | communion         | the invitation itself                            |
        | announcements     | the most content-bearing notice                  |
        | qa                | the first question asked                         |

    @happy-path
    Scenario: The excerpt avoids dead air
      When the summarization stage runs
      Then no cue excerpt begins or ends inside a silence
      And no cue excerpt is chosen from a span with no speech

  Rule: Nothing leaves the local network

    @happy-path @measured
    Scenario: Summarization runs locally
      # Q76 — confirmed: "I do want this to stay local if possible... from the
      # standpoint of not wanting to pay for API usage... I do want to run it
      # locally." The congregation's audio is also not ours to send anywhere.
      When the summarization stage runs
      Then no audio leaves the local network
      And no transcript leaves the local network
      And no third-party API is called

    @happy-path
    Scenario: The model may live on a different machine
      # The server this runs on has little GPU capability, so the model may sit
      # on a separate box reachable over the tailnet.
      Given the summarization model is hosted on another machine on the tailnet
      When the summarization stage runs
      Then it calls that machine rather than a hosted service
      And the machine it used is recorded with the summary

    @happy-path
    Scenario: A weaker model is an acceptable trade
      Given only a small local model is available
      When the summarization stage runs
      Then summaries are produced at whatever quality that model gives
      And the system does not fall back to a hosted service to improve them

    @happy-path
    Scenario: Heuristics are an acceptable substitute
      Given no language model is available at all
      When the summarization stage runs
      Then summaries fall back to heuristics drawn from the transcript
      And the reviewer is told the summaries are heuristic
      # Q76 — a spike will decide what is actually worth running. The spec is
      # written so that answer can be "a small model", "a big model on another
      # box", or "no model at all" without changing anything downstream.

  Rule: Summarization is optional and never blocks review

    @edge-case
    Scenario: The summarizer is unavailable
      Given the summarization stage fails on every attempt
      When Analysis runs
      Then Analysis completes without summaries
      And the Recording still reaches "awaiting_review"
      And Blocks are labelled by type alone
      And cue excerpts fall back to the first few seconds of each Block
      And the reviewer is told summaries were unavailable

    @edge-case
    Scenario: A summary is obviously wrong
      Given a Block summary does not match its audio
      When the reviewer corrects or clears the summary
      Then the correction is stored
      And the machine summary is retained alongside it for comparison

    @happy-path
    Scenario: Summaries are never authoritative
      Then no boundary, classification or disposition depends on a summary
      And a wrong summary can mislead a reviewer but cannot produce a wrong file
      # Summaries are a reading aid. Everything that affects output is derived
      # from the transcript, the speaker spans and the block types.
