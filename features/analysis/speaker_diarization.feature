@analysis @slow
Feature: Speaker diarization
  In order to spot the change of voice that starts the sermon
  As the Sermon Processor
  I want the recording split into speaker-labelled segments

  The README's strongest punch-in signal is "a new speaker after a scripture
  reading by a different speaker". That signal is useless without knowing where
  voices change.

  Background:
    Given a Recording in state "downloaded"
    And transcription has completed

  Rule: The recording is segmented by speaker

    @happy-path
    Scenario: A typical service with several voices
      When the diarization stage runs
      Then the recording is divided into contiguous speaker segments
      And each segment has a start time, an end time and a speaker label
      And the labels are stable within the recording
      And each segment carries a confidence

    @happy-path
    Scenario: Segments are joined to the transcript
      When the diarization stage runs
      Then every transcript utterance is attributed to a speaker segment
      And the reviewer can see who is speaking beside each utterance in the transcript view

    @happy-path @measured
    Scenario: The preacher is recognised across weeks
      # Q12 — confirmed: "the roster is small. Almost all of them are by one
      # person... a maximum of three or four others who will preach." A voice
      # library of five profiles is small enough to be worth maintaining and
      # is the strongest single signal for finding the teaching block.
      Given a voice profile exists for the primary preacher
      When the diarization stage runs
      Then spans matching that profile are labelled with that preacher
      And spans that match no known profile keep generic labels

    @happy-path
    Scenario: Enrolling a voice from an approved segment
      Given a reviewer approved a Segment classified "sermon"
      And they confirmed who was preaching
      Then that Segment can be used to enrol or strengthen that speaker's profile
      And no separate enrolment recording session is required

    @edge-case
    Scenario: A guest preacher matches nobody
      Given the teaching span matches no known voice profile
      When the diarization stage runs
      Then the span keeps a generic label
      And classification does not penalise it for being an unknown voice
      # Guests are normal. An unknown voice is not evidence against teaching.

    @edge-case
    Scenario: Two speakers overlap
      Given two people speak at once for 6 seconds
      When the diarization stage runs
      Then the overlapping span is marked as overlapping speech
      And it is not treated as a clean speaker change

    @edge-case
    Scenario: Congregational singing confuses speaker detection
      Given the congregation sings for 8 minutes
      When the diarization stage runs
      Then the singing is not emitted as a speaker change
      And the span is labelled as non-speech

    @edge-case
    Scenario: The scripture reader and the preacher are the same person
      # The README calls this out as an occasional case.
      Given one voice reads scripture and then preaches without an intervening speaker
      When the diarization stage runs
      Then no speaker change is detected at the sermon start
      And boundary detection must fall back to other evidence
      And the resulting Proposal has reduced confidence

    @edge-case
    Scenario: Diarization fails
      Given the diarization stage fails on every attempt
      When Analysis runs
      Then boundary detection continues using transcript evidence alone
      And the Proposal is marked as "no speaker evidence"
      And its confidence is reduced
