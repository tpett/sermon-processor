from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from sermon.store import Artifact, layout


def writes_json(store, recording, kind, payload):
    path = layout.artifact_path(recording.recording_id, kind)
    body = json.dumps(payload, sort_keys=True).encode()
    artifact = Artifact(
        recording_id=recording.recording_id,
        kind=kind,
        path=path,
        size_bytes=len(body),
        checksum=hashlib.md5(body).hexdigest(),
    )
    destination = store.resolves(artifact)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    existing = store.lists(Artifact, recording_id=recording.recording_id, kind=kind)
    if existing:
        return store.saves(replace(existing[0], size_bytes=len(body), checksum=artifact.checksum, path=path))
    return store.saves(artifact)


def reads_json(store, recording, kind):
    artifacts = store.lists(Artifact, recording_id=recording.recording_id, kind=kind)
    if not artifacts:
        return None
    path = store.resolves(artifacts[0])
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text())
