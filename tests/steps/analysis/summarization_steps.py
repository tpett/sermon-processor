import re

from pytest_bdd import given, parsers, then
from steps import _analysis, _web

from sermon.analysis import SummarizesBlocks
from sermon.analysis.io import reads_json
from sermon.pipeline import classify
from sermon.store import Block, LogEntry, Segment

GLANCE_CHARACTERS = 120
CUE_SHORTEST_S = 3.0
CUE_LONGEST_S = 10.0
HEBREWS_SERMON = "turn with me to hebrews chapter 12 where the writer speaks of discipline"
UNLOCATABLE = "nothing like this phrase was ever said in the service"
UNANNOUNCED_READING = "please stand for the reading of gods holy word"


def spoken_blocks(store):
    spoken = [block for block in _analysis.blocks_of(store) if block.type != "music"]
    assert spoken, "the Recording holds no spoken Block"
    return spoken


def words_of(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    return [word for utterance in doc["utterances"] for word in utterance.get("words", ())]


def words_in(store, block):
    return [word for word in words_of(store) if block.start_seconds <= word["start"] < block.end_seconds]


def prompts_for(block):
    return [
        prompt
        for prompt in classify.call_json.prompts
        if f"Block runs from {classify.hms(block.start_seconds)} to {classify.hms(block.end_seconds)}" in prompt
    ]


def quoted_words(store, block):
    prompts = prompts_for(block)
    assert len(prompts) == 1, f"the {block.type} Block was put to the model {len(prompts)} times"
    wanted = _analysis.quoted_by(prompts[0]).split()
    spoken = words_in(store, block)
    for start in range(len(spoken) - len(wanted) + 1):
        if [word["w"] for word in spoken[start : start + len(wanted)]] == wanted:
            return spoken[start : start + len(wanted)]
    raise AssertionError(f"the quote {wanted} is not in the {block.type} Block's transcript")


@then("each spoken Block carries a one-line summary, for example:")
def _(store, datatable):
    spoken = spoken_blocks(store)
    for kind, _ in datatable[1:]:
        assert any(block.type == kind and block.summary for block in spoken), f"no summarised {kind} Block"
    for block in spoken:
        assert block.summary
        assert "\n" not in block.summary


@then("each summary is short enough to read at a glance")
def _(store):
    spoken = spoken_blocks(store)
    assert spoken
    for block in spoken:
        assert block.summary
        assert len(block.summary) <= GLANCE_CHARACTERS


@given(parsers.parse('a Block typed "{block_type}" with no speech'))
def _(store, block_type):
    recording = _analysis.recording_of(store)
    spans = [(start, end, kind) for start, end, kind in _analysis.reads_rows(_analysis.SUNDAY)]
    spans = [(start, end, block_type if kind == "music" else kind) for start, end, kind in spans]
    _analysis.lays_out(store, recording, [(start, end, kind, "" if kind == block_type else _analysis.SPOKEN[kind]) for start, end, kind in spans])


@then("no summary is attempted for it")
def _(store):
    silent = [block for block in _analysis.blocks_of(store) if block.type == "music"]
    assert silent
    for block in silent:
        assert not words_in(store, block)
        assert prompts_for(block) == []
        assert block.summary is None


@then("it is labelled by its type alone")
def _(store):
    page = _web.opens_detail(store, _analysis.the_recording(store).recording_id)
    rows = re.findall(r'<li data-row="block" data-block-type="music".*?</li>', page, flags=re.S)
    assert rows
    for row in rows:
        assert '<span data-field="block-type">music</span>' in row
        assert '<span data-field="block-summary"></span>' in row


@given(parsers.parse('a Segment classified "{classification}" whose transcript references Hebrews 12'))
def _(store, classification):
    recording = _analysis.recording_of(store)
    spoken = {"sermon": HEBREWS_SERMON, "scripture_reading": UNANNOUNCED_READING}
    spans = [
        (start, end, kind, spoken[kind]) if kind in spoken else (start, end, kind)
        for start, end, kind in _analysis.reads_rows(_analysis.SUNDAY)
    ]
    _analysis.lays_out(store, recording, spans)
    sermon = [block for block in _analysis.blocks_of(store) if block.type == "sermon"][0]
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            seed_block_id=sermon.block_id,
            classification=classification,
            state="proposed",
            span_start_seconds=sermon.start_seconds,
            span_end_seconds=sermon.end_seconds,
            punch_in_seconds=sermon.start_seconds,
            punch_out_seconds=sermon.end_seconds,
            boundary_source="model",
        )
    )


