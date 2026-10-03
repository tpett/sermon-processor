from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def now():
    return datetime.now(UTC)


@dataclass
class ScansOnSchedule:
    reconciles: object
    queues: object
    interval: timedelta
    clock: object = now
    prints: object = print
    due: datetime | None = None

    def __call__(self):
        moment = self.clock()
        if self.due is not None and moment < self.due:
            return False
        self.due = moment + self.interval
        try:
            scan = self.reconciles()
            if scan.failure:
                return self._fails(scan.failure)
            queued = self.queues()
        except Exception as error:  # noqa: BLE001 - a scan must never stop the worker
            return self._fails(f"{type(error).__name__}: {error}")
        named = ", ".join(item.recording_id for item in queued)
        self.prints(
            f"scheduled scan: discovered {scan.discovered_count}, "
            f"queued {len(queued)} for download" + (f": {named}" if named else "")
        )
        return True

    def _fails(self, reason):
        self.prints(f"scheduled scan failed: {reason}; next scan in {self.interval}")
        return True
