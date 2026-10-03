import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment, ReviewSession
from sermon.extends_segment_span import ReadsTimecode
from sermon.reopens_segment import ReopensSegment
from sermon.settles_recording import SettlesRecording
from sermon.shows_recording import NOTICES, formats_precise
from sermon.skips_segment import SkipsSegment
from sermon.store import Block, Job, LogEntry, Proposal, Recording, Segment
from sermon.web import creates_app
from steps import _audio, _browser, _forms, _web
from steps._markup import reads_field, reads_role, reads_rows
from steps._peaks import writes_peaks, writes_utterances

READS = ReadsTimecode()
PREVIEW_SECONDS = 11520.0
CUE_LEAD_SECONDS = 20.0
CUE_SECONDS = 3.0
A_FEW_SECONDS = 15.0


def renders_detail(store, recording):
    response = creates_app(store=store).test_client().get(f"/recordings/{recording.recording_id}")
    return response.get_data(as_text=True)


@pytest.fixture
def review_session():
    return ReviewSession()


def parses_boundaries(text):
    start, end = text.split(" – ")
    return READS(start.strip()), READS(end.strip())


@given(
    parsers.parse('a Recording in state "{state}" containing {count:d} Segments:'),
    target_fixture="recording",
)
def _(store, state, count, datatable):
    stored = store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state=state,
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=PREVIEW_SECONDS,
        )
    )
    writes_peaks(store, stored)
    rows = datatable[1:]
    assert len(rows) == count
    for _, classification, boundaries, confidence in rows:
        start, end = parses_boundaries(boundaries)
        segment = store.saves(
            Segment(
                recording_id=stored.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=start,
                span_end_seconds=end,
                punch_in_seconds=start,
                punch_out_seconds=end,
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence=confidence,
                boundary_confidence=confidence,
                punch_in_grade="moderate",
                punch_out_grade="moderate",
            )
        )
    _audio.registers_preview(store, stored, PREVIEW_SECONDS)
    return stored


@given("its remaining Blocks are music, prayer, qa and communion")
def _(store, recording):
    start = 0.0
    for block_type in ("music", "prayer", "qa", "communion"):
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=start,
                end_seconds=start + 60.0,
                type=block_type,
                summary=f"the {block_type}",
                cue_start_seconds=start + CUE_LEAD_SECONDS,
                cue_end_seconds=start + CUE_LEAD_SECONDS + CUE_SECONDS,
            )
        )
        start += 60.0


@given(
    parsers.parse('a Segment classified "{classification}" whose cuts are both graded "{grade}"'),
    target_fixture="segment",
)
def _(store, recording, classification, grade):
    segment = [
        item
        for item in store.lists(Segment, recording_id=recording.recording_id)
        if item.classification == classification
    ][0]
    proposal = store.lists(Proposal, segment_id=segment.segment_id)[0]
    store.saves(replace(proposal, punch_in_grade=grade, punch_out_grade=grade))
    return segment


@when("I preview the punch-in")
def _(review_session, segment):
    review_session.previews_punch_in(segment)


@when("I preview the punch-out")
def _(review_session, segment):
    review_session.previews_punch_out(segment)


@when("I approve")
def _(store, segment, clock):
    ApprovesSegment(store=store, clock=clock)(segment)


@then("the Segment is queued for processing")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert len(jobs) == 1
    assert jobs[0].state == "queued"
    assert store.loads(Segment, segment.segment_id).state == "approved"


@then("I did not have to open the waveform editor")
def _(review_session):
    assert review_session.waveform_editor_opened is False


def numbered_segment(store, recording, number):
    segments = sorted(
        store.lists(Segment, recording_id=recording.recording_id),
        key=lambda item: item.span_start_seconds,
    )
    return segments[number - 1]


@when(parsers.parse("I approve Segment {number:d}"))
def _(store, recording, number, clock):
    ApprovesSegment(store=store, clock=clock)(numbered_segment(store, recording, number))


@when(parsers.parse("I skip Segment {number:d}"))
def _(store, recording, number, clock):
    SkipsSegment(store=store, clock=clock)(numbered_segment(store, recording, number))


@then(parsers.parse('Segment {number:d} enters "{state}" and is queued for processing'))
def _(store, recording, number, state):
    segment = numbered_segment(store, recording, number)
    assert store.loads(Segment, segment.segment_id).state == state
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert jobs[0].state == "queued"


@then(parsers.parse('Segment {number:d} enters "{state}"'))
def _(store, recording, number, state):
    segment = numbered_segment(store, recording, number)
    assert store.loads(Segment, segment.segment_id).state == state


@then("exactly one MP3 will be produced")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len(jobs) == 1


@then("two separate processing jobs are queued")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len(jobs) == 2


