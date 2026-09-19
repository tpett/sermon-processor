import sqlite3
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from sermon.store import (
    Artifact,
    Block,
    Candidate,
    ChannelLevel,
    CorpusPair,
    DATABASE_NAME,
    Discovery,
    Evidence,
    Job,
    LogEntry,
    Notification,
    Proposal,
    Recording,
    PathEscapesDataRoot,
    Segment,
    SkippedObject,
    SpeakerMatch,
    SpeakerProfile,
    Store,
    UnstorableValue,
    opens_store,
    vocabularies,
)

IDENTITIES = {
    "recording": "recording_id",
    "block": "block_id",
    "segment": "segment_id",
    "proposal": "proposal_id",
    "artifact": "artifact_id",
    "job": "job_id",
    "notification": "notification_id",
    "speaker_profile": "speaker_profile_id",
    "log_entry": "log_entry_id",
    "skipped_object": "object_key",
    "discovery": "discovery_id",
    "corpus_pair": "corpus_pair_id",
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
    "log_entry": LogEntry,
    "skipped_object": SkippedObject,
    "discovery": Discovery,
    "corpus_pair": CorpusPair,
}

CLOSED_COLUMNS = [
    ("recording", "state", vocabularies.RECORDING_STATES),
    ("recording", "started_at_source", vocabularies.STARTED_AT_SOURCES),
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
    ("log_entry", "entered_state", vocabularies.RECORDING_STATES + vocabularies.SEGMENT_STATES),
    ("log_entry", "boundary_source", vocabularies.BOUNDARY_SOURCES),
    ("skipped_object", "reason", vocabularies.SKIP_REASONS),
    ("discovery", "kind", vocabularies.DISCOVERY_KINDS),
    ("discovery", "failure", vocabularies.DISCOVERY_FAILURES),
    ("corpus_pair", "classification", vocabularies.SEGMENT_CLASSIFICATIONS),
    ("corpus_pair", "alignment", vocabularies.CORPUS_ALIGNMENTS),
    ("corpus_pair", "punch_in_difficulty", vocabularies.CUT_DIFFICULTIES),
    ("corpus_pair", "punch_out_difficulty", vocabularies.CUT_DIFFICULTIES),
    ("corpus_pair", "provenance", vocabularies.CORPUS_PROVENANCES),
]

CLOSED_COLLECTIONS = [
    ("recording", "warnings", vocabularies.RECORDING_WARNINGS),
    ("segment", "warnings", vocabularies.SEGMENT_WARNINGS),
]

COMPANIONS = {
    ("discovery", "kind"): {"failure": None, "event": None},
    ("discovery", "failure"): {"kind": "scan", "discovered_count": 0, "event": None},
    ("corpus_pair", "alignment"): {
        "punch_in_seconds": None,
        "punch_out_seconds": None,
        "drift_ppm": None,
        "punch_in_difficulty": None,
        "punch_out_difficulty": None,
    },
    ("corpus_pair", "provenance"): {
        "alignment": None,
        "punch_in_seconds": None,
        "punch_out_seconds": None,
        "drift_ppm": None,
        "punch_in_difficulty": None,
        "punch_out_difficulty": None,
    },
}

SKIPPED_OBJECTS = (
    ("recording_19700101_000000.flac", "recorder clock not set"),
    ("sermon-2027-01-03.flac", "key does not match the pattern"),
    ("recordings/README.txt", "not an audio object"),
    ("recording_20240107_101500.flac", "before the ingest cutoff"),
)

MOMENTS = [
    ("recording", "started_at"),
    ("segment", "disposition_at"),
    ("job", "queued_at"),
    ("notification", "created_at"),
    ("log_entry", "occurred_at"),
    ("discovery", "occurred_at"),
]


def populated_recording():
    return Recording(
        recording_id="recording_20260913_090014",
        object_key="2026/09/13/recording_20260913_090014.flac",
        state="awaiting_review",
        started_at=datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC),
        started_at_source="key",
        size_bytes=1_412_230_144,
        capture_device="sanctuary-pi-01",
        kind="class",
        duration_seconds=11520.0,
        channels=2,
        sample_rate=44100,
        bits_per_raw_sample=32,
        channel_levels=(
            ChannelLevel(channel=1, rms_db=-21.3),
            ChannelLevel(channel=2, rms_db=-90.4),
        ),
        mono_source="channel 1 only",
        mono_source_confirmed=True,
        local_path="recording_20260913_090014/source.flac",
        checksum="ac5f0d2b9e1c4477",
        sidecar_present=True,
        integrated_loudness_lufs=-24.6,
        true_peak_dbtp=0.4,
        loudness_range_lu=7.2,
        dynamic_range_db=63.4,
        active_fraction=0.82,
        longest_active_seconds=3492.5,
        waiting_since=datetime(2026, 9, 13, 9, 30, tzinfo=UTC),
        warnings=("damaged container", "unexpected stereo content"),
        skip_reason="transcription timed out",
    )


def minimal_recording():
    return Recording(
        recording_id="recording_20260823_102900",
        object_key="2026/08/23/recording_20260823_102900.flac",
        state="discovered",
        started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
        started_at_source="key",
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
        possibly_multiple_types=True,
    )


def minimal_block(recording):
    return Block(
        recording_id=recording.recording_id,
        start_seconds=0.0,
        end_seconds=61.0,
        type="announcements",
    )


def populated_segment(recording, block, profile):
    return Segment(
        recording_id=recording.recording_id,
        seed_block_id=block.block_id,
        classification="lesson",
        state="approved",
        span_start_seconds=61.0,
        span_end_seconds=3600.0,
        punch_in_seconds=61.5,
        punch_out_seconds=3497.25,
        intent="publish",
        disposition_at=datetime(2026, 9, 14, 8, 12, tzinfo=UTC),
        distribution_confirmed=True,
        confirmed_speaker_profile_id=profile.speaker_profile_id,
        boundary_source="model-in/refined-out",
        leading_silence_seconds=0.75,
        summary="A class on Hebrews 12, taught by one voice",
        warnings=("check the opening", "source was very quiet"),
        publication_date=date(2026, 9, 13),
        label="Hebrews 12.4-11",
    )


