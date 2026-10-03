import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sermon.analysis.io import writes_json
from sermon.analysis.proposes_from_transcript import ASR_CONFIG
from sermon.cli import (
    ENVIRONMENT_FILE,
    analyzes,
    derives_corpus,
    fetches,
    lists_bucket,
    reconciles,
    regrades,
    renders,
    resolves_settings,
    serves,
)
from sermon.jobs.downloads_recording import FetchesObject
from sermon.object_store import ListsBucketObjects
from sermon.pipeline import classify, segments
from sermon.store import (
    DATABASE_NAME,
    Artifact,
    Block,
    CorpusPair,
    Job,
    Notification,
    Proposal,
    Recording,
    Segment,
    opens_store,
)

ENDPOINT = "https://s3.home.tpett.me"
BUCKET = "reformation-recordings"
ACCESS_KEY_ID = "an-access-key-id-that-is-not-real"
SECRET_ACCESS_KEY = "a-secret-access-key-that-is-not-real"
MODEL_ENDPOINT = "http://mac-m1:11434"
FLAC_BYTES = b"fLaC" + bytes(64)
SEEN = "recordings/recording_20260823_103015.flac"
UNSEEN = "recordings/recording_20260816_102958.flac"
FROZEN = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def settings_file(root, **overrides):
    values = {
        "SERMON_DATA_ROOT": str(root / "data"),
        "SERMON_OBJECT_STORE_ENDPOINT": ENDPOINT,
        "SERMON_OBJECT_STORE_BUCKET": BUCKET,
        "SERMON_OBJECT_STORE_ACCESS_KEY_ID": ACCESS_KEY_ID,
        "SERMON_OBJECT_STORE_SECRET_ACCESS_KEY": SECRET_ACCESS_KEY,
        "SERMON_MODEL_ENDPOINT": MODEL_ENDPOINT,
        **overrides,
    }
    (root / ENVIRONMENT_FILE).write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return values


def bucket_holding(*keys):
    objects = FetchesObject()
    for key in keys:
        objects.stores(key, FLAC_BYTES, last_modified=FROZEN - timedelta(days=1))
    return objects


class RecordsLines:
    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        self.lines.append(str(line))

    def __str__(self):
        return "\n".join(self.lines)


class RecordsServer:
    def __init__(self):
        self.app = None
        self.host = None
        self.port = None

    def __call__(self, app, host, port):
        self.app = app
        self.host = host
        self.port = port


def test_the_environment_file_supplies_every_setting(tmp_path):
    written = settings_file(tmp_path)
    assert resolves_settings(root=tmp_path, environment={}) == written


def test_the_process_environment_wins_over_the_environment_file(tmp_path):
    settings_file(tmp_path)
    resolved = resolves_settings(
        root=tmp_path, environment={"SERMON_OBJECT_STORE_BUCKET": "another-bucket"}
    )
    assert resolved["SERMON_OBJECT_STORE_BUCKET"] == "another-bucket"
    assert resolved["SERMON_OBJECT_STORE_ENDPOINT"] == ENDPOINT


def test_blank_lines_comments_and_quotes_are_not_settings(tmp_path):
    (tmp_path / ENVIRONMENT_FILE).write_text(
        '\n# the endpoint\nSERMON_OBJECT_STORE_BUCKET="quoted-bucket"\n\n',
        encoding="utf-8",
    )
    assert resolves_settings(root=tmp_path, environment={}) == {
        "SERMON_OBJECT_STORE_BUCKET": "quoted-bucket"
    }


def test_no_environment_file_leaves_the_process_environment_alone(tmp_path):
    assert resolves_settings(root=tmp_path, environment={"SERMON_DATA_ROOT": "/srv"}) == {
        "SERMON_DATA_ROOT": "/srv"
    }


def test_the_listing_is_built_for_the_configured_bucket(tmp_path):
    from sermon.config import ReadsConfiguration

    listing = lists_bucket(ReadsConfiguration(settings_file(tmp_path))())
    assert isinstance(listing, ListsBucketObjects)
    assert listing.bucket == BUCKET