@then("two separate MP3s will be produced")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert len({job.segment_id for job in jobs}) == 2


@then("each carries its own publication details")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert len(segments) == 2


@then("its boundaries, classification, confidence and evidence remain stored")
def _(store, recording):
    segment = numbered_segment(store, recording, 1)
    assert segment.punch_in_seconds
    assert segment.classification
    assert store.lists(Proposal, segment_id=segment.segment_id)


@then("it remains visible on the Recording detail view")
def _(store, recording):
    rows = reads_rows(renders_detail(store, recording), "segment")
    assert [row for row in rows if row["segment-state"] == "skipped"]


@then("I see every Block in order with its type and its one-line summary")
def _(store, recording):
    blocks = sorted(store.lists(Block, recording_id=recording.recording_id), key=lambda one: one.start_seconds)
    rows = reads_rows(renders_detail(store, recording), "block")
    assert [row["block-type"] for row in rows] == [block.type for block in blocks]
    assert all(row["block-summary"] for row in rows)


@then("I can see the whole shape of the service without playing anything")
def _(store, recording):
    page = renders_detail(store, recording)
    assert all(row["block-span"] for row in reads_rows(page, "block"))


@then("the music Blocks are shown in the anatomy of the Recording")
def _(store, recording):
    rows = reads_rows(renders_detail(store, recording), "block")
    assert [row for row in rows if row["block-type"] == "music"]


@then("no Segment was proposed for them")
def _(store, recording):
    segments = store.lists(Segment, recording_id=recording.recording_id)
    assert [one for one in segments if one.classification == "music"] == []


@then("nothing offers them for publication")
def _(store, recording):
    rows = reads_rows(renders_detail(store, recording), "segment")
    assert [row for row in rows if row["classification"] == "music"] == []


@then("I can approve it at any point in the future")
def _(store, recording):
    segment = numbered_segment(store, recording, 1)
    assert segment.state == "skipped"



@then("I am told the punch-in needs checking and why")
def _(store, segment):
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{store.loads(Segment, segment.segment_id).recording_id}"
             f"?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    said = reads_field(page, "needs-checking-punch-in")
    assert said, "the page said nothing about the punch-in needing a look"
    assert "punch-in" in said, said
    grade = store.lists(Proposal, segment_id=segment.segment_id)[0].punch_in_grade
    assert grade in said, said
@given('a Recording returned to "awaiting_review" by a revisit', target_fixture="revisited")
def _(store, recording, clock):
    skips = SkipsSegment(store=store, clock=clock)
    skipped = [skips(one) for one in store.lists(Segment, recording_id=recording.recording_id)]
    assert store.loads(Recording, recording.recording_id).state == "reviewed"
    return ReopensSegment(store=store, clock=clock)(skipped[0])


@when("I dispose of that Segment", target_fixture="detail_page")
def _(store, revisited, clock):
    return _web.posts(store, _web.segment_action(revisited, "skip"), clock=clock)


@then('the Recording returns to "reviewed"')
def _(store, revisited, detail_page):
    assert reads_field(detail_page, "state") == "reviewed"
    assert store.loads(Recording, revisited.recording_id).state == "reviewed"


@given(parsers.parse('a proposed Segment classified "{classification}"'), target_fixture="segment")
def _(store, classification):
    recording = store.saves(
        Recording(
            recording_id="recording_20260920_094416",
            object_key="recordings/recording_20260920_094416.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 20, 9, 44, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=10000.0,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=100.0,
            span_end_seconds=900.0,
            punch_in_seconds=100.0,
            punch_out_seconds=900.0,
        )
    )


@when(parsers.parse('I reclassify it as "{classification}"'), target_fixture="detail_page")
def _(store, segment, classification):
    return _web.posts(
        store,
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/classify",
        classification=classification,
    )


@then(parsers.parse('the Segment is classified "{classification}"'))
def _(store, segment, classification):
    assert store.loads(Segment, segment.segment_id).classification == classification


@then("the change is recorded against the Segment")
def _(store, segment):
    kinds = [e.kind for e in store.lists(LogEntry, segment_id=segment.segment_id)]
    assert "classification_change" in kinds, kinds


@then("its boundaries are unchanged")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (
        segment.punch_in_seconds,
        segment.punch_out_seconds,
    )


@when("I try to reclassify it", target_fixture="detail_page")
def _(store, segment):
    return _web.posts(
        store,
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/classify",
        classification="meeting",
    )


@then("the classification is unchanged")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).classification == segment.classification


@then("I am told it can no longer be reclassified")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == (
        "a Segment that has been approved cannot be reclassified"
    )


