"""Doubles for the queue worker's handlers that a scenario does not expect to run."""


def refuses_other_work(*_args, **_kwargs):
    raise AssertionError("the worker ran a job or a step this scenario does not expect")
