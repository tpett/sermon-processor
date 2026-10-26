from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

EMAIL_FAILURES_FREE = 5
ADDRESS_FAILURES_FREE = 20
FIRST_WAIT = timedelta(seconds=30)
LONGEST_WAIT = timedelta(minutes=15)
FORGET_AFTER = timedelta(hours=1)
MAX_TRACKED = 10_000
EMAIL = "email"
ADDRESS = "address"
FREE = {EMAIL: EMAIL_FAILURES_FREE, ADDRESS: ADDRESS_FAILURES_FREE}


def now():
    return datetime.now(UTC)


@dataclass
class Failures:
    count: int
    last_at: datetime
    held_until: datetime


@dataclass
class ThrottlesLogins:
    clock: object = now
    seen: OrderedDict = field(default_factory=OrderedDict, init=False)
    turn: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __call__(self, email, address):
        with self.turn:
            moment = self.clock()
            remaining = [
                self.held(key, moment) for key in ((EMAIL, email), (ADDRESS, address))
            ]
            return max(remaining)

    def fails(self, email, address):
        with self.turn:
            moment = self.clock()
            for key in ((EMAIL, email), (ADDRESS, address)):
                self.counts_against(key, moment)
            while len(self.seen) > MAX_TRACKED:
                self.seen.popitem(last=False)

    def succeeds(self, email):
        with self.turn:
            self.seen.pop((EMAIL, email), None)

    def tracked(self):
        return len(self.seen)

    def held(self, key, moment):
        failures = self.current(key, moment)
        if failures is None or failures.held_until <= moment:
            return timedelta(0)
        return failures.held_until - moment

    def counts_against(self, key, moment):
        failures = self.current(key, moment)
        count = 1 if failures is None else failures.count + 1
        over = count - FREE[key[0]]
        held_until = moment
        if over >= 0:
            held_until = moment + min(FIRST_WAIT * 2**over, LONGEST_WAIT)
        self.seen[key] = Failures(count=count, last_at=moment, held_until=held_until)
        self.seen.move_to_end(key)

    def current(self, key, moment):
        failures = self.seen.get(key)
        if failures is not None and moment - failures.last_at >= FORGET_AFTER:
            del self.seen[key]
            return None
        return failures
