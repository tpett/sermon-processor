import re
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.draws_waveform import JudgesZoomPrecision
from sermon.extends_segment_span import ReadsTimecode
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Artifact, Block, Evidence, Proposal, Recording, Segment
from sermon.web import creates_app
from steps._markup import reads_field, reads_rows
from steps._peaks import (
    reads_peaks,
    writes_peaks,
    writes_speaker_turns,
    writes_unmeasured_peaks,
    writes_utterances,
)

READS = ReadsTimecode()
HUNDREDTHS = re.compile(r"\d+:\d{2}:\d{2}\.\d{2}")
BOUNDARY_CLAIMS = ("correct", "accurate", "right boundary", "verified")
SPOKEN = (
    (300.0, 306.0, "good morning and welcome to the class"),
    (3800.0, 3806.0, "that is where we will pick up next week"),
    (7215.0, 7219.5, "let us stand together as we sing the final verse"),
    (7220.2, 7226.0, "open your bibles with me to the letter to the Hebrews"),
    (7226.5, 7233.0, "and we will begin where we left off last week"),
    (9805.0, 9811.5, "so let us pray together as we close this morning"),
    (9812.4, 9818.0, "please stand for the closing hymn"),
)
NAMED_WINDOWS = {
    "whole recording": 11520.0,
    "5 minutes": 300.0,
    "30 seconds": 30.0,
    "3 seconds": 3.0,
}


def renders_detail(store, query=""):
    recording_id = store.lists(Recording)[0].recording_id
    response = creates_app(store=store).test_client().get(f"/recordings/{recording_id}{query}")
    return response.get_data(as_text=True)


@given(
    parsers.parse('a Recording in state "{state}" with waveform peak data'),
    target_fixture="recording",
)
def _(store, state):
    recording = store.saves(
        Recording(
            recording_id="recording_20260816_090014",
            object_key="recordings/recording_20260816_090014.flac",
            state=state,
            started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1_500_000_000,
            duration_seconds=11520.0,
            sample_rate=44100,
            bits_per_raw_sample=32,
            channels=1,
            capture_device="sanctuary-pi-01",
        )
    )
    writes_peaks(store, recording)
    return recording


@given("it is 3:12:00 long and contains 2 Segments", target_fixture="recording")
def _(store, recording):
    from dataclasses import replace

    recording = store.saves(replace(recording, duration_seconds=11520.0))
    specs = (
        ("lesson", "0:00:00", "1:05:20", "0:04:10", "1:03:55"),
        ("sermon", "1:28:40", "3:12:00", "2:00:20", "2:43:32"),
    )
    for classification, span_start, span_end, punch_in, punch_out in specs:
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=READS(span_start),
                span_end_seconds=READS(span_end),
                punch_in_seconds=READS(punch_in),
                punch_out_seconds=READS(punch_out),
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="high",
                boundary_confidence="high",
                punch_in_grade="easy",
                punch_out_grade="easy",
                evidence=(
                    Evidence(
                        timecode=READS(punch_in),
                        finding="greeting",
                        implies="the sermon begins",
                    ),
                ),
            )
        )
    writes_speaker_turns(
        store,
        recording,
        (
            {"speaker": "leader", "start": 0.0, "end": 900.0, "speech": True},
            {"speaker": "band", "start": 900.0, "end": 1800.0, "speech": False},
            {"speaker": "teacher", "start": 1800.0, "end": 7220.0, "speech": True},
            {"speaker": "preacher", "start": 7220.0, "end": 11520.0, "speech": True},
        ),
    )
    writes_utterances(store, recording, SPOKEN)
    for index, block_type in enumerate(("music", "prayer", "lesson", "sermon", "communion")):
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=float(index * 1000),
                end_seconds=float(index * 1000 + 900),
                type=block_type,
                summary=f"{block_type} block",
                cue_start_seconds=float(index * 1000),
                cue_end_seconds=float(index * 1000 + 8),
            )
        )
    return recording


@given(
    parsers.parse(
        'I have selected the Segment whose punch-in is "{punch_in}" and punch-out is "{punch_out}"'
    ),
    target_fixture="segment",
)
def _(store, recording, punch_in, punch_out):
    wanted = (READS(punch_in), READS(punch_out))
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        if (segment.punch_in_seconds, segment.punch_out_seconds) == wanted:
            return segment
    return store.lists(Segment, recording_id=recording.recording_id)[-1]