def test_reconciling_discovers_what_the_bucket_holds(tmp_path):
    settings = settings_file(tmp_path)
    assert reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists) == 0
    store = opens_store(settings["SERMON_DATA_ROOT"])
    try:
        assert sorted(item.object_key for item in store.lists(Recording)) == [UNSEEN, SEEN]
    finally:
        store.close()


def test_reconciling_reports_what_it_found(tmp_path):
    prints = RecordsLines()
    reconciles(
        settings=settings_file(tmp_path),
        lists_objects=bucket_holding(SEEN, UNSEEN).lists,
        prints=prints,
    )
    assert BUCKET in str(prints)
    assert "2" in str(prints)


def test_reconciling_reports_a_refused_credential_and_fails(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding(SEEN)
    objects.error = "403 Forbidden"
    outcome = reconciles(
        settings=settings_file(tmp_path), lists_objects=objects.lists, prints=prints
    )
    assert outcome == 1
    assert "credentials" in str(prints)


def test_reconciling_reports_an_unreachable_store_and_fails(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding(SEEN)
    objects.error = "connection reset"
    outcome = reconciles(
        settings=settings_file(tmp_path), lists_objects=objects.lists, prints=prints
    )
    assert outcome == 1
    assert "transient" in str(prints)


def test_reconciling_never_prints_a_credential(tmp_path):
    prints = RecordsLines()
    reconciles(
        settings=settings_file(tmp_path),
        lists_objects=bucket_holding(SEEN).lists,
        prints=prints,
    )
    assert ACCESS_KEY_ID not in str(prints)
    assert SECRET_ACCESS_KEY not in str(prints)


def test_serving_binds_the_configured_host_and_port(tmp_path):
    runs = RecordsServer()
    serves(
        settings=settings_file(tmp_path, SERMON_BIND_HOST="127.0.0.1", SERMON_PORT="8123"),
        lists_objects=bucket_holding().lists,
        runs=runs,
    )
    assert runs.host == "127.0.0.1"
    assert runs.port == 8123


def test_the_served_app_shows_what_reconciliation_discovered(tmp_path):
    settings = settings_file(tmp_path)
    reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists)
    runs = RecordsServer()
    serves(settings=settings, lists_objects=bucket_holding().lists, runs=runs)
    body = runs.app.test_client().get("/api/recordings").get_json()
    assert sorted(row["recording_id"] for row in body["recordings"]) == [
        "recording_20260816_102958",
        "recording_20260823_103015",
    ]


def test_the_served_home_page_names_every_discovered_recording(tmp_path):
    settings = settings_file(tmp_path)
    reconciles(settings=settings, lists_objects=bucket_holding(SEEN, UNSEEN).lists)
    runs = RecordsServer()
    serves(settings=settings, lists_objects=bucket_holding().lists, runs=runs)
    page = runs.app.test_client().get("/").get_data(as_text=True)
    assert "recording_20260823_103015" in page
    assert "recording_20260816_102958" in page


def test_an_incomplete_environment_is_refused_rather_than_guessed(tmp_path):
    from sermon.config import MissingConfiguration

    with pytest.raises(MissingConfiguration):
        reconciles(settings={"SERMON_DATA_ROOT": str(tmp_path)}, lists_objects=lambda: [])


def test_the_served_app_answers_a_request_made_on_another_thread(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    settings = settings_file(tmp_path)
    reconciles(settings=settings, lists_objects=bucket_holding(SEEN).lists)
    runs = RecordsServer()
    serves(settings=settings, lists_objects=bucket_holding().lists, runs=runs)
    with ThreadPoolExecutor(max_workers=1) as pool:
        answered = pool.submit(lambda: runs.app.test_client().get("/").status_code).result()
    assert answered == 200


def real_source(root, seconds=20.0, live_channel=1, sample_rate=44100):
    import subprocess

    import numpy as np

    generator = np.random.default_rng(5)
    samples = int(seconds * sample_rate)
    noise = np.convolve(
        generator.standard_normal(samples).astype(np.float32),
        np.ones(24, dtype=np.float32) / 24,
        mode="same",
    )
    spoken = np.zeros(samples, dtype=np.float32)
    silence = int(0.4 * sample_rate)
    for phrase, start in enumerate(range(0, samples, sample_rate)):
        spoken[start + silence:start + sample_rate] = 0.15 + 0.85 * ((phrase * 3 % 5) / 4.0)
    live = noise * spoken * 0.5 / max(float(np.abs(noise).max()), 1e-9)
    dead = np.zeros(samples, dtype=np.float32)
    channels = [live, dead] if live_channel == 1 else [dead, live]
    raw = root / "source.raw"
    root.mkdir(parents=True, exist_ok=True)
    raw.write_bytes((np.stack(channels, axis=1) * (2 ** 31 - 1)).astype(np.int32).tobytes())
    flac = root / "source.flac"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "s32le", "-ar", str(sample_rate), "-ac", "2",
         "-i", str(raw), "-c:a", "flac", "-sample_fmt", "s32", str(flac)],
        check=True,
    )
    raw.unlink()
    return flac


