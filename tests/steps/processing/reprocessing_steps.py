import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_mp3 import RenderedAudio
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.removes_span import kept_pieces
from sermon.sends_notification import SendsNotification
from sermon.store import Artifact, Job, LogEntry, Recording, Segment, layout
from steps import _forms, _web
from steps._markup import reads_field, reads_field_link
from steps._worker import refuses_other_work

READS = ReadsTimecode()
LABEL = "Hebrews 12.4-11"
SOURCE_BYTES = b"fLaC" + bytes(range(256)) * 64
SPAN_ROOM_SECONDS = 300.0
MOST_WORKER_PASSES = 20
STAND_IN_SETTINGS = {"loudness_target_lufs": -16.0, "true_peak_ceiling_dbtp": -1.0}


def writes_the_cut(source, punch_in, punch_out, destination, *, channel=0, removed=()):
    """Stands in for the render chain: the file records which stretches of the source it kept."""
    kept = kept_pieces(punch_in, punch_out, removed)
    Path(destination).write_text(json.dumps({"source": str(source), "kept": kept}))
    return RenderedAudio(
        path=Path(destination),
        size_bytes=Path(destination).stat().st_size,
        duration_seconds=sum(end - start for start, end in kept),
        channels=1,
        sample_rate=44100,
        kbps=96,
        input_loudness_lufs=-30.0,
        achieved_loudness_lufs=-16.0,
        achieved_true_peak_dbtp=-1.0,
        achieved_loudness_range_lu=None,
        settings=STAND_IN_SETTINGS,
    )


def drains(store, clock):
    runs = RunsQueuedJobs(
        store=store,
        downloads=refuses_other_work,
        analyzes=refuses_other_work,
        renders=RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=clock,
            renders=writes_the_cut,
        ),
        clock=clock,
    )
    for _ in range(MOST_WORKER_PASSES):
        if runs() is None:
            return
    raise AssertionError("render jobs were still queued after the worker gave up")


def renders_through(store, clock, segment):
    ApprovesSegment(store=store, clock=clock)(segment)
    drains(store, clock)
    rendered = store.loads(Segment, segment.segment_id)
    if rendered.state != "complete":
        raise AssertionError(f"the Segment did not render: it is {rendered.state}")
    return rendered


def opens(store, segment):
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


def presses(store, segment, action):
    return _forms.submits(store, opens(store, segment), f'data-field="action-control">{action}<')


def recuts(store, segment):
    page = presses(store, segment, "Re-cut")
    if store.loads(Segment, segment.segment_id).state != "recut":
        raise AssertionError(f"the Segment was not re-cut: {reads_field(page, 'action-notice')}")
    return page


def renders_of(store, segment):
    return store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")


def current_render(store, segment):
    current = [item for item in renders_of(store, segment) if item.superseded_by is None]
    assert len(current) == 1, f"{len(current)} current renders: {current}"
    return current[0]


def first_render(store, segment):
    return renders_of(store, segment)[0]


def kept_by(store, artifact):
    return [tuple(piece) for piece in json.loads(store.resolves(artifact).read_text())["kept"]]


def approvals_of(store, segment):
    return [
        (entry.punch_in_seconds, entry.punch_out_seconds)
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "approved"
    ]


def downloads(store, link):
    return _web.opens_app(store).test_client().get(link)


@given(
    parsers.parse(
        'a Segment in state "complete" with punch-in "{punch_in}" and punch-out "{punch_out}"'
    ),
    target_fixture="segment",
)
def _(store, clock, punch_in, punch_out):
    recording = Recording(
        recording_id="recording_20260823_102900",
        object_key="recordings/recording_20260823_102900.flac",
        state="awaiting_review",
        started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
        started_at_source="key",
        size_bytes=len(SOURCE_BYTES),
        duration_seconds=11520.0,
        checksum=hashlib.sha256(SOURCE_BYTES).hexdigest(),
    )
    recording = replace(recording, local_path=layout.source_path(recording))
    source = store.resolves(recording)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(SOURCE_BYTES)
    store.saves(recording)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            intent="publish",
            label=LABEL,
            span_start_seconds=READS(punch_in) - SPAN_ROOM_SECONDS,
            span_end_seconds=READS(punch_out) + SPAN_ROOM_SECONDS,
            punch_in_seconds=READS(punch_in),
            punch_out_seconds=READS(punch_out),
        )
    )
    return renders_through(store, clock, segment)


@when("I choose to re-cut the Segment", target_fixture="detail_page")
def _(store, segment):
    return presses(store, segment, "Re-cut")


@when("I re-cut this Segment", target_fixture="detail_page")
def _(store, segment):
    return presses(store, segment, "Re-cut")


@given("I have re-cut the Segment", target_fixture="detail_page")
def _(store, segment):
    return recuts(store, segment)


@given(parsers.parse('I re-cut and adjusted the punch-out to "{timecode}"'), target_fixture="detail_page")
def _(store, segment, timecode):
    recuts(store, segment)
    page = _web.posts(store, _web.boundary_action(segment, "punch-out"), do="set", timecode=timecode)
    if abs(store.loads(Segment, segment.segment_id).punch_out_seconds - READS(timecode)) > 0.0005:
        raise AssertionError(f"the punch-out did not move: {reads_field(page, 'action-notice')}")
    return page


