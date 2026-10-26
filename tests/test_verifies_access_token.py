import json
import logging
import time
from datetime import UTC, datetime, timedelta

import pytest

from signs_access_tokens import (
    ACCESS,
    EMAIL,
    KEY_ID,
    TEAM_DOMAIN,
    claims,
    public_jwk,
    published_keys,
    signed,
    signed_with_the_public_key_as_a_shared_secret,
    unsigned,
    without,
)
from sermon.verifies_access_token import (
    AccessIdentity,
    AccessKeysUnavailable,
    AccessRefused,
    FetchesAccessKeys,
    HoldsAccessKeys,
    VerifiesAccessToken,
)

START = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.moment = START

    def __call__(self):
        return self.moment

    def advances(self, **delta):
        self.moment += timedelta(**delta)


class PublishesKeys:
    def __init__(self, *jwks):
        self.published = published_keys(*jwks)
        self.fetches = 0
        self.failure = None

    def rotates_to(self, *jwks):
        self.published = published_keys(*jwks)

    def __call__(self):
        self.fetches += 1
        if self.failure is not None:
            raise self.failure
        return self.published


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cloudflare():
    return PublishesKeys(public_jwk())


@pytest.fixture
def verifies(cloudflare, clock):
    return VerifiesAccessToken(
        access=ACCESS, keys=HoldsAccessKeys(fetches=cloudflare, clock=clock)
    )


def refusal_of(verifies, token):
    with pytest.raises(AccessRefused) as refused:
        verifies(token)
    return str(refused.value)


def test_a_token_signed_by_the_published_key_names_who_is_signed_in(verifies):
    assert verifies(signed()) == AccessIdentity(email=EMAIL)


def test_the_email_is_read_from_the_verified_claim_in_lower_case(verifies):
    assert verifies(signed(claims(email="Pastor@Reformation.Example"))).email == EMAIL


def test_an_audience_list_holding_ours_among_others_is_accepted(verifies):
    assert verifies(signed(claims(aud=["another-app-tag", ACCESS.audience]))).email == EMAIL


def test_a_token_for_another_application_is_refused(verifies):
    assert "audience" in refusal_of(verifies, signed(claims(aud=["another-app-tag"])))


def test_a_token_from_another_team_is_refused(verifies):
    assert "issuer" in refusal_of(verifies, signed(claims(iss="https://other.cloudflareaccess.com")))


def test_an_issuer_that_only_starts_like_ours_is_refused(verifies):
    assert "issuer" in refusal_of(verifies, signed(claims(iss=f"https://{TEAM_DOMAIN}.evil.example")))


def test_an_expired_token_is_refused(verifies):
    assert "expired" in refusal_of(verifies, signed(claims(exp=int(time.time()) - 3600)))


def test_a_token_that_expired_a_moment_ago_is_within_the_leeway(verifies):
    assert verifies(signed(claims(exp=int(time.time()) - 5))).email == EMAIL


def test_a_token_not_yet_valid_beyond_the_leeway_is_refused(verifies):
    assert "not yet valid" in refusal_of(verifies, signed(claims(nbf=int(time.time()) + 3600)))


def test_a_token_with_no_expiry_is_refused(verifies):
    assert "exp" in refusal_of(verifies, signed(without(claims(), "exp")))


@pytest.mark.parametrize("email", [None, "", "   ", 7, ["a@b.example"]])
def test_a_token_without_a_usable_email_is_refused(verifies, email):
    assert "email" in refusal_of(verifies, signed(claims(email=email)))


def test_a_token_with_no_email_claim_is_refused(verifies):
    assert "email" in refusal_of(verifies, signed(without(claims(), "email")))


def test_a_token_signed_by_another_key_under_our_key_id_is_refused(verifies):
    assert "signature" in refusal_of(verifies, signed(key="attacker"))


def test_a_token_naming_a_key_id_nobody_published_is_refused(verifies):
    assert "unknown key" in refusal_of(verifies, signed(key="attacker", kid="not-published"))


def test_a_token_with_no_key_id_is_refused(verifies):
    from signs_access_tokens import private_pem

    import jwt

    anonymous = jwt.encode(claims(), private_pem(), algorithm="RS256")
    assert "key id" in refusal_of(verifies, anonymous)


def test_an_unsigned_token_is_refused(verifies):
    assert "algorithm" in refusal_of(verifies, unsigned())


def test_a_token_signed_with_the_public_key_as_a_shared_secret_is_refused(verifies):
    assert "algorithm" in refusal_of(verifies, signed_with_the_public_key_as_a_shared_secret())