def minimal_segment(recording):
    return Segment(
        recording_id=recording.recording_id,
        classification="meeting",
        state="proposed",
        span_start_seconds=0.0,
        span_end_seconds=11520.0,
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
        punch_in_candidates=(
            Candidate(timecode=6890.0, considered_because="4.2 s of quiet before a greeting"),
        ),
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


def populated_log_entry(recording, segment, job, proposal, artifact):
    return LogEntry(
        recording_id=recording.recording_id,
        segment_id=segment.segment_id,
        job_id=job.job_id,
        proposal_id=proposal.proposal_id,
        artifact_id=artifact.artifact_id,
        kind="approved",
        occurred_at=datetime(2026, 9, 13, 8, 55, tzinfo=UTC),
        correlation_id="ingest-7f3a1c",
        actor="the reviewer",
        entered_state="approved",
        duration_seconds=812.4,
        error="the transcription service was unreachable",
        punch_in_seconds=7220.0,
        punch_out_seconds=9812.0,
        boundary_source="human",
    )


def minimal_log_entry(recording):
    return LogEntry(
        recording_id=recording.recording_id,
        kind="state_change",
        occurred_at=datetime(2026, 9, 13, 9, 2, tzinfo=UTC),
        correlation_id="analyze-4b20e9",
    )


def received_webhook():
    return Discovery(
        kind="webhook",
        occurred_at=datetime(2026, 9, 13, 9, 2, tzinfo=UTC),
        discovered_count=1,
        event="recording.uploaded",
    )


def completed_scan():
    return Discovery(
        kind="scan",
        occurred_at=datetime(2026, 9, 13, 3, 0, tzinfo=UTC),
        discovered_count=2,
    )


def system_alert():
    return Notification(
        kind="scratch_exhausted",
        recipient="reviewer",
        summary="Scratch space is exhausted; downloads and renders are paused",
        created_at=datetime(2026, 9, 13, 4, 15, tzinfo=UTC),
        state="pending",
    )


def skipped_object():
    key, reason = SKIPPED_OBJECTS[0]
    return SkippedObject(object_key=key, reason=reason)


def labelled_corpus_pair(recording, classification="sermon"):
    return CorpusPair(
        recording_id=recording.recording_id,
        classification=classification,
        alignment="aligned",
        punch_in_seconds=1000.0,
        punch_out_seconds=3999.61,
        drift_ppm=-130.0,
        punch_in_difficulty="easy",
        punch_out_difficulty="hard",
        covers_more_than_95_percent=False,
        provenance="human",
    )


def machine_cut_corpus_pair(recording):
    return CorpusPair(
        recording_id=recording.recording_id,
        classification="sermon",
        provenance="machine",
    )


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
    block = store.saves(
        replace(
            block,
            speaker_matches=(
                SpeakerMatch(speaker_profile_id=profile.speaker_profile_id, similarity=0.94),
            ),
        )
    )
    segment = store.saves(populated_segment(recording, block, profile))
    proposal = store.saves(populated_proposal(segment))
    artifact = store.saves(populated_artifact(recording, segment))
    job = store.saves(populated_job(recording, segment))
    return {
        "recording": recording,
        "block": block,
        "speaker_profile": profile,
        "segment": segment,
        "proposal": proposal,
        "artifact": artifact,
        "job": job,
        "notification": store.saves(populated_notification(recording, segment)),
        "log_entry": store.saves(
            populated_log_entry(recording, segment, job, proposal, artifact)
        ),
        "skipped_object": store.saves(skipped_object()),
        "discovery": store.saves(received_webhook()),
        "corpus_pair": store.saves(labelled_corpus_pair(recording, classification="lesson")),
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
        "corpus_pair": store.saves(machine_cut_corpus_pair(recording)),
    }
    assert {name: reloaded(store, saved, name) for name, saved in minimal.items()} == minimal


def test_a_recording_lists_the_level_measured_on_each_of_its_channels(store, graph):
    remeasured = (ChannelLevel(channel=1, rms_db=-18.7), ChannelLevel(channel=2, rms_db=-88.1))
    reprobed = store.saves(replace(graph["recording"], channel_levels=remeasured))
    assert reloaded(store, reprobed, "recording").channel_levels == remeasured


def test_a_recording_keeps_its_channel_levels_in_the_order_the_probe_reported_them(store, graph):
    reported = (ChannelLevel(channel=2, rms_db=-90.4), ChannelLevel(channel=1, rms_db=-21.3))
    reprobed = store.saves(replace(graph["recording"], channel_levels=reported))
    assert reloaded(store, reprobed, "recording").channel_levels == reported


def test_a_recording_records_which_channel_or_mix_the_render_must_take(store, graph):
    decided = store.saves(replace(graph["recording"], mono_source="both channels mixed"))
    assert reloaded(store, decided, "recording").mono_source == "both channels mixed"


def test_a_mono_source_a_human_answered_for_is_distinguishable_from_one_the_probe_decided(store):
    asked = store.saves(replace(minimal_recording(), mono_source="both channels mixed"))
    answered = store.saves(replace(asked, mono_source_confirmed=True))
    decided = store.saves(
        replace(
            minimal_recording(),
            recording_id="recording_20260830_102900",
            object_key="2026/08/30/recording_20260830_102900.flac",
            mono_source="channel 1 only",
        )
    )
    assert reloaded(store, answered, "recording").mono_source_confirmed is True
    assert reloaded(store, decided, "recording").mono_source_confirmed is None


def test_a_recording_whose_channels_the_reviewer_must_rule_on_holds_no_mono_source_yet(store):
    stored = reloaded(store, store.saves(minimal_recording()), "recording")
    assert (stored.mono_source, stored.mono_source_confirmed) == (None, None)


def test_a_start_time_taken_from_the_upload_is_distinguishable_from_one_read_off_the_key(
    store, graph
):
    from_key = store.saves(minimal_recording())
    fallen_back = store.saves(replace(from_key, started_at_source="last_modified"))
    assert reloaded(store, fallen_back, "recording").started_at_source == "last_modified"
    assert reloaded(store, graph["recording"], "recording").started_at_source == "key"


def test_a_recording_cannot_leave_the_source_of_its_start_time_unsaid():
    with pytest.raises(TypeError):
        Recording(
            recording_id="recording_20260823_102900",
            object_key="2026/08/23/recording_20260823_102900.flac",
            state="discovered",
            started_at=datetime(2026, 8, 23, 10, 29, tzinfo=UTC),
            size_bytes=1_073_741_824,
        )


def test_a_missing_sidecar_is_noted_on_the_recording(store, graph):
    downloaded = store.saves(replace(graph["recording"], sidecar_present=False))
    assert reloaded(store, downloaded, "recording").sidecar_present is False


def test_a_recording_nothing_has_looked_for_a_sidecar_for_notes_neither(store):
    saved = store.saves(minimal_recording())
    assert reloaded(store, saved, "recording").sidecar_present is None


def test_a_recording_names_the_device_that_captured_it(store, graph):
    moved = store.saves(replace(graph["recording"], capture_device="sanctuary-pi-02"))
    assert reloaded(store, moved, "recording").capture_device == "sanctuary-pi-02"


def test_a_recording_the_recorder_announced_no_host_for_names_no_device(store):
    saved = store.saves(minimal_recording())
    assert reloaded(store, saved, "recording").capture_device is None


def test_a_recording_lists_the_warnings_the_pipeline_raised_on_it(store, graph):
    raised = ("damaged container", "unexpected language")
    flagged = store.saves(replace(graph["recording"], warnings=raised))
    assert reloaded(store, flagged, "recording").warnings == raised


def test_a_recording_keeps_its_warnings_in_the_order_they_were_raised(store, graph):
    raised = ("unexpected language", "damaged container")
    flagged = store.saves(replace(graph["recording"], warnings=raised))
    assert reloaded(store, flagged, "recording").warnings == raised


def test_a_recording_the_pipeline_found_nothing_wrong_with_carries_no_warnings(store):
    assert reloaded(store, store.saves(minimal_recording()), "recording").warnings == ()


def test_a_recording_whose_source_clips_is_flagged_beside_its_other_warnings(store, graph):
    raised = ("damaged container", "source clipping detected")
    flagged = store.saves(replace(graph["recording"], warnings=raised))
    assert reloaded(store, flagged, "recording").warnings == raised


def test_a_clipping_flag_leaves_the_recording_where_analysis_found_it(store, graph):
    analysing = store.saves(replace(graph["recording"], state="analyzing"))
    flagged = store.saves(replace(analysing, warnings=("source clipping detected",)))
    stored = reloaded(store, flagged, "recording")
    assert (stored.state, stored.warnings) == ("analyzing", ("source clipping detected",))


def test_a_discrepancy_between_the_sidecar_and_the_audio_is_recorded_as_a_warning(store, graph):
    probed = store.saves(
        replace(
            graph["recording"],
            duration_seconds=6268.950,
            warnings=("sidecar disagrees with the audio",),
        )
    )
    stored = reloaded(store, probed, "recording")
    assert (stored.duration_seconds, stored.warnings) == (
        6268.950,
        ("sidecar disagrees with the audio",),
    )


def test_a_recording_whose_source_vanished_is_flagged_where_review_left_it(store, graph):
    reviewed = store.saves(replace(graph["recording"], state="reviewed"))
    flagged = store.saves(replace(reviewed, warnings=("source no longer available",)))
    stored = reloaded(store, flagged, "recording")
    assert (stored.state, stored.warnings) == ("reviewed", ("source no longer available",))


def test_the_segments_no_longer_extractable_are_the_skipped_ones_whose_source_vanished(
    store, graph
):
    vanished = store.saves(replace(graph["recording"], warnings=("source no longer available",)))
    intact = store.saves(minimal_recording())
    orphaned = store.saves(replace(minimal_segment(vanished), state="skipped"))
    store.saves(replace(minimal_segment(intact), state="skipped"))
    store.saves(replace(minimal_segment(vanished), state="approved"))
    flagged = {
        recording.recording_id
        for recording in store.lists(Recording)
        if "source no longer available" in recording.warnings
    }
    unextractable = [
        segment for segment in store.lists(Segment, state="skipped")
        if segment.recording_id in flagged
    ]
    assert [segment.segment_id for segment in unextractable] == [orphaned.segment_id]


def test_a_recording_holds_the_source_loudness_the_render_normalizes_from(store, graph):
    reprobed = store.saves(
        replace(
            graph["recording"],
            integrated_loudness_lufs=-19.8,
            true_peak_dbtp=-1.2,
            loudness_range_lu=9.4,
        )
    )
    stored = reloaded(store, reprobed, "recording")
    assert (stored.integrated_loudness_lufs, stored.true_peak_dbtp, stored.loudness_range_lu) == (
        -19.8,
        -1.2,
        9.4,
    )
    assert stored.dynamic_range_db == 63.4


def test_a_recording_holds_no_loudness_until_the_probe_measures_it(store):
    stored = reloaded(store, store.saves(minimal_recording()), "recording")
    assert (stored.integrated_loudness_lufs, stored.true_peak_dbtp, stored.loudness_range_lu) == (
        None,
        None,
        None,
    )


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


def test_a_segment_holds_an_outer_span_its_punch_points_sit_inside(store, graph):
    stored = reloaded(store, graph["segment"], "segment")
    assert (stored.span_start_seconds, stored.span_end_seconds) == (61.0, 3600.0)
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (61.5, 3497.25)


def test_extending_a_segments_span_leaves_its_punch_points_where_they_were(store, graph):
    extended = store.saves(
        replace(graph["segment"], span_start_seconds=5.0, span_end_seconds=3900.0)
    )
    stored = reloaded(store, extended, "segment")
    assert (stored.span_start_seconds, stored.span_end_seconds) == (5.0, 3900.0)
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (61.5, 3497.25)


def test_a_segment_no_block_seeded_holds_a_span_of_its_own(store, graph):
    drawn = store.saves(minimal_segment(graph["recording"]))
    stored = reloaded(store, drawn, "segment")
    assert stored.seed_block_id is None
    assert (stored.span_start_seconds, stored.span_end_seconds) == (0.0, 11520.0)


def test_a_segment_lists_the_warnings_its_analysis_raised(store, graph):
    raised = ("boundary is not acceptable", "check the opening")
    flagged = store.saves(replace(graph["segment"], warnings=raised))
    assert reloaded(store, flagged, "segment").warnings == raised


def test_a_cut_with_no_quiet_margin_is_flagged_at_the_end_it_was_found(store, graph):
    raised = ("no clean cut point found at punch-in", "no clean cut point found at punch-out")
    flagged = store.saves(replace(graph["segment"], warnings=raised))
    assert reloaded(store, flagged, "segment").warnings == raised


def test_a_segment_nothing_went_wrong_with_carries_no_warnings(store, graph):
    saved = store.saves(minimal_segment(graph["recording"]))
    assert reloaded(store, saved, "segment").warnings == ()


def test_a_boundary_that_cannot_satisfy_the_cut_rules_is_flagged_rather_than_moved(store, graph):
    flagged = store.saves(replace(graph["segment"], warnings=("boundary is not acceptable",)))
    stored = reloaded(store, flagged, "segment")
    assert (stored.punch_in_seconds, stored.warnings) == (
        graph["segment"].punch_in_seconds,
        ("boundary is not acceptable",),
    )


def test_a_proposed_segment_carries_a_summary_of_its_own(store, graph):
    summarised = store.saves(
        replace(graph["segment"], summary="On enduring hardship as discipline, from Hebrews 12")
    )
    stored = reloaded(store, summarised, "segment")
    assert stored.summary == "On enduring hardship as discipline, from Hebrews 12"


def test_a_segment_carries_no_summary_until_summarization_runs(store, graph):
    drawn = store.saves(minimal_segment(graph["recording"]))
    assert reloaded(store, drawn, "segment").summary is None


def test_correcting_a_proposal_does_not_make_it_a_second_one(store, graph):
    replacement = replace(graph["proposal"], boundary_confidence="low", missing_evidence=())
    store.saves(replacement)
    assert store.lists(Proposal, segment_id=graph["segment"].segment_id) == [replacement]


def test_a_re_run_keeps_the_proposal_it_replaced(store, graph):
    fresh = store.saves(
        replace(populated_proposal(graph["segment"]), classification_confidence="low")
    )
    previous = store.saves(replace(graph["proposal"], superseded_by=fresh.proposal_id))
    assert store.lists(Proposal, segment_id=graph["segment"].segment_id) == [previous, fresh]


def test_the_machine_proposal_beside_a_reviewers_work_is_the_one_not_yet_superseded(store, graph):
    adjusted = store.saves(
        replace(graph["segment"], punch_in_seconds=5582.0, boundary_source="human")
    )
    fresh = store.saves(populated_proposal(adjusted))
    store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="boundaries_proposed",
            segment_id=adjusted.segment_id,
            proposal_id=fresh.proposal_id,
            punch_in_seconds=5590.5,
            boundary_source="model",
        )
    )
    store.saves(replace(graph["proposal"], superseded_by=fresh.proposal_id))
    stored = reloaded(store, adjusted, "segment")
    assert (stored.punch_in_seconds, stored.boundary_source) == (5582.0, "human")
    assert store.lists(Proposal, segment_id=adjusted.segment_id, superseded_by=None) == [fresh]
    logged = store.lists(LogEntry, proposal_id=fresh.proposal_id)
    assert [entry.punch_in_seconds for entry in logged] == [5590.5]


