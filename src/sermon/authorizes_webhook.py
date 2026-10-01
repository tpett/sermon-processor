from __future__ import annotations

import hmac
from dataclasses import dataclass

from sermon.config import WEBHOOK_TOKEN, Credential, refuses_a_bare_credential

SCHEME = "bearer"
ALLOWED = (None, None)
UNAUTHENTICATED = "the webhook requires a bearer token"
UNCONFIGURED = f"nothing sets {WEBHOOK_TOKEN}"


@dataclass(frozen=True)
class AuthorizesWebhook:
    token: Credential | None = None

    def __post_init__(self):
        if self.token is not None:
            refuses_a_bare_credential(WEBHOOK_TOKEN, self.token)

    def __call__(self, presented):
        if self.token is None:
            return 503, UNCONFIGURED
        scheme, separator, offered = (presented or "").partition(" ")
        if not separator or scheme.lower() != SCHEME:
            return 401, UNAUTHENTICATED
        if not hmac.compare_digest(offered.encode(), self.token.reveals().encode()):
            return 401, UNAUTHENTICATED
        return ALLOWED
