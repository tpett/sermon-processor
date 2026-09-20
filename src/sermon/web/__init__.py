from dataclasses import asdict
from datetime import date

from flask import Flask, request

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now
from sermon.approves_segment import ApprovesSegment
from sermon.skips_segment import SkipsSegment
from sermon.lists_recordings import ListsRecordings
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.shows_recording import ShowsRecording
from sermon.store import Segment


def creates_app(*, store, clock=now):
    app = Flask(__name__)
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)
    lists = ListsRecordings(store=store)
    shows = ShowsRecording(store=store)
    approves = ApprovesSegment(store=store, clock=clock)
    skips = SkipsSegment(store=store, clock=clock)

    @app.post("/api/webhooks/recordings")
    def recordings_webhook():
        accepts(request.get_json())
        return ("", 202)

    @app.get("/api/recordings")
    def recordings_list():
        include_discarded = request.args.get("discarded") == "1"
        rows = lists(include_discarded=include_discarded)
        return {
            "recordings": [asdict(row) for row in rows],
            "awaiting_disposition": sum(row.awaiting_disposition for row in rows),
        }

    @app.get("/api/recordings/<recording_id>")
    def recording_detail(recording_id):
        return asdict(shows(recording_id))

    @app.post("/api/segments/<int:segment_id>/approve")
    def approve_segment(segment_id):
        segment = store.loads(Segment, segment_id)
        approved = approves(segment)
        return asdict(shows(approved.recording_id))

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
