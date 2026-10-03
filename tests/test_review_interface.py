from datetime import UTC, datetime

import pytest

from sermon.store import Recording, Segment, opens_store
from sermon.web import creates_app
from steps._markup import reads_role, reads_rows


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )


def saves_segment(store, recording, **seconds):
    held = {
        "span_start_seconds": 1165.74,
        "span_end_seconds": 3000.0,
        "punch_in_seconds": 1165.74,
        "punch_out_seconds": 3000.0,
    } | seconds
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            **held,
        )
    )


def test_a_punch_in_just_before_its_span_does_not_open_the_page_with_dead_punch_controls(
    store, recording
):
    segment = saves_segment(store, recording, punch_in_seconds=1165.70)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    assert "disabled" not in page.split('data-role="punch"')[1].split("</ol>")[0]


def test_the_punch_controls_carry_the_span_the_client_judges_them_against(store, recording):
    segment = saves_segment(store, recording)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    punch = reads_role(page, "punch")
    assert float(punch["span-start-seconds"]) == segment.span_start_seconds
    assert float(punch["span-end-seconds"]) == segment.span_end_seconds
    assert punch["unavailable-reason"] == "the playhead is outside the Segment"


UNKNOWN_RECORDING = "recording_19990101_000000"
UNKNOWN_SEGMENT = 99999
NAMED_IN_THE_PATH = {
    "action": (
        "discard",
        "restore",
        "archive-whole-recording",
        "re-run-analysis",
        "create-segment",
        "split-segment",
        "merge-segments",
        "approve",
        "skip",
        "reopen",
        "revert",
        "classify",
    ),
    "edge": ("start", "end"),
    "boundary": ("punch-in", "punch-out"),
}
FORM = {
    "do": "set",
    "timecode": "1:00:00",
    "from": "1:00:00",
    "to": "1:30:00",
    "at": "1:10:00",
    "classification": "sermon",
}
JSON = {"seconds": 12.0, "date": "2026-09-13", "label": "Hebrews 12"}


def addresses_unknown_entities(app):
    for rule in app.url_map.iter_rules():
        if not {"recording_id", "segment_id"} & rule.arguments:
            continue
        method = sorted(rule.methods - {"HEAD", "OPTIONS"})[0]
        named = [name for name in rule.arguments if name in NAMED_IN_THE_PATH]
        choices = NAMED_IN_THE_PATH[named[0]] if named else (None,)
        for choice in choices:
            values = {"recording_id": UNKNOWN_RECORDING, "segment_id": UNKNOWN_SEGMENT}
            if named:
                values[named[0]] = choice
            built = rule.build(
                {name: value for name, value in values.items() if name in rule.arguments}
            )
            yield method, built[1]


def test_no_route_answers_500_for_an_unknown_recording_or_segment(store):
    app = creates_app(store=store)
    client = app.test_client()
    answered = {}
    for method, url in addresses_unknown_entities(app):
        sent = {"json": JSON} if url.startswith("/api/") else {"data": FORM}
        answered[f"{method} {url}"] = client.open(url, method=method, **sent).status_code
    assert len(answered) >= 30, answered
    assert {url: code for url, code in answered.items() if code != 404} == {}


def test_seeking_an_unknown_recording_holds_no_playhead_for_it(store):
    client = creates_app(store=store).test_client()
    assert (
        client.post(f"/api/recordings/{UNKNOWN_RECORDING}/seek", json={"seconds": 1234.5})
    ).status_code == 404
    recording = store.saves(
        Recording(
            recording_id=UNKNOWN_RECORDING,
            object_key=f"1999/01/01/{UNKNOWN_RECORDING}.flac",
            state="awaiting_review",
            started_at=datetime(1999, 1, 1, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )
    shown = client.get(f"/api/recordings/{recording.recording_id}").get_json()
    assert shown["playhead_seconds"] == 0.0
