from datetime import UTC, datetime, timedelta

import pytest

from sermon.signs_in_user import SignsInUser
from sermon.store import User, opens_store

FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
EMAIL = "pastor@reformation.example"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_the_first_sign_in_creates_the_user_at_that_moment(store):
    user = SignsInUser(store=store, clock=lambda: FIRST)(EMAIL)
    assert user == User(email=EMAIL, first_seen_at=FIRST)
    assert store.lists(User) == [user]


def test_a_later_sign_in_finds_the_same_user_and_keeps_when_they_were_first_seen(store):
    SignsInUser(store=store, clock=lambda: FIRST)(EMAIL)
    again = SignsInUser(store=store, clock=lambda: FIRST + timedelta(days=30))(EMAIL)
    assert again.first_seen_at == FIRST
    assert len(store.lists(User)) == 1


def test_two_people_are_two_users(store):
    signs_in = SignsInUser(store=store, clock=lambda: FIRST)
    signs_in(EMAIL)
    signs_in("elder@reformation.example")
    assert {user.email for user in store.lists(User)} == {EMAIL, "elder@reformation.example"}


def test_a_user_is_still_there_when_the_store_is_opened_again(tmp_path):
    first = opens_store(tmp_path)
    SignsInUser(store=first, clock=lambda: FIRST)(EMAIL)
    first.close()
    second = opens_store(tmp_path)
    try:
        assert second.loads(User, EMAIL) == User(email=EMAIL, first_seen_at=FIRST)
    finally:
        second.close()
