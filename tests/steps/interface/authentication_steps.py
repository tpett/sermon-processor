import dataclasses
import html
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

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
from sermon.cli import manages_users, serves
from sermon.config import Credential
from sermon.sets_password import SetsPassword
from sermon.signs_in_user import SignsInUser
from sermon.store import Artifact, LogEntry, Recording, User
from sermon.store import Credential as StoredCredential
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
PASSWORD = "correct horse battery"
SESSION_COOKIE = "sermon_session"
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
ANOTHER_SITE = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
REDIRECTS = frozenset({301, 302, 303, 307, 308})
START = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
HALVES = {
    "the Access team": ("SERMON_ACCESS_TEAM_DOMAIN", "SERMON_ACCESS_AUD"),
    "the Access application": ("SERMON_ACCESS_AUD", "SERMON_ACCESS_TEAM_DOMAIN"),
}


class SignInRequired:
    def __init__(self, store):
        self.store = store
        self.tailnet_host = TAILNET_HOST
        self.keys = lambda: published_keys(public_jwk())
        self.moment = START
        self.app = None
        self.posted = None
        self.cookie = None
        self.answers = []
        self.first_asked = None

    def now(self):
        return self.moment

    def client(self):
        if self.app is None:
            access = dataclasses.replace(ACCESS, tailnet_host=self.tailnet_host)
            verifies = VerifiesAccessToken(access=access, keys=HoldsAccessKeys(fetches=self.keys))
            self.app = creates_app(
                store=self.store,
                verifies_access=verifies,
                webhook_token=Credential(BEARER),
                clock=self.now,
                secret_key="a-key-only-the-sign-in-scenarios-sign-with",
            )
            self.browser = self.app.test_client()
        return self.browser


