from datetime import UTC, datetime

from pytest_bdd import given, then, when

from sermon.store import Job, Recording
from sermon.web import creates_app

FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@when("I open the system health view", target_fixture="health")
def _(store):
    return creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health").get_json()


@then("I see how many jobs are queued, running, and failed")
def _(health):
    assert "queued" in health and "running" in health and "failed" in health


@then("I can see how long the oldest queued job has been waiting")
def _(health):
    assert "oldest_queued_seconds" in health
