@ingestion @edge-case
Feature: S3 reconciliation
  In order to never silently lose a Sunday
  As a church operator
  I want the Processor to find recordings even when the webhook did not arrive

  The webhook is an optimisation, not a guarantee. A periodic scan of the
  bucket is the system of record for "what recordings exist".

  Background:
    Given the object store is a Garage S3 instance reachable over the tailnet
    And it contains a bucket "sermons"
    And the Processor scans the bucket on a schedule

  Rule: The scan discovers anything the webhook missed

    @happy-path
    Scenario: An un-notified recording is found
      Given the bucket contains:
        | object_key                                   | size_bytes | last_modified             |
        | recordings/recording_20260823_103015.flac    | 743829120  | 2026-08-23T11:05:00-05:00 |
        | recordings/recording_20260816_102958.flac    | 701244416  | 2026-08-16T11:04:12-05:00 |
      And the Processor has never seen "recordings/recording_20260816_102958.flac"
      When the reconciliation scan runs
      Then a Recording is created for "recordings/recording_20260816_102958.flac"
      And it is queued for download
      And no duplicate is created for "recordings/recording_20260823_103015.flac"

    @edge-case
    Scenario: The scan sees a file that is still being uploaded
      Given the bucket contains "recordings/recording_20260823_103015.flac" modified 4 seconds ago
      # Q6 — assumed: a settle window avoids grabbing partial multipart uploads.
      When the reconciliation scan runs
      Then no Recording is created yet
      And the object is reconsidered on the next scan

    @edge-case
    Scenario: Objects that are not recordings are ignored
      Given the bucket contains:
        | object_key                                          |
        | recordings/recording_20260823_103015.flac.meta.json  |
        | recordings/README.txt                                |
        | recordings/.keep                                     |
      When the reconciliation scan runs
      Then no Recordings are created
      And the sidecar metadata file is associated with its parent recording if one exists

    @edge-case @measured
    Scenario: A recording predates the Processor's deployment
      # Q7 — confirmed: "Not needed except for testing. Everything in the old
      # recordings list has already been edited and published."
      Given the Processor's ingest cutoff date is its deployment date
      And the bucket contains a recording from before that date
      When the reconciliation scan runs
      Then no Recording is created for it
      And it can still be ingested manually for testing

    @edge-case
    Scenario: The object store is unreachable during a scan
      Given the object store returns connection errors
      When the reconciliation scan runs
      Then the scan fails without changing any Recording state
      And the failure is surfaced on the system health view
      And the next scheduled scan runs normally

  Rule: An operator can force ingestion

    Scenario: Ingesting a specific object on demand
      Given an operator is signed in
      When they submit the object key "recordings/recording_20240107_101500.flac" for manual ingestion
      Then a Recording is created regardless of the ingest cutoff date
      And this is how the sample corpus is loaded for the accuracy suite
      And it is queued for download
