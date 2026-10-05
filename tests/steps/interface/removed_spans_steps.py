import tempfile
from html import unescape
from dataclasses import replace
from pathlib import Path

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.pipeline.render import probe_format
from sermon.shows_recording import formats_precise
from sermon.store import LogEntry, Recording, Segment, layout
from steps import _analysis, _forms, _rendering, _web
from steps._markup import reads_field, reads_role, reads_rows

READS = ReadsTimecode()
LABEL = "Hebrews 13.9-14"
REMOVAL_CONTROL = 'data-field="remove-span-control"'
SPAN_LOGGED = ("span_removed", "span_restored")
JOIN_SIDE_SECONDS = 5.0
HEARD_TOLERANCE_SECONDS = 2 * _rendering.MP3_FRAME_SECONDS
PEAK_MARGIN_DB = 6.0


def removed_spans_url(segment):
    return f"{_web.segment_action(segment, 'removed-spans')}"


def opens(store, segment):
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


def removes(store, segment, start, end):
    return _forms.submits(
        store, opens(store, segment), REMOVAL_CONTROL, do="remove", **{"from": start, "to": end}
    )


def listed(page):
    return [
        (row["removed-from"], row["removed-to"], row["removed-lasting"])
        for row in reads_rows(page, "removed-span")
    ]


def precise(timecode):
    return formats_precise(READS(timecode))


@when(parsers.parse('I remove the span from "{start}" to "{end}"'), target_fixture="detail_page")
def _(store, segment, start, end):
    return removes(store, segment, start, end)


@when(parsers.parse('I try to remove the span from "{start}" to "{end}"'), target_fixture="detail_page")
def _(store, segment, start, end):
    return removes(store, segment, start, end)


@given(parsers.parse('I have removed the span from "{start}" to "{end}"'), target_fixture="detail_page")
def _(store, segment, start, end):
    page = removes(store, segment, start, end)
    if (precise(start), precise(end)) not in [row[:2] for row in listed(page)]:
        raise AssertionError(f"the span was not removed: {reads_field(page, 'action-notice')}")
    return page


@when("I mark the start of a removal at the playhead", target_fixture="detail_page")
def _(store, segment):
    return _forms.submits(
        store, opens(store, segment), REMOVAL_CONTROL, do="mark-start", playhead=store._playhead
    )


@when("I mark the end of the removal at the playhead", target_fixture="detail_page")
def _(store, detail_page):
    return _forms.submits(
        store, detail_page, REMOVAL_CONTROL, do="mark-end", playhead=store._playhead
    )


def restores_from(store, page):
    rows = reads_rows(page, "removed-span")
    assert len(rows) == 1, rows
    return _forms.submits(store, page, f'data-restores="{rows[0]["removed-from"]}"', do="restore")


@when("I restore that span", target_fixture="detail_page")
def _(store, detail_page):
    return restores_from(store, detail_page)


@when("I try to restore that span", target_fixture="detail_page")
def _(store, segment, detail_page):
    rows = reads_rows(detail_page, "removed-span")
    assert len(rows) == 1, rows
    return _web.posts(
        store,
        removed_spans_url(segment),
        do="restore",
        **{"from": rows[0]["from-seconds"], "to": rows[0]["to-seconds"]},
    )


@given("I approve the Segment", target_fixture="detail_page")
def _(store, segment):
    page = _forms.submits(
        store, opens(store, segment), 'data-field="action-control">Approve', label=LABEL
    )
    if store.loads(Segment, segment.segment_id).state != "approved":
        raise AssertionError(f"the Segment was not approved: {reads_field(page, 'action-notice')}")
    return page


@given("I cancel processing", target_fixture="detail_page")
def _(store, segment, detail_page):
    page = _forms.submits(store, detail_page, 'data-field="action-control">Cancel processing')
    if store.loads(Segment, segment.segment_id).state != "proposed":
        raise AssertionError(f"processing was not cancelled: {reads_field(page, 'action-notice')}")
    return page


@given("the Recording's transcript covers each of its Blocks")
def _(store, recording):
    blocks = _analysis.blocks_of(store, recording)
    if not blocks:
        raise AssertionError("the Recording holds no Blocks")
    _analysis.writes_json(
        store,
        recording,
        "transcript",
        _analysis.transcript_over(
            recording, [(block.start_seconds, block.end_seconds, block.type) for block in blocks]
        ),
    )


@when("the machine proposes Segments for the Recording again", target_fixture="detail_page")
def _(store, recording, segment):
    _analysis.proposes(store, recording)
    return opens(store, segment)


@then(
    parsers.parse(
        'the span from "{start}" to "{end}" is listed as removed, lasting "{lasting}"'
    )
)
def _(detail_page, start, end, lasting):
    assert (precise(start), precise(end), lasting) in listed(detail_page)


