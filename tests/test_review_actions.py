from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.store import Job, LogEntry, Recording, Segment, opens_store
from sermon.web import creates_app

from steps._markup import reads_field, reads_rows

RECORDING_ID = "recording_20260913_090014"


@pytest.fixture
def data_root(tmp_path):
    return tmp_path


@pytest.fixture
def store(data_root):
    opened = opens_store(data_root)
    yield opened
    opened.close()


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"2026/09/13/{RECORDING_ID}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )


@pytest.fixture
def segment(store, recording):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=5320.0,
            span_end_seconds=11520.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
            boundary_source="model",
        )
    )


@pytest.fixture
def client(store):
    return creates_app(store=store).test_client()


def follows(client, response):
    assert response.status_code == 303, response.status_code
    return client.get(response.headers["Location"]).get_data(as_text=True)


def reads_again(data_root, entity_type, identity):
    second = opens_store(data_root)
    try:
        return second.loads(entity_type, identity)
    finally:
        second.close()


def lists_again(data_root, entity_type, **criteria):
    second = opens_store(data_root)
    try:
        return second.lists(entity_type, **criteria)
    finally:
        second.close()


def test_approving_through_the_form_stores_the_approval(data_root, store, client, segment):
    page = follows(
        client,
        client.post(
            f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/approve",
            data={"intent": "publish", "label": "Hebrews 12.4-11"},
        ),
    )
    assert "the Segment is approved and queued for processing" in page
    stored = reads_again(data_root, Segment, segment.segment_id)
    assert stored.state == "approved"
    assert stored.label == "Hebrews 12.4-11"
    assert stored.disposition_at is not None
    queued = lists_again(data_root, Job, segment_id=segment.segment_id, kind="render")
    assert [job.state for job in queued] == ["queued"]


def test_a_refused_approval_stores_no_approval(data_root, store, client, segment):
    page = follows(
        client,
        client.post(
            f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/approve",
            data={"intent": "publish", "label": ""},
        ),
    )
    assert "a publication label is required before publishing" in page
    stored = reads_again(data_root, Segment, segment.segment_id)
    assert stored.state == "proposed"
    assert stored.disposition_at is None
    assert lists_again(data_root, Job, segment_id=segment.segment_id) == []
    assert lists_again(data_root, LogEntry, segment_id=segment.segment_id) == []
    assert stored.intent == "publish"


def test_approving_twice_queues_one_render(data_root, store, client, segment):
    approve = f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/approve"
    client.post(approve, data={"intent": "archive"})
    page = follows(client, client.post(approve, data={"intent": "archive"}))
    assert "it has already been approved" in page
    queued = lists_again(data_root, Job, segment_id=segment.segment_id, kind="render")
    assert len(queued) == 1


def test_a_refused_boundary_stores_nothing(data_root, store, client, segment):
    page = follows(
        client,
        client.post(
            f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/boundaries/punch-in",
            data={"do": "set", "timecode": "1:20:00"},
        ),
    )
    assert "the boundary must fall within the Segment" in page
    stored = reads_again(data_root, Segment, segment.segment_id)
    assert stored.punch_in_seconds == 7220.0
    assert stored.boundary_source == "model"
    assert lists_again(data_root, LogEntry, segment_id=segment.segment_id) == []


def test_an_accepted_boundary_keeps_the_machine_proposal(data_root, store, client, segment):
    client.post(
        f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/boundaries/punch-in",
        data={"do": "set", "timecode": "2:00:16.500"},
    )
    stored = reads_again(data_root, Segment, segment.segment_id)
    assert stored.punch_in_seconds == 7216.5
    assert stored.boundary_source == "human"
    history = lists_again(data_root, LogEntry, segment_id=segment.segment_id)
    assert [(entry.boundary_source, entry.punch_in_seconds) for entry in history] == [
        ("model", 7220.0),
        ("human", 7216.5),
    ]


def test_reverting_restores_the_machine_proposal(data_root, store, client, segment):
    boundaries = f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/boundaries/punch-in"
    client.post(boundaries, data={"do": "set", "timecode": "2:00:16.500"})
    client.post(boundaries, data={"do": "revert"})
    stored = reads_again(data_root, Segment, segment.segment_id)
    assert stored.punch_in_seconds == 7220.0
    discarded = [
        entry
        for entry in lists_again(data_root, LogEntry, segment_id=segment.segment_id)
        if entry.correlation_id == f"revert:{segment.segment_id}"
    ]
    assert [entry.punch_in_seconds for entry in discarded] == [7216.5]


def test_boundaries_are_locked_once_approved(data_root, store, client, segment):
    client.post(
        f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/approve",
        data={"intent": "archive"},
    )
    page = follows(
        client,
        client.post(
            f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/boundaries/punch-in",
            data={"do": "set", "timecode": "2:00:16.500"},
        ),
    )
    assert "the boundaries cannot be changed once the Segment is approved" in page
    assert reads_again(data_root, Segment, segment.segment_id).punch_in_seconds == 7220.0


