@analysis @happy-path
Feature: Classifying each block
  In order for the reviewer to see the shape of a service at a glance
  As the Sermon Processor
  I want each Block labelled with what it is

  This is where the spoken cues live. Recognising "turn with me to Romans" makes
  a Block a scripture reading; recognising "are there any questions" makes a
  Block a Q&A. The boundary rules downstream are then simple, because they work
  on block types rather than re-scanning the transcript.

  Background:
    Given a Recording divided into Blocks with a completed transcript

  Rule: Every block gets a type and a confidence

    @happy-path
    Scenario Outline: The block types we recognise
      # Q73 — confirmed as sufficient for now.
      When block classification runs
      Then a Block may be typed "<type>" meaning "<meaning>"

      # The closed set. `special_service` used to appear here and does not
      # belong: a Good Friday service *contains* announcements, music, readings
      # and teaching Blocks. What is special is the service, not a span inside
      # it. It is a Recording kind — see features/README.md, "The three
      # vocabularies", which this table is the authority for.
      Examples:
        | type              | meaning                                                     |
        | announcements     | welcome, notices, housekeeping                              |
        | music             | congregational singing or instrumental                      |
        | prayer            | someone praying aloud; may contain long silence             |
        | scripture_reading | a passage being read, usually announced by reference        |
        | sermon            | the Sunday message                                          |
        | lesson            | a class session: teaching, usually followed by questions    |
        | seminar           | a session of a multi-part course                            |
        | communion         | the invitation to and serving of communion                  |
        | qa                | audience questions; short alternating turns                 |
        | rehearsal         | playing, stopping, restarting — a run-through, not a performance |
        | other             | speech that is none of the above                            |

    @happy-path
    Scenario Outline: Only teaching Blocks can seed a Segment
      # The three vocabularies are distinct and this is where they meet. A Block
      # type is not a Segment classification; only these three cross over.
      Then a Block typed "<type>" <seeds> a Segment

      Examples:
        | type              | seeds     |
        | sermon            | seeds     |
        | lesson            | seeds     |
        | seminar           | seeds     |
        | announcements     | never seeds |
        | music             | never seeds |
        | prayer            | never seeds |
        | scripture_reading | never seeds |
        | communion         | never seeds |
        | qa                | never seeds |
        | rehearsal         | never seeds |
        | other             | never seeds |

    @happy-path
    Scenario: Consecutive Blocks of one type are one Block for seeding
      # 2026-09-13: the classifier split the class at 0:01:43, typing both
      # halves `lesson` correctly, and seeding each produced a 1.7-minute
      # Segment from the first fragment. Runs are coalesced before seeding.
      Given two adjacent Blocks are both typed "lesson"
      When Segment proposal runs
      Then one Segment is seeded, not two
      And it spans both Blocks

    @happy-path
    Scenario: A whole service classified
      Given a Recording containing a normal Sunday service
      When block classification runs
      Then the Blocks are typed in order:
        | type              |
        | announcements     |
        | prayer            |
        | music             |
        | prayer            |
        | scripture_reading |
        | sermon            |
        | prayer            |
        | communion         |
        | music             |
        | prayer            |
      And each type carries a confidence derived from evidence, not self-reported
      # See analysis/analysis_confidence.feature for what derives it.
      And each carries the evidence that produced it

  Rule: Spoken cues drive classification

    @happy-path
    Scenario Outline: Scripture reading cues
      Given a Block contains "<phrase>"
      When block classification runs
      Then the Block is typed "scripture_reading"

      Examples:
        | phrase                                                  |
        | our scripture reading this morning is from             |
        | please turn with me in your bibles to                  |
        | hear now the word of the Lord from the gospel of John  |
        | this is the word of the Lord                           |
        | the reading this morning comes from the book of        |

    @happy-path
    Scenario Outline: Prayer cues
      Given a Block contains "<phrase>"
      When block classification runs
      Then the Block is typed "prayer"

      Examples:
        | phrase                  |
        | let us pray             |
        | would you pray with me  |
        | father, we thank you    |
        | in Jesus name, amen     |

    @happy-path
    Scenario Outline: Communion cues
      Given a Block contains "<phrase>"
      When block classification runs
      Then the Block is typed "communion"

      Examples:
        | phrase                                                          |
        | if you are a visitor with us we would like to invite you to join us |
        | as we come to the table this morning                            |
        | the elders will be coming forward to serve communion            |
        | we are going to take the Lord's supper together                 |

    @happy-path @measured
    Scenario Outline: Q&A cues
      # Confirmed: a class ends with prayer, then Q&A. The audience is not
      # mic'd, so the questions are hard to hear and are never published.
      Given a Block contains "<phrase>"
      When block classification runs
      Then the Block is typed "qa"

      Examples:
        | phrase                          |
        | alright, let us have some questions |
        | are there any questions          |
        | any questions before we go       |
        | what questions do you have       |

    @happy-path
    Scenario: A Q&A block is recognisable by shape as well as words
      Given a Block contains many short alternating contributions
      And some contributions are much quieter than others
      When block classification runs
      Then that shape counts as evidence for "qa"
      # The audience is unmic'd, so quiet interjections are the signature.

  Rule: Teaching blocks are identified by structure, not just words

    @happy-path
    Scenario: The sermon is the sustained monologue
      Given a Block is a single speaker talking for 44 minutes
      And it follows a scripture reading
      When block classification runs
      Then the Block is typed "sermon"
      And the evidence includes "sustained single-speaker teaching"
      And the evidence includes "follows a scripture reading"

    @happy-path
    Scenario: A known preacher raises confidence
      # Q12 — the roster is one primary preacher plus three or four others.
      Given the Block matches the voice profile of a known preacher
      When block classification runs
      Then the confidence that the Block is teaching is increased
      And the evidence names the matched speaker

    @happy-path @measured
    Scenario: Wall-clock time is evidence, not a rule
      # The service starts at 10:30 and the file is stamped around 10:29:52.
      # Occasionally there is a Saturday sermon, so the day is not a rule.
      Given a Block begins at "10:34 AM"
      When block classification runs
      Then starting shortly after the usual service time counts as evidence for "sermon"
      And a Block starting at another time is not excluded from being a sermon

    @happy-path
    Scenario: A class is distinguished from a sermon by what follows it
      Given a teaching Block is followed by a "prayer" Block and then a "qa" Block
      When block classification runs
      Then the teaching Block is typed "lesson" rather than "sermon"
      And the evidence records "followed by question and answer"

  Rule: The Sunday service has a known shape, used as a prior and nothing more

    @happy-path @measured
    Scenario: The expected Sunday running order
      # Q16 — the Sunday service is "very consistent from week to week". The
      # other recordings are "very, very sporadic", so this order is scored as
      # evidence, never required. A recording that does not match it is not
      # penalised; a recording that does match it gains confidence.
      Then the expected Sunday order is:
        | position | type              | notes                                          |
        | 1        | announcements     | welcome and notices                            |
        | 2        | prayer            | closes the announcements, pitches to worship   |
        | 3        | music             | usually three songs                            |
        | 4        | prayer            | prayer time, includes silence for the room     |
        | 5        | scripture_reading | the passage for the sermon                     |
        | 6        | sermon            | 50 to 60 minutes                               |
        | 7        | prayer            | closing prayer                                 |
        | 8        | communion         | about five minutes                             |
        | 9        | music             | one closing song                               |
        | 10       | prayer            | benediction                                    |

    @happy-path @measured
    Scenario: Matching the expected order raises confidence
      Given a Recording whose Blocks match the expected Sunday order
      When block classification runs
      Then each Block gains confidence from its position in the order
      And the evidence records "matches the expected Sunday order"

    @happy-path @measured
    Scenario: A recording that does not match is not penalised
      # Confirmed: "the other services are very, very sporadic... In general, on
      # those, it is just all spoken, so the punch-in and out points are usually
      # simpler because there is not a lot of other stuff going on."
      Given a Recording that is one speaker talking for 70 minutes with nothing else
      When block classification runs
      Then it is classified on its own evidence
      And no confidence is deducted for failing to match the Sunday order
      And the simpler structure makes the boundaries easier, not harder

    @happy-path @measured
    Scenario: The sermon follows the scripture reading directly
      # Confirmed: "After the scripture is read, the preacher of the sermon will
      # come up and start the sermon. That is the punch-in point."
      Given a scripture_reading Block is immediately followed by a new speaker
      When block classification runs
      Then that following Block is strong evidence for "sermon"
      And the punch-in falls at the start of it

    @happy-path @measured
    Scenario: The prayer time with silence comes before the scripture reading
      # Confirmed: the announcements speaker returns after the songs, pitches to
      # a prayer time with silence in it, and closes that time in prayer. The
      # scripture reading follows. That silence must not split anything.
      Given a prayer Block contains 20 seconds of silence
      And it is followed by a scripture_reading Block
      When block classification runs
      Then the silence does not create a Block boundary
      And the prayer Block is not mistaken for the sermon

    @happy-path @measured
    Scenario: One voice recurs throughout the service
      # Confirmed: the announcements, the return before the prayer time, the
      # scripture reading and usually the benediction are the same person.
      Given one speaker appears in the announcements, the prayer time and the benediction
      When block classification runs
      Then that recurrence is evidence that the speaker is hosting rather than preaching
      And a Block from that speaker is less likely to be typed "sermon"
      And this is evidence only, since the preacher occasionally gives the benediction

  Rule: Rehearsal is not the same thing as music in a service

    @happy-path @measured
    Scenario: A whole recording of rehearsal
      # Measured: rehearsal is the largest unpublished category in the bucket —
      # 8 of 20 sampled, 20 to 68 minutes, 63 to 76 dB dynamic range, in the same
      # room with the same voices as a service. It is the case most likely to
      # produce a false positive, and it is materially different from "there is
      # singing in this service".
      Given a Recording of a band running songs, stopping, and restarting them
      When block classification runs
      Then its Blocks are typed "rehearsal", not "music"
      And no Segment is proposed
      And the Recording is shown as needing no attention

    @happy-path @measured
    Scenario Outline: What distinguishes rehearsal from a service
      Given a Block containing "<signal>"
      When block classification runs
      Then that counts as evidence for "rehearsal"

      Examples:
        | signal                                          |
        | the same passage of a song sung more than once   |
        | talk about monitor levels or microphones        |
        | starting a song, stopping, and starting again   |
        | discussion of which songs to play               |

  Rule: Not every service is a Sunday service

    @happy-path @measured
    Scenario Outline: Services with a different shape
      # Measured: the bucket contains a Good Friday Tenebrae service — readings,
      # songs and explanations, a shape nothing like a Sunday — and a Saturday
      # gathering with worship, intercessory prayer, sermons and personal
      # testimony. Both previously classified as "other", which tells a reviewer
      # nothing about a recording they may well want to publish.
      # Two separate labels, and conflating them was the bug: the *Recording*
      # is the unusual thing, its teaching Blocks are ordinary teaching.
      Given a Recording that is "<event>"
      When block classification runs
      Then the Recording kind is "<kind>"
      And its teaching Blocks are typed "<block type>"
      And the Recording is summarised as "<event>" rather than as "other"

      Examples:
        | event                                    | kind            | block type |
        | a Good Friday service                    | special_service | sermon     |
        | a Saturday worship and prayer gathering  | special_service | sermon     |
        | a seminar day with several sessions      | special_service | seminar    |
        | an ordinary Sunday                       | service         | sermon     |
        | a members' meeting                       | meeting         | other      |
        | band practice, start to finish           | rehearsal       | rehearsal  |

    @happy-path
    Scenario: A special service still produces a reviewable Segment
      Given a Recording whose kind is "special_service"
      Then a Segment is proposed for each sustained teaching Block
      And the reviewer decides what to publish, as with any other Recording
      # The point of the type is that the reviewer is told what they are looking
      # at, not that the system treats it differently.

    @edge-case @measured
    Scenario: One event across several recordings
      # Good Friday produced four recordings across a day; a Saturday event
      # produced four more. Joining them is out of scope (Q65) — but the reviewer
      # still has to understand that they are parts of one thing.
      Given several Recordings on the same day within a few hours of each other
      And each contains part of what is evidently one event
      Then each is reviewed on its own
      And the interface shows them grouped by day
      And the reviewer is told they may be parts of one event

  Rule: The reviewer can always correct a block

    @happy-path
    Scenario: Retyping a block
      Given a Block was typed "other"
      When the reviewer retypes it as "sermon"
      Then the Block type is updated
      And Segment proposal runs again for the affected Blocks
      And any boundary the reviewer set by hand is preserved

    @edge-case @measured
    Scenario: Classification is unsure
      # This used to say "no type scores above the confidence floor", which
      # cannot work: the only per-type score available is the model's own
      # number, and that is a constant at 0.95 (see
      # analysis/analysis_confidence.feature). A floor on it would either fire
      # never or always.
      #
      # What actually indicates an unsure classification is the *absence of
      # corroborating evidence*, which is observable.
      Given a Block has none of the following:
        | corroboration                                        |
        | a cue phrase matching its type                       |
        | a position consistent with the expected running order |
        | a duration typical of its type                       |
        | a speaker distinct from the surrounding Blocks        |
      When block classification runs
      Then the Block keeps the type the classifier gave it
      And its classification confidence is "low"
      And it is flagged as needing the reviewer to look at it
      And the evidence states which corroboration was missing

    @edge-case
    Scenario: An unsure teaching Block still produces a Segment
      # The previous version retyped an unsure Block to "other", which would
      # silently destroy the Segment -- `other` does not seed. Flagging a
      # low-confidence sermon is useful; deleting it is not.
      Given a Block typed "sermon" with low classification confidence
      When Segment proposal runs
      Then a Segment is still seeded on it
      And it is shown as needing attention

    @edge-case
    Scenario: A block that is genuinely two things
      Given a Block contains a scripture reading that runs straight into teaching
      When block classification runs
      Then the Block is flagged as possibly containing more than one type
      And the reviewer can split it
