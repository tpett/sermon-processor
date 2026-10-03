import json
import os
import shutil
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path, PurePosixPath

from flask import Flask, redirect, render_template, request, send_file, url_for

from sermon.accepts_recording_webhook import AcceptsRecordingWebhook, now
from sermon.adjusts_punch_point import (
    AdjustsPunchPoint,
    BoundaryRejected,
    RevertsToProposal,
    reads_nudge_amount,
)
from sermon.analysis.io import reads_json
from sermon.approves_segment import ApprovesSegment, PublicationLabelRequired, SegmentNotReady
from sermon.archives_whole_recording import ArchivesWholeRecording
from sermon.authorizes_webhook import AuthorizesWebhook
from sermon.classifies_segment import ClassificationRejected, ClassifiesSegment
from sermon.discards_recording import (
    DiscardsRecording,
    PublishedSegmentExists,
    RestoresRecording,
)
from sermon.draws_waveform import words_across
from sermon.extends_segment_span import (
    SPAN_EDGES,
    ExtendsSegmentSpan,
    SpanWouldOverlapNeighbour,
)
from sermon.forces_ingestion import INGEST_ACTION, ForcesIngestion
from sermon.lists_recordings import ListsRecordings
from sermon.pipeline.preview import MEDIA_TYPE as PREVIEW_MEDIA_TYPE
from sermon.records_publication_details import (
    FilenameCollision,
    RecordsPublicationDetails,
    places_publication_date,
)
from sermon.reconciles_bucket import MalformedObjectKey, ReconcilesBucket
from sermon.reopens_segment import ReopensSegment, SegmentAlreadyRendered
from sermon.retries_processing import ProcessingNotFailed, RetriesProcessing
from sermon.reruns_analysis import RerunsAnalysis
from sermon.shows_recording import (
    NOTICES,
    PLAYHEAD_OUTSIDE_SPAN,
    ShowsRecording,
    formats_precise,
    formats_seconds,
)
from sermon.skips_segment import SkipsSegment
from sermon.splits_segment import CreatesSegment, MergesSegments, SplitsSegment
from sermon.splits_segment import NothingToMerge
from sermon.store import Artifact, Discovery, Job, Recording, Segment, layout
from sermon.store.vocabularies import SEGMENT_CLASSIFICATIONS


AUTHORIZATION = "Authorization"
BOUNDARIES = ("punch-in", "punch-out")
INLINE_KINDS = frozenset({"preview"})
ARTIFACT_UNAVAILABLE = "the artifact is unavailable"
REPROCESS_OFFER = "re-process the Segment"
NO_SUCH_RECORDING = ({"error": "no such recording"}, 404)
NO_SUCH_SEGMENT = ({"error": "no such segment"}, 404)


def unavailable(path, entity):
    """A 404 that names the trouble and offers the one cure: re-processing."""
    body = {
        "error": ARTIFACT_UNAVAILABLE,
        "path": path,
        "offered": REPROCESS_OFFER,
        "segment_id": getattr(entity, "segment_id", None),
        "recording_id": getattr(entity, "recording_id", None),
    }
    return body, 404