def test_a_segment_lists_the_renders_made_from_it(store, graph):
    assert store.lists(Artifact, segment_id=graph["segment"].segment_id) == [graph["artifact"]]


def test_a_stage_that_reads_the_envelope_finds_the_one_already_computed(store, graph):
    computed = store.saves(
        replace(
            minimal_artifact(graph["recording"]),
            kind="envelope",
            path="recording_20260913_090014/envelope",
        )
    )
    cached = store.lists(Artifact, recording_id=graph["recording"].recording_id, kind="envelope")
    assert cached == [computed]


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


def test_a_block_that_may_contain_more_than_one_type_is_flagged_for_splitting(store, graph):
    unflagged = store.saves(minimal_block(graph["recording"]))
    flagged = store.saves(replace(unflagged, possibly_multiple_types=True))
    assert reloaded(store, flagged, "block").possibly_multiple_types is True


def test_a_block_the_classifier_read_as_one_thing_is_not_offered_for_splitting(store, graph):
    saved = store.saves(minimal_block(graph["recording"]))
    assert reloaded(store, saved, "block").possibly_multiple_types is False


def test_a_block_lists_the_voices_recognised_in_it(store, graph):
    stored = reloaded(store, graph["block"], "block")
    assert [match.speaker_profile_id for match in stored.speaker_matches] == [
        graph["speaker_profile"].speaker_profile_id
    ]