def bucket_holding_audio(tmp_path, live_channel=1):
    objects = FetchesObject()
    objects.stores(
        SEEN,
        real_source(tmp_path / "made", live_channel=live_channel).read_bytes(),
        last_modified=FROZEN - timedelta(days=1),
    )
    return objects


def test_fetching_streams_the_named_object_into_the_data_root(tmp_path):
    settings = settings_file(tmp_path)
    objects = bucket_holding_audio(tmp_path)
    assert fetches(settings=settings, object_key=SEEN, fetches_object=objects,
                   lists_objects=objects.lists, prints=RecordsLines()) == 0
    assert (tmp_path / "data" / "recordings" / "recording_20260823_103015" / "source.flac").is_file()


def test_fetching_probes_what_it_fetched(tmp_path):
    settings = settings_file(tmp_path)
    objects = bucket_holding_audio(tmp_path)
    fetches(settings=settings, object_key=SEEN, fetches_object=objects,
            lists_objects=objects.lists, prints=RecordsLines())
    store = opens_store(settings["SERMON_DATA_ROOT"])
    try:
        recording = store.lists(Recording)[0]
        assert recording.duration_seconds == pytest.approx(20.0, abs=0.1)
        assert (recording.channels, recording.sample_rate) == (2, 44100)
        assert recording.integrated_loudness_lufs is not None
        assert recording.mono_source == "channel 1"
    finally:
        store.close()


