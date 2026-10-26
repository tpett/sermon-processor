import dataclasses
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from signs_access_tokens import ACCESS, EMAIL, public_jwk, published_keys
from sermon.config import Credential
from sermon.sets_password import SetsPassword
from sermon.store import Credential as StoredCredential
from sermon.store import User, opens_store
from sermon.verifies_access_token import HoldsAccessKeys, VerifiesAccessToken
from sermon.web import creates_app
from sermon.web.signs_in_by_password import reads_safe_destination

TAILNET = "sermon-processor.home.tpett.me"
PUBLIC = "sermon.example.org"
PASSWORD = "correct horse battery"
SECRET = "a-test-secret-that-is-long-enough-to-sign-with"
BROWSER = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    SetsPassword(store=opened, clock=lambda: FIRST)(EMAIL, PASSWORD)
    yield opened
    opened.close()


def app_for(store, secret=SECRET):
    access = dataclasses.replace(ACCESS, tailnet_host=TAILNET)
    verifies = VerifiesAccessToken(
        access=access, keys=HoldsAccessKeys(fetches=lambda: published_keys(public_jwk()))
    )
    app = creates_app(
        store=store,
        verifies_access=verifies,
        webhook_token=Credential("the-bearer"),
        secret_key=secret,
    )
    app.config["PREFERRED_URL_SCHEME"] = "https"
    return app


@pytest.fixture
def client(store):
    return app_for(store).test_client()


def signs_in(client, email=EMAIL, password=PASSWORD, **headers):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        headers={"Host": TAILNET, **headers},
    )


def cookie_of(response):
    return next(
        value for value in response.headers.getlist("Set-Cookie") if value.startswith("sermon_session=")
    )


@pytest.mark.parametrize(
    "asked, kept",
    [
        ("/", "/"),
        ("/recordings/recording_20260913_090014", "/recordings/recording_20260913_090014"),
        ("/?q=hebrews&page=2", "/?q=hebrews&page=2"),
        ("https://evil.example/", "/"),
        ("//evil.example/", "/"),
        ("/\\evil.example", "/"),
        ("\\\\evil.example", "/"),
        ("/%5Cevil.example", "/%5Cevil.example"),
        ("javascript:alert(1)", "/"),
        ("evil.example", "/"),
        ("", "/"),
        (None, "/"),
        ("/login", "/"),
        ("/login?next=/", "/"),
        ("/ok\r\nSet-Cookie: x=1", "/"),
        ("/" + "a" * 3000, "/"),
    ],
)
def test_only_a_page_of_this_service_is_a_destination(asked, kept):
    assert reads_safe_destination(asked) == kept


def test_a_sign_in_form_from_this_site_is_accepted(client):
    answered = signs_in(client, Origin=f"https://{TAILNET}")
    assert answered.status_code == 303


def test_a_sign_in_form_from_a_non_browser_with_no_origin_is_accepted(client):
    assert signs_in(client).status_code == 303


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": f"https://{TAILNET}.evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": f"https://{TAILNET}", "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_a_sign_in_form_from_anywhere_else_is_refused_before_the_password_is_looked_at(client, headers, store):
    answered = signs_in(client, **headers)
    assert answered.status_code == 403
    assert not answered.headers.getlist("Set-Cookie")


@pytest.mark.parametrize("fetch_site", ["same-origin", "none"])
def test_a_browser_saying_the_form_is_its_own_is_believed(client, fetch_site):
    assert signs_in(client, **{"Sec-Fetch-Site": fetch_site}).status_code == 303


def test_the_session_cookie_is_host_only_http_only_lax_and_for_the_whole_site(client):
    parts = [part.strip().lower() for part in cookie_of(signs_in(client)).split(";")]
    assert "httponly" in parts and "samesite=lax" in parts and "path=/" in parts
    assert not any(part.startswith("domain") for part in parts)
    assert not any(part.startswith("samesite=none") for part in parts)
    assert any(part.startswith("max-age=") or part.startswith("expires=") for part in parts)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Forwarded-Proto": "https"},
        {"X-Forwarded-Proto": "http"},
        {"X-Forwarded-Proto": "http, https"},
    ],
)
def test_the_cookie_is_secure_whatever_the_request_or_the_proxy_says_about_its_scheme(client, headers):
    parts = [part.strip().lower() for part in cookie_of(signs_in(client, **headers)).split(";")]
    assert "secure" in parts


