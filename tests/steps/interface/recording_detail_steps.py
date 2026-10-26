from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.analyzes_recording import STAGE_ORDER
from sermon.store import Job, Proposal, Recording, Segment
from steps import _browser, _progress, _web
from sermon.web import creates_app
from steps._markup import reads_field, reads_pairs, reads_role, reads_rows

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
    wanted = {label: value for label, value in datatable[1:]}
    assert wanted, "the table names nothing to see"
    shown = reads_pairs(detail_page)
    assert {label: shown.get(label) for label in wanted} == wanted


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
    stored = store.saves(replace(recording, state=state))
    if state == "analyzing":
        _progress.leaves_analysis_part_way(store, stored)
    return stored


@given(
    parsers.parse('the Recording is in state "{state}" with reason "{reason}"'),
    target_fixture="recording",
)
def _(store, recording, state, reason):
    return store.saves(replace(recording, state=state, skip_reason=reason))


@then("I see which analysis stage is currently running")
def _(store, recording, detail_page):
    assert reads_field(detail_page, "state") == "analyzing"
    assert "Analysis is running" in reads_field(detail_page, "progress")
    running = _progress.running_stages(store, recording)
    shown = {row["stage"] for row in reads_rows(detail_page, "stage") if row["state"] == "running"}
    assert shown == running == {"transcription"}
    assert reads_field(detail_page, "analysis-stage") == "transcribing the audio"
    assert reads_field(detail_page, "analysis-detail") == (
        "chunk 3 of 7, 42% of the audio recognised, 1:20:20 of 3:12:00"
    )


@then("I see which stages have completed")
def _(store, recording, detail_page):
    rows = reads_rows(detail_page, "stage")
    assert [row["stage"] for row in rows] == list(STAGE_ORDER)
    completed = _progress.completed_stages(store, recording)
    assert completed == {"envelope", "probe", "waveform", "preview"}
    assert {row["stage"] for row in rows if row["state"] == "complete"} == completed
    assert reads_field(detail_page, "analysis-completed") == f"4 of {len(STAGE_ORDER)} stages complete"
    assert all(row["stage-took"] for row in rows if row["state"] == "complete")


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


@when("I choose to archive the whole recording", target_fixture="detail_page")
def _(store, recording):
    return _web.posts(store, _web.recording_action(recording, "archive-whole-recording"))


@then("a Segment is created spanning the entire Recording")
def _(store, recording, detail_page):
    archived = [
        one
        for one in store.lists(Segment, recording_id=recording.recording_id)
        if one.classification == "meeting"
    ]
    assert [(one.punch_in_seconds, one.punch_out_seconds) for one in archived] == [
        (0.0, recording.duration_seconds)
    ]
    assert [row["classification"] for row in reads_rows(detail_page, "segment")].count("meeting") == 1


@then('its intent is "archive"')
def _(store, recording):
    archived = [
        one
        for one in store.lists(Segment, recording_id=recording.recording_id)
        if one.classification == "meeting"
    ]
    assert [one.intent for one in archived] == ["archive"]


@then("it is approved for processing without asking me for boundaries")
def _(store, recording, detail_page):
    archived = [
        one
        for one in store.lists(Segment, recording_id=recording.recording_id)
        if one.classification == "meeting"
    ]
    assert [one.state for one in archived] == ["approved"]
    assert reads_field(detail_page, "action-notice") == "the whole Recording is kept as an archive copy"
    assert store.lists(Job, segment_id=archived[0].segment_id, kind="render")


@then("I see the failure reason")
def _(detail_page):
    assert reads_field(detail_page, "reason") == "transcription timed out"


@then("I can retry Analysis")
def _(store, detail_page):
    retry = [row for row in reads_rows(detail_page, "action") if row["action"] == "Retry analysis"]
    assert [row["action-control"] for row in retry] == ["Retry analysis"]
    recording = store.lists(Recording)[0]
    assert f"/recordings/{recording.recording_id}/actions/retry-analysis" in detail_page


@then("I can create a Segment by hand instead")
def _(store, detail_page):
    drawn = [
        row
        for row in reads_rows(detail_page, "action")
        if row["action"] == "Create segment by hand"
    ]
    assert [row["action-control"] for row in drawn] == ["Create segment by hand"]
    recording = store.lists(Recording)[0]
    assert f"/recordings/{recording.recording_id}/actions/create-segment" in detail_page


DETAILS_SECTIONS = ("why", "analysis", "transcript", "source", "actions")


def opens_in_browser(store):
    recording = store.lists(Recording)[0]
    return _browser.opens_page(store), f"/recordings/{recording.recording_id}"


@then("the recording's details are closed")
def _(store):
    opening, address = opens_in_browser(store)
    with opening as page:
        page.goto(address)
        assert page.locator('[data-role="open-details"]').is_visible(), "nothing offers the details"
        for section in DETAILS_SECTIONS:
            shown = page.locator(f'[data-details-section="{section}"]')
            assert shown.count() == 1, f"no {section} section in the details"
            assert not shown.is_visible(), f"the {section} section shows before the details are opened"


@then(
    "why the cut was proposed, the analysis stages, the transcript, the source details "
    "and the recording-level actions are inside them"
)
def _(store):
    opening, address = opens_in_browser(store)
    with opening as page:
        page.goto(address)
        details = page.locator('[data-role="recording-details"]')
        assert details.count() == 1, "the page has no recording details"
        inside = [
            section
            for section in DETAILS_SECTIONS
            if details.locator(f'[data-details-section="{section}"]').count() == 1
        ]
        assert inside == list(DETAILS_SECTIONS), inside


@when("I open the recording's details", target_fixture="detail_page")
def _(store):
    opening, address = opens_in_browser(store)
    with opening as page:
        page.goto(address)
        control = page.locator('[data-role="open-details"]')
        assert control.count() == 1, "nothing offers the details"
        control.click()
        page.locator('[data-details-section="source"]').wait_for(state="visible", timeout=5000)
        return page.content()


@then("the control that opens the recording's details shows there is a warning")
def _(detail_page):
    control = reads_role(detail_page, "open-details")
    assert control is not None, "nothing offers the details"
    assert control.get("warnings") == "1", control
