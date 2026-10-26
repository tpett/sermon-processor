import dataclasses

import pytest

from signs_access_tokens import ACCESS, EMAIL, claims, public_jwk, published_keys, signed
from sermon.identifies_requester import (
    ACCESS_TOKEN_HEADER,
    EDGE_HEADERS,
    IdentifiesRequester,
    LoginRequired,
    Requester,
)
from sermon.verifies_access_token import AccessKeysUnavailable, AccessRefused, HoldsAccessKeys, VerifiesAccessToken

TAILNET = "sermon-processor.home.tpett.me"
PUBLIC = "sermon.example.org"


def verifier(access=ACCESS, fetches=lambda: published_keys(public_jwk())):
    return VerifiesAccessToken(access=access, keys=HoldsAccessKeys(fetches=fetches))


def identifies(tailnet_host=TAILNET):
    return IdentifiesRequester(verifies=verifier(dataclasses.replace(ACCESS, tailnet_host=tailnet_host)))


def test_with_enforcement_off_everyone_is_unidentified_and_welcome():
    assert IdentifiesRequester(verifies=None)(PUBLIC, {}, login=never_asked) == Requester(email=None)


def test_a_valid_token_names_who_is_signed_in():
    assert identifies()(PUBLIC, {ACCESS_TOKEN_HEADER: signed()}) == Requester(email=EMAIL)


def test_a_request_without_a_token_is_refused_on_the_public_host():
    with pytest.raises(AccessRefused):
        identifies()(PUBLIC, {})


def test_an_invalid_token_is_refused_on_the_public_host():
    with pytest.raises(AccessRefused):
        identifies()(PUBLIC, {ACCESS_TOKEN_HEADER: signed(claims(aud=["other"]))})


def test_the_plain_email_header_is_not_a_sign_in():
    with pytest.raises(AccessRefused):
        identifies()(PUBLIC, {"Cf-Access-Authenticated-User-Email": EMAIL})


def signed_in_by_password():
    return EMAIL


def never_asked():
    raise AssertionError("a password sign-in was looked for where none counts")


def test_the_tailnet_host_without_a_password_sign_in_is_asked_to_sign_in():
    with pytest.raises(LoginRequired):
        identifies()(TAILNET, {})


def test_the_tailnet_host_names_who_signed_in_by_password():
    assert identifies()(TAILNET, {}, login=signed_in_by_password) == Requester(
        email=EMAIL, by_login=True, on_tailnet=True
    )


def test_the_tailnet_host_is_matched_in_any_case():
    assert identifies()(TAILNET.upper(), {}, login=signed_in_by_password).email == EMAIL


def test_a_token_on_the_tailnet_host_is_not_looked_at():
    with pytest.raises(LoginRequired):
        identifies()(TAILNET, {ACCESS_TOKEN_HEADER: signed()})


def test_a_token_on_the_tailnet_host_does_not_stand_in_for_the_password_sign_in():
    assert identifies()(TAILNET, {ACCESS_TOKEN_HEADER: "garbage"}, login=signed_in_by_password).email == EMAIL


def test_a_route_that_needs_no_sign_in_on_the_tailnet_host_is_anonymous_and_asks_nothing():
    assert identifies()(TAILNET, {}, login=never_asked, needs_login=False) == Requester(
        email=None, on_tailnet=True
    )


def test_a_route_that_needs_no_sign_in_is_still_refused_from_outside_the_tailnet():
    with pytest.raises(AccessRefused):
        identifies()(PUBLIC, {}, login=never_asked, needs_login=False)


def test_the_public_host_never_looks_for_a_password_sign_in():
    with pytest.raises(AccessRefused):
        identifies()(PUBLIC, {}, login=never_asked)
    assert identifies()(PUBLIC, {ACCESS_TOKEN_HEADER: signed()}, login=never_asked) == Requester(email=EMAIL)


@pytest.mark.parametrize("edge_header", EDGE_HEADERS)
def test_the_tailnet_host_name_arriving_through_cloudflare_is_not_the_tailnet(edge_header):
    with pytest.raises(AccessRefused):
        identifies()(TAILNET, {edge_header: "8a1b2c3d4e5f6a7b-ORD"}, login=never_asked)


@pytest.mark.parametrize("edge_header", EDGE_HEADERS)
def test_through_cloudflare_a_valid_token_still_opens_the_tailnet_host_name(edge_header):
    assert identifies()(TAILNET, {edge_header: "x", ACCESS_TOKEN_HEADER: signed()}) == Requester(email=EMAIL)


def test_the_edge_headers_are_the_two_cloudflare_adds_to_every_proxied_request():
    assert set(EDGE_HEADERS) == {"Cf-Ray", "Cf-Connecting-Ip"}


@pytest.mark.parametrize("host", [PUBLIC, f"{TAILNET}.evil.example", f"evil.{TAILNET}", f"{TAILNET}:8000", "", None])
def test_only_the_exact_tailnet_host_takes_a_password_sign_in(host):
    with pytest.raises(AccessRefused):
        identifies()(host, {}, login=never_asked)


def test_with_no_tailnet_host_named_nothing_takes_a_password_sign_in():
    with pytest.raises(AccessRefused):
        identifies(tailnet_host=None)(TAILNET, {}, login=never_asked)


def test_keys_that_cannot_be_fetched_are_not_a_refusal_of_the_token():
    def unreachable():
        raise ConnectionRefusedError("no route")

    with pytest.raises(AccessKeysUnavailable):
        IdentifiesRequester(verifies=verifier(fetches=unreachable))(PUBLIC, {ACCESS_TOKEN_HEADER: signed()})