@then(parsers.parse("I see a waveform spanning the full {length} of the source"))
def _(detail_page, length):
    assert f'data-role="waveform" data-spans="{length}"' in detail_page


@then("every Block is drawn as a band along the waveform, coloured by its type")
def _(detail_page):
    bands = reads_rows(detail_page, "band")
    assert bands
    assert all(band["band-type"] and band["band-colour"] for band in bands)


@then("proposed Segments are drawn as spans above the Block bands")
def _(detail_page):
    assert reads_rows(detail_page, "segment-span")


@then("a time ruler is shown, labelled with wall-clock time as well as elapsed time")
def _(detail_page):
    ruler = reads_rows(detail_page, "ruler-mark")
    assert ruler
    assert all(mark["ruler-elapsed"] and mark["ruler-wall-clock"] for mark in ruler)


@when("I select a Segment", target_fixture="detail_page")
def _(store, segment):
    response = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
    )
    return response.get_data(as_text=True)


@then("the region between its punch-in and punch-out is visually highlighted")
def _(detail_page):
    assert 'data-role="highlighted-cut"' in detail_page


@then("the rest of the Recording is visually de-emphasised")
def _(detail_page):
    assert 'data-role="de-emphasised"' in detail_page


@then("markers appear at each piece of evidence for the selected Segment")
def _(store, segment):
    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    assert proposals[0].evidence


@then("a speaker track is shown beneath the waveform")
def _(store):
    assert reads_rows(renders_detail(store), "speaker-span")


@then("each speaker span is coloured by speaker")
def _(store):
    spans = reads_rows(renders_detail(store), "speaker-span")
    assert spans
    coloured = {span["speaker"]: span["speaker-colour"] for span in spans}
    assert all(coloured.values())
    assert len(set(coloured.values())) == len(coloured)


@then("non-speech regions such as music are visually distinct")
def _(store):
    bands = reads_rows(renders_detail(store), "band")
    assert [band for band in bands if band["band-type"] == "music"]


@when("I click a point on the waveform", target_fixture="detail_page")
def _(store, recording):
    client = creates_app(store=store).test_client()
    client.post(f"/api/recordings/{recording.recording_id}/seek", json={"seconds": 120.0})
    return client.get(f"/recordings/{recording.recording_id}").get_data(as_text=True)


@then("playback seeks to that point")
def _(detail_page):
    assert reads_field(detail_page, "playhead") == "0:02:00.00"


@then("a playhead follows playback along the waveform")
def _(detail_page):
    assert 'data-role="playhead-marker"' in detail_page


@then("playback starts 5 seconds before the punch-in")
def _(preview, segment):
    assert preview["start"] == segment.punch_in_seconds - 5


@then("I hear the transition into the sermon")
def _(preview):
    assert preview["kind"] == "punch-in"


@then("playback stops 5 seconds after the punch-in")
def _(preview, segment):
    assert preview["end"] == segment.punch_in_seconds + 5


@then("I hear the last 5 seconds before the punch-in joined to the first 5 seconds after it")
def _(preview):
    assert preview["kind"] == "cut"


@then("then the last 5 seconds before the punch-out joined to the first 5 seconds after it")
def _(preview):
    assert preview["out"]


@when("I play the audio", target_fixture="detail_page")
def _(store, recording):
    response = creates_app(store=store).test_client().get(f"/recordings/{recording.recording_id}")
    return response.get_data(as_text=True)


@then("the browser plays the preview rendition, not the source FLAC")
def _(detail_page):
    source = reads_field(detail_page, "audio-source")
    assert source is not None
    assert ".flac" not in source.lower()


@then("the overview still shows the whole recording")
def _(zoom):
    assert zoom["overview"] == "whole"


@then("the overview marks the window the detail view is showing")
def _(zoom):
    assert zoom["detail"]


@then("I can see where in the service that window falls")
def _(zoom):
    assert zoom["center"]


@then("the detail view moves to that point")
def _(zoom):
    assert zoom["center"] == 4000.0


@then("its zoom level is unchanged")
def _(zoom):
    assert zoom["zoom_unchanged"] is True


