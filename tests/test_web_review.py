import re
from datetime import UTC, datetime
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from sermon.analysis import ProposesSegments
from sermon.shows_recording import formats_precise
from sermon.store import Block, Job, Proposal, Recording, Segment, opens_store
from sermon.web import creates_app
from steps._peaks import writes_peaks, writes_utterances


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_approve_via_http_queues_render(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=7200.0,
            span_end_seconds=9900.0,
            punch_in_seconds=7200.0,
            punch_out_seconds=9900.0,
        )
    )
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="high",
            boundary_confidence="high",
            punch_in_grade="easy",
            punch_out_grade="easy",
        )
    )
    client = creates_app(store=store).test_client()
    response = client.post(f"/api/segments/{segment.segment_id}/approve")
    assert response.status_code == 200
    body = response.get_json()
    assert body["segments"][0]["state"] == "approved"
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert jobs[0].state == "queued"


def test_an_unknown_recording_id_is_not_found_on_the_html_route(store):
    client = creates_app(store=store).test_client()
    assert client.get("/recordings/recording_20260101_000000").status_code == 404


def test_an_unknown_recording_id_is_not_found_on_the_api_route(store):
    client = creates_app(store=store).test_client()
    response = client.get("/api/recordings/recording_20260101_000000")
    assert response.status_code == 404
    assert response.get_json() == {"error": "no such recording"}


PRODUCTION_SPAN = (3060.83, 5594.695)
PRODUCTION_PUNCHES = (3060.83, 5594.575)


def a_reviewable_segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260927_095721",
            object_key="recordings/recording_20260927_095721.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=7200.0,
        )
    )
    writes_peaks(store, recording)
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=PRODUCTION_SPAN[0],
            span_end_seconds=PRODUCTION_SPAN[1],
            punch_in_seconds=PRODUCTION_PUNCHES[0],
            punch_out_seconds=PRODUCTION_PUNCHES[1],
        )
    )


def detail_of(client, segment, **query):
    asked = {"segment": segment.segment_id} | query
    return client.get(
        f"/recordings/{segment.recording_id}", query_string=asked
    ).get_data(as_text=True)


def test_the_rendered_playhead_starts_at_the_focused_boundary(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    page = detail_of(client, segment, focus="punch-out")
    assert f'data-role="detail-playhead" data-playhead-seconds="{PRODUCTION_PUNCHES[1]}"' in page


def test_the_rendered_playhead_falls_back_to_the_punch_in(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    page = detail_of(client, segment)
    assert f'data-role="detail-playhead" data-playhead-seconds="{PRODUCTION_PUNCHES[0]}"' in page


def test_punching_from_the_playhead_before_any_seek_is_not_a_refusal(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    posted = client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/punch-out",
        data={"do": "playhead"},
    )
    notice = parse_qs(urlsplit(posted.headers["Location"]).query).get("notice", [""])[0]
    assert notice == "adjusted", notice
    assert store.loads(Segment, segment.segment_id).punch_out_seconds != 0.0


def test_the_punch_control_is_withheld_when_the_playhead_cannot_be_punched(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    client.post(
        f"/api/recordings/{segment.recording_id}/seek", json={"seconds": 10.0}
    )
    page = detail_of(client, segment)
    assert "the playhead is outside the Segment" in page
    assert 'data-role="punch-from-playhead" disabled' in page


def test_a_punch_in_reaches_earlier_than_the_detected_span_once_it_is_grown(store):
    segment = a_reviewable_segment(store)
    client = creates_app(store=store).test_client()
    client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/span/start",
        data={"do": "set", "timecode": "3000.0"},
    )
    client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/punch-in",
        data={"do": "set", "timecode": "3054.93"},
    )
    stored = store.loads(Segment, segment.segment_id)
    assert stored.span_start_seconds == 3000.0
    assert stored.punch_in_seconds == 3054.93


PRODUCTION_DURATION = 6791.607619
PRODUCTION_BLOCKS = (
    (0.0, 1940.0, "other"),
    (1940.0, 2015.0, "announcements"),
    (2015.0, 2060.0, "prayer"),
    (2060.0, 2780.0, "music"),
    (2780.0, 3045.0, "prayer"),
    (3045.0, 3060.0, "scripture_reading"),
    (3060.0, 5595.0, "sermon"),
    (5595.0, 5770.0, "communion"),
    (5770.0, 6791.6, "other"),
)
PRODUCTION_SPOKEN = (
    (3040.0, 3044.0, "let us pray together before we open the word"),
    (3046.0, 3059.0, "hear the reading of the letter to the Hebrews"),
    (3061.0, 3068.0, "good morning and welcome to the message this week"),
    (5590.0, 5594.0, "let us pray as we come to the table"),
)


def a_freshly_proposed_segment(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260927_095721",
            object_key="recordings/recording_20260927_095721.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 27, 9, 57, 21, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=PRODUCTION_DURATION,
        )
    )
    writes_peaks(store, recording)
    writes_utterances(store, recording, PRODUCTION_SPOKEN)
    for start, end, type_ in PRODUCTION_BLOCKS:
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=start,
                end_seconds=end,
                type=type_,
                self_reported_confidence=0.9,
            )
        )
    ProposesSegments(
        store=store,
        derives=lambda spans, doc: (
            {
                "classification": "sermon",
                "punch_in": PRODUCTION_PUNCHES[0],
                "punch_out": PRODUCTION_PUNCHES[1],
                "confidence": 0.9,
            },
        ),
    )(recording)
    return store.lists(Segment, recording_id=recording.recording_id)[0]


