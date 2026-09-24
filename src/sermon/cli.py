from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from sermon.analysis import MeasuresBoundaryError, ProposesFromStoredTranscript, ReadsStoredTranscript
from sermon.analysis.proposes_from_transcript import BindsCorpusRoots
from sermon.analysis.proposes_from_transcript import ASR_CONFIG, CLASSIFIER, SUMMARIZER, TranscriptNotStored
from sermon.analysis.transcribes_audio import transcribes_with
from sermon.approves_segment import ApprovesSegment
from sermon.binds_model_endpoint import BindsModelEndpoint
from sermon.config import DATA_ROOT, ModelEndpointUnreachable, MissingConfiguration, ReadsConfiguration
from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.analyzes_recording import RecordingContents, RunsAnalyzeJob
from sermon.jobs.downloads_recording import DownloadsRecording, RunsDownloadJob
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.jobs.probes_recording import MeasuresRecordingAudio, ProbesRecording
from sermon.jobs.recovers_interrupted_jobs import RecoversInterruptedJobs
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.jobs.renders_mp3 import ChannelsNeedReview, RendersMp3
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.object_store import FetchesBucketObject, ListsBucketObjects, OpensObjectStore
from sermon.organizes_data_root import IN_PLACE, OrganizesDataRoot
from sermon.pipeline.classify import hms
from sermon.pipeline.roots import RootNotConfigured
from sermon.reconciles_bucket import (
    DEFAULT_CUTOFF,
    ObjectStoreForbidden,
    ObjectStoreUnreachable,
    ReconcilesBucket,
)
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.sends_notification import SendsNotification
from sermon.store import (
    Artifact,
    Block,
    Discovery,
    Job,
    Proposal,
    Recording,
    Reviewer,
    Segment,
    SkippedObject,
    StoredSchemaDiffers,
    layout,
    opens_store,
)
from sermon.web import creates_app
from waitress import serve

ENVIRONMENT_FILE = ".env"
REVIEWER = "reviewer"
READS_TIMECODE = ReadsTimecode()
FETCH_USAGE = "sermon-fetch <object-key-or-recording-id>"
RENDER_USAGE = (
    "sermon-render <object-key-or-recording-id> "
    "--from <h:mm:ss> --to <h:mm:ss> --label <text> [--date <yyyy-mm-dd>]"
)
ANALYZE_USAGE = (
    "sermon-analyze <recording-id> --corpus <corpus-root> "
    "[--prompts <path>] [--model <name>] [--summaries <name-or-none>] [--asr <config>]"
)
PROPOSE_USAGE = (
    "sermon-propose <recording-id> [<recording-id> ...] --corpus <corpus-root> "
    "[--prompts <path>] [--model <name>] [--summaries <name-or-none>] "
    "[--asr <config>] [--store <data-root>]"
)
NO_SUMMARIES = "none"
NOTHING_FABRICATED = RecordingContents(segments=())
JOB_ATTEMPTS = 5
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


def opens_or_reports(settings, lists_objects, prints):
    try:
        return opens(settings, lists_objects)
    except StoredSchemaDiffers as stale:
        prints(str(stale))
        return None


INGEST_CUTOFF = "SERMON_INGEST_CUTOFF"


def cutoff_from(environment=None):
    """The date before which the scan creates no Recording.

    The spec sets it to the Processor's deployment date, and Q7 is why: 'Not
    needed except for testing. Everything in the old recordings list has already
    been edited and published.' Without it a first scan of a bucket holding
    years of services discovers every one of them and queues a download for
    each -- 39 GiB of already-published audio.
    """
    named = (os.environ if environment is None else environment).get(INGEST_CUTOFF)
    if not named:
        return DEFAULT_CUTOFF
    return date.fromisoformat(named)


def reconciles(settings=None, lists_objects=None, prints=print):
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    configuration, store, lists_objects = opened
    try:
        prints(
            f"scanning {configuration.object_store.bucket} "
            f"at {configuration.object_store.endpoint}"
        )
        ReconcilesBucket(
            store=store, lists_objects=lists_objects, ingest_cutoff=cutoff_from()
        )()
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


class NothingNamesIt(RuntimeError):
    pass