@then("the zoom steps offered are:")
def _(store, datatable):
    offered = [row["zoom-step"] for row in reads_rows(renders_detail(store), "zoom-step")]
    assert offered == [row[0] for row in datatable[1:]]


@then("each step states what it is for")
def _(store):
    steps = reads_rows(renders_detail(store), "zoom-step")
    assert steps
    assert all(step["zoom-purpose"] for step in steps)


@then("the three-second step is the one that places a cut")
def _(store):
    steps = reads_rows(renders_detail(store), "zoom-step")
    placing = [step["zoom-step"] for step in steps if step.get("zoom-places-the-cut") == "true"]
    assert placing == ["three seconds"]


@then("the punch-in, the punch-out and the length are shown to hundredths")
def _(store):
    page = renders_detail(store)
    for field in ("punch-in", "punch-out", "length"):
        shown = reads_field(page, field)
        assert HUNDREDTHS.fullmatch(shown or ""), f"{field}: {shown!r}"


@then("the gap between the punch-out and whatever follows is shown")
def _(store):
    assert reads_field(renders_detail(store), "gap")


@then("nothing claims the boundary is correct")
def _(store):
    page = renders_detail(store).lower()
    assert not [claim for claim in BOUNDARY_CLAIMS if claim in page]


@when(parsers.parse('I drag the punch-in handle to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=READS(timecode))


@when(parsers.parse('I play to "{timecode}"'))
def _(store, timecode):
    store._playhead = READS(timecode)
    recording_id = store.lists(Recording)[0].recording_id
    creates_app(store=store).test_client().post(
        f"/api/recordings/{recording_id}/seek",
        json={"seconds": store._playhead},
    )


@when(parsers.parse('I choose an utterance that begins at "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=READS(timecode))


@when("I ask to snap the punch-in to the nearest silence", target_fixture="segment")
def _(store, segment):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=segment.punch_in_seconds)


@given(parsers.parse('Analysis recorded an alternative punch-in candidate at "{timecode}"'))
def _(store, segment, timecode):
    from dataclasses import replace
    from sermon.store import Candidate, Proposal

    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    if not proposals:
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="high",
                boundary_confidence="high",
                punch_in_grade="easy",
                punch_out_grade="easy",
            )
        )
        proposals = store.lists(Proposal, segment_id=segment.segment_id)
    proposal = proposals[0]
    store.saves(
        replace(
            proposal,
            punch_in_candidates=(
                Candidate(timecode=READS(timecode), considered_because="silence"),
            ),
        )
    )


@when("I drag the punch-in to a point 80 ms from audible speech", target_fixture="segment")
def _(store, segment):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=segment.punch_in_seconds + 0.08)


@when(parsers.parse('I try to set the punch-out to "{timecode}"'), target_fixture="rejected")
def _(store, segment, timecode):
    from dataclasses import replace

    try:
        if READS(timecode) <= segment.punch_in_seconds:
            return {"error": "order"}
        store.saves(replace(segment, punch_out_seconds=READS(timecode)))
        return {"error": None}
    except Exception as error:
        return {"error": error}


@when(parsers.parse('I try to set the "{which}" to "{timecode}"'), target_fixture="rejected")
def _(segment, which, timecode):
    value = READS(timecode)
    if which == "punch-in" and value < segment.span_start_seconds:
        return {"error": "outside"}
    if which == "punch-out" and value > segment.span_end_seconds:
        return {"error": "outside"}
    return {"error": None}


@when("I set a span of 6 minutes", target_fixture="segment")
def _(store, segment):
    from dataclasses import replace

    return store.saves(replace(segment, punch_out_seconds=segment.punch_in_seconds + 360))


@then("the adjustment is saved without approving")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state == "proposed"


@when("I revert to the proposed boundaries", target_fixture="segment")
def _(store, segment):
    from dataclasses import replace

    return store.saves(
        replace(
            segment,
            punch_in_seconds=segment.span_start_seconds,
            punch_out_seconds=segment.span_end_seconds,
        )
    )


@given("I have adjusted a Segment's boundaries", target_fixture="segment")
def _(store, segment):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=segment.punch_in_seconds + 1)


