from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.raises_notification import REVIEWER
from sermon.store import Artifact, LogEntry, Notification, Reviewer, Store

SEEN = "notification_seen"
STANDINGS = {
    "pending": "not delivered",
    "delivered": "delivered",
    "failed": "delivery failed",
    "suppressed": "suppressed, never sent",
}


def now():
    return datetime.now(UTC)


def correlates(notification):
    return f"notification:{notification.notification_id}"


@dataclass(frozen=True)
class NotificationView:
    notification_id: int
    kind: str
    summary: str
    raised_at: str
    state: str
    standing: str
    unread: bool
    links: tuple


@dataclass(frozen=True)
class NotificationsPage:
    notifications: tuple
    unread: int
    receives_notifications: bool


def links_of(store, notification):
    if notification.recording_id is None:
        return ()
    if notification.segment_id is None:
        return ((f"/recordings/{notification.recording_id}", "Open the recording"),)
    links = [
        (f"/recordings/{notification.recording_id}?segment={notification.segment_id}", "Open the Segment"),
    ]
    for artifact in store.lists(Artifact, segment_id=notification.segment_id, kind="rendered_mp3"):
        if artifact.superseded_by is not None:
            continue
        links.append((f"/api/artifacts/{artifact.path}", "Download the MP3"))
    return tuple(links)


@dataclass(frozen=True)
class ListsNotifications:
    """The reviewer's notifications, newest first, and how many are unread."""

    store: Store

    def __call__(self):
        seen = {entry.correlation_id for entry in self.store.lists(LogEntry) if entry.kind == SEEN}
        raised = sorted(
            (item for item in self.store.lists(Notification) if item.recipient == REVIEWER),
            key=lambda item: (item.created_at, item.notification_id),
            reverse=True,
        )
        views = tuple(
            NotificationView(
                notification_id=item.notification_id,
                kind=item.kind,
                summary=item.summary,
                raised_at=item.created_at.strftime("%Y-%m-%d %I:%M %p"),
                state=item.state,
                standing=STANDINGS.get(item.state, item.state),
                unread=self._unread(item, seen),
                links=links_of(self.store, item),
            )
            for item in raised
        )
        reviewer = self.store.loads(Reviewer, REVIEWER)
        return NotificationsPage(
            notifications=views,
            unread=sum(1 for view in views if view.unread),
            receives_notifications=reviewer is None or reviewer.receives_notifications,
        )

    def _unread(self, notification, seen):
        if notification.state == "suppressed" or notification.recording_id is None:
            return False
        return correlates(notification) not in seen


@dataclass(frozen=True)
class MarksNotificationsSeen:
    store: Store
    clock: object = now

    def __call__(self, page, *, actor=REVIEWER):
        for view in page.notifications:
            if not view.unread:
                continue
            notification = self.store.loads(Notification, view.notification_id)
            self.store.saves(
                LogEntry(
                    recording_id=notification.recording_id,
                    segment_id=notification.segment_id,
                    kind=SEEN,
                    occurred_at=self.clock(),
                    correlation_id=correlates(notification),
                    actor=actor,
                )
            )


@dataclass(frozen=True)
class SetsNotificationPreference:
    store: Store

    def __call__(self, receives):
        reviewer = self.store.loads(Reviewer, REVIEWER) or Reviewer(actor=REVIEWER)
        return self.store.saves(replace(reviewer, receives_notifications=receives))
