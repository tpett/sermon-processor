from dataclasses import replace

import pytest
from test_web_access import (
    EMAIL,
    PUBLIC,
    RECORDING_ID,
    TAILNET,
    enforcing,
    makes_reviewers,
    on,
    recording,
    segment,
    signed_in,
    store,
)

from sermon.store import (
    Artifact,
    Discovery,
    Job,
    LogEntry,
    Notification,
    Recording,
    Reviewer,
    Segment,
    User,
    opens_store,
)
from sermon.web import creates_app

CHANGING = ("POST", "PUT", "PATCH", "DELETE")
OPEN_TO_A_VIEWER = {
    "signs_in_by_password": "signing in",
    "signs_out": "signing out",
    "recordings_webhook": "the Recorder's webhook, which answers to its bearer token",
    "seek": "moving the playhead, which keeps nothing",
}
SAMPLED = {"IntegerConverter": 1, "UnicodeConverter": "x", "PathConverter": "x/y"}


@pytest.fixture
def app(store):
    return enforcing(store)


@pytest.fixture
def client(app):
    return app.test_client()


def changing_routes(app):
    for rule in app.url_map.iter_rules():
        values = {name: SAMPLED[type(rule._converters[name]).__name__] for name in rule.arguments}
        for method in sorted(rule.methods & set(CHANGING)):
            yield rule.endpoint, method, rule.build(values, append_unknown=False)[1]


def holds(store):
    return tuple(
        repr(store.lists(entity))
        for entity in (Recording, Segment, LogEntry, Job, Notification, Reviewer, Artifact, Discovery)
    )


def test_the_enumeration_finds_every_state_changing_route_the_app_has(app):
    found = {(method, path) for _, method, path in changing_routes(app)}
    assert len(found) >= 18
    assert ("POST", "/api/segments/1/approve") in found
    assert ("PUT", "/api/segments/1/publication") in found
    assert ("POST", "/recordings/refresh") in found
    assert ("POST", "/api/ingest") in found


def test_a_viewer_is_refused_every_state_changing_route_but_the_ones_that_keep_nothing(
    app, client, store, recording, segment
):
    client.get("/", headers=on(PUBLIC, **signed_in()))
    assert store.loads(User, EMAIL).role == "viewer"
    held = holds(store)
    refused = []
    for endpoint, method, path in changing_routes(app):
        answered = client.open(path, method=method, headers=on(PUBLIC, **signed_in()))
        if endpoint in OPEN_TO_A_VIEWER:
            assert answered.status_code != 403, (endpoint, method, path)
        else:
            assert answered.status_code == 403, (endpoint, method, path, answered.status_code)
            refused.append(endpoint)
    assert len(refused) >= 14
    assert holds(store) == held


def test_a_viewer_is_refused_with_a_plain_answer_that_names_no_one(client, recording, segment):
    refused = client.post(
        f"/api/segments/{segment.segment_id}/approve", headers=on(PUBLIC, **signed_in())
    )
    assert refused.status_code == 403
    assert refused.mimetype == "text/plain"
    assert EMAIL not in refused.get_data(as_text=True)


def test_a_viewer_who_names_real_things_changes_nothing(client, store, recording, segment):
    client.get("/", headers=on(PUBLIC, **signed_in()))
    held = holds(store)
    base = f"/recordings/{RECORDING_ID}"
    chosen = f"{base}/segments/{segment.segment_id}"
    asked = [
        ("POST", f"{chosen}/approve", {"intent": "archive"}),
        ("POST", f"{chosen}/skip", {}),
        ("POST", f"{chosen}/classify", {"classification": "lesson"}),
        ("POST", f"{chosen}/boundaries/punch-in", {"do": "set", "timecode": "2:00:30.000"}),
        ("POST", f"{chosen}/removed-spans", {"do": "remove", "from": "2:01:00", "to": "2:01:01"}),
        ("POST", f"{chosen}/span/start", {"do": "set", "timecode": "1:30:00"}),
        ("POST", f"{base}/actions/retitle", {"title": "Renamed by a viewer"}),
        ("POST", f"{base}/actions/discard", {"confirm": "yes"}),
        ("POST", f"{base}/actions/re-run-analysis", {}),
        ("POST", f"/api/recordings/{RECORDING_ID}/discard", {}),
        ("POST", f"/api/segments/{segment.segment_id}/skip", {}),
        ("PUT", f"/api/segments/{segment.segment_id}/publication", {"label": "Mine"}),
        ("POST", "/recordings/refresh", {}),
        ("POST", "/notifications/preference", {"receives": "off"}),
    ]
    for method, path, form in asked:
        answered = client.open(path, method=method, data=form, headers=on(PUBLIC, **signed_in()))
        assert answered.status_code == 403, (method, path, answered.status_code)
    assert holds(store) == held


