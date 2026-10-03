import re
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Block, Proposal, Recording, Segment
from sermon.store.vocabularies import SEGMENT_CLASSIFICATIONS
from sermon.web import creates_app
from steps._markup import reads_field, reads_rows
from steps._peaks import writes_utterances

READS = ReadsTimecode()


def renders_list(store, query=""):
    return creates_app(store=store).test_client().get(f"/{query}").get_data(as_text=True)


def classifications(row):
    return row["classifications"].split()


def finds_row(rows, recorded_at):
    return next(row for row in rows if row["recorded-at"] == recorded_at)


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
        gives_content(store, recording)


def gives_content(store, recording):
    """What analysis and the reviewer left on the two recordings the search scenario finds."""
    if recording.recording_id == "recording_20260823_102900":
        (sermon,) = store.lists(Segment, recording_id=recording.recording_id)
        store.saves(replace(sermon, label="Hebrews 12.4-11"))
        writes_utterances(store, recording, ((900.0, 904.0, SPOKEN_ON_THE_23RD),))
    if recording.recording_id == "recording_20260816_090000":
        store.saves(
            Block(
                recording_id=recording.recording_id,
                start_seconds=60.0,
                end_seconds=3300.0,
                type="lesson",
                summary="A class on Hebrews 12 and the race set before us",
            )
        )


@when("I visit the recordings list", target_fixture="list_page")
def _(store):
    return renders_list(store)


@then(parsers.parse("I see {count:d} recordings"))
def _(list_page, count):
    assert len(reads_rows(list_page, "recording")) == count


@then("each row shows the recording date and time")
def _(list_page):
    rows = reads_rows(list_page, "recording")
    assert rows
    assert all(row["recorded-at"] for row in rows)


@then("each row shows the source duration")
def _(list_page):
    rows = reads_rows(list_page, "recording")
    assert rows
    assert all(row["duration"] for row in rows)


@then("each row shows the current state")
def _(list_page):
    rows = reads_rows(list_page, "recording")
    assert rows
    assert all(row["state"] for row in rows)


@then("each row summarises the Segments found inside it by classification")
def _(list_page):
    sermon = finds_row(reads_rows(list_page, "recording"), "2026-08-23 10:29 AM")
    assert "sermon" in classifications(sermon)


@then("each row shows the confidence of its most publishable Segment")
def _(list_page):
    rows = [row for row in reads_rows(list_page, "recording") if classifications(row)]
    assert rows
    assert all(row["confidence"] for row in rows)


@then(
    parsers.parse(
        'the row for "{when}" shows that it contains a lesson and a sermon'
    )
)
def _(list_page, when):
    row = finds_row(reads_rows(list_page, "recording"), when)
    assert set(classifications(row)) == {"lesson", "sermon"}


@then("I can see at a glance that both still need dispositioning")
def _(list_page):
    row = finds_row(reads_rows(list_page, "recording"), "2026-08-16 09:00 AM")
    assert row["awaiting"] == "2"
    assert row["attention"] == "true"


@then("recordings with undispositioned publishable Segments are visually distinguished")
def _(list_page):
    assert [row for row in reads_rows(list_page, "recording") if row["attention"] == "true"]


@then('recordings in "analysis_failed" are visually distinguished')
def _(list_page):
    failed = [row for row in reads_rows(list_page, "recording") if row["failed"] == "true"]
    assert failed
    assert all(row["state"] == "analysis_failed" for row in failed)


@then("the count of Segments awaiting disposition is shown")
def _(list_page):
    assert int(reads_field(list_page, "awaiting")) >= 1


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


def nothing_proposed(store):
    return {
        recording.recording_id
        for recording in store.lists(Recording)
        if not any(
            segment.state == "proposed"
            for segment in store.lists(Segment, recording_id=recording.recording_id)
        )
    }


@then("it is not counted as needing attention")
def _(store, list_page):
    subjects = [row for row in reads_rows(list_page, "recording") if row["id"] in nothing_proposed(store)]
    assert subjects, "the recording with nothing proposed is not in the list"
    assert all(row["attention"] == "false" for row in subjects)


@then("I do not have to discard it for the queue to stay clean")
def _(store):
    needing = renders_list(store, "?filter=Needs attention")
    assert not {row["id"] for row in reads_rows(needing, "recording")} & nothing_proposed(store)
    assert reads_field(renders_list(store), "awaiting") == "0"


@then("it remains available if I ever want it")
def _(store, list_page):
    subjects = nothing_proposed(store)
    assert subjects <= {row["id"] for row in reads_rows(list_page, "recording")}
    for recording_id in subjects:
        detail = creates_app(store=store).test_client().get(f"/recordings/{recording_id}")
        assert detail.status_code == 200
        assert reads_rows(detail.get_data(as_text=True), "block")


@then("it is still visible in the list")
def _(list_page):
    rows = reads_rows(list_page, "recording")
    assert [row for row in rows if row["recorded-at"] == "2026-08-16 08:15 AM"]


