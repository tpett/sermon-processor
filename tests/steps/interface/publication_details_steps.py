from datetime import UTC, datetime, date

from pytest_bdd import given, parsers, then, when

from sermon.records_publication_details import RecordsPublicationDetails
from sermon.shows_recording import NOTICES
from sermon.store import Recording, Segment
from steps import _forms
from steps._markup import reads_field


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
def _(store, segment):
    recording = store.loads(Recording, segment.recording_id)
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


@given(parsers.parse('the date is "{value}" and the label is "{label}"'), target_fixture="segment")
def _(store, segment, value, label):
    return RecordsPublicationDetails(store=store).saves(
        segment,
        publication_date=date.fromisoformat(value),
        label=label,
    )


@when("the Segment is processed", target_fixture="processed_segment")
def _(store, segment, clock):
    from sermon.approves_segment import ApprovesSegment
    from sermon.jobs.renders_segment import RunsRenderJob
    from sermon.sends_notification import SendsNotification

    ApprovesSegment(store=store, clock=clock)(store.loads(Segment, segment.segment_id))
    RunsRenderJob(store=store, steps=lambda _name: None, notifies=SendsNotification(store=store), clock=clock)()
    return store.loads(Segment, segment.segment_id)


@then(parsers.parse('the output file is named "{filename}"'))
def _(store, processed_segment, filename):
    from sermon.store import Artifact, layout

    artifacts = store.lists(Artifact, segment_id=processed_segment.segment_id, kind="rendered_mp3")
    assert artifacts[0].path == layout.published_path(filename)


@then("I can change the label or confirm that this replaces the previous file")
def _(store, segment, detail_page):
    approving = 'data-field="action-control">Approve'
    _, offered = _forms.finds_form(detail_page, approving)
    assert _forms.offers_field(offered, "label"), "the label cannot be changed here"
    assert _forms.offers_field(offered, "replace"), "replacing the previous file is not offered"
    confirmed = _forms.submits(store, detail_page, approving, replace="yes")
    assert reads_field(confirmed, "action-notice") == NOTICES["approved"]
    assert store.loads(Segment, segment.segment_id).label == "Hebrews 12.4-11"
