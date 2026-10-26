from __future__ import annotations

from dataclasses import dataclass

from sermon.verifies_access_token import VerifiesAccessToken

ACCESS_TOKEN_HEADER = "Cf-Access-Jwt-Assertion"
EDGE_HEADERS = ("Cf-Ray", "Cf-Connecting-Ip")


class LoginRequired(Exception):
    pass


@dataclass(frozen=True)
class Requester:
    email: str | None = None
    by_login: bool = False
    on_tailnet: bool = False


def nobody():
    return None


@dataclass(frozen=True)
class IdentifiesRequester:
    verifies: VerifiesAccessToken | None

    def __call__(self, host, headers, login=nobody, needs_login=True):
        if self.verifies is None:
            return Requester(email=None)
        if not self.is_on_the_tailnet(host, headers):
            return Requester(email=self.verifies(headers.get(ACCESS_TOKEN_HEADER)).email)
        if not needs_login:
            return Requester(email=None, on_tailnet=True)
        email = login()
        if email is None:
            raise LoginRequired()
        return Requester(email=email, by_login=True, on_tailnet=True)

    def is_on_the_tailnet(self, host, headers):
        named = self.verifies.access.tailnet_host
        if named is None or host is None or host.lower() != named.lower():
            return False
        return not any(edge in headers for edge in EDGE_HEADERS)
