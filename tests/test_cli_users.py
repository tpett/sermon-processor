import getpass
import sqlite3
from datetime import UTC, datetime
from unittest import mock

from werkzeug.security import check_password_hash

from sermon.cli import manages_users
from sermon.store import DATABASE_NAME, Credential, User, opens_store

EMAIL = "pastor@reformation.example"
PASSWORD = "a long enough passphrase"
FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


class Lines:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    def __str__(self):
        return "\n".join(self.lines)


class Typing:
    def __init__(self, *entries):
        self.entries = list(entries)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.entries.pop(0)


def runs(tmp_path, *arguments, typed=(PASSWORD, PASSWORD), settings=None):
    said, typing = Lines(), Typing(*typed)
    outcome = manages_users(
        settings={"SERMON_DATA_ROOT": str(tmp_path)} if settings is None else settings,
        arguments=list(arguments),
        prints=said,
        asks=typing,
    )
    return outcome, said, typing


def reads(tmp_path, entity, identity):
    store = opens_store(tmp_path)
    try:
        return store.loads(entity, identity)
    finally:
        store.close()


def test_adding_a_person_makes_them_a_user_with_a_hashed_password(tmp_path):
    outcome, said, _ = runs(tmp_path, "add", EMAIL)
    assert outcome == 0
    assert reads(tmp_path, User, EMAIL).email == EMAIL
    held = reads(tmp_path, Credential, EMAIL).password_hash
    assert held != PASSWORD and check_password_hash(held, PASSWORD)
    assert EMAIL in str(said)


def test_the_password_is_asked_for_twice(tmp_path):
    _, _, typing = runs(tmp_path, "add", EMAIL)
    assert len(typing.prompts) == 2


def test_a_password_given_as_an_argument_is_refused_and_not_echoed_back(tmp_path):
    outcome, said, typing = runs(tmp_path, "add", EMAIL, PASSWORD)
    assert outcome == 1 and "sermon-user" in str(said)
    assert PASSWORD not in str(said)
    assert typing.prompts == [] and reads(tmp_path, User, EMAIL) is None


def test_the_default_prompt_is_getpass_so_nothing_is_echoed(tmp_path):
    with mock.patch.object(getpass, "getpass", side_effect=[PASSWORD, PASSWORD]) as asked:
        manages_users(
            settings={"SERMON_DATA_ROOT": str(tmp_path)}, arguments=["add", EMAIL], prints=Lines()
        )
    assert asked.call_count == 2


def test_neither_the_password_nor_its_hash_is_ever_printed(tmp_path):
    _, said, _ = runs(tmp_path, "add", EMAIL)
    _, listed, _ = runs(tmp_path, "list")
    held = reads(tmp_path, Credential, EMAIL).password_hash
    for output in (str(said), str(listed)):
        assert PASSWORD not in output and held not in output and "scrypt" not in output


def test_two_entries_that_differ_set_nothing(tmp_path):
    outcome, said, _ = runs(tmp_path, "add", EMAIL, typed=(PASSWORD, PASSWORD + "x"))
    assert outcome == 1 and "do not match" in str(said)
    assert reads(tmp_path, User, EMAIL) is None


def test_a_password_that_is_too_short_sets_nothing(tmp_path):
    outcome, said, _ = runs(tmp_path, "add", EMAIL, typed=("short", "short"))
    assert outcome == 1 and "at least 10" in str(said)
    assert reads(tmp_path, User, EMAIL) is None


def test_something_that_is_not_an_address_is_refused_before_a_password_is_asked(tmp_path):
    outcome, said, typing = runs(tmp_path, "add", "pastor")
    assert outcome == 1 and "not an email address" in str(said)
    assert typing.prompts == []


def test_adding_someone_who_already_has_a_password_points_to_set_password(tmp_path):
    runs(tmp_path, "add", EMAIL)
    outcome, said, typing = runs(tmp_path, "add", EMAIL)
    assert outcome == 1 and "set-password" in str(said)
    assert typing.prompts == []


def test_adding_someone_who_only_came_through_access_gives_them_a_password(tmp_path):
    store = opens_store(tmp_path)
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    store.close()
    outcome, _, _ = runs(tmp_path, "add", EMAIL)
    assert outcome == 0
    assert reads(tmp_path, User, EMAIL).first_seen_at == FIRST
    assert reads(tmp_path, Credential, EMAIL) is not None


def test_setting_a_password_replaces_the_old_one(tmp_path):
    runs(tmp_path, "add", EMAIL)
    outcome, _, _ = runs(tmp_path, "set-password", EMAIL, typed=("another long passphrase",) * 2)
    held = reads(tmp_path, Credential, EMAIL).password_hash
    assert outcome == 0
    assert check_password_hash(held, "another long passphrase") and not check_password_hash(held, PASSWORD)


def test_setting_a_password_for_nobody_points_to_add(tmp_path):
    outcome, said, typing = runs(tmp_path, "set-password", EMAIL)
    assert outcome == 1 and "add" in str(said)
    assert typing.prompts == []


