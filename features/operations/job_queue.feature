@ops
Feature: Background jobs and retries
  In order to trust that work will finish
  As an operator
  I want long-running work queued, retried and observable

  Ingestion, analysis and processing are all long-running. A web request must
  never wait on them, and a restart must never lose them.

  Rule: Work is queued, not performed inline

    @happy-path
    Scenario Outline: Long-running work runs in the background
      When "<trigger>" happens
      Then a job is enqueued
      And the triggering request returns immediately

      Examples:
        | trigger                              |
        | a webhook announces a new recording  |
        | a download completes                 |
        | a reviewer approves a recording      |
        | an operator retries a failed stage   |

    @happy-path
    Scenario: Jobs survive a restart
      Given jobs are queued
      When the application restarts
      Then the queued jobs still run
      And no job runs twice as a result of the restart

  Rule: Failures are retried within a budget

    @happy-path
    Scenario: Backoff between attempts
      Given a job fails
      Then it is retried with increasing delay between attempts
      And each attempt is recorded with its error

    @edge-case
    Scenario: The retry budget is exhausted
      Given a job has failed its maximum number of attempts
      Then the Recording enters the matching failed state
      And the job stops retrying
      And an operator can retry it manually

    @edge-case
    Scenario: A permanently invalid input is not retried
      Given a job fails because the source file is not decodable audio
      Then it is not retried
      And the Recording enters "ingest_failed" immediately

  Rule: Expensive work does not run more than once

    @edge-case
    Scenario: The same job is enqueued twice
      Given an analysis job is already queued for a Recording
      When another analysis job is enqueued for the same Recording
      Then only one job runs

    @edge-case
    Scenario: Concurrency is bounded
      Given 10 Recordings are ingested at once
      When the worker works through the analysis queue
      Then no more than the configured number of analysis jobs run concurrently
      And the rest wait in the queue

  Rule: The queue is visible

    @happy-path
    Scenario: Viewing the queue
      Given I am on the tailnet
      When I open the system health view
      Then I see how many jobs are queued, running, and failed
      And I can see how long the oldest queued job has been waiting