def test_the_cookie_is_secure_over_https_too(client):
    answered = client.post(
        "/login", data={"email": EMAIL, "password": PASSWORD}, base_url=f"https://{TAILNET}"
    )
    assert "secure" in [part.strip().lower() for part in cookie_of(answered).split(";")]


def test_the_cookie_that_ends_a_sign_in_is_secure_too(client):
    signs_in(client)
    cleared = cookie_of(client.post("/logout", headers={"Host": TAILNET}))
    assert "secure" in [part.strip().lower() for part in cleared.split(";")]


def test_a_cookie_made_with_another_key_is_not_a_sign_in(store):
    other = app_for(store, secret="a-different-secret-that-is-also-long-enough").test_client()
    signs_in(other)
    forged = other.get_cookie("sermon_session", domain=TAILNET)
    assert forged is not None
    kept = app_for(store).test_client()
    kept.set_cookie("sermon_session", forged.value, domain=TAILNET)
    answered = kept.get("/", headers={"Host": TAILNET, **BROWSER})
    assert answered.status_code == 303 and urlsplit(answered.headers["Location"]).path == "/login"


def test_a_restart_with_the_same_secret_keeps_people_signed_in(store):
    first = app_for(store).test_client()
    signs_in(first)
    cookie = first.get_cookie("sermon_session", domain=TAILNET)
    second = app_for(store).test_client()
    second.set_cookie("sermon_session", cookie.value, domain=TAILNET)
    answered = second.get("/", headers={"Host": TAILNET})
    assert answered.status_code == 200


def test_the_signed_in_person_is_named_and_a_user(client, store):
    signs_in(client)
    page = client.get("/", headers={"Host": TAILNET}).get_data(as_text=True)
    assert f'data-field="signed-in-as">{EMAIL}<' in page
    assert [user.email for user in store.lists(User)] == [EMAIL]


def test_the_sign_in_page_does_not_loop_for_someone_not_signed_in(client):
    answered = client.get("/login", headers={"Host": TAILNET, **BROWSER})
    assert answered.status_code == 200 and "Location" not in answered.headers


def test_the_sign_in_page_carries_where_the_person_was_going(client):
    answered = client.get("/login?next=/recordings/x%3Fplayhead%3D3", headers={"Host": TAILNET})
    assert 'name="next" value="/recordings/x?playhead=3"' in answered.get_data(as_text=True)


def test_the_sign_in_page_will_not_carry_another_site_as_where_to_go(client):
    answered = client.get("/login?next=https://evil.example/", headers={"Host": TAILNET})
    assert "evil.example" not in answered.get_data(as_text=True)


def test_a_failed_sign_in_shows_the_page_again_with_where_the_person_was_going(client):
    answered = client.post(
        "/login",
        data={"email": EMAIL, "password": "wrong", "next": "/notifications"},
        headers={"Host": TAILNET},
    )
    assert answered.status_code == 401
    assert 'name="next" value="/notifications"' in answered.get_data(as_text=True)
    assert not answered.headers.getlist("Set-Cookie")


def test_someone_already_signed_in_who_asks_for_the_sign_in_page_is_taken_on(client):
    signs_in(client)
    answered = client.get("/login?next=/notifications", headers={"Host": TAILNET})
    assert answered.status_code == 303 and answered.headers["Location"] == "/notifications"


def test_a_browser_is_sent_back_to_the_page_with_its_query(client):
    answered = client.get("/?q=hebrews&page=2", headers={"Host": TAILNET, **BROWSER})
    assert answered.status_code == 303
    reached = urlsplit(answered.headers["Location"])
    assert reached.path == "/login" and parse_qs(reached.query) == {"next": ["/?q=hebrews&page=2"]}
    assert answered.get_data() == b""


