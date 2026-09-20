from dataclasses import asdict

from flask import Flask, request

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now
from sermon.lists_recordings import ListsRecordings


def creates_app(*, store, clock=now):
    app = Flask(__name__)
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)
    lists = ListsRecordings(store=store)

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

    return app
