from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

NAMES = Path(__file__).with_name("names.toml")


class GlossaryUnreadable(ValueError):
    pass


@dataclass(frozen=True)
class Glossary:
    """Acronyms the church uses, and the names they stand for."""

    names: dict[str, str] = field(default_factory=dict)

    def spells_out(self, text):
        for acronym, name in self.names.items():
            text = re.sub(rf"(?<![\w-]){re.escape(acronym)}(?![\w])", name, text)
        return text

    def abbreviates(self, text):
        for acronym, name in sorted(self.names.items(), key=lambda item: -len(item[1])):
            text = re.sub(rf"\b{re.escape(name)}\b", acronym, text, flags=re.IGNORECASE)
        return text


@dataclass(frozen=True)
class ReadsGlossary:
    path: Path = NAMES

    def __call__(self):
        try:
            read = tomllib.loads(Path(self.path).read_text())
        except (OSError, tomllib.TOMLDecodeError) as unreadable:
            raise GlossaryUnreadable(f"{self.path}: {unreadable}") from unreadable
        refused = sorted(key for key, value in read.items() if not isinstance(value, str))
        if refused:
            raise GlossaryUnreadable(f"{self.path}: {', '.join(refused)} is not a name")
        return Glossary(names={acronym.strip(): name.strip() for acronym, name in read.items()})
