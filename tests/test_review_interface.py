from datetime import UTC, datetime

import pytest

from sermon.lists_recordings import formats_precise
from sermon.store import Evidence, Proposal, Recording, Segment, opens_store
from sermon.web import creates_app
from steps import _browser
from steps._peaks import writes_peaks
from steps._markup import reads_field, reads_role, reads_rows


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id="recording_20260913_090014",
            object_key="2026/09/13/recording_20260913_090014.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=7200.0,
        )
    )


def saves_segment(store, recording, **seconds):
    held = {
        "span_start_seconds": 1165.74,
        "span_end_seconds": 3000.0,
        "punch_in_seconds": 1165.74,
        "punch_out_seconds": 3000.0,
    } | seconds
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            **held,
        )
    )


def test_a_punch_in_just_before_its_span_does_not_open_the_page_with_dead_punch_controls(
    store, recording
):
    segment = saves_segment(store, recording, punch_in_seconds=1165.70)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    assert "disabled" not in page.split('data-role="punch"')[1].split("</ol>")[0]


def test_the_punch_controls_carry_the_span_the_client_judges_them_against(store, recording):
    segment = saves_segment(store, recording)
    page = (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{recording.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )
    punch = reads_role(page, "punch")
    assert float(punch["span-start-seconds"]) == segment.span_start_seconds
    assert float(punch["span-end-seconds"]) == segment.span_end_seconds
    assert punch["unavailable-reason"] == "the playhead is outside the Segment"


UNKNOWN_RECORDING = "recording_19990101_000000"
UNKNOWN_SEGMENT = 99999
NAMED_IN_THE_PATH = {
    "action": (
        "discard",
        "restore",
        "archive-whole-recording",
        "re-run-analysis",
        "create-segment",
        "split-segment",
        "merge-segments",
        "approve",
        "skip",
        "reopen",
        "revert",
        "classify",
    ),
    "edge": ("start", "end"),
    "boundary": ("punch-in", "punch-out"),
}
FORM = {
    "do": "set",
    "timecode": "1:00:00",
    "from": "1:00:00",
    "to": "1:30:00",
    "at": "1:10:00",
    "classification": "sermon",
}
JSON = {"seconds": 12.0, "date": "2026-09-13", "label": "Hebrews 12"}


def addresses_unknown_entities(app):
    for rule in app.url_map.iter_rules():
        if not {"recording_id", "segment_id"} & rule.arguments:
            continue
        method = sorted(rule.methods - {"HEAD", "OPTIONS"})[0]
        named = [name for name in rule.arguments if name in NAMED_IN_THE_PATH]
        choices = NAMED_IN_THE_PATH[named[0]] if named else (None,)
        for choice in choices:
            values = {"recording_id": UNKNOWN_RECORDING, "segment_id": UNKNOWN_SEGMENT}
            if named:
                values[named[0]] = choice
            built = rule.build(
                {name: value for name, value in values.items() if name in rule.arguments}
            )
            yield method, built[1]


def test_no_route_answers_500_for_an_unknown_recording_or_segment(store):
    app = creates_app(store=store)
    client = app.test_client()
    answered = {}
    for method, url in addresses_unknown_entities(app):
        sent = {"json": JSON} if url.startswith("/api/") else {"data": FORM}
        answered[f"{method} {url}"] = client.open(url, method=method, **sent).status_code
    assert len(answered) >= 30, answered
    assert {url: code for url, code in answered.items() if code != 404} == {}


def test_seeking_an_unknown_recording_holds_no_playhead_for_it(store):
    client = creates_app(store=store).test_client()
    assert (
        client.post(f"/api/recordings/{UNKNOWN_RECORDING}/seek", json={"seconds": 1234.5})
    ).status_code == 404
    recording = store.saves(
        Recording(
            recording_id=UNKNOWN_RECORDING,
            object_key=f"1999/01/01/{UNKNOWN_RECORDING}.flac",
            state="awaiting_review",
            started_at=datetime(1999, 1, 1, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=3600.0,
        )
    )
    shown = client.get(f"/api/recordings/{recording.recording_id}").get_json()
    assert shown["playhead_seconds"] == 0.0


def opens_segment(store, segment):
    return (
        creates_app(store=store)
        .test_client()
        .get(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )


def test_the_detail_page_shows_the_proposal_the_reviewer_is_deciding_on(store, recording):
    segment = saves_segment(store, recording)
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="high",
            boundary_confidence="low",
            punch_in_grade="moderate",
            punch_out_grade="hard",
            evidence=(
                Evidence(timecode=1800.5, finding="a closing prayer", implies="punch-out"),
                Evidence(timecode=1170.25, finding="a speaker change", implies="punch-in"),
            ),
            missing_evidence=("where the sermon ends",),
        )
    )
    page = opens_segment(store, segment)
    assert reads_field(page, "classification-confidence") == "high confidence"
    assert reads_field(page, "boundary-confidence") == "low confidence"
    assert reads_field(page, "punch-in-grade") == "moderate to place"
    assert reads_field(page, "punch-out-grade") == "hard to place"
    evidence = reads_rows(page, "evidence")
    assert [
        (row["evidence-at"], row["evidence-finding"], row["evidence-implies"]) for row in evidence
    ] == [
        ("0:19:30.25", "a speaker change", "punch-in"),
        ("0:30:00.50", "a closing prayer", "punch-out"),
    ]
    assert reads_field(page, "missing-evidence") == "nothing was found to show where the sermon ends"
    assert reads_field(page, "no-evidence") is None
    assert reads_field(page, "no-proposal") is None


def test_a_superseded_proposal_is_not_the_one_shown(store, recording):
    segment = saves_segment(store, recording)
    later = store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="medium",
            boundary_confidence="medium",
            punch_in_grade="easy",
            punch_out_grade="easy",
        )
    )
    store.saves(
        Proposal(
            segment_id=segment.segment_id,
            classification_confidence="low",
            boundary_confidence="low",
            punch_in_grade="hard",
            punch_out_grade="hard",
            superseded_by=later.proposal_id,
        )
    )
    page = opens_segment(store, segment)
    assert reads_field(page, "classification-confidence") == "medium confidence"
    assert reads_field(page, "punch-in-grade") == "easy to place"
    assert reads_field(page, "no-evidence") == "No evidence was recorded for this proposal."


