from pathlib import Path

from test_store_vocabularies import domain_row

DOMAIN = Path(__file__).resolve().parents[1] / "features" / "DOMAIN.md"


def why(entity, field):
    return domain_row(entity, field).split("|")[2].strip()


def does_not_decide():
    return DOMAIN.read_text().split(
        "## What this model deliberately does not decide", 1
    )[1]


def test_a_hand_drawn_segment_has_no_seed_block():
    stated = why("Segment", "seed_block_id").lower()
    assert "null only" not in stated
    assert "hand-drawn" in stated


def test_a_publication_label_is_suggested_from_the_summary():
    stated = why("Segment", "label").lower()
    assert "the only part a human writes" not in stated
    assert "suggest" in stated
    assert "from the summary" in stated
    assert "reviewer can correct" in stated


def test_the_machines_grade_of_its_cut_and_the_ground_truth_difficulty_are_separately_named():
    proposal = DOMAIN.read_text().split("\n## Proposal\n", 1)[1].split("\n## ")[0]
    corpus = DOMAIN.read_text().split("\n## CorpusPair\n", 1)[1].split("\n## ")[0]
    assert "`punch_in_grade`" in proposal
    assert "`punch_out_grade`" in proposal
    assert "`punch_in_difficulty`" not in proposal
    assert "`punch_out_difficulty`" not in proposal
    assert "`punch_in_difficulty`" in corpus
    assert "`punch_out_difficulty`" in corpus
    assert "`punch_in_grade`" not in corpus
    assert "`punch_out_grade`" not in corpus
    stated = why("CorpusPair", "punch_in_difficulty").lower()
    assert "human cut" in stated
    assert "configuration cannot change" in stated


def test_agreement_gap_seconds_is_still_a_proposal_field():
    section = DOMAIN.read_text().split("\n## Proposal\n", 1)[1].split("\n## ")[0]
    assert "`agreement_gap_seconds`" in section


def test_agreement_gap_is_null_because_v1_runs_one_analysis():
    stated = why("Proposal", "agreement_gap_seconds").lower()
    assert "configured" not in stated
    assert "v1" in stated
    assert "one analysis" in stated
    assert "deferred" in stated


def test_settled_questions_are_out_of_what_the_model_does_not_decide():
    section = does_not_decide()
    lowered = section.lower()
    assert "storage engine" in lowered
    assert "second analysis" not in lowered
    assert "local audio" not in lowered
    assert "hard delete" not in lowered
    assert "@needs-decision" not in section
    assert "q34" not in lowered
