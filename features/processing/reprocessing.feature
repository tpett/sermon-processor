@processing @edge-case
Feature: Re-cutting a completed segment
  In order to fix a cut I only noticed was wrong after the fact
  As a reviewer
  I want to change a Segment's boundaries and render it again

  Background:
    Given I am on the tailnet
    And a Segment in state "complete" with punch-in "2:00:20" and punch-out "2:43:32"

  Rule: A completed segment can be sent back for re-cutting

    @happy-path
    Scenario: Re-cutting
      # Not "proposed": a re-cut Segment still has a finished artifact, and
      # artifact_downloads.feature correctly refuses to offer an MP3 for a
      # proposed Segment. Reusing that state made the two files contradict.
      When I choose to re-cut the Segment
      Then it enters "recut"
      And the previously approved boundaries are shown as the starting point
      And the existing MP3 remains downloadable until a new one replaces it

    @happy-path
    Scenario: Approving the new cut
      Given I re-cut and adjusted the punch-out to "2:44:10"
      When I approve the Segment
      And the worker renders it
      Then it is processed again
      And the new MP3 replaces the previous one
      And the previous cut's boundaries are retained in the history

    @happy-path
    Scenario: The original FLAC is never affected
      Given I have re-cut and re-approved a Segment twice
      Then the original FLAC is unchanged
      And it is still downloadable

    @happy-path
    Scenario: Re-cutting one segment leaves its siblings alone
      Given another Segment from the same Recording is "complete"
      When I re-cut this Segment
      Then the other Segment stays "complete"
      And its MP3 is untouched

    @happy-path
    Scenario: Re-cutting to take a span out
      # Asked for when a rendered sermon still held a podium bump: "yes build
      # it". Removing a span is part of the cut, so re-cutting reopens it too.
      Given I have re-cut the Segment
      And I have removed the span from "2:00:21.400" to "2:00:22.100"
      When I approve the Segment
      And the worker renders it
      Then it is processed again
      And the new MP3 leaves out the span from "2:00:21.400" to "2:00:22.100"
      And the new MP3 replaces the previous one

    @edge-case
    Scenario: Re-approving under the same label is not a name collision
      # The file already published under that name is this Segment's own, and
      # it is the file the new render replaces.
      Given I have re-cut the Segment
      When I approve the Segment with the label "Hebrews 12.4-11"
      And the worker renders it
      Then it is processed again
      And the new MP3 replaces the previous one

    @edge-case
    Scenario: Skipping a re-cut keeps the MP3 already published
      # Skipping says no new cut is wanted. It does not unpublish the old one.
      Given I have re-cut the Segment
      When I skip the Segment
      Then it enters "skipped"
      And the existing MP3 remains downloadable until a new one replaces it

    @edge-case
    Scenario: Cancelling a re-approved render goes back to re-cutting
      # Not to "proposed": the Segment still has a published MP3 behind it.
      Given I have re-cut the Segment
      And I approve the Segment
      When I cancel processing
      Then it enters "recut"
      And the existing MP3 remains downloadable until a new one replaces it

  Rule: Re-rendering can be triggered without changing boundaries

    @happy-path
    Scenario: Re-rendering after changing render settings
      Given the loudness target has been changed in configuration
      When an operator re-renders the Segment
      Then the boundaries are unchanged
      And a new MP3 is produced with the new settings
      And the render settings used are recorded


    @happy-path
    Scenario: Renaming without re-rendering
      Given I corrected the label after processing
      When the change is saved
      Then the MP3 audio is not re-encoded
      And the downloadable filename reflects the corrected label

  Rule: Only the current render is kept

    @happy-path
    Scenario: A re-render replaces its predecessor
      # Q52 — confirmed: "if we keep all of the metadata that is necessary for
      # regenerating the previous render, then it is just a derivative product
      # that takes up space, so we can remove them."
      Given a Segment has been rendered twice
      Then only the most recent MP3 is stored
      And the earlier render is deleted

    @happy-path
    Scenario: Every past render remains reproducible
      Given a Segment has been cut, re-cut and re-rendered
      When I view its history
      Then I see each set of boundaries with who approved them and when
      And I see the loudness and encoding settings used for each render
      And any past render could be reproduced from that record and the source

    @happy-path
    Scenario: Reproducing a past render is not offered as a feature
      Then the interface does not offer to restore an earlier render
      And the stored history is what makes adding that later possible
      # Deliberately recorded rather than built. The information is kept; the
      # feature is not, until someone actually wants it.
