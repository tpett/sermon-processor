import dataclasses
import re
from datetime import UTC, datetime

import pytest

from signs_access_tokens import (
    ACCESS,
    EMAIL,
    claims,
    public_jwk,
    published_keys,
    signed,
)
from sermon.config import Credential
from sermon.identifies_requester import ACCESS_TOKEN_HEADER
from sermon.store import LogEntry, Notification, Recording, Segment, User, opens_store
from sermon.verifies_access_token import HoldsAccessKeys, VerifiesAccessToken
from sermon.web import creates_app

TAILNET = "sermon-processor.home.tpett.me"
PUBLIC = "sermon.example.org"
BEARER = "the-recorder-bearer-token"
RECORDING_ID = "recording_20260913_090014"
WEBHOOK = {
    "event": "recording.uploaded",
    "bucket": "reformation-recordings",
    "object_key": f"2026/09/13/{RECORDING_ID}.flac",
    "recorded_at": "2026-09-13T09:00:14Z",
    "size_bytes": 1,
}
EDGE = {"Cf-Ray": "8a1b2c3d4e5f6a7b-ORD"}


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def recording(store):
    return store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=f"2026/09/13/{RECORDING_ID}.flac",
            state="awaiting_review",
            started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=11520.0,
        )
    )


@pytest.fixture
def segment(store, recording):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=5320.0,
            span_end_seconds=11520.0,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
            boundary_source="model",
        )
    )


def enforcing(store, tailnet_host=TAILNET, fetches=lambda: published_keys(public_jwk())):
    access = dataclasses.replace(ACCESS, tailnet_host=tailnet_host)
    verifies = VerifiesAccessToken(access=access, keys=HoldsAccessKeys(fetches=fetches))
    return creates_app(store=store, verifies_access=verifies, webhook_token=Credential(BEARER))


def app_for_sign_in(store):
    return enforcing(store)


@pytest.fixture
def app(store):
    return enforcing(store)


@pytest.fixture
def client(app):
    return app.test_client()


def signed_in(token=None, email=EMAIL):
    return {ACCESS_TOKEN_HEADER: token or signed(claims(email=email))}


def on(host, **headers):
    return {"Host": host, **headers}


def every_route(app):
    sampled = {"IntegerConverter": 1, "UnicodeConverter": "x", "PathConverter": "x/y"}
    for rule in app.url_map.iter_rules():
        values = {name: sampled[type(rule._converters[name]).__name__] for name in rule.arguments}
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield method, rule.build(values, append_unknown=False)[1]


def test_the_sampling_covers_every_route_the_app_has(app):
    routes = list(every_route(app))
    assert len(routes) >= 25
    assert ("GET", "/static/x/y") in routes
    assert ("POST", "/api/webhooks/recordings") in routes


def test_every_route_refuses_a_request_with_no_sign_in_on_the_public_host(app, client, recording, segment):
    for method, path in every_route(app):
        refused = client.open(path, method=method, headers=on(PUBLIC))
        assert refused.status_code == 401, (method, path, refused.status_code)


def test_a_path_that_does_not_exist_is_refused_not_revealed_as_missing(client):
    assert client.get("/no/such/page", headers=on(PUBLIC)).status_code == 401


def test_a_refusal_is_plain_and_says_nothing_of_why(client, recording):
    expired = signed(claims(exp=1))
    refused = client.get("/", headers=on(PUBLIC, **signed_in(expired)))
    assert refused.status_code == 401
    assert "Location" not in refused.headers
    assert refused.mimetype == "text/plain"
    body = refused.get_data(as_text=True).lower()
    assert "expired" not in body
    assert RECORDING_ID not in body


def test_a_valid_token_is_served_on_the_public_host(client, recording):
    served = client.get("/", headers=on(PUBLIC, **signed_in()))
    assert served.status_code == 200
    assert RECORDING_ID in served.get_data(as_text=True) or "recording" in served.get_data(as_text=True).lower()


