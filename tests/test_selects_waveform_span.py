from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.store import Recording, RemovedSpan, Segment, opens_store
from steps import _audio, _browser
from steps._peaks import writes_peaks

PUNCH_IN = 30.0
PUNCH_OUT = 90.0
CENTRE = 45.0
SELECTION = (44.65, 45.35)
DETAIL = '[data-role="detail"]'


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
            duration_seconds=120.0,
        )
    )


@pytest.fixture
def segment(store, recording):
    _audio.registers_preview(store, recording, seconds=120.0)
    writes_peaks(store, recording)
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


def opens_editor(page, recording, segment, centre=CENTRE, zoom="three+seconds"):
    page.goto(
        f"/recordings/{recording.recording_id}?segment={segment.segment_id}"
        f"&mode=edit&zoom={zoom}&centre={centre}"
    )
    page.wait_for_selector(f"{DETAIL}[data-window-start-seconds]")


def selects(page, start=SELECTION[0], end=SELECTION[1]):
    page.locator(DETAIL).scroll_into_view_if_needed()
    _browser.drags_between_seconds(page, DETAIL, start, end)
    page.wait_for_selector('[data-role="selection"]:not([hidden])')


def audio_state(page):
    return page.evaluate(
        "(() => { const a = document.querySelector('[data-role=\"preview-audio\"]');"
        " return { time: a.currentTime, paused: a.paused }; })()"
    )


def selection_is_hidden(page):
    return page.locator('[data-role="selection"]').evaluate("(node) => node.hidden")


def test_the_selection_toolbar_stays_clickable_after_playing_the_selection(store, recording, segment):
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        selects(page)
        page.locator('[data-role="play-selection"]').click()
        page.wait_for_function(
            "(end) => { const a = document.querySelector('[data-role=\"preview-audio\"]');"
            " return a.paused && a.currentTime >= end - 0.05; }",
            arg=SELECTION[1],
        )
        centre = page.locator('[data-role="clear-selection"]').bounding_box()
        reached = page.evaluate(
            "([x, y]) => document.elementFromPoint(x, y).closest('[data-role]').dataset.role",
            [centre["x"] + centre["width"] / 2, centre["y"] + centre["height"] / 2],
        )
        assert reached == "clear-selection"
        page.locator('[data-role="clear-selection"]').click(timeout=2000)

        assert selection_is_hidden(page)


def test_playing_the_selection_stops_at_its_end(store, recording, segment):
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        selects(page)
        page.locator('[data-role="play-selection"]').click()
        page.wait_for_function(
            "(end) => { const a = document.querySelector('[data-role=\"preview-audio\"]');"
            " return a.paused && a.currentTime >= end - 0.05; }",
            arg=SELECTION[1],
        )
        heard = audio_state(page)

        assert heard["time"] == pytest.approx(SELECTION[1], abs=0.15)
        assert not selection_is_hidden(page)


def test_clearing_the_selection_removes_nothing(store, recording, segment):
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        selects(page)
        page.locator('[data-role="clear-selection"]').click()

        assert selection_is_hidden(page)
        assert page.locator('[data-role="removed-span-detail"]').count() == 0
        assert page.locator('[data-row="removed-span"]').count() == 0


def test_a_press_released_outside_the_pane_before_dragging_leaves_nothing_pending(
    store, recording, segment
):
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        pane = page.locator(DETAIL)
        box = pane.bounding_box()
        x = box["x"] + box["width"] / 2
        page.mouse.move(x, box["y"] + 2)
        page.mouse.down()
        page.mouse.move(x, box["y"] - 40, steps=4)
        page.mouse.up()
        page.mouse.move(x, box["y"] + box["height"] / 2, steps=4)
        page.mouse.move(x + 60, box["y"] + box["height"] / 2, steps=4)

        assert selection_is_hidden(page)


def box_of(page, selector):
    return page.locator(selector).bounding_box()


@pytest.mark.parametrize("device", [_browser.DESKTOP, _browser.PHONE], ids=["desktop", "phone"])
def test_the_punch_controls_follow_the_zoom_row_with_the_reach_and_help_below(
    store, recording, segment, device
):
    with _browser.opens_page(store, device) as page:
        opens_editor(page, recording, segment)
        zoom = box_of(page, ".transport .zoom-steps")
        punch = box_of(page, ".transport .punch-set")
        keys = box_of(page, ".transport .keys")
        reach = box_of(page, ".transport .reach")

        assert zoom["y"] <= punch["y"] < zoom["y"] + zoom["height"] + 16
        assert keys["y"] >= punch["y"] + punch["height"]
        assert reach["y"] >= punch["y"] + punch["height"]


