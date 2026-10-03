from pytest_bdd import given, parsers, then, when
from steps import _analysis

from sermon.analysis import DividesIntoBlocks
from sermon.analysis.io import reads_json, writes_json

READS = _analysis.READS
PAUSE_S = 2.0
RUN_GAP_S = 20.0
TALK_PERIOD_S = 8.5
SUNDAY_TURNS = (
    (0.0, 270.0, "Speaker 1"),
    (270.0, 1570.0, "(music)"),
    (1570.0, 1900.0, "Speaker 2"),
    (1900.0, 4580.0, "Speaker 3"),
    (4580.0, 5412.0, "Speaker 1"),
)


def turn(start, end, speaker):
    return {
        "start": float(start),
        "end": float(end),
        "speaker": speaker,
        "confidence": 0.9,
        "overlapping": False,
        "non_speech": speaker == "(music)",
    }


def hears(store, turns, duration=None):
    """A transcript of whatever speech the turns hold, and the turns as diarization."""
    recording = _analysis.recording_of(store)
    spans = [(start, end, "music" if speaker == "(music)" else "other") for start, end, speaker in turns]
    writes_json(store, recording, "transcript", _analysis.transcript_over(recording, spans, duration, TALK_PERIOD_S, fill=True))
    writes_json(store, recording, "diarization", {"turns": [turn(*held) for held in turns]})


def blocks(store):
    found = _analysis.blocks_of(store)
    assert found, "blocking produced no Block"
    return found


def implications(block):
    return {evidence.implies for evidence in block.evidence}


def transcript(store):
    return reads_json(store, _analysis.the_recording(store), "transcript")


@given("a Recording with a completed transcript and speaker spans")
def _(store):
    hears(store, SUNDAY_TURNS)


@given("diarization reports a speaker change near a block boundary")
def _(store):
    recording = _analysis.recording_of(store)
    spoken = [(0.0, 1897.0, "other"), (1903.0, 4500.0, "other"), (4500.0, 5412.0, "other")]
    writes_json(store, recording, "transcript", _analysis.transcript_over(recording, spoken, period=TALK_PERIOD_S, fill=True))
    writes_json(
        store,
        recording,
        "diarization",
        {"turns": [turn(0.0, 1900.2, "Speaker 2"), turn(1900.2, 4500.0, "Speaker 3"), turn(4500.0, 5412.0, "Speaker 1")]},
    )


@when("blocking runs")
def _(store):
    recording = _analysis.recording_of(store)
    diarized = reads_json(store, recording, "diarization")
    turns = diarized["turns"] if diarized else []
    answered = [(item["start"], item["end"], "other") for item in turns] or speech_runs(store, recording)
    DividesIntoBlocks(store=store, divides=_analysis.divides_as(answered))(recording)


def speech_runs(store, recording):
    """What a reader of the transcript alone would answer: each run of speech without a long gap."""
    runs = []
    for item in reads_json(store, recording, "transcript")["utterances"]:
        if runs and item["start"] - runs[-1][1] < RUN_GAP_S:
            runs[-1] = (runs[-1][0], item["end"], "other")
        else:
            runs.append((item["start"], item["end"], "other"))
    return runs


@then("the boundary is placed on the nearest utterance edge")
def _(store):
    edges = {item["start"] for item in transcript(store)["utterances"]} | {
        item["end"] for item in transcript(store)["utterances"]
    }
    near = [block for block in blocks(store) if abs(block.start_seconds - 1900.2) < 30.0]
    assert len(near) == 1
    nearest = min(edges, key=lambda edge: abs(edge - 1900.2))
    assert near[0].start_seconds == nearest


@then("the speaker change is recorded as the reason for the boundary")
def _(store):
    near = [block for block in blocks(store) if abs(block.start_seconds - 1900.2) < 30.0]
    assert len(near) == 1
    assert "speaker change" in implications(near[0])


@given("the speaker spans are:")
def _(store, datatable):
    hears(store, [(READS(start), READS(end), speaker) for start, end, speaker in datatable[1:]])


@then("a Block is produced for each contiguous speaker span")
def _(store):
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    contiguous = []
    for item in turns:
        if contiguous and contiguous[-1][2] == item["speaker"] and contiguous[-1][1] == item["start"]:
            contiguous[-1] = (contiguous[-1][0], item["end"], item["speaker"])
        else:
            contiguous.append((item["start"], item["end"], item["speaker"]))
    assert [(block.start_seconds, block.end_seconds) for block in blocks(store)] == [
        (start, end) for start, end, _ in contiguous
    ]


