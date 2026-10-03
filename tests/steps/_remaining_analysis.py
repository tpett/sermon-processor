"""Services laid out for the classification, confidence and summary scenarios, as the reasoning stage would see them."""

import re

from steps import _analysis, _web

from sermon.analysis import DividesIntoBlocks
from sermon.analysis.io import writes_json

LIST_ROW = r'<li data-row="recording" data-id="{id}"[^>]*>'
MEASURED_SELF_REPORT = 0.95
REHEARSAL_TALK = "one two three four from the top again stop stop can we get more vocals in the monitor and hold the last chord"
MEETING_TALK = "the next item on the agenda is the budget all in favour please raise your hand the motion carries"
TESTIMONY = "i want to share what the lord has done in my family this year and how he carried us through"
READING_INTO_TEACHING = (
    "hear the word of the lord from romans chapter eight there is therefore now no condemnation "
    "and this morning we will look at what the apostle means by that word condemnation"
)

EVENTS = {
    "a Good Friday service": (
        (0.0, 600.0, "scripture_reading"), (600.0, 1200.0, "music"), (1200.0, 1800.0, "scripture_reading"),
        (1800.0, 2400.0, "music"), (2400.0, 3600.0, "sermon"), (3600.0, 5412.0, "music"),
    ),
    "a Saturday worship and prayer gathering": (
        (0.0, 1200.0, "music"), (1200.0, 2400.0, "prayer"), (2400.0, 4200.0, "sermon"),
        (4200.0, 5412.0, "other", TESTIMONY),
    ),
    "a seminar day with several sessions": (
        (0.0, 2400.0, "seminar"), (2400.0, 2700.0, "other"), (2700.0, 5100.0, "seminar"), (5100.0, 5412.0, "other"),
    ),
    "an ordinary Sunday": tuple(_analysis.reads_rows(_analysis.SUNDAY)),
    "a members' meeting": ((0.0, 5412.0, "other", MEETING_TALK),),
    "band practice, start to finish": ((0.0, 5412.0, "music", REHEARSAL_TALK),),
}


def divides_each(spans):
    """The reasoning stage's answer, each span with the confidence it reported."""

    def divides(doc):
        return [
            {"start": float(start), "end": float(end), "type": kind, "confidence": confidence, "evidence": "speaker change"}
            for start, end, kind, confidence in spans
        ]

    return divides


def lays_out(store, spans, confidence=MEASURED_SELF_REPORT, confidences=None, transcript=None):
    """The transcript covers the spans and the reasoning stage has divided it; nothing is classified yet."""
    recording = _analysis.recording_of(store)
    _analysis.lays_out(store, recording, spans, typed=False)
    if transcript is not None:
        doc = _analysis.transcript_of(store, recording)
        transcript(doc)
        writes_json(store, recording, "transcript", doc)
    answered = [
        (start, end, kind, (confidences or {}).get(index, confidence))
        for index, (start, end, kind, *_) in enumerate(spans)
    ]
    DividesIntoBlocks(store=store, divides=divides_each(answered))(recording)
    return recording


def block_at(store, start):
    found = [block for block in _analysis.blocks_of(store) if block.start_seconds == start]
    assert len(found) == 1, f"{len(found)} Blocks start at {start}"
    return found[0]


def listed_row(store, recording):
    listed = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = re.search(LIST_ROW.format(id=recording.recording_id), listed)
    assert row, f"{recording.recording_id} is not on the recordings list"
    return row.group(0)


SERMON_SERVICE = (
    (0.0, 1570.0, "music"),
    (1570.0, 1900.0, "scripture_reading"),
    (1900.0, 4360.0, "sermon"),
    (4360.0, 4500.0, "prayer"),
    (4500.0, 4800.0, "communion"),
    (4800.0, 5412.0, "music"),
)
WITHOUT = {
    "scripture reading": {"scripture_reading": "music"},
    "communion cue": {"communion": "music"},
    "closing prayer": {"prayer": "music"},
    "block types": {kind: "other" for _, _, kind in SERMON_SERVICE},
}


def service_without(missing):
    """The ordinary sermon service, with the named evidence taken out of it."""
    replaced = WITHOUT.get(missing, {})
    return tuple((start, end, replaced.get(kind, kind)) for start, end, kind in SERMON_SERVICE)


CUE_INTO_BLOCK_S = 30.0
CUE_LENGTH_S = 6.0
SUMMARY = "the preacher opens Romans eight on condemnation"


def summarizes_with_a_cue(block, doc):
    """The summariser's answer: a summary, and an excerpt it chose from inside the block."""
    return SUMMARY, (block.start_seconds + CUE_INTO_BLOCK_S, block.start_seconds + CUE_INTO_BLOCK_S + CUE_LENGTH_S)


CUE_BUTTON = re.compile(r'data-role="preview-cue-excerpt" data-kind="cue" data-start="([^"]+)" data-end="([^"]+)"')
BLOCK_ROW = re.compile(r'<li data-row="block"(.*?)</li>', re.S)


def block_row_markup(page, block_type):
    rows = [row for row in BLOCK_ROW.findall(page) if f' data-block-type="{block_type}"' in row.split(">", 1)[0]]
    assert len(rows) == 1, f"{len(rows)} {block_type} Block rows are listed"
    return rows[0]
