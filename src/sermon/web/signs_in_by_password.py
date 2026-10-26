from __future__ import annotations

from urllib.parse import urlsplit

from flask import g, request
from flask.sessions import SecureCookieSessionInterface

HOME = "/"
SIGN_IN_PATH = "/login"
MAX_DESTINATION = 2000
MAX_ADDRESS = 64
SAME_ORIGIN_FETCHES = frozenset({"same-origin", "none"})


def reads_safe_destination(asked):
    if not isinstance(asked, str) or not asked or len(asked) > MAX_DESTINATION:
        return HOME
    if any(ord(character) < 32 or ord(character) == 127 or character == "\\" for character in asked):
        return HOME
    reached = urlsplit(asked)
    if reached.scheme or reached.netloc or not asked.startswith("/") or asked.startswith("//"):
        return HOME
    if reached.path == SIGN_IN_PATH:
        return HOME
    return asked


def comes_from_another_site(asked):
    origin = asked.headers.get("Origin")
    if origin is not None and urlsplit(origin).netloc.lower() != asked.host.lower():
        return True
    fetch_site = asked.headers.get("Sec-Fetch-Site")
    return fetch_site is not None and fetch_site.lower() not in SAME_ORIGIN_FETCHES


def reads_client_address(asked):
    forwarded = asked.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
    return (forwarded or asked.remote_addr or "unknown")[:MAX_ADDRESS]


class SessionsForTailnet(SecureCookieSessionInterface):
    """Secure when the request was HTTPS or, on the tailnet host only, the proxy says it was."""

    def get_cookie_secure(self, app):
        if request.is_secure:
            return True
        if not g.get("on_tailnet"):
            return False
        return request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() == "https"
