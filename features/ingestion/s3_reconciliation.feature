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
      And it is not queued for download until someone asks for it
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

  Rule: Nothing is dropped without being counted

    @edge-case @policy
    Scenario: An object the Processor decided to skip
      # Three ways a recording disappears silently today: a recorder clock reset
      # writes an unparseable key, a naming change stops matching the pattern,
      # and anything before the ingest cutoff is discarded. Each currently ends
      # in "no Recording is created" with no reporting clause.
      #
      # Q57 declined an alert for a missing Sunday. That decision only holds if
      # skipped objects are visible somewhere.
      Given the reconciliation scan skips an object
      Then the object key and the reason are recorded
      And an operator can see every object the Processor has ever skipped
      And no alert is raised for it

    @edge-case @policy
    Scenario Outline: Reasons an object is skipped
      Given an object "<key>"
      When the reconciliation scan runs
      Then it is recorded as skipped with the reason "<reason>"

      Examples:
        | key                            | reason                         |
        | recording_19700101_000000.flac | recorder clock not set         |
        | sermon-2027-01-03.flac         | key does not match the pattern |
        | recordings/README.txt          | not an audio object            |
        | recording_20240107_101500.flac | before the ingest cutoff       |

    @edge-case @policy
    Scenario: A credential failure is not a transient error
      # The retry outline covers 500, 503, connection reset and read timeout. A
      # 403 would burn the whole retry budget as though it were transient, and
      # then look identical to a quiet week.
      Given the object store responds with "403 Forbidden"
      When the reconciliation scan runs
      Then it is not retried as a transient failure
      And it is surfaced on the system health view as a credential problem

  Rule: An operator can ask for a scan now

    @happy-path
    Scenario: Scanning the bucket on demand
      # The scheduled scan is still to come, so a recording whose webhook never
      # arrived is invisible until someone asks. Listing a bucket is quick and
      # answers in the request; what it finds waits for someone to ingest it,
      # because downloading is the slow part and belongs to the worker.
      Given I am on the tailnet
      And the bucket contains a recording the Processor has never seen
      When I ask for a scan
      Then the new recording appears in the list
      And I am told how many were found

    @edge-case
    Scenario: Asking for a scan while the object store is unreachable
      Given the object store returns connection errors
      When I ask for a scan
      Then I am told the object store could not be reached
      And no Recording state is changed

  Rule: An operator can force ingestion

    Scenario: Ingesting a specific object on demand
      Given I am on the tailnet
      When they submit the object key "recordings/recording_20240107_101500.flac" for manual ingestion
      Then a Recording is created regardless of the ingest cutoff date
      And this is how the sample corpus is loaded for the accuracy suite
      And it is queued for download
