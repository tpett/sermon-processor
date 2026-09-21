from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from sermon.approves_segment import ApprovesSegment
from sermon.config import ReadsConfiguration
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.downloads_recording import DownloadsRecording
from sermon.jobs.probes_recording import MeasuresRecordingAudio, ProbesRecording
from sermon.jobs.renders_mp3 import ChannelsNeedReview, RendersMp3
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.object_store import FetchesBucketObject, ListsBucketObjects, OpensObjectStore
from sermon.reconciles_bucket import ObjectStoreForbidden, ObjectStoreUnreachable, ReconcilesBucket
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.sends_notification import SendsNotification
from sermon.store import (
    Artifact,
    Discovery,
    Job,
    Recording,
    Reviewer,
    Segment,
    SkippedObject,
    opens_store,
)
from sermon.web import creates_app

ENVIRONMENT_FILE = ".env"
REVIEWER = "reviewer"
READS_TIMECODE = ReadsTimecode()
FETCH_USAGE = "usage: sermon-fetch <object-key-or-recording-id>"
RENDER_USAGE = (
    "usage: sermon-render <object-key-or-recording-id> "
    "--from <h:mm:ss> --to <h:mm:ss> --label <text> [--date <yyyy-mm-dd>]"
)
BIND_HOST = "SERMON_BIND_HOST"
PORT = "SERMON_PORT"
DEFAULT_PORT = 8000
QUOTES = "\"'"


def reads_environment_file(path):
    if not path.is_file():
        return {}
    settings = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().partition("=")
        if not separator or name.startswith("#"):
            continue
        settings[name.strip()] = value.strip().strip(QUOTES)
    return settings


def resolves_settings(root=None, environment=None):
    root = Path.cwd() if root is None else Path(root)
    environment = os.environ if environment is None else environment
    return {**reads_environment_file(root / ENVIRONMENT_FILE), **environment}


def lists_bucket(configuration):
    return ListsBucketObjects(
        bucket=configuration.object_store.bucket,
        client=OpensObjectStore(object_store=configuration.object_store)(),
    )


def opens(settings, lists_objects):
    configuration = ReadsConfiguration(resolves_settings() if settings is None else settings)()
    return (
        configuration,
        opens_store(configuration.data_root),
        lists_bucket(configuration) if lists_objects is None else lists_objects,
    )


def reconciles(settings=None, lists_objects=None, prints=print):
    configuration, store, lists_objects = opens(settings, lists_objects)
    try:
        prints(
            f"scanning {configuration.object_store.bucket} "
            f"at {configuration.object_store.endpoint}"
        )
        ReconcilesBucket(store=store, lists_objects=lists_objects)()
        scan = store.lists(Discovery, kind="scan")[-1]
        if scan.failure:
            prints(f"the scan failed: {scan.failure}")
            return 1
        prints(
            f"discovered {scan.discovered_count}, "
            f"skipped {len(store.lists(SkippedObject))}, "
            f"{len(store.lists(Recording))} recordings known"
        )
        return 0
    finally:
        store.close()


def fetch_for(configuration, fetches_object):
    if fetches_object is not None:
        return fetches_object
    return FetchesBucketObject(
        bucket=configuration.object_store.bucket,
        client=OpensObjectStore(object_store=configuration.object_store)(),
    )


def names_the_recording(store, named):
    for recording in store.lists(Recording):
        if named in (recording.recording_id, recording.object_key):
            return recording
    return None


def discovers(store, named, lists_objects):
    known = names_the_recording(store, named)
    if known is not None:
        return known
    ReconcilesBucket(store=store, lists_objects=lists_objects)()
    return names_the_recording(store, named)


def brings_local(store, recording, fetch, prints):
    local = store.resolves(recording)
    if local is None or not local.is_file():
        prints(f"fetching {recording.object_key}")
        recording = DownloadsRecording(
            store=store, fetches=fetch, probes=MeasuresRecordingAudio()
        )(recording)
    if recording.integrated_loudness_lufs is None:
        recording = ProbesRecording(
            store=store, measures=MeasuresRecordingAudio(resolves=store.resolves)
        )(recording)
    return recording


def reports_source(recording, prints):
    prints(f"{recording.object_key} -> {recording.local_path}")
    prints(
        f"{recording.size_bytes} bytes, {recording.duration_seconds:.1f} s, "
        f"{recording.channels} channels at {recording.sample_rate} Hz"
    )
    prints(
        f"{recording.integrated_loudness_lufs} LUFS integrated, "
        f"{recording.true_peak_dbtp} dBTP true peak, "
        f"{recording.loudness_range_lu} LU range"
    )
    for level in recording.channel_levels:
        prints(f"channel {level.channel}: {level.rms_db} dB RMS")
    prints(f"signal on {recording.mono_source or 'no single channel'}")
    for warning in recording.warnings:
        prints(f"warning: {warning}")