@given("I have re-cut and re-approved a Segment twice")
def _(store, clock, segment):
    for moved_to in ("2:43:40", "2:43:50"):
        recuts(store, segment)
        _web.posts(store, _web.boundary_action(segment, "punch-out"), do="set", timecode=moved_to)
        renders_through(store, clock, store.loads(Segment, segment.segment_id))


@given(parsers.parse('another Segment from the same Recording is "{state}"'), target_fixture="sibling")
def _(store, clock, segment, state):
    assert state == "complete", f"only a complete sibling is modelled, not {state}"
    sibling = store.saves(
        Segment(
            recording_id=segment.recording_id,
            classification="lesson",
            state="proposed",
            intent="publish",
            label="TEC",
            span_start_seconds=60.0,
            span_end_seconds=3000.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3000.0,
        )
    )
    return renders_through(store, clock, sibling)


@given("a Segment has been rendered twice")
def _(store, clock, segment):
    recuts(store, segment)
    renamed = store.saves(replace(store.loads(Segment, segment.segment_id), label="Hebrews 12.4-13"))
    renders_through(store, clock, renamed)


@when("I skip the Segment", target_fixture="detail_page")
def _(store, segment):
    return presses(store, segment, "Skip")


@when("the worker renders it")
def _(store, clock):
    drains(store, clock)


@then(parsers.parse('it enters "{state}"'))
def _(store, segment, state):
    assert store.loads(Segment, segment.segment_id).state == state


@then("the previously approved boundaries are shown as the starting point")
def _(store, segment, detail_page):
    approved_in, approved_out = approvals_of(store, segment)[-1]
    assert reads_field(detail_page, "boundary-controls") == "editable"
    assert READS(reads_field(detail_page, "punch-in")) == approved_in
    assert READS(reads_field(detail_page, "punch-out")) == approved_out


@then("the existing MP3 remains downloadable until a new one replaces it")
def _(store, segment):
    page = opens(store, segment)
    link = reads_field_link(page, "mp3-download")
    assert link == f"/api/artifacts/{first_render(store, segment).path}", link
    response = downloads(store, link)
    assert response.status_code == 200
    assert hashlib.sha256(response.data).hexdigest() == first_render(store, segment).checksum


@then("it is processed again")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    renders = [
        job.state for job in store.lists(Job, segment_id=segment.segment_id, kind="render")
    ]
    assert (stored.state, renders) == ("complete", ["succeeded", "succeeded"])


@then("the new MP3 replaces the previous one")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    current = current_render(store, segment)
    earlier = [item for item in renders_of(store, segment) if item.superseded_by is not None]
    assert [item.superseded_by for item in earlier] == [current.artifact_id]
    assert kept_by(store, current) == list(
        kept_pieces(stored.punch_in_seconds, stored.punch_out_seconds, stored.removed_spans)
    )
    link = reads_field_link(opens(store, segment), "mp3-download")
    assert link == f"/api/artifacts/{current.path}", link
    assert hashlib.sha256(downloads(store, link).data).hexdigest() == current.checksum
    assert earlier[0].path == current.path or not store.resolves(earlier[0]).exists()


@then("the previous cut's boundaries are retained in the history")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    original = (READS("2:00:20"), READS("2:43:32"))
    assert approvals_of(store, segment) == [
        original,
        (stored.punch_in_seconds, stored.punch_out_seconds),
    ]
    assert original != (stored.punch_in_seconds, stored.punch_out_seconds)


@then(parsers.parse('the new MP3 leaves out the span from "{start}" to "{end}"'))
def _(store, segment, start, end):
    kept = kept_by(store, current_render(store, segment))
    assert len(kept) == 2, kept
    assert (kept[0][1], kept[1][0]) == (READS(start), READS(end))


@then("the original FLAC is unchanged")
def _(store, segment):
    recording = store.loads(Recording, segment.recording_id)
    held = store.resolves(recording).read_bytes()
    assert hashlib.sha256(held).hexdigest() == recording.checksum
    assert len(renders_of(store, segment)) == 3


@then("it is still downloadable")
def _(store, segment):
    link = reads_field_link(opens(store, segment), "source-download")
    response = downloads(store, link)
    assert response.status_code == 200
    assert response.data == SOURCE_BYTES


@then(parsers.parse('the other Segment stays "{state}"'))
def _(store, sibling, state):
    assert store.loads(Segment, sibling.segment_id).state == state


@then("its MP3 is untouched")
def _(store, sibling):
    rendered = renders_of(store, sibling)
    assert [item.superseded_by for item in rendered] == [None]
    held = store.resolves(rendered[0]).read_bytes()
    assert hashlib.sha256(held).hexdigest() == rendered[0].checksum


@then("only the most recent MP3 is stored")
def _(store, segment):
    current = current_render(store, segment)
    published = sorted(path.name for path in store.resolves(current).parent.iterdir())
    assert published == [Path(current.path).name], published


@then("the earlier render is deleted")
def _(store, segment):
    earlier = first_render(store, segment)
    assert earlier.superseded_by == current_render(store, segment).artifact_id
    assert earlier.path != current_render(store, segment).path
    assert not store.resolves(earlier).exists()
