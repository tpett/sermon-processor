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

  Rule: Inference is reached over HTTP, and only over HTTP

    # Settled 2026-09-17. Reasoning runs on a separate always-on Mac because the
    # app server has little GPU. That host serves ollama and nothing else.
    #
    # "Normal operations of this tool should only invoke ollama over the API. We
    # will not deploy ssh credentials to the production environment to be able to
    # talk to mac-m1 that way."
    #
    # This is a boundary on the *runtime*, not on how the host was set up. It
    # decides where each stage can physically run, so it belongs here rather than
    # in a deployment note nobody reads.

    @happy-path
    Scenario: Reasoning stages call the model host over its API
      Given block classification and summarisation need a language model
      When those stages run
      Then they issue HTTP requests to the configured model endpoint
      And they hold no credentials for the machine serving it
      And they never open a shell on it

    @happy-path @measured
    Scenario: Speech-to-text cannot be delegated to that endpoint
      # Checked on ollama 0.32.15 and 0.34.0: `POST /v1/audio/transcriptions`
      # exists and routes, but every `whisper` tag in the library registry 404s
      # and `ollama pull whisper` fails. The endpoint has no model behind it.
      Then transcription runs wherever the application itself runs
      And it is not sent to the model endpoint

    @edge-case
    Scenario: The model host is unreachable
      Given the model endpoint does not answer
      When analysis reaches a reasoning stage
      Then the Recording is left in a state the run can resume from
      And the stages already cached are not recomputed
      And the failure names the endpoint, not a generic model error

  Rule: The pipeline runs its stages in dependency order

    @happy-path
    Scenario: A full analysis run
      When Analysis starts
      Then the Recording enters "analyzing"
      And the following stages run in order:
        | stage                | produces                                            |
        | envelope             | the amplitude envelope every later stage reads      |
        | probe                | duration, channels, bit depth, loudness, emptiness  |
        | waveform             | downsampled peak data for the interface             |
        | preview              | a constant-bitrate seekable rendition for the browser |
        | transcription        | timestamped words and utterances                    |
        | diarization          | speaker-labelled spans                              |
        | blocking             | the Recording divided on speaker and activity change|
        | block_classification | what each Block is                                  |
        | summarization        | a one-line summary and cue excerpt per Block        |
        | segment_proposal     | publishable Segments built from Blocks              |
        | boundary_refinement  | precise punch-in and punch-out per Segment          |
        | agreement            | a second independent analysis, for the review signal |
        | scoring              | a Proposal per Segment, with its evidence           |
      And blocking and block_classification iterate until stable, because a block
        edge can depend on what its neighbour turns out to be
      And the agreement stage repeats segment_proposal independently, so it runs
        after it rather than before
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
