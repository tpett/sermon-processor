RECORDING_STATES = (
    "discovered",
    "downloading",
    "ingest_failed",
    "downloaded",
    "analyzing",
    "analysis_failed",
    "ignored",
    "awaiting_review",
    "reviewed",
    "discarded",
)

SEGMENT_STATES = (
    "proposed",
    "approved",
    "skipped",
    "processing",
    "processing_failed",
    "complete",
    "recut",
)

LOGGED_STATES = RECORDING_STATES + SEGMENT_STATES

BLOCK_TYPES = (
    "announcements",
    "music",
    "prayer",
    "scripture_reading",
    "sermon",
    "lesson",
    "seminar",
    "communion",
    "qa",
    "rehearsal",
    "other",
)

STARTED_AT_SOURCES = ("key", "last_modified")

RECORDING_WARNINGS = (
    "damaged container",
    "source clipping detected",
    "sidecar disagrees with the audio",
    "unexpected stereo content",
    "unexpected language",
    "low transcript quality",
    "source no longer available",
)

SEGMENT_WARNINGS = (
    "check the opening",
    "boundary is not acceptable",
    "source was very quiet",
)

SEGMENT_CLASSIFICATIONS = ("sermon", "lesson", "seminar", "meeting")

RECORDING_KINDS = (
    "service",
    "class",
    "special_service",
    "meeting",
    "rehearsal",
    "empty",
    "unknown",
)

SEGMENT_INTENTS = ("publish", "archive")

BOUNDARY_SOURCES = ("model", "refined", "model-in/refined-out", "human")

CONFIDENCE_LEVELS = ("high", "medium", "low")

CUT_DIFFICULTIES = ("easy", "moderate", "hard")

ARTIFACT_KINDS = (
    "source_flac",
    "envelope",
    "rendered_mp3",
    "transcript",
    "waveform_peaks",
    "preview",
    "diarization",
)

JOB_KINDS = ("download", "analyze", "render")

JOB_STATES = ("queued", "running", "succeeded", "failed", "cancelled")

JOB_STATES_IN_FLIGHT = ("queued", "running")

NOTIFICATION_STATES = ("pending", "delivered", "failed", "suppressed")

SKIP_REASONS = (
    "recorder clock not set",
    "key does not match the pattern",
    "not an audio object",
    "before the ingest cutoff",
)

DISCOVERY_KINDS = ("webhook", "scan")

DISCOVERY_FAILURES = ("transient", "credentials")
