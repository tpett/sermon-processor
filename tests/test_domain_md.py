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
    assert "never by the system" in stated
    assert "configuration cannot change" in stated
    graded = why("Proposal", "punch_in_grade").lower()
    assert "machine proposed" in graded
    assert "shown to the reviewer" in graded
    assert "human cut" not in graded
    assert "configuration" not in graded


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


def glance():
    return DOMAIN.read_text().split("## Entities at a glance", 1)[1].split("```", 2)[1]


def test_enrolment_names_the_segments_that_contributed():
    stated = why("SpeakerProfile", "enrolled_from[]").lower()
    assert "segment" in stated
    assert "recording" not in stated
    assert "un-enrol" in stated


def test_enrolment_is_a_second_profile_to_segment_relationship():
    speaker_lines = "\n".join(line for line in glance().splitlines() if "SpeakerProfile" in line)
    assert "SpeakerProfile ──1:N──▶ Segment" in speaker_lines
    assert "SpeakerProfile ──N:M──▶ Segment" in speaker_lines
    assert "Recording" not in speaker_lines


def glance_intro():
    return DOMAIN.read_text().split("## Entities at a glance", 1)[1].split("## Recording", 1)[0]


def section(entity):
    return DOMAIN.read_text().split(f"\n## {entity}\n", 1)[1].split("\n## ")[0]


def test_glance_includes_the_reviewer():
    assert "Reviewer" in glance()


def test_the_reviewer_is_counted_among_the_system_nouns():
    intro = glance_intro()
    assert "plus ten the system needs" in intro
    assert "`Reviewer`" in intro
    assert "plus nine the system needs" not in intro


def test_the_user_is_counted_among_the_system_nouns_and_drawn_without_a_foreign_key():
    assert "`User`" in glance_intro()
    user_lines = "\n".join(line for line in glance().splitlines() if line.startswith("User"))
    assert user_lines
    assert "──" not in user_lines


def test_a_user_is_the_verified_address_and_the_actor_is_not_a_reference_to_it():
    assert "\n## User\n" in DOMAIN.read_text()
    stated = why("User", "email").lower()
    assert "verified" in stated
    assert "never one the request announced" in stated
    assert "actor" in stated
    actor = why("LogEntry", "actor").lower()
    assert "not a foreign key" in actor
    assert "tailnet" in section("User").lower()


def test_the_tailnet_host_no_longer_records_the_reviewer_and_says_who_does():
    actor = why("LogEntry", "actor")
    assert "whenever sign-in is required" in actor
    assert "on the tailnet host as much as outside it" in actor
    assert "Nobody on the tailnet host is a `User`" not in section("User")
    assert "no sign-in is configured" in section("Reviewer")


def test_a_credential_is_a_salted_hash_for_a_user_and_never_a_column_on_one():
    assert "`Credential`" in glance_intro()
    held = why("Credential", "password_hash").lower()
    assert "salted" in held and "never the password" in held
    assert "reference to `user`" in why("Credential", "email").lower()
    stated = section("Credential")
    assert "Why not a column on `User`" in stated
    assert "cannot sign in" in stated
    assert "A password is kept only as a salted hash" in stated


def test_opting_out_is_modelled_on_the_reviewer_not_the_notification():
    assert "nothing yet models" not in section("Notification")
    stated = why("Reviewer", "receives_notifications").lower()
    assert "send" in stated
    assert "created" in stated


def test_the_reviewer_is_identified_by_the_actor_seam():
    assert "\n## Reviewer\n" in DOMAIN.read_text()
    stated = why("Reviewer", "actor").lower()
    assert "seam" in stated
    assert "recipient" in stated
    recipient = why("Notification", "recipient").lower()
    assert "not a reference" in recipient


def test_the_reviewer_is_not_drawn_as_a_foreign_key():
    reviewer_lines = "\n".join(line for line in glance().splitlines() if "Reviewer" in line)
    assert "──" not in reviewer_lines


def test_speaker_profile_is_still_the_one_place_a_person_is_stored():
    assert "something about a person" in section("SpeakerProfile").lower()
    assert "person the system stores" in section("Reviewer").lower()
