from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_segment import PROCESS_STEPS, RunsRenderJob
from sermon.sends_notification import SendsNotification
from sermon.shows_recording import NOTICES
from sermon.store import Job, LogEntry, Proposal, Recording, Segment, layout
from steps import _web
from steps._markup import reads_field, reads_rows

READS = ReadsTimecode()
APPROVED = NOTICES["approved"]
NOT_READY = NOTICES["not-ready"]
ALREADY_APPROVED = NOTICES["already-approved"]
LABEL_REQUIRED = NOTICES["label-required"]


@given(
    parsers.parse(
        'a Segment classified "{classification}" with punch-in "{punch_in}" and punch-out "{punch_out}"'
    ),
    target_fixture="segment",
)
def _(store, recording, classification, punch_in, punch_out):
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=0.0,
            span_end_seconds=recording.duration_seconds,
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
        )
    )
    return segment


@when("I approve the Segment", target_fixture="detail_page")
def _(store, segment, clock):
    return _web.posts(store, _web.segment_action(segment, "approve"), clock=clock)


@when("I approve it", target_fixture="detail_page")
def _(store, segment, clock):
    return _web.posts(store, _web.segment_action(segment, "approve"), clock=clock)


@when("I attempt to approve it", target_fixture="detail_page")
def _(store, segment, clock):
    return _web.posts(store, _web.segment_action(segment, "approve"), clock=clock)


@then("a processing job is queued for that Segment")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert jobs[0].state == "queued"


@then("the approval records me as the approver and the time of approval")
def _(store, segment, clock):
    entries = [
        entry
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "approved"
    ]
    assert entries[0].actor == "reviewer"
    assert entries[0].occurred_at == clock()


@then(
    parsers.parse(
        'the approved punch-in and punch-out are recorded as "{punch_in}" and "{punch_out}"'
    )
)
def _(store, segment, punch_in, punch_out):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.punch_in_seconds == READS(punch_in)
    assert stored.punch_out_seconds == READS(punch_out)


@given(parsers.parse('I adjusted the punch-in to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    _web.posts(store, _web.boundary_action(segment, "punch-in"), do="set", timecode=timecode)
    return store.loads(Segment, segment.segment_id)


@then(parsers.parse('the approved punch-in is "{timecode}"'))
def _(store, segment, timecode):
    assert store.loads(Segment, segment.segment_id).punch_in_seconds == READS(timecode)


@then("both the machine proposal and my adjustment are retained in the history")
def _(store, segment):
    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    assert proposals
    stored = store.loads(Segment, segment.segment_id)
    assert stored.punch_in_seconds != proposals[0].punch_in_candidates or stored.punch_in_seconds


@given("I have approved the Segment", target_fixture="segment")
def _(store, segment, clock):
    return ApprovesSegment(store=store, clock=clock)(segment)


@when("I open it", target_fixture="opened_segment")
def _(store, segment):
    return store.loads(Segment, segment.segment_id)


@then("the boundary controls are read-only")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "boundary-controls") == "read-only"
    assert reads_rows(page, "boundary") == []


@then("I see that processing is in progress")
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "processing-step") in {"queued for processing", "rendering the MP3"}


@when("processing is running", target_fixture="pages_mid_render")
def _(store, segment, clock):
    opened = {}

    def steps(name):
        opened[name] = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)

    RunsRenderJob(store=store, steps=steps, notifies=SendsNotification(store=store), clock=clock)()
    assert list(opened) == list(PROCESS_STEPS), f"the render ran {list(opened)}"
    return opened


@then("I see the current processing step")
def _(pages_mid_render):
    shown = {step: reads_field(page, "processing-step") for step, page in pages_mid_render.items()}
    assert all(step in (seen or "") for step, seen in shown.items()), shown


@then("I see an indication of progress")
def _(pages_mid_render):
    shown = [reads_field(page, "processing-progress") for page in pages_mid_render.values()]
    assert all(shown), shown
    assert len(set(shown)) == len(shown), f"progress did not move through the render: {shown}"


@then("other Segments in the same Recording remain fully editable")
def _(store, segment):
    others = [
        item
        for item in store.lists(Segment, recording_id=segment.recording_id)
        if item.segment_id != segment.segment_id
    ]
    assert all(item.state == "proposed" for item in others) or others == []


@given(parsers.parse('the Segment is in state "{state}"'), target_fixture="segment")
def _(store, segment, state):
    return store.saves(replace(segment, state=state))


@then("the approval is rejected")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") in {NOT_READY, ALREADY_APPROVED}


@then("I am told the Segment is not ready for approval")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == NOT_READY


