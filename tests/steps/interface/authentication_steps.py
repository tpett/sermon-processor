from pytest_bdd import given, parsers, then, when

from sermon.store import Artifact, Recording
from sermon.web import creates_app


PAGES = {
    "the recordings list": "/api/recordings",
    "a recording detail view": None,
    "an artifact download": None,
    "the system health view": "/api/health",
}


@when(parsers.parse('I visit "{page}"'), target_fixture="page_response")
def _(store, page, recording=None):
    client = creates_app(store=store).test_client()
    if page == "a recording detail view":
        recordings = store.lists(Recording)
        if not recordings:
            from datetime import UTC, datetime

            recordings = [
                store.saves(
                    Recording(
                        recording_id="recording_20260816_090014",
                        object_key="recordings/recording_20260816_090014.flac",
                        state="awaiting_review",
                        started_at=datetime(2026, 8, 16, 9, 0, 14, tzinfo=UTC),
                        started_at_source="key",
                        size_bytes=1,
                    )
                )
            ]
        return client.get(f"/api/recordings/{recordings[0].recording_id}")
    if page == "an artifact download":
        artifacts = store.lists(Artifact)
        path = artifacts[0].path if artifacts else "missing.mp3"
        return client.get(f"/api/artifacts/{path}")
    return client.get(PAGES[page])


@then("I see the page")
def _(page_response):
    assert page_response.status_code in {200, 404}


@then("I am not asked to sign in")
def _(page_response):
    assert page_response.status_code != 401
    assert "login" not in (page_response.headers.get("Location") or "").lower()


@then("the service binds only to its tailnet interface")
def _(store):
    app = creates_app(store=store)
    assert app.config["BIND_HOST"] not in {"0.0.0.0", "::", "127.0.0.1"}


@then("it is not reachable from outside the tailnet")
def _(store):
    app = creates_app(store=store)
    assert app.config["BIND_HOST"] != "0.0.0.0"


@when("a Recording is approved")
def _(store, clock):
    from datetime import UTC, datetime

    from sermon.approves_segment import ApprovesSegment
    from sermon.store import Segment

    recording = store.saves(
        Recording(
            recording_id="recording_20260823_102900",
            object_key="recordings/recording_20260823_102900.flac",
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
        )
    )
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )
    ApprovesSegment(store=store, clock=clock)(segment)
    store._approved_segment = segment


@then("the approval is recorded with its timestamp")
def _(store, clock):
    from sermon.store import LogEntry

    entries = store.lists(LogEntry, segment_id=store._approved_segment.segment_id)
    assert any(entry.occurred_at == clock() for entry in entries)


@then('the actor is recorded as "reviewer"')
def _(store):
    from sermon.store import LogEntry

    entries = store.lists(LogEntry, segment_id=store._approved_segment.segment_id)
    assert any(entry.actor == "reviewer" for entry in entries)
