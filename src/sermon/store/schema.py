from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from . import vocabularies
from .entities import (
    Artifact,
    Block,
    Candidate,
    ChannelLevel,
    Discovery,
    Evidence,
    Job,
    LogEntry,
    Notification,
    Proposal,
    Recording,
    Segment,
    SkippedObject,
    SpeakerMatch,
    SpeakerProfile,
)

COLUMN_TYPES = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
    bytes: "BLOB",
    dict: "TEXT",
    date: "TEXT",
    datetime: "TEXT",
}


class UnsupportedAnnotation(TypeError):
    pass


def unwrapped(annotation):
    arguments = get_args(annotation)
    if not arguments:
        return (annotation, False)
    admitted = [argument for argument in arguments if argument is not type(None)]
    if get_origin(annotation) in (Union, UnionType) and len(admitted) == 1:
        return (admitted[0], True)
    raise UnsupportedAnnotation(annotation)


def column_type(kind):
    if kind not in COLUMN_TYPES:
        raise UnsupportedAnnotation(kind)
    return COLUMN_TYPES[kind]


@dataclass(frozen=True)
class Uniqueness:
    column: str
    only_while: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Presence:
    column: str
    requires: tuple[str, ...] = ()
    only_while: dict[str, tuple[str | int, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Collection:
    field: str
    table: str
    owner: str
    element: type
    column: str | None = None
    references: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Table:
    entity: type
    name: str
    identity: str
    generated: bool = True
    order: tuple[str, ...] = ()
    unique: tuple[Uniqueness, ...] = ()
    presence: tuple[Presence, ...] = ()
    paths: tuple[str, ...] = ()
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
            paths=("local_path",),
            closed={
                "state": vocabularies.RECORDING_STATES,
                "kind": vocabularies.RECORDING_KINDS,
            },
            collections=(
                Collection(
                    field="channel_levels",
                    table="recording_channel_level",
                    owner="recording_id",
                    element=ChannelLevel,
                ),
            ),
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
                    field="speaker_matches",
                    table="block_speaker_match",
                    owner="block_id",
                    element=SpeakerMatch,
                    references={"speaker_profile_id": "speaker_profile(speaker_profile_id)"},
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
                    references={"recording_id": "recording(recording_id)"},
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
                "confirmed_speaker_profile_id": "speaker_profile(speaker_profile_id)",
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
            identity="proposal_id",
            references={
                "segment_id": "segment(segment_id)",
                "superseded_by": "proposal(proposal_id)",
            },
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
                    owner="proposal_id",
                    element=Evidence,
                ),
                Collection(
                    field="missing_evidence",
                    table="proposal_missing_evidence",
                    owner="proposal_id",
                    element=str,
                    column="description",
                ),
                Collection(
                    field="punch_in_candidates",
                    table="proposal_punch_in_candidate",
                    owner="proposal_id",
                    element=Candidate,
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
            paths=("path",),
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
        Table(
            entity=Notification,
            name="notification",
            identity="notification_id",
            order=("created_at",),
            references={
                "recording_id": "recording(recording_id)",
                "segment_id": "segment(segment_id)",
            },
            presence=(Presence(column="segment_id", requires=("recording_id",)),),
            closed={"state": vocabularies.NOTIFICATION_STATES},
        ),
        Table(
            entity=SkippedObject,
            name="skipped_object",
            identity="object_key",
            generated=False,
            closed={"reason": vocabularies.SKIP_REASONS},
        ),
        Table(
            entity=Discovery,
            name="discovery",
            identity="discovery_id",
            order=("occurred_at",),
            closed={
                "kind": vocabularies.DISCOVERY_KINDS,
                "failure": vocabularies.DISCOVERY_FAILURES,
            },
        ),
        Table(
            entity=LogEntry,
            name="log_entry",
            identity="log_entry_id",
            order=("occurred_at",),
            references={
                "recording_id": "recording(recording_id)",
                "segment_id": "segment(segment_id)",
                "job_id": "job(job_id)",
                "proposal_id": "proposal(proposal_id)",
                "artifact_id": "artifact(artifact_id)",
            },
            closed={
                "entered_state": vocabularies.LOGGED_STATES,
                "boundary_source": vocabularies.BOUNDARY_SOURCES,
            },
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
    return (*table.order, table.identity)


def listed(values):
    return ", ".join(f"'{value}'" if isinstance(value, str) else str(value) for value in values)


def column_definition(table, name, annotation):
    kind, optional = unwrapped(annotation)
    parts = [name, column_type(kind)]
    if name == table.identity:
        parts.append("PRIMARY KEY" if table.generated else "NOT NULL PRIMARY KEY")
    elif not optional:
        parts.append("NOT NULL")
    if kind is bool:
        parts.append(f"CHECK ({name} IN (0, 1))")
    if name in table.closed:
        parts.append(f"CHECK ({name} IN ({listed(table.closed[name])}))")
    if name in table.references:
        parts.append(f"REFERENCES {table.references[name]}")
    return " ".join(parts)


def table_ddl(table):
    annotations = get_type_hints(table.entity)
    definitions = [
        column_definition(table, name, annotations[name]) for name in column_names(table)
    ]
    definitions += [presence_check(one) for one in table.presence]
    return creates(table.name, definitions)


def presence_check(presence):
    conditions = [f"{name} IS NOT NULL" for name in presence.requires]
    conditions += [
        f"{column} IN ({listed(values)})" for column, values in presence.only_while.items()
    ]
    return f"CHECK ({presence.column} IS NULL OR ({' AND '.join(conditions)}))"


def unique_ddl(table, unique):
    conditions = " AND ".join(
        f"{column} IN ({listed(values)})" for column, values in unique.only_while.items()
    )
    scope = f" WHERE {conditions}" if conditions else ""
    return (
        f"CREATE UNIQUE INDEX IF NOT EXISTS unique_{table.name}_{unique.column} "
        f"ON {table.name} ({unique.column}){scope}"
    )


def element_definition(collection, name, annotation):
    kind, optional = unwrapped(annotation)
    parts = [name, column_type(kind)]
    if not optional:
        parts.append("NOT NULL")
    if name in collection.references:
        parts.append(f"REFERENCES {collection.references[name]}")
    return " ".join(parts)


def element_definitions(collection):
    if collection.column:
        return [element_definition(collection, collection.column, collection.element)]
    annotations = get_type_hints(collection.element)
    return [
        element_definition(collection, name, annotations[name])
        for name in element_columns(collection)
    ]


def collection_ddl(table, collection):
    owner_type = column_type(unwrapped(get_type_hints(table.entity)[table.identity])[0])
    definitions = [
        f"{collection.owner} {owner_type} NOT NULL REFERENCES {table.name}({table.identity})",
        "position INTEGER NOT NULL",
        *element_definitions(collection),
        f"PRIMARY KEY ({collection.owner}, position)",
    ]
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