@given(parsers.parse('a rendered Segment classified "{classification}"'), target_fixture="segment")
def _(store, classification):
    recording = store.saves(
        Recording(
            recording_id="recording_20260920_094416",
            object_key="recordings/recording_20260920_094416.flac",
            state="reviewed",
            started_at=datetime(2026, 9, 20, 9, 44, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=10000.0,
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="complete",
            span_start_seconds=100.0,
            span_end_seconds=900.0,
            punch_in_seconds=100.0,
            punch_out_seconds=900.0,
        )
    )


@then("it still appears as needing attention")
def _(store, recording):
    client = creates_app(store=store).test_client()
    for query in ("", "?filter=Needs attention"):
        rows = reads_rows(client.get(f"/{query}").get_data(as_text=True), "recording")
        listed = [row for row in rows if row["id"] == recording.recording_id]
        assert listed and listed[0]["attention"] == "true", query


@then("I am not forced to disposition everything in one sitting")
def _(store, recording):
    untouched = numbered_segment(store, recording, 1)
    page = _web.opens_detail(store, recording.recording_id, segment=untouched.segment_id)
    offered = [row["action"] for row in reads_rows(page, "segment-action")]
    assert {"Approve", "Skip"} <= set(offered)
    states = {row["segment"]: row["state"] for row in reads_rows(page, "segment")}
    assert states[str(untouched.segment_id)] == "proposed"


@then("approving is available without any further step")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    approving = 'data-field="action-control">Approve'
    assert page.index(approving) < page.index("<h3>Boundaries</h3>")
    approved = _forms.submits(store, page, approving)
    assert reads_field(approved, "action-notice") == NOTICES["approved"]
    reopened = _forms.submits(store, approved, 'data-field="action-control">Cancel processing')
    assert reads_field(reopened, "action-notice") == NOTICES["reopened"]


@then("boundary editing is available but not required")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "boundary-controls") in {"editable", "collapsed"}
    assert [row["boundary"] for row in reads_rows(page, "boundary")] == ["punch-in", "punch-out"]


SPOKEN_ACROSS_THE_MORNING = (
    (600.0, 606.0, "turn with me to the second chapter of Ruth"),
    (5400.0, 5406.0, "let us stand and sing together"),
    (7200.0, 7206.0, "good morning, open your bibles to Hebrews twelve"),
    (9600.0, 9606.0, "let us pray as we close"),
)


@given("I have selected a Segment", target_fixture="segment")
def _(store, recording):
    writes_utterances(store, recording, SPOKEN_ACROSS_THE_MORNING)
    return numbered_segment(store, recording, 2)


@when("I read the transcript", target_fixture="detail_page")
def _(store, segment):
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


@then("I see the transcript for that Segment")
def _(detail_page):
    assert [row["utterance-text"] for row in reads_rows(detail_page, "utterance")] == [
        "good morning, open your bibles to Hebrews twelve",
        "let us pray as we close",
    ]


@then("I can expand to the full Recording transcript if I want it")
def _(detail_page):
    expander = re.search(r'<details\b([^>]*)data-role="full-transcript"([^>]*)>', detail_page)
    assert expander, "no expander offers the whole Recording's transcript"
    assert " open" not in "".join(expander.groups()), "the whole transcript is forced open"
    assert [row["utterance-text"] for row in reads_rows(detail_page, "recording-utterance")] == [
        text for _, _, text in SPOKEN_ACROSS_THE_MORNING
    ]


@then("all Blocks are drawn on a single waveform of the whole Recording")
def _(store, recording, detail_page):
    assert detail_page.count('data-role="waveform"') == 1
    drawn = reads_role(detail_page, "waveform")
    assert float(drawn["duration-seconds"]) == recording.duration_seconds
    stored = sorted(store.lists(Block, recording_id=recording.recording_id), key=lambda b: b.start_seconds)
    assert [band["band-type"] for band in reads_rows(detail_page, "band")] == [
        block.type for block in stored
    ]


@then("each is coloured by its type")
def _(detail_page):
    colours = {}
    for band in reads_rows(detail_page, "band"):
        colours.setdefault(band["band-type"], set()).add(band["band-colour"])
    assert all(len(held) == 1 for held in colours.values())
    assert len({next(iter(held)) for held in colours.values()}) == len(colours)


@then("proposed Segments are drawn as spans above the Blocks they cover")
def _(store, recording, detail_page):
    proposed = sorted(
        (item for item in store.lists(Segment, recording_id=recording.recording_id) if item.state == "proposed"),
        key=lambda item: item.punch_in_seconds,
    )
    spans = reads_rows(detail_page, "segment-span")
    assert [int(span["segment"]) for span in spans] == [item.segment_id for item in proposed]
    for span, segment in zip(spans, proposed):
        left = re.search(r"left:([0-9.]+)%", detail_page.split(f'data-row="segment-span" data-segment="{segment.segment_id}"')[1]).group(1)
        assert abs(float(left) - 100.0 * segment.punch_in_seconds / recording.duration_seconds) < 0.01
    assert detail_page.index('class="spans"') < detail_page.index('class="bands"')


