from datetime import UTC, datetime

import pytest

from sermon.analysis.titles_recording import (
    AsksModelForTitle,
    DescribesRecording,
    InfersTitle,
    TitleNotInferred,
    TitlesRecording,
    without_dates,
)
from sermon.config import ModelEndpointUnreachable
from sermon.glossary import Glossary, GlossaryUnreadable, ReadsGlossary
from sermon.pipeline import classify
from sermon.store import Block, Recording, RecordingTitle, Segment, opens_store

NAMES = Glossary(names={"TEC": "Theological Equipping Class", "CT": "Culture and Theology"})


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def recorded(store, at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC), kind=None):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="recordings/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=at,
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
            kind=kind,
        )
    )


def with_contents(store, recording, label="Hebrews 12.25-29", taught="A class on giving as worship"):
    store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=3300.0, type="lesson", summary=taught))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=5400.0, end_seconds=10800.0, type="sermon"))
    for classification, start, end, written in (("lesson", 60.0, 3300.0, None), ("sermon", 5400.0, 10800.0, label)):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=start,
                span_end_seconds=end,
                punch_in_seconds=start,
                punch_out_seconds=end,
                label=written,
            )
        )


def answering(answer):
    asked = []

    def asks(prompt):
        asked.append(prompt)
        return answer

    asks.asked = asked
    return asks


def test_the_glossary_spells_out_an_acronym_and_abbreviates_a_name():
    assert NAMES.spells_out("TEC - Giving") == "Theological Equipping Class - Giving"
    assert NAMES.spells_out("CT - Islam") == "Culture and Theology - Islam"
    assert NAMES.spells_out("A DIRECT talk") == "A DIRECT talk"
    assert NAMES.abbreviates("Theological Equipping Class - Giving") == "TEC - Giving"
    assert NAMES.abbreviates("culture and theology") == "CT"


def test_the_shipped_glossary_names_tec_and_ct():
    assert ReadsGlossary()().names == NAMES.names


def test_a_glossary_entry_that_is_not_a_name_is_refused(tmp_path):
    written = tmp_path / "names.toml"
    written.write_text('TEC = 3\n')
    with pytest.raises(GlossaryUnreadable, match="TEC"):
        ReadsGlossary(written)()


@pytest.mark.parametrize(
    "said, kept",
    [
        ("Sunday Service - September 13, 2026", "Sunday Service"),
        ("Sunday Service - 2026-09-13 - Hebrews 12:25-29", "Sunday Service - Hebrews 12:25-29"),
        ("Members Meeting (9/13)", "Members Meeting"),
        ("13th September Pre-Service Rehearsal", "Pre-Service Rehearsal"),
        ("Mark 14:60-64", "Mark 14:60-64"),
        ("Good Friday Service 2026", "Good Friday Service"),
    ],
)
def test_a_title_never_carries_the_date(said, kept):
    assert without_dates(said) == kept


def test_the_model_is_shown_the_weekday_and_time_and_never_the_date(store):
    recording = recorded(store)
    with_contents(store, recording)
    shown = DescribesRecording(NAMES)(recording, store.lists(Block), store.lists(Segment))
    assert "Sunday at 09:00" in shown
    assert "2026" not in shown and "09-13" not in shown and "September" not in shown
    assert "TEC = Theological Equipping Class" in shown
    assert "Hebrews 12:25-29" in shown
    assert "A class on giving as worship" in shown


def test_a_kind_outside_the_vocabulary_is_unknown(store):
    recording = recorded(store)
    titled = InfersTitle(store=store, asks=answering({"kind": "worship night", "title": "Prayer Night"}), glossary=NAMES)(recording)
    assert titled.kind == "unknown"
    assert titled.title == "Prayer Night"


def test_an_answer_naming_neither_kind_nor_title_is_no_answer(store):
    recording = recorded(store)
    with pytest.raises(TitleNotInferred):
        InfersTitle(store=store, asks=answering({"summary": "words"}), glossary=NAMES)(recording)


def test_an_unreachable_model_is_a_title_not_inferred(monkeypatch):
    def unreachable(model, prompt):
        raise ModelEndpointUnreachable("http://mac-m1:11434")

    monkeypatch.setattr(classify, "call_json", unreachable)
    with pytest.raises(TitleNotInferred):
        AsksModelForTitle()("prompt")