def test_fetching_reports_what_it_measured(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding_audio(tmp_path)
    fetches(settings=settings_file(tmp_path), object_key=SEEN, fetches_object=objects,
            lists_objects=objects.lists, prints=prints)
    reported = str(prints)
    assert "channel 1" in reported
    assert "LUFS" in reported
    assert "44100" in reported


def test_fetching_an_object_the_bucket_does_not_hold_fails(tmp_path):
    objects = bucket_holding_audio(tmp_path)
    assert fetches(settings=settings_file(tmp_path), object_key=UNSEEN,
                   fetches_object=objects, lists_objects=objects.lists,
                   prints=RecordsLines()) == 1


def test_fetching_never_prints_a_credential(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding_audio(tmp_path)
    fetches(settings=settings_file(tmp_path), object_key=SEEN, fetches_object=objects,
            lists_objects=objects.lists, prints=prints)
    assert ACCESS_KEY_ID not in str(prints)
    assert SECRET_ACCESS_KEY not in str(prints)


def ages_the_database(data_root, statement):
    connection = sqlite3.connect(Path(data_root) / DATABASE_NAME)
    with connection:
        connection.execute(statement)
    connection.close()


def test_a_database_the_code_cannot_use_stops_a_render_before_it_fetches(tmp_path):
    settings = settings_file(tmp_path)
    opens_store(settings["SERMON_DATA_ROOT"]).close()
    ages_the_database(
        settings["SERMON_DATA_ROOT"], "ALTER TABLE artifact DROP COLUMN input_loudness_lufs"
    )
    objects = bucket_holding(SEEN)
    prints = RecordsLines()
    outcome = renders(
        settings=settings,
        object_key=SEEN,
        punch_in="0:00:02",
        punch_out="0:00:18",
        label="Hebrews 12.4-11",
        published_on="2026-08-23",
        fetches_object=objects,
        lists_objects=objects.lists,
        prints=prints,
    )
    assert (outcome, objects.fetched) == (1, [])
    assert "input_loudness_lufs" in str(prints)
    assert "sermon-reconcile" in str(prints)


def rendered_by_hand(tmp_path, prints, **overrides):
    objects = bucket_holding_audio(tmp_path, live_channel=overrides.pop("live_channel", 1))
    arguments = {
        "object_key": SEEN,
        "punch_in": "0:00:02",
        "punch_out": "0:00:18",
        "label": "Hebrews 12.4-11",
        "published_on": "2026-08-23",
        **overrides,
    }
    return renders(
        settings=settings_file(tmp_path),
        fetches_object=objects,
        lists_objects=objects.lists,
        prints=prints,
        **arguments,
    )


def test_rendering_a_hand_specified_cut_writes_a_named_mp3(tmp_path):
    prints = RecordsLines()
    rendered_by_hand(tmp_path, prints)
    store = opens_store(str(tmp_path / "data"))
    try:
        artifact = store.lists(Artifact, kind="rendered_mp3")[0]
        assert artifact.path == "published/2026-08-23 - Hebrews 12.4-11.mp3"
        assert store.resolves(artifact).stat().st_size == artifact.size_bytes > 1000
    finally:
        store.close()


def test_rendering_fetches_and_probes_the_source_it_needs(tmp_path):
    rendered_by_hand(tmp_path, RecordsLines())
    store = opens_store(str(tmp_path / "data"))
    try:
        recording = store.lists(Recording)[0]
        assert recording.duration_seconds == pytest.approx(20.0, abs=0.1)
        assert recording.mono_source == "channel 1"
    finally:
        store.close()


def test_rendering_takes_the_channel_the_probe_named(tmp_path):
    rendered_by_hand(tmp_path, RecordsLines(), live_channel=2)
    store = opens_store(str(tmp_path / "data"))
    try:
        assert store.lists(Artifact, kind="rendered_mp3")[0].render_settings["source_channel"] == 2
    finally:
        store.close()


def test_rendering_reports_the_span_and_what_the_output_achieved(tmp_path):
    prints = RecordsLines()
    rendered_by_hand(tmp_path, prints)
    reported = str(prints)
    assert "2026-08-23 - Hebrews 12.4-11.mp3" in reported
    assert "LUFS" in reported
    assert "dBTP" in reported
    assert "kbps" in reported


def test_rendering_records_the_boundaries_a_human_chose(tmp_path):
    rendered_by_hand(tmp_path, RecordsLines())
    store = opens_store(str(tmp_path / "data"))
    try:
        segment = store.lists(Segment)[0]
        assert (segment.punch_in_seconds, segment.punch_out_seconds) == (2.0, 18.0)
        assert segment.boundary_source == "human"
        assert segment.state == "complete"
    finally:
        store.close()


def test_rendering_fails_when_the_output_misses_a_published_target(tmp_path):
    prints = RecordsLines()
    outcome = rendered_by_hand(tmp_path, prints)
    store = opens_store(str(tmp_path / "data"))
    try:
        artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    finally:
        store.close()
    on_target = (
        abs(artifact.output_loudness_lufs + 17.0) <= 1.0
        and artifact.output_true_peak_dbtp <= -1.5
        and 96 <= (artifact.size_bytes * 8) // 16000 <= 108
    )
    assert (outcome == 0) is on_target


def test_rendering_refuses_a_source_whose_channels_were_never_settled(tmp_path):
    prints = RecordsLines()
    settings = settings_file(tmp_path)
    objects = FetchesObject()
    objects.stores(SEEN, stereo_source(tmp_path).read_bytes(),
                   last_modified=FROZEN - timedelta(days=1))
    outcome = renders(
        settings=settings,
        object_key=SEEN,
        punch_in="0:00:02",
        punch_out="0:00:18",
        label="Hebrews 12.4-11",
        published_on="2026-08-23",
        fetches_object=objects,
        lists_objects=objects.lists,
        prints=prints,
    )
    assert outcome == 1
    assert "channel" in str(prints)


def stereo_source(tmp_path):
    import subprocess

    import numpy as np

    sample_rate = 44100
    generator = np.random.default_rng(9)
    samples = int(20.0 * sample_rate)
    both = [
        np.convolve(
            generator.standard_normal(samples).astype(np.float32),
            np.ones(24, dtype=np.float32) / 24,
            mode="same",
        ) * 0.2
        for _ in range(2)
    ]
    root = tmp_path / "stereo"
    root.mkdir(parents=True, exist_ok=True)
    raw = root / "source.raw"
    raw.write_bytes((np.stack(both, axis=1) * (2 ** 31 - 1)).astype(np.int32).tobytes())
    flac = root / "source.flac"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "s32le", "-ar", str(sample_rate), "-ac", "2",
         "-i", str(raw), "-c:a", "flac", "-sample_fmt", "s32", str(flac)],
        check=True,
    )
    raw.unlink()
    return flac


