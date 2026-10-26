from __future__ import annotations

import json
import logging
import threading
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import jwt

from sermon.config import CloudflareAccess

log = logging.getLogger("sermon.access")

ALGORITHM = "RS256"
LEEWAY_SECONDS = 30
KEYS_LIVE = timedelta(hours=1)
FETCH_COOLDOWN = timedelta(seconds=60)
FETCH_TIMEOUT_SECONDS = 5
REQUIRED_CLAIMS = ("exp", "iss", "aud")
REFUSED_AS = {
    jwt.ExpiredSignatureError: "expired",
    jwt.ImmatureSignatureError: "not yet valid",
    jwt.InvalidAudienceError: "audience is not this application",
    jwt.InvalidIssuerError: "issuer is not this team",
    jwt.InvalidSignatureError: "signature does not verify",
    jwt.MissingRequiredClaimError: "a required claim is missing (exp, iss or aud)",
}


class AccessRefused(Exception):
    pass


class AccessKeysUnavailable(Exception):
    pass


@dataclass(frozen=True)
class AccessIdentity:
    email: str


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class FetchesAccessKeys:
    url: str
    opens: Callable = urllib.request.urlopen

    def __call__(self):
        asked = urllib.request.Request(
            self.url, headers={"Accept": "application/json", "User-Agent": "sermon-processor"}
        )
        with self.opens(asked, timeout=FETCH_TIMEOUT_SECONDS) as answered:
            return json.loads(answered.read())


def reads_keys(published):
    if not isinstance(published, Mapping) or not isinstance(published.get("keys"), list):
        raise ValueError("the answer holds no list of keys")
    return {
        key["kid"]: key
        for key in published["keys"]
        if isinstance(key, Mapping) and isinstance(key.get("kid"), str)
    }


@dataclass
class HoldsAccessKeys:
    fetches: Callable[[], object]
    clock: Callable[[], datetime] = now
    lives: timedelta = KEYS_LIVE
    cools: timedelta = FETCH_COOLDOWN
    held: dict = field(default_factory=dict, init=False)
    fetched_at: datetime | None = field(default=None, init=False)
    attempted_at: datetime | None = field(default=None, init=False)
    turn: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __call__(self, key_id):
        with self.turn:
            moment = self.clock()
            if self.fetched_at is None or moment - self.fetched_at >= self.lives:
                self.refreshes(moment)
            if key_id not in self.held:
                self.refreshes(moment)
            if not self.held:
                raise AccessKeysUnavailable("Cloudflare's signing keys have not been fetched")
            return self.held.get(key_id)

    def refreshes(self, moment):
        if self.attempted_at is not None and moment - self.attempted_at < self.cools:
            return
        self.attempted_at = moment
        try:
            self.held = reads_keys(self.fetches())
        except (OSError, ValueError, TypeError) as failure:
            log.warning("could not fetch Cloudflare's signing keys: %s: %s", type(failure).__name__, failure)
            return
        self.fetched_at = moment


@dataclass(frozen=True)
class VerifiesAccessToken:
    access: CloudflareAccess
    keys: Callable[[str], Mapping | None]

    def __call__(self, token):
        try:
            return self.identifies(token)
        except AccessRefused as refused:
            log.warning("refused an Access token: %s", refused)
            raise

    def identifies(self, token):
        if not token:
            raise AccessRefused("no token was presented")
        try:
            header = jwt.get_unverified_header(token)
        except (jwt.PyJWTError, TypeError, AttributeError) as unreadable:
            raise AccessRefused("not a readable token") from unreadable
        if header.get("alg") != ALGORITHM:
            raise AccessRefused(f"algorithm is not {ALGORITHM}")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise AccessRefused("the token names no key id")
        published = self.keys(key_id)
        if published is None:
            raise AccessRefused("unknown key id")
        try:
            claims = jwt.decode(
                token,
                jwt.PyJWK(dict(published)).key,
                algorithms=[ALGORITHM],
                audience=self.access.audience,
                issuer=self.access.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as invalid:
            raise AccessRefused(reads_refusal(invalid)) from invalid
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise AccessRefused("the token carries no email")
        return AccessIdentity(email=email.strip().lower())


def reads_refusal(invalid):
    for kind, said in REFUSED_AS.items():
        if isinstance(invalid, kind):
            return said
    return f"invalid ({type(invalid).__name__})"