def test_a_block_records_how_strongly_each_voice_matched_it(store, graph):
    match = SpeakerMatch(
        speaker_profile_id=graph["speaker_profile"].speaker_profile_id, similarity=0.94
    )
    saved = store.saves(replace(minimal_block(graph["recording"]), speaker_matches=(match,)))
    assert reloaded(store, saved, "block").speaker_matches == (match,)


def test_a_block_keeps_the_voices_it_matched_in_the_order_they_ranked(store, graph):
    guest = store.saves(minimal_speaker_profile())
    ranked = (
        SpeakerMatch(
            speaker_profile_id=graph["speaker_profile"].speaker_profile_id, similarity=0.94
        ),
        SpeakerMatch(speaker_profile_id=guest.speaker_profile_id, similarity=0.31),
    )
    saved = store.saves(replace(minimal_block(graph["recording"]), speaker_matches=ranked))
    assert reloaded(store, saved, "block").speaker_matches == ranked


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


def test_a_human_confirming_who_preached_is_recorded_against_the_segment(store, graph):
    confirmed = store.saves(
        replace(
            graph["segment"],
            confirmed_speaker_profile_id=graph["speaker_profile"].speaker_profile_id,
        )
    )
    stored = reloaded(store, confirmed, "segment")
    assert stored.confirmed_speaker_profile_id == graph["speaker_profile"].speaker_profile_id


def test_a_corrected_speaker_outlives_a_re_analysis_that_re_ranks_the_machine_matches(store, graph):
    guest = store.saves(minimal_speaker_profile())
    corrected = store.saves(
        replace(graph["segment"], confirmed_speaker_profile_id=guest.speaker_profile_id)
    )
    store.saves(
        replace(
            graph["block"],
            speaker_matches=(
                SpeakerMatch(
                    speaker_profile_id=graph["speaker_profile"].speaker_profile_id, similarity=0.97
                ),
            ),
        )
    )
    stored = reloaded(store, corrected, "segment")
    assert stored.confirmed_speaker_profile_id == guest.speaker_profile_id


def test_a_segment_confirming_a_voice_that_does_not_exist_is_never_stored(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["segment"], confirmed_speaker_profile_id=404))
    assert everything_stored(store, tmp_path) == stored


def test_a_segment_nobody_has_confirmed_a_voice_for_names_none(store, graph):
    drawn = store.saves(minimal_segment(graph["recording"]))
    assert reloaded(store, drawn, "segment").confirmed_speaker_profile_id is None


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


def test_a_publication_date_is_stored_as_the_calendar_date_the_filename_uses(
    store, graph, tmp_path
):
    store.saves(replace(graph["segment"], publication_date=date(2026, 8, 23)))
    assert "2026-08-23" in rows_another_connection_sees(tmp_path)["segment"][0]


