@interface
Feature: Discarding and skipping
  In order to keep the queue meaningful
  As a reviewer
  I want to leave things alone without losing them, and throw away what is genuinely rubbish

  There are two different actions here, and conflating them was a mistake in the
  first draft of this spec:

  - **Skip a Segment** — I am not publishing this today. It stays, fully
    described, and I can come back for it. This is the common case.
  - **Discard a Recording** — this whole file is of no interest. An accidental
    trigger, a sound check, a false start.

  Background:
    Given I am on the tailnet

  Rule: Skipping a segment is not throwing it away

    @happy-path
    Scenario: Skipping a segment I might want later
      Given a Recording containing a "lesson" Segment and a "sermon" Segment
      When I approve the sermon and skip the lesson
      Then the lesson Segment enters "skipped"
      And its boundaries, classification, evidence and transcript remain stored
      And it is listed on the Recording detail view as available
      And I can approve it at any time without re-running Analysis

    @happy-path
    Scenario: Skipping does not need a reason
      When I skip a Segment
      Then no reason is required
      And who skipped it and when is recorded

  Rule: A recording can be taken out of the queue entirely

    @happy-path
    Scenario: Discarding an accidental trigger
      Given a Recording of 4 minutes containing 0 Segments
      When I discard it with the reason "accidental trigger"
      Then the Recording enters "discarded"
      And it no longer appears in the default list
      And the reason and who discarded it are recorded

    @happy-path
    Scenario: Discarding while it is still analysing
      Given a Recording in state "analyzing"
      When I discard it
      Then any running analysis job is cancelled
      And the Recording enters "discarded"

    @happy-path
    Scenario: Restoring a discarded recording
      Given a Recording in state "discarded"
      When I restore it
      Then it returns to the state it was in before it was discarded
      And its Segments are intact

    @edge-case
    Scenario: Discarding a recording with a published segment
      Given a Recording containing a Segment in state "complete"
      When I attempt to discard it
      Then I am warned that it contains a published segment
      And the discard proceeds only if I confirm
      And the rendered MP3 remains downloadable

  Rule: Discarding is not deleting

    @happy-path
    Scenario: The source file survives a discard
      Given a Recording in state "discarded"
      Then the source object in the object store is untouched
      And the Recording's record and analysis artifacts are retained
      # Q34 — should discarding eventually free local disk? After how long?

    @deferred
    Scenario: Permanently deleting a recording
      # Q35 — **not in v1** (2026-09-18). There is no hard delete: `discarded`
      # retains the record and the derived artifacts, and the source object is
      # never touched by anything.
      #
      # That is the safe default rather than a gap, for two reasons. The object
      # store keeps every source indefinitely, so nothing is at risk of being
      # lost by *not* deleting. And authentication is none with no roles
      # (interface/authentication.feature), so a hard delete would be an
      # irreversible action available to anything on the tailnet — the one
      # combination worth avoiding until there is a reason for it.
      #
      # Kept specified because the shape is settled and only the scheduling is
      # not. Whoever adds it should add it exactly like this.
      Given a Recording in state "discarded"
      When it is permanently deleted
      Then the local audio and derived artifacts are removed
      And the record of the deletion is retained
      And the source object in the object store is not removed
      And the Recording can be re-ingested from the object store afterwards

  Rule: Recordings with nothing publishable do not need dispositioning

    @happy-path
    Scenario: Band practice needs no action
      Given a Recording whose Blocks are all typed "music"
      And no Segment was proposed
      When I visit the recordings list
      Then it is not counted as needing attention
      And I do not have to discard it for the queue to stay clean
      And it remains available if I ever want it

    @happy-path @measured
    Scenario: A false trigger is ignored without asking me
      # Q36 — confirmed, and it is a content test rather than a duration one.
      # See analysis/audio_probe.feature for the detection.
      Given a Recording containing one transient and otherwise near-silence
      When it is ingested
      Then it is flagged "no substantive content" and marked ignored
      And it never appears as work
      And I can still find and restore it if the machine was wrong

    @happy-path
    Scenario: Duration alone never decides anything
      # The recorder's silence timeout sets the length, so a ten minute file and
      # a forty second file are equally likely to be nothing.
      Given a Recording of 10 minutes containing a real 8 minute conversation
      When it is ingested
      Then it is analysed normally
