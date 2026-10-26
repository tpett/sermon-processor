from datetime import UTC, datetime
from unittest import mock

import pytest

from sermon import logs_in_user
from sermon.logs_in_user import LoginRefused, LoginThrottled, LogsInUser, RecognisesLogin
from sermon.sets_password import SetsPassword
from sermon.store import User, opens_store
from sermon.throttles_logins import EMAIL_FAILURES_FREE, ThrottlesLogins

FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
EMAIL = "pastor@reformation.example"
PASSWORD = "a long enough passphrase"
ADDRESS = "100.64.0.9"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def logs_in(store):
    SetsPassword(store=store, clock=lambda: FIRST)(EMAIL, PASSWORD)
    return LogsInUser(store=store, throttle=ThrottlesLogins(clock=lambda: FIRST))


def test_the_right_password_signs_in_the_user(logs_in):
    assert logs_in(EMAIL, PASSWORD, ADDRESS).user == User(email=EMAIL, first_seen_at=FIRST)


def test_the_address_is_matched_without_regard_to_case_or_padding(logs_in):
    assert logs_in("  Pastor@REFORMATION.example ", PASSWORD, ADDRESS).user.email == EMAIL


def test_a_wrong_password_is_refused(logs_in):
    with pytest.raises(LoginRefused):
        logs_in(EMAIL, PASSWORD + "x", ADDRESS)


def test_an_unknown_address_is_refused_the_same_way(logs_in):
    with pytest.raises(LoginRefused) as unknown:
        logs_in("nobody@reformation.example", PASSWORD, ADDRESS)
    with pytest.raises(LoginRefused) as wrong:
        logs_in(EMAIL, "not the password", ADDRESS)
    assert type(unknown.value) is type(wrong.value) and str(unknown.value) == str(wrong.value)


def test_an_unknown_address_still_costs_a_hash_check(logs_in):
    with mock.patch.object(logs_in_user, "check_password_hash", return_value=False) as checked:
        with pytest.raises(LoginRefused):
            logs_in("nobody@reformation.example", PASSWORD, ADDRESS)
    assert checked.call_count == 1


def test_a_user_who_only_came_through_access_cannot_sign_in(store, logs_in):
    store.saves(User(email="elder@reformation.example", first_seen_at=FIRST))
    with pytest.raises(LoginRefused):
        logs_in("elder@reformation.example", "", ADDRESS)
    with pytest.raises(LoginRefused):
        logs_in("elder@reformation.example", "anything at all", ADDRESS)


def test_an_empty_password_and_an_empty_address_are_refused(logs_in):
    with pytest.raises(LoginRefused):
        logs_in(EMAIL, "", ADDRESS)
    with pytest.raises(LoginRefused):
        logs_in("", PASSWORD, ADDRESS)


def test_an_enormous_password_is_refused_without_being_hashed_whole(logs_in):
    with mock.patch.object(logs_in_user, "check_password_hash", return_value=True) as checked:
        with pytest.raises(LoginRefused):
            logs_in(EMAIL, "x" * 100_000, ADDRESS)
    assert len(checked.call_args.args[1]) <= 1025


def test_repeated_failures_hold_the_person_off_even_for_the_right_password(logs_in):
    for _ in range(EMAIL_FAILURES_FREE):
        with pytest.raises(LoginRefused):
            logs_in(EMAIL, "not the password", ADDRESS)
    with pytest.raises(LoginThrottled) as held:
        logs_in(EMAIL, PASSWORD, ADDRESS)
    assert held.value.seconds > 0


def test_an_attempt_made_while_held_off_is_not_counted_against_the_person(store):
    clock = [FIRST]
    throttle = ThrottlesLogins(clock=lambda: clock[0])
    SetsPassword(store=store, clock=lambda: FIRST)(EMAIL, PASSWORD)
    logs_in = LogsInUser(store=store, throttle=throttle)
    for _ in range(EMAIL_FAILURES_FREE):
        with pytest.raises(LoginRefused):
            logs_in(EMAIL, "not the password", ADDRESS)
    for _ in range(10):
        with pytest.raises(LoginThrottled):
            logs_in(EMAIL, "not the password", ADDRESS)
    clock[0] = FIRST.replace(minute=2)
    assert logs_in(EMAIL, PASSWORD, ADDRESS).user.email == EMAIL


def test_a_sign_in_is_remembered_as_the_address_and_a_stamp_of_the_password(store, logs_in):
    remembered = RecognisesLogin(store=store)(logs_in(EMAIL, PASSWORD, ADDRESS).remembered())
    assert remembered == EMAIL


@pytest.mark.parametrize("held", [None, {}, {"email": EMAIL}, {"stamp": "x"}, {"email": 3, "stamp": "x"}, {"email": EMAIL, "stamp": "forged"}, "pastor"])
def test_something_that_is_not_a_sign_in_is_not_recognised(store, logs_in, held):
    assert RecognisesLogin(store=store)(held) is None


def test_a_sign_in_ends_when_the_password_is_changed(store, logs_in):
    remembered = logs_in(EMAIL, PASSWORD, ADDRESS).remembered()
    SetsPassword(store=store, clock=lambda: FIRST)(EMAIL, "a different passphrase")
    assert RecognisesLogin(store=store)(remembered) is None


def test_a_sign_in_for_someone_with_no_password_is_not_recognised(store):
    store.saves(User(email="elder@reformation.example", first_seen_at=FIRST))
    assert RecognisesLogin(store=store)({"email": "elder@reformation.example", "stamp": ""}) is None
