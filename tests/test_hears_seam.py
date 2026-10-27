import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.pipeline.render import probe_format
from sermon.store import RemovedSpan, Recording, Segment, layout, opens_store
from sermon.web import creates_app
from steps import _rendering

TOLERANCE_SECONDS = 2 * _rendering.MP3_FRAME_SECONDS
PUNCH_IN = 7220.0
PUNCH_OUT = 9812.0


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260816_090014",
            object_key="recordings/recording_20260816_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=10000.0,
        )
    )
    store.saves(replace(recording, local_path=layout.source_path(recording)))
    _rendering.places(_rendering.source(), store.resolves(store.loads(Recording, recording.recording_id)))
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=PUNCH_IN,
            span_end_seconds=PUNCH_OUT,
            punch_in_seconds=PUNCH_IN,
            punch_out_seconds=PUNCH_OUT,
        )
    )


def hears(store, segment, seam):
    return creates_app(store=store).test_client().get(f"/api/segments/{segment.segment_id}/seam/{seam}")


def pieces_of(heard):
    return json.loads(heard.headers["X-Kept-Pieces"])


def lasting(path_bytes, tmp_path):
    path = tmp_path / "seam.mp3"
    path.write_bytes(path_bytes)
    return probe_format(path)["duration"]


def test_the_opening_is_the_five_seconds_either_side_of_the_punch_in(store, segment, tmp_path):
    heard = hears(store, segment, "opening")

    assert heard.status_code == 200
    assert heard.content_type.startswith("audio/mpeg")
    assert pieces_of(heard) == [[PUNCH_IN - 5.0, PUNCH_IN + 5.0]]
    assert abs(lasting(heard.data, tmp_path) - 10.0) <= TOLERANCE_SECONDS


def test_the_ending_is_the_five_seconds_either_side_of_the_punch_out(store, segment, tmp_path):
    heard = hears(store, segment, "ending")

    assert pieces_of(heard) == [[PUNCH_OUT - 5.0, PUNCH_OUT + 5.0]]
    assert abs(lasting(heard.data, tmp_path) - 10.0) <= TOLERANCE_SECONDS


def test_a_removed_span_inside_the_opening_window_is_left_out(store, segment, tmp_path):
    store.saves(replace(segment, removed_spans=(RemovedSpan(start_seconds=PUNCH_IN + 2.0, end_seconds=PUNCH_IN + 3.5),)))

    heard = hears(store, segment, "opening")

    assert pieces_of(heard) == [[PUNCH_IN - 5.0, PUNCH_IN + 2.0], [PUNCH_IN + 3.5, PUNCH_IN + 5.0]]
    assert abs(lasting(heard.data, tmp_path) - 8.5) <= 2 * TOLERANCE_SECONDS


def test_a_nudged_boundary_is_heard_at_its_new_place_without_re_analysis(store, segment):
    store.saves(replace(segment, punch_in_seconds=PUNCH_IN + 1.5))

    assert pieces_of(hears(store, segment, "opening")) == [[PUNCH_IN - 3.5, PUNCH_IN + 6.5]]


def test_a_seam_that_does_not_exist_is_not_found(store, segment):
    assert hears(store, segment, "middle").status_code == 404


def test_a_seam_is_never_cached(store, segment):
    assert "no-store" in hears(store, segment, "opening").headers["Cache-Control"]