def posts_a_punch_in(client, segment, timecode, **query):
    return client.post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/punch-in",
        data={"do": "set", "timecode": timecode},
        query_string=query,
    )


def moves_the_punch_in(client, segment, timecode, **query):
    posted = posts_a_punch_in(client, segment, timecode, **query)
    return client.get(posted.headers["Location"]).get_data(as_text=True)


def reads_field(page, name):
    found = re.search(rf'data-field="{name}">(.*?)<', page, re.S)
    return None if found is None else " ".join(found.group(1).split())


def window_step_of(page):
    return re.search(r'data-window-step="([^"]*)"', page).group(1)


def window_centre_of(page):
    return float(re.search(r'data-window-centre-seconds="([^"]*)"', page).group(1))


def a_zoom_other_than(page):
    return "thirty seconds" if window_step_of(page) != "thirty seconds" else "three seconds"


def test_a_freshly_proposed_punch_in_moves_earlier_without_touching_the_span(store):
    segment = a_freshly_proposed_segment(store)
    client = creates_app(store=store).test_client()
    page = moves_the_punch_in(client, segment, "3050.00")
    assert reads_field(page, "action-notice") == "the adjustment is saved without approving"
    assert reads_field(page, "punch-in") == formats_precise(3050.0)


def test_a_refusal_keeps_the_zoom_the_reviewer_chose(store):
    segment = a_freshly_proposed_segment(store)
    client = creates_app(store=store).test_client()
    chosen = a_zoom_other_than(detail_of(client, segment))
    page = moves_the_punch_in(
        client, segment, "600.00", zoom=chosen, centre=PRODUCTION_PUNCHES[0]
    )
    assert reads_field(page, "action-notice") == "the boundary must fall within the Segment"
    assert window_step_of(page) == chosen


def test_an_accepted_move_keeps_the_zoom_the_reviewer_chose(store):
    segment = a_freshly_proposed_segment(store)
    client = creates_app(store=store).test_client()
    chosen = a_zoom_other_than(detail_of(client, segment))
    page = moves_the_punch_in(
        client, segment, "3050.00", zoom=chosen, centre=PRODUCTION_PUNCHES[0]
    )
    assert reads_field(page, "action-notice") == "the adjustment is saved without approving"
    assert window_step_of(page) == chosen


def test_the_drag_target_the_page_offers_carries_the_zoom_back(store):
    segment = a_freshly_proposed_segment(store)
    client = creates_app(store=store).test_client()
    chosen = a_zoom_other_than(detail_of(client, segment))
    zoomed = detail_of(client, segment, zoom=chosen, centre=PRODUCTION_PUNCHES[0])
    offered = re.search(r'data-role="handle-punch-in"[^>]*data-url="([^"]+)"', zoomed)
    posted = client.post(unescape(offered.group(1)), data={"do": "set", "timecode": "3050.00"})
    page = client.get(posted.headers["Location"]).get_data(as_text=True)
    assert window_step_of(page) == chosen
    assert window_centre_of(page) == window_centre_of(zoomed)
    assert reads_field(page, "punch-in") == formats_precise(3050.0)


def test_the_outcome_is_announced_beside_the_waveform(store):
    segment = a_freshly_proposed_segment(store)
    client = creates_app(store=store).test_client()
    refused = posts_a_punch_in(client, segment, "600.00")
    assert refused.headers["Location"].endswith("#waveform")
    page = client.get(refused.headers["Location"]).get_data(as_text=True)
    assert page.count('data-field="action-notice"') == 1
    announced = page.index('data-field="action-notice"')
    assert page.index('<section class="waveform"') < announced
    assert announced < page.index('data-field="punch-control"')
    assert announced < page.index('data-field="span-edge-control"')
