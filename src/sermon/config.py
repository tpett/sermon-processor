from __future__ import annotations

import os
import urllib.error
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

DATA_ROOT = "SERMON_DATA_ROOT"
OBJECT_STORE_ENDPOINT = "SERMON_OBJECT_STORE_ENDPOINT"
OBJECT_STORE_BUCKET = "SERMON_OBJECT_STORE_BUCKET"
OBJECT_STORE_ACCESS_KEY_ID = "SERMON_OBJECT_STORE_ACCESS_KEY_ID"
OBJECT_STORE_SECRET_ACCESS_KEY = "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY"
MODEL_ENDPOINT = "SERMON_MODEL_ENDPOINT"
WEBHOOK_TOKEN = "SERMON_WEBHOOK_TOKEN"
SECRET_KEY = "SERMON_SECRET_KEY"
SECRET_KEY_MINIMUM_LENGTH = 32
NOTIFICATION_CHANNEL = "SERMON_NOTIFICATION_CHANNEL"
SLACK_WEBHOOK_URL = "SERMON_SLACK_WEBHOOK_URL"
APP_URL = "SERMON_APP_URL"
ACCESS_TEAM_DOMAIN = "SERMON_ACCESS_TEAM_DOMAIN"
ACCESS_AUDIENCE = "SERMON_ACCESS_AUD"
TAILNET_HOST = "SERMON_TAILNET_HOST"
IN_APP = "in-app"
SLACK = "slack"
NOTIFICATION_CHANNELS = (IN_APP, SLACK)
SLACK_HOOK_HOST = "hooks.slack.com"

VARIABLES = (
    DATA_ROOT,
    OBJECT_STORE_ENDPOINT,
    OBJECT_STORE_BUCKET,
    OBJECT_STORE_ACCESS_KEY_ID,
    OBJECT_STORE_SECRET_ACCESS_KEY,
    MODEL_ENDPOINT,
)

HTTP_SCHEMES = ("http", "https")


class MissingConfiguration(ValueError):
    pass


class UnusableConfiguration(ValueError):
    pass


class ModelEndpointUnreachable(ConnectionError):
    def __init__(self, endpoint):
        super().__init__(f"the model endpoint {endpoint} did not answer")
        self.endpoint = endpoint


class Credential:
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def reveals(self):
        return self._value

    def __repr__(self):
        return f"{type(self).__name__}(redacted)"

    __str__ = __repr__

    def __eq__(self, other):
        return type(other) is type(self) and other.reveals() == self._value

    def __hash__(self):
        return hash((type(self), self._value))


def refuses_a_non_http_endpoint(name, endpoint):
    reached = urlparse(endpoint)
    if reached.scheme not in HTTP_SCHEMES or not reached.netloc:
        raise UnusableConfiguration(f"{name} is {endpoint!r}, which is not an HTTP endpoint")


def refuses_a_foreign_slack_webhook(webhook):
    if webhook is None:
        raise UnusableConfiguration(
            f"{NOTIFICATION_CHANNEL} is {SLACK!r} but nothing sets {SLACK_WEBHOOK_URL}"
        )
    refuses_a_bare_credential(SLACK_WEBHOOK_URL, webhook)
    if any(character.isspace() or not character.isprintable() for character in webhook.reveals()):
        raise UnusableConfiguration(
            f"{SLACK_WEBHOOK_URL} holds whitespace or control characters, so it is not a usable URL"
        )
    reached = urlparse(webhook.reveals())
    if reached.scheme != "https" or reached.netloc != SLACK_HOOK_HOST:
        raise UnusableConfiguration(
            f"{SLACK_WEBHOOK_URL} is not an https://{SLACK_HOOK_HOST}/ webhook"
        )


def refuses_a_bare_credential(name, credential):
    if not isinstance(credential, Credential):
        raise UnusableConfiguration(f"{name} is a {type(credential).__name__}, not a Credential")


@dataclass(frozen=True)
class ObjectStore:
    endpoint: str
    bucket: str
    access_key_id: Credential
    secret_access_key: Credential

    def __post_init__(self):
        refuses_a_non_http_endpoint(OBJECT_STORE_ENDPOINT, self.endpoint)
        refuses_a_bare_credential(OBJECT_STORE_ACCESS_KEY_ID, self.access_key_id)
        refuses_a_bare_credential(OBJECT_STORE_SECRET_ACCESS_KEY, self.secret_access_key)


def refuses_a_name_that_is_not_a_bare_host(name, value, example, labels_needed=1):
    labels = value.split(".")
    if len(labels) < labels_needed or not all(
        label.isascii()
        and label.replace("-", "").isalnum()
        and not label.startswith("-")
        and not label.endswith("-")
        for label in labels
    ):
        raise UnusableConfiguration(
            f"{name} is {value!r}, which is not a bare host name like {example}"
        )


