@analysis @happy-path
Feature: Dividing a recording into blocks
  In order to describe what actually happens in a service
  As the Sermon Processor
  I want the recording divided wherever the speaker or the activity changes

  Blocks are the anatomy of a recording, not its published output. A block is a
  contiguous span attributed to one speaker doing one thing. Everything
  downstream — classification, summaries, Segment proposal — works from blocks.

  The division is driven by **speaker change**, not by silence. There are no
  long silences inside a service, and the one silence that does occur is a
  deliberate pause during the sermon's opening prayer, which must not split
  anything.

  Background:
    Given a Recording with a completed transcript and speaker spans

  Rule: Blocks are bounded by speaker changes

    @happy-path
    Scenario: A normal Sunday
      Given the speaker spans are:
        | start   | end     | speaker   |
        | 0:00:00 | 0:04:30 | Speaker 1 |
        | 0:04:30 | 0:26:10 | (music)   |
        | 0:26:10 | 0:29:55 | Speaker 2 |
        | 0:29:55 | 0:31:40 | Speaker 2 |
        | 0:31:40 | 1:16:20 | Speaker 3 |
        | 1:16:20 | 1:30:12 | Speaker 1 |
      When blocking runs
      Then a Block is produced for each contiguous speaker span
      And every Block has a start time, an end time and a speaker label
      And the Blocks cover the whole Recording with no gaps and no overlaps

    @happy-path
    Scenario: One speaker doing two things becomes two blocks
      Given Speaker 1 gives the announcements from "0:00:00" to "0:04:00"
      And Speaker 1 then prays from "0:04:00" to "0:04:30"
      When blocking runs
      Then 2 Blocks are produced, not 1
      And the split is justified by a change in activity rather than a change in voice
      # A speaker change is the primary signal, but not the only one — otherwise
      # the host who announces and then prays would be one undifferentiated block.

    @happy-path
    Scenario: A class and a service in one file
      Given the Recording is 3:12:00 long
      And it contains a 9:00 class followed by the 10:30 service
      When blocking runs
      Then Blocks are produced across the whole Recording
      And the class and the service are not treated as a special case
      And the boundary between them falls out of the ordinary speaker changes

  Rule: Silence does not drive the division

    @happy-path @measured
    Scenario: The prayer pause does not split a block
      # Confirmed: 15-20 seconds of deliberate silence during the prayer at the
      # start of the sermon, while people pray. Splitting there would cut the
      # sermon in half.
      Given the sermon contains 18 seconds of near-silence at "0:33:10"
      And the same speaker continues before and after it
      When blocking runs
      Then no Block boundary is created at "0:33:10"
      And the silence is recorded as a pause within the Block

    @happy-path
    Scenario: Silence is still recorded as evidence
      When blocking runs
      Then every silence gap longer than 2 seconds is recorded with its start and end
      And those gaps are available for snapping a boundary later

  Rule: Trivial blocks are merged away

    @edge-case @assumption
    Scenario Outline: Very short spans do not become blocks
      # A one-line interjection is not a section of the service.
      Given a speaker span lasting <length>
      When blocking runs
      Then it <outcome>

      Examples:
        | length  | outcome                                          |
        | 0:00:03 | is merged into the surrounding Block             |
        | 0:00:20 | is merged into the surrounding Block             |
        | 0:02:00 | becomes a Block of its own                       |

    @edge-case
    Scenario: A back-and-forth exchange
      Given two speakers alternate every few seconds for 6 minutes
      When blocking runs
      Then the exchange becomes one Block rather than dozens
      And the Block records that it contains multiple speakers
      # This is what a Q&A section looks like, and recognising it as one thing
      # is what lets the punch-out sit cleanly before it.

  Rule: Blocking degrades without speaker information

    @edge-case
    Scenario: Diarization was unavailable
      Given the diarization stage failed
      When blocking runs
      Then Blocks are produced from transcript structure and silence alone
      And each Block is marked as having no speaker attribution
      And downstream confidence is reduced

    @edge-case
    Scenario: The recording contains no speech at all
      Given the Recording is entirely music
      When blocking runs
      Then one Block covering the whole Recording is produced
      And it is marked as containing no speech
