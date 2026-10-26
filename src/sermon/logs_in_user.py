from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

from werkzeug.security import check_password_hash

from sermon.sets_password import MAXIMUM_LENGTH, hashes
from sermon.signs_in_user import SignsInUser
from sermon.store import Credential, Store, User
from sermon.throttles_logins import ThrottlesLogins

EMAIL = "email"
STAMP = "stamp"


class LoginRefused(Exception):
    def __init__(self):
        super().__init__("the email address or password is not right")


class LoginThrottled(Exception):
    def __init__(self, seconds):
        super().__init__("too many attempts; try again later")
        self.seconds = seconds


@cache
def hash_nobody_has():
    return hashes("a password no one was given")


def stamps(credential):
    return hashlib.sha256(credential.password_hash.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class Login:
    user: User
    stamp: str

    def remembered(self):
        return {EMAIL: self.user.email, STAMP: self.stamp}


@dataclass(frozen=True)
class LogsInUser:
    store: Store
    throttle: ThrottlesLogins

    def __call__(self, email, password, address):
        named = email.strip().lower()
        wait = self.throttle(named, address)
        if wait.total_seconds() > 0:
            raise LoginThrottled(math.ceil(wait.total_seconds()))
        credential = self.store.loads(Credential, named) if named else None
        held = credential.password_hash if credential else hash_nobody_has()
        right = check_password_hash(held, password[: MAXIMUM_LENGTH + 1])
        if credential is None or not right or len(password) > MAXIMUM_LENGTH:
            self.throttle.fails(named, address)
            raise LoginRefused()
        self.throttle.succeeds(named)
        return Login(user=SignsInUser(store=self.store)(named), stamp=stamps(credential))


@dataclass(frozen=True)
class RecognisesLogin:
    store: Store

    def __call__(self, remembered):
        if not isinstance(remembered, Mapping):
            return None
        email, stamp = remembered.get(EMAIL), remembered.get(STAMP)
        if not isinstance(email, str) or not isinstance(stamp, str):
            return None
        credential = self.store.loads(Credential, email)
        if credential is None or not hmac.compare_digest(stamp, stamps(credential)):
            return None
        return email