def test_a_token_signed_with_another_rsa_algorithm_is_refused(verifies):
    assert "algorithm" in refusal_of(verifies, signed(algorithm="RS384"))


@pytest.mark.parametrize("token", [None, "", "not-a-token", "a.b.c", "....", " "])
def test_something_that_is_not_a_token_is_refused(verifies, token):
    assert refusal_of(verifies, token)


def test_the_keys_are_fetched_once_for_many_tokens(verifies, cloudflare):
    for _ in range(5):
        verifies(signed())
    assert cloudflare.fetches == 1


def test_the_keys_are_fetched_again_once_they_have_lived_their_hour(verifies, cloudflare, clock):
    verifies(signed())
    clock.advances(minutes=59)
    verifies(signed())
    assert cloudflare.fetches == 1
    clock.advances(minutes=2)
    verifies(signed())
    assert cloudflare.fetches == 2


def test_a_rotated_key_is_found_by_fetching_again_on_the_unknown_key_id(verifies, cloudflare, clock):
    verifies(signed())
    clock.advances(minutes=5)
    cloudflare.rotates_to(public_jwk(), public_jwk("rotated", kid="b7e2"))
    assert verifies(signed(key="rotated", kid="b7e2")).email == EMAIL
    assert cloudflare.fetches == 2


def test_a_key_id_nobody_published_does_not_make_every_request_fetch(verifies, cloudflare, clock):
    verifies(signed())
    clock.advances(minutes=5)
    for _ in range(20):
        refusal_of(verifies, signed(key="attacker", kid="not-published"))
    assert cloudflare.fetches == 2


def test_an_unknown_key_id_may_fetch_again_once_the_cooldown_has_passed(verifies, cloudflare, clock):
    verifies(signed())
    clock.advances(minutes=5)
    refusal_of(verifies, signed(key="attacker", kid="not-published"))
    clock.advances(seconds=61)
    refusal_of(verifies, signed(key="attacker", kid="not-published"))
    assert cloudflare.fetches == 3


def test_keys_that_cannot_be_fetched_and_were_never_held_refuse_to_decide(verifies, cloudflare):
    cloudflare.failure = ConnectionRefusedError("no route")
    with pytest.raises(AccessKeysUnavailable):
        verifies(signed())


def test_a_failed_fetch_is_not_retried_by_every_request(verifies, cloudflare):
    cloudflare.failure = ConnectionRefusedError("no route")
    for _ in range(10):
        with pytest.raises(AccessKeysUnavailable):
            verifies(signed())
    assert cloudflare.fetches == 1


def test_a_failed_fetch_is_retried_after_the_cooldown(verifies, cloudflare, clock):
    cloudflare.failure = ConnectionRefusedError("no route")
    with pytest.raises(AccessKeysUnavailable):
        verifies(signed())
    cloudflare.failure = None
    clock.advances(seconds=61)
    assert verifies(signed()).email == EMAIL


def test_the_keys_already_held_keep_verifying_while_a_refresh_fails(verifies, cloudflare, clock):
    verifies(signed())
    clock.advances(hours=2)
    cloudflare.failure = TimeoutError("timed out")
    assert verifies(signed()).email == EMAIL


@pytest.mark.parametrize("answer", [{}, {"keys": "nope"}, {"keys": [None]}, [], "html"])
def test_an_answer_that_is_not_a_key_set_is_unavailable_not_a_crash(clock, answer):
    verifies = VerifiesAccessToken(
        access=ACCESS, keys=HoldsAccessKeys(fetches=lambda: answer, clock=clock)
    )
    with pytest.raises(AccessKeysUnavailable):
        verifies(signed())


def test_the_published_keys_are_asked_for_at_the_team_domain():
    asked = []

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *failure):
            return False

        def read(self):
            return json.dumps(published_keys(public_jwk())).encode()

    def opens(request, timeout):
        asked.append((request.full_url, timeout))
        return Answer()

    assert FetchesAccessKeys(url=ACCESS.keys_url, opens=opens)() == published_keys(public_jwk())
    assert asked == [(f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs", 5)]


def test_a_refusal_is_logged_with_its_reason_and_never_the_token(verifies, caplog):
    token = signed(claims(aud=["another-app-tag"]))
    with caplog.at_level(logging.INFO, logger="sermon.access"):
        refusal_of(verifies, token)
    assert "audience" in caplog.text
    assert token not in caplog.text
