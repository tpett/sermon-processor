import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.store import (
    Artifact,
    Block,
    DATABASE_NAME,
    Evidence,
    Job,
    Proposal,
    Recording,
    PathEscapesDataRoot,
    Segment,
    SpeakerProfile,
    opens_store,
    vocabularies,
)

IDENTITIES = {
    "recording": "recording_id",
    "block": "block_id",
    "segment": "segment_id",
    "proposal": "segment_id",
    "artifact": "artifact_id",
    "job": "job_id",
    "speaker_profile": "speaker_profile_id",
}

ENTITY_TYPES = {
    "recording": Recording,
    "block": Block,
    "segment": Segment,
    "proposal": Proposal,
    "artifact": Artifact,
    "job": Job,
    "speaker_profile": SpeakerProfile,
}

CLOSED_COLUMNS = [
    ("recording", "state", vocabularies.RECORDING_STATES),
    ("recording", "kind", vocabularies.RECORDING_KINDS),
    ("block", "type", vocabularies.BLOCK_TYPES),
    ("block", "classification_confidence", vocabularies.CONFIDENCE_LEVELS),
    ("segment", "classification", vocabularies.SEGMENT_CLASSIFICATIONS),
    ("segment", "state", vocabularies.SEGMENT_STATES),
    ("segment", "intent", vocabularies.SEGMENT_INTENTS),
    ("segment", "boundary_source", vocabularies.BOUNDARY_SOURCES),
    ("proposal", "classification_confidence", vocabularies.CONFIDENCE_LEVELS),
    ("proposal", "boundary_confidence", vocabularies.CONFIDENCE_LEVELS),
    ("proposal", "punch_in_difficulty", vocabularies.CUT_DIFFICULTIES),
    ("proposal", "punch_out_difficulty", vocabularies.CUT_DIFFICULTIES),
    ("artifact", "kind", vocabularies.ARTIFACT_KINDS),
    ("job", "kind", vocabularies.JOB_KINDS),
    ("job", "state", vocabularies.JOB_STATES),
]


def populated_recording():
    return Recording(
        recording_id="recording_20260913_090014",
        object_key="2026/09/13/recording_20260913_090014.flac",
        state="awaiting_review",
        started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        size_bytes=1_412_230_144,
        kind="class",
        duration_seconds=11520.0,
        channels=2,
        sample_rate=44100,
        bits_per_raw_sample=32,
        local_path="recording_20260913_090014/source.flac",
        checksum="ac5f0d2b9e1c4477",
        dynamic_range_db=63.4,
        active_fraction=0.82,
        longest_active_seconds=3492.5,
        waiting_since=datetime(2026, 9, 13, 9, 30, tzinfo=UTC),
        skip_reason="no local disk",
    )


def minimal_recording():
    return Recording(
        recording_id="recording_20260823_102900",
        object_key="2026/08/23/recording_20260823_102900.flac",
        state="discovered",
        started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
        size_bytes=1_073_741_824,
    )


def populated_block(recording):
    return Block(
        recording_id=recording.recording_id,
        start_seconds=61.0,
        end_seconds=3600.0,
        type="lesson",
        classification_confidence="high",
        self_reported_confidence=0.95,
        evidence="0:01:01 speaker change, then “turn with me to Hebrews”",
        summary="A class on Hebrews 12, taught by one voice",
        cue_start_seconds=120.0,
        cue_end_seconds=132.0,
        retyped_by_human=True,
    )


def minimal_block(recording):
    return Block(
        recording_id=recording.recording_id,
        start_seconds=0.0,
        end_seconds=61.0,
        type="announcements",
    )


def populated_segment(recording, block):
    return Segment(
        recording_id=recording.recording_id,
        seed_block_id=block.block_id,
        classification="lesson",
        state="approved",
        punch_in_seconds=61.5,
        punch_out_seconds=3497.25,
        proposed_punch_in=63.125,
        proposed_punch_out=3499.0,
        intent="publish",
        disposition_at=datetime(2026, 9, 14, 8, 12, tzinfo=UTC),
        boundary_source="model-in/refined-out",
        leading_silence_seconds=0.75,
    )


def minimal_segment(recording):
    return Segment(
        recording_id=recording.recording_id,
        classification="meeting",
        state="proposed",
        punch_in_seconds=0.0,
        punch_out_seconds=11520.0,
    )


def populated_proposal(segment):
    return Proposal(
        segment_id=segment.segment_id,
        classification_confidence="high",
        boundary_confidence="medium",
        punch_in_difficulty="easy",
        punch_out_difficulty="hard",
        agreement_gap_seconds=1.375,
        evidence=(
            Evidence(timecode=61.5, finding="speaker change", implies="the class begins"),
            Evidence(timecode=3497.25, finding="amen", implies="the closing prayer ends"),
        ),
        missing_evidence=("no diarization for the final 4 minutes",),
    )


def minimal_proposal(segment):
    return Proposal(
        segment_id=segment.segment_id,
        classification_confidence="low",
        boundary_confidence="low",
        punch_in_difficulty="moderate",
        punch_out_difficulty="moderate",
    )


