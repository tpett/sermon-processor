from pytest_bdd import given, parsers, then, when

from sermon.extends_segment_span import ReadsTimecode
from sermon.places_punch_in import PlacesPunchIn
from sermon.store import Segment

READS = ReadsTimecode()


def seconds_from_amount(amount):
    number, unit = amount.split()
    value = float(number)
    if unit == "ms":
        return value / 1000
    return value


@when(parsers.parse('I nudge the punch-in earlier by "{amount}"'), target_fixture="segment")
def _(store, segment, amount):
    return PlacesPunchIn(store=store)(
        segment, punch_in_seconds=segment.punch_in_seconds - seconds_from_amount(amount)
    )


@when(parsers.parse('I nudge the punch-in later by "{amount}"'), target_fixture="segment")
def _(store, segment, amount):
    return PlacesPunchIn(store=store)(
        segment, punch_in_seconds=segment.punch_in_seconds + seconds_from_amount(amount)
    )


@when(parsers.parse('I adjust the punch-in to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=READS(timecode))


@given(parsers.parse('I have adjusted the punch-in to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    return PlacesPunchIn(store=store)(segment, punch_in_seconds=READS(timecode))


@when(parsers.parse('I set the punch-out to "{timecode}"'), target_fixture="segment")
def _(store, segment, timecode):
    from dataclasses import replace

    return store.saves(replace(segment, punch_out_seconds=READS(timecode)))


@then(parsers.parse('the punch-in is "{timecode}"'))
def _(store, segment, timecode):
    assert store.loads(Segment, segment.segment_id).punch_in_seconds == READS(timecode)


@then(parsers.parse('the punch-in becomes "{timecode}"'))
def _(store, segment, timecode):
    assert abs(store.loads(Segment, segment.segment_id).punch_in_seconds - READS(timecode)) < 0.001
