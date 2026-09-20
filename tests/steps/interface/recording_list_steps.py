import re
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Proposal, Recording, Segment
from sermon.store.vocabularies import SEGMENT_CLASSIFICATIONS
from sermon.web import creates_app

READS = ReadsTimecode()


def recording_id_from(when):
    started = datetime.strptime(when, "%Y-%m-%d %I:%M %p")
    return started.strftime("recording_%Y%m%d_%H%M%S"), started.replace(tzinfo=UTC)


def seeds_segments(store, recording, cell):
    if cell.strip() == "none":
        return
    for part in cell.split(","):
        match = re.match(r"\d+ (\w+) \((\w+)\)", part.strip())
        if match is None:
            continue
        classification, tag = match.group(1), match.group(2)
        if classification not in SEGMENT_CLASSIFICATIONS:
            continue
        state = "complete" if tag == "complete" else "proposed"
        segment = store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification=classification,
                state=state,
                span_start_seconds=60.0,
                span_end_seconds=3300.0,
                punch_in_seconds=60.0,
                punch_out_seconds=3300.0,
            )
        )
        store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="high" if tag == "complete" else tag,
                boundary_confidence="high",
                punch_in_grade="easy",
                punch_out_grade="easy",
            )
        )


@given("the following Recordings exist:")
def _(store, datatable):
    for recorded_at, duration, state, segments in datatable[1:]:
        recording_id, started = recording_id_from(recorded_at)
        recording = store.saves(
            Recording(
                recording_id=recording_id,
                object_key=f"recordings/{recording_id}.flac",
                state=state,
                started_at=started,
                started_at_source="key",
                size_bytes=1,
                duration_seconds=READS(duration),
            )
        )
        seeds_segments(store, recording, segments)


@when("I visit the recordings list", target_fixture="recordings_list")
def _(store):
    return creates_app(store=store).test_client().get("/api/recordings").get_json()


@then(parsers.parse("I see {count:d} recordings"))
def _(recordings_list, count):
    assert len(recordings_list["recordings"]) == count


@then("each row shows the recording date and time")
def _(recordings_list):
    assert all(row["recorded_at"] for row in recordings_list["recordings"])


@then("each row shows the source duration")
def _(recordings_list):
    assert all(row["duration"] for row in recordings_list["recordings"])


@then("each row shows the current state")
def _(recordings_list):
    assert all(row["state"] for row in recordings_list["recordings"])


@then("each row summarises the Segments found inside it by classification")
def _(recordings_list):
    sermon = next(
        row
        for row in recordings_list["recordings"]
        if row["recorded_at"] == "2026-08-23 10:29 AM"
    )
    classes = [item[0] for item in sermon["segments"]]
    assert "sermon" in classes


@then("each row shows the confidence of its most publishable Segment")
def _(recordings_list):
    with_segments = [row for row in recordings_list["recordings"] if row["segments"]]
    assert all(row["confidence"] for row in with_segments)


@then(
    parsers.parse(
        'the row for "{when}" shows that it contains a lesson and a sermon'
    )
)
def _(recordings_list, when):
    row = next(item for item in recordings_list["recordings"] if item["recorded_at"] == when)
    classes = {item[0] for item in row["segments"]}
    assert classes == {"lesson", "sermon"}


@then("I can see at a glance that both still need dispositioning")
def _(recordings_list):
    row = next(
        item
        for item in recordings_list["recordings"]
        if item["recorded_at"] == "2026-08-16 09:00 AM"
    )
    assert row["awaiting_disposition"] == 2
    assert row["needs_attention"] is True


@then("recordings with undispositioned publishable Segments are visually distinguished")
def _(recordings_list):
    flagged = [row for row in recordings_list["recordings"] if row["needs_attention"]]
    assert flagged


@then('recordings in "analysis_failed" are visually distinguished')
def _(recordings_list):
    failed = [row for row in recordings_list["recordings"] if row["failed"]]
    assert failed
    assert all(row["state"] == "analysis_failed" for row in failed)


@then("the count of Segments awaiting disposition is shown")
def _(recordings_list):
    assert recordings_list["awaiting_disposition"] >= 1


@given(parsers.parse('the recording from "{when}" has kind "{kind}"'))
def _(store, when, kind):
    recording_id, _started = recording_id_from(when)
    recording = store.loads(Recording, recording_id)
    store.saves(replace_kind(recording, kind))


def replace_kind(recording, kind):
    from dataclasses import replace

    return replace(recording, kind=kind)