def creates_app(
    *, store, clock=now, lists_objects=None, fetches_object=None, webhook_token=None
):
    web_dir = Path(__file__).parent
    app = Flask(
        __name__,
        template_folder=str(web_dir / "templates"),
        static_folder=str(web_dir / "static"),
    )
    app.config["BIND_HOST"] = os.environ.get("SERMON_BIND_HOST", "100.64.0.1")
    app.add_template_filter(formats_precise, "precise")
    app.add_template_filter(formats_seconds, "seconds")
    app.jinja_env.globals["playhead_outside_span"] = PLAYHEAD_OUTSIDE_SPAN
    app.jinja_env.globals["notices"] = NOTICES
    accepts = AcceptsRecordingWebhook(store=store, clock=clock)
    authorizes = AuthorizesWebhook(token=webhook_token)
    lists = ListsRecordings(store=store, clock=clock)
    shows = ShowsRecording(store=store)
    approves = ApprovesSegment(store=store, clock=clock)
    skips = SkipsSegment(store=store, clock=clock)
    discards = DiscardsRecording(store=store, clock=clock)
    restores = RestoresRecording(store=store, clock=clock)
    reconciles = ReconcilesBucket(store=store, lists_objects=lists_objects, clock=clock)
    forces = ForcesIngestion(store=store, clock=clock)
    classifies = ClassifiesSegment(store=store, clock=clock)
    archives = ArchivesWholeRecording(store=store, clock=clock)
    reopens = ReopensSegment(store=store, clock=clock)
    retries_processing = RetriesProcessing(store=store, clock=clock)
    reruns = RerunsAnalysis(store=store, clock=clock)
    adjusts = AdjustsPunchPoint(store=store, clock=clock)
    reverts = RevertsToProposal(store=store, clock=clock)
    splits = SplitsSegment(store=store)
    merges = MergesSegments(store=store)
    creates = CreatesSegment(store=store)
    extends = ExtendsSegmentSpan(store=store)
    playheads = {}

    def playhead_of(recording_id, segment_id=None, focus=None):
        carried = request.values.get("playhead", type=float)
        if carried is not None:
            return carried
        held = playheads.get(recording_id)
        if held is not None:
            return held
        segments = store.lists(Segment, recording_id=recording_id)
        chosen = [one for one in segments if one.segment_id == segment_id] or segments
        if not chosen:
            return 0.0
        working = chosen[0]
        if focus == "punch-out":
            return min(working.punch_out_seconds, working.span_end_seconds)
        return max(working.punch_in_seconds, working.span_start_seconds)

    def returns_to(recording_id, notice, segment_id=None, focus=None):
        return redirect(
            url_for(
                "html_detail",
                recording_id=recording_id,
                notice=notice,
                segment=segment_id,
                focus=focus,
                zoom=request.values.get("zoom"),
                centre=request.values.get("centre"),
                playhead=request.values.get("playhead"),
                _anchor="waveform",
            ),
            code=303,
        )

    def reads_timecode(text):
        parts = [part for part in str(text).strip().split(":") if part != ""]
        if not parts:
            raise ValueError("no timecode was given")
        seconds = float(parts[-1])
        for place, part in enumerate(reversed(parts[:-1]), start=1):
            seconds += int(part) * 60**place
        return seconds

    def reads_classification():
        chosen = request.form.get("classification")
        if not chosen:
            return {}
        if chosen not in SEGMENT_CLASSIFICATIONS:
            raise ValueError("that is not a classification a Segment can have")
        return {"classification": chosen}

    def reads_page_criteria():
        return {
            "include_discarded": request.args.get("discarded") == "1",
            "filter_name": request.args.get("filter"),
            "classification": request.args.get("classification"),
            "q": request.args.get("q"),
            "page": request.args.get("page", type=int) or 1,
        }

    def keeps_the_narrowing(number):
        if number is None:
            return None
        return url_for("home", **{**request.args.to_dict(), "page": number})

    SCAN_NOTICES = {
        "scanned": "the bucket was scanned",
        "scan-transient": "the object store could not be reached; nothing changed",
        "scan-credentials": "the object store refused the credentials; nothing changed",
    }

    def scan_notice():
        said = SCAN_NOTICES.get(request.args.get("notice", ""))
        if said is None:
            return None
        found = request.args.get("found", type=int)
        if found is None:
            return said
        if found == 0:
            return f"{said}; nothing new"
        return f"{said}; {found} new recording{'' if found == 1 else 's'} found"

    @app.get("/")
    def home():
        paged = lists.paginates(**reads_page_criteria())
        return render_template(
            "list.html",
            recordings=paged.rows,
            awaiting=paged.awaiting,
            paging=paged,
            previous_url=keeps_the_narrowing(paged.previous),
            next_url=keeps_the_narrowing(paged.next),
            notice=scan_notice(),
            searched=request.args.get("q"),
        )

    @app.get("/recordings/<recording_id>")
    def html_detail(recording_id):
        selected = request.args.get("segment", type=int)
        focus = request.args.get("focus")
        view = shows(
            recording_id,
            selected_segment_id=selected,
            playhead_seconds=playhead_of(recording_id, selected, focus),
            zoom=request.args.get("zoom"),
            centre_seconds=request.args.get("centre", type=float),
            auditioning=request.args.get("preview"),
            notice=request.args.get("notice"),
            focused_boundary=focus,
        )
        if view is None:
            return ("", 404)
        return render_template("detail.html", view=view, payload=json.dumps(asdict(view)))

    @app.get("/api/recordings/<recording_id>/peaks")
    def recording_peaks(recording_id):
        recording = store.loads(Recording, recording_id)
        if recording is None:
            return NO_SUCH_RECORDING
        payload = reads_json(store, recording, "waveform_peaks") or {}
        resolutions = payload.get("resolutions") or {}
        wanted = request.args.get("resolution", "overview")
        if wanted not in resolutions:
            return ("", 404)
        return {
            "recording_id": recording_id,
            "duration_seconds": payload.get("duration_seconds"),
            "full_scale": payload.get("full_scale"),
            "resolution": wanted,
        } | resolutions[wanted]

    @app.get("/api/recordings/<recording_id>/words")
    def recording_words(recording_id):
        recording = store.loads(Recording, recording_id)
        if recording is None:
            return ("", 404)
        document = reads_json(store, recording, "transcript") or {}
        transcript = tuple(
            (item["start"], item["end"], item.get("text", ""), item.get("speaker"))
            for item in document.get("utterances", [])
        )
        start = request.args.get("from", type=float)
        seconds = request.args.get("seconds", type=float)
        if start is None or seconds is None or seconds <= 0:
            return ("", 400)
        return {
            "recording_id": recording_id,
            "from_seconds": start,
            "seconds": seconds,
            "words": [
                {
                    "text": word.text,
                    "at": word.at,
                    "at_seconds": word.at_seconds,
                    "left": word.left,
                }
                for word in words_across(transcript, start, seconds)
            ],
        }

    @app.post("/api/webhooks/recordings")
    def recordings_webhook():
        refusal, named = authorizes(request.headers.get(AUTHORIZATION))
        if refusal is not None:
            return {"error": named}, refusal
        status, detail = accepts(request.get_json(silent=True) or {})
        if status == 422:
            return detail, 422
        return ("", status)

    @app.get("/api/recordings")
    def recordings_list():
        paged = lists.paginates(**reads_page_criteria())
        return {
            "recordings": [asdict(row) for row in paged.rows],
            "awaiting_disposition": paged.awaiting,
            "page": paged.page,
            "pages": paged.pages,
            "total": paged.total,
        }

    def finds_artifact(path):
        artifacts = store.lists(Artifact)
        matching = [item for item in artifacts if item.path == path]
        if matching:
            return matching[0]
        recordings = [
            item
            for item in store.lists(Recording)
            if path in {item.local_path, item.object_key}
        ]
        if recordings:
            return recordings[0]
        return moved_since(artifacts, path)

    def moved_since(artifacts, path):
        """A link handed out before the layout was organised.

        The reviewer's MP3s were at the top of the data root and are now under
        `published/`; a Recording's documents were in `<recording_id>/` and are
        now under `recordings/`. Those links are in people's hands, so the path
        they were given is read as the tail of where the artifact lives now.
        Only one row may claim it: `preview.mp3` alone names every Recording's
        preview and must not resolve to whichever one is listed first.
        """
        wanted = PurePosixPath(path).parts
        carrying = [
            item for item in artifacts if PurePosixPath(item.path).parts[-len(wanted):] == wanted
        ]
        return carrying[0] if len(carrying) == 1 else None

    def restores_from_the_object_store(entity, path):
        """Refetch a source whose local copy was cleaned up to save disk."""
        if fetches_object is None or not isinstance(entity, Recording):
            return None
        held = layout.source_path(entity)
        destination = store.resolves(replace(entity, local_path=held))
        if fetches_object(entity.object_key, destination) is None:
            return None
        store.saves(replace(entity, local_path=held))
        return destination if destination.is_file() else None

    @app.get("/api/artifacts/<path:path>")
    def artifact_download(path):
        entity = finds_artifact(path)
        if entity is None:
            return unavailable(path, None)
        resolved = store.resolves(entity)
        if resolved is None or not resolved.is_file():
            resolved = restores_from_the_object_store(entity, path)
        if resolved is None or not resolved.is_file():
            return unavailable(path, entity)
        inline = isinstance(entity, Artifact) and entity.kind in INLINE_KINDS
        return send_file(
            resolved,
            mimetype=PREVIEW_MEDIA_TYPE if inline else None,
            as_attachment=not inline,
            download_name=Path(path).name,
            conditional=True,
        )

    @app.get("/api/health")
    def health():
        jobs = store.lists(Job)
        queued = [job for job in jobs if job.state == "queued"]
        oldest_queued_seconds = None
        if queued:
            oldest_queued_seconds = (clock() - queued[0].queued_at).total_seconds()
        scans = store.lists(Discovery, kind="scan")
        webhooks = store.lists(Discovery, kind="webhook")
        last_scan = scans[-1] if scans else None
        last_webhook = webhooks[-1] if webhooks else None
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        scan_failure = None if last_scan is None else last_scan.failure
        object_store_status = "unhealthy" if scan_failure else "healthy"
        disk_status = "healthy"
        channel_status = "healthy"
        alerts = []
        recordings = store.lists(Recording)
        if any("source no longer available" in recording.warnings for recording in recordings):
            alerts.append("source no longer available")
        status = 200 if object_store_status == "healthy" and ffmpeg_ok and disk_status == "healthy" else 503
        last_ingest_seconds = None
        short_on_disk = [item for item in recordings if item.waiting_since is not None]
        if recordings:
            newest = max(recordings, key=lambda item: item.started_at)
            last_ingest_seconds = (clock() - newest.started_at).total_seconds()
        body = {
            "queued": len(queued),
            "running": sum(1 for job in jobs if job.state == "running"),
            "failed": sum(1 for job in jobs if job.state == "failed"),
            "oldest_queued_seconds": oldest_queued_seconds,
            "bind_host": app.config["BIND_HOST"],
            "last_webhook_at": None if last_webhook is None else last_webhook.occurred_at.isoformat(),
            "last_scan_at": None if last_scan is None else last_scan.occurred_at.isoformat(),
            "webhook_discovered": 0 if last_webhook is None else last_webhook.discovered_count,
            "scan_discovered": 0 if last_scan is None else last_scan.discovered_count,
            "scan_failure": scan_failure,
            "last_ingest_seconds": last_ingest_seconds,
            "storage_alert": bool(short_on_disk) or bool(alerts),
            "storage_alert_reason": "local disk is short" if short_on_disk else (alerts[0] if alerts else None),
            "alerts": alerts,
            "object_store": object_store_status,
            "ffmpeg": ffmpeg_ok,
            "dependencies": {
                "the object store": object_store_status,
                "the job queue": "healthy",
                "the transcription service": "healthy",
                "local disk space": disk_status,
                "ffmpeg availability": "healthy" if ffmpeg_ok else "unhealthy",
                "the notification channel": channel_status,
            },
        }
        return body, status

    @app.post("/recordings/refresh")
    def refresh():
        # The scan is a bucket listing, not a download, so it answers inside the
        # request. What it enqueues is the long work, which is the queue's.
        before = {item.recording_id for item in store.lists(Recording)}
        reconciles()
        scans = store.lists(Discovery, kind="scan")
        found = len({item.recording_id for item in store.lists(Recording)} - before)
        if scans and scans[-1].failure:
            return redirect(url_for("home", notice=f"scan-{scans[-1].failure}"))
        return redirect(url_for("home", notice="scanned", found=found))

    @app.post("/api/ingest")
    def ingest():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return {"malformed": "body"}, 422
        if not body.get("object_key"):
            return {"missing": "object_key"}, 422
        try:
            recording = reconciles.ingests(body["object_key"])
        except MalformedObjectKey:
            return {"malformed": "object_key"}, 422
        return {"recording_id": recording.recording_id, "state": recording.state}, 202

    @app.get("/api/recordings/<recording_id>")
    def recording_detail(recording_id):
        selected = request.args.get("segment", type=int)
        view = shows(
            recording_id,
            selected_segment_id=selected,
            playhead_seconds=playhead_of(recording_id, selected),
        )
        if view is None:
            return NO_SUCH_RECORDING
        return asdict(view)

    @app.post("/api/recordings/<recording_id>/seek")
    def seek(recording_id):
        seconds = float(request.get_json()["seconds"])
        view = shows(recording_id, playhead_seconds=seconds)
        if view is None:
            return NO_SUCH_RECORDING
        playheads[recording_id] = seconds
        return asdict(view)

    @app.post("/api/segments/<int:segment_id>/approve")
    def approve_segment(segment_id):
        segment = store.loads(Segment, segment_id)
        if segment is None:
            return NO_SUCH_SEGMENT
        try:
            approved = approves(segment)
        except PublicationLabelRequired as error:
            return {"error": str(error), "prompt": "label"}, 409
        except SegmentNotReady as error:
            return {"error": str(error), "prompt": "not ready"}, 409
        return asdict(shows(approved.recording_id))

    @app.post("/api/recordings/<recording_id>/discard")
    def discard_recording(recording_id):
        body = request.get_json(silent=True) or {}
        recording = store.loads(Recording, recording_id)
        if recording is None:
            return NO_SUCH_RECORDING
        discarded = discards(recording, reason=body.get("reason"))
        return {"recording_id": discarded.recording_id, "state": discarded.state}

    @app.post("/api/recordings/<recording_id>/restore")
    def restore_recording(recording_id):
        recording = store.loads(Recording, recording_id)
        if recording is None:
            return NO_SUCH_RECORDING
        restored = restores(recording)
        return {"recording_id": restored.recording_id, "state": restored.state}

    @app.post("/api/segments/<int:segment_id>/skip")
    def skip_segment(segment_id):
        segment = store.loads(Segment, segment_id)
        if segment is None:
            return NO_SUCH_SEGMENT
        skipped = skips(segment)
        return asdict(shows(skipped.recording_id))

    @app.post("/recordings/<recording_id>/actions/<action>")
    def recording_action(recording_id, action):
        recording = store.loads(Recording, recording_id)
        if recording is None:
            return ("", 404)
        selected = request.form.get("segment", type=int)
        try:
            notice = performs_recording_action(recording, action, selected)
        except (BoundaryRejected, SpanWouldOverlapNeighbour, ValueError) as refusal:
            return returns_to(recording_id, str(refusal), selected)
        if notice is None:
            return ("", 404)
        return returns_to(recording_id, notice, selected)

    def performs_recording_action(recording, action, selected):
        if action == "discard":
            try:
                discards(
                    recording,
                    reason=request.form.get("reason") or None,
                    confirm=request.form.get("confirm") == "yes",
                )
            except PublishedSegmentExists:
                return "discard-needs-confirm"
            return "discarded"
        if action == "restore":
            restores(recording)
            return "restored"
        if action == "archive-whole-recording":
            archives(recording)
            return "archived"
        if action in {INGEST_ACTION, "retry-ingestion"}:
            return f"ingest-{forces(recording).outcome}"
        if action in {"re-run-analysis", "retry-analysis"}:
            reruns(recording)
            return "reanalysis-queued"
        if action == "create-segment":
            creates(
                recording,
                from_seconds=reads_timecode(request.form["from"]),
                to_seconds=reads_timecode(request.form["to"]),
                **reads_classification(),
            )
            return "created"
        if action == "split-segment":
            splits(store.loads(Segment, selected), at_seconds=reads_timecode(request.form["at"]))
            return "split"
        if action == "merge-segments":
            merges(store.loads(Segment, selected), neighbour_of(recording, selected))
            return "merged"
        return None

    def neighbour_of(recording, segment_id):
        held = sorted(
            store.lists(Segment, recording_id=recording.recording_id),
            key=lambda one: one.punch_in_seconds,
        )
        chosen = [one for one in held if one.segment_id == segment_id]
        if not chosen:
            raise NothingToMerge()
        following = [one for one in held if one.punch_in_seconds > chosen[0].punch_in_seconds]
        if not following:
            raise NothingToMerge()
        return following[0]

    @app.post("/recordings/<recording_id>/segments/<int:segment_id>/<action>")
    def segment_action(recording_id, segment_id, action):
        segment = store.loads(Segment, segment_id)
        if segment is None or segment.recording_id != recording_id:
            return ("", 404)
        focus = request.form.get("focus")
        try:
            notice = performs_segment_action(segment, action)
        except PublicationLabelRequired:
            return returns_to(recording_id, "label-required", segment_id, focus)
        except FilenameCollision:
            return returns_to(recording_id, "label-collides", segment_id, focus)
        except SegmentNotReady:
            return returns_to(recording_id, refusal_for(segment), segment_id, focus)
        except (
            BoundaryRejected, SegmentAlreadyRendered, ClassificationRejected, ProcessingNotFailed
        ) as refusal:
            return returns_to(recording_id, str(refusal), segment_id, focus)
        if notice is None:
            return ("", 404)
        return returns_to(recording_id, notice, segment_id, focus)

    def refusal_for(segment):
        queued = store.lists(Job, segment_id=segment.segment_id, kind="render")
        if segment.state == "approved" and queued:
            return "already-approved"
        return "not-ready"

    def performs_segment_action(segment, action):
        if action == "approve":
            approves(chosen_intent(segment))
            return "approved"
        if action == "skip":
            skips(segment)
            return "skipped"
        if action == "reopen":
            reopens(segment)
            return "reopened"
        if action == "retry-processing":
            _, queued = retries_processing(segment)
            return "processing-retried" if queued else "processing-standing"
        if action == "revert":
            reverts(segment)
            return "reverted"
        if action == "classify":
            classifies(segment, request.form.get("classification", ""))
            return "reclassified"
        return None

    def chosen_intent(segment):
        intent = request.form.get("intent")
        label = request.form.get("label")
        if intent is None and label is None:
            return segment
        chosen = store.saves(
            replace(
                segment,
                intent=intent or segment.intent,
                label=(label or None) if label is not None else segment.label,
            )
        )
        RecordsPublicationDetails(store=store).saves(
            chosen,
            publication_date=places_publication_date(
                chosen, store.loads(Recording, chosen.recording_id)
            ),
            label=chosen.label,
            replace_existing=request.form.get("replace") == "yes",
        )
        return store.saves(chosen)

    @app.post("/recordings/<recording_id>/segments/<int:segment_id>/span/<edge>")
    def span_action(recording_id, segment_id, edge):
        segment = store.loads(Segment, segment_id)
        if segment is None or segment.recording_id != recording_id or edge not in SPAN_EDGES:
            return ("", 404)
        try:
            extends(segment, **{f"{edge}_seconds": offered_edge(segment, edge)})
        except (SpanWouldOverlapNeighbour, BoundaryRejected, ValueError) as refusal:
            return returns_to(recording_id, str(refusal), segment_id, request.form.get("focus"))
        return returns_to(recording_id, "span-extended", segment_id, request.form.get("focus"))

    def offered_edge(segment, edge):
        action = request.form["do"]
        if action == "set":
            return reads_timecode(request.form["timecode"])
        if action == "nudge":
            step = reads_nudge_amount(request.form["amount"])
            held = getattr(segment, f"span_{edge}_seconds")
            return held - step if request.form["direction"] == "earlier" else held + step
        raise ValueError("no such span action")

    @app.post("/recordings/<recording_id>/segments/<int:segment_id>/boundaries/<boundary>")
    def boundary_action(recording_id, segment_id, boundary):
        segment = store.loads(Segment, segment_id)
        if segment is None or segment.recording_id != recording_id or boundary not in BOUNDARIES:
            return ("", 404)
        try:
            moved = moves_boundary(segment, boundary)
        except (BoundaryRejected, ValueError) as refusal:
            return returns_to(recording_id, str(refusal), segment_id, boundary)
        return returns_to(recording_id, moved, segment_id, boundary)

    def moves_boundary(segment, boundary):
        action = request.form["do"]
        if action == "focus":
            return "focused"
        if action == "revert":
            reverts(segment)
            return "reverted"
        adjusts(segment, **{f"{boundary.replace('-', '_')}_seconds": offered(segment, boundary, action)})
        return "adjusted"

    def offered(segment, boundary, action):
        held = getattr(segment, f"{boundary.replace('-', '_')}_seconds")
        if action == "set":
            return reads_timecode(request.form["timecode"])
        if action == "playhead":
            return playhead_of(segment.recording_id, segment.segment_id, boundary)
        if action == "nudge":
            step = reads_nudge_amount(request.form["amount"])
            return held - step if request.form["direction"] == "earlier" else held + step
        raise ValueError("no such boundary action")

    @app.put("/api/segments/<int:segment_id>/publication")
    def publication_details(segment_id):
        body = request.get_json()
        segment = store.loads(Segment, segment_id)
        if segment is None:
            return NO_SUCH_SEGMENT
        try:
            RecordsPublicationDetails(store=store).saves(
                segment,
                publication_date=date.fromisoformat(body["date"]),
                label=body["label"],
                replace_existing=body.get("replace") is True,
            )
        except FilenameCollision as collision:
            return {"error": NOTICES["label-collides"], "path": str(collision)}, 409
        return asdict(shows(segment.recording_id))

    return app
