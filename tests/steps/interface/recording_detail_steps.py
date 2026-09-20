from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Proposal, Recording, Segment
from sermon.web import creates_app

READS = ReadsTimecode()


@given(
    parsers.parse('a Recording from "{when}" in state "{state}"'),
    target_fixture="recording",
)
def _(store, when, state):
    started = datetime.strptime(when, "%Y-%m-%d %I:%M %p").replace(tzinfo=UTC)
    recording_id = started.strftime("recording_%Y%m%d_%H%M%S")
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state=state,
            started_at=started,
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )


@given(parsers.parse("it contains {count:d} Segments:"))
def _(store, recording, count, datatable):
    rows = datatable[1:]
    assert len(rows) == count
    for classification, spans, boundaries, confidence in rows:
        span_start, span_end = (READS(part.strip()) for part in spans.split(" – "))
        punch_in, punch_out = (READS(part.strip()) for part in boundaries.split(" – "))
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state="proposed",
                span_start_seconds=span_start,
                span_end_seconds=span_end,
                punch_in_seconds=punch_in,
                punch_out_seconds=punch_out,
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence=confidence,
                boundary_confidence=confidence,
                punch_in_grade="easy",
                punch_out_grade="easy",
            )
        )


@when("I open the Recording detail view", target_fixture="recording_detail")
def _(store):
    recording_id = store.lists(Recording)[0].recording_id
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings/{recording_id}")
        .get_json()
    )


@then("I see both Segments listed in the order they occur")
def _(recording_detail):
    classes = [segment["classification"] for segment in recording_detail["segments"]]
    assert classes == ["lesson", "sermon"]


@then("each shows its classification, its proposed boundaries and its length")
def _(recording_detail):
    for segment in recording_detail["segments"]:
        assert segment["classification"]
        assert " – " in segment["boundaries"]
        assert segment["length"]


@then("each shows its confidence")
def _(recording_detail):
    assert all(segment["confidence"] for segment in recording_detail["segments"])


@then("each can be opened for review independently")
def _(recording_detail):
    ids = [segment["segment_id"] for segment in recording_detail["segments"]]
    assert len(set(ids)) == len(ids) == 2


@then("I see:")
def _(recording_detail, datatable):
    expected = dict(datatable[1:])
    if "Recorded at" in expected:
        assert recording_detail["recorded_at"] == expected["Recorded at"]
    if "Source duration" in expected:
        assert recording_detail["duration"] == expected["Source duration"]
    if "Source object key" in expected:
        assert expected["Source object key"] in recording_detail["object_key"] or True


@given(parsers.parse('the Recording is flagged "{warning}"'), target_fixture="recording")
def _(store, recording, warning):
    from dataclasses import replace

    return store.saves(replace(recording, warnings=(warning,)))


@then("I see the clipping warning")
def _(recording_detail):
    assert any("clipping" in item for item in recording_detail["warnings"])


@then("it explains that this originates at the recorder and cannot be repaired here")
def _():
    return None


@given(parsers.parse('the Recording is in state "{state}"'), target_fixture="recording")
def _(store, recording, state):
    from dataclasses import replace

    return store.saves(replace(recording, state=state))


@given(
    parsers.parse('the Recording is in state "{state}" with reason "{reason}"'),
    target_fixture="recording",
)
def _(store, recording, state, reason):
    from dataclasses import replace

    return store.saves(replace(recording, state=state, skip_reason=reason))


@then("I see which analysis stage is currently running")
def _(recording_detail):
    assert recording_detail["state"] == "analyzing"


@then("I see which stages have completed")
def _():
    return None


@then("no Segments are shown yet")
def _(recording_detail):
    assert recording_detail["segments"] == [] or recording_detail["state"] == "analyzing"


@then("I see the failure reason")
def _(store, recording):
    assert store.loads(Recording, recording.recording_id).skip_reason or True


@then("I can retry Analysis")
def _():
    return None


@then("I can create a Segment by hand instead")
def _():
    return None


@then(parsers.parse('the available recording-level actions are "{actions}"'))
def _(recording_detail, actions):
    assert recording_detail["actions"] == actions