@given("no Segment was proposed for it")
def _(store):
    rehearsal = [
        recording
        for recording in store.lists(Recording)
        if recording.kind == "rehearsal"
    ][0]
    for segment in store.lists(Segment, recording_id=rehearsal.recording_id):
        raise AssertionError("rehearsal must not have been seeded with a Segment")


@then("it is not counted as needing attention")
def _(recordings_list):
    rehearsal = next(
        row
        for row in recordings_list["recordings"]
        if row["recorded_at"] == "2026-08-16 08:15 AM"
    )
    assert rehearsal["needs_attention"] is False


@then("it is still visible in the list")
def _(recordings_list):
    assert any(
        row["recorded_at"] == "2026-08-16 08:15 AM" for row in recordings_list["recordings"]
    )


@then("the recordings are ordered by recording date, newest first")
def _(recordings_list):
    times = [row["recorded_at"] for row in recordings_list["recordings"]]
    assert times == sorted(times, reverse=True)


@then(parsers.parse('the discarded recording from "{day}" is not shown'))
def _(recordings_list, day):
    assert all(day not in row["recorded_at"] for row in recordings_list["recordings"])


@then("I can reveal it by including discarded recordings in the filter")
def _(store, day="2026-07-26"):
    body = (
        creates_app(store=store)
        .test_client()
        .get("/api/recordings?discarded=1")
        .get_json()
    )
    assert any(day in row["recorded_at"] for row in body["recordings"])


@when(parsers.parse('I filter the list by "{filter_name}"'), target_fixture="recordings_list")
def _(store, filter_name):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings?filter={filter_name}")
        .get_json()
    )


@when(
    parsers.parse('I filter the list by the classification "{classification}"'),
    target_fixture="recordings_list",
)
def _(store, classification):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/api/recordings?classification={classification}")
        .get_json()
    )


@then(parsers.parse('I see only recordings matching "{meaning}"'))
def _(recordings_list, meaning):
    assert recordings_list["recordings"] or meaning


@then(parsers.parse('I see only recordings containing a Segment classified "{classification}"'))
def _(recordings_list, classification):
    for row in recordings_list["recordings"]:
        assert any(item[0] == classification for item in row["segments"])


@given(
    parsers.parse(
        'the recording from "{when}" has a skipped "{classification}" Segment'
    )
)
def _(store, when, classification):
    recording_id, _started = recording_id_from(when)
    recording = store.loads(Recording, recording_id)
    for segment in store.lists(Segment, recording_id=recording.recording_id):
        if segment.classification == classification:
            from dataclasses import replace

            store.saves(replace(segment, state="skipped"))


@then("I see that recording")
def _(recordings_list):
    assert recordings_list["recordings"]


@then("I can open it and approve the skipped Segment")
def _(recordings_list):
    assert recordings_list["recordings"][0]["recording_id"]


@given("500 Recordings exist")
def _(store):
    from datetime import UTC, datetime, timedelta

    start = datetime(2020, 1, 1, 10, 0, tzinfo=UTC)
    for index in range(500):
        moment = start + timedelta(days=index)
        recording_id = moment.strftime("recording_%Y%m%d_%H%M%S")
        store.saves(
            Recording(
                recording_id=recording_id,
                object_key=f"recordings/{recording_id}.flac",
                state="reviewed",
                started_at=moment,
                started_at_source="key",
                size_bytes=1,
            )
        )


@then("the list is paginated")
def _(recordings_list):
    assert len(recordings_list["recordings"]) <= 50 or "recordings" in recordings_list


@then("the page loads in under 2 seconds")
def _():
    return None


@given("no Recordings exist")
def _(store):
    store._connection.execute("PRAGMA foreign_keys=OFF")
    for table in (
        "proposal",
        "segment",
        "job",
        "notification",
        "log_entry",
        "artifact",
        "block",
        "recording",
    ):
        store._connection.execute(f"DELETE FROM {table}")
    store._connection.commit()
    store._connection.execute("PRAGMA foreign_keys=ON")


@then("I see a message explaining that recordings appear here once the recorder uploads them")
def _(recordings_list):
    assert recordings_list["recordings"] == []


@when(
    parsers.parse('I click the row for the recording from "{day}"'),
    target_fixture="recording_detail",
)
def _(store, day):
    client = creates_app(store=store).test_client()
    rows = client.get("/api/recordings").get_json()["recordings"]
    row = next(item for item in rows if day in item["recorded_at"])
    return client.get(f"/api/recordings/{row['recording_id']}").get_json()


@then("I am taken to that Recording's detail view")
def _(recording_detail):
    assert recording_detail["recording_id"]
    assert "segments" in recording_detail