def test_a_moment_in_time_is_refused_where_a_calendar_date_belongs(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(TypeError):
        store.saves(replace(graph["segment"], publication_date=graph["recording"].started_at))
    assert everything_stored(store, tmp_path) == stored


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


def test_recordings_that_finish_together_raise_one_notification_each(store, graph):
    raised = []
    for minute, suffix in ((41, "102900"), (43, "104900"), (45, "105100")):
        recording = store.saves(
            replace(
                minimal_recording(),
                recording_id=f"recording_20260823_{suffix}",
                object_key=f"2026/08/23/recording_20260823_{suffix}.flac",
            )
        )
        raised.append(
            store.saves(
                replace(
                    minimal_notification(recording),
                    state="pending",
                    created_at=datetime(2026, 9, 13, 12, minute, tzinfo=UTC),
                )
            )
        )
    listed = store.lists(Notification, recipient="reviewer", state="pending")
    assert listed == raised
    assert len({one.recording_id for one in listed}) == 3


def test_a_notification_nothing_was_publishable_for_is_recorded_rather_than_dropped(store, graph):
    suppressed = store.saves(minimal_notification(graph["recording"]))
    assert store.loads(Notification, suppressed.notification_id).state == "suppressed"


def test_a_recording_lists_every_entry_in_its_processing_log_oldest_first(store, graph):
    recording = graph["recording"]
    transition = store.saves(replace(minimal_log_entry(recording), entered_state="analyzing"))
    attempt = store.saves(
        replace(
            minimal_log_entry(recording),
            kind="analyze_attempt",
            occurred_at=datetime(2026, 9, 13, 9, 15, 30, tzinfo=UTC),
            job_id=graph["job"].job_id,
            duration_seconds=812.4,
            error="the transcription service was unreachable",
        )
    )
    action = store.saves(
        replace(
            minimal_log_entry(recording),
            kind="approved",
            occurred_at=datetime(2026, 9, 13, 11, 4, 9, tzinfo=UTC),
            segment_id=graph["segment"].segment_id,
            actor="the reviewer",
        )
    )
    assert store.lists(LogEntry, recording_id=recording.recording_id) == [
        graph["log_entry"],
        transition,
        attempt,
        action,
    ]


def test_the_processing_log_is_in_time_order_whatever_offset_its_entries_were_written_with(store):
    recording = store.saves(minimal_recording())
    for written in (
        datetime(2026, 9, 13, 10, 0, tzinfo=timezone(timedelta(hours=2))),
        datetime(2026, 9, 13, 9, 0, tzinfo=UTC),
        datetime(2026, 9, 13, 9, 0, tzinfo=timezone(timedelta(hours=-5))),
    ):
        store.saves(replace(minimal_log_entry(recording), occurred_at=written))
    logged = store.lists(LogEntry, recording_id=recording.recording_id)
    assert [entry.occurred_at for entry in logged] == [
        datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
        datetime(2026, 9, 13, 9, 0, tzinfo=UTC),
        datetime(2026, 9, 13, 14, 0, tzinfo=UTC),
    ]


@pytest.mark.parametrize("name, column", MOMENTS)
def test_a_moment_that_carries_no_offset_is_never_stored(store, graph, tmp_path, name, column):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(UnstorableValue):
        store.saves(replace(graph[name], **{column: datetime(2026, 9, 13, 9, 2)}))
    assert everything_stored(store, tmp_path) == stored


def test_a_state_transition_records_the_state_it_entered_and_when(store, graph):
    entered = store.saves(replace(minimal_log_entry(graph["recording"]), entered_state="analyzing"))
    stored = reloaded(store, entered, "log_entry")
    assert (stored.entered_state, stored.occurred_at) == ("analyzing", entered.occurred_at)


def test_the_log_records_a_segments_transitions_beside_the_recordings(store, graph):
    store.saves(replace(minimal_log_entry(graph["recording"]), entered_state="awaiting_review"))
    store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            entered_state="recut",
            segment_id=graph["segment"].segment_id,
            occurred_at=datetime(2026, 9, 14, 8, 0, tzinfo=UTC),
        )
    )
    logged = store.lists(LogEntry, recording_id=graph["recording"].recording_id)
    assert [(entry.entered_state, entry.segment_id) for entry in logged] == [
        ("approved", graph["segment"].segment_id),
        ("awaiting_review", None),
        ("recut", graph["segment"].segment_id),
    ]


def test_every_job_attempt_is_recorded_with_its_timestamp_duration_and_error(store, graph):
    job = store.saves(minimal_job(graph["recording"]))
    attempt = replace(
        minimal_log_entry(graph["recording"]),
        kind="analyze_attempt",
        job_id=job.job_id,
        duration_seconds=44.5,
        error="the transcription service was unreachable",
    )
    first = store.saves(attempt)
    second = store.saves(
        replace(
            attempt,
            occurred_at=datetime(2026, 9, 13, 9, 20, tzinfo=UTC),
            duration_seconds=2841.0,
            error=None,
        )
    )
    logged = store.lists(LogEntry, job_id=job.job_id)
    assert [(entry.occurred_at, entry.duration_seconds, entry.error) for entry in logged] == [
        (first.occurred_at, 44.5, "the transcription service was unreachable"),
        (second.occurred_at, 2841.0, None),
    ]


def test_an_entry_that_cannot_be_correlated_to_the_application_logs_is_never_stored(
    store, graph, tmp_path
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(minimal_log_entry(graph["recording"]), correlation_id=None))
    assert everything_stored(store, tmp_path) == stored


def test_a_human_action_records_who_performed_it_and_against_which_segment(store, graph):
    adjustment = store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="punch_in_adjusted",
            actor="the reviewer",
            segment_id=graph["segment"].segment_id,
        )
    )
    stored = reloaded(store, adjustment, "log_entry")
    assert (stored.kind, stored.actor, stored.segment_id) == (
        "punch_in_adjusted",
        "the reviewer",
        graph["segment"].segment_id,
    )


def test_each_set_of_boundaries_is_kept_with_who_approved_it_and_when(store, graph):
    segment = store.saves(minimal_segment(graph["recording"]))
    first = store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="approved",
            segment_id=segment.segment_id,
            actor="the reviewer",
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
        )
    )
    second = store.saves(
        replace(
            first,
            log_entry_id=None,
            occurred_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
            punch_out_seconds=9850.0,
        )
    )
    logged = store.lists(LogEntry, segment_id=segment.segment_id)
    assert [
        (entry.punch_in_seconds, entry.punch_out_seconds, entry.actor, entry.occurred_at)
        for entry in logged
    ] == [
        (7220.0, 9812.0, "the reviewer", first.occurred_at),
        (7220.0, 9850.0, "the reviewer", second.occurred_at),
    ]


def test_a_superseded_proposal_keeps_the_cuts_it_proposed(store, graph):
    segment = store.saves(minimal_segment(graph["recording"]))
    proposed = store.saves(minimal_proposal(segment))
    store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="boundaries_proposed",
            segment_id=segment.segment_id,
            proposal_id=proposed.proposal_id,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
        )
    )
    fresh = store.saves(minimal_proposal(segment))
    store.saves(replace(proposed, superseded_by=fresh.proposal_id))
    logged = store.lists(LogEntry, proposal_id=proposed.proposal_id)
    assert [(entry.punch_in_seconds, entry.punch_out_seconds) for entry in logged] == [
        (7220.0, 9812.0)
    ]


def test_each_logged_set_of_boundaries_records_whether_it_was_proposed_or_refined(store, graph):
    segment = store.saves(minimal_segment(graph["recording"]))
    proposed = store.saves(minimal_proposal(segment))
    boundaries = replace(
        minimal_log_entry(graph["recording"]),
        kind="boundaries_proposed",
        segment_id=segment.segment_id,
        proposal_id=proposed.proposal_id,
        punch_in_seconds=7220.0,
        punch_out_seconds=9812.0,
        boundary_source="model",
    )
    store.saves(boundaries)
    store.saves(
        replace(
            boundaries,
            log_entry_id=None,
            kind="boundaries_refined",
            occurred_at=datetime(2026, 9, 13, 9, 3, tzinfo=UTC),
            punch_in_seconds=7216.5,
            boundary_source="model-in/refined-out",
        )
    )
    store.saves(replace(segment, punch_in_seconds=7210.0, boundary_source="human"))
    logged = store.lists(LogEntry, segment_id=segment.segment_id)
    assert [(entry.punch_in_seconds, entry.boundary_source) for entry in logged] == [
        (7220.0, "model"),
        (7216.5, "model-in/refined-out"),
    ]


