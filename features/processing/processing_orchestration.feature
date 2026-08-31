@processing @happy-path
Feature: Processing orchestration
  In order to turn an approved segment into a finished file
  As the Sermon Processor
  I want to run the rendering steps in order and produce the artifact

  Processing operates on a Segment, not a Recording. One Recording can have
  several Segments processing independently.

  Background:
    Given a Segment approved with punch-in "2:00:20" and punch-out "2:43:32"

  Rule: Processing runs as a background job after approval

    @happy-path
    Scenario: A full processing run
      When processing starts
      Then the Segment enters "processing"
      And the following steps run in order:
        | step        | produces                                          |
        | extract     | channel 1 of the approved span                    |
        | normalize   | loudness-corrected audio                          |
        | encode      | an MP3                                            |
        | name        | the output filename from the date and label       |
        | publish     | the artifact made available for download          |
      And when publishing completes the Segment enters "complete"
      And the reviewer is notified

    @happy-path
    Scenario: The approval is what gets rendered
      When processing completes
      Then the MP3 starts at the approved punch-in
      And the MP3 ends at the approved punch-out
      And the MP3 duration is "0:43:12" within 100 ms

    @happy-path
    Scenario: Two segments from one recording process independently
      Given a second Segment from the same Recording is also approved
      When processing runs
      Then both Segments are processed
      And each produces its own MP3
      And a failure in one does not affect the other

    @happy-path
    Scenario: Processing does not block the interface
      When processing starts
      Then the reviewer can continue working with other Recordings and Segments
      And the recordings list shows this Segment as processing

  Rule: Failures are recoverable

    @edge-case
    Scenario Outline: A processing step fails
      Given the "<step>" step fails on every attempt
      When processing runs
      Then the Segment enters "processing_failed"
      And the failure names the step "<step>" and its error
      And partial output is cleaned up
      And a reviewer can retry processing without re-approving

      Examples:
        | step      |
        | extract   |
        | normalize |
        | encode    |

    @edge-case
    Scenario: A transient failure is retried
      Given the "encode" step fails once and then succeeds
      When processing runs
      Then the step is retried
      And processing completes normally

    @edge-case
    Scenario: The source FLAC is no longer on local disk
      Given the local FLAC has been cleaned up
      When processing runs
      Then the source is re-downloaded from the object store first
      And processing continues normally

    @edge-case
    Scenario: The source is gone from the object store too
      Given the local FLAC has been cleaned up
      And the source object no longer exists in the object store
      When processing runs
      Then the Segment enters "processing_failed"
      And the failure reason is "source audio is no longer available"
      # Q56 — this is why the recorder's retention window matters.

    @edge-case
    Scenario: There is not enough disk to render
      Given local storage does not have room for the output
      When processing runs
      Then processing does not begin
      And the Segment stays in "approved" pending space
      And a storage alert is raised

    @edge-case
    Scenario: The process is killed mid-render
      Given processing was interrupted by a restart
      When the system comes back up
      Then the Segment is detected as stuck in "processing"
      And processing is restarted from the beginning
      And no partial artifact is exposed as a download