def removes_spans(store, segment, *spans):
    return store.saves(
        replace(
            segment,
            removed_spans=tuple(RemovedSpan(start_seconds=a, end_seconds=b) for a, b in spans),
        )
    )


def marks(page):
    return page.locator('[data-role="removed-span-detail"]')


def clicks_overview_at(page, seconds):
    box = box_of(page, '[data-role="waveform"]')
    page.mouse.click(box["x"] + box["width"] * seconds / 120.0, box["y"] + box["height"] / 2)


def test_a_removed_span_outside_the_detail_window_shows_no_mark_or_pill(store, recording, segment):
    removes_spans(store, segment, (60.0, 61.0))
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        assert marks(page).count() == 1
        assert not marks(page).first.is_visible()
        assert not page.locator('[data-role="put-back-span"]').is_visible()

        clicks_overview_at(page, 60.5)
        page.wait_for_function(
            "document.querySelector('[data-role=\"removed-span-detail\"]').offsetParent !== null"
        )
        assert page.locator('[data-role="put-back-span"]').is_visible()

        clicks_overview_at(page, 80.0)
        page.wait_for_function(
            "document.querySelector('[data-role=\"removed-span-detail\"]').offsetParent === null"
        )
        assert not page.locator('[data-role="put-back-span"]').is_visible()


@pytest.mark.parametrize("removed", [(42.0, 43.8), (46.3, 47.0)], ids=["left-edge", "right-edge"])
def test_a_put_back_pill_on_a_span_at_the_window_edge_stays_inside_the_pane(
    store, recording, segment, removed
):
    removes_spans(store, segment, removed)
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        pill = box_of(page, '[data-role="put-back-span"]')
        pane = box_of(page, DETAIL)

        assert pill["x"] >= pane["x"]
        assert pill["x"] + pill["width"] <= pane["x"] + pane["width"]


def test_putting_a_span_back_from_the_waveform_stays_in_edit_mode(store, recording, segment):
    removes_spans(store, segment, (44.4, 44.9))
    with _browser.opens_page(store) as page:
        opens_editor(page, recording, segment)
        with page.expect_navigation():
            page.locator('[data-role="put-back-span"]').click()

        assert "mode=edit" in page.url
        assert page.locator('[data-role="detail"]').count() == 1
        assert marks(page).count() == 0
        assert page.locator('[data-row="removed-span"]').count() == 0


def touch_drags(page, start, end):
    pane = page.locator(DETAIL)
    pane.scroll_into_view_if_needed()
    (x1, y), (x2, _) = (_browser.x_at_seconds(pane, at) for at in (start, end))
    session = page.context.new_cdp_session(page)
    session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x1, "y": y}]})
    for step in range(1, 9):
        x = x1 + (x2 - x1) * step / 8
        session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]})
    session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def test_a_touch_drag_across_the_detail_pane_selects_on_a_phone(store, recording, segment):
    with _browser.opens_page(store, _browser.PHONE) as page:
        opens_editor(page, recording, segment)
        touch_drags(page, *SELECTION)
        page.wait_for_selector('[data-role="selection"]:not([hidden])')

        assert page.locator('[data-field="selection-length"]').inner_text().strip() == "0.70 s"


def test_the_selection_and_put_back_controls_are_44px_targets_inside_the_pane_on_a_phone(
    store, recording, segment
):
    removes_spans(store, segment, (44.4, 44.9))
    with _browser.opens_page(store, _browser.PHONE) as page:
        opens_editor(page, recording, segment)
        selects(page, 45.0, 45.6)
        pane = box_of(page, DETAIL)
        controls = [
            '[data-role="play-selection"]',
            '[data-role="remove-selection"]',
            '[data-role="clear-selection"]',
            '[data-role="put-back-span"]',
        ]
        for selector in controls:
            box = box_of(page, selector)
            assert box["height"] >= 44, selector
            assert pane["x"] <= box["x"], selector
            assert box["x"] + box["width"] <= pane["x"] + pane["width"], selector

        bar = box_of(page, '[data-role="selection-toolbar"]')
        assert pane["x"] <= bar["x"]
        assert bar["x"] + bar["width"] <= pane["x"] + pane["width"]


def test_the_edit_page_does_not_scroll_sideways_on_a_phone_with_a_selection(store, recording, segment):
    removes_spans(store, segment, (44.4, 44.9))
    with _browser.opens_page(store, _browser.PHONE) as page:
        opens_editor(page, recording, segment)
        selects(page, 45.0, 45.6)

        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
