from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from sermon.store import Artifact, Store


def names_rendered_mp3(published_on, label=None):
    day = published_on.isoformat() if hasattr(published_on, "isoformat") else str(published_on)
    if not label:
        return f"{day}.mp3"
    cleaned = label.replace(":", ".").replace("/", " - ").replace('"', "")
    return f"{day} - {' '.join(cleaned.split())}.mp3"


class FilenameCollision(ValueError):
    pass


@dataclass(frozen=True)
class PublicationForm:
    date: date
    label: str

    def fields(self):
        return {"Date": self.date.isoformat(), "Label": self.label}


@dataclass(frozen=True)
class RecordsPublicationDetails:
    store: Store

    def opens(self, segment, recording):
        return PublicationForm(
            date=segment.publication_date or recording.started_at.date(),
            label=segment.label or "",
        )

    def saves(self, segment, *, publication_date, label, replace_existing=False):
        path = names_rendered_mp3(publication_date, label)
        existing = [
            item
            for item in self.store.lists(Artifact, kind="rendered_mp3")
            if item.path == path and item.segment_id != segment.segment_id
        ]
        if existing and not replace_existing:
            self.store._filename_collision = path
            raise FilenameCollision(path)
        return self.store.saves(
            replace(segment, publication_date=publication_date, label=label)
        )