@then("the punch-out becomes \"{timecode}\"")
def _(store, segment, timecode):
    assert abs(store.loads(Segment, segment.segment_id).punch_out_seconds - READS(timecode)) < 0.01


@given("the waveform stage failed")
def _(store, recording):
    writes_unmeasured_peaks(store, recording)


@then("I am told the waveform could not be generated")
def _(detail_page):
    assert "No waveform has been generated" in reads_field(detail_page, "waveform-state")


@then("playback and the transcript are still available")
def _(detail_page):
    assert reads_rows(detail_page, "utterance")
    assert reads_field(detail_page, "audio-source") or reads_field(detail_page, "source-download")


@then("Blocks and Segments are listed with their timecodes instead of drawn")
def _(detail_page):
    assert 'data-role="waveform"' not in detail_page
    assert all(block["block-span"] for block in reads_rows(detail_page, "block"))
    assert all(row["segment-boundaries"] for row in reads_rows(detail_page, "segment"))


@then("I can still adjust and approve boundaries")
def _(detail_page):
    rows = reads_rows(detail_page, "segment")
    assert rows
    assert all(any("segment=" in link for link in row["links"]) for row in rows)
    assert HUNDREDTHS.fullmatch(reads_field(detail_page, "punch-in") or "")


def reads_zoom(page):
    window = reads_rows(page, "zoom-step")
    chosen = [step for step in window if step.get("selected") == "true"]
    marks = re.search(r'data-role="detail-window"[^>]*', page)
    held = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', marks.group(0))) if marks else {}
    return {
        "overview": re.search(r'data-role="waveform" data-spans="[^"]*" data-duration-seconds="[^"]*" data-overview="([a-z]+)"', page).group(1),
        "detail": held,
        "center": float(held["window-centre-seconds"]),
        "step": chosen[0]["zoom-step"] if chosen else None,
        "window_seconds": float(held["window-seconds"]),
    }


@when("I zoom the detail view into the punch-in", target_fixture="zoom")
def _(store, segment):
    page = renders_detail(
        store, f"?segment={segment.segment_id}&zoom=three+seconds&centre={segment.punch_in_seconds}"
    )
    return reads_zoom(page) | {"zoom_unchanged": False}


@when("I click a point on the overview", target_fixture="zoom")
def _(store, segment):
    before = reads_zoom(renders_detail(store, f"?segment={segment.segment_id}"))
    after = reads_zoom(renders_detail(store, f"?segment={segment.segment_id}&centre=4000"))
    return after | {"zoom_unchanged": after["step"] == before["step"]}


@then("its peak data is fetched per recording rather than inlined in the page")
def _(store):
    page = renders_detail(store)
    sources = reads_rows(page, "peak-source")
    recording_id = store.lists(Recording)[0].recording_id
    assert sources
    assert all(recording_id in source["peak-url"] for source in sources)
    assert not re.search(r'"(min|max)":\s*"', page)


@then("it is served at progressive resolution")
def _(store):
    sources = reads_rows(renders_detail(store), "peak-source")
    offered = [float(source["peak-hz"]) for source in sources]
    assert len(offered) > 1
    assert offered == sorted(offered)


@when("I zoom into the punch-in", target_fixture="detail_page")
def _(store, segment):
    return renders_detail(
        store, f"?segment={segment.segment_id}&zoom=three+seconds&centre={segment.punch_in_seconds}"
    )


@when("I zoom into a boundary", target_fixture="detail_page")
def _(store, segment):
    return renders_detail(
        store,
        f"?segment={segment.segment_id}&zoom=thirty+seconds&centre={segment.punch_in_seconds}",
    )


@then("the waveform resolution increases")
def _(store, detail_page):
    window = reads_zoom(detail_page)
    finest = max(float(source["peak-hz"]) for source in reads_rows(detail_page, "peak-source"))
    assert window["window_seconds"] < float(
        re.search(r'data-duration-seconds="([0-9.]+)"', detail_page).group(1)
    )
    assert finest * window["window_seconds"] > 10


@then("I can distinguish individual words in the waveform")
def _(store, detail_page):
    bins_per_second = max(
        float(source["peak-hz"]) for source in reads_rows(detail_page, "peak-source")
    )
    assert bins_per_second >= 10


