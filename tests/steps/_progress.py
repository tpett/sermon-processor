"""A Recording caught part way through Analysis, staged the way the worker stages it.

A Recording is only ever `analyzing` because a worker is partway down
STAGE_ORDER, and going through the shipped recorder keeps the two from drifting.
"""

from __future__ import annotations

from sermon.analysis.progress import (
    RecordsStageProgress,
    ReportsTranscriptionProgress,
    reads_stage_progress,
)
from sermon.jobs.analyzes_recording import STAGE_ORDER

STAGE_SECONDS = 12.0
CHUNK = 3
CHUNKS = 7
RECOGNISED_SECONDS = 4820.0


def leaves_analysis_part_way(store, recording, reached="transcription"):
    records = RecordsStageProgress(store=store)
    for name in STAGE_ORDER[: STAGE_ORDER.index(reached)]:
        records.started(recording, name)
        records.completed(recording, name, STAGE_SECONDS)
    records.started(recording, reached)
    if reached == "transcription":
        ReportsTranscriptionProgress(store=store)(
            recording,
            chunk=CHUNK,
            chunks=CHUNKS,
            recognised_seconds=RECOGNISED_SECONDS,
            duration_seconds=recording.duration_seconds,
        )
    return recording


def completed_stages(store, recording):
    return {
        name
        for name, recorded in reads_stage_progress(store, recording).items()
        if recorded["state"] == "complete"
    }


def running_stages(store, recording):
    return {
        name
        for name, recorded in reads_stage_progress(store, recording).items()
        if recorded["state"] == "running"
    }
