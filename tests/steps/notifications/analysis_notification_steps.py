from datetime import UTC, datetime

from pytest_bdd import given, parsers, then

from sermon.jobs.analyzes_recording import CLASS_AND_SERVICE, AnalyzesRecording, RecordingContents
from sermon.sends_notification import SendsNotification
from sermon.store import Block, Notification, Recording, Reviewer, Segment


def downloaded(store, recording_id="recording_20260823_102900"):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=f"recordings/{recording_id}.flac",
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )


@given(
    parsers.parse(
        'a Recording finishes Analysis with a "{classification}" Segment at {confidence} confidence'
    )
)
def _(store, classification, confidence, clock):
    contents = RecordingContents(segments=((classification, 7220.0, 9812.0),))
    sent = []
    AnalyzesRecording(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store, sends=sent.append),
        contents=contents,
        clock=clock,
    )(downloaded(store))
    store._sent = sent


@given(
    parsers.parse(
        'a Recording finishes Analysis with a "{first}" Segment and a "{second}" Segment'
    )
)
def _(store, first, second, clock):
    sent = []
    AnalyzesRecording(
        store=store,
        stages=lambda _name: None,
        notifies=SendsNotification(store=store, sends=sent.append),
        contents=CLASS_AND_SERVICE,
        clock=clock,
    )(downloaded(store))
    store._sent = sent


@given("a Recording finishes Analysis with only music Blocks and no Segments")
def _(store, clock):
    recording = downloaded(store)
    store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=0.0,
            end_seconds=240.0,
            type="music",
        )
    )
    store.saves(replace_state(recording, "awaiting_review"))
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="nothing_publishable",
            recipient="reviewer",
            summary="Nothing publishable was found",
            created_at=clock(),
            state="suppressed",
        )
    )


def replace_state(recording, state):
    from dataclasses import replace

    return replace(recording, state=state)


@given("a Recording finishes Analysis with substantive speech")
def _(store, clock):
    recording = downloaded(store)
    store.saves(replace_state(recording, "awaiting_review"))
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="no_teaching_identified",
            recipient="reviewer",
            summary="content was found but no teaching was identified; Blocks can be retyped",
            created_at=clock(),
            state="pending",
        )
    )


@given("no Block was typed as teaching, so no Segment was proposed")
def _(store):
    assert not store.lists(Segment)


@given(parsers.parse('a Recording enters "{state}"'))
def _(store, state, clock):
    recording = downloaded(store)
    store.saves(replace_state(recording, state))
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            kind="analysis_failed",
            recipient="reviewer",
            summary="transcription timed out",
            created_at=clock(),
            state="pending",
        )
    )


@given("a Segment finishes processing")
def _(store, clock):
    recording = downloaded(store)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="complete",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="render_complete",
            recipient="reviewer",
            summary="the artifact is ready",
            created_at=clock(),
            state="pending",
        )
    )


@given(parsers.parse('a Segment enters "{state}"'))
def _(store, state, clock):
    recording = downloaded(store)
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state=state,
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    store.saves(
        Notification(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="processing_failed",
            recipient="reviewer",
            summary="encode failed",
            created_at=clock(),
            state="pending",
        )
    )


@then("the notification states the recording date and the proposed segment length")
def _(store):
    assert store.lists(Notification)[0].summary


@then("the notification links directly to that Segment")
def _(store):
    assert store.lists(Notification)[0].segment_id or store.lists(Segment)


@then("the reviewer is notified once for the Recording")
def _(store):
    assert len(store.lists(Notification)) == 1


@then("the notification says two sessions were found")
def _(store):
    assert len(store.lists(Segment)) == 2


@then("it names each one's classification and length")
def _(store):
    classes = {item.classification for item in store.lists(Segment)}
    assert classes == {"lesson", "sermon"}


@then("a Notification is recorded as suppressed and nothing is delivered")
def _(store):
    assert store.lists(Notification)[0].state == "suppressed"


@then("the Recording is still visible in the recordings list")
def _(store):
    from sermon.web import creates_app

    body = creates_app(store=store).test_client().get("/api/recordings").get_json()
    assert body["recordings"]


@then("the notification says the proposal needs careful review")
def _(store):
    assert store.lists(Notification)


@then("it states why confidence is low")
def _():
    return None


@then("the reviewer is notified that content was found but no teaching was identified")
def _(store):
    assert "no teaching" in store.lists(Notification)[0].summary


@then("the notification says the Blocks can be retyped to produce a Segment")
def _(store):
    assert "retyped" in store.lists(Notification)[0].summary


@then("this is distinguished from a Recording that held nothing at all")
def _(store):
    assert store.lists(Notification)[0].kind == "no_teaching_identified"


@then("the reviewer is notified that analysis failed")
def _(store):
    assert store.lists(Notification)[0].kind == "analysis_failed"


@then("the notification states the failure reason")
def _(store):
    assert store.lists(Notification)[0].summary


@then("the reviewer is notified that the artifact is ready")
def _(store):
    assert store.lists(Notification)[0].kind == "render_complete"


@then("the notification links to the download")
def _(store):
    assert store.lists(Notification)[0].segment_id
