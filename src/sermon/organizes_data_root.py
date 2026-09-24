"""Move a data root laid out by whoever wrote to it first onto the deliberate one.

The paths in `recording.local_path` and `artifact.path` are the layout: nothing
else records where a file is. So moving files without rewriting rows breaks every
download, and rewriting rows without moving files breaks them the same way.

`Store.saves` is atomic for one entity; a rename plus a row update is not. **The
file moves first, then its row.** Interrupted, that leaves a row naming a path
with no file, and the file already where it belongs -- and the next run sees
exactly that and writes the row. The other order would leave a row naming the new
path, the file still at the old one, and nothing anywhere recording which old one:
the file's whereabouts would have to be guessed from its name.

Everything here is therefore idempotent, and a second run reports only `in place`.
Running it on a root that holds nothing lays out the empty skeleton and stops.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from sermon.store import Artifact, Recording, layout
from sermon.store.stored_paths import PathEscapesDataRoot

MOVED = "moved"
IN_PLACE = "in place"
ROW_REPAIRED = "row repaired, file was already moved"
NO_FILE = "row rewritten, no file to move"
COLLIDES = "refused: a file is already there"
REFUSED = "refused: the stored path escapes the data root"

LEGACY_RECORDING_DIRECTORY = "recording_*"
SIDECAR_SUFFIX = ".meta.json"


@dataclass(frozen=True)
class Relocation:
    """One thing that moved, or did not, and why."""

    subject: str
    was: str
    now: str
    outcome: str

    def __str__(self):
        if self.outcome == IN_PLACE:
            return f"{self.subject}: {self.now} ({IN_PLACE})"
        return f"{self.subject}: {self.was} -> {self.now} ({self.outcome})"


def destination_for(artifact):
    """Where an Artifact of this kind belongs, from its kind alone.

    The filename of a rendered MP3 is the reviewer's, not ours -- it is what the
    publication form named -- so only its directory changes. Everything else is
    named after its kind by `layout`.
    """
    held = PurePosixPath(artifact.path)
    if artifact.kind == "rendered_mp3":
        return layout.published_path(held.name)
    if artifact.kind == "source_flac":
        return f"{layout.recording_directory(artifact.recording_id)}/{layout.SOURCE_STEM}{held.suffix}"
    return layout.artifact_path(artifact.recording_id, artifact.kind)


@dataclass(frozen=True)
class OrganizesDataRoot:
    store: object
    data_root: object
    dry_run: bool = False

    def __call__(self):
        self._lays_out_the_skeleton()
        claimed = {}
        by_row = [
            *self._relocates_sources(claimed),
            *self._relocates_artifacts(claimed),
        ]
        owned = {relocation.was for relocation in by_row}
        return (
            *by_row,
            *self._sweeps_legacy_recording_directories(owned),
            *self._gathers_the_corpus(),
        )

    def _lays_out_the_skeleton(self):
        if self.dry_run:
            return
        for directory in layout.directories(self.data_root):
            directory.mkdir(parents=True, exist_ok=True)

    def _relocates_sources(self, claimed):
        for recording in self.store.lists(Recording):
            if recording.local_path is None:
                continue
            yield self._relocates(
                subject=f"recording {recording.recording_id} source",
                entity=recording,
                field="local_path",
                now=layout.source_path(recording),
                claimed=claimed,
            )

    def _relocates_artifacts(self, claimed):
        for artifact in self.store.lists(Artifact):
            if artifact.path is None:
                continue
            yield self._relocates(
                subject=f"artifact {artifact.artifact_id} {artifact.kind}",
                entity=artifact,
                field="path",
                now=destination_for(artifact),
                claimed=claimed,
            )

    def _relocates(self, *, subject, entity, field, now, claimed):
        was = getattr(entity, field)
        if was == now:
            claimed[now] = subject
            return Relocation(subject=subject, was=was, now=now, outcome=IN_PLACE)
        try:
            here = self.store.resolves_path(was)
            there = self.store.resolves_path(now)
        except PathEscapesDataRoot:
            return Relocation(subject=subject, was=was, now=now, outcome=REFUSED)
        if now in claimed or (there.exists() and here.exists()):
            return Relocation(subject=subject, was=was, now=now, outcome=COLLIDES)
        claimed[now] = subject
        if here.exists():
            outcome = MOVED
            if not self.dry_run:
                self._carries(here, there)
        elif there.exists():
            outcome = ROW_REPAIRED
        else:
            # The cached-stage placeholder records that a stage ran and writes nothing.
            outcome = NO_FILE
        if not self.dry_run:
            self.store.saves(replace(entity, **{field: now}))
        return Relocation(subject=subject, was=was, now=now, outcome=outcome)

    def _carries(self, here, there):
        """One filesystem, so the rename is atomic and a 700 MB FLAC is never copied."""
        there.parent.mkdir(parents=True, exist_ok=True)
        os.replace(here, there)
        sidecar = here.with_name(f"{here.name}{SIDECAR_SUFFIX}")
        if sidecar.is_file():
            os.replace(sidecar, there.with_name(f"{there.name}{SIDECAR_SUFFIX}"))

    def _sweeps_legacy_recording_directories(self, owned):
        """`<recording_id>/` at the top level held files no row owns.

        `analysis_progress.json` is written through `resolves_path`, so nothing
        names it; so is the `.writing` file it is replaced from. Whatever is left
        in one of these directories belongs to that Recording either way.
        """
        for directory in sorted(self.data_root.glob(LEGACY_RECORDING_DIRECTORY)):
            if not directory.is_dir():
                continue
            under = self.data_root / layout.recording_directory(directory.name)
            for held in sorted(directory.iterdir()):
                subject = f"unowned file {directory.name}/{held.name}"
                was = f"{directory.name}/{held.name}"
                now = f"{layout.recording_directory(directory.name)}/{held.name}"
                if was in owned:
                    continue
                if (under / held.name).exists():
                    yield Relocation(subject=subject, was=was, now=now, outcome=COLLIDES)
                    continue
                if not self.dry_run:
                    under.mkdir(parents=True, exist_ok=True)
                    os.replace(held, under / held.name)
                yield Relocation(subject=subject, was=was, now=now, outcome=MOVED)
            if not self.dry_run and not any(directory.iterdir()):
                directory.rmdir()

    def _gathers_the_corpus(self):
        """The pipeline's `diarization` root was a peer of the recordings."""
        legacy = self.data_root / layout.DIARIZATION
        wanted = layout.diarization_root(self.data_root)
        if not legacy.is_dir() or legacy == wanted:
            return
        for held in sorted(legacy.iterdir()):
            subject = f"diarization {held.name}"
            was = f"{layout.DIARIZATION}/{held.name}"
            now = f"{layout.CORPUS}/{layout.DIARIZATION}/{held.name}"
            if (wanted / held.name).exists():
                yield Relocation(subject=subject, was=was, now=now, outcome=COLLIDES)
                continue
            if not self.dry_run:
                wanted.mkdir(parents=True, exist_ok=True)
                os.replace(held, wanted / held.name)
            yield Relocation(subject=subject, was=was, now=now, outcome=MOVED)
        if not any(legacy.iterdir()) or self.dry_run:
            if not self.dry_run:
                legacy.rmdir()
            yield Relocation(
                subject="the pipeline's diarization root",
                was=layout.DIARIZATION,
                now=f"{layout.CORPUS}/{layout.DIARIZATION}",
                outcome=MOVED,
            )