def populated_artifact(recording, segment):
    return Artifact(
        recording_id=recording.recording_id,
        segment_id=segment.segment_id,
        kind="rendered_mp3",
        path="recording_20260913_090014/2026-09-13 - Hebrews 12.mp3",
        size_bytes=41_287_168,
        checksum="7b1e39c4aa08f562",
        render_settings={"loudness_lufs": -17.0, "true_peak_dbtp": -1.5, "lame_quality": 3},
        asr_config=None,
        superseded_by=None,
    )


def minimal_artifact(recording):
    return Artifact(
        recording_id=recording.recording_id,
        kind="source_flac",
        path="recording_20260913_090014/source.flac",
        size_bytes=1_412_230_144,
        checksum="ac5f0d2b9e1c4477",
    )


def populated_job(recording, segment):
    return Job(
        recording_id=recording.recording_id,
        segment_id=segment.segment_id,
        kind="render",
        state="failed",
        attempts=3,
        max_attempts=3,
        dedupe_key="render:recording_20260913_090014:1",
        last_error="ffmpeg exited 1",
        failed_permanently=True,
        queued_at=datetime(2026, 9, 14, 8, 12, 1, tzinfo=UTC),
        started_at=datetime(2026, 9, 14, 8, 12, 4, tzinfo=UTC),
    )


def minimal_job(recording):
    return Job(
        recording_id=recording.recording_id,
        kind="download",
        state="queued",
        max_attempts=5,
        dedupe_key="download:recording_20260913_090014",
        queued_at=datetime(2026, 9, 13, 12, 30, tzinfo=UTC),
    )


def populated_speaker_profile(recording):
    return SpeakerProfile(
        name="Travis Pettijohn",
        embedding=bytes(range(32)),
        enrolled_from=(recording.recording_id,),
        confirmed_by_human=True,
    )


def minimal_speaker_profile():
    return SpeakerProfile(name="not a known voice", embedding=b"\x00\x01")


@pytest.fixture
def store(tmp_path):
    opened = opens_store(data_root=tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def graph(store):
    recording = store.saves(populated_recording())
    block = store.saves(populated_block(recording))
    profile = store.saves(populated_speaker_profile(recording))
    block = store.saves(replace(block, speaker_profile_ids=(profile.speaker_profile_id,)))
    segment = store.saves(populated_segment(recording, block))
    return {
        "recording": recording,
        "block": block,
        "speaker_profile": profile,
        "segment": segment,
        "proposal": store.saves(populated_proposal(segment)),
        "artifact": store.saves(populated_artifact(recording, segment)),
        "job": store.saves(populated_job(recording, segment)),
    }


def reloaded(store, entity, name):
    return store.loads(type(entity), getattr(entity, IDENTITIES[name]))


def rows_another_connection_sees(tmp_path):
    connection = sqlite3.connect(tmp_path / DATABASE_NAME)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {name: connection.execute(f"SELECT * FROM {name}").fetchall() for name in tables}
    finally:
        connection.close()


def everything_stored(store, tmp_path):
    return (
        {name: store.lists(entity) for name, entity in ENTITY_TYPES.items()},
        rows_another_connection_sees(tmp_path),
    )


@pytest.mark.parametrize("name", sorted(IDENTITIES))
def test_every_field_of_an_entity_survives_a_round_trip(store, graph, name):
    assert reloaded(store, graph[name], name) == graph[name]


def test_a_recording_round_trips_with_only_what_discovery_knows(store):
    saved = store.saves(minimal_recording())
    assert reloaded(store, saved, "recording") == saved


def test_the_remaining_entities_round_trip_with_only_their_required_fields(store):
    recording = store.saves(minimal_recording())
    block = store.saves(minimal_block(recording))
    segment = store.saves(minimal_segment(recording))
    minimal = {
        "block": block,
        "segment": segment,
        "proposal": store.saves(minimal_proposal(segment)),
        "artifact": store.saves(minimal_artifact(recording)),
        "job": store.saves(minimal_job(recording)),
        "speaker_profile": store.saves(minimal_speaker_profile()),
    }
    assert {name: reloaded(store, saved, name) for name, saved in minimal.items()} == minimal


def test_a_recording_lists_its_blocks_in_the_order_they_cover_it(store, graph):
    later = store.saves(
        replace(graph["block"], block_id=None, start_seconds=3600.0, end_seconds=7200.0)
    )
    earlier = store.saves(minimal_block(graph["recording"]))
    listed = store.lists(Block, recording_id=graph["recording"].recording_id)
    assert [block.block_id for block in listed] == [
        earlier.block_id,
        graph["block"].block_id,
        later.block_id,
    ]


def test_a_segment_grows_from_the_block_that_seeded_it(store, graph):
    assert reloaded(store, graph["segment"], "segment").seed_block_id == graph["block"].block_id


def test_a_segment_has_one_proposal(store, graph):
    replacement = replace(graph["proposal"], boundary_confidence="low", missing_evidence=())
    store.saves(replacement)
    assert store.lists(Proposal, segment_id=graph["segment"].segment_id) == [replacement]


def test_a_segment_lists_the_renders_made_from_it(store, graph):
    assert store.lists(Artifact, segment_id=graph["segment"].segment_id) == [graph["artifact"]]


def test_a_recording_lists_every_artifact_derived_from_it(store, graph):
    source = store.saves(minimal_artifact(graph["recording"]))
    listed = store.lists(Artifact, recording_id=graph["recording"].recording_id)
    assert {artifact.kind for artifact in listed} == {"rendered_mp3", "source_flac"}
    assert source in listed


def test_a_recording_lists_its_jobs_oldest_first(store, graph):
    download = store.saves(minimal_job(graph["recording"]))
    listed = store.lists(Job, recording_id=graph["recording"].recording_id)
    assert listed == [download, graph["job"]]


def test_a_block_lists_the_voices_recognised_in_it(store, graph):
    stored = reloaded(store, graph["block"], "block")
    assert stored.speaker_profile_ids == (graph["speaker_profile"].speaker_profile_id,)


def test_a_speaker_profile_lists_the_recordings_that_enrolled_it(store, graph):
    stored = reloaded(store, graph["speaker_profile"], "speaker_profile")
    assert stored.enrolled_from == (graph["recording"].recording_id,)


def test_a_recut_keeps_the_previous_render_until_the_new_one_succeeds(store, graph):
    fresh = store.saves(
        replace(graph["artifact"], artifact_id=None, path="recording/2026-09-13 - Hebrews 12.mp3")
    )
    previous = store.saves(replace(graph["artifact"], superseded_by=fresh.artifact_id))
    assert reloaded(store, previous, "artifact").superseded_by == fresh.artifact_id


def test_skipping_a_segment_keeps_everything_the_machine_found(store, graph):
    skipped = store.saves(
        replace(
            graph["segment"],
            state="skipped",
            disposition_at=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
        )
    )
    assert reloaded(store, skipped, "segment") == skipped
    assert reloaded(store, graph["proposal"], "proposal") == graph["proposal"]


def test_saving_an_entity_again_does_not_duplicate_its_collections(store, graph):
    store.saves(graph["proposal"])
    store.saves(graph["block"])
    assert reloaded(store, graph["proposal"], "proposal") == graph["proposal"]
    assert reloaded(store, graph["block"], "block") == graph["block"]


@pytest.mark.parametrize("name, column, allowed", CLOSED_COLUMNS)
def test_a_closed_column_refuses_a_value_the_spec_does_not_declare(
    store, graph, tmp_path, name, column, allowed
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph[name], **{column: "whatever the caller felt like"}))
    assert everything_stored(store, tmp_path) == stored


