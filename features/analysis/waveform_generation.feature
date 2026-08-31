@analysis
Feature: Waveform peak generation
  In order to let a reviewer see the shape of the service
  As the Sermon Processor
  I want to precompute downsampled waveform data

  A 90 minute FLAC is far too large to draw in a browser. The interface needs a
  compact peak file it can render instantly and zoom into.

  Background:
    Given a Recording in state "downloaded"
    And the Recording is 1:30:12 long

  Rule: Peak data is generated once and reused

    @happy-path
    Scenario: Generating peaks for a recording
      When the waveform stage runs
      Then a peak file is produced for the Recording
      And it contains min/max pairs at a fixed resolution
      And it is small enough to load in the browser in under 2 seconds on a normal connection
      And it is stored as an artifact of the Recording

    @happy-path @assumption
    Scenario: Multiple zoom levels are available
      # Q17 — assumed: the reviewer needs to zoom to second-level precision
      # around the punch points without downloading the whole audio file.
      When the waveform stage runs
      Then peak data is available at an overview resolution covering the whole recording
      And at a detail resolution suitable for placing a boundary within 100 ms

    @edge-case
    Scenario: Peak generation fails
      Given the waveform stage fails on every attempt
      When Analysis runs
      Then Analysis continues to the remaining stages
      And the Recording still reaches "awaiting_review"
      And the interface shows the reviewer that the waveform is unavailable
      And the reviewer can still adjust Segment boundaries using playback and the transcript

  Rule: The waveform reflects the source, not the render

    Scenario: Peaks are generated from the untrimmed, unnormalized FLAC
      When the waveform stage runs
      Then the peaks span the full duration of the source recording
      And no normalization has been applied to the peak data
