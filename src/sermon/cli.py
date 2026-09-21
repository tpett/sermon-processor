from __future__ import annotations

import os
from pathlib import Path

ENVIRONMENT_FILE = ".env"


def resolves_settings(root=None, environment=None):
    return {}


def lists_bucket(configuration):
    return None


def reconciles(settings=None, lists_objects=None, prints=print):
    return 0


def starts(app, host, port):
    app.run(host=host, port=port)


def serves(settings=None, lists_objects=None, runs=starts):
    return 0
