from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import get_type_hints

from .artifact_paths import DEFAULT_DATA_ROOT, ResolvesArtifactPath
from .schema import TABLES, column_names, element_columns, order_by, schema_sql, unwrapped

DATABASE_NAME = "sermon.sqlite3"


def to_column(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def from_column(annotation, value):
    if value is None:
        return None
    kind, _ = unwrapped(annotation)
    if kind is bool:
        return bool(value)
    if kind is datetime:
        return datetime.fromisoformat(value)
    if kind is dict:
        return json.loads(value)
    return value


class Store:
    def __init__(self, connection, resolves_artifact_path=ResolvesArtifactPath()):
        self._connection = connection
        self._resolves_artifact_path = resolves_artifact_path

    def resolves(self, artifact):
        return None

    def close(self):
        self._connection.close()

    def saves(self, entity):
        table = TABLES[type(entity)]
        columns = column_names(table)
        assignments = ", ".join(
            f"{name} = excluded.{name}" for name in columns if name != table.identity
        )
        cursor = self._connection.execute(
            f"INSERT INTO {table.name} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))}) "
            f"ON CONFLICT({table.identity}) DO UPDATE SET {assignments}",
            [to_column(getattr(entity, name)) for name in columns],
        )
        identity = getattr(entity, table.identity)
        if identity is None:
            identity = cursor.lastrowid
        for collection in table.collections:
            self._writes(collection, identity, getattr(entity, collection.field))
        self._connection.commit()
        return replace(entity, **{table.identity: identity})

    def loads(self, entity_type, identity):
        table = TABLES[entity_type]
        row = self._connection.execute(
            f"SELECT * FROM {table.name} WHERE {table.identity} = ?", (to_column(identity),)
        ).fetchone()
        return self._entity(table, row) if row is not None else None

    def lists(self, entity_type, **criteria):
        table = TABLES[entity_type]
        unknown = sorted(set(criteria) - set(column_names(table)))
        if unknown:
            raise ValueError(f"{table.entity.__name__} holds no {', '.join(unknown)}")
        matching = " AND ".join(f"{name} IS ?" for name in criteria)
        rows = self._connection.execute(
            f"SELECT * FROM {table.name}{f' WHERE {matching}' if criteria else ''} "
            f"ORDER BY {', '.join(order_by(table))}",
            [to_column(value) for value in criteria.values()],
        ).fetchall()
        return [self._entity(table, row) for row in rows]

    def _entity(self, table, row):
        annotations = get_type_hints(table.entity)
        values = {name: from_column(annotations[name], row[name]) for name in column_names(table)}
        for collection in table.collections:
            values[collection.field] = self._reads(collection, row[table.identity])
        return table.entity(**values)

    def _writes(self, collection, identity, elements):
        columns = element_columns(collection)
        self._connection.execute(
            f"DELETE FROM {collection.table} WHERE {collection.owner} = ?", (identity,)
        )
        self._connection.executemany(
            f"INSERT INTO {collection.table} "
            f"({collection.owner}, position, {', '.join(columns)}) "
            f"VALUES ({', '.join('?' * (len(columns) + 2))})",
            [
                (identity, position, *values_of(collection, element))
                for position, element in enumerate(elements)
            ],
        )

    def _reads(self, collection, identity):
        columns = element_columns(collection)
        rows = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM {collection.table} "
            f"WHERE {collection.owner} = ? ORDER BY position",
            (identity,),
        ).fetchall()
        if collection.column:
            return tuple(row[0] for row in rows)
        annotations = get_type_hints(collection.element)
        return tuple(
            collection.element(
                **{name: from_column(annotations[name], row[name]) for name in columns}
            )
            for row in rows
        )


def values_of(collection, element):
    if collection.column:
        return (to_column(element),)
    return tuple(to_column(getattr(element, name)) for name in element_columns(collection))


def opens_store(data_root=DEFAULT_DATA_ROOT):
    root = Path(data_root)
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    connection.executescript(schema_sql())
    connection.execute("PRAGMA foreign_keys = ON")
    return Store(connection, ResolvesArtifactPath(data_root=root))
