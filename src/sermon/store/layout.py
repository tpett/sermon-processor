"""Where everything lives under the data root.

Every writer used to pick its own path, so sources sat beside their own
directories, rendered MP3s were loose at the top level, and the pipeline's
scratch was a peer of the recordings. One module decides instead, and the
stored path is still what `Store.resolves` reads -- nothing here widens what a
row is allowed to say.

    <data root>/
      sermon.sqlite3
      recordings/<recording_id>/source.flac        the untouched source
                               /preview.mp3        the whole service, seekable
                               /transcript.json    and every other analysis
                               /waveform_peaks.json  document, one per kind
                               /envelope.json
                               /analysis_progress.json
                               /model_segments.json  the reasoning's own cuts
      published/<date> - <label>.mp3               what a human collects
      corpus/diarization/                          the pipeline's own roots
      models/                                      the whisper weights

`corpus` exists because `pipeline.segments.DATA_ROOT` and `pipeline.classify.DATA`
demand a `diarization` directory directly beneath whatever they are bound to,
and that demand is a guard worth keeping. Binding them to their own subtree
keeps it satisfied without a corpus-shaped directory pretending to be a peer of
the recordings.
"""

from __future__ import annotations

from pathlib import PurePosixPath

RECORDINGS = "recordings"
PUBLISHED = "published"
CORPUS = "corpus"
DIARIZATION = "diarization"
MODELS = "models"

SOURCE_STEM = "source"
PREVIEW = "preview.mp3"
PROGRESS = "analysis_progress.json"
MODEL_SEGMENTS = "model_segments.json"

#: Kinds whose file is not the `<kind>.json` document that `analysis.io` writes.
NAMED_ARTIFACTS = {"preview": PREVIEW}


def recording_directory(recording_id):
    """Everything belonging to one Recording hangs off here."""
    return f"{RECORDINGS}/{recording_id}"


def source_path(recording):
    """The source keeps the container the object key named; only the stem is ours."""
    suffix = PurePosixPath(recording.object_key).suffix
    return f"{recording_directory(recording.recording_id)}/{SOURCE_STEM}{suffix}"


def artifact_path(recording_id, kind):
    """One file per artifact kind, named after the kind, beside the recording."""
    return f"{recording_directory(recording_id)}/{NAMED_ARTIFACTS.get(kind, f'{kind}.json')}"


def progress_path(recording_id):
    """Transcription's own fraction: a document no row owns."""
    return f"{recording_directory(recording_id)}/{PROGRESS}"


def model_segments_path(recording_id):
    """The reasoning stage's own boundaries, which no row holds."""
    return f"{recording_directory(recording_id)}/{MODEL_SEGMENTS}"


def published_path(filename):
    """The rendered MP3s, in the one place to point a browser or an rsync at."""
    return f"{PUBLISHED}/{filename}"


def corpus_root(data_root):
    return data_root / CORPUS


def diarization_root(data_root):
    return corpus_root(data_root) / DIARIZATION


def directories(data_root):
    """The skeleton a fresh deployment needs before any job runs."""
    return (
        data_root / RECORDINGS,
        data_root / PUBLISHED,
        diarization_root(data_root),
    )
