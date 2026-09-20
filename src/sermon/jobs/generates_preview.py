from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Artifact, Store


@dataclass(frozen=True)
class GeneratesPreview:
    store: Store

    def __call__(self, recording):
        path = f"{recording.recording_id}/preview.m4a"
        artifact = Artifact(
            recording_id=recording.recording_id,
            kind="preview",
            path=path,
            size_bytes=1,
            checksum="preview",
        )
        destination = self.store.resolves(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = b"preview-channel-1"
        destination.write_bytes(payload)
        return self.store.saves(replace(artifact, size_bytes=len(payload)))
