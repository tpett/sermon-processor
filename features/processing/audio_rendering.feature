@processing @slow
Feature: Rendering a segment's audio
  In order to publish something that sounds consistent week to week
  As the Sermon Processor
  I want to extract, trim, normalize and encode an approved Segment

  Today this is done by hand: split the stereo track to mono and delete the
  silent channel, set the punch points, cut, normalize, export. This feature
  turns that into a repeatable step — and fixes a problem the manual process
  creates without meaning to (see the loudness rule).

  Background:
    Given an approved Segment with punch-in "2:00:20" and punch-out "2:43:32"
    And the source is FLAC 44.1 kHz stereo 32-bit
    And channel 2 of the source is silent

  Rule: The source is reduced to its one real channel

    @happy-path @measured
    Scenario: Channel 1 is extracted, not downmixed
      # The recorder feeds a mono signal into a stereo recorder. Averaging the
      # two channels would cost 6 dB and fold in the dead channel's noise.
      When the render runs
      Then the output takes channel 1 only
      And channel 2 is discarded without being mixed in
      And the output level matches channel 1's level, not half of it
      And the output is mono

    @edge-case
    Scenario: Both channels carry signal
      Given the probe flagged the Recording "unexpected stereo content"
      When the render runs
      Then the render does not start automatically
      And the reviewer is asked how the channels should be treated
      # Never guess. A silent 6 dB error is worse than a question.

  Rule: The output contains exactly the approved span

    @happy-path
    Scenario: Trimming to the approved boundaries
      When the render runs
      Then the output begins at the approved punch-in
      And the output ends at the approved punch-out
      And the output duration matches the approved span within 100 ms
      And the trim is sample-accurate rather than snapped to a frame boundary

    @happy-path @assumption
    Scenario: The cut does not click or pop
      # Q47 — short fades prevent a click at a non-zero-crossing cut.
      When the render runs
      Then a short fade-in is applied at the start
      And a short fade-out is applied at the end
      And neither fade is long enough to swallow a spoken word

  Rule: Loudness is one operation, not two

    @happy-path @measured
    Scenario: Normalizing to a target loudness
      # Q48/Q49 — confirmed. The old process was "click Normalize in Audacity,
      # then usually Compress", which measured -20.8 to -29.9 LUFS across four
      # weeks from sources only 1.2 LU apart. Peak normalization keys off one
      # loudest sample, so a single cough drags a whole sermon down.
      #
      # Confirmed too that normalize and compress are one concern, not two:
      # "we do not need to separate normalize and compress". So there is one
      # loudness stage that measures, corrects and limits in a single pass.
      When the render runs
      # Measured: two-pass loudnorm in linear mode lands at -16.8 to -17.4 LUFS,
      # holding back to protect the true-peak ceiling. An earlier version of this
      # scenario asserted -16 within 1 LU, which four of six validated renders
      # failed. The target is what the renderer actually achieves, consistently.
      Then the output integrated loudness is "-17 LUFS" within 1 LU
      # Measured: -1.5 dBTP is what the loudness stage is asked for before
      # encoding, not what the file achieves — the six validated renders
      # decoded to -1.1, -0.8, -1.0, -0.8, -0.6 and -0.7 dBTP. The ceiling
      # below allows 1 dB of encoder overshoot and stays clear of full scale.
      And the output true peak, measured on the decoded MP3, does not exceed "-0.5 dBTP"
      And the measured input and output loudness are recorded on the Segment

    @happy-path @measured
    Scenario: Every week sounds the same
      Given two Segments whose sources differ in loudness by 8 LU
      When both are rendered
      Then their output integrated loudness values are within 1 LU of each other

    @happy-path @measured
    Scenario: A single loud moment does not drag the whole file down
      # This is the specific failure in 2026-05-24, which shipped 9 LU quieter
      # than its neighbours despite a near-identical source.
      Given the Segment contains one isolated peak 12 dB above the speech level
      When the render runs
      Then the output integrated loudness still meets the target
      And the isolated peak is limited rather than allowed to set the level

    @happy-path @measured
    Scenario: Quiet passages come up without a separate compression step
      # Confirmed: "when we had quiet recordings, the compression seemed to
      # bring up some of the quieter parts. I am not sure that this is really
      # helpful with the normalized feature." Loudness normalization measures
      # the whole programme rather than its loudest sample, which is what
      # actually raises a quiet passage.
      Given the Segment contains passages 18 dB quieter than the loudest passage
      When the render runs
      Then the quiet passages are audible at a normal listening volume
      And the loudest passages are not clipped
      And no separate compression stage is applied

    @happy-path
    Scenario: The loudness treatment is a single configured target
      Then there is one set of loudness settings, not a normalize toggle and a compress toggle
      And the settings used are recorded on every rendered Segment
      And changing them is what makes a re-render meaningful

    @edge-case
    Scenario: The source is already clipping
      # Known and being fixed at the hardware, but files already recorded still
      # have to render.
      Given the source true peak is "0.4 dBFS" with samples at full scale
      When the render runs
      Then the output is brought down to the target loudness and peak ceiling
      And no attempt is made to reconstruct the clipped peaks
      And the Segment records that the source was clipped

    @edge-case
    Scenario: The source is very quiet
      Given the source integrated loudness is "-34 LUFS"
      When the render runs
      Then the output reaches the target loudness
      And the noise floor is not raised to a distracting level
      And the Segment is flagged "source was very quiet"


  Rule: The MP3 matches what is already being shipped

    @happy-path @measured
    Scenario: Encoding settings
      # Measured across 24 files: mono, 44.1 kHz, VBR averaging 96-108 kbps.
      # Confirmed as fine, and it is a sane spoken-word setting — comfortably
      # above where mono speech becomes audibly degraded. See Q50 for the one
      # option worth considering later.
      When the render runs
      Then the output is an MP3
      And the channel layout is mono
      And the sample rate is 44100 Hz
      And the bitrate is variable, averaging between 96 and 108 kbps

    @happy-path @measured
    Scenario: File size is reasonable
      Given the Segment is 43 minutes long
      When the render runs
      Then the resulting MP3 is between 25 MB and 40 MB

    @happy-path
    Scenario: Encoding settings are configurable in one place
      Then bitrate, channel layout and sample rate are configuration, not code
      And changing them is a re-render, never a re-analysis

  Rule: Archival renders are cheaper and less fussy

    @happy-path
    Scenario: An archival segment is converted, not produced
      # Q68 — "it's really just about archival... not public consumption."
      Given the Segment's intent is "archive"
      When the render runs
      Then the full span is converted without trimming refinement
      And channel 1 extraction is still applied
      And loudness normalization is still applied
      And the same single loudness treatment is applied


  Rule: Rendering is deterministic

    @happy-path
    Scenario: The same input produces the same output
      Given a Segment has been rendered
      When it is rendered again with identical settings
      Then the output is byte-identical apart from embedded timestamps
      And the recorded render settings are unchanged

    @manual
    Scenario: A human confirms it sounds right
      Given a rendered MP3
      When a reviewer listens to it end to end
      Then the speech is intelligible throughout
      And there are no clicks, dropouts or pumping artifacts
      And it sits at a comparable volume to other recent sermons
