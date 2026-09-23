@interface @happy-path
Feature: Reviewing the waveform
  In order to trust the punch points before I approve them
  As a reviewer
  I want to see and hear the audio around the proposed boundaries

  The shape of this screen was settled by building it against real recordings
  rather than by drawing it. What that exercise established, and what the
  scenarios below are the consequences of:

  **Two views, not one, and both on screen at once.** A single zoomable waveform
  cannot do this job, because the two things a reviewer does need incompatible
  scales. Finding the moment needs minutes in view; placing the cut needs
  seconds. So there is an overview of the whole recording that never moves, and a
  detail view that does — and the overview carries the detail view's window as a
  marker, so the reviewer never loses the answer to "where am I".

  **Zoom is a small set of named steps, not a slider.** The measured table below
  is why: precision is not a smooth function of window size, it has a cliff. At
  thirty seconds, 100 ms is under four pixels and placing a cut is awkward; at
  three seconds it is thirty-seven pixels and comfortable. A continuous zoom
  invites the reviewer to sit at the wrong scale and blame themselves for a
  fiddly cut. Discrete steps — the whole recording, a few minutes, thirty
  seconds, three seconds — each correspond to a task, and the last of them is the
  only one where the cut actually gets placed.

  **The words sit beside the detail view and belong to a different step.** At a
  thirty-second window about forty-eight words are readable; at the tightest zoom
  there are none, because a good cut lands in silence. That is not a defect of
  the transcript panel — it is the signal that the reviewer has finished reading
  and started placing.

  **The numbers are part of the interface, not decoration.** Punch-in, punch-out,
  length, and the gap to whatever comes next, all to hundredths. The gap is the
  one a reviewer would otherwise have to infer from pixels, and it is exactly
  what the tail rule and the 250 ms clearance are about.

  One thing the exercise produced that deliberately does **not** appear here: it
  showed each boundary's distance from the known human cut. That was an
  instrument for judging the machine, and it has no counterpart in use — in
  production there is no human boundary to compare against until the reviewer
  makes one. Carrying it across would mean inventing a number, so the numbers
  above are all about the audio and the proposal, never about correctness.

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

    @deferred
    Scenario: Playback speed
      # **Not in v1** (2026-09-18). Playback is single-speed.
      #
      # The three-click week is two short auditions, where speed is irrelevant.
      # It would only matter for listening through a segment to judge content
      # rather than boundaries, and that is not a job this screen claims.
      Then playback runs at normal speed
      And no speed control is offered


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
    Scenario: The cut is marked while I audition it
      # A preview is ten seconds of audio with the boundary in the middle of it.
      # Hearing it is not enough to judge it: a punch-in half a second late
      # sounds much like a clean one unless the reviewer can see which instant
      # was the cut. So the boundary is marked, and the sides are named.
      When I choose to preview the punch-in
      Then the boundary is marked at the punch-in timecode
      And the mark says which boundary it is
      And what would be cut away is distinguished from what would be kept
      And the playhead is shown against that mark as the audio plays

    @happy-path
    Scenario: A cut light shows the exact instant
      # Asked for directly: "come up with a way to show the precise moment the
      # cut happens during the preview. Like a cut light or other visual
      # indicator." A mark on the waveform means watching the right pixel; a
      # light is unmissable while listening. It names the sides because a
      # punch-in keeps what follows it and a punch-out keeps what precedes it,
      # and a reviewer told that backwards would trust it.
      When I choose to preview the punch-in
      Then a cut light shows the boundary it is tracking and its timecode
      And it reads the playhead's offset from the cut as a signed number
      And it says whether the audio now playing would be kept or discarded
      And it names which side of this boundary is discarded

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

  Rule: The overview and the detail view are both present, and linked

    @happy-path
    Scenario: The overview never moves
      When I zoom the detail view into the punch-in
      Then the overview still shows the whole recording
      And the overview marks the window the detail view is showing
      And I can see where in the service that window falls

    @happy-path
    Scenario: Moving around from the overview
      When I click a point on the overview
      Then the detail view moves to that point
      And its zoom level is unchanged
      # Changing position and changing scale are separate acts. Doing both at
      # once is how a reviewer gets lost.

    @happy-path
    Scenario: Zoom is chosen from named steps
      Then the zoom steps offered are:
        | step            |
        | whole recording |
        | a few minutes   |
        | thirty seconds  |
        | three seconds   |
      And each step states what it is for
      And the three-second step is the one that places a cut

  Rule: The readout says where the boundaries are, never how right they are

    @happy-path
    Scenario: What the numbers show
      Then the punch-in, the punch-out and the length are shown to hundredths
      And the gap between the punch-out and whatever follows is shown
      And nothing claims the boundary is correct

    @happy-path
    Scenario: The gap is shown because it is the thing pixels hide
      # The tail rule and the 250 ms clearance are both about this number, and it
      # cannot be read off a waveform at any useful zoom.
      Given the punch-out is 0.90 seconds before the next speech
      Then the gap is shown as "0.90 s"
      And it is marked as shorter than the 1.5 second tail the editor prefers

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

    # The table below is the reason zoom is a set of steps rather than a
    # continuum, and the reason the tightest step exists at all. Read the
    # `pixels` column as "how much of the screen 100 milliseconds buys you".


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

  Rule: When something the screen needs is missing, it says so

    # The waveform-unavailable path was already here. These are the other two
    # things this screen depends on and cannot produce itself.

    @edge-case
    Scenario: The preview audio will not play
      Given the seekable preview has not been rendered
      When I try to audition the punch-in
      Then I am told the preview is not ready rather than left with a dead control
      And the waveform and the transcript remain usable
      And the boundaries can still be adjusted and approved

    @edge-case
    Scenario: The model host is unreachable while I am reviewing
      # Analysis reaches the reasoning host over HTTP and nothing else -- see
      # analysis/analysis_orchestration.feature. A reviewer mid-edit should not
      # discover that by watching a control do nothing.
      Given the configured model endpoint does not answer
      Then reviewing, adjusting and approving continue to work
      And only the actions that need a model are shown as unavailable
      And the reason names the endpoint rather than blaming the Recording

  Rule: The interface degrades usefully

    @edge-case
    Scenario: Waveform data is unavailable
      Given the waveform stage failed
      When I open the Recording detail view
      Then I am told the waveform could not be generated
      And playback and the transcript are still available
      And Blocks and Segments are listed with their timecodes instead of drawn
      And I can still adjust and approve boundaries