def test_a_discarded_adjustment_is_kept_in_the_history(store, graph):
    segment = store.saves(minimal_segment(graph["recording"]))
    adjusted = store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="punch_in_adjusted",
            segment_id=segment.segment_id,
            actor="the reviewer",
            punch_in_seconds=7216.5,
        )
    )
    store.saves(
        replace(
            adjusted,
            log_entry_id=None,
            kind="adjustment_discarded",
            occurred_at=datetime(2026, 9, 13, 11, 6, tzinfo=UTC),
            punch_in_seconds=7220.0,
        )
    )
    logged = store.lists(LogEntry, segment_id=segment.segment_id)
    assert [(entry.kind, entry.punch_in_seconds) for entry in logged] == [
        ("punch_in_adjusted", 7216.5),
        ("adjustment_discarded", 7220.0),
    ]


def test_a_past_render_is_reproducible_from_the_boundaries_and_settings_it_used(store, graph):
    rendered = store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="rendered",
            segment_id=graph["segment"].segment_id,
            artifact_id=graph["artifact"].artifact_id,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
        )
    )
    stored = reloaded(store, rendered, "log_entry")
    render = store.loads(Artifact, stored.artifact_id)
    assert (stored.punch_in_seconds, stored.punch_out_seconds, render.render_settings) == (
        7220.0,
        9812.0,
        graph["artifact"].render_settings,
    )


def test_analysis_records_an_alternative_punch_in_candidate_and_why_it_was_considered(store, graph):
    alternative = Candidate(
        timecode=6890.0, considered_because="4.2 s of quiet before “good morning”"
    )
    proposal = store.saves(replace(graph["proposal"], punch_in_candidates=(alternative,)))
    assert reloaded(store, proposal, "proposal").punch_in_candidates == (alternative,)


def test_alternative_punch_in_candidates_are_kept_in_the_order_analysis_ranked_them(store, graph):
    ranked = (
        Candidate(timecode=6890.0, considered_because="4.2 s of quiet before “good morning”"),
        Candidate(timecode=6842.0, considered_because="the end of the preceding prayer"),
    )
    proposal = store.saves(replace(graph["proposal"], punch_in_candidates=ranked))
    assert reloaded(store, proposal, "proposal").punch_in_candidates == ranked


def test_the_last_webhook_and_the_last_scan_are_each_recorded_with_what_they_found(store):
    webhook = store.saves(received_webhook())
    scan = store.saves(completed_scan())
    assert store.lists(Discovery) == [scan, webhook]
    assert [(one.kind, one.discovered_count) for one in store.lists(Discovery)] == [
        ("scan", 2),
        ("webhook", 1),
    ]


def test_a_scan_that_could_not_reach_the_object_store_is_recorded_as_having_found_nothing(
    store, graph
):
    failed = store.saves(
        replace(
            graph["discovery"],
            kind="scan",
            occurred_at=datetime(2026, 9, 20, 3, 0, tzinfo=UTC),
            discovered_count=0,
            failure="transient",
            event=None,
        )
    )
    stored = reloaded(store, failed, "discovery")
    assert (stored.kind, stored.discovered_count, stored.failure, stored.event) == (
        "scan",
        0,
        "transient",
        None,
    )
    assert stored.occurred_at == datetime(2026, 9, 20, 3, 0, tzinfo=UTC)


def test_a_credential_problem_is_distinguishable_from_a_transient_failure(store):
    store.saves(replace(completed_scan(), discovered_count=0, failure="transient"))
    store.saves(
        replace(
            completed_scan(),
            occurred_at=datetime(2026, 9, 20, 3, 0, tzinfo=UTC),
            discovered_count=0,
            failure="credentials",
        )
    )
    assert [one.failure for one in store.lists(Discovery)] == ["transient", "credentials"]


def test_a_scan_that_ran_to_the_end_records_no_failure(store):
    assert store.loads(Discovery, store.saves(completed_scan()).discovery_id).failure is None


def test_a_webhook_the_processor_does_not_handle_records_the_event_type_it_ignored(store):
    ignored = store.saves(
        replace(received_webhook(), event="recording.started", discovered_count=0)
    )
    stored = store.loads(Discovery, ignored.discovery_id)
    assert (stored.event, stored.discovered_count) == ("recording.started", 0)
    assert store.lists(Recording) == []


def test_a_scan_carries_no_event_type_because_nothing_announced_it(store):
    assert store.loads(Discovery, store.saves(completed_scan()).discovery_id).event is None


def test_a_webhook_does_not_carry_a_failure_only_a_scan_can_have(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(received_webhook(), failure="credentials"))
    assert everything_stored(store, tmp_path) == stored


def test_a_scan_does_not_carry_an_event_type_only_a_webhook_announces(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(completed_scan(), event="recording.uploaded"))
    assert everything_stored(store, tmp_path) == stored


def test_a_scan_that_failed_does_not_also_report_recordings_it_discovered(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(completed_scan(), failure="transient", discovered_count=99))
    assert everything_stored(store, tmp_path) == stored


def test_an_alert_about_the_system_itself_is_raised_against_no_recording(store):
    raised = store.saves(system_alert())
    stored = store.loads(Notification, raised.notification_id)
    assert (stored.recording_id, stored.segment_id) == (None, None)
    assert store.lists(Recording) == []


def test_an_alert_about_the_system_is_not_listed_among_a_recordings_notifications(store, graph):
    alert = store.saves(system_alert())
    assert store.lists(Notification, recording_id=None) == [alert]
    listed = store.lists(Notification, recording_id=graph["recording"].recording_id)
    assert listed == [graph["notification"]]


def test_a_notification_about_a_segment_names_the_recording_the_segment_belongs_to(
    store, graph, tmp_path
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["notification"], notification_id=None, recording_id=None))
    assert everything_stored(store, tmp_path) == stored


def test_an_object_the_scan_skipped_is_recorded_with_its_key_and_reason(store):
    skipped = store.saves(skipped_object())
    assert store.loads(SkippedObject, skipped.object_key) == skipped


def test_an_operator_can_see_every_object_the_processor_has_ever_skipped(store):
    for key, reason in SKIPPED_OBJECTS:
        store.saves(SkippedObject(object_key=key, reason=reason))
    listed = store.lists(SkippedObject)
    assert {(one.object_key, one.reason) for one in listed} == set(SKIPPED_OBJECTS)


def test_a_key_no_recording_could_be_built_from_is_still_recorded_as_skipped(store):
    skipped = store.saves(skipped_object())
    assert store.lists(Recording) == []
    assert store.loads(SkippedObject, skipped.object_key).reason == "recorder clock not set"


def test_an_object_skipped_again_for_another_reason_is_not_listed_twice(store):
    store.saves(skipped_object())
    reconsidered = store.saves(replace(skipped_object(), reason="not an audio object"))
    assert store.lists(SkippedObject) == [reconsidered]


def test_the_derived_boundaries_are_stored_as_the_expected_answer_for_that_pair(store):
    recording = store.saves(minimal_recording())
    saved = store.saves(labelled_corpus_pair(recording))
    stored = store.loads(CorpusPair, saved.corpus_pair_id)
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (1000.0, 3999.61)


