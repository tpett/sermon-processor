import dataclasses
from datetime import UTC, datetime

from pytest_bdd import given, parsers, then, when

from signs_access_tokens import (
    ACCESS,
    EMAIL,
    claims,
    public_jwk,
    published_keys,
    signed,
    unsigned,
)
from sermon.cli import serves
from sermon.config import Credential
from sermon.store import Artifact, LogEntry, Recording, User
from sermon.verifies_access_token import HoldsAccessKeys, VerifiesAccessToken
from sermon.web import creates_app

TAILNET_HOST = "sermon-processor.home.tpett.me"
PUBLIC_HOST = "sermon.example.org"
BEARER = "the-token-only-the-sign-in-scenarios-issue"
WEBHOOK = {
    "event": "recording.uploaded",
    "bucket": "reformation-recordings",
    "object_key": "2026/09/13/recording_20260913_090014.flac",
    "recorded_at": "2026-09-13T09:00:14Z",
    "size_bytes": 1,
}
EDGE_MARKS = {
    "request identifier": ("Cf-Ray", "8a1b2c3d4e5f6a7b-ORD"),
    "record of the sender's address": ("Cf-Connecting-Ip", "203.0.113.9"),
}
UNCHECKABLE_SIGN_INS = {
    "issued for another application": lambda: signed(claims(aud=["another-application"])),
    "issued by another team": lambda: signed(claims(iss="https://other.cloudflareaccess.com")),
    "that has expired": lambda: signed(claims(exp=1)),
    "signed by someone who is not Access": lambda: signed(key="attacker"),
    "that is not signed at all": unsigned,
}
HALVES = {
    "the Access team": ("SERMON_ACCESS_TEAM_DOMAIN", "SERMON_ACCESS_AUD"),
    "the Access application": ("SERMON_ACCESS_AUD", "SERMON_ACCESS_TEAM_DOMAIN"),
}


class SignInRequired:
    def __init__(self, store):
        self.store = store
        self.tailnet_host = TAILNET_HOST
        self.keys = lambda: published_keys(public_jwk())

    def client(self):
        access = dataclasses.replace(ACCESS, tailnet_host=self.tailnet_host)
        verifies = VerifiesAccessToken(access=access, keys=HoldsAccessKeys(fetches=self.keys))
        app = creates_app(store=self.store, verifies_access=verifies, webhook_token=Credential(BEARER))
        return app.test_client()


PAGES = {
    "the recordings list": "/",
    "a recording detail view": None,
    "an artifact download": None,
    "the system health view": "/api/health",
    "the notifications page": "/notifications",
}


def gets(client, store, page, **headers):
    if page == "a recording detail view":
        recordings = store.lists(Recording)
        if not recordings:
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
        return client.get(f"/recordings/{recordings[0].recording_id}", headers=headers)
    if page == "an artifact download":
        artifacts = store.lists(Artifact)
        path = artifacts[0].path if artifacts else "missing.mp3"
        return client.get(f"/api/artifacts/{path}", headers=headers)
    return client.get(PAGES[page], headers=headers)


@when(parsers.parse('I visit "{page}"'), target_fixture="page_response")
def _(store, page):
    return gets(creates_app(store=store).test_client(), store, page)


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


@given("sign-in is required", target_fixture="sign_in")
def _(store, recording):
    return SignInRequired(store)


@given("Access's signing keys cannot be fetched")
def _(sign_in):
    def unreachable():
        raise ConnectionRefusedError("no route to Access")

    sign_in.keys = unreachable


@given("no tailnet host is named")
def _(sign_in):
    sign_in.tailnet_host = None


def presents(sign_in, token):
    return {"Host": PUBLIC_HOST, "Cf-Access-Jwt-Assertion": token}


@when(
    parsers.parse('I ask for "{page}" from outside the tailnet without signing in'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=PUBLIC_HOST)


@when(
    parsers.parse("I present a sign-in {kind} from outside the tailnet"),
    target_fixture="page_response",
)
def _(store, sign_in, kind):
    return gets(sign_in.client(), store, "the recordings list", **presents(sign_in, UNCHECKABLE_SIGN_INS[kind]()))


@when(
    parsers.parse('I present a valid sign-in for "{email}" from outside the tailnet'),
    target_fixture="page_response",
)
def _(store, sign_in, email):
    token = signed(claims(email=email))
    return gets(sign_in.client(), store, "the recordings list", **presents(sign_in, token))


@when(
    parsers.parse('I ask for "{page}" from outside the tailnet claiming to be "{email}"'),
    target_fixture="page_response",
)
def _(store, sign_in, page, email):
    return gets(
        sign_in.client(),
        store,
        page,
        Host=PUBLIC_HOST,
        **{"Cf-Access-Authenticated-User-Email": email},
    )


@when(parsers.parse('I ask for "{page}" on the tailnet host'), target_fixture="page_response")
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=TAILNET_HOST)