@dataclass(frozen=True)
class CloudflareAccess:
    team_domain: str
    audience: str
    tailnet_host: str | None = None

    def __post_init__(self):
        refuses_a_name_that_is_not_a_bare_host(
            ACCESS_TEAM_DOMAIN, self.team_domain, "myteam.cloudflareaccess.com", labels_needed=2
        )
        if not self.audience.strip():
            raise UnusableConfiguration(f"{ACCESS_AUDIENCE} is empty")
        if self.tailnet_host is not None:
            refuses_a_name_that_is_not_a_bare_host(
                TAILNET_HOST, self.tailnet_host, "sermon-processor.home.example.me"
            )

    @property
    def issuer(self):
        return f"https://{self.team_domain}"

    @property
    def keys_url(self):
        return f"{self.issuer}/cdn-cgi/access/certs"


def reads_access(environment):
    team_domain = environment.get(ACCESS_TEAM_DOMAIN)
    audience = environment.get(ACCESS_AUDIENCE)
    if not team_domain and not audience:
        return None
    if not audience:
        raise UnusableConfiguration(
            f"{ACCESS_TEAM_DOMAIN} is set but nothing sets {ACCESS_AUDIENCE}; "
            f"set both to require Cloudflare Access, or neither"
        )
    if not team_domain:
        raise UnusableConfiguration(
            f"{ACCESS_AUDIENCE} is set but nothing sets {ACCESS_TEAM_DOMAIN}; "
            f"set both to require Cloudflare Access, or neither"
        )
    tailnet_host = environment.get(TAILNET_HOST)
    return CloudflareAccess(
        team_domain=team_domain,
        audience=audience,
        tailnet_host=tailnet_host.strip().lower() if tailnet_host and tailnet_host.strip() else None,
    )


@dataclass(frozen=True)
class Configuration:
    data_root: Path
    object_store: ObjectStore
    model_endpoint: str
    webhook_token: Credential | None = None
    notification_channel: str = IN_APP
    slack_webhook: Credential | None = None
    app_url: str | None = None
    access: CloudflareAccess | None = None
    secret_key: Credential | None = None

    def __post_init__(self):
        if not isinstance(self.data_root, Path):
            raise UnusableConfiguration(
                f"{DATA_ROOT} is a {type(self.data_root).__name__}, not a Path"
            )
        if not self.data_root.is_absolute():
            raise UnusableConfiguration(
                f"{DATA_ROOT} is {str(self.data_root)!r}, which moves with the working directory"
            )
        refuses_a_non_http_endpoint(MODEL_ENDPOINT, self.model_endpoint)
        if self.webhook_token is not None:
            refuses_a_bare_credential(WEBHOOK_TOKEN, self.webhook_token)
        if self.secret_key is not None:
            refuses_a_bare_credential(SECRET_KEY, self.secret_key)
            if len(self.secret_key.reveals()) < SECRET_KEY_MINIMUM_LENGTH:
                raise UnusableConfiguration(
                    f"{SECRET_KEY} is shorter than {SECRET_KEY_MINIMUM_LENGTH} characters, "
                    f"too short to sign a sign-in with"
                )
        if self.notification_channel not in NOTIFICATION_CHANNELS:
            raise UnusableConfiguration(
                f"{NOTIFICATION_CHANNEL} is {self.notification_channel!r}; no such channel is built; "
                f"the channels are {', '.join(repr(name) for name in NOTIFICATION_CHANNELS)}"
            )
        if self.notification_channel == SLACK:
            refuses_a_foreign_slack_webhook(self.slack_webhook)


@dataclass(frozen=True)
class ReadsConfiguration:
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ)

    def __call__(self):
        unset = [name for name in VARIABLES if not self.environment.get(name)]
        if unset:
            raise MissingConfiguration(f"nothing sets {', '.join(unset)}")
        offered = self.environment.get(WEBHOOK_TOKEN)
        return Configuration(
            data_root=Path(self.environment[DATA_ROOT]),
            object_store=ObjectStore(
                endpoint=self.environment[OBJECT_STORE_ENDPOINT],
                bucket=self.environment[OBJECT_STORE_BUCKET],
                access_key_id=Credential(self.environment[OBJECT_STORE_ACCESS_KEY_ID]),
                secret_access_key=Credential(self.environment[OBJECT_STORE_SECRET_ACCESS_KEY]),
            ),
            model_endpoint=self.environment[MODEL_ENDPOINT],
            webhook_token=Credential(offered) if offered else None,
            notification_channel=self.environment.get(NOTIFICATION_CHANNEL) or IN_APP,
            slack_webhook=Credential(hook) if (hook := self.environment.get(SLACK_WEBHOOK_URL)) else None,
            app_url=self.environment.get(APP_URL) or None,
            access=reads_access(self.environment),
            secret_key=Credential(secret) if (secret := self.environment.get(SECRET_KEY)) else None,
        )


@dataclass(frozen=True)
class ReachesModelEndpoint:
    endpoint: str
    over: Callable[[str], object]

    def __post_init__(self):
        refuses_a_non_http_endpoint(MODEL_ENDPOINT, self.endpoint)

    def __call__(self):
        try:
            return self.over(self.endpoint)
        except urllib.error.HTTPError:
            raise
        except OSError as unanswered:
            raise ModelEndpointUnreachable(self.endpoint) from unanswered