def test_a_pair_that_cannot_be_aligned_is_excluded_from_the_corpus_and_the_exclusion_is_reported(
    store,
):
    recording = store.saves(minimal_recording())
    excluded = store.saves(
        CorpusPair(
            recording_id=recording.recording_id,
            classification="sermon",
            alignment="cannot be aligned",
            provenance="human",
        )
    )
    stored = store.loads(CorpusPair, excluded.corpus_pair_id)
    assert stored.alignment == "cannot be aligned"
    assert (stored.punch_in_seconds, stored.punch_out_seconds, stored.drift_ppm) == (None, None, None)
    assert store.lists(CorpusPair) == [excluded]


def test_the_drift_is_measured_rather_than_averaged_away(store):
    recording = store.saves(minimal_recording())
    saved = store.saves(labelled_corpus_pair(recording))
    stored = store.loads(CorpusPair, saved.corpus_pair_id)
    assert stored.drift_ppm == -130.0
    assert stored.punch_in_seconds == 1000.0
    assert stored.punch_out_seconds == 1000.0 + 3000.0 * (1 + stored.drift_ppm / 1_000_000)


def test_a_pair_whose_probes_do_not_fall_on_a_straight_line_is_excluded_as_not_a_contiguous_excerpt(
    store,
):
    recording = store.saves(minimal_recording())
    excluded = store.saves(
        CorpusPair(
            recording_id=recording.recording_id,
            classification="sermon",
            alignment="not a contiguous excerpt",
            provenance="human",
        )
    )
    stored = store.loads(CorpusPair, excluded.corpus_pair_id)
    assert stored.alignment == "not a contiguous excerpt"
    assert (stored.punch_in_seconds, stored.punch_out_seconds, stored.drift_ppm) == (None, None, None)
    assert store.lists(CorpusPair) == [excluded]


def test_a_published_output_that_covers_more_than_95_percent_of_its_source_is_flagged_rather_than_silently_accepted(
    store,
):
    recording = store.saves(minimal_recording())
    flagged = store.saves(
        replace(labelled_corpus_pair(recording), covers_more_than_95_percent=True)
    )
    stored = store.loads(CorpusPair, flagged.corpus_pair_id)
    assert stored.covers_more_than_95_percent is True
    labelled = [
        pair
        for pair in store.lists(CorpusPair)
        if pair.alignment == "aligned"
        and pair.provenance == "human"
        and not pair.covers_more_than_95_percent
    ]
    assert labelled == []


def test_a_published_output_the_system_produced_itself_stores_its_provenance_and_is_excluded_from_ground_truth(
    store,
):
    recording = store.saves(minimal_recording())
    published = store.saves(machine_cut_corpus_pair(recording))
    stored = store.loads(CorpusPair, published.corpus_pair_id)
    assert stored.provenance == "machine"
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (None, None)
    assert (stored.punch_in_difficulty, stored.punch_out_difficulty) == (None, None)
    labelled = [
        pair
        for pair in store.lists(CorpusPair)
        if pair.provenance == "human" and pair.alignment == "aligned"
    ]
    assert labelled == []
    assert store.lists(CorpusPair) == [published]


def test_the_corpus_includes_sermons_and_class_sessions(store):
    recording = store.saves(minimal_recording())
    sermon = store.saves(labelled_corpus_pair(recording, classification="sermon"))
    lesson = store.saves(
        replace(
            labelled_corpus_pair(recording, classification="lesson"),
            punch_in_seconds=61.5,
            punch_out_seconds=3497.25,
        )
    )
    listed = store.lists(CorpusPair, recording_id=recording.recording_id)
    assert {pair.classification for pair in listed} == {"sermon", "lesson"}
    assert {pair.corpus_pair_id for pair in listed} == {sermon.corpus_pair_id, lesson.corpus_pair_id}


def test_the_machines_grade_of_its_cut_and_the_ground_truth_difficulty_are_separately_named():
    proposal = {field.name for field in fields(Proposal)}
    corpus = {field.name for field in fields(CorpusPair)}
    assert {"punch_in_grade", "punch_out_grade"} <= proposal
    assert {"punch_in_difficulty", "punch_out_difficulty"} <= corpus
    assert proposal.isdisjoint({"punch_in_difficulty", "punch_out_difficulty"})
    assert corpus.isdisjoint({"punch_in_grade", "punch_out_grade"})


def test_each_pair_is_graded_against_the_difficulty_of_its_own_transition(store):
    recording = store.saves(minimal_recording())
    saved = store.saves(
        replace(
            labelled_corpus_pair(recording),
            punch_in_difficulty="easy",
            punch_out_difficulty="hard",
        )
    )
    stored = store.loads(CorpusPair, saved.corpus_pair_id)
    assert (stored.punch_in_difficulty, stored.punch_out_difficulty) == ("easy", "hard")


def test_a_recording_and_the_approved_boundaries_can_be_added_to_the_corpus(store, graph):
    saved = store.saves(
        CorpusPair(
            recording_id=graph["recording"].recording_id,
            classification=graph["segment"].classification,
            alignment="aligned",
            punch_in_seconds=graph["segment"].punch_in_seconds,
            punch_out_seconds=graph["segment"].punch_out_seconds,
            punch_in_difficulty="easy",
            punch_out_difficulty="hard",
            provenance="human",
        )
    )
    stored = store.loads(CorpusPair, saved.corpus_pair_id)
    assert stored.recording_id == graph["recording"].recording_id
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (
        graph["segment"].punch_in_seconds,
        graph["segment"].punch_out_seconds,
    )


def test_an_untouched_approval_does_not_become_a_labelled_example(store):
    recording = store.saves(minimal_recording())
    published = store.saves(machine_cut_corpus_pair(recording))
    stored = store.loads(CorpusPair, published.corpus_pair_id)
    assert stored.provenance == "machine"
    labelled = [
        pair
        for pair in store.lists(CorpusPair)
        if pair.provenance == "human"
        and pair.punch_in_seconds is not None
        and pair.punch_in_difficulty is not None
    ]
    assert labelled == []


def test_one_recording_can_yield_two_published_outputs(store):
    recording = store.saves(minimal_recording())
    lesson = store.saves(labelled_corpus_pair(recording, classification="lesson"))
    sermon = store.saves(
        replace(
            labelled_corpus_pair(recording, classification="sermon"),
            punch_in_seconds=3600.0,
            punch_out_seconds=7200.0,
        )
    )
    listed = store.lists(CorpusPair, recording_id=recording.recording_id)
    assert [pair.classification for pair in listed] == ["lesson", "sermon"]
    assert {pair.corpus_pair_id for pair in listed} == {lesson.corpus_pair_id, sermon.corpus_pair_id}


def test_two_identical_labelled_sermon_pairs_for_one_recording_are_not_listed_twice(store):
    recording = store.saves(minimal_recording())
    store.saves(labelled_corpus_pair(recording))
    again = store.saves(labelled_corpus_pair(recording))
    assert store.lists(CorpusPair) == [again]


