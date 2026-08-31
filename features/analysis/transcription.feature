@analysis @slow
Feature: Transcription
  In order to find the sermon by what is said
  As the Sermon Processor
  I want a timestamped transcript of the whole service

  Boundary detection leans on spoken cues — a scripture reading, "let us pray",
  "amen", the communion invitation. None of that works without word-level
  timestamps.

  Background:
    Given a Recording in state "downloaded"
    And the Recording is 1:30:12 long

  Rule: Transcription produces timestamped text for the whole recording

    @happy-path
    Scenario: Transcribing a full service
      When the transcription stage runs
      Then a transcript is produced covering the full duration
      And every utterance has a start time and an end time
      And every word has a start time
      And each utterance carries a recognition confidence
      And the transcript is stored as an artifact of the Recording

    @happy-path
    Scenario: The transcript is available to the reviewer
      Given transcription has completed
      When a reviewer opens the Recording detail view
      Then they can read the transcript
      And clicking an utterance seeks the player to that timecode
      And the utterance under the playhead is highlighted during playback

    @edge-case
    Scenario: Music is transcribed as noise
      Given the first 22 minutes of the service is congregational singing
      When the transcription stage runs
      Then the singing produces low-confidence or empty utterances
      And those regions are marked as "likely music" rather than treated as speech
      # Q10 — is a music/speech classifier worth it, or is low ASR confidence enough?

    @edge-case
    Scenario: Long silences produce no utterances
      Given there is 90 seconds of near-silence between segments
      When the transcription stage runs
      Then no utterances are produced for that span
      And the span is recorded as a silence gap with its start and end times

    @edge-case
    Scenario Outline: Audio conditions that degrade recognition
      Given the recording has <condition>
      When the transcription stage runs
      Then the transcript is still produced
      And the average confidence for the affected region is recorded
      And the Recording is flagged "<flag>" when the transcript is measurably poor
      # The threshold is deliberately unstated. An earlier draft asserted 0.5 and
      # nothing in the corpus ever produced it, so there is no evidence for any
      # particular value. Set it when a recording appears that needs it.

      Examples:
        | condition                        | flag                     |
        | heavy room reverb                | low transcript quality   |
        | a microphone that clipped badly  | low transcript quality   |
        | background HVAC noise            | low transcript quality   |

    @edge-case
    Scenario: The service is not in English
      # Q11 — do we ever need another language? Assumed English-only for now.
      Given the spoken language is not English
      When the transcription stage runs
      Then the Recording is flagged "unexpected language"
      And Analysis continues with low confidence

  Rule: Nothing leaves the local network

    @happy-path @measured
    Scenario: Transcription runs locally
      # Q76 — the same constraint as summarization, and for the same two
      # reasons: avoiding API cost, and not sending the congregation's audio to
      # a third party. This narrows Q13 considerably.
      When the transcription stage runs
      Then no audio leaves the local network
      And no third-party transcription API is called

    @happy-path
    Scenario: The transcription model may live on a different machine
      Given the transcription model is hosted on another machine on the tailnet
      When the transcription stage runs
      Then it calls that machine rather than a hosted service

  Rule: Transcription cost and time are bounded

    @edge-case
    Scenario: A very long recording
      Given the Recording is 3:10:00 long
      When the transcription stage runs
      Then the recording is transcribed in chunks
      And chunk boundaries do not lose or duplicate words
      And timestamps remain absolute against the source file

    @edge-case
    Scenario: The transcription service is unavailable
      Given the local transcription service returns errors
      When the transcription stage runs
      Then the stage is retried with backoff
      And after the retry budget is exhausted the Recording enters "analysis_failed"
      And the reviewer can still set boundaries manually
