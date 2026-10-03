from pytest_bdd import then

from sermon.store import Proposal, Segment
from steps import _web
from steps._markup import reads_field


@then("the grade is shown to the reviewer")
def _(store):
    segment = store.lists(Segment)[0]
    proposals = store.lists(Proposal, segment_id=segment.segment_id)
    assert proposals, "no Proposal was recorded for the Segment, so no grade can be shown"
    page = _web.opens_detail(store, segment.recording_id, segment=segment.segment_id)
    assert reads_field(page, "punch-in-grade") == f"{proposals[-1].punch_in_grade} to place"
