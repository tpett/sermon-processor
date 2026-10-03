from pytest_bdd import given, parsers, then, when

from sermon.store import Artifact, Recording
from sermon.web import creates_app


PAGES = {
    "the recordings list": "/",
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
        return client.get(f"/recordings/{recordings[0].recording_id}")
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


def approvals_of(store, segment):
    from sermon.store import LogEntry

    return [
        entry
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "approved"
    ]


@when("a Recording is approved", target_fixture="detail_page")
def _(store, segment, clock):
    from steps import _web

    assert segment.state == "proposed", segment.state
    return _web.posts(store, _web.segment_action(segment, "approve"), clock=clock)


@then("the approval is recorded with its timestamp")
def _(store, segment, clock):
    approved = approvals_of(store, segment)
    assert [entry.occurred_at for entry in approved] == [clock()], approved


@then('the actor is recorded as "reviewer"')
def _(store, segment):
    approved = approvals_of(store, segment)
    assert [entry.actor for entry in approved] == ["reviewer"], approved