PAGES = {
    "the recordings list": "/",
    "a recording detail view": None,
    "an artifact download": None,
    "the system health view": "/api/health",
    "the notifications page": "/notifications",
    "the sign-in page": "/login",
    "the sign-in page's styling": "/static/review.css",
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
@when(parsers.parse('I ask for "{page}" on the tailnet host without signing in'), target_fixture="page_response")
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
@when("I approve a Segment on the tailnet host", target_fixture="page_response")
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


def tailnet(**headers):
    return {"Host": TAILNET_HOST, "Origin": f"http://{TAILNET_HOST}", **headers}


def reads_cookie(response):
    for set_cookie in response.headers.getlist("Set-Cookie"):
        if set_cookie.startswith(f"{SESSION_COOKIE}="):
            return set_cookie
    return None


def remembers_cookie(sign_in, response):
    set_cookie = reads_cookie(response)
    if set_cookie is not None:
        sign_in.cookie = set_cookie.split(";", 1)[0]


def follows_locally(sign_in, response):
    location = response.headers.get("Location", "")
    reached = urlsplit(location)
    if response.status_code not in REDIRECTS or reached.netloc or location.startswith("//"):
        return response
    return sign_in.client().get(location, headers={"Host": TAILNET_HOST, **BROWSER})


SIGN_IN_VARIANT = re.compile(
    r'^(?: asking to be taken to "(?P<destination>[^"]*)"'
    r"| having come through Cloudflare"
    r"| over a secure connection)?$"
)


def signs_in(sign_in, email, password, destination=None, **headers):
    form = {"email": email, "password": password}
    if destination is not None:
        form["next"] = destination
    posted = sign_in.client().post("/login", data=form, headers=tailnet(**headers))
    sign_in.posted = posted
    sign_in.answers.append((posted.status_code, posted.get_data()))
    remembers_cookie(sign_in, posted)
    return posted


@given(
    parsers.re(r'"(?P<email>[^"]*)" has the password "(?P<password>[^"]*)"'),
)
def _(sign_in, email, password):
    SetsPassword(store=sign_in.store, clock=sign_in.now)(email, password)


@given(parsers.parse('"{email}" has only signed in through Cloudflare'))
def _(sign_in, email):
    SignsInUser(store=sign_in.store, clock=sign_in.now)(email)


@given(
    parsers.parse(
        '"{first}" and "{second}" have both been given the password "{password}"'
    )
)
def _(sign_in, first, second, password):
    sets = SetsPassword(store=sign_in.store, clock=sign_in.now)
    sets(first, password)
    sets(second, password)
    sign_in.chosen = password


@given(
    parsers.re(r'I have signed in on the tailnet host as "(?P<email>[^"]*)" with "(?P<password>[^"]*)"')
)
def _(sign_in, email, password):
    posted = signs_in(sign_in, email, password)
    assert posted.status_code == 303, posted.status_code


@when(
    parsers.re(r'I sign in on the tailnet host as "(?P<email>[^"]*)" with "(?P<password>[^"]*)"(?P<how>.*)'),
    target_fixture="page_response",
)
def _(sign_in, email, password, how):
    variant = SIGN_IN_VARIANT.match(how)
    assert variant, f"no such way of signing in: {how!r}"
    headers = {}
    if "Cloudflare" in how:
        headers["Cf-Ray"] = "8a1b2c3d4e5f6a7b-ORD"
    if "secure connection" in how:
        headers["X-Forwarded-Proto"] = "https"
    posted = signs_in(sign_in, email, password, variant.group("destination"), **headers)
    return follows_locally(sign_in, posted)


@when(
    parsers.parse('I ask for "{page}" on the tailnet host in a browser without signing in'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    sign_in.first_asked = page
    return gets(sign_in.client(), store, page, Host=TAILNET_HOST, **BROWSER)


@when(
    parsers.parse('I ask for "{page}" on the tailnet host in a browser'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=TAILNET_HOST, **BROWSER)


@when(
    parsers.parse(
        'I sign in as "{email}" with "{password}" on the sign-in page I was sent to'
    ),
    target_fixture="page_response",
)
def _(sign_in, page_response, email, password):
    sent_to = page_response.headers["Location"]
    page = sign_in.client().get(sent_to, headers={"Host": TAILNET_HOST, **BROWSER}).get_data(as_text=True)
    carried = re.search(r'<input type="hidden" name="next" value="([^"]*)"', page)
    assert carried, "the sign-in page carries nothing about where the person was going"
    posted = signs_in(sign_in, email, password, html.unescape(carried.group(1)))
    return follows_locally(sign_in, posted)


@when("a browser that has not signed in approves a Segment on the tailnet host", target_fixture="page_response")
def _(sign_in, segment):
    return sign_in.client().post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/approve",
        headers={"Host": TAILNET_HOST, **BROWSER},
    )


@when(
    parsers.parse('I skip a Segment on the tailnet host'),
    target_fixture="page_response",
)
def _(sign_in, segment):
    return sign_in.client().post(
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/skip",
        headers={"Host": TAILNET_HOST},
    )


@when("I sign out", target_fixture="page_response")
def _(sign_in):
    return sign_in.client().post("/logout", headers=tailnet())


@when(
    parsers.parse(
        'a page on another site submits "{email}" with "{password}" to the tailnet host\'s sign-in'
    ),
    target_fixture="page_response",
)
def _(sign_in, email, password):
    return sign_in.client().post(
        "/login",
        data={"email": email, "password": password},
        headers={"Host": TAILNET_HOST, **ANOTHER_SITE},
    )


@when("a page on another site asks to sign me out", target_fixture="page_response")
def _(sign_in):
    return sign_in.client().post("/logout", headers={"Host": TAILNET_HOST, **ANOTHER_SITE})


@when(
    parsers.parse('someone gives a wrong password for "{email}" {times:d} times on the tailnet host'),
)
def _(sign_in, email, times):
    for _ in range(times):
        signs_in(sign_in, email, "not the password")


@when(
    parsers.parse("someone tries {times:d} different email addresses from one machine on the tailnet host"),
)
def _(sign_in, times):
    for number in range(times):
        signs_in(sign_in, f"stranger{number}@elsewhere.example", "not the password")


@when(parsers.parse("{minutes:d} minutes pass"))
def _(sign_in, minutes):
    sign_in.moment += timedelta(minutes=minutes)


@when(
    parsers.parse('I ask for "{page}" from outside the tailnet carrying that sign-in'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=PUBLIC_HOST, Cookie=sign_in.cookie)


@when(
    parsers.parse(
        'I present a valid sign-in for "{email}" from outside the tailnet carrying that sign-in'
    ),
    target_fixture="page_response",
)
def _(store, sign_in, email):
    return gets(
        sign_in.client(),
        store,
        "the recordings list",
        Cookie=sign_in.cookie,
        **presents(sign_in, signed(claims(email=email))),
    )


@when(
    parsers.parse(
        'I ask for "{page}" on the tailnet host, carrying that sign-in, having come through Cloudflare, shown by its {mark}'
    ),
    target_fixture="page_response",
)
def _(store, sign_in, page, mark):
    name, value = EDGE_MARKS[mark]
    return gets(
        sign_in.client(),
        store,
        page,
        Host=TAILNET_HOST,
        Cookie=sign_in.cookie,
        **{name: value},
    )


@when(
    parsers.parse('I ask for "{page}" from outside the tailnet claiming a secure connection'),
    target_fixture="page_response",
)
def _(store, sign_in, page):
    return gets(sign_in.client(), store, page, Host=PUBLIC_HOST, **{"X-Forwarded-Proto": "https"})


def owner_runs(data_root, arguments, password):
    said = []
    outcome = manages_users(
        settings={"SERMON_DATA_ROOT": str(data_root)},
        arguments=arguments,
        prints=said.append,
        asks=lambda prompt: password,
    )
    return {"outcome": outcome, "said": "\n".join(said)}


@when(
    parsers.parse('the owner adds "{email}" with the password "{password}"'),
    target_fixture="owner_says",
)
@when(
    parsers.parse('the owner tries to add "{email}" with the password "{password}"'),
    target_fixture="owner_says",
)
def _(tmp_path, sign_in, email, password):
    return owner_runs(tmp_path, ["add", email], password)


@when(
    parsers.parse('the owner gives "{email}" the new password "{password}"'),
    target_fixture="owner_says",
)
def _(tmp_path, sign_in, email, password):
    return owner_runs(tmp_path, ["set-password", email], password)


@then("I am sent to the sign-in page")
def _(page_response):
    assert page_response.status_code in {302, 303}, page_response.status_code
    assert urlsplit(page_response.headers["Location"]).path == "/login"


@then("I am not sent to the sign-in page")
def _(webhook_response):
    assert webhook_response.status_code not in REDIRECTS
    assert "login" not in (webhook_response.headers.get("Location") or "").lower()


@then("the sign-in page is shown")
def _(page_response):
    page = page_response.get_data(as_text=True)
    assert page_response.status_code == 200, page_response.status_code
    assert 'name="email"' in page and 'name="password"' in page
    assert "Location" not in page_response.headers


@then("the sign-in page is shown again")
def _(page_response):
    page = page_response.get_data(as_text=True)
    assert page_response.status_code == 401, page_response.status_code
    assert 'name="email"' in page and 'name="password"' in page
    assert "Location" not in page_response.headers


@then("it says only that the email address or password is not right")
def _(page_response):
    page = page_response.get_data(as_text=True)
    assert "The email address or password is not right" in page
    assert "no such" not in page.lower() and "unknown" not in page.lower()


@then("the two answers are identical")
def _(sign_in):
    (first_status, first_body), (second_status, second_body) = sign_in.answers[-2:]
    assert (first_status, first_body) == (second_status, second_body)


@then("I am told to wait before trying again")
def _(page_response):
    assert page_response.status_code == 429, page_response.status_code
    assert int(page_response.headers["Retry-After"]) > 0
    assert "try again" in page_response.get_data(as_text=True)


@then("I am taken to the recordings list")
def _(sign_in, page_response):
    reached = urlsplit(sign_in.posted.headers.get("Location", ""))
    assert sign_in.posted.status_code == 303, sign_in.posted.status_code
    assert (reached.netloc, reached.path) == ("", "/"), sign_in.posted.headers.get("Location")
    assert page_response.status_code == 200
    assert "<h1>Recordings</h1>" in page_response.get_data(as_text=True)


@then("I am taken to the page I first asked for")
def _(store, sign_in, page_response):
    expected = gets(sign_in.client(), store, sign_in.first_asked, Host=TAILNET_HOST).request.path
    assert urlsplit(sign_in.posted.headers["Location"]).path == expected
    assert page_response.status_code == 200


@then("the submission is refused")
def _(page_response):
    assert page_response.status_code == 403, page_response.status_code


@then("the styling is served")
def _(page_response):
    assert page_response.status_code == 200
    assert page_response.mimetype == "text/css"


@then("there is no such page")
def _(page_response):
    assert page_response.status_code == 404


@then("no approval is recorded")
def _(store, segment):
    assert approvals_of(store, segment) == []


@then(parsers.parse('the skip is recorded against "{actor}"'))
def _(store, segment, actor):
    skipped = [
        entry
        for entry in store.lists(LogEntry, segment_id=segment.segment_id)
        if entry.entered_state == "skipped"
    ]
    assert [entry.actor for entry in skipped] == [actor], skipped


@then("the owner is told the password is too short")
def _(owner_says):
    assert owner_says["outcome"] != 0
    assert "at least 10" in owner_says["said"]


@then("the system holds a different record of each")
def _(store):
    first, second = [one.password_hash for one in store.lists(StoredCredential)]
    assert first != second


@then("neither record contains the password")
def _(store, sign_in):
    assert all(sign_in.chosen not in one.password_hash for one in store.lists(StoredCredential))


def session_cookie(sign_in):
    held = reads_cookie(sign_in.posted)
    assert held is not None, "no sign-in was remembered"
    return [part.strip() for part in held.split(";")]


@then("the browser is told to keep the sign-in for the tailnet host alone")
def _(sign_in):
    attributes = [part.split("=")[0].lower() for part in session_cookie(sign_in)[1:]]
    assert "domain" not in attributes
    assert "path=/" in [part.lower() for part in session_cookie(sign_in)]


@then("the browser is told not to send the sign-in with a request another site causes")
def _(sign_in):
    assert "samesite=lax" in [part.lower() for part in session_cookie(sign_in)]


@then("the browser is told to keep the sign-in from a page's scripts")
def _(sign_in):
    assert "httponly" in [part.lower() for part in session_cookie(sign_in)]


@then("the browser is told to send the sign-in only over a secure connection")
def _(sign_in):
    assert "secure" in [part.lower() for part in session_cookie(sign_in)]


@then("the browser is not told to send the sign-in only over a secure connection")
def _(sign_in):
    assert "secure" not in [part.lower() for part in session_cookie(sign_in)]


@then("no sign-in is remembered")
def _(page_response):
    assert reads_cookie(page_response) is None
    assert not page_response.headers.getlist("Set-Cookie")


@then("the page offers to sign out")
def _(page_response):
    page = page_response.get_data(as_text=True)
    assert re.search(r'<form[^>]*method="post"[^>]*action="/logout"', page), page
    assert 'data-field="sign-out"' in page


@then("the page does not offer to sign out")
def _(page_response):
    page = page_response.get_data(as_text=True)
    assert 'data-field="sign-out"' not in page and "/logout" not in page