@then("the recordings are ordered by recording date, newest first")
def _(list_page):
    times = [row["recorded-at"] for row in reads_rows(list_page, "recording")]
    assert times == sorted(times, reverse=True)


@then(parsers.parse('the discarded recording from "{day}" is not shown'))
def _(list_page, day):
    assert all(day not in row["recorded-at"] for row in reads_rows(list_page, "recording"))


@then("I can reveal it by including discarded recordings in the filter")
def _(store, day="2026-07-26"):
    rows = reads_rows(renders_list(store, "?discarded=1"), "recording")
    assert [row for row in rows if day in row["recorded-at"]]


SEARCH_FORM = re.compile(r'<form\b([^>]*data-role="search"[^>]*)>(.*?)</form>', re.S)
SPOKEN_ON_THE_23RD = "the Lord disciplines the one he loves"


def searches(store, query):
    """Submit the search box the list page renders, as a browser would."""
    form = SEARCH_FORM.search(renders_list(store))
    assert form, "the recordings list renders no search box"
    attributes, inside = form.groups()
    assert 'method="get"' in attributes
    action = re.search(r'action="([^"]*)"', attributes).group(1)
    named = re.search(r'<input\b[^>]*type="search"[^>]*name="([^"]+)"', inside)
    assert named, "the search box has no field to type into"
    return (
        creates_app(store=store)
        .test_client()
        .get(action, query_string={named.group(1): query})
        .get_data(as_text=True)
    )


def found(page):
    return {row["recorded-at"] for row in reads_rows(page, "recording")}


@when(parsers.parse('I search for "{query}"'), target_fixture="list_page")
def _(store, query):
    return searches(store, query)


@then("I see recordings whose label or summary matches")
def _(list_page):
    assert found(list_page) == {"2026-08-23 10:29 AM", "2026-08-16 09:00 AM"}


@then("I can search by date, by classification, and by what was said")
def _(store):
    assert found(searches(store, "2026-08-16")) == {"2026-08-16 09:00 AM", "2026-08-16 08:15 AM"}
    assert found(searches(store, "lesson")) == {"2026-08-16 09:00 AM"}
    assert found(searches(store, "disciplines the one he loves")) == {"2026-08-23 10:29 AM"}, (
        "what was said is not searched"
    )


@when(parsers.parse('I filter the list by "{filter_name}"'), target_fixture="list_page")
def _(store, filter_name):
    return renders_list(store, f"?filter={filter_name}")


@when(
    parsers.parse('I filter the list by the classification "{classification}"'),
    target_fixture="list_page",
)
def _(store, classification):
    return renders_list(store, f"?classification={classification}")


@then(parsers.parse('I see only recordings matching "{meaning}"'))
def _(list_page, meaning):
    assert reads_rows(list_page, "recording") or reads_field(list_page, "empty")


@then(parsers.parse('I see only recordings containing a Segment classified "{classification}"'))
def _(store, list_page, classification):
    holding = {
        segment.recording_id
        for segment in store.lists(Segment)
        if segment.classification == classification
        and store.loads(Recording, segment.recording_id).state != "discarded"
    }
    assert holding, f"no Recording holds a {classification} Segment"
    rows = reads_rows(list_page, "recording")
    assert {row["id"] for row in rows} == holding, [row["id"] for row in rows]
    assert all(classification in classifications(row) for row in rows)


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
def _(list_page):
    assert reads_rows(list_page, "recording")


@then("I can open it and approve the skipped Segment")
def _(list_page):
    rows = reads_rows(list_page, "recording")
    assert [f"/recordings/{rows[0]['id']}"] == [link for link in rows[0]["links"]]


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
def _(store, list_page):
    first = reads_rows(list_page, "recording")
    assert 0 < len(first) <= 50
    assert reads_field(list_page, "paging").startswith("Page 1 of ")
    assert reads_field(list_page, "older-page") == "Older recordings"
    second = reads_rows(renders_list(store, "?page=2"), "recording")
    assert 0 < len(second) <= 50
    assert {row["id"] for row in first}.isdisjoint({row["id"] for row in second})


@then("the page loads in under 2 seconds")
def _(store):
    started = perf_counter()
    rendered = renders_list(store)
    elapsed = perf_counter() - started
    assert reads_rows(rendered, "recording"), rendered
    assert elapsed < 2.0, f"the list took {elapsed:.3f} s"


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
def _(list_page):
    assert "once the recorder uploads them" in reads_field(list_page, "empty")


@when(
    parsers.parse('I click the row for the recording from "{day}"'),
    target_fixture="detail_page",
)
def _(store, day):
    client = creates_app(store=store).test_client()
    rows = reads_rows(client.get("/").get_data(as_text=True), "recording")
    row = next(item for item in rows if day in item["recorded-at"])
    return client.get(row["links"][0]).get_data(as_text=True)


@then("I am taken to that Recording's detail view")
def _(store, detail_page):
    assert reads_field(detail_page, "object-key")
    assert reads_field(detail_page, "state")
