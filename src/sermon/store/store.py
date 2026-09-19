from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import get_type_hints

from .schema import TABLES, column_names, element_columns, order_by, schema_statements, unwrapped
from .stored_paths import ResolvesStoredPath

DATABASE_NAME = "sermon.sqlite3"


class UnstorableValue(TypeError):
    pass


def to_column(annotation, value):
    if value is None:
        return None
    kind, _ = unwrapped(annotation)
    if type(value) is not kind:
        raise UnstorableValue(f"{type(value).__name__} where {kind.__name__} is declared")
    if kind is bool:
        return int(value)
    if kind is datetime:
        return in_utc(value).isoformat()
    if kind is date:
        return value.isoformat()
    if kind is dict:
        return json.dumps(value, sort_keys=True)
    return value


def in_utc(moment):
    if moment.tzinfo is None:
        raise UnstorableValue("naive datetime, which no stored moment can be ordered against")
    return moment.astimezone(UTC)


def from_column(annotation, value):
    if value is None:
        return None
    kind, _ = unwrapped(annotation)
    if kind is bool:
        return bool(value)
    if kind is datetime:
        return datetime.fromisoformat(value)
    if kind is date:
        return date.fromisoformat(value)
    if kind is dict:
        return json.loads(value)
    return value


class Store:
    def __init__(self, connection, resolves_stored_path):
        self._connection = connection
        self._resolves_stored_path = resolves_stored_path

    def resolves(self, entity):
        table = TABLES[type(entity)]
        if len(table.paths) != 1:
            raise ValueError(f"{table.entity.__name__} holds no single path")
        stored = getattr(entity, table.paths[0])
        return self._resolves_stored_path(stored) if stored is not None else None

    def close(self):
        self._connection.close()

    def saves(self, entity):
        table = TABLES[type(entity)]
        self._guards_paths(table, entity)
        columns = column_names(table)
        annotations = get_type_hints(table.entity)
        assignments = ", ".join(
            f"{name} = excluded.{name}" for name in columns if name != table.identity
        )
        with self._connection:
            cursor = self._connection.execute(
                f"INSERT INTO {table.name} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' * len(columns))}) "
                f"ON CONFLICT({table.identity}) DO UPDATE SET {assignments}",
                [to_column(annotations[name], getattr(entity, name)) for name in columns],
            )
            identity = getattr(entity, table.identity)
            if identity is None:
                identity = cursor.lastrowid
            for collection in table.collections:
                self._writes(collection, identity, getattr(entity, collection.field))
        return replace(entity, **{table.identity: identity})

    def loads(self, entity_type, identity):
        table = TABLES[entity_type]
        annotations = get_type_hints(table.entity)
        row = self._connection.execute(
            f"SELECT * FROM {table.name} WHERE {table.identity} = ?",
            (to_column(annotations[table.identity], identity),),
        ).fetchone()
        return self._entity(table, row) if row is not None else None

    def lists(self, entity_type, **criteria):
        table = TABLES[entity_type]
        unknown = sorted(set(criteria) - set(column_names(table)))
        if unknown:
            raise ValueError(f"{table.entity.__name__} holds no {', '.join(unknown)}")
        annotations = get_type_hints(table.entity)
        matching = " AND ".join(f"{name} IS ?" for name in criteria)
        rows = self._connection.execute(
            f"SELECT * FROM {table.name}{f' WHERE {matching}' if criteria else ''} "
            f"ORDER BY {', '.join(order_by(table))}",
            [to_column(annotations[name], value) for name, value in criteria.items()],
        ).fetchall()
        return [self._entity(table, row) for row in rows]

    def _guards_paths(self, table, entity):
        for name in table.paths:
            stored = getattr(entity, name)
            if stored is not None:
                self._resolves_stored_path(stored)

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
        return (to_column(collection.element, element),)
    annotations = get_type_hints(collection.element)
    return tuple(
        to_column(annotations[name], getattr(element, name)) for name in element_columns(collection)
    )


def creates_schema(connection):
    with connection:
        connection.execute("BEGIN")
        for statement in schema_statements():
            connection.execute(statement)


def opens_store(data_root):
    root = Path(data_root)
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    creates_schema(connection)
    return Store(connection, ResolvesStoredPath(data_root=root))