def test_archiving_the_whole_recording_approves_one_meeting_segment(data_root, store, client, recording):
    page = follows(
        client, client.post(f"/recordings/{RECORDING_ID}/actions/archive-whole-recording")
    )
    assert "the whole Recording is kept as an archive copy" in page
    stored = lists_again(data_root, Segment, recording_id=RECORDING_ID)
    assert [(one.classification, one.state, one.intent) for one in stored] == [
        ("meeting", "approved", "archive")
    ]
    assert (stored[0].punch_in_seconds, stored[0].punch_out_seconds) == (0.0, 11520.0)


def test_discarding_a_published_recording_needs_confirmation(data_root, store, client, recording):
    store.saves(
        Segment(
            recording_id=RECORDING_ID,
            classification="sermon",
            state="complete",
            span_start_seconds=0.0,
            span_end_seconds=100.0,
            punch_in_seconds=0.0,
            punch_out_seconds=100.0,
        )
    )
    page = follows(client, client.post(f"/recordings/{RECORDING_ID}/actions/discard"))
    assert "confirm to discard it" in page
    assert reads_again(data_root, Recording, RECORDING_ID).state == "awaiting_review"
    follows(
        client,
        client.post(f"/recordings/{RECORDING_ID}/actions/discard", data={"confirm": "yes"}),
    )
    assert reads_again(data_root, Recording, RECORDING_ID).state == "discarded"


def test_an_unknown_segment_is_not_found(client, recording):
    assert client.post(f"/recordings/{RECORDING_ID}/segments/404/approve").status_code == 404


def test_an_unknown_action_is_not_found(client, recording, segment):
    assert client.post(f"/recordings/{RECORDING_ID}/actions/obliterate").status_code == 404
    assert (
        client.post(
            f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/boundaries/punch-sideways"
        ).status_code
        == 404
    )


@pytest.fixture
def discovered(store, recording):
    return store.saves(
        replace(recording, state="discovered")
    )


def test_the_ingest_control_is_offered_on_a_discovered_recording(client, discovered):
    page = client.get(f"/recordings/{RECORDING_ID}").get_data(as_text=True)
    assert reads_field(page, "ingest-control") == "Ingest"
    assert f"/recordings/{RECORDING_ID}/actions/ingest" in page
    assert reads_field(page, "ingest-standing") == "Nothing is queued for this Recording yet"


def test_the_ingest_control_is_not_offered_once_the_recording_is_past_discovery(
    client, recording
):
    page = client.get(f"/recordings/{RECORDING_ID}").get_data(as_text=True)
    assert reads_field(page, "ingest-control") is None


def test_ingesting_queues_the_download_without_performing_it(data_root, client, discovered):
    page = follows(client, client.post(f"/recordings/{RECORDING_ID}/actions/ingest"))
    assert "the download is queued; the worker will fetch it and run the pipeline" in page
    queued = lists_again(data_root, Job, recording_id=RECORDING_ID, kind="download")
    assert [(job.state, job.dedupe_key) for job in queued] == [
        ("queued", f"download:{RECORDING_ID}")
    ]
    assert reads_again(data_root, Recording, RECORDING_ID).local_path is None
    assert reads_again(data_root, Recording, RECORDING_ID).state == "discovered"


def test_ingesting_twice_queues_one_download_and_says_it_is_still_waiting(
    data_root, client, discovered
):
    client.post(f"/recordings/{RECORDING_ID}/actions/ingest")
    page = follows(client, client.post(f"/recordings/{RECORDING_ID}/actions/ingest"))
    assert "the download was already queued and is still waiting for the worker" in page
    assert len(lists_again(data_root, Job, recording_id=RECORDING_ID, kind="download")) == 1
    assert "Queued for download, waiting for the worker — 1 of 1 queued jobs" in page


def test_ingesting_while_the_download_runs_says_so(store, client, discovered):
    store.saves(
        Job(
            recording_id=RECORDING_ID,
            kind="download",
            state="running",
            max_attempts=5,
            dedupe_key=f"download:{RECORDING_ID}",
            queued_at=datetime(2026, 9, 13, 9, 30, tzinfo=UTC),
            started_at=datetime(2026, 9, 13, 9, 31, tzinfo=UTC),
        )
    )
    page = follows(client, client.post(f"/recordings/{RECORDING_ID}/actions/ingest"))
    assert "the download is already running" in page


def test_the_list_offers_the_ingest_control_for_a_discovered_recording(client, discovered):
    rows = reads_rows(client.get("/").get_data(as_text=True), "recording")
    assert [row["row-ingest-control"] for row in rows] == ["Ingest"]
    assert [row["ingest"] for row in rows] == ["none"]
    assert [row["row-ingest-standing"] for row in rows] == [
        "Nothing is queued for this Recording yet"
    ]


def test_the_ingest_control_stays_off_the_actions_row(client, discovered):
    page = client.get(f"/recordings/{RECORDING_ID}").get_data(as_text=True)
    assert [row["action"] for row in reads_rows(page, "action")] == ["Discard"]
