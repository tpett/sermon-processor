import re
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis, _web
from steps._markup import reads_rows, strips_tags
from steps._remaining_analysis import divides_each

from sermon.analysis import DividesIntoBlocks
from sermon.analysis.titles_recording import TitlesRecording
from sermon.config import ModelEndpointUnreachable
from sermon.jobs.analyzes_recording import OPTIONAL_STAGE_FAILED
from sermon.lists_recordings import formats_recorded_at
from sermon.names_stored_recordings import NamesStoredRecordings
from sermon.pipeline import classify
from sermon.store import Artifact, LogEntry, Recording, RecordingTitle, Segment

NAMING = "You are naming one audio recording"
SUNDAY_CLASS = "recording_20260913_090014"
REHEARSAL = "recording_20260913_081500"
READINGS = {
    "Hebrews 12.25-29": "please stand for the reading of gods word from hebrews chapter 12 verses 25 to 29",
}
CLASS_THEN_SERMON = (
    (0.0, 60.0, "music"),
    (60.0, 3300.0, "lesson"),
    (3300.0, 5400.0, "music"),
    (5400.0, 5700.0, "scripture_reading"),
    (5700.0, 9300.0, "sermon"),
    (9300.0, 11520.0, "music"),
)
SHOWN_NO_DATE = ("2026", "09-13", "13 Sep", "September", "Sep 13")
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S)


class NamesLikeAModel:
    """Answers the naming prompt as told and passes every other prompt to the double it replaced."""

    def __init__(self, answer, otherwise):
        self.answer = answer
        self.otherwise = otherwise
        self.shown = []

    def __call__(self, model, prompt, think=False):
        if NAMING not in prompt:
            return self.otherwise(model, prompt, think)
        self.shown.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return dict(self.answer), 0


def the_class_recording(store):
    return store.loads(Recording, SUNDAY_CLASS)


def segment_classified(store, classification):
    found = [one for one in store.lists(Segment, recording_id=SUNDAY_CLASS) if one.classification == classification]
    assert len(found) == 1, f"{len(found)} {classification} Segments"
    return found[0]


def row_for(page, recording_id):
    rows = [row for row in reads_rows(page, "recording") if row.get("id") == recording_id]
    assert rows, f"{recording_id} is not on the list"
    return rows[0]


def heading_of(page):
    found = H1.search(page)
    assert found, "the page has no heading"
    return strips_tags(found.group(1))


def answered(kind, title, series=None, topic=None):
    return {"kind": kind, "title": title, "series": series or None, "topic": topic or None}


def named_by_analysis(store, recording, answer):
    return TitlesRecording(store=store, asks=lambda _prompt: answer)(recording)


