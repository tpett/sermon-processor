from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from sermon.config import Credential

SECRET_FILE = "session_secret"
OWNER_ONLY = 0o600


@dataclass(frozen=True)
class KeepsSessionSecret:
    data_root: Path
    named: Credential | None

    def __call__(self):
        if self.named is not None:
            return self.named.reveals()
        kept = Path(self.data_root) / SECRET_FILE
        found = self.reads(kept)
        if found:
            return found
        return self.makes(kept)

    def reads(self, kept):
        try:
            found = kept.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        if found:
            os.chmod(kept, OWNER_ONLY)
        return found

    def makes(self, kept):
        made = secrets.token_hex(32)
        kept.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(kept, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, OWNER_ONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as written:
            written.write(made)
        os.chmod(kept, OWNER_ONLY)
        return made
