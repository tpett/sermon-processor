@analysis
Feature: Preview audio for review
  In order to scrub a three-hour recording without downloading it
  As a reviewer
  I want a lightweight, seekable version of the audio to play in the browser

  Sources are up to 1.4 GB of 32-bit stereo FLAC. Reviewing a multi-block
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
      When the preview stage runs
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

    @happy-path @measured
    Scenario: A constant-bitrate file served with range requests
      # Q77, measured. Two candidates on the same source:
      #
      #   CBR MP3 + HTTP range   37.6 MB, one file,  0.04 s worst seek error
      #   HLS segments           42.3 MB, 628 files
      #
      # Seeking to 10, 30, 60, 90 and 100 minutes landed within 0.04 s every
      # time, fetching 0.16% of the file, verified against the source audio.
      # One file, no manifest, no packaging step.
      When the preview stage runs
      Then the preview is a constant-bitrate file
      And it is served with HTTP range request support
      And no seek index has to be parsed before the first seek
      # A variable-bitrate file would need its index read first, which is exactly
      # the complication this was meant to avoid.

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
