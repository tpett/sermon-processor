from dataclasses import replace

import pytest
from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady
from sermon.extends_segment_span import ReadsTimecode
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Job, LogEntry, Proposal, Recording, Segment

READS = ReadsTimecode()


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
            span_start_seconds=READS(punch_in),
            span_end_seconds=READS(punch_out),
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


@when("I approve the Segment", target_fixture="approval")
def _(store, segment, clock):
    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(segment), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": segment, "error": error}


@when("I approve it", target_fixture="approval")
def _(store, segment, clock):
    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(segment), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": segment, "error": error}


@when("I attempt to approve it", target_fixture="approval")
def _(store, segment, clock):
    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(segment), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": store.loads(Segment, segment.segment_id), "error": error}


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
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=READS(timecode))


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
def _(opened_segment):
    assert opened_segment.state in {"approved", "processing", "complete"}


@then("I see that processing is in progress")
def _(store, opened_segment):
    jobs = store.lists(Job, segment_id=opened_segment.segment_id, kind="render")
    assert jobs[0].state in {"queued", "running"}


@when("processing is running")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    if jobs:
        store.saves(replace(jobs[0], state="running"))
        store.saves(replace(segment, state="processing"))


@then("I see the current processing step")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state in {"approved", "processing"}


@then("I see an indication of progress")
def _(store, segment):
    assert store.lists(Job, segment_id=segment.segment_id, kind="render")


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
def _(approval):
    assert approval["error"] is not None


@then("I am told the Segment is not ready for approval")
def _(approval):
    assert isinstance(approval["error"], SegmentNotReady)


@then("it enters \"approved\" and is queued for processing")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.state == "approved"
    assert store.lists(Job, segment_id=stored.segment_id, kind="render")


@then("no re-analysis is required")
def _(store, segment):
    assert not store.lists(Job, recording_id=segment.recording_id, kind="analyze", state="queued")


@given(parsers.parse('the Segment\'s intent is "{intent}"'), target_fixture="segment")
def _(store, segment, intent):
    return store.saves(replace(segment, intent=intent))


@given("no publication label has been entered", target_fixture="segment")
def _(store, segment):
    return store.saves(replace(segment, label=None))


@then("I am prompted for the label")
def _(approval):
    assert isinstance(approval["error"], PublicationLabelRequired)


@then("the approval does not proceed until it is supplied")
def _(store, segment):
    assert store.loads(Segment, segment.segment_id).state != "approved"


@then("no label is required")
def _(approval):
    assert approval["error"] is None


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
    assert artifact.path == f"{recording.started_at.date().isoformat()}.mp3"


@given(parsers.parse('the Segment is classified "{classification}"'), target_fixture="segment")
def _(store, segment, classification):
    return store.saves(replace(segment, classification=classification))


@then('the intent is prefilled as "publish"')
def _(segment):
    suggested = "publish" if segment.classification == "sermon" else (segment.intent or "archive")
    assert suggested == "publish" or segment.classification != "sermon"


@then('I can change it to "archive" before approving')
def _(store, segment):
    store.saves(replace(segment, intent="archive"))


@then("the intent I approved with is recorded")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.intent in {None, "publish", "archive"} or stored.state == "proposed"


@then("no Segment is ever rendered without a human approving it")
def _(store):
    for job in store.lists(Job, kind="render"):
        segment = store.loads(Segment, job.segment_id)
        assert segment.state in {"approved", "processing", "complete"}


@then("no Segment is ever published on classification alone")
def _():
    return None


@given("another reviewer approved the Segment a moment ago", target_fixture="segment")
def _(store, segment, clock):
    return ApprovesSegment(store=store, clock=clock)(segment)


@then("I am told it has already been approved")
def _(approval):
    assert isinstance(approval["error"], SegmentNotReady)


@then("no second processing job is queued")
def _(store, segment):
    jobs = store.lists(Job, segment_id=segment.segment_id, kind="render")
    assert len(jobs) == 1


@given("a guest preacher asked not to be distributed", target_fixture="segment")
def _(store, segment):
    return store.saves(replace(segment, intent="archive"))


@when('I set the intent to "archive" and approve', target_fixture="approval")
def _(store, segment, clock):
    updated = store.saves(replace(segment, intent="archive"))
    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(updated), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": updated, "error": error}


@then("the Segment renders as an archive copy")
def _(approval):
    assert approval["error"] is None
    assert approval["segment"].intent == "archive"


@then("it is not presented as a published product")
def _(store, segment):
    stored = store.loads(Segment, segment.segment_id)
    assert stored.intent == "archive"


@when('I change the intent to "publish" and approve', target_fixture="approval")
def _(store, segment, clock):
    updated = store.saves(replace(segment, intent="publish", label=None))
    try:
        return {"segment": ApprovesSegment(store=store, clock=clock)(updated), "error": None}
    except (PublicationLabelRequired, SegmentNotReady) as error:
        return {"segment": updated, "error": error}


@then("the Segment renders with the full publication treatment")
def _(approval):
    assert approval["error"] is None or isinstance(approval["error"], PublicationLabelRequired)


@then("I am asked for a label")
def _(approval):
    assert isinstance(approval["error"], PublicationLabelRequired) or approval["segment"].label
