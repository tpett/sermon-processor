@ingestion @happy-path
Feature: Upload webhook notification
  In order to start work the moment a recording is available
  As the Sermon Processor
  I want the Recorder to tell me when it has finished uploading a file

  The Recorder and the Processor sit on the same tailnet, so the Recorder simply
  calls a web endpoint on the Processor. There is no signing ceremony and no
  replay window — the network is the boundary. What matters instead is that the
  handler is **idempotent**, because the same file must never be ingested twice.

  A matching feature belongs in the audio-recorder repository; this defines the
  contract from the Processor's side. The webhook is an optimisation, never a
  guarantee — `s3_reconciliation.feature` is the safety net.

  Background:
    Given the Sermon Processor is running
    And the webhook endpoint is "POST /api/webhooks/recordings"
    And the Recorder reaches it over the tailnet

  Rule: A valid webhook creates exactly one Recording

    @happy-path
    Scenario: The Recorder reports a completed upload
      # Payload fields confirmed available from the recorder: the sidecar
      # .meta.json carries timestamp, datetime, duration, format, sample_rate,
      # channels, threshold_db, device and version; the S3 upload path already
      # computes an MD5 for ETag verification. See Q3.
      When the Recorder sends a webhook with the payload:
        | field        | value                                               |
        | event        | recording.uploaded                                  |
        | bucket       | sermons                                             |
        | object_key   | recordings/recording_20260823_102952.flac           |
        | metadata_key | recordings/recording_20260823_102952.flac.meta.json |
        | size_bytes   | 841368564                                           |
        | md5          | 8f14e45fceea167a5a36dedd4bea2543                    |
        | recorded_at  | 2026-08-23T10:29:52-05:00                           |
        | duration     | 6268.95                                             |
        | sample_rate  | 44100                                               |
        | channels     | 2                                                   |
      Then the Processor responds with "202 Accepted"
      And a Recording is created with the state "discovered"
      And the Recording is queued for download
      And no audio has been downloaded yet

    @happy-path
    Scenario: A field the recorder does not currently send is optional
      # The recorder has no machine identity field today — its "device" value is
      # the ALSA device string, not a host. Adding one is a recorder-side change.
      When the Recorder sends a webhook with no host identity
      Then the Processor responds with "202 Accepted"
      And the Recording is created without a device identity

  Rule: The handler is idempotent

    @happy-path
    Scenario: The same webhook is delivered twice
      Given a Recording exists for object key "recordings/recording_20260823_102952.flac"
      When the Recorder sends an identical webhook for that object key
      Then the Processor responds with "200 OK"
      And no duplicate Recording is created
      And no additional download is queued

    @happy-path
    Scenario: The webhook races the reconciliation scan
      Given the reconciliation scan has just created a Recording for an object key
      When a webhook arrives for the same object key
      Then no duplicate Recording is created
      And whichever arrived first owns the Recording

    @happy-path
    Scenario: The object key is the identity
      # Q4 — confirmed: "Source files are immutable. They do not change since
      # they are recorded live and then archived." So the key alone identifies
      # the Recording, and there is no changed-content case to handle.
      Then a Recording is uniquely identified by its bucket and object key
      And the same key always refers to the same audio

    @happy-path
    Scenario: Two webhooks arrive simultaneously for the same object
      When two identical webhooks are handled concurrently
      Then exactly one Recording exists afterwards
      And exactly one download is queued

  Rule: Malformed webhooks are rejected without side effects

    @edge-case
    Scenario Outline: A required field is missing
      When the Recorder sends a webhook with "<field>" omitted
      Then the Processor responds with "422 Unprocessable Entity"
      And the response body names the missing field "<field>"
      And no Recording is created

      Examples:
        | field       |
        | event       |
        | bucket      |
        | object_key  |
        | recorded_at |

    @edge-case
    Scenario: The webhook announces an event type we do not handle
      When the Recorder sends a webhook with event "recording.started"
      Then the Processor responds with "202 Accepted"
      And no Recording is created
      And the ignored event type is logged

  Rule: The Processor is resilient to delivery failures

    @edge-case
    Scenario: The Processor is down when the Recorder fires the webhook
      Given the Sermon Processor is unreachable
      When the Recorder attempts to deliver a webhook
      Then the Recorder retries with exponential backoff
      And after the retry budget is exhausted the Recorder records a delivery failure
      And the Recording is still ingested later by S3 reconciliation

    @edge-case
    Scenario: The webhook arrives before the object is readable in the bucket
      Given the object store has not yet made the object available
      When the Recorder sends a webhook for that object key
      Then the Processor responds with "202 Accepted"
      And the download is retried until the object becomes readable
      And the Recording does not enter "ingest_failed" before 3 attempts