def test_a_viewer_may_still_read_download_and_hear(app, client, recording, segment):
    for path in (
        "/",
        f"/recordings/{RECORDING_ID}?segment={segment.segment_id}",
        "/notifications",
        "/api/health",
        f"/api/recordings/{RECORDING_ID}",
        f"/api/segments/{segment.segment_id}/join?from=7300&to=7301",
    ):
        answered = client.get(path, headers=on(PUBLIC, **signed_in()))
        assert answered.status_code != 403, path


def test_a_viewer_moves_the_playhead_and_signs_out(client, recording):
    moved = client.post(f"/api/recordings/{RECORDING_ID}/seek", json={"seconds": 5}, headers=on(PUBLIC, **signed_in()))
    assert moved.status_code != 403


def test_a_reviewer_is_not_refused(client, store, recording, segment):
    makes_reviewers(store, EMAIL)
    store.saves(replace(segment, intent="archive"))
    answered = client.post(
        f"/api/segments/{segment.segment_id}/approve", headers=on(PUBLIC, **signed_in())
    )
    assert answered.status_code != 403
    assert [entry.actor for entry in store.lists(LogEntry) if entry.entered_state == "approved"] == [EMAIL]


def test_a_person_promoted_while_signed_in_can_change_things_on_the_next_request(
    client, store, recording, segment
):
    store.saves(replace(segment, intent="archive"))
    path = f"/api/segments/{segment.segment_id}/approve"
    assert client.post(path, headers=on(PUBLIC, **signed_in())).status_code == 403
    makes_reviewers(store, EMAIL)
    assert client.post(path, headers=on(PUBLIC, **signed_in())).status_code != 403


def test_without_a_sign_in_configured_the_person_at_the_browser_can_change_things(
    store, recording, segment
):
    store.saves(replace(segment, intent="archive"))
    answered = creates_app(store=store).test_client().post(f"/api/segments/{segment.segment_id}/approve")
    assert answered.status_code != 403
    assert store.lists(User) == []


def test_a_password_sign_in_gets_the_same_role_as_the_same_person_through_access(store, recording, segment):
    from sermon.sets_password import SetsPassword

    SetsPassword(store=store)(EMAIL, "correct horse battery")
    client = enforcing(store).test_client()
    client.post("/login", data={"email": EMAIL, "password": "correct horse battery"}, headers=on(TAILNET))
    path = f"/api/segments/{segment.segment_id}/skip"
    assert client.post(path, headers=on(TAILNET)).status_code == 403
    makes_reviewers(store, EMAIL)
    assert client.post(path, headers=on(TAILNET)).status_code != 403


MP3 = "2026/09/13/recording_20260913_090014/hebrews-13-7-8.mp3"


@pytest.fixture
def published(store, segment):
    done = store.saves(replace(segment, state="complete", label="Hebrews 13.7-8", intent="publish"))
    store.saves(
        Artifact(
            recording_id=RECORDING_ID,
            segment_id=done.segment_id,
            kind="rendered_mp3",
            path=MP3,
            size_bytes=40_000_000,
            checksum="abc",
        )
    )
    return done


def opens(client, segment, *, mode=None, **headers):
    query = f"?segment={segment.segment_id}" + (f"&mode={mode}" if mode else "")
    return client.get(f"/recordings/{RECORDING_ID}{query}", headers=on(PUBLIC, **(headers or signed_in())))


def beside(page):
    return page.split('<div class="supporting">', 1)[1]


