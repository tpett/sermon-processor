from datetime import UTC, datetime

import pytest

from sermon import cli
from sermon.pipeline import classify
from sermon.store import Block, Recording, RecordingTitle, Segment, opens_store

ENDPOINT = "http://mac-m1.example:11434"


@pytest.fixture
def data_root(tmp_path):
    store = opens_store(tmp_path)
    recording = store.saves(
        Recording(
            recording_id="recording_20260830_094400",
            object_key="recordings/recording_20260830_094400.flac",
            state="reviewed",
            started_at=datetime(2026, 8, 30, 9, 44, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=2400.0, type="rehearsal"))
    store.saves(
        Recording(
            recording_id="recording_20260831_120000",
            object_key="recordings/recording_20260831_120000.flac",
            state="downloaded",
            started_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.close()
    return tmp_path


@pytest.fixture
def model(monkeypatch):
    asked = []

    def answers(name, prompt, think=False):
        asked.append((name, prompt, classify.ENDPOINT))
        return {"kind": "rehearsal", "title": "Pre-Service Rehearsal", "series": None, "topic": None}, 0

    monkeypatch.setattr(classify, "call_json", answers)
    return asked


def run(data_root, *arguments):
    printed = []
    code = cli.titles(
        settings={"SERMON_DATA_ROOT": str(data_root), "SERMON_MODEL_ENDPOINT": ENDPOINT},
        arguments=list(arguments),
        prints=printed.append,
    )
    return code, printed


def test_a_dry_run_prints_the_proposed_title_and_writes_nothing(data_root, model):
    code, printed = run(data_root, "--dry-run")
    assert code == 0
    assert "2026-08-30 09:44  rehearsal  Pre-Service Rehearsal  [recording_20260830_094400]" in printed, printed
    assert not any("recording_20260831_120000" in line for line in printed), "an unanalysed Recording was named"
    store = opens_store(data_root)
    try:
        assert store.loads(RecordingTitle, "recording_20260830_094400") is None
        assert store.loads(Recording, "recording_20260830_094400").kind is None
    finally:
        store.close()


def test_a_run_writes_the_title_and_kind_through_the_configured_endpoint(data_root, model):
    code, _ = run(data_root)
    assert code == 0
    assert [endpoint for _, _, endpoint in model] == [ENDPOINT]
    store = opens_store(data_root)
    try:
        assert store.loads(RecordingTitle, "recording_20260830_094400").title == "Pre-Service Rehearsal"
        assert store.loads(Recording, "recording_20260830_094400").kind == "rehearsal"
    finally:
        store.close()
    assert classify.ENDPOINT is None


def test_a_recording_already_named_is_left_unless_asked_again(data_root, model):
    run(data_root)
    run(data_root)
    assert len(model) == 1
    run(data_root, "--again")
    assert len(model) == 2


def test_naming_needs_a_model_endpoint(data_root, model):
    printed = []
    code = cli.titles(settings={"SERMON_DATA_ROOT": str(data_root)}, arguments=[], prints=printed.append)
    assert code == 1
    assert printed == ["nothing sets SERMON_MODEL_ENDPOINT"]
    assert model == []


def test_the_segments_it_names_get_a_label_only_where_none_is_written(data_root, monkeypatch):
    store = opens_store(data_root)
    for label in (None, "Members Meeting (budget)"):
        store.saves(
            Segment(
                recording_id="recording_20260830_094400",
                classification="meeting",
                state="proposed",
                span_start_seconds=0.0 if label is None else 1200.0,
                span_end_seconds=1200.0 if label is None else 2400.0,
                punch_in_seconds=0.0 if label is None else 1200.0,
                punch_out_seconds=1200.0 if label is None else 2400.0,
                label=label,
            )
        )
    store.close()
    monkeypatch.setattr(
        classify, "call_json", lambda *_a, **_k: ({"kind": "meeting", "title": "Members Meeting"}, 0)
    )
    run(data_root)
    store = opens_store(data_root)
    try:
        assert sorted(one.label for one in store.lists(Segment)) == ["Members Meeting", "Members Meeting (budget)"]
    finally:
        store.close()


def test_a_write_run_never_touches_a_recording_a_reviewer_titled(data_root, model):
    store = opens_store(data_root)
    store.saves(RecordingTitle(recording_id="recording_20260830_094400", title="Band practice", edited_by_human=True))
    store.close()
    code, printed = run(data_root, "--again")
    assert code == 0
    assert model == []
    assert any("Band practice  (kept: titled by a reviewer)" in line for line in printed), printed
    store = opens_store(data_root)
    try:
        assert store.loads(Recording, "recording_20260830_094400").kind is None
        assert store.loads(RecordingTitle, "recording_20260830_094400").title == "Band practice"
    finally:
        store.close()


def test_a_dry_run_line_carries_the_label_it_would_suggest(data_root, monkeypatch):
    store = opens_store(data_root)
    store.saves(
        Segment(
            recording_id="recording_20260830_094400",
            classification="lesson",
            state="proposed",
            span_start_seconds=0.0,
            span_end_seconds=1200.0,
            punch_in_seconds=0.0,
            punch_out_seconds=1200.0,
        )
    )
    store.close()
    monkeypatch.setattr(
        classify,
        "call_json",
        lambda *_a, **_k: ({"kind": "class", "title": "TEC - Giving", "series": "TEC", "topic": "Giving"}, 0),
    )
    _, printed = run(data_root, "--dry-run")
    assert (
        "2026-08-30 09:44  class  Theological Equipping Class - Giving  label: TEC - Giving (lesson)"
        "  [recording_20260830_094400]"
    ) in printed, printed
