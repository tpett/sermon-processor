from __future__ import annotations

from dataclasses import dataclass

from sermon.verifies_access_token import VerifiesAccessToken

ACCESS_TOKEN_HEADER = "Cf-Access-Jwt-Assertion"
EDGE_HEADERS = ("Cf-Ray", "Cf-Connecting-Ip")


@dataclass(frozen=True)
class Requester:
    email: str | None = None


@dataclass(frozen=True)
class IdentifiesRequester:
    verifies: VerifiesAccessToken | None

    def __call__(self, host, headers):
        if self.verifies is None or self.is_on_the_tailnet(host, headers):
            return Requester(email=None)
        return Requester(email=self.verifies(headers.get(ACCESS_TOKEN_HEADER)).email)

    def is_on_the_tailnet(self, host, headers):
        named = self.verifies.access.tailnet_host
        if named is None or host is None or host.lower() != named.lower():
            return False
        return not any(edge in headers for edge in EDGE_HEADERS)