@pytest.mark.parametrize(
    "token",
    [
        signed(claims(aud=["another-app"])),
        signed(claims(iss="https://other.cloudflareaccess.com")),
        signed(claims(exp=1)),
        signed(key="attacker"),
        "not-a-token",
    ],
)
def test_a_token_that_does_not_check_out_is_refused(client, token):
    assert client.get("/", headers=on(PUBLIC, **signed_in(token))).status_code == 401


def test_the_plain_email_header_alone_is_not_a_sign_in(client):
    refused = client.get("/", headers=on(PUBLIC, **{"Cf-Access-Authenticated-User-Email": EMAIL}))
    assert refused.status_code == 401


def test_a_valid_token_is_served_on_every_route_it_may_reach(app, client, recording, segment):
    for method, path in every_route(app):
        if path == "/api/webhooks/recordings":
            continue
        answered = client.open(path, method=method, headers=on(PUBLIC, **signed_in()))
        assert answered.status_code != 401, (method, path)


SIGN_IN_PATHS = {("GET", "/login"), ("POST", "/login")}
SIGN_IN_ASSET = ("GET", "/static/review.css")
BEARER_ONLY = ("POST", "/api/webhooks/recordings")


def refused_for_want_of_a_sign_in(answered):
    return answered.status_code == 401 and answered.get_data(as_text=True) == "sign-in required\n"


def test_every_route_on_the_tailnet_host_needs_a_password_sign_in_but_the_ones_that_cannot(app, client, recording, segment):
    exempt = SIGN_IN_PATHS | {BEARER_ONLY}
    for method, path in every_route(app):
        answered = client.open(path, method=method, headers=on(TAILNET))
        if (method, path) in exempt:
            assert not refused_for_want_of_a_sign_in(answered), (method, path)
        else:
            assert refused_for_want_of_a_sign_in(answered), (method, path, answered.status_code)


def test_only_the_stylesheet_the_sign_in_page_links_is_open_among_the_static_files(client):
    assert client.get("/static/review.css", headers=on(TAILNET)).status_code == 200
    assert refused_for_want_of_a_sign_in(client.get("/static/review.js", headers=on(TAILNET)))


def test_the_tailnet_host_sends_a_browser_to_the_sign_in_page(client, recording):
    sent = client.get("/", headers=on(TAILNET, Accept="text/html"))
    assert sent.status_code == 303 and sent.headers["Location"].startswith("/login")


def test_a_valid_token_alone_does_not_open_the_tailnet_host(client, recording):
    assert client.get("/", headers=on(TAILNET, **signed_in())).status_code == 401


def test_the_webhook_is_not_sent_to_the_sign_in_page_even_for_a_browser(client):
    asked = client.post(
        "/api/webhooks/recordings", json=WEBHOOK, headers=on(TAILNET, Accept="text/html")
    )
    assert asked.status_code == 401 and "Location" not in asked.headers
    assert "bearer" in asked.get_data(as_text=True)


@pytest.mark.parametrize("edge", [{"Cf-Ray": "8a1b-ORD"}, {"Cf-Connecting-Ip": "203.0.113.9"}])
def test_the_tailnet_host_name_through_cloudflare_is_refused_without_a_token(client, edge):
    assert client.get("/", headers=on(TAILNET, **edge)).status_code == 401


def test_the_tailnet_host_name_through_cloudflare_is_served_with_a_token(client, recording):
    assert client.get("/", headers=on(TAILNET, **EDGE, **signed_in())).status_code == 200


def test_with_no_tailnet_host_named_nothing_is_exempt(store):
    client = enforcing(store, tailnet_host=None).test_client()
    assert client.get("/", headers=on(TAILNET)).status_code == 401


def test_enforcement_off_leaves_everything_open(store, recording):
    client = creates_app(store=store).test_client()
    assert client.get("/", headers=on(PUBLIC)).status_code == 200
    assert client.get("/", headers=on(PUBLIC, **{"Cf-Ray": "x"})).status_code == 200


def test_keys_that_cannot_be_fetched_answer_unavailable_not_open(store):
    def unreachable():
        raise ConnectionRefusedError("no route")

    refused = enforcing(store, fetches=unreachable).test_client().get("/", headers=on(PUBLIC, **signed_in()))
    assert refused.status_code == 503