def test_fetching_reports_a_scan_that_could_not_reach_the_store(tmp_path):
    prints = RecordsLines()
    objects = bucket_holding_audio(tmp_path)
    objects.error = "connection reset"
    assert fetches(settings=settings_file(tmp_path), object_key=SEEN,
                   fetches_object=objects, lists_objects=objects.lists,
                   prints=prints) == 1
    assert "failed" in str(prints)
    assert "holds no" not in str(prints)


def test_rendering_an_object_the_bucket_does_not_hold_fails(tmp_path):
    prints = RecordsLines()
    assert rendered_by_hand(tmp_path, prints, object_key=UNSEEN) == 1
    assert f"holds no {UNSEEN}" in str(prints)


ANALYZED = "recording_20260412_102318"


@pytest.fixture
def injected_roots():
    held = (classify.ENDPOINT, classify.DATA, classify.PROMPTS, segments.DATA_ROOT)
    yield
    classify.ENDPOINT, classify.DATA, classify.PROMPTS, segments.DATA_ROOT = held


def spoken_service():
    return {
        "recording_id": ANALYZED,
        "duration": 4200.0,
        "started_at": "2026-04-12T10:23:18",
        "utterances": [
            {
                "start": float(start),
                "end": float(start) + 20.0,
                "text": "Good morning, church. Amen.",
                "words": [{"w": "morning", "start": float(start), "end": float(start) + 1.0}],
            }
            for start in range(0, 4200, 60)
        ],
        "silences": [],
    }


def reasoned_blocks(_doc=None):
    return {
        "blocks": [
            {"start": 0.0, "end": 600.0, "type": "music", "confidence": 0.9},
            {"start": 600.0, "end": 3600.0, "type": "sermon", "confidence": 0.9},
            {"start": 3600.0, "end": 3900.0, "type": "prayer", "confidence": 0.9},
        ],
        "model_segments": [{"punch_in": 600.0, "punch_out": 3900.0}],
    }


def corpus_holding_the_transcript(root):
    corpus = root / "corpus"
    (corpus / "transcripts").mkdir(parents=True)
    (corpus / "diarization").mkdir(parents=True)
    (corpus / "transcripts" / f"{ANALYZED}.{ASR_CONFIG}.json").write_text(
        json.dumps(spoken_service()), encoding="utf-8"
    )
    return corpus