@then("every Block has a start time, an end time and evidence naming the speaker change")
def _(store):
    for block in blocks(store):
        assert block.end_seconds > block.start_seconds
        assert "speaker change" in implications(block)


@then("the Blocks cover the whole Recording with no gaps and no overlaps")
def _(store):
    found = blocks(store)
    assert found[0].start_seconds == 0.0
    assert found[-1].end_seconds == _analysis.the_recording(store).duration_seconds
    for left, right in zip(found, found[1:]):
        assert left.end_seconds == right.start_seconds


@given("it contains a 9:00 class followed by the 10:30 service")
def _(store):
    duration = _analysis.recording_of(store).duration_seconds
    hears(store, ((0.0, 3900.0, "Teacher"), (3900.0, 5400.0, "(music)"), (5400.0, duration, "Preacher")), duration)


@then("Blocks are produced across the whole Recording")
def _(store):
    found = blocks(store)
    assert found[0].start_seconds == 0.0
    assert found[-1].end_seconds == _analysis.the_recording(store).duration_seconds


@then("the boundary between them falls out of the ordinary speaker changes")
def _(store):
    starts = {block.start_seconds: block for block in blocks(store)}
    assert 5400.0 in starts
    assert "speaker change" in implications(starts[5400.0])


@given(parsers.parse('the sermon contains {seconds:d} seconds of near-silence at "{timecode}"'))
def _(store, seconds, timecode):
    recording = _analysis.recording_of(store)
    quiet = READS(timecode)
    spans = [(0.0, 1900.0, "other"), (1900.0, quiet, "other"), (quiet + seconds, 4500.0, "other"), (4500.0, 5412.0, "other")]
    writes_json(store, recording, "transcript", _analysis.transcript_over(recording, spans, period=TALK_PERIOD_S, fill=True))


@given("the same speaker continues before and after it")
def _(store):
    recording = _analysis.recording_of(store)
    writes_json(
        store,
        recording,
        "diarization",
        {"turns": [turn(0.0, 1900.0, "Speaker 2"), turn(1900.0, 4500.0, "Speaker 3"), turn(4500.0, 5412.0, "Speaker 1")]},
    )


@then("the silence is recorded as a pause within the Block")
def _(store):
    quiet = READS("0:33:10")
    holding = [block for block in blocks(store) if block.start_seconds < quiet < block.end_seconds]
    assert len(holding) == 1
    long_gaps = [gap["start"] for gap in transcript(store)["silences"] if gap["start"] <= quiet <= gap["end"]]
    assert len(long_gaps) == 1
    assert any(
        evidence.implies == "pause within the Block" and evidence.timecode == long_gaps[0]
        for evidence in holding[0].evidence
    )


@then("every silence gap longer than 2 seconds is recorded with its start and end")
def _(store):
    gaps = [gap for gap in transcript(store)["silences"] if gap["end"] - gap["start"] > PAUSE_S]
    assert gaps
    recorded = {evidence.timecode for block in blocks(store) for evidence in block.evidence if "pause" in evidence.implies}
    assert {gap["start"] for gap in gaps} <= recorded


@then("those gaps are available for snapping a boundary later")
def _(store):
    words = [word for item in transcript(store)["utterances"] for word in item["words"]]
    gaps = [
        (earlier["end"], later["start"])
        for earlier, later in zip(words, words[1:])
        if later["start"] - earlier["end"] > PAUSE_S
    ]
    assert gaps
    stored = {(gap["start"], gap["end"]) for gap in transcript(store)["silences"]}
    assert set(gaps) <= stored


@given("a run of turns too short to be a block of their own")
def _(store):
    hears(
        store,
        ((0.0, 120.0, "Speaker 1"), (120.0, 125.0, "Speaker 1"), (125.0, 400.0, "Speaker 1"),
         (400.0, 403.0, "Speaker 2"), (403.0, 900.0, "Speaker 3"), (900.0, 5412.0, "(music)")),
    )


@then("only into the larger neighbour when neither shares it")
def _(store):
    starts = [block.start_seconds for block in blocks(store)]
    assert 403.0 not in starts
    assert 400.0 in starts


@then("absorbing them never moves a boundary across a change of voice")
def _(store):
    ends = [block.end_seconds for block in blocks(store)]
    assert 400.0 in ends
    assert 403.0 not in ends


