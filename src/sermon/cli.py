from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from sermon.analysis import (
    DerivesGroundTruth,
    MeasuresBoundaryError,
    ProposesFromStoredTranscript,
    ReadsStoredTranscript,
)
from sermon.analysis.aligns_edit import (
    UNALIGNABLE,
    AlignsPublishedEdit,
    DerivesPairsForEdit,
    reads_duration,
)
from sermon.analysis.recognises_machine_cut import MACHINE, RecognisesMachineCut
from sermon.analysis.reports_approval_rate import ReportsApprovalRate
from sermon.analysis.derives_corpus_entry import (
    DEFAULT_TAG,
    BlockFileAlreadyWritten,
    DerivesCorpusEntry,
    NothingToBlock,
)
from sermon.analysis.proposes_from_transcript import BindsCorpusRoots, ReasonsOverTranscript
from sermon.analysis.proposes_from_transcript import ASR_CONFIG, CLASSIFIER, SUMMARIZER, TranscriptNotStored
from sermon.analysis.grades_cut_accuracy import GradesCorpusAccuracy
from sermon.analysis.measures_boundary_error import (
    ReadsLabelledFromFile,
    ReadsLabelledFromStore,
)
from sermon.analysis.regrades_stored_cuts import DerivesStoredProposals, RegradesStoredCuts
from sermon.analysis import gates_shipping_cuts as gate
from sermon.analysis import judges_cut
from sermon.analysis.diarizes_audio import diarizes_with
from sermon.analysis.transcribes_audio import transcribes_with
from sermon.approves_segment import ApprovesSegment
from sermon.binds_model_endpoint import BindsModelEndpoint
from sermon.config import DATA_ROOT, ModelEndpointUnreachable, MissingConfiguration, ReadsConfiguration
from sermon.extends_segment_span import ReadsTimecode, WidensProposedSpan
from sermon.jobs.analyzes_recording import NOTHING_FABRICATED, RunsAnalyzeJob
from sermon.jobs.downloads_recording import DownloadsRecording, RunsDownloadJob
from sermon.jobs.enqueues_job import EnqueuesJob
from sermon.jobs.probes_recording import MeasuresRecordingAudio, ProbesRecording
from sermon.jobs.recovers_interrupted_jobs import RecoversInterruptedJobs
from sermon.jobs.runs_queued_jobs import RunsQueuedJobs
from sermon.jobs.renders_mp3 import ChannelsNeedReview, RendersMp3
from sermon.jobs.renders_segment import RunsRenderJob
from sermon.object_store import (
    FetchesBucketObject,
    ListsBucketObjects,
    OpensObjectStore,
    StreamsBucketObject,
)
from sermon.organizes_data_root import IN_PLACE, OrganizesDataRoot
from sermon.pipeline.classify import hms
from sermon.pipeline.roots import RootNotConfigured
from sermon.reconciles_bucket import (
    DEFAULT_CUTOFF,
    ObjectStoreForbidden,
    ObjectStoreUnreachable,
    ReconcilesBucket,
)
from sermon.queues_new_recordings import QueuesNewRecordings
from sermon.records_publication_details import RecordsPublicationDetails
from sermon.scans_on_schedule import IntervalNotUnderstood, ScansOnSchedule, interval_from
from sermon.scores_cut import (
    DEGRADED,
    EQUAL,
    IMPROVED,
    LONG_RUN_SECONDS,
    SAME_CUT,
    WORD_BUFFER_SECONDS,
)
from sermon.reminds_reviewer import RemindsReviewer
from sermon.sends_notification import SendsNotification, opens_channel
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
from sermon.store.vocabularies import SEGMENT_CLASSIFICATIONS
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
ALIGN_USAGE = (
    "sermon-align <recording-id> [<recording-id> ...] <path-to-edit.mp3> "
    "[--source <path>] [--classification <name>] [--store <data-root>] [--work <dir>]"
)
ALIGN_WORK = "corpus/alignment"
PROPOSE_USAGE = (
    "sermon-propose <recording-id> [<recording-id> ...] --corpus <corpus-root> "
    "[--prompts <path>] [--model <name>] [--summaries <name-or-none>] "
    "[--asr <config>] [--store <data-root>]"
)
NO_SUMMARIES = "none"
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