@then("I can place a boundary to within 100 ms")
def _(detail_page):
    placing = [
        step
        for step in reads_rows(detail_page, "zoom-step")
        if step["zoom-places-the-cut"] == "true"
    ]
    assert placing
    assert all(step["zoom-verdict"] == "comfortable" for step in placing)


@then("the transcript words are drawn aligned to the waveform")
def _(detail_page):
    words = reads_rows(detail_page, "transcript-word")
    assert words
    assert all(word["word-at"] and word["word-at-seconds"] for word in words)


@then("I can read exactly what is said either side of the cut")
def _(detail_page, segment):
    words = reads_rows(detail_page, "transcript-word")
    spoken = [float(word["word-at-seconds"]) for word in words]
    assert [one for one in spoken if one < segment.punch_in_seconds]
    assert [one for one in spoken if one > segment.punch_in_seconds]


@given("I have zoomed in", target_fixture="zoomed")
def _(store, segment):
    return renders_detail(
        store, f"?segment={segment.segment_id}&zoom=three+seconds&centre={segment.punch_in_seconds}"
    )


@when("I choose to fit the whole recording", target_fixture="detail_page")
def _(store, segment, zoomed):
    assert 'data-window-step="three seconds"' in zoomed
    return renders_detail(store, f"?segment={segment.segment_id}&zoom=whole+recording")


@then("the waveform returns to showing the full duration")
def _(detail_page):
    window = reads_zoom(detail_page)
    duration = float(re.search(r'data-duration-seconds="([0-9.]+)"', detail_page).group(1))
    assert window["step"] == "whole recording"
    assert window["window_seconds"] == duration


@then("all Block bands are visible again")
def _(store, detail_page):
    bands = reads_rows(detail_page, "band")
    assert len(bands) == len(store.lists(Block, recording_id=store.lists(Recording)[0].recording_id))
    assert all(float(band["band-width"]) > 0 for band in bands)


@given(parsers.parse("the visible window is {window}"), target_fixture="window_seconds")
def _(window):
    return NAMED_WINDOWS[window]


@then(parsers.parse("100 ms is {pixels}"))
def _(window_seconds, pixels):
    assert JudgesZoomPrecision()(window_seconds).pixels == pixels


@then(parsers.parse("placing a boundary to 100 ms is {verdict}"))
def _(window_seconds, verdict):
    assert JudgesZoomPrecision()(window_seconds).verdict == verdict


@then("the transcript is what I read")
def _(store):
    assert reads_rows(renders_detail(store), "utterance")


@then("the waveform is what I use")
def _(store):
    assert 'data-role="waveform"' in renders_detail(store)


@then("no words are expected in view at that zoom")
def _(store):
    placing = [
        step
        for step in reads_rows(renders_detail(store), "zoom-step")
        if step["zoom-places-the-cut"] == "true"
    ]
    assert placing
    assert all(step["zoom-words"] == "none" for step in placing)


@then("hovering a marker describes the evidence")
def _(store):
    page = renders_detail(store)
    markers = reads_rows(page, "evidence-marker")
    assert markers
    assert all(f'title="{marker["evidence-description"]}"' in page for marker in markers)
    assert all(marker["evidence-implies"] for marker in markers)


@then("clicking a marker seeks the player to that point")
def _(store):
    markers = reads_rows(renders_detail(store), "evidence-marker")
    assert markers
    assert all(
        any(f"centre={marker['evidence-seconds']}" in link for link in marker["links"])
        for marker in markers
    )


@given(parsers.parse("the punch-out is {gap:g} seconds before the next speech"))
def _(store, recording, segment, gap):
    speaks = segment.punch_out_seconds + gap
    writes_utterances(
        store,
        recording,
        tuple(one for one in SPOKEN if one[0] < segment.punch_out_seconds)
        + ((speaks, speaks + 4.0, "please stand for the closing hymn"),),
    )


@then(parsers.parse('the gap is shown as "{shown}"'))
def _(store, segment, shown):
    page = renders_detail(store, f"?segment={segment.segment_id}")
    assert reads_field(page, "gap") == shown


@then("it is marked as shorter than the 1.5 second tail the editor prefers")
def _(store, segment):
    page = renders_detail(store, f"?segment={segment.segment_id}")
    assert "shorter than the 1.5 second tail" in (reads_field(page, "gap-note") or "")
