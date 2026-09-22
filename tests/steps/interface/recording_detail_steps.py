from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Proposal, Recording, Segment
from sermon.web import creates_app
from steps._markup import reads_field, reads_pairs, reads_rows

READS = ReadsTimecode()
RECORDER_LAG_SECONDS = 4


def renders_detail(store, recording_id=None, query=""):
    if recording_id is None:
        recording_id = store.lists(Recording)[0].recording_id
    response = creates_app(store=store).test_client().get(f"/recordings/{recording_id}{query}")
    return response.get_data(as_text=True)


@given(
    parsers.parse('a Recording from "{when}" in state "{state}"'),
    target_fixture="recording",
)
def _(store, when, state):
    scheduled = datetime.strptime(when, "%Y-%m-%d %I:%M %p").replace(tzinfo=UTC)
    started = scheduled + timedelta(seconds=RECORDER_LAG_SECONDS)
    recording_id = started.strftime("recording_%Y%m%d_%H%M%S")
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state=state,
            started_at=started,
            started_at_source="key",
            size_bytes=1_500_000_000,
            duration_seconds=11520.0,
            sample_rate=44100,
            bits_per_raw_sample=32,
            channels=1,
            capture_device="sanctuary-pi-01",
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


@when("I open the Recording detail view", target_fixture="detail_page")
def _(store):
    return renders_detail(store)


@then("I see:")
def _(detail_page, datatable):
    shown = reads_pairs(detail_page)
    for label, value in datatable[1:]:
        assert shown.get(label) == value, f"{label}: {shown.get(label)!r}"


@then("I see both Segments listed in the order they occur")
def _(detail_page):
    rows = reads_rows(detail_page, "segment")
    assert [row["classification"] for row in rows] == ["lesson", "sermon"]


@then("each shows its classification, its proposed boundaries and its length")
def _(detail_page):
    rows = reads_rows(detail_page, "segment")
    assert rows
    for row in rows:
        assert row["segment-classification"]
        assert " – " in row["segment-boundaries"]
        assert row["segment-length"]


@then("each shows its confidence")
def _(detail_page):
    rows = reads_rows(detail_page, "segment")
    assert rows
    assert all(row["segment-confidence"] for row in rows)


@then("each can be opened for review independently")
def _(detail_page):
    rows = reads_rows(detail_page, "segment")
    opened = {link for row in rows for link in row["links"] if "segment=" in link}
    assert len(opened) == len(rows) == 2


@given(parsers.parse('the Recording is flagged "{warning}"'), target_fixture="recording")
def _(store, recording, warning):
    return store.saves(replace(recording, warnings=(warning,)))


@then("I see the clipping warning")
def _(detail_page):
    warnings = [row["warning"] for row in reads_rows(detail_page, "warning")]
    assert any("clipping" in warning for warning in warnings)


@then("it explains that this originates at the recorder and cannot be repaired here")
def _(detail_page):
    explanation = reads_field(detail_page, "warning-origin")
    assert "originate at the recorder" in explanation
    assert "cannot be repaired here" in explanation


@given(parsers.parse('the Recording is in state "{state}"'), target_fixture="recording")
def _(store, recording, state):
    return store.saves(replace(recording, state=state))


@given(
    parsers.parse('the Recording is in state "{state}" with reason "{reason}"'),
    target_fixture="recording",
)
def _(store, recording, state, reason):
    return store.saves(replace(recording, state=state, skip_reason=reason))


@then("I see which analysis stage is currently running")
def _(detail_page):
    assert reads_field(detail_page, "state") == "analyzing"
    assert "Analysis is running" in reads_field(detail_page, "progress")


@then("no Segments are shown yet")
def _(detail_page):
    assert reads_rows(detail_page, "segment") == []


@then(parsers.parse('the available recording-level actions are "{actions}"'))
def _(detail_page, actions):
    offered = [row["action"] for row in reads_rows(detail_page, "action")]
    assert ", ".join(offered) == actions


@then("I can download the original FLAC regardless of the Recording's state")
def _(store, detail_page):
    recording = store.lists(Recording)[0]
    assert reads_field(detail_page, "source-download") == "Download the original FLAC"
    assert f"/api/artifacts/{recording.object_key}" in detail_page