def test_listing_shows_each_person_and_whether_they_can_sign_in_with_a_password(tmp_path):
    runs(tmp_path, "add", EMAIL)
    store = opens_store(tmp_path)
    store.saves(User(email="elder@reformation.example", first_seen_at=FIRST))
    store.close()
    outcome, said, _ = runs(tmp_path, "list")
    lines = {line.split()[0]: line for line in said.lines}
    assert outcome == 0
    assert "password set" in lines[EMAIL]
    assert "no password" in lines["elder@reformation.example"]
    assert "2026-10-26" in lines["elder@reformation.example"]


def test_listing_with_nobody_says_so(tmp_path):
    outcome, said, _ = runs(tmp_path, "list")
    assert outcome == 0 and "no users" in str(said)


def test_a_command_it_does_not_know_prints_the_usage_and_fails(tmp_path):
    outcome, said, _ = runs(tmp_path, "delete", EMAIL)
    assert outcome == 1 and "sermon-user" in str(said)


def test_no_command_prints_the_usage_and_fails(tmp_path):
    outcome, said, _ = runs(tmp_path)
    assert outcome == 1 and "sermon-user" in str(said)


def test_without_a_data_root_it_says_what_is_missing(tmp_path):
    outcome, said, _ = runs(tmp_path, "list", settings={})
    assert outcome == 1 and "SERMON_DATA_ROOT" in str(said)


def test_a_database_the_code_cannot_use_is_reported(tmp_path):
    opens_store(tmp_path).close()
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    with connection:
        connection.execute("ALTER TABLE artifact DROP COLUMN input_loudness_lufs")
    connection.close()
    outcome, said, _ = runs(tmp_path, "list")
    assert outcome == 1 and "sermon-reconcile" in str(said)


def test_a_cancelled_prompt_sets_nothing(tmp_path):
    def cancelled(prompt):
        raise KeyboardInterrupt

    said = Lines()
    outcome = manages_users(
        settings={"SERMON_DATA_ROOT": str(tmp_path)}, arguments=["add", EMAIL], prints=said, asks=cancelled
    )
    assert outcome == 1 and "cancelled" in str(said)
    assert reads(tmp_path, User, EMAIL) is None


def test_a_person_added_by_the_owner_is_a_viewer(tmp_path):
    runs(tmp_path, "add", EMAIL)
    assert reads(tmp_path, User, EMAIL).role == "viewer"


def test_promoting_a_person_makes_them_a_reviewer_and_says_so(tmp_path):
    store = opens_store(tmp_path)
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    store.close()
    outcome, said, typing = runs(tmp_path, "promote", EMAIL)
    assert outcome == 0
    assert str(said) == f"{EMAIL} is now a reviewer"
    assert reads(tmp_path, User, EMAIL).role == "reviewer"
    assert reads(tmp_path, User, EMAIL).first_seen_at == FIRST
    assert typing.prompts == []


def test_promoting_keeps_the_password(tmp_path):
    runs(tmp_path, "add", EMAIL)
    held = reads(tmp_path, Credential, EMAIL).password_hash
    runs(tmp_path, "promote", EMAIL)
    assert reads(tmp_path, Credential, EMAIL).password_hash == held


def test_promoting_someone_already_a_reviewer_says_so_and_changes_nothing(tmp_path):
    runs(tmp_path, "add", EMAIL)
    runs(tmp_path, "promote", EMAIL)
    outcome, said, _ = runs(tmp_path, "promote", EMAIL)
    assert outcome == 0 and str(said) == f"{EMAIL} is already a reviewer"
    assert reads(tmp_path, User, EMAIL).role == "reviewer"


def test_promoting_the_address_in_capitals_finds_the_same_person(tmp_path):
    runs(tmp_path, "add", EMAIL)
    outcome, said, _ = runs(tmp_path, "promote", EMAIL.upper())
    assert outcome == 0 and str(said) == f"{EMAIL} is now a reviewer"


def test_promoting_someone_who_has_not_signed_in_yet_makes_nobody(tmp_path):
    outcome, said, _ = runs(tmp_path, "promote", EMAIL)
    assert outcome == 1 and "not a user yet" in str(said)
    assert reads(tmp_path, User, EMAIL) is None


def test_promoting_something_that_is_not_an_address_is_refused(tmp_path):
    outcome, said, _ = runs(tmp_path, "promote", "pastor")
    assert outcome == 1 and "not an email address" in str(said)


def test_listing_shows_each_persons_role(tmp_path):
    runs(tmp_path, "add", EMAIL)
    runs(tmp_path, "add", "elder@reformation.example")
    runs(tmp_path, "promote", EMAIL)
    outcome, said, _ = runs(tmp_path, "list")
    lines = {line.split()[0]: line for line in said.lines}
    assert outcome == 0
    assert lines[EMAIL].split()[1] == "reviewer"
    assert lines["elder@reformation.example"].split()[1] == "viewer"


def test_the_usage_names_promote(tmp_path):
    _, said, _ = runs(tmp_path)
    assert "promote <email>" in str(said)