@then('"Hebrews 12" is suggested as the publication label')
def _(store):
    segments = store.lists(Segment)
    assert len(segments) == 1
    assert segments[0].label and "Hebrews 12" in segments[0].label


@then("the reviewer can correct it")
def _(store):
    segment = store.lists(Segment)[0]
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert f'name="label" value="{segment.label}"' in page


@then("each proposed Segment carries its own summary")
def _(store):
    segments = store.lists(Segment)
    assert segments, "no Segment was proposed for the summary to belong to"
    for segment in segments:
        assert segment.summary


@then("the summary is shown beside it in the review interface")
def _(store):
    segments = store.lists(Segment)
    assert segments, "no Segment was proposed for the summary to belong to"
    for segment in segments:
        assert segment.summary
        page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
        assert segment.summary in page


@then("the model returns the exact words of the recognisable moment")
def _(store):
    for block in spoken_blocks(store):
        prompts = prompts_for(block)
        assert len(prompts) == 1
        assert "cue_quote" in prompts[0] and "verbatim" in prompts[0]


@then("those words are located in the word-level transcript")
def _(store):
    for block in spoken_blocks(store):
        quoted = quoted_words(store, block)
        assert block.cue_start_seconds == quoted[0]["start"]
        assert block.cue_end_seconds == quoted[-1]["end"]


@then("the excerpt's timing comes from the transcript, never from the model")
def _(store):
    edges = {word["start"] for word in words_of(store)} | {word["end"] for word in words_of(store)}
    for block in spoken_blocks(store):
        assert block.cue_start_seconds in edges and block.cue_end_seconds in edges
        assert block.cue_start_seconds != block.start_seconds


@given("the returned words do not appear in the transcript")
def _(store, monkeypatch):
    monkeypatch.setattr(classify, "call_json", _analysis.AnswersLikeAModel(quotes=UNLOCATABLE))
    SummarizesBlocks(store=store)(_analysis.recording_of(store))


@then("no cue excerpt is stored for that Block")
def _(store):
    for block in spoken_blocks(store):
        assert block.cue_start_seconds is None and block.cue_end_seconds is None


@then("the Block falls back to its first few seconds")
def _(store):
    for block in spoken_blocks(store):
        assert block.cue_start_seconds == block.start_seconds
        assert block.cue_end_seconds <= block.start_seconds + CUE_LONGEST_S


@then("the failure is counted, so a model that drifts is visible")
def _(store):
    recording = _analysis.the_recording(store)
    entries = [entry for entry in store.lists(LogEntry, recording_id=recording.recording_id) if "quote" in entry.kind]
    assert len(entries) == len(spoken_blocks(store))


@then("each spoken Block carries a cue excerpt with a start and end time")
def _(store):
    for block in spoken_blocks(store):
        assert block.cue_start_seconds is not None and block.cue_end_seconds is not None
        assert block.start_seconds <= block.cue_start_seconds < block.cue_end_seconds <= block.end_seconds


@then("the excerpt is between 3 and 10 seconds long")
def _(store):
    for block in spoken_blocks(store):
        assert CUE_SHORTEST_S <= block.cue_end_seconds - block.cue_start_seconds <= CUE_LONGEST_S


@then("it is chosen to be immediately recognisable rather than simply the first words")
def _(store):
    for block in spoken_blocks(store):
        quoted = quoted_words(store, block)
        first = words_in(store, block)[0]
        assert block.cue_start_seconds == quoted[0]["start"] != first["start"]


@then("no cue excerpt begins or ends inside a silence")
def _(store):
    for block in spoken_blocks(store):
        spoken = words_in(store, block)
        for moment in (block.cue_start_seconds, block.cue_end_seconds):
            assert any(word["start"] <= moment <= word["end"] for word in spoken), f"{moment} is in a silence"


@then("no cue excerpt is chosen from a span with no speech")
def _(store):
    for block in spoken_blocks(store):
        assert any(
            block.cue_start_seconds <= word["start"] and word["end"] <= block.cue_end_seconds
            for word in words_in(store, block)
        )