def test_a_machine_cut_and_a_labelled_sermon_for_the_same_recording_both_remain(store):
    recording = store.saves(minimal_recording())
    labelled = store.saves(labelled_corpus_pair(recording))
    published = store.saves(machine_cut_corpus_pair(recording))
    listed = store.lists(CorpusPair, recording_id=recording.recording_id)
    assert {pair.provenance for pair in listed} == {"human", "machine"}
    assert {pair.corpus_pair_id for pair in listed} == {
        labelled.corpus_pair_id,
        published.corpus_pair_id,
    }


def test_saving_a_corpus_pair_again_corrects_the_fit_it_already_wrote(store):
    recording = store.saves(minimal_recording())
    saved = store.saves(labelled_corpus_pair(recording))
    corrected = store.saves(
        replace(
            saved,
            drift_ppm=-131.6,
            punch_in_seconds=1228.788,
            punch_out_seconds=4228.393,
            punch_in_difficulty="hard",
            covers_more_than_95_percent=True,
        )
    )
    assert store.lists(CorpusPair) == [corrected]
    stored = store.loads(CorpusPair, saved.corpus_pair_id)
    assert (stored.drift_ppm, stored.punch_in_seconds, stored.punch_out_seconds) == (
        -131.6,
        1228.788,
        4228.393,
    )
    assert (stored.punch_in_difficulty, stored.covers_more_than_95_percent) == ("hard", True)


def test_a_pair_that_cannot_be_aligned_does_not_carry_derived_boundaries(store, tmp_path):
    recording = store.saves(minimal_recording())
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(
            replace(
                labelled_corpus_pair(recording),
                alignment="cannot be aligned",
                drift_ppm=None,
            )
        )
    assert everything_stored(store, tmp_path) == stored


def test_a_pair_that_is_not_a_contiguous_excerpt_does_not_carry_derived_boundaries(
    store, tmp_path
):
    recording = store.saves(minimal_recording())
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(
            replace(
                labelled_corpus_pair(recording),
                alignment="not a contiguous excerpt",
                drift_ppm=None,
            )
        )
    assert everything_stored(store, tmp_path) == stored


def test_a_published_output_the_system_produced_does_not_carry_an_expected_answer(
    store, tmp_path
):
    recording = store.saves(minimal_recording())
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(labelled_corpus_pair(recording), provenance="machine"))
    assert everything_stored(store, tmp_path) == stored


def test_a_machine_cut_does_not_carry_an_alignment_only_a_human_edit_has(store, tmp_path):
    recording = store.saves(minimal_recording())
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(machine_cut_corpus_pair(recording), alignment="aligned"))
    assert everything_stored(store, tmp_path) == stored


def test_a_corpus_pair_cannot_belong_to_a_recording_that_does_not_exist(store, graph, tmp_path):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(
            replace(
                graph["corpus_pair"],
                corpus_pair_id=None,
                recording_id="recording_20000101_000000",
            )
        )
    assert everything_stored(store, tmp_path) == stored


def test_a_labelled_pair_cannot_be_rewritten_as_a_machine_cut_that_keeps_its_expected_answer(
    store, graph, tmp_path
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["corpus_pair"], provenance="machine"))
    assert everything_stored(store, tmp_path) == stored


def test_a_labelled_pair_cannot_be_rewritten_as_unaligned_while_keeping_its_boundaries(
    store, graph, tmp_path
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph["corpus_pair"], alignment="cannot be aligned"))
    assert everything_stored(store, tmp_path) == stored


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
    base = replace(graph[name], **COMPANIONS.get((name, column), {}))
    for value in allowed:
        saved = store.saves(replace(base, **{column: value}))
        assert getattr(reloaded(store, saved, name), column) == value


@pytest.mark.parametrize("name, field, allowed", CLOSED_COLLECTIONS)
def test_a_closed_collection_refuses_a_value_the_spec_does_not_declare(
    store, graph, tmp_path, name, field, allowed
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph[name], **{field: ("whatever the caller felt like",)}))
    assert everything_stored(store, tmp_path) == stored


@pytest.mark.parametrize("name, field, allowed", CLOSED_COLLECTIONS)
def test_a_closed_collection_holds_every_value_the_spec_declares_at_once(
    store, graph, name, field, allowed
):
    saved = store.saves(replace(graph[name], **{field: allowed}))
    assert getattr(reloaded(store, saved, name), field) == allowed


@pytest.mark.parametrize("name, field, allowed", CLOSED_COLLECTIONS)
def test_a_set_shaped_collection_refuses_the_same_value_twice(
    store, graph, tmp_path, name, field, allowed
):
    stored = everything_stored(store, tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(replace(graph[name], **{field: (allowed[0], allowed[0])}))
    assert everything_stored(store, tmp_path) == stored


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
        store.saves(
            replace(
                minimal_block(graph["recording"]),
                speaker_matches=(SpeakerMatch(speaker_profile_id=404, similarity=0.94),),
            )
        )
    assert everything_stored(store, tmp_path) == stored


def test_a_refused_write_does_not_become_durable_when_a_later_one_commits(store, graph, tmp_path):
    with pytest.raises(sqlite3.IntegrityError):
        store.saves(
            replace(
                minimal_block(graph["recording"]),
                speaker_matches=(SpeakerMatch(speaker_profile_id=404, similarity=0.94),),
            )
        )
    later = store.saves(minimal_block(graph["recording"]))
    seen = [row[0] for row in rows_another_connection_sees(tmp_path)["block"]]
    assert seen == [graph["block"].block_id, later.block_id]


def test_reverting_to_the_machine_proposal_reads_the_cuts_that_proposal_carries(store, graph):
    segment = store.saves(minimal_segment(graph["recording"]))
    proposed = store.saves(minimal_proposal(segment))
    store.saves(
        replace(
            minimal_log_entry(graph["recording"]),
            kind="boundaries_proposed",
            segment_id=segment.segment_id,
            proposal_id=proposed.proposal_id,
            punch_in_seconds=7220.0,
            punch_out_seconds=9812.0,
            boundary_source="model",
        )
    )
    adjusted = store.saves(replace(segment, punch_in_seconds=7216.5, boundary_source="human"))
    current = store.lists(Proposal, segment_id=adjusted.segment_id, superseded_by=None)
    machine = store.lists(LogEntry, proposal_id=current[-1].proposal_id)[-1]
    reverted = store.saves(
        replace(
            adjusted,
            punch_in_seconds=machine.punch_in_seconds,
            punch_out_seconds=machine.punch_out_seconds,
            boundary_source=machine.boundary_source,
        )
    )
    assert (reverted.punch_in_seconds, reverted.punch_out_seconds, reverted.boundary_source) == (
        7220.0,
        9812.0,
        "model",
    )


def test_a_recording_keeps_no_copy_of_the_codec_its_key_already_names(store):
    with pytest.raises(ValueError):
        store.lists(Recording, codec="flac")


def test_a_segment_keeps_no_second_copy_of_the_cuts_the_machine_proposed(store):
    with pytest.raises(ValueError):
        store.lists(Segment, proposed_punch_in=63.125)


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
