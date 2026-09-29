from sermon.web import creates_app

REDIRECTS = frozenset({301, 302, 303, 307, 308})


def opens_app(store, clock=None):
    if clock is None:
        return creates_app(store=store)
    return creates_app(store=store, clock=clock)


def opens_detail(store, recording_id, clock=None, **query):
    client = opens_app(store, clock).test_client()
    given = {name: value for name, value in query.items() if value is not None}
    return client.get(f"/recordings/{recording_id}", query_string=given).get_data(as_text=True)


def posts(store, url, clock=None, **form):
    client = opens_app(store, clock).test_client()
    posted = client.post(url, data=form)
    if posted.status_code in REDIRECTS:
        return client.get(posted.headers["Location"]).get_data(as_text=True)
    return posted.get_data(as_text=True)


def recording_action(recording, action):
    return f"/recordings/{recording.recording_id}/actions/{action}"


def segment_action(segment, action):
    return f"/recordings/{segment.recording_id}/segments/{segment.segment_id}/{action}"


def boundary_action(segment, boundary):
    return (
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/boundaries/{boundary}"
    )


def span_action(segment, edge):
    return (
        f"/recordings/{segment.recording_id}/segments/{segment.segment_id}"
        f"/span/{edge}"
    )
