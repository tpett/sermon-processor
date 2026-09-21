from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Artifact, Block, Evidence, Proposal, Recording, Segment
from sermon.web import creates_app

READS = ReadsTimecode()


def peaks_for(duration):
    count = max(int(duration), 8)
    return ",".join(str((index % 10) / 10) for index in range(count))


def current_detail(store):
    recording_id = store.lists(Recording)[0].recording_id
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings/{recording_id}")
        .get_json()
    )


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
def _(recording_detail, length):
    assert recording_detail["duration"] == length.replace(":", ":")
    assert recording_detail["peaks"]


@then("every Block is drawn as a band along the waveform, coloured by its type")
def _(recording_detail):
    types = {item[0] for item in recording_detail["blocks"]}
    assert types


@then("proposed Segments are drawn as spans above the Block bands")
def _(recording_detail):
    assert recording_detail["segments"]


@then("a time ruler is shown, labelled with wall-clock time as well as elapsed time")
def _(recording_detail):
    assert recording_detail["recorded_at"]
    assert recording_detail["duration"]


@when("I select a Segment", target_fixture="recording_detail")
def _(store, segment):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings/{segment.recording_id}?segment={segment.segment_id}")
        .get_json()
    )


@then("the region between its punch-in and punch-out is visually highlighted")
def _(recording_detail):
    assert recording_detail["selected_segment_id"]


@then("the rest of the Recording is visually de-emphasised")
def _(recording_detail):
    assert recording_detail["selected_segment_id"]


@then("markers appear at each piece of evidence for the selected Segment")
def _(store, segment):
    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    assert proposals[0].evidence


@then("a speaker track is shown beneath the waveform")
def _(store):
    detail = current_detail(store)
    assert detail["blocks"] or detail["peaks"]


@then("non-speech regions such as music are visually distinct")
def _(store):
    assert any(item[0] == "music" for item in current_detail(store)["blocks"])


@when("I click a point on the waveform", target_fixture="recording_detail")
def _(store, recording):
    return (
        creates_app(store=store)
        .test_client()
        .post(f"/api/recordings/{recording.recording_id}/seek", json={"seconds": 120.0})
        .get_json()
    )


@then("playback seeks to that point")
def _(recording_detail):
    assert recording_detail["playhead_seconds"] == 120.0


@then("a playhead follows playback along the waveform")
def _(recording_detail):
    assert "playhead_seconds" in recording_detail


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


@when("I play the audio", target_fixture="recording_detail")
def _(store, recording):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings/{recording.recording_id}")
        .get_json()
    )


@then("the browser plays the preview rendition, not the source FLAC")
def _(recording_detail):
    assert recording_detail["preview_kind"] == "preview"


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
    expected = [row[0] for row in datatable[1:]]
    assert list(current_detail(store)["zoom_steps"]) == expected


@then("each step states what it is for")
def _(store):
    assert current_detail(store)["zoom_steps"]


@then("the three-second step is the one that places a cut")
def _(store):
    assert current_detail(store)["zoom_steps"][-1] == "three seconds"


@then("the punch-in, the punch-out and the length are shown to hundredths")
def _(store):
    detail = current_detail(store)
    assert detail["punch_in_seconds"] is not None
    assert detail["length_seconds"] is not None


@then("the gap between the punch-out and whatever follows is shown")
def _(store):
    assert "gap_seconds" in current_detail(store)


@then("nothing claims the boundary is correct")
def _(store):
    assert "correct" not in current_detail(store)


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
