import hashlib
import io
import tarfile

import pytest

from sermon.analysis.diarizes_audio import EMBEDDING, SEGMENTATION
from sermon.analysis.provisions_diarization_models import (
    MODEL_SOURCES,
    ChecksumMismatch,
    ModelSource,
    ProvisionsDiarizationModels,
)

SEGMENTATION_BYTES = b"segmentation weights"
EMBEDDING_BYTES = b"embedding weights"


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def archive_holding(members):
    held = io.BytesIO()
    with tarfile.open(fileobj=held, mode="w:bz2") as archive:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return held.getvalue()


ARCHIVE = archive_holding(
    {
        str(SEGMENTATION): SEGMENTATION_BYTES,
        "sherpa-onnx-pyannote-segmentation-3-0/run.sh": b"#!/bin/sh\n",
    }
)

SOURCES = (
    ModelSource(
        path=SEGMENTATION,
        sha256=sha256(SEGMENTATION_BYTES),
        url="https://example.invalid/segmentation.tar.bz2",
        url_sha256=sha256(ARCHIVE),
        member=str(SEGMENTATION),
    ),
    ModelSource(
        path=EMBEDDING,
        sha256=sha256(EMBEDDING_BYTES),
        url="https://example.invalid/embedding.onnx",
        url_sha256=sha256(EMBEDDING_BYTES),
    ),
)


class Answers:
    def __init__(self, bodies):
        self.bodies = bodies
        self.asked = []

    def __call__(self, url, timeout=None):
        self.asked.append(url)
        return io.BytesIO(self.bodies[url])


def answering(**changed):
    bodies = {SOURCES[0].url: ARCHIVE, SOURCES[1].url: EMBEDDING_BYTES}
    bodies.update(changed)
    return Answers(bodies)


def test_both_models_land_where_the_diarizer_looks(tmp_path):
    ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES, opens=answering())()
    assert (tmp_path / SEGMENTATION).read_bytes() == SEGMENTATION_BYTES
    assert (tmp_path / EMBEDDING).read_bytes() == EMBEDDING_BYTES


def test_only_the_model_is_taken_from_the_archive(tmp_path):
    ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES, opens=answering())()
    assert sorted(path.name for path in tmp_path.rglob("*") if path.is_file()) == sorted(
        [SEGMENTATION.name, EMBEDDING.name]
    )


def test_a_download_whose_checksum_differs_is_refused_and_nothing_is_written(tmp_path):
    opens = answering(**{SOURCES[1].url: b"something else"})
    with pytest.raises(ChecksumMismatch, match="embedding.onnx"):
        ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES, opens=opens)()
    assert not (tmp_path / EMBEDDING).exists()


def test_an_extracted_model_whose_checksum_differs_is_refused(tmp_path):
    tampered = archive_holding({str(SEGMENTATION): b"tampered"})
    sources = (SOURCES[0].__class__(**{**SOURCES[0].__dict__, "url_sha256": sha256(tampered)}),)
    opens = answering(**{SOURCES[0].url: tampered})
    with pytest.raises(ChecksumMismatch, match="model.onnx"):
        ProvisionsDiarizationModels(destination=tmp_path, sources=sources, opens=opens)()
    assert not (tmp_path / SEGMENTATION).exists()


def test_models_already_in_place_are_not_fetched_again(tmp_path):
    ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES, opens=answering())()
    again = answering()
    ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES, opens=again)()
    assert again.asked == []


def test_a_model_in_place_with_the_wrong_checksum_is_fetched_again(tmp_path):
    (tmp_path / EMBEDDING).write_bytes(b"truncated")
    opens = answering()
    ProvisionsDiarizationModels(destination=tmp_path, sources=SOURCES[1:], opens=opens)()
    assert opens.asked == [SOURCES[1].url]
    assert (tmp_path / EMBEDDING).read_bytes() == EMBEDDING_BYTES


def test_the_shipped_sources_are_the_spikes_files_pinned_by_checksum():
    assert {source.path: (source.url, source.url_sha256, source.sha256) for source in MODEL_SOURCES} == {
        SEGMENTATION: (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/"
            "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
            "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
            "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079",
        ),
        EMBEDDING: (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
            "nemo_en_titanet_small.onnx",
            "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
            "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        ),
    }
