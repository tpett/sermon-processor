@analysis
Feature: Preview audio for review
  In order to scrub a three-hour recording without downloading it
  As a reviewer
  I want a lightweight, seekable version of the audio to play in the browser

  Sources are up to 1.4 GB of 24-bit stereo FLAC. Reviewing a multi-block
  recording means jumping between a dozen points across three hours, so the
  browser must be able to fetch only the part being played.

  Background:
    Given a Recording in state "downloaded"

  Rule: A preview rendition is produced during analysis

    @happy-path
    Scenario: Generating the preview
      When the preview stage runs
      Then a preview rendition of the whole Recording is produced
      And it is derived from channel 1 only, like the final render
      And it is stored as an artifact of the Recording
      And it is available before any Segment is approved

    @happy-path
    Scenario: The preview is not the product
      Then the preview is never offered as a download
      And the published MP3 is always rendered from the source FLAC, never from the preview
      # The preview exists to be scrubbed. Quality decisions belong to the render.

  Rule: Playback fetches only what it needs

    @happy-path @measured
    Scenario: Jumping to a point mid-recording
      # Q27 — confirmed: "allowing the player in the browser to jump to certain
      # points and only download segments of the file relevant to where they are
      # scrubbed... that would make the response time much faster."
      Given a Recording 3 hours long
      When I seek to "2:14:00"
      Then only the audio around that point is fetched
      And playback begins within 2 seconds
      And the earlier part of the recording is never downloaded

    @happy-path
    Scenario: Previewing a cue excerpt
      Given a Block has a cue excerpt at "1:42:10"
      When I press Preview
      Then only the audio for that excerpt is fetched
      And playback begins almost immediately

    @happy-path
    Scenario: Auditioning a boundary
      When I preview a punch-in
      Then only the seconds either side of the boundary are fetched

    @happy-path @assumption
    Scenario: The format supports seeking without a full download
      # Q77 — the exact mechanism is a technology choice: segmented streaming,
      # or a constant-bitrate format that supports byte-range seeking. Either
      # satisfies this spec. Confirmed the constraint is that it must not be
      # "overly complicated".
      Then the preview format allows the player to seek without downloading the whole file
      And the mechanism is chosen for simplicity over sophistication

    @happy-path @measured
    Scenario: Seekability buys quality back
      # Confirmed: "Something like that would also allow us to have a higher bit
      # rate without sacrificing response time."
      Given playback fetches only the region being played
      Then the preview may use a higher bitrate than a whole-file download would allow
      And responsiveness is unaffected by the increase

  Rule: Review still works without a preview

    @edge-case
    Scenario: Preview generation fails
      Given the preview stage fails on every attempt
      When Analysis runs
      Then Analysis continues to the remaining stages
      And the Recording still reaches "awaiting_review"
      And the reviewer is told playback is unavailable
      And the transcript, summaries and waveform are still usable
      And boundaries can still be adjusted and approved

    @edge-case
    Scenario: The preview is stale after a re-run
      Given the source was re-downloaded
      Then the preview is regenerated
      And no reviewer ever hears audio from a different Recording
