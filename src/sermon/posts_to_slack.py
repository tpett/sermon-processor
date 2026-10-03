from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

TIMEOUT_SECONDS = 10


class SlackRefused(RuntimeError):
    pass


def opens(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class PostsToSlack:
    """Posts a Notification's summary to a Slack incoming webhook; the webhook is the credential."""

    webhook: object
    opens: object = field(default=opens, repr=False)
    links_to: str | None = None

    def __call__(self, notification):
        request = urllib.request.Request(
            self.webhook.reveals(),
            data=json.dumps({"text": self._text(notification)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opens(request, timeout=TIMEOUT_SECONDS) as answer:
                status = getattr(answer, "status", 200)
                body = answer.read()
        except urllib.error.HTTPError as refused:
            raise SlackRefused(f"Slack answered {refused.code}") from None
        except (urllib.error.URLError, OSError) as unreachable:
            raise SlackRefused(f"Slack could not be reached ({type(unreachable).__name__})") from None
        if status != 200 or body.strip() != b"ok":
            raise SlackRefused(f"Slack answered {status}: {body[:80].decode(errors='replace')}")

    def _text(self, notification):
        if self.links_to and notification.recording_id:
            base = self.links_to.rstrip("/")
            return (
                f"{notification.summary}\n"
                f"<{base}/recordings/{notification.recording_id}|Open the recording>"
            )
        return notification.summary
