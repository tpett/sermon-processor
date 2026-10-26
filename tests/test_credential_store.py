import sqlite3
from datetime import UTC, datetime

import pytest

from sermon.store import DATABASE_NAME, Credential, User, opens_store

EMAIL = "pastor@reformation.example"
FIRST = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
HASH = "scrypt:32768:8:1$salt$digest"


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def test_a_credential_is_kept_for_the_user_it_belongs_to(store):
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    store.saves(Credential(email=EMAIL, password_hash=HASH))
    assert store.loads(Credential, EMAIL) == Credential(email=EMAIL, password_hash=HASH)


def test_saving_a_credential_again_replaces_the_hash(store):
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    store.saves(Credential(email=EMAIL, password_hash=HASH))
    store.saves(Credential(email=EMAIL, password_hash="scrypt:32768:8:1$other$digest"))
    assert [one.password_hash for one in store.lists(Credential)] == ["scrypt:32768:8:1$other$digest"]


def test_a_credential_for_nobody_is_refused(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(Credential(email=EMAIL, password_hash=HASH))


def test_a_user_with_no_credential_is_still_a_user(store):
    store.saves(User(email=EMAIL, first_seen_at=FIRST))
    assert store.loads(Credential, EMAIL) is None


def test_a_database_written_before_credentials_opens_and_keeps_its_users(tmp_path):
    first = opens_store(tmp_path)
    first.saves(User(email=EMAIL, first_seen_at=FIRST))
    first.close()
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    with connection:
        connection.execute("DROP TABLE credential")
    connection.close()
    second = opens_store(tmp_path)
    try:
        assert second.loads(User, EMAIL) == User(email=EMAIL, first_seen_at=FIRST)
        second.saves(Credential(email=EMAIL, password_hash=HASH))
        assert second.loads(Credential, EMAIL).password_hash == HASH
    finally:
        second.close()