def discovers(store, named, lists_objects):
    known = names_the_recording(store, named)
    if known is not None:
        return known
    ReconcilesBucket(store=store, lists_objects=lists_objects)()
    scans = store.lists(Discovery, kind="scan")
    if scans and scans[-1].failure:
        raise NothingNamesIt(f"the scan for {named} failed: {scans[-1].failure}")
    found = names_the_recording(store, named)
    if found is None:
        raise NothingNamesIt(f"the bucket holds no {named}")
    return found


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
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    configuration, store, lists_objects = opened
    try:
        recording = discovers(store, object_key, lists_objects)
        reports_source(brings_local(store, recording, fetch_for(configuration, fetches_object), prints), prints)
        return 0
    except NothingNamesIt as unknown:
        prints(str(unknown))
        return 1
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
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    configuration, store, lists_objects = opened
    store.saves(Reviewer(actor=REVIEWER, receives_notifications=True))
    try:
        recording = discovers(store, object_key, lists_objects)
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
    except NothingNamesIt as unknown:
        prints(str(unknown))
        return 1
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
        prints(f"usage: {usage}")
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
        prints(f"usage: {RENDER_USAGE}")
        return None
    return (asked.recording, asked.punch_in, asked.punch_out, asked.label, asked.published_on)


SERVER_THREADS = 4


def starts(app, host, port):
    """Serve the app on waitress, in development as well as in production.

    One process with a thread pool, which is the model the app is written for:
    the playhead a reviewer scrubs to lives in a dict inside creates_app, and
    'set the boundary from the playhead' reads it back on a later request. Under
    a multi-process server that read lands in a different worker's empty dict and
    silently sets the boundary to zero. Threads keep it one dict.

    Running the same server in both places is the point -- a production-only
    server is a production-only class of bug.
    """
    serve(app, host=host, port=port, threads=SERVER_THREADS, ident="sermon")


IDLE_POLL_SECONDS = 5.0


def parses_work_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-work", add_help=False)
    parser.add_argument("--corpus")
    parser.add_argument("--prompts")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--poll", type=float, default=IDLE_POLL_SECONDS)
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(
            "usage: sermon-work [--corpus DIR] [--prompts DIR] "
            "[--once] [--limit N] [--poll SECONDS]"
        )
        return None


def analyses_for(store, asked, prints):
    """The corpus shortcut, or None to walk the stages.

    None is the production path and the one that transcribes: AnalyzesRecording
    reads `if self.analyses is not None: self.analyses(...)` and otherwise walks
    STAGE_ORDER, and TranscribesRecording is only reached inside that walk. A
    corpus is the spike's shortcut -- it reads a transcript somebody already
    made -- so naming one is an override, never the default.
    """
    if not asked.corpus:
        return None
    corpus = Path(asked.corpus).resolve()
    prompts = Path(asked.prompts).resolve() if asked.prompts else corpus.parent / "prompts"
    return ProposesFromStoredTranscript(
        store=store, corpus_root=corpus, prompts_root=prompts
    )


def drains(runs, asked, prints, sleeps):
    """Run queued work until asked to stop.

    --once runs a single job. The queue holds 93 downloads against a read-only
    39 GiB bucket, so draining it is never what one keystroke does.
    """
    done = 0
    while True:
        job = runs()
        if job is not None:
            done += 1
            prints(f"ran {job.kind} job {job.job_id} for {job.recording_id}")
            if asked.once or (asked.limit and done >= asked.limit):
                return 0
            continue
        if asked.once or asked.limit:
            prints("nothing queued")
            return 0
        sleeps(asked.poll)


def works(settings=None, arguments=None, prints=print, sleeps=time.sleep):
    asked = parses_work_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    opened = opens_or_reports(settings, None, prints)
    if opened is None:
        return 1
    configuration, store, _ = opened
    try:
        recovered = RecoversInterruptedJobs(store=store)()
        for job in recovered:
            prints(f"requeued {job.kind} job {job.job_id}, interrupted mid-run")
        analyses = analyses_for(store, asked, prints)
        BindsModelEndpoint(configuration=configuration)()
        if analyses is None:
            # The stage walk has no corpus to bind roots from, but the
            # classifier still reads prompt templates off disk, and the pipeline
            # holds that a root with no diarization directory is a
            # misconfiguration rather than an absent result -- a distinction
            # tests/test_pipeline_library.py pins. Production has no corpus, so
            # it lays the directory out and leaves it empty: no file for a
            # recording then means no diarization for it, which is supported.
            layout.diarization_root(configuration.data_root).mkdir(parents=True, exist_ok=True)
            BindsCorpusRoots(
                corpus_root=layout.corpus_root(configuration.data_root),
                prompts_root=Path(
                    asked.prompts or os.environ.get("SERMON_PROMPTS_ROOT", "prompts")
                ),
            )()
        runs = RunsQueuedJobs(
            store=store,
            downloads=RunsDownloadJob(
                store=store,
                fetches=FetchesBucketObject(
                    bucket=configuration.object_store.bucket,
                    client=OpensObjectStore(object_store=configuration.object_store)(),
                ),
                probes=MeasuresRecordingAudio(),
            ),
            analyzes=RunsAnalyzeJob(
                store=store,
                stages=lambda _name: None,
                notifies=SendsNotification(store=store),
                analyses=analyses,
                transcribes=transcribes_with(store=store),
            ),
            renders=RunsRenderJob(
                store=store,
                steps=lambda _name: None,
                notifies=SendsNotification(store=store),
                renders=RendersMp3(),
            ),
        )
        return drains(runs, asked, prints, sleeps)
    finally:
        store.close()


