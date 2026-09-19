from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

import pytest

from sermon.store import Block, LogEntry, schema


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