@pytest.mark.parametrize("name, column, allowed", CLOSED_COLUMNS)
def test_a_closed_column_accepts_every_value_the_spec_declares(store, graph, name, column, allowed):
    for value in allowed:
        saved = store.saves(replace(graph[name], **{column: value}))
        assert getattr(reloaded(store, saved, name), column) == value


def test_two_recordings_cannot_claim_one_object_key(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["recording"], recording_id="recording_20260920_090014"))
    assert everything_stored(store, tmp_path) == stored


def test_one_recording_cannot_have_the_same_work_enqueued_twice(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["job"], job_id=None))
    assert everything_stored(store, tmp_path) == stored


def test_an_artifact_cannot_belong_to_a_recording_that_does_not_exist(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(
            replace(
                graph["artifact"], artifact_id=None, recording_id="recording_20000101_000000"
            )
        )
    assert everything_stored(store, tmp_path) == stored


def test_a_segment_cannot_be_seeded_by_a_block_that_does_not_exist(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["segment"], segment_id=None, seed_block_id=404))
    assert everything_stored(store, tmp_path) == stored


def test_a_block_naming_a_voice_that_does_not_exist_is_never_stored(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(minimal_block(graph["recording"]), speaker_profile_ids=(404,)))
    assert everything_stored(store, tmp_path) == stored


def test_a_refused_write_does_not_become_durable_when_a_later_one_commits(store, graph, tmp_path):
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(minimal_block(graph["recording"]), speaker_profile_ids=(404,)))
    later = store.saves(minimal_block(graph["recording"]))
    seen = [row[0] for row in rows_another_connection_sees(tmp_path)["block"]]
    assert seen == [graph["block"].block_id, later.block_id]


def test_listing_by_something_no_entity_holds_is_refused(store):
    with pytest.raises(ValueError):
        store.lists(Recording, needs_attention=True)


def test_reopening_the_data_root_finds_what_was_stored(tmp_path):
    first = opens_store(data_root=tmp_path)
    saved = first.saves(minimal_recording())
    first.close()
    second = opens_store(data_root=tmp_path)
    try:
        assert second.loads(Recording, saved.recording_id) == saved
    finally:
        second.close()


def test_the_store_resolves_an_artifact_under_its_data_root(store, graph, tmp_path):
    assert store.resolves(graph["artifact"]) == tmp_path / graph["artifact"].path


def test_an_artifact_whose_path_escapes_the_data_root_is_never_stored(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(PathEscapesDataRoot):
        store.saves(replace(graph["artifact"], artifact_id=None, path="../../escaped.mp3"))
    assert everything_stored(store, tmp_path) == stored
