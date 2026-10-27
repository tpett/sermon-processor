import io
import json
import math
import struct
import wave
from datetime import UTC, datetime

import pytest

from sermon.store import Recording, Segment, opens_store
from steps import _audio, _browser
from steps._peaks import writes_peaks

PUNCH_IN = 30.0
PUNCH_OUT = 90.0
OPENING_PIECES = [[26.0, 28.0]]
ENDING_PIECES = [[88.0, 90.0]]
CLIP_SECONDS = 2.0
RATE = 8000

LISTENS = """
window.heard = [];
for (const name of ["seam:position", "preview:started", "preview:ended"]) {
  document.addEventListener(name, (event) => {
    const { clock, ...detail } = event.detail || {};
    window.heard.push({ name, ...detail });
  });
}
"""


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


def tone(seconds):
    body = io.BytesIO()
    with wave.open(body, "wb") as encoded:
        encoded.setnchannels(1)
        encoded.setsampwidth(2)
        encoded.setframerate(RATE)
        encoded.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / RATE)))
                for n in range(int(seconds * RATE))
            )
        )
    return body.getvalue()


def serves_clips(page, delays=None):
    clips = {"opening": OPENING_PIECES, "ending": ENDING_PIECES}
    delays = delays or {}

    def answer(route):
        seam = route.request.url.rsplit("/", 1)[-1]
        if seam in delays:
            page.wait_for_timeout(delays[seam])
        route.fulfill(
            body=tone(CLIP_SECONDS),
            headers={
                "Content-Type": "audio/wav",
                "X-Kept-Pieces": json.dumps(clips[seam]),
                "Cache-Control": "no-store",
            },
        )

    page.route("**/api/segments/*/seam/*", answer)


def opens_review(page, recording, segment):
    page.add_init_script(LISTENS)
    page.goto(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")


def hears(page, seam):
    return page.locator(f'[data-row="seam"][data-seam="{seam}"] [data-field="hear-seam-control"]')


def events(page, name):
    return page.evaluate("(name) => window.heard.filter((e) => e.name === name)", name)


def last_position(page):
    return events(page, "seam:position")[-1]["seconds"]


def preview_time(page):
    return page.evaluate("document.querySelector('[data-role=\"preview-audio\"]').currentTime")


def waits_for_position_after(page, seconds):
    page.wait_for_function(
        "(seconds) => window.heard.some((e) => e.name === 'seam:position' && e.seconds > seconds)",
        arg=seconds,
    )


def test_stopping_a_seam_leaves_the_preview_where_the_seam_had_reached(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)
        hears(page, "opening").click()
        reached = last_position(page)

        assert preview_time(page) == pytest.approx(reached, abs=0.01)
        assert preview_time(page) > OPENING_PIECES[0][0]


def test_the_transport_key_after_a_seam_plays_the_preview_from_there(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)
        hears(page, "opening").click()
        reached = last_position(page)
        page.keyboard.press("Space")
        page.wait_for_function("!document.querySelector('[data-role=\"preview-audio\"]').paused")

        assert preview_time(page) >= reached - 0.01
        assert preview_time(page) < reached + 1.0


def test_a_seam_that_plays_to_its_end_leaves_the_preview_at_the_end_of_its_pieces(
    store, recording, segment
):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "ending").click()
        page.wait_for_function("!document.querySelector('[data-playing]')")

        assert preview_time(page) == pytest.approx(ENDING_PIECES[0][1], abs=0.05)
        assert hears(page, "ending").get_attribute("data-playing") is None


def test_the_whole_cut_plays_the_opening_then_the_ending_and_then_rests(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        page.locator('[data-role="preview-cut"]').click()
        page.wait_for_function("!document.querySelector('[data-playing]')")

        started = [e["boundary"] for e in events(page, "preview:started")]
        ended = [e["boundary"] for e in events(page, "preview:ended")]
        positions = [e["seconds"] for e in events(page, "seam:position")]
        assert started == ["punch-in", "punch-out"]
        assert ended == ["punch-in", "punch-out"]
        assert min(p for p in positions if p > 60) >= ENDING_PIECES[0][0]
        assert max(p for p in positions if p < 60) <= OPENING_PIECES[0][1] + 0.01
        assert preview_time(page) == pytest.approx(ENDING_PIECES[0][1], abs=0.05)


def test_choosing_another_seam_stops_the_first_and_plays_only_the_second(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)
        hears(page, "ending").click()
        page.wait_for_function("!document.querySelector('[data-playing]')")

        assert [e["boundary"] for e in events(page, "preview:started")] == ["punch-in", "punch-out"]
        assert [e["boundary"] for e in events(page, "preview:ended")] == ["punch-in", "punch-out"]
        assert preview_time(page) == pytest.approx(ENDING_PIECES[0][1], abs=0.05)


def test_stopping_while_a_seam_is_still_loading_plays_nothing(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page, delays={"opening": 600})
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        hears(page, "opening").click()
        page.wait_for_timeout(1500)

        assert events(page, "preview:started") == []
        assert events(page, "seam:position") == []
        assert hears(page, "opening").get_attribute("data-playing") is None
        assert preview_time(page) == 0


def test_a_seek_while_a_seam_plays_stops_it_and_the_seek_stands(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)
        page.evaluate(
            "document.dispatchEvent(new CustomEvent('waveform:seek', { detail: { seconds: 55 } }))"
        )
        settled = len(events(page, "seam:position"))
        page.wait_for_timeout(300)

        assert hears(page, "opening").get_attribute("data-playing") is None
        assert len(events(page, "seam:position")) == settled
        assert preview_time(page) == pytest.approx(55, abs=0.01)


def test_the_transport_key_pauses_and_resumes_the_seam_not_the_preview(store, recording, segment):
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)
        page.keyboard.press("Space")
        page.wait_for_timeout(100)
        paused_at = last_position(page)
        page.wait_for_timeout(300)

        assert last_position(page) == paused_at
        assert page.evaluate("document.querySelector('[data-role=\"preview-audio\"]').paused")
        assert hears(page, "opening").get_attribute("data-playing") == "true"

        page.keyboard.press("Space")
        waits_for_position_after(page, paused_at + 0.1)

        assert page.evaluate("document.querySelector('[data-role=\"preview-audio\"]').paused")


def test_the_cut_light_follows_the_seam_in_recording_time_and_lets_go_when_it_stops(
    store, recording, segment
):
    light = '[data-role="cut-light"]'
    with _browser.opens_page(store) as page:
        serves_clips(page)
        opens_review(page, recording, segment)
        hears(page, "opening").click()
        waits_for_position_after(page, OPENING_PIECES[0][0] + 0.3)

        assert page.locator(light).get_attribute("data-auditioning") == "yes"
        assert page.locator(light).get_attribute("data-state") == "before"
        offset = page.locator(f'{light} [data-field="cut-light-offset"]').text_content()
        assert offset.startswith("−") and float(offset[1:-2]) > PUNCH_IN - OPENING_PIECES[0][1] - 0.01

        hears(page, "opening").click()
        page.wait_for_timeout(100)
        shown = page.locator(f'{light} [data-field="cut-light-offset"]').text_content()
        page.wait_for_timeout(300)

        assert page.locator(light).get_attribute("data-auditioning") is None
        assert page.locator(f'{light} [data-field="cut-light-offset"]').text_content() == shown