def test_a_segment_with_no_proposal_says_so(store, recording):
    page = opens_segment(store, saves_segment(store, recording))
    assert reads_field(page, "no-proposal") == "No proposal has been recorded for this Segment."
    assert reads_field(page, "punch-in-grade") is None


A_HAIR_UNDER_A_BOUNDARY = (
    (59.999, "0:01:00.00"),
    (3599.9999, "1:00:00.00"),
    (3899.999, "1:05:00.00"),
    (86399.999, "24:00:00.00"),
    (59.994, "0:00:59.99"),
    (3051.25, "0:50:51.25"),
    (0.0, "0:00:00.00"),
)


@pytest.mark.parametrize(("seconds", "shown"), A_HAIR_UNDER_A_BOUNDARY)
def test_the_server_rounds_a_timecode_before_carrying_it(seconds, shown):
    assert formats_precise(seconds) == shown


def test_the_page_rounds_a_timecode_before_carrying_it(store, recording):
    segment = saves_segment(store, recording)
    writes_peaks(store, recording)
    with _browser.opens_page(store) as page:
        page.goto(
            f"/recordings/{recording.recording_id}?segment={segment.segment_id}"
            "&zoom=three+seconds&centre=3899.9&playhead=3899.899"
        )
        page.locator("body").click(position={"x": 5, "y": 5})
        page.keyboard.press(".")
        assert page.locator('.waveform [data-field="playhead"]').text_content() == "1:05:00.00"
        shown = page.evaluate(
            "(values) => values.map(formatsTimecode)",
            [seconds for seconds, _ in A_HAIR_UNDER_A_BOUNDARY],
        )
    assert shown == [timecode for _, timecode in A_HAIR_UNDER_A_BOUNDARY]


def test_a_colliding_label_can_be_changed_instead_of_replacing_the_file(store, recording):
    from sermon.shows_recording import NOTICES
    from sermon.store import Artifact, layout
    from steps import _forms, _web

    segment = saves_segment(store, recording)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=layout.published_path("2026-09-13 - Hebrews 12.mp3"),
            size_bytes=1,
            checksum="existing",
        )
    )
    approving = 'data-field="action-control">Approve'
    page = _web.opens_detail(store, recording.recording_id, segment=segment.segment_id)
    refused = _forms.submits(store, page, approving, label="Hebrews 12")
    assert reads_field(refused, "action-notice") == NOTICES["label-collides"]
    renamed = _forms.submits(store, refused, approving, label="Hebrews 12.1-3")
    assert reads_field(renamed, "action-notice") == NOTICES["approved"]
    assert store.loads(Segment, segment.segment_id).label == "Hebrews 12.1-3"


def test_publication_details_that_collide_answer_409_not_500(store, recording):
    from sermon.store import Artifact, layout

    segment = saves_segment(store, recording)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=layout.published_path("2026-09-13 - Hebrews 12.mp3"),
            size_bytes=1,
            checksum="existing",
        )
    )
    client = creates_app(store=store).test_client()
    url = f"/api/segments/{segment.segment_id}/publication"
    refused = client.put(url, json={"date": "2026-09-13", "label": "Hebrews 12"})
    assert refused.status_code == 409
    assert refused.get_json()["path"] == "published/2026-09-13 - Hebrews 12.mp3"
    replaced = client.put(url, json={"date": "2026-09-13", "label": "Hebrews 12", "replace": True})
    assert replaced.status_code == 200


def test_a_publication_date_is_kept_for_the_log_and_never_names_the_file(store, recording):
    from datetime import date

    from sermon.approves_segment import ApprovesSegment
    from sermon.jobs.renders_segment import RendersSegment
    from sermon.sends_notification import SendsNotification
    from sermon.store import Artifact

    segment = saves_segment(store, recording)
    client = creates_app(store=store).test_client()
    url = f"/api/segments/{segment.segment_id}/publication"
    assert client.put(url, json={"date": "2026-09-20", "label": "Hebrews 12"}).status_code == 200
    approved = ApprovesSegment(store=store)(store.loads(Segment, segment.segment_id))
    RendersSegment(store=store, steps=lambda _name: None, notifies=SendsNotification(store=store))(
        approved
    )
    assert store.loads(Segment, segment.segment_id).publication_date == date(2026, 9, 20)
    artifact = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")[0]
    assert artifact.path == "published/2026-09-13 - Hebrews 12.mp3"


def test_a_collision_is_judged_on_the_recording_date_not_the_publication_date(store, recording):
    from sermon.store import Artifact, layout

    segment = saves_segment(store, recording)
    store.saves(
        Artifact(
            recording_id=recording.recording_id,
            kind="rendered_mp3",
            path=layout.published_path("2026-09-13 - Hebrews 12.mp3"),
            size_bytes=1,
            checksum="existing",
        )
    )
    client = creates_app(store=store).test_client()
    url = f"/api/segments/{segment.segment_id}/publication"
    refused = client.put(url, json={"date": "2026-09-20", "label": "Hebrews 12"})
    assert refused.status_code == 409
    assert refused.get_json()["path"] == "published/2026-09-13 - Hebrews 12.mp3"
