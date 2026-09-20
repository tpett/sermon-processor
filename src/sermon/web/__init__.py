from flask import Flask, request

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now


def creates_app(*, store, clock=now):
    app = Flask(__name__)
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)

    @app.post("/api/webhooks/recordings")
    def recordings_webhook():
        accepts(request.get_json())
        return ("", 202)

    return app
