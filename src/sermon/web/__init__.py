import json
import os
import shutil
from dataclasses import asdict
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request, send_file

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now
from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady
from sermon.discards_recording import DiscardsRecording, RestoresRecording
from sermon.lists_recordings import ListsRecordings
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.shows_recording import ShowsRecording
from sermon.skips_segment import SkipsSegment
from sermon.store import Artifact, Discovery, Job, Recording, Segment


def creates_app(*, store, clock=now, lists_objects=None):
    web_dir = Path(__file__).parent
    app = Flask(
        __name__,
        template_folder=str(web_dir / "templates"),
        static_folder=str(web_dir / "static"),
    )
    app.config["BIND_HOST"] = os.environ.get("SERMON_BIND_HOST", "100.64.0.1")
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)
    lists = ListsRecordings(store=store, clock=clock)
    shows = ShowsRecording(store=store)
    approves = ApprovesSegment(store=store, clock=clock)
    skips = SkipsSegment(store=store, clock=clock)
    discards = DiscardsRecording(store=store, clock=clock)
    restores = RestoresRecording(store=store, clock=clock)
    reconciles = ReconcilesBucket(store=store, lists_objects=lists_objects, clock=clock)
    playheads = {}

    @app.get("/")
    def home():
        rows = lists()
        return render_template(
            "list.html",
            recordings=rows,
            awaiting=sum(row.awaiting_disposition for row in rows),
        )

    @app.get("/recordings/<recording_id>")
    def html_detail(recording_id):
        view = shows(recording_id, playhead_seconds=playheads.get(recording_id, 0.0))
        return render_template("detail.html", payload=json.dumps(asdict(view)))

    @app.post("/api/webhooks/recordings")
    def recordings_webhook():
        status, detail = accepts(request.get_json(silent=True) or {})
        if status == 422:
            return {"missing": detail}, 422
        return ("", status)

    @app.get("/api/recordings")
    def recordings_list():
        include_discarded = request.args.get("discarded") == "1"
        rows = lists(
            include_discarded=include_discarded,
            filter_name=request.args.get("filter"),
            classification=request.args.get("classification"),
            q=request.args.get("q"),
        )
        return {
            "recordings": [asdict(row) for row in rows],
            "awaiting_disposition": sum(row.awaiting_disposition for row in rows),
        }

    @app.get("/api/artifacts/<path:path>")
    def artifact_download(path):
        matching = [item for item in store.lists(Artifact) if item.path == path]
        entity = matching[0] if matching else None
        if entity is None:
            recordings = [item for item in store.lists(Recording) if item.local_path == path]
            entity = recordings[0] if recordings else None
        if entity is None:
            return ("", 404)
        resolved = store.resolves(entity)
        if resolved is None or not resolved.is_file():
            return ("", 404)
        return send_file(
            resolved,
            as_attachment=True,
            download_name=Path(path).name,
            conditional=True,
        )

    @app.get("/api/health")
    def health():
        jobs = store.lists(Job)
        queued = [job for job in jobs if job.state == "queued"]
        oldest_queued_seconds = None
        if queued:
            oldest_queued_seconds = (clock() - queued[0].queued_at).total_seconds()
        scans = store.lists(Discovery, kind="scan")
        webhooks = store.lists(Discovery, kind="webhook")
        last_scan = scans[-1] if scans else None
        last_webhook = webhooks[-1] if webhooks else None
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        scan_failure = None if last_scan is None else last_scan.failure
        object_store_status = "unhealthy" if scan_failure else "healthy"
        disk_status = "healthy"
        channel_status = "healthy"
        alerts = []
        if getattr(store, "_scratch_exhausted", False):
            disk_status = "unhealthy"
            alerts.append("scratch exhausted")
        if getattr(store, "_storage_percent", 0) >= 90:
            alerts.append("long-lived storage at 90%")
        if getattr(store, "_channel_unavailable", False):
            channel_status = "unhealthy"
            alerts.append("notification channel unavailable")
        recordings = store.lists(Recording)
        if any("source no longer available" in recording.warnings for recording in recordings):
            alerts.append("source no longer available")
        status = 200 if object_store_status == "healthy" and ffmpeg_ok and disk_status == "healthy" else 503
        last_ingest_seconds = None
        short_on_disk = [item for item in recordings if item.waiting_since is not None]
        if recordings:
            newest = max(recordings, key=lambda item: item.started_at)
            last_ingest_seconds = (clock() - newest.started_at).total_seconds()
        body = {
            "queued": len(queued),
            "running": sum(1 for job in jobs if job.state == "running"),
            "failed": sum(1 for job in jobs if job.state == "failed"),
            "oldest_queued_seconds": oldest_queued_seconds,
            "bind_host": app.config["BIND_HOST"],
            "last_webhook_at": None if last_webhook is None else last_webhook.occurred_at.isoformat(),
            "last_scan_at": None if last_scan is None else last_scan.occurred_at.isoformat(),
            "webhook_discovered": 0 if last_webhook is None else last_webhook.discovered_count,
            "scan_discovered": 0 if last_scan is None else last_scan.discovered_count,
            "scan_failure": scan_failure,
            "last_ingest_seconds": last_ingest_seconds,
            "storage_alert": bool(short_on_disk) or bool(alerts),
            "storage_alert_reason": "local disk is short" if short_on_disk else (alerts[0] if alerts else None),
            "alerts": alerts,
            "object_store": object_store_status,
            "ffmpeg": ffmpeg_ok,
            "dependencies": {
                "the object store": object_store_status,
                "the job queue": "healthy",
                "the transcription service": "healthy",
                "local disk space": disk_status,
                "ffmpeg availability": "healthy" if ffmpeg_ok else "unhealthy",
                "the notification channel": channel_status,
            },
        }
        return body, status

    @app.post("/api/ingest")
    def ingest():
        body = request.get_json(silent=True) or {}
        recording = reconciles.ingests(body["object_key"])
        return {"recording_id": recording.recording_id, "state": recording.state}, 202

    @app.get("/api/recordings/<recording_id>")
    def recording_detail(recording_id):
        selected = request.args.get("segment", type=int)
        return asdict(
            shows(
                recording_id,
                selected_segment_id=selected,
                playhead_seconds=playheads.get(recording_id, 0.0),
            )
        )

    @app.post("/api/recordings/<recording_id>/seek")
    def seek(recording_id):
        seconds = float(request.get_json()["seconds"])
        playheads[recording_id] = seconds
        return asdict(
            shows(
                recording_id,
                playhead_seconds=seconds,
            )
        )

    @app.post("/api/segments/<int:segment_id>/approve")
    def approve_segment(segment_id):
        segment = store.loads(Segment, segment_id)
        try:
            approved = approves(segment)
        except PublicationLabelRequired as error:
            return {"error": str(error), "prompt": "label"}, 409
        except SegmentNotReady as error:
            return {"error": str(error), "prompt": "not ready"}, 409
        return asdict(shows(approved.recording_id))

    @app.post("/api/recordings/<recording_id>/discard")
    def discard_recording(recording_id):
        body = request.get_json(silent=True) or {}
        recording = store.loads(Recording, recording_id)
        discarded = discards(recording, reason=body.get("reason"))
        return {"recording_id": discarded.recording_id, "state": discarded.state}

    @app.post("/api/recordings/<recording_id>/restore")
    def restore_recording(recording_id):
        recording = store.loads(Recording, recording_id)
        restored = restores(recording)
        return {"recording_id": restored.recording_id, "state": restored.state}

    @app.post("/api/segments/<int:segment_id>/skip")
    def skip_segment(segment_id):
        segment = store.loads(Segment, segment_id)
        skipped = skips(segment)
        return asdict(shows(skipped.recording_id))

    @app.put("/api/segments/<int:segment_id>/publication")
    def publication_details(segment_id):
        body = request.get_json()
        segment = store.loads(Segment, segment_id)
        RecordsPublicationDetails(store=store).saves(
            segment,
            publication_date=date.fromisoformat(body["date"]),
            label=body["label"],
        )
        return asdict(shows(segment.recording_id))

    return app
