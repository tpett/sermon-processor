from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sermon.cli import organizes
from sermon.organizes_data_root import (
    COLLIDES,
    IN_PLACE,
    MOVED,
    NO_FILE,
    REFUSED,
    ROW_REPAIRED,
    OrganizesDataRoot,
)
from sermon.store import Artifact, Recording, Segment, layout, opens_store
from sermon.web import creates_app

STARTED = datetime(2026, 9, 13, 9, 0, 14, tzinfo=UTC)
RECORDING_ID = "recording_20260913_090014"
OBJECT_KEY = f"{RECORDING_ID}.flac"
PUBLISHED = "2026-09-13 - Hebrews 12.25-29.mp3"
FLAC = b"fLaC" + bytes(28)


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def store(data_root):
    opened = opens_store(data_root)
    yield opened
    opened.close()


def organises(store, data_root, **held):
    return OrganizesDataRoot(store=store, data_root=data_root, **held)()


def outcomes(relocations):
    return {relocation.now: relocation.outcome for relocation in relocations}


def plants(data_root, path, body=b"stub"):
    held = data_root / path
    held.parent.mkdir(parents=True, exist_ok=True)
    held.write_bytes(body)
    return held


def legacy_recording(store, data_root, *, downloaded=True):
    """A Recording stored the way the first writer to reach it stored it."""
    recording = store.saves(
        Recording(
            recording_id=RECORDING_ID,
            object_key=OBJECT_KEY,
            state="reviewed",
            started_at=STARTED,
            started_at_source="key",
            size_bytes=len(FLAC),
            duration_seconds=5412.4,
            local_path=OBJECT_KEY if downloaded else None,
        )
    )
    if downloaded:
        plants(data_root, OBJECT_KEY, FLAC)
    return recording


def legacy_segment(store, recording):
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="complete",
            span_start_seconds=0.0,
            span_end_seconds=60.0,
            punch_in_seconds=0.0,
            punch_out_seconds=60.0,
            label="Hebrews 12.25-29",
        )
    )


def legacy_artifact(store, data_root, recording, kind, path, *, segment=None, planted=True):
    if planted:
        plants(data_root, path)
    return store.saves(
        Artifact(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id if segment else None,
            kind=kind,
            path=path,
            size_bytes=4,
            checksum="stub",
        )
    )


def legacy_root(store, data_root):
    recording = legacy_recording(store, data_root)
    segment = legacy_segment(store, recording)
    legacy_artifact(store, data_root, recording, "rendered_mp3", PUBLISHED, segment=segment)
    legacy_artifact(
        store, data_root, recording, "transcript", f"{RECORDING_ID}/transcript.json"
    )
    legacy_artifact(store, data_root, recording, "preview", f"{RECORDING_ID}/preview.mp3")
    plants(data_root, f"{RECORDING_ID}/{layout.PROGRESS}")
    return recording


def test_an_empty_root_gets_the_skeleton_and_nothing_moves(store, data_root):
    assert organises(store, data_root) == ()
    assert sorted(
        held.relative_to(data_root).as_posix() for held in data_root.rglob("*") if held.is_dir()
    ) == ["corpus", "corpus/diarization", "published", "recordings"]


def test_the_source_moves_under_its_own_recording_and_the_row_follows(store, data_root):
    recording = legacy_recording(store, data_root)
    organises(store, data_root)
    stored = store.loads(Recording, recording.recording_id)
    assert stored.local_path == f"recordings/{RECORDING_ID}/source.flac"
    assert store.resolves(stored).read_bytes() == FLAC
    assert not (data_root / OBJECT_KEY).exists()


def test_the_sidecar_travels_with_the_source_it_describes(store, data_root):
    recording = legacy_recording(store, data_root)
    plants(data_root, f"{OBJECT_KEY}.meta.json", b"{}")
    organises(store, data_root)
    stored = store.loads(Recording, recording.recording_id)
    assert store.resolves(stored).with_name("source.flac.meta.json").read_bytes() == b"{}"


