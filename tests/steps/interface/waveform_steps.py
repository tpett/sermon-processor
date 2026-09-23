import re
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Artifact, Block, Evidence, Proposal, Recording, Segment
from sermon.web import creates_app
from steps import _audio
from steps._markup import reads_field, reads_rows

READS = ReadsTimecode()
HUNDREDTHS = re.compile(r"\d+:\d{2}:\d{2}\.\d{2}")
BOUNDARY_CLAIMS = ("correct", "accurate", "right boundary", "verified")


def peaks_for(duration):
    count = max(int(duration), 8)
    return ",".join(str((index % 10) / 10) for index in range(count))


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
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="waveform_peaks",
            path="peaks.json",
            size_bytes=count_bytes(11520),
            checksum=peaks_for(11520),
        )
    )
    _audio.registers_preview(store, recording)
    return recording


def count_bytes(duration):
    return int(duration)


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
