@analysis
Feature: Probing a recording's technical metadata
  In order to show operators what they are working with
  As the Sermon Processor
  I want to read the technical properties of every recording

  The expected values here are measured from 24 real recordings, not assumed.

  Background:
    Given a Recording in state "downloaded"

  Rule: Technical metadata is extracted from the audio itself

    @happy-path @measured
    Scenario: Probing a normal Sunday recording
      Given the FLAC is 1:44:29 long, 44100 Hz, stereo, 24-bit
      When the probe stage runs
      Then the Recording records:
        | field            | value      |
        | duration         | 6268.950   |
        | sample_rate      | 44100      |
        | channels         | 2          |
        | bit_depth        | 24         |
        | codec            | flac       |
        | file_size_bytes  | 841368564  |
      And the values are shown on the Recording detail view

    @happy-path @measured
    Scenario: The dead channel is detected
      # Every sample recording carries signal on channel 1 only; channel 2 sits
      # at the -90 dB noise floor. A mono source into a stereo recorder.
      Given channel 1 measures -21.3 dB RMS
      And channel 2 measures -90.4 dB RMS
      When the probe stage runs
      Then the Recording records a per-channel RMS level
      And channel 2 is identified as silent
      And the Recording records that the render should use channel 1 only

    @edge-case
    Scenario: Both channels carry signal
      Given channel 1 measures -21.3 dB RMS
      And channel 2 measures -23.8 dB RMS
      When the probe stage runs
      Then neither channel is identified as silent
      And the Recording is flagged "unexpected stereo content"
      And the reviewer is asked to confirm how it should be mixed to mono
      # This has never happened in the samples, but a changed cable or an
      # altered recorder config would produce it, and a silent guess is worse
      # than a question.

    @happy-path @measured
    Scenario: Loudness is measured for later normalization
      When the probe stage runs
      Then the Recording records an integrated loudness in LUFS
      And a true peak in dBTP
      And a loudness range in LU
      And these values are used as inputs to the render stage

    @happy-path @measured
    Scenario: Clipping in the source is detected and reported
      # Sources measure 0.0 to 0.9 dBFS true peak with samples pinned at full
      # scale. Known hardware gain-staging issue, being fixed at the A2D unit.
      # Nothing downstream can undo it, so the system reports rather than repairs.
      Given the source true peak is "0.4 dBFS"
      And 112 samples in a 120 second window sit at absolute full scale
      When the probe stage runs
      Then the Recording is flagged "source clipping detected"
      And the flag is visible on the Recording detail view
      And Analysis continues normally
      And no attempt is made to repair the clipping

    @edge-case
    Scenario: The sidecar disagrees with the audio
      Given the sidecar metadata claims a duration of 5000.0 seconds
      And the audio decodes to 6268.950 seconds
      When the probe stage runs
      Then the probed duration wins
      And the discrepancy is recorded as a warning on the Recording

    @edge-case @measured
    Scenario Outline: Recordings outside the observed range are flagged
      # Observed source durations across 24 recordings: 79 to 155 minutes.
      Given the FLAC is <duration> long
      When the probe stage runs
      Then the Recording is flagged "<flag>"

      Examples:
        | duration | flag                        |
        | 0:00:45  | suspiciously short          |
        | 0:12:00  | suspiciously short          |
        | 4:30:00  | suspiciously long           |

  Rule: Recordings with no substance are recognised and set aside

    @happy-path @measured
    Scenario: A single pop triggers a ten minute recording
      # Q36 — confirmed: "a single noise, like a pop from somebody turning the
      # system on or off, might trigger a recording that is 10 minutes long...
      # the substance of the recording will just be a single noise and almost
      # entirely silence."
      #
      # This is a content test, not a duration test. The recorder's own silence
      # timeout decides the length, so length says nothing useful.
      Given the FLAC is 10 minutes long
      And it contains one transient followed by near-silence
      And less than 1% of it is above the noise floor
      When the probe stage runs
      Then the Recording is flagged "no substantive content"
      And Analysis stops after the probe stage
      And the Recording is marked as ignored without a human being asked

    @happy-path
    Scenario: Ignored recordings stay out of the way but remain visible
      Given a Recording marked ignored
      Then it does not appear in the default list
      And it does not count as needing attention
      And no notification is sent
      And a reviewer can find it by filtering for ignored recordings
      And a reviewer can restore it for analysis if the machine was wrong

    @happy-path @assumption
    Scenario Outline: What counts as substantive
      # Q78 — the threshold is a guess. The sample corpus has no examples of
      # this, so it is worth checking against a few real false triggers.
      Given <proportion> of the Recording is above the noise floor
      When the probe stage runs
      Then the Recording is <outcome>

      Examples:
        | proportion | outcome                            |
        | 0.2%       | flagged "no substantive content"   |
        | 1%         | flagged "no substantive content"   |
        | 15%        | analysed normally                  |
        | 60%        | analysed normally                  |

    @edge-case
    Scenario: A quiet but real recording is not discarded
      Given a Recording of a sparsely attended meeting with long pauses
      And 20% of it is above the noise floor
      When the probe stage runs
      Then it is analysed normally
      # The test is for near-empty files, not for quiet ones. Erring toward
      # analysing costs a little local compute; erring the other way loses a
      # recording silently.

    @edge-case
    Scenario: The recording is silent throughout
      Given the FLAC contains only digital silence
      When the probe stage runs
      Then the Recording is flagged "no audio content"
      And Analysis stops after the probe stage
      And the Recording enters "analysis_failed" with reason "no audio content"
