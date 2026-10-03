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
