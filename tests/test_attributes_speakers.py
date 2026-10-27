from datetime import UTC, datetime

import pytest

from sermon.analysis.attributes_speakers import AttributesSpeakers
from sermon.analysis.io import writes_json
from sermon.shows_recording import ShowsRecording
from sermon.store import Recording, opens_store
from sermon.web import creates_app

TURNS = [
    {"start": 0.0, "end": 10.0, "speaker": "S0"},
    {"start": 9.0, "end": 30.0, "speaker": "S1"},
    {"start": 40.0, "end": 50.0, "speaker": "S0"},
]


def utterance(start, end, speaker=None):
    return {"start": start, "end": end, "text": "words", "speaker": speaker}


def test_each_utterance_takes_the_speaker_it_overlaps_most():
    spoken = [utterance(1.0, 8.0), utterance(8.0, 14.0), utterance(41.0, 49.0)]
    assert AttributesSpeakers()(spoken, TURNS) == ("S0", "S1", "S0")


def test_an_utterance_no_turn_covers_has_no_speaker():
    assert AttributesSpeakers()([utterance(31.0, 39.0)], TURNS) == (None,)


def test_the_turns_outrank_a_speaker_the_transcript_names():
    assert AttributesSpeakers()([utterance(1.0, 8.0, speaker="Speaker 1")], TURNS) == ("S0",)


def test_a_speaker_the_transcript_names_is_kept_where_no_turn_covers_it():
    assert AttributesSpeakers()([utterance(31.0, 39.0, speaker="Speaker 1")], TURNS) == ("Speaker 1",)


def test_without_turns_nothing_is_attributed():
    assert AttributesSpeakers()([utterance(1.0, 8.0)], []) == (None,)


def test_a_long_turn_far_behind_still_covers_a_late_utterance():
    turns = [{"start": 0.0, "end": 3000.0, "speaker": "S0"}] + [
        {"start": float(at), "end": float(at) + 1.0, "speaker": "S1"} for at in range(100, 2000, 10)
    ]
    assert AttributesSpeakers()([utterance(2500.0, 2510.0)], turns) == ("S0",)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def a_diarized_recording(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=60.0,
        )
    )
    writes_json(
        store,
        recording,
        "transcript",
        {"duration": 60.0, "utterances": [utterance(1.0, 8.0), utterance(41.0, 49.0), utterance(31.0, 39.0)]},
    )
    writes_json(store, recording, "diarization", {"turns": TURNS})
    return recording


def test_the_recording_view_names_who_speaks_each_utterance(store):
    recording = a_diarized_recording(store)
    view = ShowsRecording(store=store)(recording.recording_id)
    assert [item[3] for item in view.transcript] == ["Speaker 1", "Speaker 1", None]


def test_the_transcript_panel_names_the_speaker_once_until_it_changes(store):
    recording = a_diarized_recording(store)
    page = creates_app(store=store).test_client().get(f"/recordings/{recording.recording_id}").get_data(as_text=True)
    assert page.count('data-field="utterance-speaker">Speaker 1<') == 1