def analyses(root, printed, **overrides):
    return analyzes(
        settings=settings_file(root),
        arguments=[
            ANALYZED,
            "--corpus",
            str(overrides.get("corpus", corpus_holding_the_transcript(root))),
            "--summaries",
            "none",
        ],
        reasons=reasoned_blocks,
        prints=printed,
    )


def test_analyzing_lands_the_blocks_and_the_proposal_in_the_configured_data_root(tmp_path, injected_roots):
    printed = RecordsLines()
    assert analyses(tmp_path, printed) == 0
    store = opens_store(tmp_path / "data")
    proposed = store.lists(Segment, recording_id=ANALYZED)
    assert [item.type for item in store.lists(Block, recording_id=ANALYZED)] == [
        "music",
        "sermon",
        "prayer",
    ]
    assert [(item.state, item.classification) for item in proposed] == [("proposed", "sermon")]
    assert [item.boundary_confidence for item in store.lists(
        Proposal, segment_id=proposed[0].segment_id
    )] == ["high"]
    store.close()


def test_analyzing_leaves_the_recording_awaiting_review_and_the_job_succeeded(tmp_path, injected_roots):
    printed = RecordsLines()
    assert analyses(tmp_path, printed) == 0
    store = opens_store(tmp_path / "data")
    assert store.loads(Recording, ANALYZED).state == "awaiting_review"
    assert [(item.kind, item.state) for item in store.lists(Job)] == [("analyze", "succeeded")]
    assert [item.kind for item in store.lists(Notification, recording_id=ANALYZED)] == [
        "segment_proposed"
    ]
    store.close()


def test_analyzing_reports_the_state_the_boundaries_and_the_confidence(tmp_path, injected_roots):
    printed = RecordsLines()
    analyses(tmp_path, printed)
    assert f"{ANALYZED} is awaiting_review" in str(printed)
    assert "sermon   0:10:00 -> 1:04:21" in str(printed)
    assert "classification high, boundary high" in str(printed)


def test_analyzing_a_recording_with_no_stored_transcript_is_refused(tmp_path, injected_roots):
    printed = RecordsLines()
    (tmp_path / "empty" / "transcripts").mkdir(parents=True)
    assert analyses(tmp_path, printed, corpus=tmp_path / "empty") == 1
    assert "no whisper-large-v3-turbo+words transcript" in str(printed)


EDITED = "recording_20260920_094416"
HUMAN_IN = 4151.2935
HUMAN_OUT = 7599.5667
MODEL_IN = 4151.0
SERVICE_SECONDS = 9000.0


def hand_edited_service():
    return {
        "recording_id": EDITED,
        "duration": SERVICE_SECONDS,
        "started_at": "2026-09-20T09:44:16",
        "utterances": [
            {
                "start": float(start),
                "end": float(start) + 20.0,
                "text": "Good morning church we are glad you are here today",
                "words": [{"w": "morning", "start": float(start), "end": float(start) + 1.0}],
            }
            for start in range(0, int(SERVICE_SECONDS), 60)
        ],
        "silences": [],
    }


def reasoned_service(_doc=None):
    return {
        "blocks": [
            {"start": 0.0, "end": 4150.0, "type": "music", "confidence": 0.9},
            {"start": 4150.0, "end": 7600.0, "type": "sermon", "confidence": 0.95},
            {"start": 7600.0, "end": 9000.0, "type": "other", "confidence": 0.8},
        ],
        "model_segments": [{"punch_in": MODEL_IN, "punch_out": 7599.0}],
    }