def serves(settings=None, lists_objects=None, runs=starts, prints=print):
    settings = resolves_settings() if settings is None else settings
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    _, store, lists_objects = opened
    app = creates_app(store=store, lists_objects=lists_objects)
    app.config["BIND_HOST"] = settings.get(BIND_HOST, app.config["BIND_HOST"])
    runs(app, app.config["BIND_HOST"], int(settings.get(PORT, DEFAULT_PORT)))
    return 0


def parses_analyze_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-analyze", usage=ANALYZE_USAGE, add_help=True)
    parser.add_argument("recording")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--prompts")
    parser.add_argument("--model", default=CLASSIFIER)
    parser.add_argument("--summaries", default=SUMMARIZER)
    parser.add_argument("--asr", default=ASR_CONFIG)
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {ANALYZE_USAGE}")
        return None


def queues_analysis(store, recording):
    return EnqueuesJob(store=store)(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=JOB_ATTEMPTS,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=datetime.now(UTC),
        )
    )


def reports_analysis(store, recording, prints):
    settled = store.loads(Recording, recording.recording_id)
    job = store.lists(Job, recording_id=settled.recording_id, kind="analyze")[-1]
    prints(f"{settled.recording_id} is {settled.state}, the analyze job {job.state}")
    prints(f"  {len(store.lists(Block, recording_id=settled.recording_id))} blocks")
    if job.last_error:
        prints(f"  {job.last_error}")
    return reports_boundaries(store, settled, prints)


def analyzes(settings=None, arguments=None, reasons=None, prints=print):
    asked = parses_analyze_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    corpus = Path(asked.corpus).resolve()
    prompts = Path(asked.prompts).resolve() if asked.prompts else corpus.parent / "prompts"
    try:
        configuration = ReadsConfiguration(
            resolves_settings() if settings is None else settings
        )()
    except MissingConfiguration as unset:
        prints(str(unset))
        return 1
    BindsModelEndpoint(configuration=configuration)()
    store = opens_store(configuration.data_root)
    try:
        try:
            recording = registers_from_transcript(store, asked.recording, corpus, asked.asr)
        except TranscriptNotStored as missing:
            prints(f"{asked.recording}: {missing}")
            return 1
        prints(f"reasoning over {configuration.model_endpoint} with {asked.model}")
        queues_analysis(store, recording)
        RunsAnalyzeJob(
            store=store,
            stages=lambda _name: None,
            notifies=SendsNotification(store=store),
            contents=NOTHING_FABRICATED,
            recording_id=recording.recording_id,
            analyses=ProposesFromStoredTranscript(
                store=store,
                corpus_root=corpus,
                prompts_root=prompts,
                model=asked.model,
                summarizer=None if asked.summaries == NO_SUMMARIES else asked.summaries,
                asr_config=asked.asr,
                reasons=reasons,
            ),
        )()
        return 0 if reports_analysis(store, recording, prints) else 1
    finally:
        store.close()


def parses_propose_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-propose", usage=PROPOSE_USAGE, add_help=True)
    parser.add_argument("recordings", nargs="+")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--prompts")
    parser.add_argument("--model", default=CLASSIFIER)
    parser.add_argument("--summaries", default=SUMMARIZER)
    parser.add_argument("--asr", default=ASR_CONFIG)
    parser.add_argument("--store")
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {PROPOSE_USAGE}")
        return None


def registers_from_transcript(store, named, corpus, asr_config):
    doc = ReadsStoredTranscript(corpus, asr_config)(named)
    known = names_the_recording(store, named)
    if known is not None:
        return store.saves(replace(known, duration_seconds=doc["duration"]))
    return store.saves(
        Recording(
            recording_id=doc["recording_id"],
            object_key=f"{doc['recording_id']}.flac",
            state="downloaded",
            started_at=datetime.fromisoformat(doc["started_at"]).replace(tzinfo=UTC),
            started_at_source="key",
            size_bytes=0,
            duration_seconds=doc["duration"],
        )
    )


