from datetime import UTC, datetime, date

from pytest_bdd import given, parsers, then, when

from sermon.records_publication_details import RecordsPublicationDetails
from sermon.store import Recording, Segment


@given(parsers.parse('a Recording from "{when}"'), target_fixture="recording")
def _(store, when):
    started = datetime.strptime(when, "%Y-%m-%d %I:%M %p").replace(tzinfo=UTC)
    return store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="2026/08/23/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=started,
            started_at_source="key",
            size_bytes=1,
        )
    )


@given(
    parsers.parse('a Segment classified "{classification}" awaiting approval'),
    target_fixture="segment",
)
def _(store, recording, classification):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=7200.0,
            span_end_seconds=9900.0,
            punch_in_seconds=7200.0,
            punch_out_seconds=9900.0,
        )
    )


@when("I open the Segment", target_fixture="publication_form")
def _(store, segment, recording):
    return RecordsPublicationDetails(store=store).opens(segment, recording)


@then("I can enter:")
def _(publication_form, datatable):
    fields = {row[0] for row in datatable[1:]}
    assert fields <= set(publication_form.fields())


@then("the details are saved with the Segment")
def _(store, segment):
    saved = RecordsPublicationDetails(store=store).saves(
        segment,
        publication_date=date(2026, 8, 23),
        label="Hebrews 12.4-11",
    )
    stored = store.loads(Segment, saved.segment_id)
    assert stored.publication_date == date(2026, 8, 23)
    assert stored.label == "Hebrews 12.4-11"


@then(parsers.parse('the date is prefilled with "{value}"'))
def _(publication_form, value):
    assert publication_form.fields()["Date"] == value


@then("I can change it")
def _(store, segment):
    saved = RecordsPublicationDetails(store=store).saves(
        segment,
        publication_date=date(2026, 8, 24),
        label="Hebrews 12.4-11",
    )
    assert store.loads(Segment, saved.segment_id).publication_date == date(2026, 8, 24)
