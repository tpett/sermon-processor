from __future__ import annotations

import os
from pathlib import Path

from sermon.config import ReadsConfiguration
from sermon.object_store import ListsBucketObjects, OpensObjectStore
from sermon.reconciles_bucket import ReconcilesBucket
from sermon.store import Discovery, Recording, SkippedObject, opens_store
from sermon.web import creates_app

ENVIRONMENT_FILE = ".env"
BIND_HOST = "SERMON_BIND_HOST"
PORT = "SERMON_PORT"
DEFAULT_PORT = 8000
QUOTES = "\"'"


def reads_environment_file(path):
    if not path.is_file():
        return {}
    settings = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().partition("=")
        if not separator or name.startswith("#"):
            continue
        settings[name.strip()] = value.strip().strip(QUOTES)
    return settings


def resolves_settings(root=None, environment=None):
    root = Path.cwd() if root is None else Path(root)
    environment = os.environ if environment is None else environment
    return {**reads_environment_file(root / ENVIRONMENT_FILE), **environment}


def lists_bucket(configuration):
    return ListsBucketObjects(
        bucket=configuration.object_store.bucket,
        client=OpensObjectStore(object_store=configuration.object_store)(),
    )


def opens(settings, lists_objects):
    configuration = ReadsConfiguration(resolves_settings() if settings is None else settings)()
    return (
        configuration,
        opens_store(configuration.data_root),
        lists_bucket(configuration) if lists_objects is None else lists_objects,
    )


def reconciles(settings=None, lists_objects=None, prints=print):
    configuration, store, lists_objects = opens(settings, lists_objects)
    try:
        prints(
            f"scanning {configuration.object_store.bucket} "
            f"at {configuration.object_store.endpoint}"
        )
        ReconcilesBucket(store=store, lists_objects=lists_objects)()
        scan = store.lists(Discovery, kind="scan")[-1]
        if scan.failure:
            prints(f"the scan failed: {scan.failure}")
            return 1
        prints(
            f"discovered {scan.discovered_count}, "
            f"skipped {len(store.lists(SkippedObject))}, "
            f"{len(store.lists(Recording))} recordings known"
        )
        return 0
    finally:
        store.close()


def starts(app, host, port):
    app.run(host=host, port=port)


def serves(settings=None, lists_objects=None, runs=starts):
    settings = resolves_settings() if settings is None else settings
    _, store, lists_objects = opens(settings, lists_objects)
    app = creates_app(store=store, lists_objects=lists_objects)
    app.config["BIND_HOST"] = settings.get(BIND_HOST, app.config["BIND_HOST"])
    runs(app, app.config["BIND_HOST"], int(settings.get(PORT, DEFAULT_PORT)))
    return 0