@given(parsers.parse('a Recording started on a Sunday at 09:00 holding a class and then a sermon on "{passage}"'))
def _(store, passage):
    recording = store.saves(
        Recording(
            recording_id=SUNDAY_CLASS,
            object_key=f"recordings/{SUNDAY_CLASS}.flac",
            state="downloaded",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )
    spans = [
        (start, end, kind, READINGS[passage]) if kind == "scripture_reading" else (start, end, kind)
        for start, end, kind in CLASS_THEN_SERMON
    ]
    _analysis.lays_out(store, recording, spans, typed=False)
    DividesIntoBlocks(store=store, divides=divides_each([(*span[:3], 0.9) for span in spans]))(recording)


@given(
    parsers.re(
        r'the model will name it kind "(?P<kind>[^"]*)", title "(?P<title>[^"]*)", '
        r'series "(?P<series>[^"]*)" and topic "(?P<topic>[^"]*)"'
    ),
    target_fixture="naming",
)
def _(monkeypatch, kind, title, series, topic):
    double = NamesLikeAModel(answered(kind, title, series, topic), classify.call_json)
    monkeypatch.setattr(classify, "call_json", double)
    return double


@given(parsers.parse('the model will name it kind "{kind}" and title "{title}"'), target_fixture="naming")
def _(monkeypatch, kind, title):
    double = NamesLikeAModel(answered(kind, title), classify.call_json)
    monkeypatch.setattr(classify, "call_json", double)
    return double


@given("the model cannot be reached when the recording is named", target_fixture="naming")
def _(monkeypatch):
    double = NamesLikeAModel(ModelEndpointUnreachable("http://mac-m1:11434"), classify.call_json)
    monkeypatch.setattr(classify, "call_json", double)
    return double


@given(parsers.parse('the class was approved with the label "{label}"'))
def _(store, label):
    _analysis.proposes(store, the_class_recording(store))
    lesson = segment_classified(store, "lesson")
    _web.posts(store, _web.segment_action(lesson, "approve"), intent="publish", label=label)
    assert segment_classified(store, "lesson").state == "approved"


@given(parsers.parse('analysis named the Recording "{title}" as a "{kind}" in the series "{series}"'))
def _(store, title, kind, series):
    named_by_analysis(store, the_class_recording(store), answered(kind, title, series))


@given(parsers.re(r'analysis named the Recording "(?P<title>[^"]+)" as a "(?P<kind>[^"]+)"'))
def _(store, title, kind):
    named_by_analysis(store, the_class_recording(store), answered(kind, title))


@given(parsers.parse('another Recording that analysis named "{title}" as a "{kind}"'))
def _(store, title, kind):
    recording = store.saves(
        Recording(
            recording_id=REHEARSAL,
            object_key=f"recordings/{REHEARSAL}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 8, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=2400.0,
        )
    )
    named_by_analysis(store, recording, answered(kind, title))


@given(parsers.parse('I renamed the Recording "{title}"'))
def _(store, title):
    _web.posts(store, _web.recording_action(the_class_recording(store), "retitle"), title=title)
    held = store.loads(RecordingTitle, SUNDAY_CLASS)
    assert held is not None and held.title == title, f"the Recording is titled {held}"


@given("the Recording was analysed before recordings were named and its audio is not on this machine")
def _(store):
    recording = the_class_recording(store)
    _analysis.proposes(store, recording)
    for artifact in store.lists(Artifact, recording_id=recording.recording_id):
        store.forgets(artifact)
    assert store.loads(Recording, SUNDAY_CLASS).local_path is None


@when(parsers.re(r'I rename it "(?P<title>[^"]*)" on its detail page'), target_fixture="renamed_page")
def _(store, title):
    return _web.posts(store, _web.recording_action(the_class_recording(store), "retitle"), title=title)


@when(parsers.parse('I filter the list by the kind "{kind}"'), target_fixture="list_page")
def _(store, kind):
    return _web.opens_app(store).test_client().get("/", query_string={"kind": kind}).get_data(as_text=True)


@when("the naming backfill runs as a dry run", target_fixture="printed")
def _(store):
    printed = []
    NamesStoredRecordings(store=store, prints=printed.append, dry_run=True)()
    return printed


@when("the naming backfill runs", target_fixture="printed")
def _(store):
    printed = []
    NamesStoredRecordings(store=store, prints=printed.append)()
    return printed


@then(parsers.parse('the Recording is titled "{title}"'))
def _(store, title):
    held = store.loads(RecordingTitle, SUNDAY_CLASS)
    assert held is not None, "the Recording has no title"
    assert held.title == title


@then(parsers.parse('the model was shown "{when}" and the passage "{passage}"'))
def _(naming, when, passage):
    assert naming.shown, "the model was never asked to name the Recording"
    assert when in naming.shown[-1]
    assert passage in naming.shown[-1]


@then("the model was shown no audio and no date")
def _(naming):
    assert naming.shown, "the model was never asked to name the Recording"
    for prompt in naming.shown:
        assert isinstance(prompt, str)
        assert "fLaC" not in prompt and "RIFF" not in prompt
        assert [mark for mark in SHOWN_NO_DATE if mark in prompt] == []


@then("the Recording is awaiting review with its Segments proposed")
def _(store):
    assert the_class_recording(store).state == "awaiting_review"
    assert {one.classification for one in store.lists(Segment, recording_id=SUNDAY_CLASS)} == {"lesson", "sermon"}


@then("the Recording has no title")
def _(store):
    assert store.loads(RecordingTitle, SUNDAY_CLASS) is None


@then("the failure to name it is in the processing log")
def _(store):
    failed = [entry.error for entry in store.lists(LogEntry, recording_id=SUNDAY_CLASS, kind=OPTIONAL_STAGE_FAILED)]
    assert [error for error in failed if error.startswith("titling: ")], failed


@then(parsers.parse('its row on the recordings list shows the title "{title}" beside the date and time'))
def _(store, title):
    page = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    row = row_for(page, SUNDAY_CLASS)
    assert row.get("title") == title
    assert row.get("recorded-at") == formats_recorded_at(the_class_recording(store).started_at)


@then(parsers.parse('its row is tagged "{tag}"'))
def _(store, tag):
    page = _web.opens_app(store).test_client().get("/").get_data(as_text=True)
    assert row_for(page, SUNDAY_CLASS).get("kind") == tag


@then(parsers.parse('the class\'s suggested label is "{label}"'))
def _(store, label):
    assert segment_classified(store, "lesson").label == label


@then(parsers.parse('the sermon\'s suggested label is still "{label}"'))
def _(store, label):
    assert segment_classified(store, "sermon").label == label


@then(parsers.parse('the detail page heading shows "{title}" and the date and time'))
def _(store, title):
    heading = heading_of(_web.opens_detail(store, SUNDAY_CLASS))
    assert title in heading
    assert formats_recorded_at(the_class_recording(store).started_at) in heading


@then("the rename is in the processing log as the reviewer's")
def _(store):
    renamed = store.lists(LogEntry, recording_id=SUNDAY_CLASS, kind="title_change")
    assert [entry.actor for entry in renamed] == ["reviewer"]


@then("I am told a title cannot be empty")
def _(renamed_page):
    assert "a title cannot be empty" in renamed_page


@then("its row shows the date and time and no title")
def _(list_page, store):
    row = row_for(list_page, SUNDAY_CLASS)
    assert row.get("recorded-at") == formats_recorded_at(the_class_recording(store).started_at)
    assert "title" not in row


@then("its detail page heading is the date and time alone")
def _(store):
    heading = heading_of(_web.opens_detail(store, SUNDAY_CLASS))
    assert heading == formats_recorded_at(the_class_recording(store).started_at)


@then(parsers.parse('the list shows "{shown}" and not "{hidden}"'))
def _(list_page, shown, hidden):
    titles = [row.get("title") for row in reads_rows(list_page, "recording")]
    assert titles == [shown]
    assert hidden not in list_page


@then(parsers.parse('it prints the title "{title}" and the kind "{kind}" for the Recording'))
def _(printed, title, kind):
    assert [line for line in printed if SUNDAY_CLASS in line and kind in line and title in line], printed


@then(parsers.parse('it prints the suggested label "{label}" for the class'))
def _(printed, label):
    assert [line for line in printed if "lesson" in line and label in line], printed


@then("the class has no label")
def _(store):
    assert segment_classified(store, "lesson").label is None


@then("it reports that the reviewer's title was kept")
def _(printed):
    assert [line for line in printed if SUNDAY_CLASS in line and "reviewer's title" in line], printed
