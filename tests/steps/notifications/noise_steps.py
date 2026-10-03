from datetime import timedelta

from pytest_bdd import given, parsers, then, when

from sermon.approves_segment import ApprovesSegment
from sermon.reruns_analysis import RerunsAnalysis
from sermon.skips_segment import SkipsSegment
from sermon.store import LogEntry, Recording, Reviewer, Segment
from sermon.web import creates_app

from steps import _notifications
from steps._markup import reads_rows

SUNDAY_RECORDINGS = (
    "recording_20260823_083000",
    "recording_20260823_093000",
    "recording_20260823_103015",
)
DELIVERY_FAILED = "notification_delivery_failed"


@given("three Recordings finish Analysis within 5 minutes")
def _(store, delivery_channel, moments):
    layouts = (_notifications.ONLY_MUSIC, _notifications.LESSON_AND_SERMON, _notifications.SUNDAY)
    for recording_id, rows in zip(SUNDAY_RECORDINGS, layouts):
        _notifications.finishes_analysis(store, rows, delivery_channel, moments, recording_id=recording_id)
        moments.passes(timedelta(minutes=2))


@then("the reviewer receives one notification covering all three")
def _(delivery_channel):
    assert len(delivery_channel.received) == 1, [item.summary for item in delivery_channel.received]


@then("it lists what was found in each")
def _(store, delivery_channel):
    assert len(delivery_channel.received) == 1
    summary = delivery_channel.received[0].summary
    for recording_id in SUNDAY_RECORDINGS:
        recorded = store.loads(Recording, recording_id).started_at.strftime("%Y-%m-%d %H:%M")
        assert recorded in summary, (recorded, summary)
    for segment in store.lists(Segment):
        assert segment.classification in summary


@given("a Recording has already notified the reviewer")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.SUNDAY, delivery_channel, moments)
    assert [item.kind for item in delivery_channel.received] == ["segment_proposed"]


@when("Analysis is re-run and completes again")
def _(store, delivery_channel, moments):
    moments.passes(timedelta(hours=1))
    recording = _notifications.registered(store)
    RerunsAnalysis(store=store, clock=moments)(recording)
    _notifications.runs_analysis(store, recording, delivery_channel, moments)


@then("the reviewer is notified again")
def _(store, delivery_channel):
    kinds = [item.kind for item in delivery_channel.received]
    assert kinds == ["segment_proposed", "segment_proposed"], kinds
    assert len({item.notification_id for item in delivery_channel.received}) == 2


@then("the notification says it is an updated proposal")
def _(delivery_channel):
    first, again = delivery_channel.received
    assert "updated proposal" not in first.summary.lower()
    assert again.summary.lower().startswith("updated proposal")


@given("a Recording has had an undispositioned publishable Segment for 3 days")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.SUNDAY, delivery_channel, moments)
    assert [item.state for item in store.lists(Segment)] == ["proposed"]
    _notifications.sweeps(store, delivery_channel, moments, days=3)


@then("a reminder is sent to the reviewer")
def _(store, delivery_channel):
    recording = _notifications.registered(store)
    reminders = [item for item in delivery_channel.received if item.kind == "review_reminder"]
    assert [(item.recording_id, item.recipient) for item in reminders] == [(recording.recording_id, "reviewer")]


@given("every Segment in a Recording has been approved or skipped")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.LESSON_AND_SERMON, delivery_channel, moments)
    lesson, sermon = sorted(store.lists(Segment), key=lambda item: item.punch_in_seconds)
    SkipsSegment(store=store, clock=moments)(lesson)
    ApprovesSegment(store=store, clock=moments)(
        store.saves(_notifications.labelled(store.loads(Segment, sermon.segment_id)))
    )
    _notifications.sweeps(store, delivery_channel, moments, days=4)


@then("no reminder is sent for that Recording")
def _(store, delivery_channel):
    assert [item.kind for item in delivery_channel.received] == ["segment_proposed"]
    assert [item.kind for item in _notifications.raised(store)] == ["segment_proposed"]


@then("skipped Segments never generate notifications of their own")
def _(store):
    skipped = store.lists(Segment, state="skipped")
    assert len(skipped) == 1
    assert [item for item in _notifications.raised(store) if item.segment_id == skipped[0].segment_id] == []


@given("the configured channel is unavailable")
def _(delivery_channel):
    delivery_channel.available = False


@when("delivery is attempted")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.SUNDAY, delivery_channel, moments)


@then("delivery is retried")
def _(store, delivery_channel):
    notification = _notifications.the_only(store)
    failures = [item for item in store.lists(LogEntry) if item.kind == DELIVERY_FAILED]
    assert delivery_channel.attempts >= 2
    assert len(failures) == delivery_channel.attempts
    assert {item.correlation_id for item in failures} == {f"notification:{notification.notification_id}"}


@then(parsers.parse('the Notification remains recorded with state "{state}"'))
def _(store, state):
    assert _notifications.the_only(store).state == state


@then("the failure is visible on the system health view")
def _(store):
    body = creates_app(store=store).test_client().get("/api/health").get_json()
    assert body["dependencies"]["the notification channel"] == "unhealthy"
    assert body["undelivered_notifications"] == 1


@then("no Recording or Segment state is affected")
def _(store):
    assert [item.state for item in store.lists(Recording)] == ["awaiting_review"]
    assert [item.state for item in store.lists(Segment)] == ["proposed"]


@given("a Recording produced nothing publishable")
def _(store, delivery_channel, moments):
    _notifications.finishes_analysis(store, _notifications.ONLY_MUSIC, delivery_channel, moments)


@then(parsers.parse('a Notification is recorded with state "{state}"'))
def _(store, state):
    notification = _notifications.the_only(store)
    assert (notification.kind, notification.state) == ("nothing_publishable", state)


@then("nothing is delivered")
def _(store, delivery_channel):
    assert delivery_channel.attempts == 0
    assert [item.state for item in _notifications.raised(store)] == ["suppressed"]


@when("a reviewer disables notifications")
def _(store, moments):
    response = creates_app(store=store, clock=moments).test_client().post(
        "/notifications/preference", data={"receives": "off"}
    )
    assert response.status_code == 303


@then("no further notifications are sent to them")
def _(store, delivery_channel):
    assert store.loads(Reviewer, "reviewer").receives_notifications is False
    raised = _notifications.raised(store)
    assert raised, "nothing was raised after opting out, so nothing shows a notification was withheld"
    assert delivery_channel.attempts == 0


@then("recordings still appear in the recordings list")
def _(store):
    recordings = store.lists(Recording)
    assert recordings, "no Recording exists, so the list cannot show one"
    page = creates_app(store=store).test_client().get("/").get_data(as_text=True)
    assert {row["id"] for row in reads_rows(page, "recording")} == {item.recording_id for item in recordings}