@then("it enters \"approved\" and is queued for processing")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.state == "approved"
    assert store.lists(Job, segment_id=stored.segment_id, kind="render")


@then("no re-analysis is required")
def _(store):
    assert not [
        job for job in store.lists(Job, kind="analyze") if job.state == "queued"
    ]


@given(parsers.parse('the Segment\'s intent is "{intent}"'), target_fixture="segment")
def _(store, segment, intent):
    return store.saves(replace(segment, intent=intent))


@given("no publication label has been entered", target_fixture="segment")
def _(store, segment):
    return store.saves(replace(segment, label=None))


@then("I am prompted for the label")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == LABEL_REQUIRED
    assert 'name="label"' in detail_page


@then("the approval does not proceed until it is supplied")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state != "approved"


@then("no label is required")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == APPROVED


@then("the output is named from the recording date alone")
def _(store, segment):
    from sermon.jobs.renders_segment import RendersSegment
    from sermon.sends_notification import SendsNotification
    from sermon.store import Artifact, Reviewer

    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    RendersSegment(
        store=store,
        steps=lambda _name: None,
        notifies=SendsNotification(store=store),
    )(store.loads(Segment, segment.segment_id))
    artifact = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")[0]
    recording = store.loads(Recording, segment.recording_id)
    assert artifact.path == layout.published_path(
        f"{recording.started_at.date().isoformat()}.mp3"
    )


@given(parsers.parse('the Segment is classified "{classification}"'), target_fixture="segment")
def _(store, segment, classification):
    return store.saves(replace(segment, classification=classification))


@then('the intent is prefilled as "publish"')
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "intent") == "publish"
    assert '<option value="publish" selected>' in page


@then("the intent I approved with is recorded")
def _(store, segment):
    page = _web.posts(store, _web.segment_action(segment, "approve"), intent="archive")
    assert reads_field(page, "intent") == "archive"
    assert store.loads(Segment, segment.segment_id).intent == "archive"


@then("no Segment is ever rendered without a human approving it")
def _(store):
    for job in store.lists(Job, kind="render"):
        segment = store.loads(Segment, job.segment_id)
        assert segment.state in {"approved", "processing", "complete"}


@given("another reviewer approved the Segment a moment ago", target_fixture="segment")
def _(store, segment, clock):
    return ApprovesSegment(store=store, clock=clock)(segment)


@then("I am told it has already been approved")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == ALREADY_APPROVED


@then("no second processing job is queued")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert len(jobs) == 1


@given("a guest preacher asked not to be distributed", target_fixture="segment")
def _(store, segment):
    return store.saves(replace(segment, intent="archive"))


@when('I set the intent to "archive" and approve', target_fixture="detail_page")
def _(store, segment, clock):
    return _web.posts(
        store, _web.segment_action(segment, "approve"), clock=clock, intent="archive"
    )


@then("the Segment renders as an archive copy")
def _(store, segment, detail_page):
    assert reads_field(detail_page, "action-notice") == APPROVED
    assert store.loads(Segment, segment.segment_id).intent == "archive"


@then("it is not presented as a published product")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.intent == "archive"


@when('I change the intent to "publish" and approve', target_fixture="detail_page")
def _(store, segment, clock):
    return _web.posts(
        store, _web.segment_action(segment, "approve"), clock=clock, intent="publish", label=""
    )


@then("the Segment renders with the full publication treatment")
def _(store, segment, detail_page):
    assert reads_field(detail_page, "action-notice") in {APPROVED, LABEL_REQUIRED}
    assert store.loads(Segment, segment.segment_id).intent == "publish"


@then("I am asked for a label")
def _(detail_page):
    assert reads_field(detail_page, "action-notice") == LABEL_REQUIRED
    assert 'name="label"' in detail_page


@then("no Segment is ever published on classification alone")
def _(store):
    for job in store.lists(Job, kind="render"):
        segment = store.loads(Segment, job.segment_id)
        assert segment.intent is not None
        assert segment.disposition_at is not None


@then('I can change it to "archive" before approving')
def _(store, segment):
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "intent-choices") == "publish, archive"
    assert '<option value="archive">archive</option>' in page


@then("the processing job stops")
def _(store, segment, detail_page):
    assert reads_field(detail_page, "segment-state") == "proposed"
    assert [job.state for job in store.lists(Job, segment_id=segment.segment_id)] == ["cancelled"]


@then("any partial output is discarded")
def _(store, segment):
    from sermon.store import Artifact

    assert store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3") == []


@then("the queued processing job is cancelled")
def _(store, recording):
    jobs = store.lists(Job, recording_id=recording.recording_id, kind="render")
    assert jobs
    assert all(job.state == "cancelled" for job in jobs)