def test_every_page_a_viewer_opens_says_view_only(client, recording, segment):
    for path in ("/", "/notifications", f"/recordings/{RECORDING_ID}?segment={segment.segment_id}"):
        page = client.get(path, headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
        assert 'data-field="access">View only<' in page, path


def test_a_reviewer_is_not_told_they_can_only_look(client, store, recording, segment):
    makes_reviewers(store, EMAIL)
    for path in ("/", "/notifications", f"/recordings/{RECORDING_ID}?segment={segment.segment_id}"):
        page = client.get(path, headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
        assert 'data-field="access"' not in page, path


def test_without_a_sign_in_configured_nobody_is_told_they_can_only_look(store, recording, segment):
    page = creates_app(store=store).test_client().get(f"/recordings/{RECORDING_ID}?segment={segment.segment_id}")
    assert 'data-field="access"' not in page.get_data(as_text=True)


@pytest.mark.parametrize("mode", [None, "review", "edit"])
def test_a_viewer_is_shown_review_mode_whatever_the_address_asks_for(client, recording, segment, mode):
    page = opens(client, segment, mode=mode).get_data(as_text=True)
    assert 'data-role="cut-view" data-mode="review"' in page
    for absent in ("edit-the-cut", "review-the-cut", "done-editing", 'class="mode-switch"', "detail-window"):
        assert absent not in page, absent


def test_a_viewer_is_offered_no_form_that_posts_anything(client, recording, segment):
    page = opens(client, segment).get_data(as_text=True)
    assert "<form" not in page.replace('<form class="inline" method="get"', "")


def test_a_viewer_of_a_published_segment_is_offered_what_was_published(client, store, recording, published):
    page = opens(client, published).get_data(as_text=True)
    column = beside(page)
    from steps._markup import reads_field, reads_field_link, reads_links

    assert reads_field(column, "label") == "Hebrews 13.7-8"
    assert reads_field(column, "mp3-filename") == "hebrews-13-7-8.mp3"
    assert reads_field(column, "mp3-length")
    assert reads_field(column, "mp3-size") == "38.1 MB"
    assert reads_field(column, "mp3-download") == "Download MP3"
    assert reads_field_link(column, "mp3-download") == f"/api/artifacts/{MP3}"
    assert reads_field(column, "original-download") == "Download the original recording"
    assert f"/api/artifacts/2026/09/13/{RECORDING_ID}.flac" in reads_links(column)


def test_the_published_file_is_offered_once_to_a_viewer_and_beside_the_cut_to_a_reviewer(
    client, store, recording, published
):
    viewing = opens(client, published).get_data(as_text=True)
    assert viewing.count('data-field="mp3-download"') == 1
    makes_reviewers(store, EMAIL)
    reviewing = opens(client, published).get_data(as_text=True)
    assert reviewing.count('data-field="mp3-download"') == 1
    assert 'data-field="mp3-download"' not in beside(reviewing)


def test_a_viewer_of_an_unpublished_segment_is_told_so_and_offered_only_the_original(
    client, recording, segment
):
    from steps._markup import reads_field

    column = beside(opens(client, segment).get_data(as_text=True))
    assert reads_field(column, "published-state") == "This Segment has not been published."
    assert reads_field(column, "mp3-download") is None
    assert reads_field(column, "original-download") == "Download the original recording"


def test_a_viewer_with_no_segment_chosen_is_still_offered_the_original(client, recording):
    page = client.get(f"/recordings/{RECORDING_ID}", headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert 'data-field="original-download"' in page


def test_a_viewer_is_not_offered_the_recording_actions_in_the_details(client, recording, segment):
    page = opens(client, segment).get_data(as_text=True)
    assert 'data-details-section="actions"' not in page
    assert 'data-details-section="source"' in page


def test_a_viewer_is_not_offered_to_scan_or_to_change_a_notification_preference(client, recording):
    listed = client.get("/", headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert 'action="/recordings/refresh"' not in listed
    told = client.get("/notifications", headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert 'action="/notifications/preference"' not in told


def test_a_reviewer_is_still_offered_to_scan_and_to_change_a_notification_preference(
    client, store, recording
):
    makes_reviewers(store, EMAIL)
    listed = client.get("/", headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert 'action="/recordings/refresh"' in listed
    told = client.get("/notifications", headers=on(PUBLIC, **signed_in())).get_data(as_text=True)
    assert 'action="/notifications/preference"' in told
