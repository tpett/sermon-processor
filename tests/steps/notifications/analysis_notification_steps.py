from pytest_bdd import given, parsers, then

from sermon.store import Artifact, Proposal, Segment
from sermon.web import creates_app

from steps import _notifications
from steps._markup import reads_rows

LAYOUTS = {"high": _notifications.SUNDAY, "low": _notifications.UNCUED_SERMON}


def shown(store, moments, notification):
    page = creates_app(store=store, clock=moments).test_client().get("/notifications").get_data(as_text=True)
    rows = [row for row in reads_rows(page, "notification") if int(row["id"]) == notification.notification_id]
    assert rows, f"Notification {notification.notification_id} is not listed in the interface"
    return rows[0]


def the_segments(store):
    return sorted(store.lists(Segment), key=lambda item: item.punch_in_seconds)


@given(
    parsers.parse(
        'a Recording finishes Analysis with a "{classification}" Segment at {confidence} confidence'
    )
)
def _(store, classification, confidence, delivery_channel, moments):
    _notifications.finishes_analysis(store, LAYOUTS[confidence], delivery_channel, moments)
    found = [(item.classification, item.state) for item in store.lists(Segment)]
    assert found == [(classification, "proposed")], found


@given(
    parsers.parse(
        'a Recording finishes Analysis with a "{first}" Segment and a "{second}" Segment'
    )
)
def _(store, first, second, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.LESSON_AND_SERMON, delivery_channel, moments)
    assert [item.classification for item in the_segments(store)] == [first, second]


@given("a Recording finishes Analysis with only music Blocks and no Segments")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.ONLY_MUSIC, delivery_channel, moments)
    assert store.lists(Segment) == []


@given("a Recording finishes Analysis with substantive speech")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.NO_TEACHING, delivery_channel, moments)


@given("no Block was typed as teaching, so no Segment was proposed")
def _(store):
    assert store.lists(Segment) == []


@given(parsers.parse('a Recording enters "{state}"'))
def _(store, state, delivery_channel, moments):
    failed = _notifications.fails_analysis(store, delivery_channel, moments)
    assert failed.state == state


@given("a Segment finishes processing")
def _(store, delivery_channel, moments):
    segment = _notifications.approved_segment(store)
    assert _notifications.renders(store, segment, delivery_channel, moments).state == "complete"


@given(parsers.parse('a Segment enters "{state}"'))
def _(store, state, delivery_channel, moments):
    segment = _notifications.approved_segment(store)
    rendered = _notifications.renders(store, segment, delivery_channel, moments, failing_step="encode")
    assert rendered.state == state


@then("the notification states the recording date and the proposed segment length")
def _(store):
    segment = the_segments(store)[0]
    summary = _notifications.the_only(store).summary
    assert "2026-08-23" in summary
    assert _notifications.formats_length(segment.punch_out_seconds - segment.punch_in_seconds) in summary


@then("the notification links directly to that Segment")
def _(store, moments):
    segment = the_segments(store)[0]
    notification = _notifications.the_only(store)
    assert notification.segment_id == segment.segment_id
    assert f"/recordings/{segment.recording_id}?segment={segment.segment_id}" in shown(store, moments, notification)["links"]


@then("the reviewer is notified once for the Recording")
def _(store, delivery_channel):
    recording = _notifications.the_recording(store)
    notification = _notifications.the_only(store)
    assert (notification.recording_id, notification.segment_id, notification.kind) == (
        recording.recording_id,
        None,
        "segment_proposed",
    )
    assert [item.notification_id for item in delivery_channel.received] == [notification.notification_id]


@then("the notification says two sessions were found")
def _(store):
    assert "two sessions" in _notifications.the_only(store).summary


@then("it names each one's classification and length")
def _(store):
    summary = _notifications.the_only(store).summary
    for segment in the_segments(store):
        named = f"{segment.classification} ({_notifications.formats_length(segment.punch_out_seconds - segment.punch_in_seconds)})"
        assert named in summary, (named, summary)


@then("a Notification is recorded as suppressed and nothing is delivered")
def _(store, delivery_channel):
    notification = _notifications.the_only(store)
    assert (notification.kind, notification.state) == ("nothing_publishable", "suppressed")
    assert delivery_channel.attempts == 0


@then("the Recording is still visible in the recordings list")
def _(store):
    page = creates_app(store=store).test_client().get("/").get_data(as_text=True)
    assert [row["id"] for row in reads_rows(page, "recording")] == [_notifications.the_recording(store).recording_id]


@then("the notification says the proposal needs careful review")
def _(store):
    assert "needs careful review" in _notifications.the_only(store).summary


@then("it states why confidence is low")
def _(store):
    segment = the_segments(store)[0]
    proposal = store.lists(Proposal, segment_id=segment.segment_id)[0]
    assert proposal.boundary_confidence == "low"
    summary = _notifications.the_only(store).summary
    assert "boundary confidence is low" in summary
    for missing in proposal.missing_evidence:
        assert missing in summary, (missing, summary)


@then("the reviewer is notified that content was found but no teaching was identified")
def _(store, delivery_channel):
    notification = _notifications.the_only(store)
    assert notification.kind == "no_teaching_identified"
    assert "no teaching was identified" in notification.summary
    assert [item.notification_id for item in delivery_channel.received] == [notification.notification_id]


@then("the notification says the Blocks can be retyped to produce a Segment")
def _(store):
    assert "retype" in _notifications.the_only(store).summary


@then("this is distinguished from a Recording that held nothing at all")
def _(store):
    notification = _notifications.the_only(store)
    assert notification.kind != "nothing_publishable"
    assert notification.state == "delivered"


@then("the reviewer is notified that analysis failed")
def _(store, delivery_channel):
    recording = _notifications.the_recording(store)
    notification = _notifications.the_only(store)
    assert (notification.kind, notification.recording_id) == ("analysis_failed", recording.recording_id)
    assert [item.notification_id for item in delivery_channel.received] == [notification.notification_id]


@then("the notification states the failure reason")
def _(store):
    notification = _notifications.the_only(store)
    criteria = {"recording_id": notification.recording_id}
    if notification.segment_id is not None:
        criteria["segment_id"] = notification.segment_id
    assert _notifications.failure_of(store, **criteria) in notification.summary


@then("the reviewer is notified that the artifact is ready")
def _(store, delivery_channel):
    segment = the_segments(store)[0]
    notification = _notifications.the_only(store)
    assert (notification.kind, notification.segment_id) == ("render_complete", segment.segment_id)
    assert [item.notification_id for item in delivery_channel.received] == [notification.notification_id]


@then("the notification links to the download")
def _(store, moments):
    notification = _notifications.the_only(store)
    artifact = store.lists(Artifact, kind="rendered_mp3", segment_id=notification.segment_id)[0]
    download = f"/api/artifacts/{artifact.path}"
    assert download in shown(store, moments, notification)["links"]
    assert creates_app(store=store).test_client().get(download).status_code == 200