@then("the removed span is drawn on the waveform where it falls")
def _(store, recording, detail_page):
    duration = store.loads(Recording, recording.recording_id).duration_seconds
    (start, end, _), = listed(detail_page)
    marks = reads_rows(detail_page, "removed-span-mark")
    assert len(marks) == 1, marks
    assert abs(float(marks[0]["left"]) - 100.0 * READS(start) / duration) < 0.001
    assert abs(float(marks[0]["width"]) - 100.0 * (READS(end) - READS(start)) / duration) < 0.001


@then(parsers.parse('the segment length reads "{length}"'))
def _(detail_page, length):
    assert reads_field(detail_page, "length") == length


@then(parsers.parse("{count:d} spans are listed as removed, in the order they fall"))
def _(detail_page, count):
    starts = [READS(start) for start, _, _ in listed(detail_page)]
    assert len(starts) == count
    assert starts == sorted(starts)


@then("no span is listed as removed")
def _(detail_page):
    assert listed(detail_page) == []
    assert reads_field(detail_page, "removed-spans-state")


@then(parsers.parse('I am told "{reason}"'))
def _(detail_page, reason):
    assert reads_field(detail_page, "action-notice") == reason


@then(parsers.parse('only the span from "{start}" to "{end}" is listed as removed'))
def _(detail_page, start, end):
    assert [row[:2] for row in listed(detail_page)] == [(precise(start), precise(end))]


@then(parsers.parse('the span from "{start}" to "{end}" is still listed as removed'))
def _(store, segment, start, end):
    assert (precise(start), precise(end)) in [row[:2] for row in listed(opens(store, segment))]


@then(parsers.parse('the punch-in and punch-out are still "{punch_in}" and "{punch_out}"'))
def _(detail_page, punch_in, punch_out):
    assert reads_field(detail_page, "punch-in") == precise(punch_in)
    assert reads_field(detail_page, "punch-out") == precise(punch_out)


def logged(store, segment):
    return [
        entry
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.kind in SPAN_LOGGED
    ]


@then(
    "the processing log records the removal and then the restoration, "
    "each with who did it and when"
)
def _(store, segment):
    entries = logged(store, segment)
    assert [entry.kind for entry in entries] == list(SPAN_LOGGED)
    assert all(entry.actor == "reviewer" for entry in entries)
    assert entries[0].occurred_at <= entries[1].occurred_at


@then("each entry carries the removed spans in force once it was made")
def _(store, segment):
    removal, restoration = logged(store, segment)
    assert [(span.start_seconds, span.end_seconds) for span in removal.removed_spans] == [
        (READS("2:00:21.400"), READS("2:00:22.100"))
    ]
    assert restoration.removed_spans == ()


@then(parsers.parse('the approval in the processing log carries the span from "{start}" to "{end}"'))
def _(store, segment, start, end):
    approvals = [
        entry
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "approved"
    ]
    assert len(approvals) == 1
    assert [(span.start_seconds, span.end_seconds) for span in approvals[0].removed_spans] == [
        (READS(start), READS(end))
    ]


@given(parsers.parse('the source carries a loud moment from "{at}" lasting {seconds:g} seconds'))
def _(store, recording, at, seconds):
    if (READS(at), seconds) != _rendering.isolated_peak_window():
        raise AssertionError(f"the staged source peaks at {_rendering.isolated_peak_window()}")
    placed = store.saves(replace(recording, local_path=layout.source_path(recording)))
    _rendering.places(_rendering.source("isolated peak"), store.resolves(placed))


@when("I choose to hear the join across that span", target_fixture="join")
def _(store, segment, detail_page):
    control = reads_role(detail_page, "hear-join")
    assert control is not None, "the page offers no way to hear the join"
    heard = _web.opens_app(store).test_client().get(unescape(control["url"]))
    assert heard.status_code == 200, heard.get_data(as_text=True)
    path = Path(tempfile.mkdtemp()) / "join.mp3"
    path.write_bytes(heard.data)
    return {"path": path, "content_type": heard.content_type, "control": control}


@then("I hear the 5 seconds before the span joined to the 5 seconds after it")
def _(join):
    assert join["content_type"].startswith("audio/mpeg")
    length = probe_format(join["path"])["duration"]
    assert abs(length - 2 * JOIN_SIDE_SECONDS) <= HEARD_TOLERANCE_SECONDS


@then("the loud moment is not in what I hear")
def _(store, recording, join):
    source = store.resolves(store.loads(Recording, recording.recording_id))
    loud = _rendering.peak_db(source, *_rendering.isolated_peak_window())
    assert _rendering.peak_db(join["path"]) <= loud - PEAK_MARGIN_DB
