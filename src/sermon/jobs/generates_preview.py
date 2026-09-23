from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from sermon.pipeline import preview as rendition
from sermon.pipeline.preview import PreviewUnavailable
from sermon.pipeline.render import probe_format
from sermon.store import Artifact, Store

CHUNK_BYTES = 1 << 20


class PreviewSourceUnavailable(PreviewUnavailable):
    def __init__(self, recording_id):
        super().__init__(f"{recording_id} has no local source to render a preview from")


def digests(path: Path) -> str:
    running = hashlib.md5()
    with path.open("rb") as reading:
        while chunk := reading.read(CHUNK_BYTES):
            running.update(chunk)
    return running.hexdigest()


@dataclass(frozen=True)
class GeneratesPreview:
    """Render the whole Recording as one constant-bitrate, seekable MP3."""

    store: Store
    encodes: object = rendition.encodes
    probes_format: object = probe_format

    def path_for(self, recording):
        return f"{recording.recording_id}/preview{rendition.SUFFIX}"

    def __call__(self, recording):
        source = self.store.resolves(recording)
        if source is None or not source.is_file():
            raise PreviewSourceUnavailable(recording.recording_id)
        artifact = Artifact(
            recording_id=recording.recording_id,
            kind="preview",
            path=self.path_for(recording),
            size_bytes=0,
            checksum="",
        )
        destination = self.store.resolves(artifact)
        self.encodes(source, destination)
        shape = self.probes_format(destination)
        existing = [
            item
            for item in self.store.lists(Artifact, recording_id=recording.recording_id, kind="preview")
            if item.path == artifact.path
        ]
        return self.store.saves(
            replace(
                artifact,
                artifact_id=existing[0].artifact_id if existing else None,
                size_bytes=destination.stat().st_size,
                checksum=digests(destination),
                render_settings={
                    **rendition.settings(),
                    "duration_seconds": shape.get("duration"),
                    "measured_kbps": shape.get("kbps"),
                },
            )
        )