def streams_from(configuration, builds_client=None):
    return StreamsBucketObject(
        bucket=configuration.object_store.bucket,
        client=OpensObjectStore(object_store=configuration.object_store, builds=builds_client)(),
    )


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
        WidensProposedSpan(store=store)(
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
            ),
            recording.duration_seconds,
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
        queued = store.lists(Job, kind="render", state="queued", segment_id=segment.segment_id)
        RunsRenderJob(
            store=store,
            steps=lambda _name: None,
            notifies=SendsNotification(store=store, sends=opens_channel(configuration.notification_channel, configuration.slack_webhook, configuration.app_url)),
            renders=keeps_what_it_rendered(RendersMp3(), produced),
            job_id=queued[0].job_id,
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
    parser.add_argument("--scan-every", type=float, default=None)
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(
            "usage: sermon-work [--corpus DIR] [--prompts DIR] "
            "[--once] [--limit N] [--poll SECONDS] [--scan-every SECONDS]"
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


def drains(runs, asked, prints, sleeps, scans=None, reminds=lambda: ()):
    """Run queued work until asked to stop.

    --once runs a single job. The queue holds 93 downloads against a read-only
    39 GiB bucket, so draining it is never what one keystroke does.
    """
    done = 0
    while True:
        if scans is not None:
            scans()
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
        reminds()
        sleeps(asked.poll)


def works(settings=None, arguments=None, prints=print, sleeps=time.sleep,
          lists_objects=None, fetches_object=None):
    asked = parses_work_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    settings = resolves_settings() if settings is None else settings
    try:
        interval = interval_from(asked.scan_every, settings)
    except IntervalNotUnderstood as refused:
        prints(str(refused))
        return 1
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    configuration, store, lists_objects = opened
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
                ) if fetches_object is None else fetches_object,
                probes=MeasuresRecordingAudio(),
            ),
            analyzes=RunsAnalyzeJob(
                store=store,
                stages=lambda _name: None,
                notifies=SendsNotification(store=store, sends=opens_channel(configuration.notification_channel, configuration.slack_webhook, configuration.app_url)),
                analyses=analyses,
                transcribes=transcribes_with(store=store),
                diarizes=diarizes_with(store=store),
            ),
            renders=RunsRenderJob(
                store=store,
                steps=lambda _name: None,
                notifies=SendsNotification(store=store, sends=opens_channel(configuration.notification_channel, configuration.slack_webhook, configuration.app_url)),
                renders=RendersMp3(),
            ),
        )
        scans = None
        if interval is not None and not (asked.once or asked.limit):
            scans = ScansOnSchedule(
                reconciles=ReconcilesBucket(
                    store=store,
                    lists_objects=lists_objects,
                    ingest_cutoff=cutoff_from(settings),
                ),
                queues=QueuesNewRecordings(store=store),
                interval=interval,
                prints=prints,
            )
        reminds = RemindsReviewer(
            store=store,
            notifies=SendsNotification(store=store, sends=opens_channel(configuration.notification_channel, configuration.slack_webhook, configuration.app_url)),
        )
        return drains(runs, asked, prints, sleeps, scans=scans, reminds=reminds)
    finally:
        store.close()


def serves(settings=None, lists_objects=None, runs=starts, prints=print, builds_client=None):
    settings = resolves_settings() if settings is None else settings
    opened = opens_or_reports(settings, lists_objects, prints)
    if opened is None:
        return 1
    configuration, store, lists_objects = opened
    app = creates_app(
        store=store,
        lists_objects=lists_objects,
        streams_object=streams_from(configuration, builds_client),
        webhook_token=configuration.webhook_token,
    )
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


