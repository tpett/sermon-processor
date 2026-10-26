from __future__ import annotations

import re
from dataclasses import dataclass

from werkzeug.security import generate_password_hash

from sermon.signs_in_user import SignsInUser, now
from sermon.store import Credential, Store

MINIMUM_LENGTH = 10
MAXIMUM_LENGTH = 1024
HASH_METHOD = "scrypt"
ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+$")


class PasswordRefused(ValueError):
    pass


class EmailRefused(ValueError):
    pass


def reads_email(text):
    named = text.strip().lower()
    if not ADDRESS.match(named):
        raise EmailRefused(f"{text.strip()!r} is not an email address")
    return named


def refuses_an_unusable_password(password):
    if len(password) < MINIMUM_LENGTH:
        raise PasswordRefused(f"a password needs at least {MINIMUM_LENGTH} characters")
    if len(password) > MAXIMUM_LENGTH:
        raise PasswordRefused(f"a password may have at most {MAXIMUM_LENGTH} characters")


def hashes(password):
    return generate_password_hash(password, method=HASH_METHOD)


@dataclass(frozen=True)
class SetsPassword:
    store: Store
    clock: object = now

    def __call__(self, email, password):
        named = reads_email(email)
        refuses_an_unusable_password(password)
        user = SignsInUser(store=self.store, clock=self.clock)(named)
        self.store.saves(Credential(email=named, password_hash=hashes(password)))
        return user
