import time

from pytest_bdd import given, then, when

from sermon.pipeline import preview as rendition
from sermon.shows_recording import PREVIEW_LEAD_SECONDS
from sermon.store import Artifact, Recording
from sermon.web import creates_app
from steps._markup import reads_field, reads_role, reads_rows

STARTS_WITHIN_SECONDS = 2.0


def renders(store, query=""):
    recording_id = store.lists(Recording)[0].recording_id
    response = creates_app(store=store).test_client().get(f"/recordings/{recording_id}{query}")
    return response.get_data(as_text=True)


def reads_window(page, role):
    control = reads_role(page, role)
    return {
        "kind": control["kind"],
        "start": float(control["start"]),
        "end": float(control["end"]),
        "at": float(control["at"]),
    }


@when("I choose to preview the punch-in", target_fixture="preview")
def _(store, segment):
    page = renders(store, f"?segment={segment.segment_id}")
    return {**reads_window(page, "preview-punch-in"), "page": page}


@when("I choose to preview the cut", target_fixture="preview")
def _(store, segment):
    page = renders(store, f"?segment={segment.segment_id}")
    control = reads_role(page, "preview-cut")
    return {
        "kind": control["kind"],
        "start": float(control["in-start"]),
        "end": float(control["in-end"]),
        "out": (float(control["out-start"]), float(control["out-end"])),
        "page": page,
    }


@then("only the region being played is fetched")
def _(store):
    recording = store.lists(Recording)[0]
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0]
    first, last = rendition.byte_range(600.0, PREVIEW_LEAD_SECONDS * 2, artifact.size_bytes)
    ranged = creates_app(store=store).test_client().get(
        f"/api/artifacts/{artifact.path}", headers={"Range": f"bytes={first}-{last}"}
    )
    assert ranged.status_code == 206
    assert ranged.headers["Content-Range"] == f"bytes {first}-{last}/{artifact.size_bytes}"
    assert len(ranged.data) == last - first + 1


@then("playback begins within 2 seconds of pressing play")
def _(store):
    recording = store.lists(Recording)[0]
    artifact = store.lists(Artifact, recording_id=recording.recording_id, kind="preview")[0]
    first, last = rendition.byte_range(0.0, PREVIEW_LEAD_SECONDS * 2, artifact.size_bytes)
    began = time.monotonic()
    ranged = creates_app(store=store).test_client().get(
        f"/api/artifacts/{artifact.path}", headers={"Range": f"bytes={first}-{last}"}
    )
    assert ranged.status_code == 206
    assert time.monotonic() - began < STARTS_WITHIN_SECONDS


@given("the seekable preview has not been rendered")
def _(store):
    for recording in store.lists(Recording):
        for artifact in store.lists(Artifact, recording_id=recording.recording_id, kind="preview"):
            resolved = store.resolves(artifact)
            if resolved is not None:
                resolved.unlink(missing_ok=True)
            store.forgets(artifact)


@when("I try to audition the punch-in", target_fixture="detail_page")
def _(store, segment):
    return renders(store, f"?segment={segment.segment_id}")


@then("I am told the preview is not ready rather than left with a dead control")
def _(detail_page):
    told = reads_field(detail_page, "preview-state")
    assert told and "has not been rendered" in told
    assert 'data-role="preview-punch-in"' not in detail_page
    assert 'data-role="preview-audio"' not in detail_page


@then("the waveform and the transcript remain usable")
def _(detail_page):
    assert 'id="overview"' in detail_page
    assert reads_rows(detail_page, "utterance") or reads_field(detail_page, "transcript-state")


@then("the boundaries can still be adjusted and approved")
def _(detail_page):
    assert reads_field(detail_page, "punch-in")
    assert reads_field(detail_page, "punch-out")
    assert [row for row in reads_rows(detail_page, "segment") if row["state"] == "proposed"]


@then("previewing the punch-in and previewing the punch-out are the most prominent actions")
def _(store, segment):
    page = renders(store, f"?segment={segment.segment_id}")
    positions = [page.find(f'data-role="preview-{which}"') for which in ("punch-in", "punch-out")]
    assert min(positions) > 0
    assert max(positions) < page.find('data-row="action"')
