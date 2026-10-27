import sqlite3
import threading
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.store import DATABASE_NAME, Credential, User, opens_store
from sermon.store import store as store_module

EMAIL = "pastor@reformation.example"
ELDER = "elder@reformation.example"
FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)

BEFORE_ROLES = """
CREATE TABLE user (
    email TEXT NOT NULL PRIMARY KEY,
    first_seen_at TEXT NOT NULL
);
CREATE TABLE credential (
    email TEXT NOT NULL PRIMARY KEY REFERENCES user(email),
    password_hash TEXT NOT NULL
);
INSERT INTO user VALUES ('pastor@reformation.example', '2026-10-01T09:00:00+00:00');
INSERT INTO user VALUES ('elder@reformation.example', '2026-10-02T09:00:00+00:00');
INSERT INTO credential VALUES ('elder@reformation.example', 'scrypt:kept');
"""


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def older_root(tmp_path):
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    connection.executescript(BEFORE_ROLES)
    connection.close()
    return tmp_path


def test_a_person_is_a_viewer_until_made_a_reviewer(store):
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    assert store.loads(User, EMAIL).role == "viewer"


def test_a_person_made_a_reviewer_stays_one(store):
    store.saves(replace(store.saves(User(email=EMAIL, first_seen_at=FIRST)), role="reviewer"))
    assert store.loads(User, EMAIL).role == "reviewer"


def test_a_role_outside_the_vocabulary_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(User(email=EMAIL, first_seen_at=FIRST, role="owner"))
    assert store.lists(User) == []


def test_a_database_written_before_roles_opens_with_its_people_as_viewers(older_root):
    store = opens_store(older_root)
    try:
        assert {one.email: one.role for one in store.lists(User)} == {
            EMAIL: "viewer",
            ELDER: "viewer",
        }
        assert store.loads(Credential, ELDER).password_hash == "scrypt:kept"
    finally:
        store.close()


def test_a_person_promoted_in_a_migrated_database_stays_promoted_on_reopening(older_root):
    store = opens_store(older_root)
    store.saves(replace(store.loads(User, EMAIL), role="reviewer"))
    store.close()
    reopened = opens_store(older_root)
    try:
        assert store_roles(reopened) == {EMAIL: "reviewer", ELDER: "viewer"}
    finally:
        reopened.close()


def test_a_migrated_database_refuses_a_role_outside_the_vocabulary(older_root):
    store = opens_store(older_root)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.saves(replace(store.loads(User, EMAIL), role="owner"))
        assert store.loads(User, EMAIL).role == "viewer"
    finally:
        store.close()


def test_two_openings_of_an_older_database_at_once_both_succeed(older_root, monkeypatch):
    inspected = threading.Barrier(2, timeout=0.5)
    seen = threading.local()
    reads = store_module.reads_stored_columns

    def reads_then_waits_for_the_other_opening(connection, table):
        columns = reads(connection, table)
        if not getattr(seen, "waited", False):
            seen.waited = True
            try:
                inspected.wait()
            except threading.BrokenBarrierError:
                pass
        return columns

    monkeypatch.setattr(
        store_module, "reads_stored_columns", reads_then_waits_for_the_other_opening
    )
    opened = []
    failures = []

    def opens():
        try:
            opened.append(opens_store(older_root))
        except sqlite3.OperationalError as error:
            failures.append(error)

    threads = [threading.Thread(target=opens) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert failures == []
        assert len(opened) == 2
        with sqlite3.connect(older_root / DATABASE_NAME) as inspecting:
            columns = [row[1] for row in inspecting.execute("PRAGMA table_info(user)")]
        assert columns.count("role") == 1
    finally:
        for one in opened:
            one.close()


def store_roles(store):
    return {one.email: one.role for one in store.lists(User)}