def reports_boundaries(store, recording, prints):
    proposed = store.lists(Segment, recording_id=recording.recording_id)
    for segment in proposed:
        graded = store.lists(Proposal, segment_id=segment.segment_id)
        prints(
            f"  {segment.classification:<8} {hms(segment.punch_in_seconds)} -> "
            f"{hms(segment.punch_out_seconds)}  "
            f"({segment.punch_out_seconds - segment.punch_in_seconds:.0f} s, "
            f"{segment.boundary_source})"
        )
        for held in graded:
            prints(
                f"           classification {held.classification_confidence}, "
                f"boundary {held.boundary_confidence}, "
                f"cuts {held.punch_in_grade}/{held.punch_out_grade}"
                + (f", missing {', '.join(held.missing_evidence)}" if held.missing_evidence else "")
            )
    return proposed


def reports_error(measured, prints):
    if not measured.found:
        prints(
            f"  NOT FOUND  human {measured.true_punch_in:.3f} -> "
            f"{measured.true_punch_out:.3f} ({measured.label})"
        )
        return False
    prints(
        f"  punch-in   proposed {measured.punch_in:9.3f}  human {measured.true_punch_in:9.3f}  "
        f"error {measured.punch_in_error:+8.3f} s  [{measured.punch_in_difficulty}]"
    )
    prints(
        f"  punch-out  proposed {measured.punch_out:9.3f}  human {measured.true_punch_out:9.3f}  "
        f"error {measured.punch_out_error:+8.3f} s  [{measured.punch_out_difficulty}]"
    )
    return True


def proposes(settings=None, prints=print):
    asked = parses_propose_command(sys.argv[1:], prints)
    if asked is None:
        return 1
    corpus = Path(asked.corpus).resolve()
    prompts = Path(asked.prompts).resolve() if asked.prompts else corpus.parent / "prompts"
    try:
        configuration = ReadsConfiguration(
            resolves_settings() if settings is None else settings
        )()
    except MissingConfiguration as unset:
        prints(str(unset))
        return 1
    BindsModelEndpoint(configuration=configuration)()
    store = opens_store(Path(asked.store).resolve() if asked.store else configuration.data_root)
    measures = MeasuresBoundaryError(ground_truth=corpus / "groundtruth.json")
    found = 0
    wanted = 0
    try:
        prints(f"reasoning over {configuration.model_endpoint} with {asked.model}")
        for named in asked.recordings:
            try:
                recording = registers_from_transcript(store, named, corpus, asked.asr)
            except TranscriptNotStored as missing:
                prints(f"{named}: {missing}")
                return 1
            started = time.time()
            try:
                ProposesFromStoredTranscript(
                    store=store,
                    corpus_root=corpus,
                    prompts_root=prompts,
                    model=asked.model,
                    summarizer=None if asked.summaries == NO_SUMMARIES else asked.summaries,
                    asr_config=asked.asr,
                )(recording)
            except (ModelEndpointUnreachable, RootNotConfigured) as refused:
                prints(f"{named}: {refused}")
                return 1
            prints(f"{recording.recording_id}  {time.time() - started:.1f} s")
            proposed = reports_boundaries(store, recording, prints)
            for measured in measures(
                recording.recording_id,
                [(item.punch_in_seconds, item.punch_out_seconds) for item in proposed],
            ):
                wanted += 1
                found += reports_error(measured, prints)
        return 0 if found == wanted else 1
    finally:
        store.close()


ORGANIZE_USAGE = "sermon-organize [--dry-run]"


def parses_organize_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-organize", usage=ORGANIZE_USAGE, add_help=False)
    parser.add_argument("--dry-run", action="store_true")
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {ORGANIZE_USAGE}")
        return None


def reports_relocations(relocations, prints):
    counted = {}
    for relocation in relocations:
        counted[relocation.outcome] = counted.get(relocation.outcome, 0) + 1
        if relocation.outcome != IN_PLACE:
            prints(str(relocation))
    for outcome in sorted(counted):
        prints(f"{counted[outcome]} {outcome}")
    return 1 if any(outcome.startswith("refused") for outcome in counted) else 0


def organizes(settings=None, arguments=None, prints=print):
    """Move a data root onto the layout, rows and files together.

    Nothing else migrates a database here, so this is the one command that
    rewrites stored rows. It is idempotent: a second run reports only `in place`.
    """
    asked = parses_organize_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    settings = resolves_settings() if settings is None else settings
    root = settings.get(DATA_ROOT)
    if not root:
        prints(f"nothing sets {DATA_ROOT}")
        return 1
    data_root = Path(root)
    if not data_root.is_absolute():
        prints(f"{DATA_ROOT} is {root!r}, which moves with the working directory")
        return 1
    try:
        store = opens_store(data_root)
    except StoredSchemaDiffers as stale:
        prints(str(stale))
        return 1
    try:
        prints(f"{'reading' if asked.dry_run else 'organizing'} {data_root}")
        return reports_relocations(
            OrganizesDataRoot(store=store, data_root=data_root, dry_run=asked.dry_run)(),
            prints,
        )
    finally:
        store.close()
