"""Put the diarization models on disk, refusing any byte that does not match its pin.

Standard library only: the image runs this file on its own, before the package
is installed, so the download layer survives a source change.

    python provisions_diarization_models.py <destination>
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SEGMENTATION = Path("sherpa-onnx-pyannote-segmentation-3-0") / "model.onnx"
EMBEDDING = Path("nemo_en_titanet_small.onnx")
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
TIMEOUT_S = 300.0


class ChecksumMismatch(RuntimeError):
    def __init__(self, what, wanted, got):
        super().__init__(f"{what}: sha256 {got} is not the pinned {wanted}")


@dataclass(frozen=True)
class ModelSource:
    path: Path
    sha256: str
    url: str
    url_sha256: str
    member: str | None = None


MODEL_SOURCES = (
    ModelSource(
        path=SEGMENTATION,
        sha256="220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079",
        url=f"{RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        url_sha256="24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
        member=str(SEGMENTATION),
    ),
    ModelSource(
        path=EMBEDDING,
        sha256="ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        url=f"{RELEASES}/speaker-recongition-models/nemo_en_titanet_small.onnx",
        url_sha256="ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
    ),
)


def _sha256(body):
    return hashlib.sha256(body).hexdigest()


def _checked(what, body, wanted):
    got = _sha256(body)
    if got != wanted:
        raise ChecksumMismatch(what, wanted, got)
    return body


@dataclass(frozen=True)
class ProvisionsDiarizationModels:
    destination: Path
    sources: tuple = MODEL_SOURCES
    opens: object = urllib.request.urlopen

    def __call__(self):
        return [self._provisions(source) for source in self.sources]

    def _provisions(self, source):
        target = Path(self.destination) / source.path
        if target.is_file() and _sha256(target.read_bytes()) == source.sha256:
            return target
        with self.opens(source.url, timeout=TIMEOUT_S) as answered:
            fetched = _checked(source.url, answered.read(), source.url_sha256)
        body = _checked(str(source.path), self._unpacks(fetched, source), source.sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        partial.write_bytes(body)
        partial.replace(target)
        return target

    def _unpacks(self, fetched, source):
        if source.member is None:
            return fetched
        with tarfile.open(fileobj=io.BytesIO(fetched), mode="r:*") as archive:
            return archive.extractfile(source.member).read()


def main(arguments=None):
    named = sys.argv[1:] if arguments is None else arguments
    if len(named) != 1:
        print("usage: provisions_diarization_models.py <destination>", file=sys.stderr)
        return 2
    for placed in ProvisionsDiarizationModels(destination=Path(named[0]))():
        print(placed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