@then("clicking one selects it for review")
def _(store, recording):
    first = numbered_segment(store, recording, 1)
    chosen = numbered_segment(store, recording, 2)
    with _browser.opens_page(store) as page:
        page.goto(f"/recordings/{recording.recording_id}?segment={first.segment_id}")
        with page.expect_navigation(timeout=5000):
            page.locator(f'[data-row="segment-span"][data-segment="{chosen.segment_id}"]').click()
        selected = page.locator('[data-row="segment"][data-selected="true"]')
        assert selected.get_attribute("data-segment") == str(chosen.segment_id)
        assert page.locator('[data-field="punch-in"]').text_content() == formats_precise(
            chosen.punch_in_seconds
        )


def auditions(store, recording, control):
    """Press a control beside a Block in Chromium and watch the audio element answer."""
    prayer = [
        block for block in store.lists(Block, recording_id=recording.recording_id) if block.type == "prayer"
    ][0]
    with _browser.opens_page(store) as page:
        page.goto(f"/recordings/{recording.recording_id}")
        row = page.locator('[data-row="block"][data-block-type="prayer"]')
        page.locator("audio").evaluate("audio => audio.muted = true")
        row.locator(f'[data-role="{control}"]').click()
        page.wait_for_function("() => !document.querySelector('audio').paused", timeout=5000)
        began = page.evaluate("() => document.querySelector('audio').currentTime")
        if control == "preview-cue-excerpt":
            page.wait_for_function(
                "() => document.querySelector('audio').paused", timeout=(CUE_SECONDS + 4) * 1000
            )
        else:
            page.wait_for_timeout(1000)
        held = page.evaluate(
            "() => ({at: document.querySelector('audio').currentTime,"
            " paused: document.querySelector('audio').paused})"
        )
        excerpt = row.locator('[data-role="preview-cue-excerpt"]')
        return {
            "block": prayer,
            "began": began,
            "ended": held["at"],
            "still_playing": not held["paused"],
            "excerpt": (float(excerpt.get_attribute("data-start")), float(excerpt.get_attribute("data-end"))),
        }


@when("I press Preview on a Block", target_fixture="audition")
def _(store, recording):
    return auditions(store, recording, "preview-cue-excerpt")


@then("playback starts at that Block's cue excerpt")
def _(audition):
    assert audition["excerpt"][0] == audition["block"].cue_start_seconds
    assert abs(audition["began"] - audition["block"].cue_start_seconds) < 0.5


@then("it stops at the end of the excerpt")
def _(audition):
    assert not audition["still_playing"]
    assert audition["block"].cue_end_seconds <= audition["ended"] < audition["block"].cue_end_seconds + 0.5


@then("a few seconds is enough for me to recognise what the Block is")
def _(audition):
    start, end = audition["excerpt"]
    assert 0 < end - start <= A_FEW_SECONDS


@when("I choose to start playback at a specific Block", target_fixture="audition")
def _(store, recording):
    return auditions(store, recording, "start-at-block")


@then("playback seeks there rather than to the cue excerpt")
def _(audition):
    assert abs(audition["began"] - audition["block"].start_seconds) < 0.5
    assert audition["block"].start_seconds != audition["block"].cue_start_seconds
    assert audition["still_playing"]


@then("the waveform and the nudge controls are offered")
def _(store, segment, device):
    with _browser.opens_page(store, device) as page:
        page.goto(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        assert page.locator('[data-role="detail"]').is_visible(), "no waveform on this device"
        summary = page.locator("details.nudges > summary").first
        assert summary.is_visible(), "the nudge controls cannot be opened on this device"
        summary.evaluate("summary => summary.parentElement.open = true")
        nudges = page.locator('[data-field="nudge-control"]')
        assert nudges.count() > 0, "no nudge control on this device"
        assert nudges.first.is_visible(), "the nudge controls are hidden on this device"


@then("the page fits the phone's width without scrolling sideways")
def _(store, segment, device):
    with _browser.opens_page(store, device) as page:
        page.goto(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        wide = page.evaluate("() => document.documentElement.scrollWidth")
        assert wide <= device["viewport"]["width"], f"{wide}px of page on a {device['viewport']['width']}px screen"


@then("I can still skip it, or approve it as-is if I choose to")
def _(store, segment, device):
    with _browser.opens_page(store, device) as page:
        page.goto(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        for action in ("Skip", "Approve"):
            control = page.locator(
                f'[data-row="segment-action"][data-action="{action}"] [data-field="action-control"]'
            )
            assert control.is_visible(), f"{action} is not offered on this device"
            box = control.bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= device["viewport"]["width"], box
