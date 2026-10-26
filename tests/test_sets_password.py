from datetime import UTC, datetime, timedelta

import pytest
from werkzeug.security import check_password_hash

from sermon.sets_password import EmailRefused, PasswordRefused, SetsPassword
from sermon.store import Credential, User, opens_store

FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
EMAIL = "pastor@reformation.example"
PASSWORD = "a long enough passphrase"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def sets(store, moment=FIRST):
    return SetsPassword(store=store, clock=lambda: moment)


def test_the_password_is_kept_only_as_a_salted_hash(store):
    sets(store)(EMAIL, PASSWORD)
    held = store.loads(Credential, EMAIL).password_hash
    assert PASSWORD not in held
    assert held.startswith("scrypt:")
    assert check_password_hash(held, PASSWORD)
    assert not check_password_hash(held, PASSWORD + "x")


def test_the_same_password_for_two_people_is_held_differently(store):
    sets(store)(EMAIL, PASSWORD)
    sets(store)("elder@reformation.example", PASSWORD)
    first, second = (one.password_hash for one in store.lists(Credential))
    assert first != second


def test_a_person_the_system_does_not_know_becomes_a_user_at_that_moment(store):
    user = sets(store)(EMAIL, PASSWORD)
    assert user == User(email=EMAIL, first_seen_at=FIRST)
    assert store.lists(User) == [user]


def test_a_person_who_signed_in_through_access_keeps_when_they_were_first_seen(store):
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    sets(store, FIRST + timedelta(days=9))(EMAIL, PASSWORD)
    assert store.lists(User) == [User(email=EMAIL, first_seen_at=FIRST)]


def test_the_address_is_kept_lower_cased_and_trimmed(store):
    sets(store)("  Pastor@Reformation.Example ", PASSWORD)
    assert [one.email for one in store.lists(Credential)] == [EMAIL]


def test_a_second_password_replaces_the_first(store):
    sets(store)(EMAIL, PASSWORD)
    sets(store)(EMAIL, "another long passphrase")
    (held,) = store.lists(Credential)
    assert check_password_hash(held.password_hash, "another long passphrase")
    assert not check_password_hash(held.password_hash, PASSWORD)


@pytest.mark.parametrize("password", ["", "short", "123456789"])
def test_a_password_under_ten_characters_is_refused(store, password):
    with pytest.raises(PasswordRefused, match="at least 10"):
        sets(store)(EMAIL, password)
    assert store.lists(Credential) == [] and store.lists(User) == []


def test_a_password_past_a_thousand_characters_is_refused(store):
    with pytest.raises(PasswordRefused, match="at most 1024"):
        sets(store)(EMAIL, "x" * 1025)


@pytest.mark.parametrize("email", ["", "pastor", "pastor@", "@reformation.example", "two words@example.org", "a@b@c"])
def test_something_that_is_not_an_address_is_refused(store, email):
    with pytest.raises(EmailRefused):
        sets(store)(email, PASSWORD)
    assert store.lists(User) == []
