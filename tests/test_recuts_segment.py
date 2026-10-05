import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sermon.analysis.stages import _is_the_reviewers
from sermon.approves_segment import ApprovesSegment
from sermon.jobs.renders_segment import RunsRenderJob, StepFailed
from sermon.lists_notifications import links_of
from sermon.raises_notification import RENDER_COMPLETE
from sermon.recuts_segment import RecutsSegment, SegmentNotComplete
from sermon.records_publication_details import FilenameCollision, RecordsPublicationDetails
from sermon.reopens_segment import ReopensSegment
from sermon.store import Artifact, Notification, Recording, Segment, layout, opens_store
from sermon.web import creates_app

FROZEN = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
LABEL = "Hebrews 13.9-14"
PUBLISHED = layout.published_path(f"2026-10-04 - {LABEL}.mp3")


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def clock():
    return FROZEN


def writes_the_cut(source, punch_in, punch_out, destination, *, channel=0, removed=()):
    Path(destination).write_text(json.dumps([punch_in, punch_out]))
    return type(
        "Rendered",
        (),
        {
            "settings": {},
            "input_loudness_lufs": None,
            "achieved_loudness_lufs": None,
            "achieved_true_peak_dbtp": None,
        },
    )()


def fails_to_render(source, punch_in, punch_out, destination, *, channel=0, removed=()):
    Path(destination).write_text("half an mp3")
    raise StepFailed("encode", "the encoder stopped")


def renders(store, renderer=writes_the_cut):
    RunsRenderJob(
        store=store, steps=lambda _name: None, notifies=lambda _n: None, clock=clock, renders=renderer
    )()


def recording(store):
    return store.saves(
        Recording(
            recording_id="recording_20261004_100000",
            object_key="recordings/recording_20261004_100000.flac",
            state="awaiting_review",
            started_at=datetime(2026, 10, 4, 10, 0, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=7200.0,
        )
    )


def complete(store, *, label=LABEL, punch_in=1000.0, punch_out=3000.0):
    segment = store.saves(
        Segment(
            recording_id=recording(store).recording_id,
            classification="sermon",
            state="proposed",
            intent="publish",
            label=label,
            span_start_seconds=punch_in - 100.0,
            span_end_seconds=punch_out + 100.0,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
        )
    )
    ApprovesSegment(store=store, clock=clock)(segment)
    renders(store)
    return store.loads(Segment, segment.segment_id)


def renders_of(store, segment):
    return store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")


def page(store, segment):
    return (
        creates_app(store=store, clock=clock)
        .test_client()
        .get(f"/recordings/{segment.recording_id}?segment={segment.segment_id}")
        .get_data(as_text=True)
    )


def approves_through_the_form(store, segment, label):
    return creates_app(store=store, clock=clock).test_client().post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/approve",
        data={"intent": "publish", "label": label},
    )


@pytest.mark.parametrize("state", ["proposed", "approved", "processing", "skipped", "recut"])
def test_only_a_complete_segment_can_be_recut(store, state):
    segment = store.saves(replace(complete(store), state=state))
    with pytest.raises(SegmentNotComplete):
        RecutsSegment(store=store, clock=clock)(segment)


def test_the_page_offers_recut_only_on_a_complete_segment(store):
    segment = complete(store)
    assert 'data-field="action-control">Re-cut<' in page(store, segment)
    RecutsSegment(store=store, clock=clock)(segment)
    assert 'data-field="action-control">Re-cut<' not in page(store, segment)


def test_reapproving_under_its_own_published_name_is_not_a_collision(store):
    segment = RecutsSegment(store=store, clock=clock)(complete(store))
    approves_through_the_form(store, segment, LABEL)
    assert store.loads(Segment, segment.segment_id).state == "approved"


def test_another_segments_published_name_still_collides(store):
    complete(store)
    other = store.saves(
        Segment(
            recording_id="recording_20261004_100000",
            classification="lesson",
            state="proposed",
            span_start_seconds=4000.0,
            span_end_seconds=5000.0,
            punch_in_seconds=4000.0,
            punch_out_seconds=5000.0,
        )
    )
    with pytest.raises(FilenameCollision):
        RecordsPublicationDetails(store=store).saves(
            other, publication_date=FROZEN.date(), label=LABEL
        )


def test_a_name_another_segment_has_since_given_up_is_free(store):
    first = RecutsSegment(store=store, clock=clock)(complete(store))
    ApprovesSegment(store=store, clock=clock)(store.saves(replace(first, label="Renamed")))
    renders(store)
    other = store.saves(replace(first, segment_id=None, state="proposed", label=None))
    RecordsPublicationDetails(store=store).saves(other, publication_date=FROZEN.date(), label=LABEL)


def test_a_renamed_rerender_deletes_the_earlier_file(store):
    segment = RecutsSegment(store=store, clock=clock)(complete(store))
    ApprovesSegment(store=store, clock=clock)(store.saves(replace(segment, label="Renamed")))
    renders(store)
    earlier, current = renders_of(store, segment)
    assert earlier.superseded_by == current.artifact_id
    assert not store.resolves(earlier).exists()
    assert sorted(path.name for path in store.resolves(current).parent.iterdir()) == [
        "2026-10-04 - Renamed.mp3"
    ]


def test_a_failed_rerender_leaves_the_published_mp3_in_place_and_offered(store):
    segment = RecutsSegment(store=store, clock=clock)(complete(store))
    published = store.resolves(renders_of(store, segment)[0]).read_text()
    ApprovesSegment(store=store, clock=clock)(
        store.saves(replace(segment, punch_out_seconds=2900.0))
    )
    renders(store, fails_to_render)
    assert store.resolves(renders_of(store, segment)[0]).read_text() == published
    assert [item.superseded_by for item in renders_of(store, segment)] == [None]
    assert sorted(path.name for path in store.resolves(renders_of(store, segment)[0]).parent.iterdir()) == [
        Path(PUBLISHED).name
    ]
    assert f"/api/artifacts/{PUBLISHED}" in page(store, store.loads(Segment, segment.segment_id))


def test_a_segment_that_never_rendered_offers_no_mp3_after_a_cancel(store):
    segment = store.saves(
        Segment(
            recording_id=recording(store).recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=0.0,
            span_end_seconds=100.0,
            punch_in_seconds=0.0,
            punch_out_seconds=100.0,
        )
    )
    approved = ApprovesSegment(store=store, clock=clock)(segment)
    assert ReopensSegment(store=store, clock=clock)(approved).state == "proposed"


def test_a_rerender_tells_the_reviewer_once_and_links_only_the_current_mp3(store):
    segment = RecutsSegment(store=store, clock=clock)(complete(store))
    told = []
    ApprovesSegment(store=store, clock=clock)(store.saves(replace(segment, label="Renamed")))
    RunsRenderJob(
        store=store, steps=lambda _name: None, notifies=told.append, clock=clock, renders=writes_the_cut
    )()
    assert [item.kind for item in told] == [RENDER_COMPLETE]
    ready = store.lists(Notification, segment_id=segment.segment_id, kind=RENDER_COMPLETE)
    assert len(ready) == 2
    downloads = [href for href, name in links_of(store, ready[-1]) if name == "Download the MP3"]
    assert downloads == ["/api/artifacts/published/2026-10-04 - Renamed.mp3"]


def test_reanalysis_leaves_a_recut_segment_alone(store):
    segment = RecutsSegment(store=store, clock=clock)(complete(store))
    assert _is_the_reviewers(segment)