def test_titling_writes_kind_title_series_and_the_class_label(store):
    recording = recorded(store)
    with_contents(store, recording)
    TitlesRecording(
        store=store,
        asks=answering({"kind": "class", "title": "TEC - Giving, then Sunday Service - Hebrews 12.25-29", "series": "TEC", "topic": "Giving"}),
        glossary=NAMES,
    )(recording)
    assert store.loads(Recording, recording.recording_id).kind == "class"
    assert store.loads(RecordingTitle, recording.recording_id) == RecordingTitle(
        recording_id=recording.recording_id,
        title="Theological Equipping Class - Giving, then Sunday Service - Hebrews 12:25-29",
        series="Theological Equipping Class",
    )
    labels = {one.classification: one.label for one in store.lists(Segment)}
    assert labels == {"lesson": "TEC - Giving", "sermon": "Hebrews 12.25-29"}


def test_an_unknown_answer_does_not_replace_a_kind_already_known(store):
    recording = recorded(store, kind="rehearsal")
    TitlesRecording(store=store, asks=answering({"kind": "nonsense", "title": "Pre-Service Rehearsal"}), glossary=NAMES)(recording)
    assert store.loads(Recording, recording.recording_id).kind == "rehearsal"


def test_a_title_a_reviewer_wrote_survives_titling(store):
    recording = recorded(store)
    store.saves(RecordingTitle(recording_id=recording.recording_id, title="Baptism Sunday", edited_by_human=True))
    TitlesRecording(store=store, asks=answering({"kind": "service", "title": "Sunday Service"}), glossary=NAMES)(recording)
    assert store.loads(RecordingTitle, recording.recording_id).title == "Baptism Sunday"
    assert store.loads(Recording, recording.recording_id).kind == "service"


def test_a_label_already_written_is_never_replaced(store):
    recording = recorded(store)
    with_contents(store, recording)
    lesson = next(one for one in store.lists(Segment) if one.classification == "lesson")
    from dataclasses import replace

    store.saves(replace(lesson, label="TEC - Generosity"))
    TitlesRecording(store=store, asks=answering({"kind": "class", "title": "TEC - Giving", "series": "TEC", "topic": "Giving"}), glossary=NAMES)(recording)
    assert store.loads(Segment, lesson.segment_id).label == "TEC - Generosity"


def test_a_class_without_a_topic_is_labelled_by_its_acronym(store):
    recording = recorded(store)
    with_contents(store, recording)
    TitlesRecording(store=store, asks=answering({"kind": "class", "title": "Theological Equipping Class", "series": "Theological Equipping Class", "topic": None}), glossary=NAMES)(recording)
    assert {one.classification: one.label for one in store.lists(Segment)}["lesson"] == "TEC"


def test_a_suggested_label_writes_a_verse_with_a_dot(store):
    recording = recorded(store)
    with_contents(store, recording, taught="A class working through Romans 8:1-11")
    TitlesRecording(store=store, asks=answering({"kind": "class", "title": "TEC - Romans 8:1-11", "series": "TEC", "topic": "Romans 8:1-11"}), glossary=NAMES)(recording)
    assert {one.classification: one.label for one in store.lists(Segment)}["lesson"] == "TEC - Romans 8.1-11"
    assert store.loads(RecordingTitle, recording.recording_id).title == "Theological Equipping Class - Romans 8:1-11"


def test_a_passage_the_model_was_not_shown_is_dropped_from_title_and_topic(store):
    recording = recorded(store)
    with_contents(store, recording, label=None)
    titled = InfersTitle(
        store=store,
        asks=answering({"kind": "service", "title": "Sunday Service - Hebrews 13:1-6", "series": "TEC", "topic": "Romans 8"}),
        glossary=NAMES,
    )(recording)
    assert titled.title == "Sunday Service"
    assert titled.topic is None


def test_a_passage_the_model_was_shown_stays(store):
    recording = recorded(store)
    with_contents(store, recording)
    titled = InfersTitle(
        store=store, asks=answering({"kind": "service", "title": "Sunday Service - Hebrews 12:25-29"}), glossary=NAMES
    )(recording)
    assert titled.title == "Sunday Service - Hebrews 12:25-29"


def test_a_long_title_is_cut_at_a_separator_never_inside_a_verse():
    from sermon.analysis.titles_recording import TITLE_LIMIT, shortened

    long = "Theological Equipping Class - Stewardship and Generosity in the Life of the Local Church, then Sunday Service - Hebrews 12:25-29"
    assert len(long) > TITLE_LIMIT
    assert shortened(long) == "Theological Equipping Class - Stewardship and Generosity in the Life of the Local Church"


def test_a_topic_starts_with_a_capital(store):
    recording = recorded(store)
    with_contents(store, recording)
    TitlesRecording(store=store, asks=answering({"kind": "class", "title": "TEC - Speech", "series": "TEC", "topic": "theology of speech"}), glossary=NAMES)(recording)
    assert {one.classification: one.label for one in store.lists(Segment)}["lesson"] == "TEC - Theology of speech"
