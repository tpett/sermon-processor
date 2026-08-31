@ops
Feature: System health
  In order to know the system is working before Sunday
  As an operator
  I want a single view of everything that could be broken

  Rule: The health view shows the state of every dependency

    @happy-path
    Scenario: Viewing system health
      Given I am signed in as an operator
      When I open the system health view
      Then I see the status of:
        | dependency              |
        | the object store        |
        | the job queue           |
        | the transcription service  |
        | local disk space        |
        | ffmpeg availability     |
        | the notification channel |

    @happy-path
    Scenario: Recent webhook activity is visible
      When I open the system health view
      Then I see when the last webhook was received
      And I see when the last reconciliation scan ran
      And I see how many recordings each discovered

    @happy-path
    Scenario: A missing Sunday is visible but not alerted
      # Q57 — confirmed: an alert is not wanted. The information is still on
      # the page, so a glance shows whether last Sunday arrived.
      Given no recording has been ingested for 8 days
      When I open the system health view
      Then I see how long it has been since the last ingest
      And no alert is raised
      And no notification is sent

  Rule: A health endpoint supports external monitoring

    @happy-path
    Scenario: Healthy
      When an external monitor requests the health endpoint
      Then it responds with "200 OK"
      And the body reports each dependency as healthy

    @edge-case
    Scenario: Degraded
      Given the object store is unreachable
      When an external monitor requests the health endpoint
      Then it responds with a non-success status
      And the body names the unhealthy dependency

  Rule: Errors are traceable

    @happy-path
    Scenario: Finding out why a recording failed
      Given a Recording is in state "analysis_failed"
      When I open its processing log
      Then I see every job attempt with its timestamp, duration and error
      And I can correlate an entry to the application logs