def fetches(settings=None, object_key=None, fetches_object=None, lists_objects=None,
            prints=print):
    if object_key is None:
        object_key = reads_one_argument(FETCH_USAGE, prints)
        if object_key is None:
            return 1
    configuration, store, lists_objects = opens(settings, lists_objects)
    try:
        recording = discovers(store, object_key, lists_objects)
        if recording is None:
            prints(f"the bucket holds no {object_key}")
            return 1
        reports_source(brings_local(store, recording, fetch_for(configuration, fetches_object), prints), prints)
        return 0
    except (ObjectStoreForbidden, ObjectStoreUnreachable) as refused:
        prints(f"the object store refused the fetch: {refused}")
        return 1
    finally:
        store.close()


def cuts_by_hand(store, recording, punch_in, punch_out, label, published_on, intent):
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=punch_in,
            span_end_seconds=punch_out,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            intent=intent,
            boundary_source="human",
        )
    )
    segment = RecordsPublicationDetails(store=store).saves(
        segment, publication_date=published_on, label=label, replace_existing=True
    )
    return ApprovesSegment(store=store)(segment)


def reports_render(store, artifact, rendered, prints):
    prints(f"{artifact.path} -> {store.resolves(artifact)}")
    prints(f"{artifact.size_bytes} bytes over {rendered.duration_seconds:.1f} s")
    prints(
        f"{rendered.achieved_loudness_lufs} LUFS integrated, "
        f"{rendered.achieved_true_peak_dbtp} dBTP true peak, "
        f"{rendered.kbps} kbps, {rendered.channels} channel at {rendered.sample_rate} Hz"
    )
    prints(f"input was {rendered.input_loudness_lufs} LUFS")
    for missed in rendered.misses():
        prints(f"off target: {missed}")
    if not rendered.misses():
        prints("on target")


def renders(settings=None, object_key=None, punch_in=None, punch_out=None, label=None,
            published_on=None, intent="publish", fetches_object=None, lists_objects=None,
            prints=print):
    asked = reads_render_arguments(object_key, punch_in, punch_out, label, published_on, prints)
    if asked is None:
        return 1
    object_key, punch_in, punch_out, label, published_on = asked
    configuration, store, lists_objects = opens(settings, lists_objects)
    store.saves(Reviewer(actor=REVIEWER, receives_notifications=True))
    try:
        recording = discovers(store, object_key, lists_objects)
        if recording is None:
            prints(f"the bucket holds no {object_key}")
            return 1
        recording = brings_local(store, recording, fetch_for(configuration, fetches_object), prints)
        if published_on is None:
            published_on = recording.started_at.date()
        segment = cuts_by_hand(
            store, recording, punch_in, punch_out, label, published_on, intent
        )
        produced = []
        RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store),
            renders=keeps_what_it_rendered(RendersMp3(), produced),
        )()
        artifacts = store.lists(Artifact, kind="rendered_mp3", segment_id=segment.segment_id)
        if not artifacts or not produced:
            prints(f"the render failed: {reads_failure(store, segment)}")
            return 1
        rendered = produced[-1]
        reports_render(store, artifacts[-1], rendered, prints)
        return 1 if rendered.misses() else 0
    except ChannelsNeedReview as unsettled:
        prints(f"{unsettled}; confirm which channel to take before rendering")
        return 1
    except (ObjectStoreForbidden, ObjectStoreUnreachable) as refused:
        prints(f"the object store refused the fetch: {refused}")
        return 1
    finally:
        store.close()


def keeps_what_it_rendered(renderer, produced):
    def renders_and_keeps(*arguments, **named):
        rendered = renderer(*arguments, **named)
        produced.append(rendered)
        return rendered

    return renders_and_keeps


def reads_failure(store, segment):
    jobs = store.lists(Job, kind="render", segment_id=segment.segment_id)
    return jobs[-1].last_error if jobs else "no render job ran"


def reads_one_argument(usage, prints):
    arguments = sys.argv[1:]
    if len(arguments) != 1:
        prints(usage)
        return None
    return arguments[0]


def reads_render_arguments(object_key, punch_in, punch_out, label, published_on, prints):
    if object_key is None:
        parsed = parses_render_command(sys.argv[1:], prints)
        if parsed is None:
            return None
        object_key, punch_in, punch_out, label, published_on = parsed
    return (
        object_key,
        READS_TIMECODE(punch_in),
        READS_TIMECODE(punch_out),
        label,
        None if published_on is None else date.fromisoformat(published_on),
    )


def parses_render_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-render", usage=RENDER_USAGE, add_help=True)
    parser.add_argument("recording")
    parser.add_argument("--from", dest="punch_in", required=True)
    parser.add_argument("--to", dest="punch_out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--date", dest="published_on")
    try:
        asked = parser.parse_args(arguments)
    except SystemExit:
        prints(RENDER_USAGE)
        return None
    return (asked.recording, asked.punch_in, asked.punch_out, asked.label, asked.published_on)


def starts(app, host, port):
    app.run(host=host, port=port)


def serves(settings=None, lists_objects=None, runs=starts):
    settings = resolves_settings() if settings is None else settings
    _, store, lists_objects = opens(settings, lists_objects)
    app = creates_app(store=store, lists_objects=lists_objects)
    app.config["BIND_HOST"] = settings.get(BIND_HOST, app.config["BIND_HOST"])
    runs(app, app.config["BIND_HOST"], int(settings.get(PORT, DEFAULT_PORT)))
    return 0