def test_a_rendered_mp3_keeps_its_name_and_moves_under_published(store, data_root):
    legacy_root(store, data_root)
    organises(store, data_root)
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    assert artifact.path == f"published/{PUBLISHED}"
    assert store.resolves(artifact).is_file()


def test_every_document_of_a_recording_moves_under_recordings(store, data_root):
    legacy_root(store, data_root)
    organises(store, data_root)
    assert {artifact.kind: artifact.path for artifact in store.lists(Artifact)} == {
        "rendered_mp3": f"published/{PUBLISHED}",
        "transcript": f"recordings/{RECORDING_ID}/transcript.json",
        "preview": f"recordings/{RECORDING_ID}/preview.mp3",
    }
    for artifact in store.lists(Artifact):
        assert store.resolves(artifact).is_file()


def test_a_file_no_row_owns_goes_with_the_recording_it_belongs_to(store, data_root):
    legacy_root(store, data_root)
    relocations = organises(store, data_root)
    assert (data_root / "recordings" / RECORDING_ID / layout.PROGRESS).is_file()
    assert not (data_root / RECORDING_ID).exists()
    assert outcomes(relocations)[f"recordings/{RECORDING_ID}/{layout.PROGRESS}"] == MOVED


def test_the_pipelines_diarization_root_moves_under_the_corpus(store, data_root):
    legacy_root(store, data_root)
    plants(data_root, f"{layout.DIARIZATION}/{RECORDING_ID}.json", b'{"turns": []}')
    organises(store, data_root)
    assert (data_root / "corpus" / "diarization" / f"{RECORDING_ID}.json").is_file()
    assert not (data_root / layout.DIARIZATION).exists()


def test_the_model_cache_and_the_database_are_left_where_they_are(store, data_root):
    legacy_root(store, data_root)
    plants(data_root, f"{layout.MODELS}/hub/weights.bin", b"weights")
    organises(store, data_root)
    assert (data_root / layout.MODELS / "hub" / "weights.bin").read_bytes() == b"weights"
    assert (data_root / "sermon.sqlite3").is_file()


def test_running_it_twice_moves_nothing_the_second_time(store, data_root):
    legacy_root(store, data_root)
    organises(store, data_root)
    before = sorted(held.relative_to(data_root).as_posix() for held in data_root.rglob("*"))
    again = organises(store, data_root)
    assert {relocation.outcome for relocation in again} == {IN_PLACE}
    assert sorted(held.relative_to(data_root).as_posix() for held in data_root.rglob("*")) == before


def test_a_run_interrupted_after_the_move_is_repaired_by_the_next_one(store, data_root):
    recording = legacy_recording(store, data_root)
    moved = layout.source_path(recording)
    store.resolves_path(moved).parent.mkdir(parents=True)
    (data_root / OBJECT_KEY).rename(store.resolves_path(moved))
    relocations = organises(store, data_root)
    assert outcomes(relocations)[moved] == ROW_REPAIRED
    assert store.loads(Recording, recording.recording_id).local_path == moved
    assert store.resolves(store.loads(Recording, recording.recording_id)).read_bytes() == FLAC


def test_a_row_whose_file_was_never_written_is_still_rewritten(store, data_root):
    recording = legacy_recording(store, data_root, downloaded=False)
    legacy_artifact(
        store, data_root, recording, "envelope", f"{RECORDING_ID}/envelope", planted=False
    )
    relocations = organises(store, data_root)
    assert outcomes(relocations) == {f"recordings/{RECORDING_ID}/envelope.json": NO_FILE}
    assert store.lists(Artifact)[0].path == f"recordings/{RECORDING_ID}/envelope.json"