def test_a_head_request_from_a_browser_is_sent_to_the_sign_in_page_too(client):
    assert client.head("/", headers={"Host": TAILNET, **BROWSER}).status_code == 303


def test_a_json_client_asking_for_the_api_is_refused_even_if_it_also_accepts_html(client):
    answered = client.get("/api/health", headers={"Host": TAILNET, **BROWSER})
    assert answered.status_code == 401 and "Location" not in answered.headers


def test_a_client_that_accepts_anything_is_refused_rather_than_redirected(client):
    answered = client.get("/", headers={"Host": TAILNET, "Accept": "*/*"})
    assert answered.status_code == 401


def test_the_throttle_counts_the_address_the_proxy_saw(client, store):
    for number in range(20):
        client.post(
            "/login",
            data={"email": f"stranger{number}@elsewhere.example", "password": "no"},
            headers={"Host": TAILNET, "X-Forwarded-For": "100.64.0.50"},
        )
    other = client.post(
        "/login",
        data={"email": EMAIL, "password": PASSWORD},
        headers={"Host": TAILNET, "X-Forwarded-For": "100.64.0.51"},
    )
    held = client.post(
        "/login",
        data={"email": EMAIL, "password": PASSWORD},
        headers={"Host": TAILNET, "X-Forwarded-For": "100.64.0.50"},
    )
    assert other.status_code == 303 and held.status_code == 429


def test_the_throttle_trusts_only_the_last_forwarded_address_so_a_made_up_one_does_not_help(client):
    for number in range(20):
        client.post(
            "/login",
            data={"email": f"stranger{number}@elsewhere.example", "password": "no"},
            headers={"Host": TAILNET, "X-Forwarded-For": f"203.0.113.{number}, 100.64.0.50"},
        )
    held = client.post(
        "/login",
        data={"email": EMAIL, "password": PASSWORD},
        headers={"Host": TAILNET, "X-Forwarded-For": "198.51.100.1, 100.64.0.50"},
    )
    assert held.status_code == 429


def test_signing_out_clears_the_cookie(client):
    signs_in(client)
    answered = client.post("/logout", headers={"Host": TAILNET})
    assert answered.status_code == 303 and answered.headers["Location"] == "/login"
    assert "sermon_session=;" in cookie_of(answered)


def test_there_is_no_sign_out_on_the_cloudflare_path(store):
    from signs_access_tokens import signed

    client = app_for(store).test_client()
    answered = client.post("/logout", headers={"Host": PUBLIC, "Cf-Access-Jwt-Assertion": signed()})
    assert answered.status_code == 404


def test_the_sign_in_page_is_refused_with_the_access_token_missing_on_the_public_host(client):
    assert client.get("/login", headers={"Host": PUBLIC}).status_code == 401
    assert client.post("/login", data={"email": EMAIL, "password": PASSWORD}, headers={"Host": PUBLIC}).status_code == 401


@pytest.mark.parametrize("path", ["/static/review.js", "/static/playback.js", "/static/nonexistent.css"])
def test_only_the_styling_the_sign_in_page_loads_is_served_without_signing_in(client, path):
    assert client.get(path, headers={"Host": TAILNET}).status_code == 401


def test_the_styling_the_sign_in_page_loads_is_served_without_signing_in(client):
    assert client.get("/static/review.css", headers={"Host": TAILNET}).status_code == 200


def test_the_styling_is_not_served_from_outside_the_tailnet_without_a_token(client):
    assert client.get("/static/review.css", headers={"Host": PUBLIC}).status_code == 401


def test_the_sign_in_page_links_only_the_styling_it_is_allowed_to_serve(client):
    page = client.get("/login", headers={"Host": TAILNET}).get_data(as_text=True)
    assert "/static/review.css" in page and ".js" not in page


def test_a_session_for_a_person_whose_credential_is_gone_is_not_a_sign_in(client, store):
    signs_in(client)
    store.forgets(store.loads(StoredCredential, EMAIL))
    assert client.get("/", headers={"Host": TAILNET}).status_code == 401

