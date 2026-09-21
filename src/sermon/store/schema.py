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
    CorpusPair,
    Discovery,
    Evidence,
    Job,
    LogEntry,
    Notification,
    Proposal,
    Recording,
    Reviewer,
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
    column: str | tuple[str, ...]
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
    distinct: bool = False
    references: dict[str, str] = field(default_factory=dict)
    closed: dict[str, tuple[str, ...]] = field(default_factory=dict)


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
                "started_at_source": vocabularies.STARTED_AT_SOURCES,
                "kind": vocabularies.RECORDING_KINDS,
            },
            collections=(
                Collection(
                    field="channel_levels",
                    table="recording_channel_level",
                    owner="recording_id",
                    element=ChannelLevel,
                ),
                Collection(
                    field="warnings",
                    table="recording_warning",
                    owner="recording_id",
                    element=str,
                    column="warning",
                    distinct=True,
                    closed={"warning": vocabularies.RECORDING_WARNINGS},
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
                    element=int,
                    column="segment_id",
                    references={"segment_id": "segment(segment_id)"},
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
            collections=(
                Collection(
                    field="warnings",
                    table="segment_warning",
                    owner="segment_id",
                    element=str,
                    column="warning",
                    distinct=True,
                    closed={"warning": vocabularies.SEGMENT_WARNINGS},
                ),
            ),
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
                "punch_in_grade": vocabularies.CUT_DIFFICULTIES,
                "punch_out_grade": vocabularies.CUT_DIFFICULTIES,
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
            entity=Reviewer,
            name="reviewer",
            identity="actor",
            generated=False,
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
            presence=(
                Presence(
                    column="failure",
                    only_while={"kind": ("scan",), "discovered_count": (0,)},
                ),
                Presence(column="event", only_while={"kind": ("webhook",)}),
            ),
            closed={
                "kind": vocabularies.DISCOVERY_KINDS,
                "failure": vocabularies.DISCOVERY_FAILURES,
            },
        ),
        Table(
            entity=CorpusPair,
            name="corpus_pair",
            identity="corpus_pair_id",
            order=("punch_in_seconds",),
            unique=(
                Uniqueness(column=("recording_id", "classification", "provenance")),
            ),
            references={"recording_id": "recording(recording_id)"},
            presence=(
                Presence(column="alignment", only_while={"provenance": ("human",)}),
                Presence(
                    column="punch_in_seconds",
                    only_while={"provenance": ("human",), "alignment": ("aligned",)},
                ),
                Presence(
                    column="punch_out_seconds",
                    requires=("punch_in_seconds",),
                    only_while={"provenance": ("human",), "alignment": ("aligned",)},
                ),
                Presence(
                    column="drift_ppm",
                    requires=("punch_in_seconds", "punch_out_seconds"),
                    only_while={"alignment": ("aligned",)},
                ),
                Presence(
                    column="punch_in_difficulty",
                    requires=("punch_in_seconds",),
                    only_while={"provenance": ("human",), "alignment": ("aligned",)},
                ),
                Presence(
                    column="punch_out_difficulty",
                    requires=("punch_out_seconds",),
                    only_while={"provenance": ("human",), "alignment": ("aligned",)},
                ),
            ),
            closed={
                "classification": vocabularies.SEGMENT_CLASSIFICATIONS,
                "alignment": vocabularies.CORPUS_ALIGNMENTS,
                "punch_in_difficulty": vocabularies.CUT_DIFFICULTIES,
                "punch_out_difficulty": vocabularies.CUT_DIFFICULTIES,
                "provenance": vocabularies.CORPUS_PROVENANCES,
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


def unique_columns(unique):
    if isinstance(unique.column, tuple):
        return unique.column
    return (unique.column,)


def unique_ddl(table, unique):
    columns = unique_columns(unique)
    conditions = " AND ".join(
        f"{column} IN ({listed(values)})" for column, values in unique.only_while.items()
    )
    scope = f" WHERE {conditions}" if conditions else ""
    return (
        f"CREATE UNIQUE INDEX IF NOT EXISTS unique_{table.name}_{'_'.join(columns)} "
        f"ON {table.name} ({', '.join(columns)}){scope}"
    )


def element_definition(collection, name, annotation):
    kind, optional = unwrapped(annotation)
    parts = [name, column_type(kind)]
    if not optional:
        parts.append("NOT NULL")
    if name in collection.closed:
        parts.append(f"CHECK ({name} IN ({listed(collection.closed[name])}))")
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
    if collection.distinct:
        held = ", ".join(element_columns(collection))
        definitions.append(f"UNIQUE ({collection.owner}, {held})")
    return creates(collection.table, definitions)


def creates(name, definitions):
    body = ",\n    ".join(definitions)
    return f"CREATE TABLE IF NOT EXISTS {name} (\n    {body}\n)"


def declared_columns():
    declared = {}
    for table in TABLES.values():
        declared[table.name] = column_names(table)
        for collection in table.collections:
            declared[collection.table] = (
                collection.owner,
                "position",
                *element_columns(collection),
            )
    return declared


def schema_statements():
    statements = []
    for table in TABLES.values():
        statements.append(table_ddl(table))
        statements += [unique_ddl(table, unique) for unique in table.unique]
        statements += [collection_ddl(table, collection) for collection in table.collections]
    return tuple(statements)
