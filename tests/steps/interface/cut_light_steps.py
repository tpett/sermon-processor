"""The cut light, asserted against the rendered page.

The light is live in the browser via requestAnimationFrame, which pytest cannot
drive. What is checkable here is the thing the browser starts from and falls back
to: the server renders the light's boundary, its timecode, the signed offset from
the stored playhead, and which side of that boundary is kept. If the server got
the sides the wrong way round, a punch-out would tell the reviewer the opposite
of the truth, and these steps would catch it.
"""

from pytest_bdd import then

from sermon.shows_recording import formats_precise, formats_signed
from sermon.store import Segment
from steps._markup import reads_field, reads_role


def light_of(preview):
    return reads_role(preview["page"], "cut-light")


def playhead_of(preview):
    """The raw seconds the page rendered, not the formatted clock."""
    marker = reads_role(preview["page"], "playhead-marker")
    return float(marker["seconds"])


@then("a cut light shows the boundary it is tracking and its timecode")
def _(store, segment, preview):
    light = light_of(preview)
    assert light, "no cut light is rendered"
    stored = store.loads(Segment, segment.segment_id)
    assert reads_field(preview["page"], "cut-light-boundary") == "punch-in"
    assert light["boundary"] == "punch-in", light
    assert float(light["at"]) == stored.punch_in_seconds, light
    assert reads_field(preview["page"], "cut-light-at") == formats_precise(
        stored.punch_in_seconds
    )


@then("it reads the playhead's offset from the cut as a signed number")
def _(store, segment, preview):
    stored = store.loads(Segment, segment.segment_id)
    light = light_of(preview)
    playhead = playhead_of(preview)
    shown = reads_field(preview["page"], "cut-light-offset")
    assert shown == formats_signed(playhead - stored.punch_in_seconds), shown
    # The sign is the point of the number: it must carry one unless it is zero.
    assert shown == "0.00 s" or shown[0] in "+−", shown


@then("it says whether the audio now playing would be kept or discarded")
def _(store, segment, preview):
    stored = store.loads(Segment, segment.segment_id)
    light = light_of(preview)
    playhead = playhead_of(preview)
    offset = playhead - stored.punch_in_seconds
    tolerance = float(light["tolerance"])
    if abs(offset) <= tolerance:
        expected_state, expected_side = "at", "on the cut"
    elif offset < 0:
        # Before a punch-in is the part that never reaches the published audio.
        expected_state, expected_side = "before", "discarded"
    else:
        expected_state, expected_side = "after", "kept"
    assert reads_field(preview["page"], "cut-light-state") == expected_state
    assert reads_field(preview["page"], "cut-light-side") == expected_side
    assert light["state"] == expected_state, light


@then("it names which side of this boundary is discarded")
def _(preview):
    light = light_of(preview)
    assert light["discards"] == "before the cut", light
    assert light["keeps"] == "after the cut", light
    assert (
        reads_field(preview["page"], "cut-light-discards")
        == "before the cut is discarded"
    )
    assert reads_field(preview["page"], "cut-light-keeps") == "after the cut is kept"
