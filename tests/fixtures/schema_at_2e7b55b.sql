CREATE TABLE recording (
    recording_id TEXT NOT NULL PRIMARY KEY,
    object_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('discovered', 'downloading', 'ingest_failed', 'downloaded', 'analyzing', 'analysis_failed', 'ignored', 'awaiting_review', 'reviewed', 'discarded')),
    started_at TEXT NOT NULL,
    started_at_source TEXT NOT NULL CHECK (started_at_source IN ('key', 'last_modified')),
    size_bytes INTEGER NOT NULL,
    capture_device TEXT,
    kind TEXT CHECK (kind IN ('service', 'class', 'special_service', 'meeting', 'rehearsal', 'empty', 'unknown')),
    duration_seconds REAL,
    channels INTEGER,
    sample_rate INTEGER,
    bits_per_raw_sample INTEGER,
    mono_source TEXT,
    mono_source_confirmed INTEGER CHECK (mono_source_confirmed IN (0, 1)),
    local_path TEXT,
    checksum TEXT,
    sidecar_present INTEGER CHECK (sidecar_present IN (0, 1)),
    integrated_loudness_lufs REAL,
    true_peak_dbtp REAL,
    loudness_range_lu REAL,
    dynamic_range_db REAL,
    active_fraction REAL,
    longest_active_seconds REAL,
    waiting_since TEXT,
    skip_reason TEXT
);
CREATE UNIQUE INDEX unique_recording_object_key ON recording (object_key);
CREATE TABLE recording_channel_level (
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    position INTEGER NOT NULL,
    channel INTEGER NOT NULL,
    rms_db REAL NOT NULL,
    PRIMARY KEY (recording_id, position)
);
CREATE TABLE recording_warning (
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    position INTEGER NOT NULL,
    warning TEXT NOT NULL CHECK (warning IN ('damaged container', 'source clipping detected', 'sidecar disagrees with the audio', 'unexpected stereo content', 'unexpected language', 'low transcript quality', 'source no longer available')),
    PRIMARY KEY (recording_id, position),
    UNIQUE (recording_id, warning)
);
CREATE TABLE block (
    block_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('announcements', 'music', 'prayer', 'scripture_reading', 'sermon', 'lesson', 'seminar', 'communion', 'qa', 'rehearsal', 'other')),
    classification_confidence TEXT CHECK (classification_confidence IN ('high', 'medium', 'low')),
    self_reported_confidence REAL,
    summary TEXT,
    cue_start_seconds REAL,
    cue_end_seconds REAL,
    retyped_by_human INTEGER NOT NULL CHECK (retyped_by_human IN (0, 1)),
    possibly_multiple_types INTEGER NOT NULL CHECK (possibly_multiple_types IN (0, 1))
);
CREATE TABLE block_evidence (
    block_id INTEGER NOT NULL REFERENCES block(block_id),
    position INTEGER NOT NULL,
    timecode REAL NOT NULL,
    finding TEXT NOT NULL,
    implies TEXT NOT NULL,
    PRIMARY KEY (block_id, position)
);
CREATE TABLE block_speaker_match (
    block_id INTEGER NOT NULL REFERENCES block(block_id),
    position INTEGER NOT NULL,
    speaker_profile_id INTEGER NOT NULL REFERENCES speaker_profile(speaker_profile_id),
    similarity REAL NOT NULL,
    PRIMARY KEY (block_id, position)
);
CREATE TABLE speaker_profile (
    speaker_profile_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    confirmed_by_human INTEGER NOT NULL CHECK (confirmed_by_human IN (0, 1))
);
CREATE TABLE speaker_profile_enrolment (
    speaker_profile_id INTEGER NOT NULL REFERENCES speaker_profile(speaker_profile_id),
    position INTEGER NOT NULL,
    segment_id INTEGER NOT NULL REFERENCES segment(segment_id),
    PRIMARY KEY (speaker_profile_id, position)
);
CREATE TABLE segment (
    segment_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    seed_block_id INTEGER REFERENCES block(block_id),
    classification TEXT NOT NULL CHECK (classification IN ('sermon', 'lesson', 'seminar', 'meeting')),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'approved', 'skipped', 'processing', 'processing_failed', 'complete', 'recut')),
    span_start_seconds REAL NOT NULL,
    span_end_seconds REAL NOT NULL,
    punch_in_seconds REAL NOT NULL,
    punch_out_seconds REAL NOT NULL,
    intent TEXT CHECK (intent IN ('publish', 'archive')),
    disposition_at TEXT,
    distribution_confirmed INTEGER CHECK (distribution_confirmed IN (0, 1)),
    confirmed_speaker_profile_id INTEGER REFERENCES speaker_profile(speaker_profile_id),
    boundary_source TEXT CHECK (boundary_source IN ('model', 'refined', 'model-in/refined-out', 'human')),
    leading_silence_seconds REAL,
    summary TEXT,
    publication_date TEXT,
    label TEXT
);
CREATE TABLE segment_warning (
    segment_id INTEGER NOT NULL REFERENCES segment(segment_id),
    position INTEGER NOT NULL,
    warning TEXT NOT NULL CHECK (warning IN ('check the opening', 'no clean cut point found at punch-in', 'no clean cut point found at punch-out', 'boundary is not acceptable', 'source was very quiet')),
    PRIMARY KEY (segment_id, position),
    UNIQUE (segment_id, warning)
);
CREATE TABLE proposal (
    proposal_id INTEGER PRIMARY KEY,
    segment_id INTEGER NOT NULL REFERENCES segment(segment_id),
    classification_confidence TEXT NOT NULL CHECK (classification_confidence IN ('high', 'medium', 'low')),
    boundary_confidence TEXT NOT NULL CHECK (boundary_confidence IN ('high', 'medium', 'low')),
    punch_in_grade TEXT NOT NULL CHECK (punch_in_grade IN ('easy', 'moderate', 'hard')),
    punch_out_grade TEXT NOT NULL CHECK (punch_out_grade IN ('easy', 'moderate', 'hard')),
    agreement_gap_seconds REAL,
    superseded_by INTEGER REFERENCES proposal(proposal_id)
);
CREATE TABLE proposal_evidence (
    proposal_id INTEGER NOT NULL REFERENCES proposal(proposal_id),
    position INTEGER NOT NULL,
    timecode REAL NOT NULL,
    finding TEXT NOT NULL,
    implies TEXT NOT NULL,
    PRIMARY KEY (proposal_id, position)
);
CREATE TABLE proposal_missing_evidence (
    proposal_id INTEGER NOT NULL REFERENCES proposal(proposal_id),
    position INTEGER NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (proposal_id, position)
);
CREATE TABLE proposal_punch_in_candidate (
    proposal_id INTEGER NOT NULL REFERENCES proposal(proposal_id),
    position INTEGER NOT NULL,
    timecode REAL NOT NULL,
    considered_because TEXT NOT NULL,
    PRIMARY KEY (proposal_id, position)
);
CREATE TABLE artifact (
    artifact_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    segment_id INTEGER REFERENCES segment(segment_id),
    kind TEXT NOT NULL CHECK (kind IN ('source_flac', 'envelope', 'rendered_mp3', 'transcript', 'waveform_peaks', 'preview', 'diarization')),
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    render_settings TEXT,
    input_loudness_lufs REAL,
    output_loudness_lufs REAL,
    output_true_peak_dbtp REAL,
    asr_config TEXT,
    superseded_by INTEGER REFERENCES artifact(artifact_id)
);
CREATE TABLE job (
    job_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    segment_id INTEGER REFERENCES segment(segment_id),
    kind TEXT NOT NULL CHECK (kind IN ('download', 'analyze', 'render')),
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    dedupe_key TEXT NOT NULL,
    last_error TEXT,
    failed_permanently INTEGER NOT NULL CHECK (failed_permanently IN (0, 1)),
    queued_at TEXT NOT NULL,
    started_at TEXT
);
CREATE UNIQUE INDEX unique_job_dedupe_key ON job (dedupe_key) WHERE state IN ('queued', 'running');
CREATE TABLE reviewer (
    actor TEXT NOT NULL PRIMARY KEY,
    receives_notifications INTEGER NOT NULL CHECK (receives_notifications IN (0, 1))
);
CREATE TABLE notification (
    notification_id INTEGER PRIMARY KEY,
    recording_id TEXT REFERENCES recording(recording_id),
    segment_id INTEGER REFERENCES segment(segment_id),
    kind TEXT NOT NULL,
    recipient TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'delivered', 'failed', 'suppressed')),
    CHECK (segment_id IS NULL OR (recording_id IS NOT NULL))
);
CREATE TABLE skipped_object (
    object_key TEXT NOT NULL PRIMARY KEY,
    reason TEXT NOT NULL CHECK (reason IN ('recorder clock not set', 'key does not match the pattern', 'not an audio object', 'before the ingest cutoff'))
);
CREATE TABLE discovery (
    discovery_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('webhook', 'scan')),
    occurred_at TEXT NOT NULL,
    discovered_count INTEGER NOT NULL,
    failure TEXT CHECK (failure IN ('transient', 'credentials')),
    event TEXT,
    CHECK (failure IS NULL OR (kind IN ('scan') AND discovered_count IN (0))),
    CHECK (event IS NULL OR (kind IN ('webhook')))
);
CREATE TABLE corpus_pair (
    corpus_pair_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    classification TEXT NOT NULL CHECK (classification IN ('sermon', 'lesson', 'seminar', 'meeting')),
    provenance TEXT NOT NULL CHECK (provenance IN ('human', 'machine')),
    alignment TEXT CHECK (alignment IN ('aligned', 'cannot be aligned', 'not a contiguous excerpt')),
    punch_in_seconds REAL,
    punch_out_seconds REAL,
    drift_ppm REAL,
    punch_in_difficulty TEXT CHECK (punch_in_difficulty IN ('easy', 'moderate', 'hard')),
    punch_out_difficulty TEXT CHECK (punch_out_difficulty IN ('easy', 'moderate', 'hard')),
    covers_more_than_95_percent INTEGER NOT NULL CHECK (covers_more_than_95_percent IN (0, 1)),
    CHECK (alignment IS NULL OR (provenance IN ('human'))),
    CHECK (punch_in_seconds IS NULL OR (provenance IN ('human') AND alignment IN ('aligned'))),
    CHECK (punch_out_seconds IS NULL OR (punch_in_seconds IS NOT NULL AND provenance IN ('human') AND alignment IN ('aligned'))),
    CHECK (drift_ppm IS NULL OR (punch_in_seconds IS NOT NULL AND punch_out_seconds IS NOT NULL AND alignment IN ('aligned'))),
    CHECK (punch_in_difficulty IS NULL OR (punch_in_seconds IS NOT NULL AND provenance IN ('human') AND alignment IN ('aligned'))),
    CHECK (punch_out_difficulty IS NULL OR (punch_out_seconds IS NOT NULL AND provenance IN ('human') AND alignment IN ('aligned')))
);
CREATE UNIQUE INDEX unique_corpus_pair_recording_id_classification_provenance ON corpus_pair (recording_id, classification, provenance);
CREATE TABLE log_entry (
    log_entry_id INTEGER PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recording(recording_id),
    segment_id INTEGER REFERENCES segment(segment_id),
    job_id INTEGER REFERENCES job(job_id),
    proposal_id INTEGER REFERENCES proposal(proposal_id),
    artifact_id INTEGER REFERENCES artifact(artifact_id),
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    actor TEXT,
    entered_state TEXT CHECK (entered_state IN ('discovered', 'downloading', 'ingest_failed', 'downloaded', 'analyzing', 'analysis_failed', 'ignored', 'awaiting_review', 'reviewed', 'discarded', 'proposed', 'approved', 'skipped', 'processing', 'processing_failed', 'complete', 'recut')),
    duration_seconds REAL,
    error TEXT,
    punch_in_seconds REAL,
    punch_out_seconds REAL,
    boundary_source TEXT CHECK (boundary_source IN ('model', 'refined', 'model-in/refined-out', 'human'))
);
