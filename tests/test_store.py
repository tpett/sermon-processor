import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from sermon.store import (
    Artifact,
    Block,
    DATABASE_NAME,
    Evidence,
    Job,
    Notification,
    Proposal,
    Recording,
    PathEscapesDataRoot,
    Segment,
    SpeakerProfile,
    Store,
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
    "notification": "notification_id",
    "speaker_profile": "speaker_profile_id",
}

ENTITY_TYPES = {
    "recording": Recording,
    "block": Block,
    "segment": Segment,
    "proposal": Proposal,
    "artifact": Artifact,
    "job": Job,
    "notification": Notification,
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
    ("notification", "state", vocabularies.NOTIFICATION_STATES),
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
        evidence=(
            Evidence(
                timecode=61.0,
                finding="a speaker change",
                implies="the previous Block ended",
            ),
            Evidence(
                timecode=64.0,
                finding="“turn with me to Hebrews”",
                implies="teaching from a passage",
            ),
        ),
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
        distribution_confirmed=True,
        boundary_source="model-in/refined-out",
        leading_silence_seconds=0.75,
        publication_date=date(2026, 9, 13),
        label="Hebrews 12.4-11",
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


def populated_notification(recording, segment):
    return Notification(
        recording_id=recording.recording_id,
        segment_id=segment.segment_id,
        kind="segment_proposed",
        recipient="reviewer",
        summary="A 57 minute sermon was proposed in the 2026-09-13 recording",
        created_at=datetime(2026, 9, 13, 12, 41, tzinfo=UTC),
        state="delivered",
    )


def minimal_notification(recording):
    return Notification(
        recording_id=recording.recording_id,
        kind="nothing_publishable",
        recipient="reviewer",
        summary="Nothing publishable was found in the 2026-09-13 recording",
        created_at=datetime(2026, 9, 13, 11, 4, tzinfo=UTC),
        state="suppressed",
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
        "notification": store.saves(populated_notification(recording, segment)),
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


def test_a_block_carries_every_piece_of_evidence_that_produced_it(store, graph):
    evidence = (
        Evidence(
            timecode=920.0,
            finding="sustained single-speaker teaching",
            implies="the Block is the sermon",
        ),
        Evidence(
            timecode=905.0,
            finding="follows a scripture reading",
            implies="the Block is the sermon",
        ),
    )
    saved = store.saves(
        replace(minimal_block(graph["recording"]), type="sermon", evidence=evidence)
    )
    assert reloaded(store, saved, "block").evidence == evidence


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


def test_confirming_that_a_recording_may_be_distributed_is_recorded_with_the_approval(store, graph):
    approved = store.saves(
        replace(graph["segment"], state="approved", intent="publish", distribution_confirmed=True)
    )
    assert reloaded(store, approved, "segment").distribution_confirmed is True


def test_a_declined_confirmation_is_distinguishable_from_never_having_been_asked(store, graph):
    declined = store.saves(replace(graph["segment"], distribution_confirmed=False))
    never_asked = store.saves(minimal_segment(graph["recording"]))
    assert reloaded(store, declined, "segment").distribution_confirmed is False
    assert reloaded(store, never_asked, "segment").distribution_confirmed is None


def test_a_published_segment_keeps_the_date_and_label_its_filename_is_built_from(store, graph):
    detailed = store.saves(
        replace(graph["segment"], publication_date=date(2026, 8, 23), label="Hebrews 12.4-11")
    )
    stored = reloaded(store, detailed, "segment")
    assert (stored.publication_date, stored.label) == (date(2026, 8, 23), "Hebrews 12.4-11")


def test_a_publication_date_is_stored_as_the_calendar_date_the_filename_uses(store, graph, tmp_path):
    store.saves(replace(graph["segment"], publication_date=date(2026, 8, 23)))
    assert "2026-08-23" in rows_another_connection_sees(tmp_path)["segment"][0]


def test_a_segment_carries_no_publication_details_until_someone_enters_them(store, graph):
    proposed = store.saves(minimal_segment(graph["recording"]))
    stored = reloaded(store, proposed, "segment")
    assert (stored.publication_date, stored.label) == (None, None)


def test_a_notification_records_what_happened_and_whether_it_was_delivered(store, graph):
    raised = store.saves(populated_notification(graph["recording"], graph["segment"]))
    assert store.loads(Notification, raised.notification_id) == raised


def test_a_notification_about_a_whole_recording_names_no_segment(store, graph):
    raised = store.saves(minimal_notification(graph["recording"]))
    assert store.loads(Notification, raised.notification_id).segment_id is None


def test_a_recording_lists_the_notifications_it_raised_oldest_first(store, graph):
    earlier = store.saves(minimal_notification(graph["recording"]))
    listed = store.lists(Notification, recording_id=graph["recording"].recording_id)
    assert listed == [earlier, graph["notification"]]


def test_a_notification_nothing_was_publishable_for_is_recorded_rather_than_dropped(store, graph):
    suppressed = store.saves(minimal_notification(graph["recording"]))
    assert store.loads(Notification, suppressed.notification_id).state == "suppressed"


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


def test_one_recording_cannot_have_the_same_work_queued_twice(store, graph, tmp_path):
    queued = store.saves(minimal_job(graph["recording"]))
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(queued, job_id=None))
    assert everything_stored(store, tmp_path) == stored


def test_work_that_is_already_running_is_not_queued_a_second_time(store, graph, tmp_path):
    running = store.saves(replace(minimal_job(graph["recording"]), state="running"))
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(running, job_id=None, state="queued"))
    assert everything_stored(store, tmp_path) == stored


@pytest.mark.parametrize("finished", ["succeeded", "failed", "cancelled"])
def test_the_same_work_is_enqueued_again_once_the_earlier_job_finished(store, graph, finished):
    earlier = store.saves(replace(graph["job"], state=finished))
    again = store.saves(
        replace(
            earlier,
            job_id=None,
            state="queued",
            attempts=0,
            last_error=None,
            failed_permanently=False,
            started_at=None,
            queued_at=datetime(2026, 9, 14, 9, 0, tzinfo=UTC),
        )
    )
    assert store.lists(Job, dedupe_key=earlier.dedupe_key) == [earlier, again]


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


def test_a_store_cannot_be_opened_without_somewhere_to_keep_it():
    with pytest.raises(TypeError):
        opens_store()


def test_a_store_is_given_the_resolver_for_the_data_root_it_lives_in(tmp_path):
    with pytest.raises(TypeError):
        Store(sqlite3.connect(tmp_path / DATABASE_NAME))


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


def test_the_store_resolves_a_recording_under_its_data_root(store, graph, tmp_path):
    assert store.resolves(graph["recording"]) == tmp_path / graph["recording"].local_path


def test_a_recording_that_was_never_downloaded_resolves_to_nothing(store):
    assert store.resolves(store.saves(minimal_recording())) is None


def test_an_entity_that_holds_no_stored_path_cannot_be_resolved(store, graph):
    with pytest.raises(ValueError):
        store.resolves(graph["segment"])


def test_a_recording_whose_local_path_escapes_the_data_root_is_never_stored(
    store, graph, tmp_path
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(PathEscapesDataRoot):
        store.saves(replace(graph["recording"], local_path="../../../etc/passwd"))
    assert everything_stored(store, tmp_path) == stored


def test_an_artifact_whose_path_escapes_the_data_root_is_never_stored(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(PathEscapesDataRoot):
        store.saves(replace(graph["artifact"], artifact_id=None, path="../../escaped.mp3"))
    assert everything_stored(store, tmp_path) == stored
