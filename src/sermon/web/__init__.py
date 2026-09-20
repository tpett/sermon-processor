import os
from dataclasses import asdict
from datetime import date

from flask import Flask, request

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now
from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady
from sermon.discards_recording import DiscardsRecording, RestoresRecording
from sermon.skips_segment import SkipsSegment
from sermon.lists_recordings import ListsRecordings
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.shows_recording import ShowsRecording
from sermon.store import Job, Recording, Segment


def creates_app(*, store, clock=now):
    app = Flask(__name__)
    app.config["BIND_HOST"] = os.environ.get("SERMON_BIND_HOST", "100.64.0.1")
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)
    lists = ListsRecordings(store=store)
    shows = ShowsRecording(store=store)
    approves = ApprovesSegment(store=store, clock=clock)
    skips = SkipsSegment(store=store, clock=clock)
    discards = DiscardsRecording(store=store, clock=clock)
    restores = RestoresRecording(store=store, clock=clock)

    @app.post("/api/webhooks/recordings")
    def recordings_webhook():
        accepts(request.get_json())
        return ("", 202)

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
        return ("", 404)

    @app.get("/api/health")
    def health():
        jobs = store.lists(Job)
        queued = [job for job in jobs if job.state == "queued"]
        waiting = None
        if queued:
            waiting = (clock() - queued[0].queued_at).total_seconds()
        return {
            "queued": len(queued),
            "running": sum(1 for job in jobs if job.state == "running"),
            "failed": sum(1 for job in jobs if job.state == "failed"),
            "oldest_queued_seconds": waiting,
            "bind_host": app.config["BIND_HOST"],
        }

    @app.get("/api/recordings/<recording_id>")
    def recording_detail(recording_id):
        return asdict(shows(recording_id))

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