def queues_analysis(store, recording, clock=lambda: datetime.now(UTC)):
    return EnqueuesJob(store=store)(
        Job(
            recording_id=recording.recording_id,
            kind="analyze",
            state="queued",
            max_attempts=JOB_ATTEMPTS,
            dedupe_key=f"analyze:{recording.recording_id}",
            queued_at=clock(),
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
            notifies=SendsNotification(store=store, sends=opens_channel(configuration.notification_channel, configuration.slack_webhook, configuration.app_url)),
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
    measures = MeasuresBoundaryError(
        reads=ReadsLabelledFromFile(ground_truth=corpus / "groundtruth.json")
    )
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


def parses_align_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-align", usage=ALIGN_USAGE, add_help=False)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--classification", default="sermon")
    parser.add_argument("--store")
    parser.add_argument("--work")
    try:
        asked = parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {ALIGN_USAGE}")
        return None
    if len(asked.names) < 2 or asked.classification not in SEGMENT_CLASSIFICATIONS:
        prints(f"usage: {ALIGN_USAGE}")
        return None
    return asked


def sources_for(store, recordings, given, prints):
    if given and len(given) != len(recordings):
        prints(f"{len(recordings)} recordings named but {len(given)} sources given")
        return None
    found = []
    for index, recording in enumerate(recordings):
        path = Path(given[index]).resolve() if given else store.resolves(recording)
        if path is None or not path.is_file():
            prints(
                f"{recording.recording_id}: the source is not on this machine; "
                f"fetch it or name it with --source"
            )
            return None
        found.append(path)
    return found


def reports_derived(pair, prints):
    prints(
        f"  {pair.recording_id}  punch-in {pair.punch_in_seconds:.4f} s  "
        f"punch-out {pair.punch_out_seconds:.4f} s  "
        f"({pair.punch_out_seconds - pair.punch_in_seconds:.3f} s of "
        f"{pair.source_duration_seconds:.3f} s)"
    )
    prints(
        f"  coarse NCC {pair.alignment.coarse_ncc}, peak ratio "
        f"{pair.alignment.coarse_peak_ratio}, probe NCC floor "
        f"{pair.alignment.probe_ncc_min}, fit residual "
        f"{pair.alignment.fit_residual_seconds} s, drift "
        f"{pair.alignment.drift_ppm:+.1f} ppm"
    )
    prints(
        f"  difficulty {pair.punch_in_difficulty.label}/{pair.punch_out_difficulty.label} "
        f"({pair.punch_in_difficulty.quiet_milliseconds} ms, "
        f"{pair.punch_out_difficulty.quiet_milliseconds} ms)"
    )


def reports_refusal(pair, prints):
    prints(f"  {pair.recording_id}: {pair.alignment.verdict}")
    for refusal in pair.refusals:
        prints(f"    {refusal}")


def stores_derived(store, pair, classification):
    return DerivesGroundTruth(store=store)(
        pair.recording_id,
        punch_in=pair.punch_in_seconds,
        punch_out=pair.punch_out_seconds,
        classification=classification,
        drift_ppm=pair.alignment.drift_ppm,
        punch_in_difficulty=pair.punch_in_difficulty.label,
        punch_out_difficulty=pair.punch_out_difficulty.label,
    )


def records_refusal(store, pair, classification):
    return DerivesGroundTruth(store=store)(
        pair.recording_id,
        punch_in=None,
        punch_out=None,
        classification=classification,
        alignment=pair.alignment.verdict if not pair.trustworthy else UNALIGNABLE,
    )


def records_machine_cut(store, recording_id, classification, prints):
    DerivesGroundTruth(store=store)(
        recording_id,
        punch_in=None,
        punch_out=None,
        classification=classification,
        provenance=MACHINE,
    )
    prints(
        f"  {recording_id}: recorded as published with machine provenance; "
        f"not aligned and not ground truth"
    )


def aligns(settings=None, arguments=None, reads=None, measures=None, prints=print):
    asked = parses_align_command(
        sys.argv[1:] if arguments is None else arguments, prints
    )
    if asked is None:
        return 1
    edit = Path(asked.names[-1]).resolve()
    if not edit.is_file():
        prints(f"{edit}: no such edit")
        return 1
    try:
        configuration = ReadsConfiguration(
            resolves_settings() if settings is None else settings
        )()
    except MissingConfiguration as unset:
        prints(str(unset))
        return 1
    store = opens_store(Path(asked.store).resolve() if asked.store else configuration.data_root)
    try:
        return aligned_against(store, asked, edit, reads, measures, prints)
    finally:
        store.close()


def aligned_against(store, asked, edit, reads, measures, prints):
    recordings = []
    for named in asked.names[:-1]:
        known = names_the_recording(store, named)
        if known is None:
            prints(f"{named}: nothing in the store names it")
            return 1
        recordings.append(known)
    if RecognisesMachineCut(store=store)(recordings[0].recording_id, edit):
        records_machine_cut(store, recordings[0].recording_id, asked.classification, prints)
        return 0
    sources = sources_for(store, recordings, asked.source, prints)
    if sources is None:
        return 1
    work = Path(asked.work).resolve() if asked.work else store.resolves_path(ALIGN_WORK)
    aligner = AlignsPublishedEdit(
        work=work,
        reads=reads,
        measures=reads_duration if measures is None else measures,
    )
    prints(f"{edit.name}")
    named = [
        (recording.recording_id, source) for recording, source in zip(recordings, sources)
    ]
    derived = DerivesPairsForEdit(
        aligns=aligner, measures=reads_duration if measures is None else measures
    )(named, edit)
    if any(not pair.trustworthy for pair in derived):
        for pair in derived:
            if pair.trustworthy:
                reports_derived(pair, prints)
            else:
                reports_refusal(pair, prints)
            excluded = records_refusal(store, pair, asked.classification)
            prints(f"  {pair.recording_id}: recorded as {excluded.alignment}; no boundaries derived")
        return 1
    for pair in derived:
        stores_derived(store, pair, asked.classification)
        reports_derived(pair, prints)
    return 0


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


REGRADE_USAGE = (
    "sermon-regrade [--corpus <corpus-root>] [--baseline <path>] [--tag <config>] "
    "[--split dev|test|all] [--unseal <reason>] [--access-log <path>] [--all] "
    "[--accept <reason>] | sermon-regrade --corpus-regime [--store <data-root>] "
    "[--before <path>] [--save <path>] [--tag <text>] [--drift]"
)
SHIPPING_BASELINE = "tests/shipping_baseline.json"
HELD_OUT_READS = "tests/held_out_reads.log"
SPLITS = {
    "dev": ("dev",),
    "test": ("test", "multi-output", "two-level", "blind"),
    "all": ("dev", "test", "multi-output", "two-level", "blind"),
}
CORPUS_REGIME_FLAGS = ("store", "before", "save", "drift")


def parses_regrade_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-regrade", usage=REGRADE_USAGE, add_help=True)
    parser.add_argument("--corpus", default=os.environ.get("SERMON_SPIKE_DATA"))
    parser.add_argument("--baseline", default=SHIPPING_BASELINE)
    parser.add_argument("--split", choices=sorted(SPLITS), default="dev")
    parser.add_argument("--unseal")
    parser.add_argument("--access-log", default=HELD_OUT_READS)
    parser.add_argument("--accept")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--corpus-regime", action="store_true")
    parser.add_argument("--store")
    parser.add_argument("--before")
    parser.add_argument("--save")
    parser.add_argument("--tag")
    parser.add_argument("--drift", action="store_true")
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {REGRADE_USAGE}")
        return None


def reads_stored_proposals(path):
    return {
        name: [(held["punch_in"], held["punch_out"]) for held in entry.get("chosen") or ()]
        for name, entry in json.loads(Path(path).read_text()).items()
    }


def writes_stored_proposals(path, graded):
    Path(path).write_text(
        json.dumps(
            {
                name: {"chosen": [{"punch_in": punch_in, "punch_out": punch_out}
                                  for punch_in, punch_out in proposed]}
                for name, proposed in graded.items()
            },
            indent=1,
            sort_keys=True,
        )
    )


def reports_placing(run, in_speech):
    if run is None:
        return "in a word" if in_speech else "no run"
    noted = f"run {run.index} ({run.seconds:.1f}s"
    if run.seconds > LONG_RUN_SECONDS:
        noted += ",long"
    if run.overlaps_audio_silence:
        noted += ",audio"
    return f"{noted})"


def reports_distance(score):
    named = "same run" if score.same_run else "a run away"
    crowded = " within the buffer" if score.within_buffer else ""
    return f"{named:<10} speech {score.speech_seconds:7.3f} s{crowded}"


def reports_accuracy_cut(cut, prints):
    named = cut.boundary.replace("_", "-")
    if not cut.found:
        prints(f"  {named:<9} human {cut.human:10.3f}  NOT FOUND  [{cut.difficulty}]")
        return
    score = cut.score
    human_at = reports_placing(score.truth_run, score.truth_in_speech)
    prints(
        f"  {named:<9} human {cut.human:10.3f} {human_at:<22} "
        f"proposed {score.proposed:10.3f} "
        f"{reports_placing(score.proposed_run, score.in_speech):<22} "
        f"{reports_distance(score)}  [{cut.difficulty}]"
    )


def reports_accuracy(graded, prints):
    cuts = [cut for proposal in graded for cut in proposal.cuts]
    for proposal in graded:
        prints(f"{proposal.recording_id}  {proposal.tag}")
        for cut in proposal.cuts:
            reports_accuracy_cut(cut, prints)
    found = [cut for cut in cuts if cut.found]
    prints(
        f"{len(graded)} proposal{'' if len(graded) == 1 else 's'} graded, {len(cuts)} cut points: "
        f"{sum(cut.score.same_run for cut in found)} in the human's run, "
        f"{sum(cut.score.in_speech for cut in found)} mid-word, "
        f"{len(cuts) - len(found)} not found, "
        f"{sum(cut.score.within_buffer for cut in found)} within "
        f"{WORD_BUFFER_SECONDS * 1000:.0f} ms of a word"
    )
    if not found:
        prints("nothing could be scored against a human cut")
        return 1
    apart = sorted(cut.score.speech_seconds for cut in found)
    prints(
        f"speech from the human cut: median {apart[len(apart) // 2]:.3f} s, "
        f"worst {apart[-1]:.3f} s, "
        f"{sum(cut.score.long_run for cut in found)} in a run over {LONG_RUN_SECONDS:.0f} s"
    )
    return 0


def reports_changed_cut(proposal, before, after, verdict, prints):
    named = after.boundary.replace("_", "-")
    prints(
        f"{proposal.recording_id}  {proposal.tag}  {named}  "
        f"human {after.human:10.3f}  {verdict}"
    )
    for side, cut in (("before", before), ("after", after)):
        if not cut.found:
            prints(f"    {side:<8} {'NOT FOUND':>10}")
            continue
        prints(
            f"    {side:<8} {cut.score.proposed:10.3f} "
            f"{reports_placing(cut.score.proposed_run, cut.score.in_speech):<22} "
            f"{reports_distance(cut.score)}"
        )


def reports_change(graded, prints):
    counted = {IMPROVED: 0, DEGRADED: 0, SAME_CUT: 0}
    cuts = 0
    for proposal in graded:
        for before, after, verdict in proposal.changes:
            cuts += 1
            if verdict == EQUAL:
                continue
            counted[verdict] += 1
            reports_changed_cut(proposal, before, after, verdict, prints)
    moved = sum(counted.values())
    prints(
        f"{len(graded)} proposal{'' if len(graded) == 1 else 's'} graded, {cuts} cut points, "
        f"{moved} moved: {counted[IMPROVED]} {IMPROVED}, {counted[DEGRADED]} {DEGRADED}, "
        f"{counted[SAME_CUT]} {SAME_CUT}"
    )
    if not cuts:
        prints("nothing could be compared against a human cut, so nothing was gated")
        return 1
    return 1 if counted[DEGRADED] else 0


def reports_drift(regraded, prints):
    for proposal in regraded:
        reports_regraded_proposal(proposal, prints)
    cuts = [cut for proposal in regraded for cut in proposal.cuts]
    moved = [cut for cut in cuts if cut.score.delta_seconds != 0.0]
    counted = {}
    for cut in moved:
        counted[cut.score.verdict] = counted.get(cut.score.verdict, 0) + 1
    prints(
        f"drift only, not accuracy: {len(regraded)} stored proposals, {len(cuts)} cut points, "
        f"{len(moved)} differ from what the corpus recorded"
        + ("" if not counted else ": " + ", ".join(f"{counted[v]} {v}" for v in sorted(counted)))
    )
    return 0


def reports_regraded_cut(cut, prints):
    score = cut.score
    prints(
        f"  {cut.boundary.replace('_', '-'):<9} "
        f"{score.truth:10.3f} {reports_placing(score.truth_run, score.truth_in_speech):<22} -> "
        f"{score.proposed:10.3f} {reports_placing(score.proposed_run, score.in_speech):<22} "
        f"delta {score.delta_seconds:+8.3f} s  speech {score.speech_seconds:7.3f} s  "
        f"{score.verdict}"
    )


def reports_regraded_proposal(proposal, prints):
    moved = [cut for cut in proposal.cuts if cut.score.delta_seconds != 0.0]
    counts_differ = proposal.regraded and proposal.stored_count != proposal.live_count
    if not proposal.regraded:
        prints(f"{proposal.recording_id}  {proposal.tag}  no transcript, not regraded")
        return
    if not moved and not counts_differ:
        return
    prints(f"{proposal.recording_id}  {proposal.tag}")
    if counts_differ:
        prints(f"  segments   stored {proposal.stored_count}, live {proposal.live_count}")
    for cut in moved:
        reports_regraded_cut(cut, prints)


def reports_approval_record(rate, prints):
    if rate.unplaced:
        prints(
            f"from the approval record, not this run: {rate.unplaced} published Segment"
            + (
                " carries no publication date and is not counted"
                if rate.unplaced == 1
                else "s carry no publication date and are not counted"
            )
        )
    if rate.proportion is None:
        prints(
            "from the approval record, not this run: nothing "
            + ("else " if rate.unplaced else "")
            + "has been published, so there is no proportion approved with no boundary edit"
        )
        return
    prints(
        f"from the approval record, not this run: {len(rate.approved_with_no_edit)} of "
        f"{rate.published} published Segment{'' if rate.published == 1 else 's'} "
        f"approved with no boundary edit ({rate.proportion:.0%})"
    )


def clock_of(seconds):
    tenths = round(seconds * 10)
    return f"{tenths // 36000}:{tenths // 600 % 60:02d}:{tenths // 10 % 60:02d}.{tenths % 10}"


def reports_distance_from_human(judged):
    if judged.missed:
        return "no proposal covers this cut"
    apart = judged.seconds_from_human
    when = "on the human's cut" if apart == 0 else (
        f"{abs(apart):.2f} s {'early' if apart < 0 else 'late'}"
    )
    where = (
        "in the human's pause"
        if judged.same_pause
        else f"{judged.speech_seconds:.2f} s of speech away"
    )
    if judged.inside_word:
        noted = ", inside a word"
    elif judged.clearance_seconds is not None and judged.clearance_seconds < 1.0:
        noted = f", {judged.clearance_seconds * 1000:.0f} ms clear of a word"
    else:
        noted = ""
    return f"{clock_of(judged.proposed)}  {when}, {where}{noted}"


def reports_judged_recording(judged, prints):
    prints(f"{judged.label}  ({judged.recording_id}, {judged.split})  {judged.verdict.upper()}")
    for cut in judged.cuts:
        named = "punch-in" if cut.boundary == "punch_in" else "punch-out"
        prints(f"  {named:<9} human {clock_of(cut.human)}  {cut.verdict}")
        prints(f"    before {reports_distance_from_human(cut.before)}")
        prints(f"    after  {reports_distance_from_human(cut.after)}")
    if judged.unpaired_before or judged.unpaired_after:
        prints(
            f"  proposals no human cut pairs with: before {judged.unpaired_before}, "
            f"after {judged.unpaired_after}"
        )


def moved_by(judged):
    finite = [
        cut.after.speech_seconds - cut.before.speech_seconds
        for cut in judged.cuts
        if not cut.before.missed and not cut.after.missed
    ]
    return sum(finite)


def reports_where_cuts_stand(report, side, prints):
    cuts = [getattr(cut, side) for one in report.recordings for cut in one.cuts]
    found = [cut for cut in cuts if not cut.missed]
    if not found:
        prints(f"{side}: no cut found")
        return
    apart = sorted(cut.speech_seconds for cut in found)
    clear = [cut.clearance_seconds for cut in found if not cut.inside_word]
    prints(
        f"{side + ':':<7} {sum(cut.same_pause for cut in found)} of {len(cuts)} cuts in the "
        f"human's pause, median {apart[len(apart) // 2]:.2f} / worst {apart[-1]:.2f} speech-s "
        f"away, {len(cuts) - len(found)} missed; diagnostics: "
        f"{sum(cut.inside_word for cut in found)} inside a word, "
        f"{sum(seconds < 0.05 for seconds in clear)} within 50 ms of one, "
        f"{sum(seconds < 0.25 for seconds in clear)} within 250 ms"
    )


def reports_gate(report, asked, prints):
    counted = report.counts
    shown = [
        one for one in report.recordings
        if asked.all or one.verdict != judges_cut.UNCHANGED
    ]
    for judged in shown:
        reports_judged_recording(judged, prints)
    for recording_id in report.not_in_baseline:
        prints(f"{recording_id}  not in the baseline, not compared")
    prints(
        f"{len(report.recordings)} recordings judged: {counted[judges_cut.BETTER]} better, "
        f"{counted[judges_cut.WORSE]} worse, {counted[gate.MIXED]} mixed, "
        f"{counted[judges_cut.UNCHANGED]} unchanged"
    )
    quietly = sum(
        cut.before.proposed != cut.after.proposed and cut.verdict == judges_cut.UNCHANGED
        for judged in report.recordings
        for cut in judged.cuts
    )
    if quietly:
        prints(
            f"{quietly} cut{'' if quietly == 1 else 's'} moved without changing "
            f"{'its' if quietly == 1 else 'their'} judgement (--all shows where)"
        )
    for judged in report.recordings:
        if judged.verdict == judges_cut.UNCHANGED:
            continue
        moved = moved_by(judged)
        direction = "better" if moved < 0 else "worse"
        prints(
            f"  {judged.recording_id}  {judged.verdict}"
            + (f", {direction} by {abs(moved):.2f} speech-s" if moved else "")
        )
    if report.recordings:
        reports_where_cuts_stand(report, "before", prints)
        reports_where_cuts_stand(report, "after", prints)
    if any(
        cut.before.proposed != cut.after.proposed
        for judged in report.recordings
        for cut in judged.cuts
    ):
        prints(
            "these proposals differ from the reference; once the change is wanted, "
            "sermon-regrade --accept \"<why>\" makes it the reference for the next one"
        )
    if report.judge_changed:
        prints(
            f"the judge changed since the baseline was accepted ({report.baseline_judge} -> "
            f"{judges_cut.JUDGE_DIGEST}); review it, then --accept it on an unchanged pipeline"
        )
    if not report.recordings:
        prints("nothing could be compared against a human cut, so nothing was gated")
    return {gate.PASSED: 0, gate.WORSENED: 1, gate.CANNOT_GATE: 2}[report.outcome]


def gates_shipping_cuts(asked, prints, replays=None):
    corpus = Path(asked.corpus).resolve()
    baseline_path = Path(asked.baseline)
    tag = asked.tag or gate.PRODUCTION_TAG
    if not gate.block_files(corpus):
        prints(f"no stored model answers under {corpus / 'blocks'}")
        return 2
    if asked.accept is not None:
        try:
            accepted = gate.AcceptsBaseline(
                corpus_root=corpus, path=baseline_path, replays=replays
            )(asked.accept)
        except ValueError as refused:
            prints(str(refused))
            return 1
        if accepted.refused:
            prints(f"not accepted: {accepted.refused}")
            return 1
        prints(
            f"accepted the shipping replay into {baseline_path}: {len(accepted.moved)} "
            f"proposal sets moved; reason recorded: {asked.accept.strip()}"
        )
        for name in accepted.moved:
            prints(f"  moved {name}")
        return 0
    baseline = gate.reads_baseline(baseline_path)
    if baseline is None:
        prints(
            f"no baseline at {baseline_path}: record one with --accept <reason> on the code "
            "you want to compare against"
        )
        return 2
    if not (corpus / "groundtruth.json").is_file():
        prints(f"no answer key at {corpus / 'groundtruth.json'}")
        return 2
    splits = SPLITS[asked.split]
    prints(f"production's analyze walk replayed over {tag}, {asked.split} split ({', '.join(splits)})")
    prints(
        f"judge v{judges_cut.JUDGE_VERSION} {judges_cut.JUDGE_DIGEST}: the human's pause first, "
        f"then speech-seconds; tolerance {judges_cut.TOLERANCE_SPEECH_SECONDS} speech-s"
    )
    prints(
        "a cut in the human's pause is the human's cut; any other is as far from it as the "
        "speech between them"
    )
    if baseline.accepted:
        last = baseline.accepted[-1]
        prints(
            f"against {baseline_path}, accepted {last['at']} at {last['commit']}: {last['reason']}"
        )
    if asked.split != "dev" and asked.unseal:
        prints(
            f"WARNING: the {asked.split} split is held out; reading it spends it, and the read "
            f"is recorded in {asked.access_log}"
        )
    try:
        report = gate.GatesShippingCuts(
            corpus_root=corpus,
            baseline=baseline,
            replays=replays,
            tag=tag,
            splits=splits,
            unsealed=asked.unseal,
            records=gate.RecordsHeldOutRead(path=Path(asked.access_log)),
        )()
    except gate.HeldOutSealed as sealed:
        prints(f"refused: {sealed}; pass --unseal <reason> to read it")
        return 2
    return reports_gate(report, asked, prints)


def regrades(arguments=None, prints=print, derives=None, replays=None):
    """Gate a change on production's proposals against the human cut, or replay the corpus regime.

    Reads the corpus and writes nothing to it. No audio leaves the machine and
    neither a transcriber nor a classifier is invoked.
    """
    asked = parses_regrade_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    if asked.corpus is None:
        prints("name the corpus: --corpus <corpus-root>, or set SERMON_SPIKE_DATA")
        return 2
    if not asked.corpus_regime and not any(
        getattr(asked, flag) for flag in CORPUS_REGIME_FLAGS
    ):
        return gates_shipping_cuts(asked, prints, replays)
    prints(
        "corpus regime: stored block files through derive() and choose(model_segments) -- "
        "not the walk production runs"
    )
    corpus = Path(asked.corpus).resolve()
    blocks = sorted((corpus / "blocks").glob("*.json"))
    if not blocks:
        prints(f"no stored proposals under {corpus / 'blocks'}")
        return 1
    data_root = Path(asked.store).resolve() if asked.store else None
    labelled = data_root or corpus / "groundtruth.json"
    if data_root is None and not asked.drift and not labelled.is_file():
        prints(
            f"no answer key at {labelled}: pass --store <data-root> to grade against "
            "the stored corpus"
        )
        return 1
    store = opens_store(data_root) if data_root else None
    reads = ReadsLabelledFromStore(store=store) if store else None
    try:
        if asked.drift:
            prints(f"reading drift against {len(blocks)} stored proposals under {corpus}")
            return reports_drift(
                RegradesStoredCuts(corpus_root=corpus, derives=derives, tag=asked.tag)(), prints
            )
        before = reads_stored_proposals(asked.before) if asked.before else None
        refused = {}
        graded = GradesCorpusAccuracy(
            corpus_root=corpus,
            reads=reads,
            derives=derives,
            before=before,
            tag=asked.tag,
            refuses=lambda unknown: refused.setdefault(unknown.recording_id, str(unknown)),
        )()
        for reason in refused.values():
            prints(reason)
        if asked.save:
            writes_stored_proposals(
                asked.save,
                {
                    found.name: found.live
                    for found in DerivesStoredProposals(
                        corpus_root=corpus, derives=derives, tag=asked.tag
                    )()
                    if found.regraded
                },
            )
            prints(f"saved {len(blocks)} live proposals to {asked.save}")
        prints(
            f"grading {len(graded)} labelled proposal{'' if len(graded) == 1 else 's'} "
            f"against {labelled}"
        )
        if before is not None:
            return reports_change(graded, prints)
        reported = reports_accuracy(graded, prints)
        if store is not None:
            reports_approval_record(ReportsApprovalRate(store=store)(), prints)
        return reported
    except RootNotConfigured as refused:
        prints(str(refused))
        return 1
    finally:
        if store is not None:
            store.close()


APPROVALS_USAGE = (
    "sermon-approvals [--since <YYYY-MM-DD>] [--until <YYYY-MM-DD>] [--store <data-root>]"
)
ALL_TIME = "all time"


def parses_approvals_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-approvals", usage=APPROVALS_USAGE, add_help=True)
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--store")
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {APPROVALS_USAGE}")
        return None


def names_period(since, until):
    if since is None and until is None:
        return ALL_TIME
    if since is None:
        return f"up to {until.isoformat()}"
    if until is None:
        return f"from {since.isoformat()} onward"
    return f"{since.isoformat()} to {until.isoformat()}"


def reports_published_cut(cut, prints):
    prints(
        f"{cut.recording_id}  {cut.classification:<8} {cut.published_on.isoformat()}  "
        f"{'edited' if cut.edited else 'unedited'}"
    )
    if not cut.edited or not cut.proposal_recorded:
        prints(
            "  no error figure: "
            + (
                "nothing the machine proposed is on record"
                if cut.edited
                else "the reviewer moved nothing, so there is no human answer to subtract"
            )
        )
        return
    for named, error in (
        ("punch-in", cut.punch_in_error_seconds),
        ("punch-out", cut.punch_out_error_seconds),
    ):
        prints(
            f"  {named:<10} no error figure: the reviewer did not move it, "
            "so there is no human answer to subtract"
            if error is None
            else f"  {named:<10} error {error:+8.3f} s"
        )


def reports_rate(rate, prints):
    for cut in rate.cuts:
        reports_published_cut(cut, prints)
    if rate.unplaced:
        prints(
            f"{rate.unplaced} published Segment"
            + (
                " carries no publication date and is in no period"
                if rate.unplaced == 1
                else "s carry no publication date and are in no period"
            )
        )
    if rate.proportion is None:
        prints("nothing was published in that period, so there is no rate to report")
        return 1
    prints(
        f"{rate.published} Segment{'' if rate.published == 1 else 's'} published, "
        f"{len(rate.approved_with_no_edit)} approved with no boundary edit: "
        f"{rate.proportion:.0%}"
    )
    return 0


def reports_approvals(settings=None, arguments=None, prints=print):
    """Print the fraction of a period's published Segments approved with no boundary edit.

    Reads the store and nothing else: no corpus, no object store, no model host.
    """
    asked = parses_approvals_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    settings = resolves_settings() if settings is None else settings
    configured = settings.get(DATA_ROOT)
    if not asked.store and not configured:
        prints(f"nothing sets {DATA_ROOT}")
        return 1
    data_root = Path(asked.store).resolve() if asked.store else Path(configured)
    try:
        store = opens_store(data_root)
    except StoredSchemaDiffers as stale:
        prints(str(stale))
        return 1
    try:
        prints(f"reading approvals from {data_root}, {names_period(asked.since, asked.until)}")
        return reports_rate(
            ReportsApprovalRate(store=store)(since=asked.since, until=asked.until), prints
        )
    finally:
        store.close()


CORPUS_USAGE = (
    "sermon-corpus <recording-id> [--corpus <corpus-root>] [--prompts <dir>] "
    "[--tag <text>] [--model <name>] [--asr <config>] [--store <data-root>]"
)


def parses_corpus_command(arguments, prints):
    parser = argparse.ArgumentParser(prog="sermon-corpus", usage=CORPUS_USAGE, add_help=True)
    parser.add_argument("recording")
    parser.add_argument("--corpus")
    parser.add_argument("--prompts")
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--model", default=CLASSIFIER)
    parser.add_argument("--asr", default=ASR_CONFIG)
    parser.add_argument("--store")
    try:
        return parser.parse_args(arguments)
    except SystemExit:
        prints(f"usage: {CORPUS_USAGE}")
        return None


def derives_corpus(settings=None, arguments=None, reasons=None, prints=print):
    """Record one Recording's classifier answer in a corpus tree the graders walk.

    The population `sermon-regrade` grades is the tagged block files, and the
    store holds no part of a classifier answer but the Blocks it became, so a
    stored pair for a recording with no block file is graded against nothing.
    Reads the store, writes no row, and sends no audio anywhere.
    """
    asked = parses_corpus_command(sys.argv[1:] if arguments is None else arguments, prints)
    if asked is None:
        return 1
    try:
        configuration = ReadsConfiguration(
            resolves_settings() if settings is None else settings
        )()
    except MissingConfiguration as unset:
        prints(str(unset))
        return 1
    data_root = Path(asked.store).resolve() if asked.store else Path(configuration.data_root)
    corpus = Path(asked.corpus).resolve() if asked.corpus else layout.corpus_root(data_root)
    prompts = Path(asked.prompts).resolve() if asked.prompts else corpus.parent / "prompts"
    BindsModelEndpoint(configuration=configuration)()
    store = opens_store(data_root)
    try:
        entry = DerivesCorpusEntry(
            store=store,
            corpus_root=corpus,
            prompts_root=prompts,
            asr_config=asked.asr,
            tag=asked.tag,
            reasons=reasons or ReasonsOverTranscript(asked.model),
        )(asked.recording)
    except (
        BlockFileAlreadyWritten,
        NothingToBlock,
        RootNotConfigured,
        TranscriptNotStored,
    ) as refused:
        prints(str(refused))
        return 1
    finally:
        store.close()
    prints(f"recorded {entry.blocks.name} beside {entry.transcript.name} under {corpus}")
    for chosen in entry.chosen:
        prints(
            f"  {chosen['classification']:<8} {hms(chosen['punch_in'])} -> "
            f"{hms(chosen['punch_out'])}  ({chosen['boundary_source']})"
        )
    return 0
