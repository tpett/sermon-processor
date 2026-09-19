from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import get_args, get_type_hints

from . import vocabularies
from .entities import Artifact, Block, Evidence, Job, Proposal, Recording, Segment, SpeakerProfile

COLUMN_TYPES = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
    bytes: "BLOB",
    dict: "TEXT",
    datetime: "TEXT",
}


def unwrapped(annotation):
    arguments = [argument for argument in get_args(annotation) if argument is not type(None)]
    return (arguments[0], True) if arguments else (annotation, False)


@dataclass(frozen=True)
class Uniqueness:
    column: str
    only_while: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Collection:
    field: str
    table: str
    owner: str
    element: type
    column: str | None = None
    references: str | None = None


@dataclass(frozen=True)
class Table:
    entity: type
    name: str
    identity: str
    generated: bool = True
    order: tuple[str, ...] = ()
    unique: tuple[Uniqueness, ...] = ()
    references: dict[str, str] = field(default_factory=dict)
    closed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    collections: tuple[Collection, ...] = ()


TABLES = {
    table.entity: table
    for table in (
        Table(
            entity=Recording,
            name="recording",
            identity="recording_id",
            generated=False,
            order=("started_at",),
            unique=(Uniqueness(column="object_key"),),
            closed={
                "state": vocabularies.RECORDING_STATES,
                "kind": vocabularies.RECORDING_KINDS,
            },
        ),
        Table(
            entity=Block,
            name="block",
            identity="block_id",
            order=("start_seconds",),
            references={"recording_id": "recording(recording_id)"},
            closed={
                "type": vocabularies.BLOCK_TYPES,
                "classification_confidence": vocabularies.CONFIDENCE_LEVELS,
            },
            collections=(
                Collection(
                    field="evidence",
                    table="block_evidence",
                    owner="block_id",
                    element=Evidence,
                ),
                Collection(
                    field="speaker_profile_ids",
                    table="block_speaker_profile",
                    owner="block_id",
                    element=int,
                    column="speaker_profile_id",
                    references="speaker_profile(speaker_profile_id)",
                ),
            ),
        ),
        Table(
            entity=SpeakerProfile,
            name="speaker_profile",
            identity="speaker_profile_id",
            collections=(
                Collection(
                    field="enrolled_from",
                    table="speaker_profile_enrolment",
                    owner="speaker_profile_id",
                    element=str,
                    column="recording_id",
                    references="recording(recording_id)",
                ),
            ),
        ),
        Table(
            entity=Segment,
            name="segment",
            identity="segment_id",
            order=("punch_in_seconds",),
            references={
                "recording_id": "recording(recording_id)",
                "seed_block_id": "block(block_id)",
            },
            closed={
                "classification": vocabularies.SEGMENT_CLASSIFICATIONS,
                "state": vocabularies.SEGMENT_STATES,
                "intent": vocabularies.SEGMENT_INTENTS,
                "boundary_source": vocabularies.BOUNDARY_SOURCES,
            },
        ),
        Table(
            entity=Proposal,
            name="proposal",
            identity="segment_id",
            generated=False,
            references={"segment_id": "segment(segment_id)"},
            closed={
                "classification_confidence": vocabularies.CONFIDENCE_LEVELS,
                "boundary_confidence": vocabularies.CONFIDENCE_LEVELS,
                "punch_in_difficulty": vocabularies.CUT_DIFFICULTIES,
                "punch_out_difficulty": vocabularies.CUT_DIFFICULTIES,
            },
            collections=(
                Collection(
                    field="evidence",
                    table="proposal_evidence",
                    owner="segment_id",
                    element=Evidence,
                ),
                Collection(
                    field="missing_evidence",
                    table="proposal_missing_evidence",
                    owner="segment_id",
                    element=str,
                    column="description",
                ),
            ),
        ),
        Table(
            entity=Artifact,
            name="artifact",
            identity="artifact_id",
            references={
                "recording_id": "recording(recording_id)",
                "segment_id": "segment(segment_id)",
                "superseded_by": "artifact(artifact_id)",
            },
            closed={"kind": vocabularies.ARTIFACT_KINDS},
        ),
        Table(
            entity=Job,
            name="job",
            identity="job_id",
            order=("queued_at",),
            unique=(
                Uniqueness(
                    column="dedupe_key",
                    only_while={"state": vocabularies.JOB_STATES_IN_FLIGHT},
                ),
            ),
            references={
                "recording_id": "recording(recording_id)",
                "segment_id": "segment(segment_id)",
            },
            closed={"kind": vocabularies.JOB_KINDS, "state": vocabularies.JOB_STATES},
        ),
    )
}


def column_names(table):
    collected = {collection.field for collection in table.collections}
    return tuple(one.name for one in fields(table.entity) if one.name not in collected)


def element_columns(collection):
    if collection.column:
        return (collection.column,)
    return tuple(one.name for one in fields(collection.element))


def order_by(table):
    return table.order or (table.identity,)


def quoted(values):
    return ", ".join(f"'{value}'" for value in values)


def column_definition(table, name, annotation):
    kind, optional = unwrapped(annotation)
    parts = [name, COLUMN_TYPES[kind]]
    if name == table.identity:
        parts.append("PRIMARY KEY" if table.generated else "NOT NULL PRIMARY KEY")
    elif not optional:
        parts.append("NOT NULL")
    if kind is bool:
        parts.append(f"CHECK ({name} IN (0, 1))")
    if name in table.closed:
        parts.append(f"CHECK ({name} IN ({quoted(table.closed[name])}))")
    if name in table.references:
        parts.append(f"REFERENCES {table.references[name]}")
    return " ".join(parts)


def table_ddl(table):
    annotations = get_type_hints(table.entity)
    definitions = [
        column_definition(table, name, annotations[name]) for name in column_names(table)
    ]
    return creates(table.name, definitions)


def unique_ddl(table, unique):
    conditions = " AND ".join(
        f"{column} IN ({quoted(values)})" for column, values in unique.only_while.items()
    )
    return (
        f"CREATE UNIQUE INDEX IF NOT EXISTS unique_{table.name}_{unique.column} "
        f"ON {table.name} ({unique.column})"
        f"{f' WHERE {conditions}' if conditions else ''}"
    )


def collection_ddl(table, collection):
    owner_type = COLUMN_TYPES[unwrapped(get_type_hints(table.entity)[table.identity])[0]]
    definitions = [
        f"{collection.owner} {owner_type} NOT NULL REFERENCES {table.name}({table.identity})",
        "position INTEGER NOT NULL",
    ]
    if collection.column:
        reference = f" REFERENCES {collection.references}" if collection.references else ""
        definitions.append(
            f"{collection.column} {COLUMN_TYPES[collection.element]} NOT NULL{reference}"
        )
    else:
        annotations = get_type_hints(collection.element)
        definitions += [
            f"{name} {COLUMN_TYPES[unwrapped(annotations[name])[0]]} NOT NULL"
            for name in element_columns(collection)
        ]
    definitions.append(f"PRIMARY KEY ({collection.owner}, position)")
    return creates(collection.table, definitions)


def creates(name, definitions):
    body = ",\n    ".join(definitions)
    return f"CREATE TABLE IF NOT EXISTS {name} (\n    {body}\n)"


def schema_statements():
    statements = []
    for table in TABLES.values():
        statements.append(table_ddl(table))
        statements += [unique_ddl(table, unique) for unique in table.unique]
        statements += [collection_ddl(table, collection) for collection in table.collections]
    return tuple(statements)
