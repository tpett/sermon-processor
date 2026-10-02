"""Where the classifier's block table sits relative to speech.

The model is handed the rendered transcript and answers with its own block
table. `classify.coerce_blocks` makes that table contiguous and in range and
leaves every edge exactly where the model wrote it, so an edge the model placed
in the middle of a word reaches Segment proposal unremarked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sermon.analysis.progress import correlation_for
from sermon.analysis.stages import seeds_segment
from sermon.pipeline import classify
from sermon.store import LogEntry

EDGE_INSIDE_SPEECH = "block_edge_inside_speech"


def now():
    return datetime.now(UTC)


@dataclass(frozen=True)
class RecordsEdgesInsideSpeech:
    """One log entry per block edge the model placed inside a spoken word.

    A record, not a verdict: such an edge is often nearer the human cut than one
    that lands clear of speech, but it sits in no silence run, so it scores
    `degraded` however small its error. This is what says which of the two it is.

    Only the blocks that can seed a Segment, because only their edges reach a cut.
    """

    store: object
    clock: object = now

    def __call__(self, recording, blocks, doc):
        return [
            self._logs(recording, found)
            for found in classify.edges_inside_speech(blocks, doc)
            if seeds_segment(found["type"])
        ]

    def _logs(self, recording, found):
        return self.store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind=EDGE_INSIDE_SPEECH,
                occurred_at=self.clock(),
                correlation_id=correlation_for(recording),
                punch_in_seconds=found["at"],
                error=(
                    f"{found['type']} block {found['edge']} {found['at']:.3f} is inside the "
                    f"word spanning {found['word_start']:.3f}-{found['word_end']:.3f}"
                ),
            )
        )
