import pytest

from sermon.lists_recordings import says_state
from sermon.store import Segment


def segment(state, intent=None):
    return Segment(
        recording_id="recording_20260913_090014",
        classification="sermon",
        state=state,
        intent=intent,
        span_start_seconds=0.0,
        span_end_seconds=10.0,
        punch_in_seconds=0.0,
        punch_out_seconds=10.0,
    )


@pytest.mark.parametrize(
    ("states", "label", "tone"),
    [
        (["complete"], "Published", "muted"),
        (["complete", "skipped"], "Published", "muted"),
        (["approved"], "Approved, waiting to render", "accent"),
        (["processing"], "Rendering", "accent"),
        (["approved", "skipped"], "Approved, waiting to render", "accent"),
        (["processing", "approved"], "Rendering", "accent"),
        (["processing_failed"], "Render failed", "bad"),
        (["processing_failed", "processing"], "Render failed", "bad"),
        (["skipped"], "Skipped", "muted"),
        (["skipped", "recut"], "Skipped", "muted"),
        (["recut"], "Nothing to publish", "muted"),
        ([], "Nothing to publish", "muted"),
    ],
)
def test_a_reviewed_recording_says_what_became_of_its_segments(states, label, tone):
    assert says_state("reviewed", [segment(state) for state in states]) == (label, tone)


def test_a_reviewed_recording_whose_complete_segments_are_all_archived_says_archived():
    assert says_state("reviewed", [segment("complete", intent="archive")]) == (
        "Archived",
        "muted",
    )
