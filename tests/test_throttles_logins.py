from datetime import UTC, datetime, timedelta

from sermon.throttles_logins import (
    ADDRESS_FAILURES_FREE,
    EMAIL_FAILURES_FREE,
    FIRST_WAIT,
    FORGET_AFTER,
    LONGEST_WAIT,
    MAX_TRACKED,
    ThrottlesLogins,
)

START = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
NOBODY = timedelta(0)


class Moving:
    def __init__(self):
        self.moment = START

    def __call__(self):
        return self.moment

    def passes(self, span):
        self.moment += span


def fails(throttle, email, address, times):
    for _ in range(times):
        throttle.fails(email, address)


def test_nobody_is_held_off_before_anyone_has_failed():
    assert ThrottlesLogins(clock=Moving())("pastor@a.example", "100.64.0.9") == NOBODY


def test_failures_up_to_the_free_count_hold_nobody_off():
    throttle = ThrottlesLogins(clock=Moving())
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE - 1)
    assert throttle("pastor@a.example", "100.64.0.9") == NOBODY


def test_the_failure_that_uses_up_the_free_count_holds_that_address_off_for_the_first_wait():
    throttle = ThrottlesLogins(clock=Moving())
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE)
    assert throttle("pastor@a.example", "100.64.0.9") == FIRST_WAIT


def test_the_email_is_held_off_whichever_machine_it_is_tried_from():
    throttle = ThrottlesLogins(clock=Moving())
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE)
    assert throttle("pastor@a.example", "100.64.0.77") == FIRST_WAIT


def test_other_people_are_not_held_off_by_one_persons_failures():
    throttle = ThrottlesLogins(clock=Moving())
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE)
    assert throttle("elder@a.example", "100.64.0.77") == NOBODY


def test_the_wait_runs_down_with_the_clock_and_then_ends():
    clock = Moving()
    throttle = ThrottlesLogins(clock=clock)
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE)
    clock.passes(FIRST_WAIT - timedelta(seconds=10))
    assert throttle("pastor@a.example", "100.64.0.9") == timedelta(seconds=10)
    clock.passes(timedelta(seconds=10))
    assert throttle("pastor@a.example", "100.64.0.9") == NOBODY


def test_each_further_failure_doubles_the_wait_up_to_the_longest():
    clock = Moving()
    throttle = ThrottlesLogins(clock=clock)
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE)
    waited = [throttle("pastor@a.example", "100.64.0.9")]
    for _ in range(12):
        clock.passes(waited[-1])
        throttle.fails("pastor@a.example", "100.64.0.9")
        waited.append(throttle("pastor@a.example", "100.64.0.9"))
    assert waited[:3] == [FIRST_WAIT, FIRST_WAIT * 2, FIRST_WAIT * 4]
    assert max(waited) == LONGEST_WAIT == waited[-1]


def test_a_success_clears_that_persons_failures():
    throttle = ThrottlesLogins(clock=Moving())
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE - 1)
    throttle.succeeds("pastor@a.example")
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE - 1)
    assert throttle("pastor@a.example", "100.64.0.9") == NOBODY


def test_one_address_trying_many_emails_is_held_off_though_no_email_is():
    throttle = ThrottlesLogins(clock=Moving())
    for number in range(ADDRESS_FAILURES_FREE):
        throttle.fails(f"person{number}@a.example", "100.64.0.9")
    assert throttle("another@a.example", "100.64.0.9") == FIRST_WAIT
    assert throttle("another@a.example", "100.64.0.10") == NOBODY


def test_a_success_does_not_clear_what_an_address_has_tried():
    throttle = ThrottlesLogins(clock=Moving())
    for number in range(ADDRESS_FAILURES_FREE):
        throttle.fails(f"person{number}@a.example", "100.64.0.9")
    throttle.succeeds("person0@a.example")
    assert throttle("person0@a.example", "100.64.0.9") == FIRST_WAIT


def test_failures_are_forgotten_after_an_idle_hour():
    clock = Moving()
    throttle = ThrottlesLogins(clock=clock)
    fails(throttle, "pastor@a.example", "100.64.0.9", EMAIL_FAILURES_FREE - 1)
    clock.passes(FORGET_AFTER + timedelta(seconds=1))
    throttle.fails("pastor@a.example", "100.64.0.9")
    assert throttle("pastor@a.example", "100.64.0.9") == NOBODY


def test_what_is_remembered_is_bounded():
    clock = Moving()
    throttle = ThrottlesLogins(clock=clock)
    for number in range(MAX_TRACKED + 500):
        clock.passes(timedelta(milliseconds=1))
        throttle.fails(f"spray{number}@a.example", f"10.0.{number % 250}.{number // 250}")
    assert throttle.tracked() <= MAX_TRACKED
