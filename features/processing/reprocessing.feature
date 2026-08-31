@processing @edge-case
Feature: Re-cutting a completed segment
  In order to fix a cut I only noticed was wrong after the fact
  As a reviewer
  I want to change a Segment's boundaries and render it again

  Background:
    Given I am signed in as a reviewer
    And a Segment in state "complete" with punch-in "2:00:20" and punch-out "2:43:32"

  Rule: A completed segment can be sent back for re-cutting

    @happy-path
    Scenario: Re-cutting
      When I choose to re-cut the Segment
      Then it returns to "proposed"
      And the previously approved boundaries are shown as the starting point
      And the existing MP3 remains downloadable until a new one replaces it

    @happy-path
    Scenario: Approving the new cut
      Given I re-cut and adjusted the punch-out to "2:44:10"
      When I approve the Segment
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

  Rule: Re-rendering can be triggered without changing boundaries

    @happy-path
    Scenario: Re-rendering after changing render settings
      Given the loudness target has been changed in configuration
      When an operator re-renders the Segment
      Then the boundaries are unchanged
      And a new MP3 is produced with the new settings
      And the render settings used are recorded

    @happy-path @assumption
    Scenario: Re-rendering the back catalogue after settling the loudness target
      # Q48 — if the target changes, older files will sit at a different volume
      # than newer ones. Worth being able to bring them into line in one pass.
      Given 20 Segments are "complete" under the previous loudness settings
      When an operator re-renders them all
      Then each is re-rendered from its stored boundaries
      And no reviewer input is required
      And any whose source is no longer available fails individually and is reported

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
