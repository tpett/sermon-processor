from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from sermon.store import Store


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

    def saves(self, segment, *, publication_date, label):
        return self.store.saves(
            replace(segment, publication_date=publication_date, label=label)
        )
