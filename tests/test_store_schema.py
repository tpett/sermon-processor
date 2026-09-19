from dataclasses import dataclass
from datetime import datetime
from typing import get_type_hints, Literal, Optional

import pytest

from sermon.store import Block, LogEntry, Notification, Reviewer, SpeakerProfile, schema


@dataclass(frozen=True, kw_only=True)
class Finding:
    timecode: float
    note: str | None = None


FINDINGS = schema.Collection(
    field="findings", table="block_finding", owner="block_id", element=Finding
)


@pytest.mark.parametrize(
    "annotation, unwrapped",
    [
        (str, (str, False)),
        (int, (int, False)),
        (datetime, (datetime, False)),
        (dict, (dict, False)),
        (str | None, (str, True)),
        (float | None, (float, True)),
        (Optional[bytes], (bytes, True)),
    ],
)
def test_only_an_annotation_that_admits_no_value_is_nullable(annotation, unwrapped):
    assert schema.unwrapped(annotation) == unwrapped


@pytest.mark.parametrize(
    "annotation",
    [
        tuple[int, ...],
        list[str],
        dict[str, int],
        str | int,
        str | int | None,
        Literal["queued", "running"],
        object,
    ],
)
def test_an_annotation_the_schema_cannot_render_is_refused(annotation):
    with pytest.raises(schema.UnsupportedAnnotation):
        schema.column_definition(schema.TABLES[Block], "whatever", annotation)


def test_an_element_column_the_entity_leaves_optional_is_nullable():
    definitions = schema.collection_ddl(schema.TABLES[Block], FINDINGS)
    assert "timecode REAL NOT NULL" in definitions
    assert "note TEXT" in definitions
    assert "note TEXT NOT NULL" not in definitions


def test_entries_sharing_an_instant_are_ordered_by_the_identity_behind_it():
    assert schema.order_by(schema.TABLES[LogEntry]) == ("occurred_at", "log_entry_id")


def enrolment():
    return schema.TABLES[SpeakerProfile].collections[0]


def test_enrolment_is_a_list_of_segment_ids():
    assert get_type_hints(SpeakerProfile)["enrolled_from"] == tuple[int, ...]
    assert enrolment().element is int


def test_enrolment_names_the_segment_that_contributed():
    collection = enrolment()
    assert collection.field == "enrolled_from"
    assert collection.table == "speaker_profile_enrolment"
    assert collection.column == "segment_id"
    assert collection.references == {"segment_id": "segment(segment_id)"}
    ddl = schema.collection_ddl(schema.TABLES[SpeakerProfile], collection)
    assert "segment_id INTEGER NOT NULL REFERENCES segment(segment_id)" in ddl
    assert "recording_id" not in ddl


def test_the_reviewer_is_identified_by_the_actor_seam():
    table = schema.TABLES[Reviewer]
    assert table.identity == "actor"
    assert table.generated is False
    assert table.references == {}
    assert "actor TEXT NOT NULL PRIMARY KEY" in schema.table_ddl(table)


def test_a_notification_recipient_is_not_a_foreign_key_to_a_reviewer():
    assert "reviewer" not in schema.TABLES[Notification].references.get("recipient", "")
    assert "REFERENCES reviewer" not in schema.table_ddl(schema.TABLES[Notification])
