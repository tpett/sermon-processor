@processing @happy-path
Feature: Downloading artifacts
  In order to upload the file wherever it needs to go
  As a reviewer
  I want to download the finished MP3 and the original FLAC

  Downloading is the finish line — the Processor does no publishing of its own.

  Background:
    Given I am on the tailnet
    And a Segment in state "complete" from a Recording dated "2026-08-23"
    And its label is "Hebrews 12.4-11"

  Rule: The finished artifacts are downloadable

    @happy-path @measured
    Scenario: Downloading the MP3
      When I open the Segment
      Then I can download the rendered MP3
      And the download filename is "2026-08-23 - Hebrews 12.4-11.mp3"
      And the file size and duration are shown before I download

    @happy-path
    Scenario: Downloading the original FLAC
      When I open the Recording detail view
      Then I can download the original untrimmed FLAC
      And it is byte-identical to what the recorder uploaded

    @happy-path
    Scenario: Downloading several segments from one recording
      Given two Segments from the same Recording are "complete"
      When I open the Recording detail view
      Then each Segment offers its own MP3 download
      And the filenames differ

    @happy-path @measured
    Scenario Outline: The transcript is downloadable
      # Q51 — confirmed: "If we end up transcribing the whole segment, I think
      # allowing that to be downloaded and also viewed in the user interface is
      # worth the little bit of time it will take to wire those up."
      When I open the Segment
      Then I can download "<artifact>"

      Examples:
        | artifact                      |
        | the transcript as plain text  |
        | the transcript with timecodes |

    @happy-path @measured
    Scenario: The transcript is readable in the interface
      When I open the Segment
      Then I can read its transcript without downloading anything
      And the transcript covers the approved span
      And I can expand to the full Recording transcript

    @happy-path
    Scenario: Downloads work on a phone
      Given I am using a phone
      When I download the MP3
      Then the download completes without the page timing out

  Rule: Downloads are served efficiently

    @happy-path @measured
    Scenario: Large files stream rather than buffer
      # Sources run up to 1.4 GB.
      Given the FLAC is 1.4 GB
      When I download it
      Then the file is streamed
      And the application does not load the whole file into memory

    @happy-path
    Scenario: Downloads can be resumed
      Given a download was interrupted at 300 MB
      When my browser resumes it
      Then the download continues from where it stopped

  Rule: Only finished artifacts are offered

    @edge-case
    Scenario Outline: Artifacts that do not exist yet
      Given the Segment is in state "<state>"
      When I open it
      Then the MP3 download is not offered

      Examples:
        | state             |
        | proposed          |
        | skipped           |
        | approved          |
        | processing        |
        | processing_failed |

    @edge-case
    Scenario: The FLAC has been cleaned up locally
      # Owner, on the link that 404'd for every source never fetched: "Stream it
      # from S3 if possible." The one named object is streamed through to the
      # download and nothing is written locally, so a click never commits the
      # Processor to holding a 0.4-1.4 GB copy it was not asked to keep.
      Given the local FLAC has been removed to save disk
      When I download the original FLAC
      Then it is streamed from the object store without being kept
      And the download still succeeds

    @edge-case
    Scenario: An artifact file is missing from storage
      Given the rendered MP3 file cannot be found
      When I attempt to download it
      Then I am told the artifact is unavailable
      And I am offered the option to re-process the Segment
