from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DATA_ROOT = Path("data")
DATABASE_NAME = "sermon.sqlite3"


class Store:
    def __init__(self, connection):
        self._connection = connection

    def saves(self, entity):
        return entity

    def loads(self, entity_type, identity):
        return None

    def lists(self, entity_type, **criteria):
        return []

    def close(self):
        self._connection.close()


def opens_store(data_root=DEFAULT_DATA_ROOT):
    root = Path(data_root)
    root.mkdir(parents=True, exist_ok=True)
    return Store(sqlite3.connect(root / DATABASE_NAME))