def test_the_webhook_on_the_tailnet_host_answers_to_its_bearer_token_alone(client):
    accepted = client.post(
        "/api/webhooks/recordings", json=WEBHOOK, headers=on(TAILNET, Authorization=f"Bearer {BEARER}")
    )
    assert accepted.status_code in {200, 202}


@pytest.mark.parametrize("presented", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": BEARER}])
def test_the_webhook_on_the_tailnet_host_still_refuses_a_bad_bearer_token(client, presented):
    refused = client.post("/api/webhooks/recordings", json=WEBHOOK, headers=on(TAILNET, **presented))
    assert refused.status_code == 401
    assert "bearer" in refused.get_data(as_text=True)


def test_the_webhook_on_the_public_host_needs_a_sign_in_as_well_as_the_bearer_token(client):
    bearer = {"Authorization": f"Bearer {BEARER}"}
    assert client.post("/api/webhooks/recordings", json=WEBHOOK, headers=on(PUBLIC, **bearer)).status_code == 401
    both = client.post("/api/webhooks/recordings", json=WEBHOOK, headers=on(PUBLIC, **bearer, **signed_in()))
    assert both.status_code in {200, 202}


def test_a_sign_in_does_not_stand_in_for_the_bearer_token(client):
    refused = client.post("/api/webhooks/recordings", json=WEBHOOK, headers=on(PUBLIC, **signed_in()))
    assert refused.status_code == 401
    assert "bearer" in refused.get_data(as_text=True)


def test_with_no_tailnet_host_named_the_webhook_needs_a_sign_in_too(store):
    client = enforcing(store, tailnet_host=None).test_client()
    bearer = {"Authorization": f"Bearer {BEARER}"}
    assert client.post("/api/webhooks/recordings", json=WEBHOOK, headers=on(TAILNET, **bearer)).status_code == 401


def shown_as_signed_in(page):
    found = re.search(r'data-field="signed-in-as"[^>]*>([^<]*)<', page)
    return found.group(1).strip() if found else None


@pytest.mark.parametrize("path", ["/", "/notifications", "/recordings/{recording}"])
def test_the_page_names_who_is_signed_in(client, recording, path):
    page = client.get(path.format(recording=RECORDING_ID), headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert shown_as_signed_in(page) == EMAIL


def test_the_email_shown_is_the_verified_claim_not_a_header_a_client_added(client):
    forged = {"Cf-Access-Authenticated-User-Email": "intruder@example.org"}
    page = client.get("/", headers=on(PUBLIC, **signed_in(), **forged)).get_data(as_text=True)
    assert shown_as_signed_in(page) == EMAIL
    assert "intruder" not in page


def test_a_hostile_email_is_escaped_in_the_header(client):
    page = client.get("/", headers=on(PUBLIC, **signed_in(email="<script>x@e.org"))).get_data(as_text=True)
    assert "<script>x" not in page


@pytest.mark.parametrize("host", [TAILNET, PUBLIC])
def test_nobody_is_named_with_enforcement_off(store, recording, host):
    page = creates_app(store=store).test_client().get("/", headers=on(host)).get_data(as_text=True)
    assert shown_as_signed_in(page) is None


def test_enforcement_off_offers_no_sign_out_and_no_sign_in_page(store, recording):
    client = creates_app(store=store).test_client()
    assert "/logout" not in client.get("/", headers=on(TAILNET)).get_data(as_text=True)
    assert client.get("/login", headers=on(TAILNET)).status_code == 404
    assert client.post("/logout", headers=on(TAILNET)).status_code == 404


def test_a_user_is_created_once_however_often_they_sign_in(client, store, recording):
    for _ in range(3):
        client.get("/", headers=on(PUBLIC, **signed_in()))
    assert [user.email for user in store.lists(User)] == [EMAIL]


def test_a_token_that_is_refused_creates_no_user(client, store):
    client.get("/", headers=on(PUBLIC, **signed_in(signed(claims(aud=["other"])))))
    client.get("/", headers=on(PUBLIC, **{"Cf-Access-Authenticated-User-Email": EMAIL}))
    assert store.lists(User) == []


def test_a_tailnet_request_with_no_sign_in_creates_no_user(client, store, recording):
    client.get("/", headers=on(TAILNET))
    assert store.lists(User) == []


def actors(store):
    return {entry.actor for entry in store.lists(LogEntry) if entry.actor is not None}


def test_an_approval_by_a_signed_in_person_is_recorded_against_their_email(client, store, segment):
    client.post(
        f"/recordings/{RECORDING_ID}/segments/{segment.segment_id}/approve",
        data={"intent": "archive"},
        headers=on(PUBLIC, **signed_in()),
    )
    approval = [entry for entry in store.lists(LogEntry) if entry.entered_state == "approved"]
    assert [entry.actor for entry in approval] == [EMAIL]


def test_the_api_approval_is_recorded_against_their_email_too(client, store, segment):
    store.saves(dataclasses.replace(segment, intent="archive"))
    client.post(f"/api/segments/{segment.segment_id}/approve", headers=on(PUBLIC, **signed_in()))
    assert actors(store) == {EMAIL}


def test_an_approval_from_the_tailnet_with_no_sign_in_is_refused_and_recorded_against_nobody(client, store, segment):
    store.saves(dataclasses.replace(segment, intent="archive"))
    refused = client.post(f"/api/segments/{segment.segment_id}/approve", headers=on(TAILNET))
    assert refused.status_code == 401
    assert actors(store) == set()


def test_an_approval_from_the_tailnet_after_a_password_sign_in_is_recorded_against_their_email(store, segment):
    from sermon.sets_password import SetsPassword

    SetsPassword(store=store)(EMAIL, "correct horse battery")
    store.saves(dataclasses.replace(segment, intent="archive"))
    client = app_for_sign_in(store).test_client()
    client.post("/login", data={"email": EMAIL, "password": "correct horse battery"}, headers=on(TAILNET))
    client.post(f"/api/segments/{segment.segment_id}/approve", headers=on(TAILNET))
    assert actors(store) == {EMAIL}


def test_two_people_are_each_recorded_against_their_own_email(client, store, segment, recording):
    client.post(
        f"/recordings/{RECORDING_ID}/actions/retitle", data={"title": "One"}, headers=on(PUBLIC, **signed_in())
    )
    client.post(
        f"/recordings/{RECORDING_ID}/actions/retitle",
        data={"title": "Two"},
        headers=on(PUBLIC, **signed_in(email="elder@reformation.example")),
    )
    assert actors(store) == {EMAIL, "elder@reformation.example"}


def test_every_human_action_a_signed_in_person_takes_is_recorded_against_them(client, store, recording, segment):
    headers = on(PUBLIC, **signed_in())
    base = f"/recordings/{RECORDING_ID}"
    chosen = f"{base}/segments/{segment.segment_id}"
    client.post(f"{base}/actions/retitle", data={"title": "A title"}, headers=headers)
    client.post(f"{chosen}/classify", data={"classification": "lesson"}, headers=headers)
    client.post(f"{chosen}/boundaries/punch-in", data={"do": "nudge", "amount": "1s", "direction": "later"}, headers=headers)
    client.post(f"{chosen}/boundaries/punch-in", data={"do": "revert"}, headers=headers)
    client.post(f"{base}/actions/re-run-analysis", headers=headers)
    client.post(f"{base}/actions/discard", data={"confirm": "yes"}, headers=headers)
    client.post(f"{base}/actions/restore", headers=headers)
    assert store.lists(LogEntry), "nothing was recorded"
    assert actors(store) == {EMAIL}


def test_seeing_the_notifications_is_recorded_against_who_saw_them(client, store, recording):
    store.saves(
        Notification(
            recording_id=RECORDING_ID,
            kind="segment_proposed",
            recipient="reviewer",
            summary="A sermon was proposed",
            created_at=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
            state="delivered",
        )
    )
    client.get("/notifications", headers=on(PUBLIC, **signed_in()))
    assert actors(store) == {EMAIL}
