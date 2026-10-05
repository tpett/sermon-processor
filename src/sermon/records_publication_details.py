from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Artifact, Recording, Store, layout


def places_publication_date(segment, recording):
    return segment.publication_date or recording.started_at.date()


def names_output(recording, label=None):
    return names_rendered_mp3(recording.started_at.date(), label)


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
    label: str

    def fields(self):
        return {"Label": self.label}


@dataclass(frozen=True)
class RecordsPublicationDetails:
    store: Store

    def opens(self, segment, recording):
        return PublicationForm(label=segment.label or "")

    def saves(self, segment, *, publication_date, label, replace_existing=False):
        recording = self.store.loads(Recording, segment.recording_id)
        path = layout.published_path(names_output(recording, label))
        existing = [
            item
            for item in self.store.lists(Artifact, kind="rendered_mp3")
            if item.path == path
            and item.segment_id != segment.segment_id
            and item.superseded_by is None
        ]
        if existing and not replace_existing:
            raise FilenameCollision(path)
        return self.store.saves(
            replace(segment, publication_date=publication_date, label=label)
        )
