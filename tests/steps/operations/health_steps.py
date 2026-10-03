from datetime import UTC, datetime, timedelta

from pytest_bdd import given, then, when

from sermon.store import Discovery, Job, Recording
from sermon.web import creates_app

FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


@when("I open the system health view", target_fixture="health")
def _(store):
    response = creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health")
    return response.get_json()


@then("I see how many jobs are queued, running, and failed")
def _(health):
    assert "queued" in health and "running" in health and "failed" in health


@then("I can see how long the oldest queued job has been waiting")
def _(health):
    assert "oldest_queued_seconds" in health


HEALTH_STATUSES = {"healthy", "unhealthy"}


@then("I see the status of:")
def _(health, datatable):
    named = sorted(row[0].strip() for row in datatable[1:])
    shown = health["dependencies"]
    assert sorted(shown) == named, f"the view names {sorted(shown)}"
    assert set(shown.values()) <= HEALTH_STATUSES, f"statuses {shown}"


@then("I see when the last webhook was received")
def _(health):
    assert "last_webhook_at" in health


@then("I see when the last reconciliation scan ran")
def _(health):
    assert "last_scan_at" in health


@then("I see how many recordings each discovered")
def _(health):
    assert "webhook_discovered" in health
    assert "scan_discovered" in health


@given("no recording has been ingested for 8 days")
def _(store):
    store.saves(
        Recording(
            recording_id="recording_20260815_103015",
            object_key="recordings/recording_20260815_103015.flac",
            state="reviewed",
            started_at=FROZEN - timedelta(days=8),
            started_at_source="key",
            size_bytes=1,
        )
    )


@then("I see how long it has been since the last ingest")
def _(health):
    assert health["last_ingest_seconds"] >= 8 * 24 * 3600


@then("no alert is raised")
def _(health):
    assert health["alerts"] == [], health["alerts"]
    assert health["storage_alert"] is False, health["storage_alert_reason"]


@then("no notification is sent")
def _(store):
    from sermon.store import Notification

    assert store.lists(Notification) == []


@when("an external monitor requests the health endpoint", target_fixture="health_response")
def _(store):
    return creates_app(store=store, clock=lambda: FROZEN).test_client().get("/api/health")


@then('it responds with "200 OK"')
def _(health_response):
    assert health_response.status_code == 200


@then("the body reports each dependency as healthy")
def _(health_response):
    body = health_response.get_json()
    assert all(status == "healthy" for status in body["dependencies"].values())


@given("the object store is unreachable")
def _(store):
    store.saves(
        Discovery(
            kind="scan",
            occurred_at=FROZEN,
            discovered_count=0,
            failure="transient",
        )
    )


@then("it responds with a non-success status")
def _(health_response):
    assert health_response.status_code >= 400


@then("the body names the unhealthy dependency")
def _(health_response):
    body = health_response.get_json()
    assert body["dependencies"]["the object store"] != "healthy"
