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
    "rendered_mp3",
    "transcript",
    "waveform_peaks",
    "preview",
    "diarization",
)

JOB_KINDS = ("download", "analyze", "render")

JOB_STATES = ("queued", "running", "succeeded", "failed", "cancelled")
