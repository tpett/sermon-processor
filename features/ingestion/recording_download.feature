@ingestion
Feature: Downloading a recording
  In order to analyse audio we do not own the machine for
  As the Sermon Processor
  I want to pull the FLAC and its metadata sidecar from the object store

  Background:
    Given a Recording in state "discovered" for object key "recordings/recording_20260823_103015.flac"
    And the object store is reachable

  Rule: A successful download makes the Recording analysable

    @happy-path
    Scenario: The FLAC and its sidecar are downloaded
      When the download job runs
      Then the Recording moves through "downloading" to "downloaded"
      And the FLAC is stored in local working storage
      And the sidecar metadata is parsed into the Recording:
        | field       | value                     |
        | recorded_at | 2026-08-23T10:30:15-05:00 |
        | duration    | 5412.4                    |
        | sample_rate | 44100                     |
        | channels    | 2                         |
        | format      | flac                      |
      And Analysis is queued automatically

    @happy-path
    Scenario: The sidecar metadata is missing
      Given the object store has no "recordings/recording_20260823_103015.flac.meta.json"
      When the download job runs
      Then the Recording still reaches "downloaded"
      And the missing sidecar is noted on the Recording
      And technical metadata is derived from the audio file itself instead
      And "recorded_at" falls back to the object's last-modified timestamp

  Rule: Downloads verify what they fetched

    @edge-case
    Scenario: The downloaded bytes do not match the announced MD5
      Given the webhook announced an MD5 of "8f14e45f..."
      And the downloaded file hashes to "3c59dc04..."
      When the download job runs
      Then the download is discarded
      And the download is retried
      And after the retry budget is exhausted the Recording enters "ingest_failed"

    @edge-case
    Scenario: The downloaded file is not decodable audio
      Given the object contains 0 bytes
      When the download job runs
      Then the Recording enters "ingest_failed"
      And the failure reason is "source file is not decodable audio"
      And an operator can retry ingestion from the interface

    @edge-case
    Scenario Outline: Transient object store failures are retried
      Given the object store responds with "<error>"
      When the download job runs
      Then the download is retried with backoff
      And the Recording stays in "downloading" until the retry budget is exhausted

      Examples:
        | error              |
        | 500 Internal Error |
        | 503 Slow Down      |
        | connection reset   |
        | read timeout       |

    @edge-case
    Scenario: There is not enough local disk to hold the file
      Given local working storage has 200 MB free
      And the source object is 720 MB
      When the download job runs
      Then the download does not begin
      And the Recording stays in "discovered"
      And a storage alert is raised on the system health view

  Rule: The source file is never modified

    Scenario: The original FLAC is preserved byte-for-byte
      When the download job completes
      Then the local FLAC hashes identically to the object in the store
      And no process rewrites the local FLAC at any later point