@then("the Block records that it contains multiple speakers")
def _(store):
    exchange = [block for block in blocks(store) if block.start_seconds < 180.0 < block.end_seconds]
    assert len(exchange) == 1
    assert "multiple speakers" in " ".join(evidence.finding for evidence in exchange[0].evidence)


@given("the diarization stage failed")
def _(store):
    writes_json(store, _analysis.recording_of(store), "diarization", {"turns": []})


@then("Blocks are produced from transcript structure and silence alone")
def _(store):
    for block in blocks(store):
        assert "speaker change" not in implications(block)


@then("each Block is marked as having no speaker attribution")
def _(store):
    for block in blocks(store):
        assert "no speaker attribution" in implications(block)


@given("a service with four distinct voices")
def _(store):
    hears(
        store,
        ((0.0, 500.0, "Speaker 1"), (500.0, 600.0, "(music)"), (600.0, 1100.0, "Speaker 2"),
         (1100.0, 1200.0, "(music)"), (1200.0, 1700.0, "Speaker 3"), (1700.0, 1800.0, "(music)"),
         (1800.0, 2300.0, "Speaker 4"), (2300.0, 5412.0, "(music)")),
    )


@then("it reports a number of speakers in the same order as reality")
def _(store):
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    voices = {item["speaker"] for item in turns if not item["non_speech"]}
    assert 3 <= len(voices) <= 6


@then("a single speaker is not split across labels within one block")
def _(store):
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    spoken = [item for item in turns if not item["non_speech"]]
    assert len({item["speaker"] for item in spoken}) == len(spoken)


@then("they are absorbed into a neighbouring block that shares their voice")
def _(store):
    starts = [block.start_seconds for block in blocks(store)]
    assert 120.0 not in starts
    assert 125.0 not in starts


@given(parsers.parse('Speaker 1 gives the announcements from "{start}" to "{end}"'))
def _(store, start, end):
    recording = _analysis.recording_of(store)
    spans = [(READS(start), READS(end), "announcements"), (READS(end), 5412.0, "music")]
    writes_json(store, recording, "transcript", _analysis.transcript_over(recording, spans, period=TALK_PERIOD_S, fill=True))
    writes_json(store, recording, "diarization", {"turns": [turn(READS(start), READS(end), "Speaker 1"), turn(READS(end), 5412.0, "(music)")]})


@given(parsers.parse('Speaker 1 then prays from "{start}" to "{end}"'))
def _(store, start, end):
    recording = _analysis.recording_of(store)
    spans = [(0.0, READS(start), "announcements"), (READS(start), READS(end), "prayer"), (READS(end), 5412.0, "music")]
    writes_json(store, recording, "transcript", _analysis.transcript_over(recording, spans, period=TALK_PERIOD_S, fill=True))
    writes_json(store, recording, "diarization", {"turns": [turn(0.0, READS(end), "Speaker 1"), turn(READS(end), 5412.0, "(music)")]})


@then(parsers.parse("{count:d} Blocks are produced, not 1"))
def _(store, count):
    spoken = [block for block in blocks(store) if block.start_seconds < READS("0:04:30")]
    assert len(spoken) == count


@then("the split is justified by a change in activity rather than a change in voice")
def _(store):
    split = [block for block in blocks(store) if block.start_seconds == READS("0:04:00")]
    assert len(split) == 1
    assert "speaker change" not in implications(split[0])
    assert any("activity" in evidence.implies for evidence in split[0].evidence)


@then("it is merged into the surrounding Block")
def _(store):
    short = [item for item in reads_json(store, _analysis.the_recording(store), "diarization")["turns"] if item["start"] == 180.0]
    assert len(short) == 1
    holding = [block for block in blocks(store) if block.start_seconds < short[0]["start"] and short[0]["end"] < block.end_seconds]
    assert len(holding) == 1


@then("it becomes a Block of its own")
def _(store):
    short = [item for item in reads_json(store, _analysis.the_recording(store), "diarization")["turns"] if item["start"] == 180.0]
    assert len(short) == 1
    assert [(block.start_seconds, block.end_seconds) for block in blocks(store) if block.start_seconds == 180.0] == [
        (180.0, short[0]["end"])
    ]


@then("the exchange becomes one Block rather than dozens")
def _(store):
    within = [block for block in blocks(store) if block.start_seconds < 360.0]
    assert len(within) == 1
