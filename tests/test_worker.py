"""The worker loop and what a restart does to work that was in flight.

Nothing here touches the object store: the queue holds 93 download jobs against
a read-only 39 GiB bucket, so a test that ran a real handler would pull the
bucket down. The loop takes its runner as an argument for exactly that reason.
"""

from argparse import Namespace
from datetime import UTC, datetime

import pytest

from sermon.cli import drains, parses_work_command
from sermon.jobs.recovers_interrupted_jobs import RecoversInterruptedJobs
from sermon.store import Job, Recording, opens_store

FROZEN = datetime(2026, 8, 23, 12, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def asked(**over):
    return Namespace(
        **{"once": False, "limit": 0, "poll": 5.0, "corpus": None, "prompts": None, **over}
    )


def queue(count):
    """A runner that hands out `count` jobs and then reports an empty queue."""
    jobs = [
        Job(
            job_id=index + 1,
            recording_id=f"recording_2026082{index}_103015",
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key=f"download:{index}",
            queued_at=FROZEN,
        )
        for index in range(count)
    ]
    handed = []

    def runs():
        if not jobs:
            return None
        handed.append(jobs.pop(0))
        return handed[-1]

    runs.handed = handed
    return runs


def test_once_runs_a_single_job_even_with_a_full_queue():
    runs = queue(93)
    said = []
    assert drains(runs, asked(once=True), said.append, lambda _: None) == 0
    assert len(runs.handed) == 1


def test_a_limit_caps_the_run():
    runs = queue(93)
    assert drains(runs, asked(limit=3), lambda _: None, lambda _: None) == 0
    assert len(runs.handed) == 3


def test_an_empty_queue_says_so_and_stops():
    said = []
    assert drains(queue(0), asked(once=True), said.append, lambda _: None) == 0
    assert "nothing queued" in said


def test_running_forever_sleeps_when_there_is_nothing_to_do():
    naps = []

    def runs():
        if len(naps) >= 3:
            raise KeyboardInterrupt
        return None

    with pytest.raises(KeyboardInterrupt):
        drains(runs, asked(poll=2.5), lambda _: None, naps.append)
    assert naps == [2.5, 2.5, 2.5]


def test_each_job_run_is_reported():
    said = []
    drains(queue(2), asked(limit=2), said.append, lambda _: None)
    assert said == [
        "ran download job 1 for recording_20260820_103015",
        "ran download job 2 for recording_20260821_103015",
    ]


def test_a_restart_requeues_what_was_running_without_duplicating_it(store):
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key="recordings/recording_20260823_103015.flac",
            state="downloaded",
            started_at=FROZEN,
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            kind="render",
            state="running",
            attempts=1,
            max_attempts=5,
            dedupe_key="render:1",
            queued_at=FROZEN,
            started_at=FROZEN,
        )
    )
    recovered = RecoversInterruptedJobs(store=store)()

    assert [job.state for job in recovered] == ["queued"]
    assert len(store.lists(Job)) == 1, "recovery must not enqueue a second job"
    assert store.lists(Job)[0].attempts == 1, "the spent attempt still counts"


def test_a_restart_leaves_queued_work_alone(store):
    store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key="recordings/recording_20260823_103015.flac",
            state="discovered",
            started_at=FROZEN,
            started_at_source="key",
            size_bytes=1,
        )
    )
    store.saves(
        Job(
            recording_id="recording_20260823_103015",
            kind="download",
            state="queued",
            max_attempts=5,
            dedupe_key="download:1",
            queued_at=FROZEN,
        )
    )
    assert RecoversInterruptedJobs(store=store)() == ()
    assert store.lists(Job)[0].state == "queued"


def test_the_command_line_defaults_to_running_forever():
    parsed = parses_work_command([], print)
    assert (parsed.once, parsed.limit) == (False, 0)


def test_a_corpus_can_be_named_for_analysis():
    parsed = parses_work_command(["--corpus", "/tmp/corpus", "--once"], print)
    assert (parsed.corpus, parsed.once) == ("/tmp/corpus", True)
