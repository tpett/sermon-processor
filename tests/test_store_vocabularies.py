import itertools
import re
from pathlib import Path

import pytest

from sermon.store import vocabularies

SPEC_ROOT = Path(__file__).resolve().parents[1] / "features"
LIFECYCLE_TABLE = "| State | Of | Exits |"
BLOCK_TYPE_TABLE = "| Block type | Teaching? | Meaning |"
CLASSIFICATION_TABLE = "| Segment classification | Where it comes from |"
RECORDING_KIND_TABLE = "| Recording kind | Meaning |"


def first_backticked(row):
    found = re.findall(r"`([^`]+)`", row)
    return found[0] if found else None


def table_rows(text, heading):
    after = text.split(heading, 1)[1].splitlines()[1:]
    return list(itertools.takewhile(lambda row: row.strip().startswith("|"), after))


def readme_rows(heading):
    return table_rows((SPEC_ROOT / "README.md").read_text(), heading)


def lifecycle_states(owner):
    return tuple(
        first_backticked(row) for row in readme_rows(LIFECYCLE_TABLE) if f"| {owner} |" in row
    )


def vocabulary_table(heading):
    return tuple(name for name in map(first_backticked, readme_rows(heading)) if name)


def domain_field(entity, field):
    text = (SPEC_ROOT / "DOMAIN.md").read_text()
    section = text.split(f"\n## {entity}\n", 1)[1].split("\n## ")[0]
    rows = [row for row in section.splitlines() if row.strip().startswith("|")]
    row = next(row for row in rows if f"`{field}`" in row.split("|")[1])
    stated = re.split(r"\. |\*\*|—", row.split("|")[2].strip())[0]
    return tuple(re.findall(r"`([^`]+)`", stated))


SPEC_VOCABULARIES = {
    "RECORDING_STATES": (10, lifecycle_states("Recording")),
    "SEGMENT_STATES": (7, lifecycle_states("Segment")),
    "BLOCK_TYPES": (11, vocabulary_table(BLOCK_TYPE_TABLE)),
    "SEGMENT_CLASSIFICATIONS": (4, vocabulary_table(CLASSIFICATION_TABLE)),
    "RECORDING_KINDS": (7, vocabulary_table(RECORDING_KIND_TABLE)),
    "SEGMENT_INTENTS": (2, domain_field("Segment", "intent")),
    "BOUNDARY_SOURCES": (4, domain_field("Segment", "boundary_source")),
    "CONFIDENCE_LEVELS": (3, domain_field("Block", "classification_confidence")),
    "CUT_DIFFICULTIES": (3, domain_field("Proposal", "punch_in_difficulty")),
    "ARTIFACT_KINDS": (6, domain_field("Artifact", "kind")),
    "JOB_KINDS": (3, domain_field("Job", "kind")),
    "JOB_STATES": (5, domain_field("Job", "state")),
    "NOTIFICATION_STATES": (4, domain_field("Notification", "state")),
}


@pytest.mark.parametrize("name", sorted(SPEC_VOCABULARIES))
def test_the_closed_set_is_the_one_the_spec_declares(name):
    size, declared = SPEC_VOCABULARIES[name]
    assert len(declared) == size
    assert getattr(vocabularies, name) == declared


def test_the_states_in_which_a_job_still_holds_its_work_are_the_unfinished_ones():
    assert set(vocabularies.JOB_STATES) - set(vocabularies.JOB_STATES_IN_FLIGHT) == {
        "succeeded",
        "failed",
        "cancelled",
    }


def test_the_difficulty_of_both_cuts_comes_from_one_vocabulary():
    assert domain_field("Proposal", "punch_out_difficulty") == vocabularies.CUT_DIFFICULTIES