@when(
    parsers.parse(
        'I ask for "{page}" on the tailnet host having come through Cloudflare, shown by its {mark}'
    ),
    target_fixture="page_response",
)
def _(store, sign_in, page, mark):
    name, value = EDGE_MARKS[mark]
    return gets(sign_in.client(), store, page, Host=TAILNET_HOST, **{name: value})


@when(
    parsers.parse('I ask for "{page}" on the host the tailnet host would have been'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=TAILNET_HOST)


def sends_webhook(sign_in, **headers):
    return sign_in.client().post("/api/webhooks/recordings", json=WEBHOOK, headers=headers)


@when("the Recorder sends a webhook on the tailnet host with its bearer token", target_fixture="webhook_response")
def _(sign_in):
    return sends_webhook(sign_in, Host=TAILNET_HOST, Authorization=f"Bearer {BEARER}")


@when("the Recorder sends a webhook on the tailnet host without its bearer token", target_fixture="webhook_response")
def _(sign_in):
    return sends_webhook(sign_in, Host=TAILNET_HOST)


@when(
    "the Recorder sends a webhook from outside the tailnet with its bearer token and no sign-in",
    target_fixture="page_response",
)
def _(sign_in):
    return sends_webhook(sign_in, Host=PUBLIC_HOST, Authorization=f"Bearer {BEARER}")


@when(
    parsers.parse("the service is started naming only {half} of its sign-in check"),
    target_fixture="start",
)
def _(tmp_path, half):
    named, missing = HALVES[half]
    ran = []
    lines = []
    outcome = serves(
        settings={
            "SERMON_DATA_ROOT": str(tmp_path / "data"),
            "SERMON_OBJECT_STORE_ENDPOINT": "https://s3.home.tpett.me",
            "SERMON_OBJECT_STORE_BUCKET": "reformation-recordings",
            "SERMON_OBJECT_STORE_ACCESS_KEY_ID": "GK7d41f0b3c2a94e6581d7b2ff",
            "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": "b892c0665f0a4d1e9c3aa71e5f4d8c02b6e97a35",
            "SERMON_MODEL_ENDPOINT": "http://mac-m1:11434",
            named: "reformation.cloudflareaccess.com" if "TEAM" in named else ACCESS.audience,
        },
        lists_objects=lambda: [],
        runs=lambda app, host, port: ran.append(app),
        prints=lines.append,
    )
    return {"outcome": outcome, "ran": ran, "said": "\n".join(lines), "missing": missing}


@when(
    parsers.parse('"{email}" visits on three separate occasions'),
    target_fixture="page_response",
)
def _(store, sign_in, email):
    client = sign_in.client()
    for _ in range(3):
        response = gets(client, store, "the recordings list", **presents(sign_in, signed(claims(email=email))))
    return response


@when(
    parsers.parse('"{email}" approves a Segment from outside the tailnet'),
    target_fixture="page_response",
)
def _(sign_in, segment, email):
    return sign_in.client().post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/approve",
        headers=presents(sign_in, signed(claims(email=email))),
    )


@when("someone approves a Segment on the tailnet host", target_fixture="page_response")
def _(sign_in, segment):
    return sign_in.client().post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/approve",
        headers={"Host": TAILNET_HOST},
    )


@then("I am refused")
def _(page_response):
    assert page_response.status_code == 401, page_response.status_code


@then("nothing of the page is shown")
def _(page_response, recording):
    body = page_response.get_data(as_text=True)
    assert recording.recording_id not in body
    assert "<h1" not in body


@then("I am told sign-in cannot be checked right now")
def _(page_response):
    assert page_response.status_code == 503
    assert "cannot be checked" in page_response.get_data(as_text=True)


@then("the recordings list is served")
def _(page_response):
    assert page_response.status_code == 200
    assert "<h1>Recordings</h1>" in page_response.get_data(as_text=True)


@then("nobody is named as signed in")
def _(page_response):
    assert 'data-field="signed-in-as"' not in page_response.get_data(as_text=True)


@then(parsers.parse('the page names "{email}" as signed in'))
def _(page_response, email):
    page = page_response.get_data(as_text=True)
    assert f'data-field="signed-in-as">{email}<' in page


@then("the webhook is accepted")
def _(webhook_response):
    assert webhook_response.status_code in {200, 202}, webhook_response.status_code


@then("the webhook is refused as unauthenticated")
def _(webhook_response):
    assert webhook_response.status_code == 401
    assert "bearer" in webhook_response.get_data(as_text=True)


@then("it refuses to start")
def _(start):
    assert start["outcome"] == 1
    assert start["ran"] == []


@then("it says what is missing")
def _(start):
    assert start["missing"] in start["said"]


@then("the system knows one person with that address")
def _(store):
    assert [user.email for user in store.lists(User)] == [EMAIL]


@then("the system knows no one")
def _(store):
    assert store.lists(User) == []


@then(parsers.parse('the approval is recorded against "{actor}"'))
def _(store, segment, actor):
    assert [entry.actor for entry in approvals_of(store, segment)] == [actor]
