from __future__ import annotations

from dataclasses import dataclass, replace

from sermon.store import Job, Store


@dataclass(frozen=True)
class RecoversInterruptedJobs:
    """Return jobs the last process died holding to the queue.

    A job is marked `running` before the work starts, so a crash or a restart
    leaves it there with nothing driving it. Requeueing is the only way it ever
    finishes, and it must not enqueue a second job to do it — the recovered row
    is the same row, with the attempt it already spent still counted against its
    budget.
    """

    store: Store

    def __call__(self):
        interrupted = self.store.lists(Job, state="running")
        return tuple(
            self.store.saves(replace(job, state="queued")) for job in interrupted
        )
