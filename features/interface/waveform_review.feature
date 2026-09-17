@interface @happy-path
Feature: Reviewing the waveform
  In order to trust the punch points before I approve them
  As a reviewer
  I want to see and hear the audio around the proposed boundaries

  Background:
    Given I am on the tailnet
    And a Recording in state "awaiting_review" with waveform peak data
    And it is 3:12:00 long and contains 2 Segments
    And I have selected the Segment whose punch-in is "2:00:20" and punch-out is "2:43:32"

  Rule: The waveform shows the whole recording and everything found in it

    @happy-path
    Scenario: Seeing the shape of the recording
      When I open the Recording detail view
      Then I see a waveform spanning the full 3:12:00 of the source
      And every Block is drawn as a band along the waveform, coloured by its type
      And proposed Segments are drawn as spans above the Block bands
      And a time ruler is shown, labelled with wall-clock time as well as elapsed time

    @happy-path
    Scenario: The selected segment's cut is highlighted
      When I select a Segment
      Then the region between its punch-in and punch-out is visually highlighted
      And the rest of the Recording is visually de-emphasised

    @happy-path
    Scenario: Evidence markers are shown on the waveform
      Then markers appear at each piece of evidence for the selected Segment
      And hovering a marker describes the evidence
      And clicking a marker seeks the player to that point

    @happy-path
    Scenario: Speaker spans are shown along the waveform
      Then a speaker track is shown beneath the waveform
      And each speaker span is coloured by speaker
      And non-speech regions such as music are visually distinct

  Rule: I can listen to the audio

    @happy-path
    Scenario: Playing from anywhere
      When I click a point on the waveform
      Then playback seeks to that point
      And a playhead follows playback along the waveform

    @happy-path
    Scenario: Auditioning a boundary
      When I choose to preview the punch-in
      Then playback starts 5 seconds before the punch-in
      And I hear the transition into the sermon
      And playback stops 5 seconds after the punch-in

    @happy-path
    Scenario: Auditioning the whole cut
      # Q26 — more useful now: sampling is how I tell one Segment from another.
      When I choose to preview the cut
      Then I hear the last 5 seconds before the punch-in joined to the first 5 seconds after it
      And then the last 5 seconds before the punch-out joined to the first 5 seconds after it

    @happy-path @measured
    Scenario: Playback uses the seekable preview
      # Q27 — confirmed. See analysis/preview_audio.feature for how it is made.
      When I play the audio
      Then the browser plays the preview rendition, not the source FLAC
      And only the region being played is fetched
      And playback begins within 2 seconds of pressing play

  Rule: Zooming lets me place a boundary precisely

    @happy-path
    Scenario: Zooming into a boundary
      When I zoom into the punch-in
      Then the waveform resolution increases
      And I can distinguish individual words in the waveform
      And I can place a boundary to within 100 ms

    @happy-path @measured
    Scenario: Words appear beside the waveform when zoomed
      When I zoom into a boundary
      Then the transcript words are drawn aligned to the waveform
      And I can read exactly what is said either side of the cut

    @happy-path
    Scenario: Returning to the overview
      Given I have zoomed in
      When I choose to fit the whole recording
      Then the waveform returns to showing the full duration
      And all Block bands are visible again

  Rule: What each zoom level is actually for

    @happy-path @measured
    Scenario Outline: Precision by window size
      # Measured on an 1100 px canvas against a 104-minute recording.
      Given the visible window is <window>
      Then 100 ms is <pixels>
      And placing a boundary to 100 ms is <verdict>

      Examples:
        | window            | pixels  | verdict     |
        | whole recording   | 0.0 px  | impossible  |
        | 5 minutes         | 0.4 px  | impossible  |
        | 30 seconds        | 3.7 px  | awkward     |
        | 3 seconds         | 36.7 px | comfortable |

    @happy-path @measured
    Scenario: Words and waveform serve different steps
      # At a 30-second window 48 words are readable beside the waveform. At the
      # tightest zoom there are none — because a good cut lands in silence. So
      # the words help find the moment and the waveform helps place it.
      Given I am looking for the right moment
      Then the transcript is what I read
      Given I am placing the cut precisely
      Then the waveform is what I use
      And no words are expected in view at that zoom

    @happy-path @measured
    Scenario: Peak data is fetched, not embedded
      # Peaks and words for one recording are about 2.76 MB.
      Given a Recording of 104 minutes
      Then its peak data is fetched per recording rather than inlined in the page
      And it is served at progressive resolution

  Rule: The interface degrades usefully

    @edge-case
    Scenario: Waveform data is unavailable
      Given the waveform stage failed
      When I open the Recording detail view
      Then I am told the waveform could not be generated
      And playback and the transcript are still available
      And Blocks and Segments are listed with their timecodes instead of drawn
      And I can still adjust and approve boundaries