def store_holding_the_hand_edit(root, transcript=True):
    data_root = root / "data"
    store = opens_store(data_root)
    recording = store.saves(
        Recording(
            recording_id=EDITED,
            object_key=f"{EDITED}.flac",
            state="discovered",
            started_at=datetime(2026, 9, 20, 9, 44, 16, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=10121.581315,
        )
    )
    if transcript:
        writes_json(store, recording, "transcript", hand_edited_service())
    store.saves(
        CorpusPair(
            recording_id=EDITED,
            classification="sermon",
            provenance="human",
            alignment="aligned",
            punch_in_seconds=HUMAN_IN,
            punch_out_seconds=HUMAN_OUT,
            punch_in_difficulty="easy",
            punch_out_difficulty="easy",
        )
    )
    store.close()
    return data_root


def derives_corpus_entry(root, printed, **overrides):
    return derives_corpus(
        settings=settings_file(root),
        arguments=[EDITED, *overrides.pop("flags", ())],
        reasons=reasoned_service,
        prints=printed,
    )


def test_deriving_a_corpus_entry_writes_the_block_file_and_the_transcript(tmp_path, injected_roots):
    store_holding_the_hand_edit(tmp_path)
    printed = RecordsLines()
    assert derives_corpus_entry(tmp_path, printed) == 0
    corpus = tmp_path / "data" / "corpus"
    assert (corpus / "transcripts" / f"{EDITED}.{ASR_CONFIG}.json").is_file()
    recorded = json.loads(
        (corpus / "blocks" / f"{EDITED}.stored.whole.v2.json").read_text()
    )
    assert recorded["model_segments"] == [{"punch_in": MODEL_IN, "punch_out": 7599.0}]
    assert str(corpus) in str(printed)
    assert "sermon   1:09:11 -> 2:06:21  (model-in/refined-out)" in str(printed)


def test_the_derived_entry_makes_the_stored_pair_change_the_reported_numbers(tmp_path, injected_roots):
    data_root = store_holding_the_hand_edit(tmp_path)
    corpus = data_root / "corpus"
    before = RecordsLines()
    (corpus / "blocks").mkdir(parents=True)
    assert regrades(
        arguments=["--corpus", str(corpus), "--store", str(data_root)], prints=before
    ) == 1
    assert "no stored proposals" in str(before)
    assert derives_corpus_entry(tmp_path, RecordsLines()) == 0
    after = RecordsLines()
    assert regrades(
        arguments=["--corpus", str(corpus), "--store", str(data_root)], prints=after
    ) == 0
    assert "1 proposal graded, 2 cut points" in str(after)
    assert f"human   {HUMAN_IN:.3f}" in str(after)
    assert f"proposed   {MODEL_IN:.3f}" in str(after)


def test_deriving_a_corpus_entry_for_a_recording_with_no_transcript_is_refused(tmp_path, injected_roots):
    store_holding_the_hand_edit(tmp_path, transcript=False)
    printed = RecordsLines()
    assert derives_corpus_entry(tmp_path, printed) == 1
    assert f"no transcript is stored for {EDITED}" in str(printed)


def test_deriving_a_corpus_entry_twice_refuses_to_redraw_the_block_file(tmp_path, injected_roots):
    store_holding_the_hand_edit(tmp_path)
    assert derives_corpus_entry(tmp_path, RecordsLines()) == 0
    recorded = (
        tmp_path / "data" / "corpus" / "blocks" / f"{EDITED}.stored.whole.v2.json"
    ).read_text()
    printed = RecordsLines()
    assert derives_corpus_entry(tmp_path, printed) == 1
    assert "already records a classifier answer" in str(printed)
    assert (
        tmp_path / "data" / "corpus" / "blocks" / f"{EDITED}.stored.whole.v2.json"
    ).read_text() == recorded


def test_a_tag_names_the_configuration_the_corpus_entry_came_from(tmp_path, injected_roots):
    store_holding_the_hand_edit(tmp_path)
    assert derives_corpus_entry(
        tmp_path, RecordsLines(), flags=("--tag", "t3-qwen3.6.whole.v2")
    ) == 0
    assert (
        tmp_path / "data" / "corpus" / "blocks" / f"{EDITED}.t3-qwen3.6.whole.v2.json"
    ).is_file()
