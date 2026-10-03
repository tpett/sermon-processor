import re
from dataclasses import replace
from datetime import UTC, date, datetime

from pytest_bdd import given, parsers, then, when

from sermon.records_publication_details import RecordsPublicationDetails
from sermon.shows_recording import NOTICES
from sermon.store import Recording, Segment
from steps import _forms, _web
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


APPROVING = 'data-field="action-control">Approve'
DATE_FIELD = re.compile(r'<input\b[^>]*(?:type="date"|name="[^"]*date[^"]*")', re.I)


def offers_no_date(page):
    assert not DATE_FIELD.search(page), "the page asks for a date"


def opens_segment(store, segment):
    return _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)


@then("I can enter a publication label")
def _(store, segment):
    _, approving = _forms.finds_form(opens_segment(store, segment), APPROVING)
    assert _forms.offers_field(approving, "label"), "the approval form takes no label"


@then("I am not asked for a date")
def _(store, segment):
    offers_no_date(opens_segment(store, segment))


@when(parsers.parse('I approve the Segment with the label "{label}"'), target_fixture="detail_page")
def _(store, segment, label):
    return _forms.submits(store, opens_segment(store, segment), APPROVING, intent="publish", label=label)


@then(parsers.parse('the label "{label}" is saved with the Segment'))
def _(store, segment, detail_page, label):
    assert reads_field(detail_page, "action-notice") == NOTICES["approved"]
    assert reads_field(detail_page, "label") == label
    assert store.loads(Segment, segment.segment_id).label == label


@then(parsers.parse('the publication date "{value}" is recorded with the Segment'))
def _(store, segment, value):
    assert store.loads(Segment, segment.segment_id).publication_date == date.fromisoformat(value)


@then("the page does not offer to change it")
def _(detail_page):
    offers_no_date(detail_page)


@when(
    parsers.parse('the publication details "{value}" and "{label}" are recorded for it'),
    target_fixture="segment",
)
def _(store, segment, value, label):
    answered = _web.opens_app(store).test_client().put(
        f"/api/segments/{segment.segment_id}/publication",
        json={"date": value, "label": label},
    )
    assert answered.status_code == 200, answered.get_data(as_text=True)
    return store.loads(Segment, segment.segment_id)


@given(
    parsers.parse('the Recording was made on "{value}" and the label is "{label}"'),
    target_fixture="segment",
)
def _(store, segment, value, label):
    recording = store.loads(Recording, segment.recording_id)
    made = datetime.combine(date.fromisoformat(value), recording.started_at.timetz())
    store.saves(replace(recording, started_at=made))
    return store.saves(replace(segment, label=label))


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
