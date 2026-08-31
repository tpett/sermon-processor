@analysis @happy-path
Feature: Analysis orchestration
  In order to hand a human a good starting point
  As the Sermon Processor
  I want to run the analysis stages in order and produce a Proposal per Segment

  Analysis is a pipeline of stages. Each stage produces evidence; the later
  stages divide the Recording into Segments, work out what each one is, and
  propose boundaries for each. Stages are individually retryable and their
  outputs are cached, so a failure late in the pipeline does not mean
  re-transcribing three hours of audio.

  Background:
    Given a Recording in state "downloaded"
    And the Recording is 3:12:00 long
    And it contains a 9:00 class and the 10:30 service

  Rule: The pipeline runs its stages in dependency order

    @happy-path
    Scenario: A full analysis run
      When Analysis starts
      Then the Recording enters "analyzing"
      And the following stages run in order:
        | stage                | produces                                            |
        | probe                | duration, channels, bit depth, loudness profile     |
        | waveform             | downsampled peak data for the interface             |
        | preview              | a constant-bitrate seekable rendition for the browser |
        | transcription        | timestamped words and utterances                    |
        | diarization          | speaker-labelled spans                              |
        | blocking             | the Recording divided on speaker and activity change|
        | block_classification | what each Block is                                  |
        | summarization        | a one-line summary and cue excerpt per Block        |
        | agreement            | a second independent analysis, for the confidence signal |
        | segment_proposal     | publishable Segments built from Blocks              |
        | boundary_refinement  | precise punch-in and punch-out per Segment          |
        | scoring              | a Proposal per Segment, with confidence and evidence|
      And when scoring completes the Recording enters "awaiting_review"
      And a notification is sent to the reviewers unless nothing publishable was found

    @happy-path
    Scenario: One recording yields several proposals
      When Analysis completes
      Then 2 Segments exist
      And each Segment has its own punch-in, punch-out, classification and confidence
      And each Segment is independently dispositionable
      And approving one does not affect the other

    @happy-path
    Scenario: Stage outputs are retained for the interface and for re-runs
      Given Analysis has completed
      Then the transcript is retrievable for the Recording
      And the speaker spans, Blocks and their classifications are retrievable
      And the waveform peak data is retrievable for the Recording
      And every Segment's boundaries and classification are stored
      And re-running only the "scoring" stage does not re-run "transcription"

    @happy-path
    Scenario: Nothing detected is ever thrown away
      Given Analysis proposed 3 Segments
      And the reviewer approved 1 and skipped 2
      Then the 2 skipped Segments remain stored with their boundaries and classification
      And they can be revisited and approved months later
      And doing so does not require re-running Analysis

  Rule: Re-running Analysis respects human work

    @edge-case
    Scenario: Analysis is re-run after the detection rules change
      Given Analysis completed and no Segment has been dispositioned
      When an operator re-runs Analysis
      Then the cached transcript and diarization are reused
      And fresh Segments and Proposals replace the previous ones
      And the previous Proposals are kept in the Recording's history

    @edge-case
    Scenario: Analysis is re-run after a reviewer has edited a segment
      # Q14 — a human edit always outranks a machine proposal.
      Given a reviewer adjusted a Segment's punch-in to "1:33:02"
      When an operator re-runs Analysis
      Then that Segment's boundaries are preserved
      And the new machine proposal is shown alongside it as a suggestion
      And Segments the reviewer never touched are replaced normally

    @edge-case
    Scenario: Analysis is re-run after a segment has been rendered
      Given a Segment is "complete"
      When an operator re-runs Analysis
      Then that Segment and its artifact are left alone
      And only undispositioned Segments are replaced

  Rule: A failing stage fails the Recording, not the queue

    @edge-case
    Scenario Outline: A stage fails permanently
      Given the "<stage>" stage fails on every attempt
      When Analysis runs
      Then the Recording enters "analysis_failed"
      And the failure names the stage "<stage>" and its error
      And other Recordings continue to be analysed
      And a reviewer can still open the Recording and create Segments by hand

      Examples:
        | stage                |
        | probe                |
        | transcription        |
        | diarization          |
        | blocking             |
        | block_classification |
        | segment_proposal     |
        | boundary_refinement  |

    @edge-case
    Scenario: A stage fails transiently
      Given the "transcription" stage fails once and then succeeds
      When Analysis runs
      Then the stage is retried
      And Analysis completes normally
      And the retry is visible in the Recording's processing log

    @edge-case
    Scenario: Analysis exceeds its time budget
      Given the analysis time budget is 90 minutes
      And the "transcription" stage has been running for 91 minutes
      Then the stage is cancelled
      And the Recording enters "analysis_failed" with reason "analysis timed out"
      # Budget raised from 45 minutes: sources run up to 2 hours 35 minutes.

  Rule: Analysis never modifies the source audio

    Scenario: The FLAC is read-only to Analysis
      When Analysis completes
      Then the local FLAC is unchanged
      And every derived artifact is written to a separate location
