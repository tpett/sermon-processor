from datetime import UTC, datetime

from flask import Flask


def now():
    return datetime.now(UTC)


def creates_app(*, store, clock=now):
    return Flask(__name__)
