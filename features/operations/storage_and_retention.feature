@ops
Feature: Storage and retention
  In order to keep everything without thinking about it
  As an operator
  I want a policy that reflects having far more disk than this system needs

  Measured: the sample folder holds 46 GB for five months, and sources run
  300 MB to 1.4 GB. The homelab has roughly 26 TB, with an S3-compatible bucket
  on the same array for long-lived files and scratch space well beyond what this
  needs. Storage is not a constraint, so the policy is simple: keep things.

  Rule: Everything is kept indefinitely

    @happy-path @measured
    Scenario Outline: What is retained
      # Q53, Q54, Q55, Q71 — all confirmed. Nothing is pruned on a schedule.
      Given a Recording ingested 2 years ago
      Then its "<artifact>" is still available

      Examples:
        | artifact                 |
        | source FLAC              |
        | rendered MP3             |
        | transcript               |
        | speaker spans and Blocks |
        | Segment boundaries       |
        | waveform peaks           |

    @happy-path
    Scenario: A skipped segment stays extractable forever
      Given a Segment was skipped 2 years ago
      When a reviewer approves it now
      Then the source is still available
      And the Segment renders from its stored boundaries
      And no re-analysis is required

    @happy-path
    Scenario: Only superseded renders are removed
      # Q52 — the one thing that is deliberately not kept.
      Given a Segment has been re-rendered
      Then only the current MP3 is stored
      And the settings needed to reproduce the previous one are retained

  Rule: Local working space is separate from long-lived storage

    @happy-path
    Scenario: Long-lived files live on the array
      Then source FLACs, rendered MP3s and analysis artifacts are written to long-lived storage
      And local scratch holds only what a running job needs

    @happy-path
    Scenario: Scratch is reclaimed after a job
      Given a processing job has finished
      Then its intermediate files are removed from scratch
      And the artifacts it produced are not

    @happy-path
    Scenario: Nothing in progress is cleaned up
      Given a Recording is downloading, analyzing, or has a Segment processing
      When scratch is reclaimed
      Then its working files are retained

  Rule: Disk is monitored even though it is ample

    @edge-case
    Scenario: Scratch fills up
      Given scratch space is exhausted
      Then new downloads and renders pause
      And an alert is raised on the system health view
      And no Recording or Segment state is lost

    @edge-case
    Scenario: Long-lived storage crosses a warning threshold
      Given long-lived storage reaches 90% of the array
      Then an alert is raised
      # 26 TB against roughly 110 GB a year means this should not fire this
      # decade. It exists so that if something goes wrong it is visible.

  Rule: The object store is the source of truth

    @happy-path
    Scenario: The processor never deletes a source
      When any cleanup runs
      Then no source object is deleted

    @edge-case
    Scenario: A source is unexpectedly missing
      Given the object store no longer holds a Recording's source
      Then the Recording is flagged "source no longer available"
      And its skipped Segments are marked as no longer extractable
      And an operator is alerted
      # Not expected, since nothing prunes the bucket. Specified because the
      # failure is silent and would destroy stored work if it ever happened.
