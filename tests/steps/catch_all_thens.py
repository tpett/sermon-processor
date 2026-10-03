from pytest_bdd import given, then, when


@then('the Segment stays in "proposed"')
def _(store, segment, detail_page):
    from sermon.store import Segment
    from steps._markup import reads_field

    assert store.loads(Segment, segment.segment_id).state == "proposed"
    assert reads_field(detail_page, "segment-state") == "proposed"


@when("I approve Segment 2 and leave Segment 1 alone")
def _(store, clock):
    from sermon.approves_segment import ApprovesSegment
    from sermon.store import Segment

    segments = sorted(store.lists(Segment), key=lambda item: item.span_start_seconds)
    if len(segments) >= 2:
        ApprovesSegment(store=store, clock=clock)(segments[1])


@given("I am using a desktop browser")
def _():
    return None
