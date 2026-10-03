import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from steps._asr import RecognizesSteadily

from sermon.analysis.proposes_from_transcript import BindsCorpusRoots
from sermon.analysis.transcribes_audio import SAMPLE_RATE, TranscribesAudio
from sermon.config import Credential
from sermon.jobs.analyzes_recording import RunsAnalyzeJob
from sermon.jobs.downloads_recording import FetchesObject, ProbesAudio, RunsDownloadJob
from sermon.jobs.renders_mp3 import RendersMp3
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.pipeline import classify, segments
from sermon.sends_notification import SendsNotification
from sermon.store import Artifact, Reviewer, Segment, layout, opens_store
from sermon.web import creates_app

OBJECT_KEY = "recordings/recording_20260823_103015.flac"
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
WEBHOOK_TOKEN_VALUE = "the-token-only-the-spec-suite-issues"


def divides_into_one_sermon(doc):
    return [{"start": 0.0, "end": doc["duration"], "type": "sermon", "confidence": 0.9}]


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


@pytest.fixture
def injected_roots(tmp_path):
    held = (classify.DATA, classify.PROMPTS, segments.DATA_ROOT)
    layout.diarization_root(tmp_path).mkdir(parents=True, exist_ok=True)
    BindsCorpusRoots(
        corpus_root=layout.corpus_root(tmp_path),
        prompts_root=Path(__file__).resolve().parents[1] / "experiments/prompts",
    )()
    yield
    classify.DATA, classify.PROMPTS, segments.DATA_ROOT = held


def writes_tone(path: Path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def queued_worker(store, fetches):
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    return RunsQueuedJobs(
        store=store,
        downloads=RunsDownloadJob(
            store=store,
            fetches=fetches,
            probes=ProbesAudio(duration_seconds=3.0, sample_rate=44100, channels=1),
            clock=lambda: FROZEN,
        ),
        analyzes=RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
            transcribes=TranscribesAudio(
                store=store, engine=RecognizesSteadily(rate=SAMPLE_RATE)
            ),
            divides=divides_into_one_sermon,
        ),
        renders=RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store),
            clock=lambda: FROZEN,
            renders=RendersMp3(),
        ),
    )


def test_webhook_to_named_mp3(store, tmp_path, injected_roots):
    tone = tmp_path / "tone.flac"
    writes_tone(tone)
    fetches = FetchesObject()
    fetches.stores(OBJECT_KEY, tone.read_bytes())
    client = creates_app(
        store=store, clock=lambda: FROZEN, webhook_token=Credential(WEBHOOK_TOKEN_VALUE)
    ).test_client()
    announced = client.post(
        "/api/webhooks/recordings",
        headers={"Authorization": f"Bearer {WEBHOOK_TOKEN_VALUE}"},
        json={
            "event": "recording.uploaded",
            "bucket": "sermons",
            "object_key": OBJECT_KEY,
            "size_bytes": tone.stat().st_size,
            "recorded_at": "2026-08-23T10:30:15-05:00",
        },
    )
    assert announced.status_code == 202
    worker = queued_worker(store, fetches)
    worker()
    worker()
    listings = client.get("/api/recordings").get_json()["recordings"]
    assert listings[0]["state"] == "awaiting_review"
    recording_id = listings[0]["recording_id"]
    detail = client.get(f"/api/recordings/{recording_id}").get_json()
    sermon = next(segment for segment in detail["segments"] if segment["classification"] == "sermon")
    client.put(
        f"/api/segments/{sermon['segment_id']}/publication",
        json={"date": "2026-08-23", "label": "Hebrews 12.4-11"},
    )
    approved = client.post(f"/api/segments/{sermon['segment_id']}/approve")
    assert approved.status_code == 200
    worker()
    artifacts = store.lists(Artifact, kind="rendered_mp3")
    assert artifacts[0].path == layout.published_path("2026-08-23 - Hebrews 12.4-11.mp3")
    rendered = store.resolves(artifacts[0])
    assert rendered.is_file()
    assert artifacts[0].size_bytes > 1000
    assert rendered.read_bytes()[:3] == b"ID3" or rendered.read_bytes()[:2] == b"\xff\xfb"
    assert store.loads(Segment, sermon["segment_id"]).state == "complete"