def test_two_rows_wanting_one_destination_are_refused_rather_than_merged(store, data_root):
    recording = legacy_recording(store, data_root, downloaded=False)
    legacy_artifact(store, data_root, recording, "transcript", f"{RECORDING_ID}/transcript.json")
    legacy_artifact(store, data_root, recording, "transcript", "transcript.json")
    relocations = organises(store, data_root)
    assert COLLIDES in {relocation.outcome for relocation in relocations}
    assert (data_root / "transcript.json").is_file()


def test_a_stored_path_that_escapes_the_data_root_is_refused(store, data_root):
    recording = legacy_recording(store, data_root, downloaded=False)
    artifact = legacy_artifact(
        store, data_root, recording, "transcript", f"{RECORDING_ID}/transcript.json", planted=False
    )
    store._connection.execute(
        "UPDATE artifact SET path = ? WHERE artifact_id = ?",
        ("../../etc/passwd", artifact.artifact_id),
    )
    store._connection.commit()
    relocations = organises(store, data_root)
    assert [relocation.outcome for relocation in relocations] == [REFUSED]
    assert store.lists(Artifact)[0].path == "../../etc/passwd"


def test_a_dry_run_reports_the_whole_move_and_changes_nothing(store, data_root):
    legacy_root(store, data_root)
    before = sorted(held.relative_to(data_root).as_posix() for held in data_root.rglob("*"))
    relocations = organises(store, data_root, dry_run=True)
    assert {relocation.outcome for relocation in relocations} == {MOVED}
    assert sorted(held.relative_to(data_root).as_posix() for held in data_root.rglob("*")) == before
    assert store.loads(Recording, RECORDING_ID).local_path == OBJECT_KEY


def test_a_link_handed_out_before_the_move_still_downloads(store, data_root):
    legacy_root(store, data_root)
    organises(store, data_root)
    client = creates_app(store=store).test_client()
    for legacy in (PUBLISHED, f"{RECORDING_ID}/preview.mp3", OBJECT_KEY):
        assert client.get(f"/api/artifacts/{legacy}").status_code == 200


def test_a_name_two_recordings_could_both_claim_resolves_to_neither(store, data_root):
    recording = legacy_root(store, data_root)
    other = store.saves(
        replace(
            recording,
            recording_id="recording_20260920_094416",
            object_key="recording_20260920_094416.flac",
            local_path=None,
        )
    )
    legacy_artifact(store, data_root, other, "preview", f"{other.recording_id}/preview.mp3")
    organises(store, data_root)
    assert creates_app(store=store).test_client().get("/api/artifacts/preview.mp3").status_code == 404


def test_the_command_reports_what_it_moved_and_succeeds(store, data_root):
    legacy_root(store, data_root)
    store.close()
    lines = []
    assert organizes(
        settings={"SERMON_DATA_ROOT": str(data_root)}, arguments=[], prints=lines.append
    ) == 0
    reported = "\n".join(lines)
    assert f"{PUBLISHED} -> published/{PUBLISHED} ({MOVED})" in reported
    assert "5 moved" in reported


def test_the_command_refuses_a_data_root_nothing_names(store, data_root):
    lines = []
    assert organizes(settings={}, arguments=[], prints=lines.append) == 1
    assert "nothing sets SERMON_DATA_ROOT" in "\n".join(lines)


def test_the_command_reports_a_relative_data_root_rather_than_guessing(store, data_root):
    lines = []
    assert organizes(
        settings={"SERMON_DATA_ROOT": "data"}, arguments=[], prints=lines.append
    ) == 1
    assert "moves with the working directory" in "\n".join(lines)


def test_the_command_exits_non_zero_when_it_refused_something(store, data_root):
    recording = legacy_recording(store, data_root, downloaded=False)
    legacy_artifact(store, data_root, recording, "transcript", f"{RECORDING_ID}/transcript.json")
    legacy_artifact(store, data_root, recording, "transcript", "transcript.json")
    store.close()
    lines = []
    assert organizes(
        settings={"SERMON_DATA_ROOT": str(data_root)}, arguments=[], prints=lines.append
    ) == 1
    assert COLLIDES in "\n".join(lines)
