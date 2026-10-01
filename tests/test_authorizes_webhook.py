import logging

import pytest

from sermon.authorizes_webhook import ALLOWED, UNAUTHENTICATED, UNCONFIGURED, AuthorizesWebhook
from sermon.config import WEBHOOK_TOKEN, Credential, UnusableConfiguration

TOKEN = "f1f0c4a7d2b54e0f9a6c3e8b7d1540a2"
AUTHORIZES = AuthorizesWebhook(token=Credential(TOKEN))

REFUSED = [
    f"Bearer {TOKEN[:-1]}",
    f"Bearer {TOKEN}0",
    f"Bearer  {TOKEN}",
    f"Bearer {TOKEN.upper()}",
    f"Basic {TOKEN}",
    f"Token {TOKEN}",
    TOKEN,
    "Bearer",
    "Bearer ",
    "",
    None,
]


def test_the_token_the_processor_was_given_is_allowed():
    assert AUTHORIZES(f"Bearer {TOKEN}") == ALLOWED


def test_the_scheme_is_read_without_regard_to_its_case():
    assert AUTHORIZES(f"bearer {TOKEN}") == ALLOWED
    assert AUTHORIZES(f"BEARER {TOKEN}") == ALLOWED


@pytest.mark.parametrize("presented", REFUSED)
def test_anything_else_is_refused_as_unauthenticated(presented):
    assert AUTHORIZES(presented) == (401, UNAUTHENTICATED)


@pytest.mark.parametrize("presented", REFUSED)
def test_a_refusal_never_repeats_what_was_presented(presented):
    assert TOKEN not in str(AUTHORIZES(presented))


def test_an_unconfigured_processor_refuses_everything_and_names_the_variable():
    unconfigured = AuthorizesWebhook()
    assert unconfigured.token is None
    for presented in [f"Bearer {TOKEN}", *REFUSED]:
        assert unconfigured(presented) == (503, UNCONFIGURED)
    assert WEBHOOK_TOKEN in UNCONFIGURED


def test_a_bare_string_token_is_refused_so_it_cannot_print_itself():
    with pytest.raises(UnusableConfiguration) as refused:
        AuthorizesWebhook(token=TOKEN)
    assert WEBHOOK_TOKEN in str(refused.value)
    assert TOKEN not in str(refused.value)


def test_the_token_reaches_no_repr_or_log_line(caplog):
    with caplog.at_level(logging.INFO):
        logging.getLogger("sermon").info("%s %r", AUTHORIZES, AUTHORIZES)
    for rendered in (repr(AUTHORIZES), str(AUTHORIZES), caplog.text):
        assert TOKEN not in rendered
