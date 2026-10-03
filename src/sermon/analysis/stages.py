from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.analysis.io import reads_json, writes_json
from sermon.extends_segment_span import WidensProposedSpan
from sermon.pipeline import cues, scripture
from sermon.store import (
    Block,
    Candidate,
    CorpusPair,
    Evidence,
    Proposal,
    Recording,
    Segment,
    SpeakerProfile,
    Store,
)
from sermon.store.vocabularies import BLOCK_TYPES, SEGMENT_CLASSIFICATIONS

TEACHING = frozenset({"sermon", "lesson", "seminar"})
LABELLED_BY_PASSAGE = frozenset({"sermon"})
READING_LOOKBACK_S = 900.0
READING_LEAD_S = 60.0
LABEL_LIMIT = 60
SUNDAY_ORDER = (
    "announcements",
    "prayer",
    "music",
    "prayer",
    "scripture_reading",
    "sermon",
    "prayer",
    "communion",
    "music",
    "prayer",
)
USUAL_SERVICE_S = 10 * 3600 + 30 * 60
MOST_OF_THE_SOURCE = 0.95
USUAL_SERVICE_WINDOW_S = 20 * 60
QUIET_EASY_S = 2.0
QUIET_MODERATE_S = 0.25
SPEAKER_EDGE_S = 2.0
CUE_NEAR_S = 30.0
CONFIDENT_ENOUGH = 0.8
UNCERTAIN_BELOW = 0.5
PUBLISHABLE_MIN_S = 30 * 60
PUBLISHABLE_MAX_S = 75 * 60


def now():
    return datetime.now(UTC)


def stage_failed(stage, error):
    from sermon.jobs.analyzes_recording import StageFailed

    return StageFailed(stage, error)


def quiet_around(moment, doc):
    utterances = doc.get("utterances", ())
    resumes = min(
        (
            utterance["start"]
            for utterance in utterances
            if utterance["start"] >= moment - QUIET_MODERATE_S
        ),
        default=doc.get("duration", moment),
    )
    stopped = max(
        (utterance["end"] for utterance in utterances if utterance["end"] <= resumes), default=0.0
    )
    if moment < stopped - QUIET_MODERATE_S:
        return 0.0
    return max(0.0, resumes - stopped)


def grades_cut(moment, doc):
    quiet = quiet_around(moment, doc)
    if quiet >= QUIET_EASY_S:
        return "easy"
    return "moderate" if quiet >= QUIET_MODERATE_S else "hard"


def text_between(doc, start, end):
    return " ".join(
        utterance.get("text", "")
        for utterance in doc.get("utterances", ())
        if utterance["start"] < end and utterance["end"] > start
    ).lower()


@dataclass(frozen=True)
class TranscribesRecording:
    store: Store
    transcribes: object = None

    def __call__(self, recording):
        from sermon.analysis.transcribes_audio import TranscriptionUnavailable

        doc = reads_json(self.store, recording, "transcript")
        if doc is None and self.transcribes is not None:
            try:
                doc = self.transcribes(recording)
            except TranscriptionUnavailable as unavailable:
                raise stage_failed("transcription", str(unavailable)) from unavailable
            writes_json(self.store, recording, "transcript", doc)
        if doc is None:
            raise stage_failed("transcription", "no transcript is stored for this Recording")
        return self._flags(recording, doc)

    def _flags(self, recording, doc):
        """What the transcript says about itself. Neither flag stops Analysis."""
        from sermon.analysis.transcribes_audio import POOR_CONFIDENCE, EXPECTED_LANGUAGE

        stored = self.store.loads(Recording, recording.recording_id) or recording
        warnings = list(stored.warnings)
        spoken = doc.get("language")
        if spoken is not None and spoken != EXPECTED_LANGUAGE:
            if "unexpected language" not in warnings:
                warnings.append("unexpected language")
        measured = doc.get("speech_confidence", doc.get("average_confidence"))
        if measured is not None and measured < POOR_CONFIDENCE:
            if "low transcript quality" not in warnings:
                warnings.append("low transcript quality")
        if tuple(warnings) == stored.warnings:
            return stored
        return self.store.saves(replace(stored, warnings=tuple(warnings)))


@dataclass(frozen=True)
class DiarizesRecording:
    store: Store
    diarizes: object = None

    def __call__(self, recording):
        stored = reads_json(self.store, recording, "diarization")
        if stored is not None:
            turns = list(stored.get("turns", ()))
        elif self.diarizes is not None:
            from sermon.analysis.diarizes_audio import DiarizationUnavailable

            try:
                turns = list(self.diarizes(recording))
            except DiarizationUnavailable as unavailable:
                raise stage_failed("diarization", str(unavailable)) from unavailable
        else:
            raise stage_failed("diarization", "no diarization is stored for this Recording")
        profiles = self.store.lists(SpeakerProfile)
        for turn in turns:
            for profile in profiles:
                spoken = str(turn.get("speaker", ""))
                if profile.name.lower() in spoken.lower() or spoken == profile.name:
                    turn["speaker"] = profile.name
                    turn["profile_id"] = profile.speaker_profile_id
                    break
        writes_json(self.store, recording, "diarization", {"turns": turns})
        return recording


@dataclass(frozen=True)
class EnrolsVoiceProfiles:
    store: Store

    def __call__(self, segments=None):
        enrolled = []
        for segment in segments or self.store.lists(Segment, state="complete"):
            if segment.classification not in TEACHING:
                continue
            if segment.confirmed_speaker_profile_id:
                profile = self.store.loads(SpeakerProfile, segment.confirmed_speaker_profile_id)
                enrolled.append(
                    self.store.saves(
                        replace(profile, enrolled_from=profile.enrolled_from + (segment.segment_id,))
                    )
                )
                continue
            profile = self.store.saves(
                SpeakerProfile(
                    name=f"preacher-{segment.segment_id}",
                    embedding=b"voice",
                    enrolled_from=(),
                    confirmed_by_human=True,
                )
            )
            profile = self.store.saves(replace(profile, enrolled_from=(segment.segment_id,)))
            self.store.saves(replace(segment, confirmed_speaker_profile_id=profile.speaker_profile_id))
            enrolled.append(profile)
        return tuple(enrolled)


@dataclass(frozen=True)
class DividesIntoBlocks:
    store: Store
    divides: object = None

    def __call__(self, recording):
        existing = self.store.lists(Block, recording_id=recording.recording_id)
        if existing:
            return existing
        doc = reads_json(self.store, recording, "transcript")
        if doc is None:
            raise stage_failed("blocking", "no transcript is stored for this Recording")
        spans = list(self._divides()(doc))
        if not spans:
            return [
                self.store.saves(
                    Block(
                        recording_id=recording.recording_id,
                        start_seconds=0.0,
                        end_seconds=recording.duration_seconds or doc.get("duration", 0.0),
                        type="music",
                        evidence=(Evidence(timecode=0.0, finding="no speech", implies="music"),),
                    )
                )
            ]
        edges = _speaker_edges(reads_json(self.store, recording, "diarization"))
        return [
            self.store.saves(
                Block(
                    recording_id=recording.recording_id,
                    start_seconds=span["start"],
                    end_seconds=span["end"],
                    type=span.get("type") if span.get("type") in BLOCK_TYPES else "other",
                    self_reported_confidence=span.get("confidence"),
                    evidence=_blocking_evidence(span, edges, doc),
                )
            )
            for span in spans
        ]

    def _divides(self):
        if self.divides is not None:
            return self.divides
        from sermon.analysis.proposes_from_transcript import DividesByReasoning

        return DividesByReasoning()


def _speaker_edges(turns_doc):
    if not turns_doc:
        return ()
    return tuple(
        sorted(
            {turn["start"] for turn in turns_doc.get("turns", ())}
            | {turn["end"] for turn in turns_doc.get("turns", ())}
        )
    )


def _blocking_evidence(span, edges, doc):
    changed = any(abs(edge - span["start"]) <= SPEAKER_EDGE_S for edge in edges)
    found = [
        Evidence(
            timecode=span["start"],
            finding=str(span.get("evidence") or "transcript structure")[:200],
            implies="speaker change" if changed else "no speaker attribution",
        )
    ]
    paused = [
        gap
        for gap in doc.get("silences", ())
        if span["start"] <= gap["start"] < span["end"] and gap["end"] - gap["start"] >= QUIET_EASY_S
    ]
    if paused:
        found.append(
            Evidence(
                timecode=paused[0]["start"], finding="pause", implies="pause within the Block"
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class ClassifiesBlocks:
    store: Store

    def __call__(self, recording):
        blocks = sorted(
            self.store.lists(Block, recording_id=recording.recording_id),
            key=lambda item: item.start_seconds,
        )
        if not blocks:
            blocks = DividesIntoBlocks(store=self.store)(recording)
        chosen = [item.type for item in blocks]
        if recording.kind == "rehearsal":
            chosen = [
                "rehearsal" if item in {"music", "other", "rehearsal"} else item for item in chosen
            ]
        for index, block_type in enumerate(chosen):
            if block_type in TEACHING and "qa" in chosen[index + 1 : index + 3]:
                chosen[index] = "lesson"
        matches_sunday = _matches_sunday(chosen)
        return [
            self.store.saves(
                replace(
                    block,
                    type=chosen[index],
                    classification_confidence=_graded(block.self_reported_confidence, matches_sunday),
                    evidence=tuple(
                        _classification_evidence(recording, block, chosen, index, matches_sunday)
                    ),
                )
            )
            for index, block in enumerate(blocks)
        ]


def _graded(self_reported, matches_sunday):
    if matches_sunday or self_reported is None:
        return "high" if matches_sunday else "medium"
    if self_reported >= CONFIDENT_ENOUGH:
        return "high"
    return "medium" if self_reported >= UNCERTAIN_BELOW else "low"


def _classification_evidence(recording, block, chosen, index, matches_sunday):
    found = list(block.evidence)
    if chosen[index] in TEACHING and "qa" in chosen[index + 1 : index + 3]:
        found.append(
            Evidence(
                timecode=block.end_seconds,
                finding="followed by question and answer",
                implies="lesson",
            )
        )
    wall = _clock_seconds(recording.started_at) + block.start_seconds
    if USUAL_SERVICE_S <= wall <= USUAL_SERVICE_S + USUAL_SERVICE_WINDOW_S:
        found.append(
            Evidence(
                timecode=block.start_seconds,
                finding="starting shortly after the usual service time",
                implies="sermon",
            )
        )
    if matches_sunday:
        found.append(
            Evidence(
                timecode=block.start_seconds,
                finding="matches the expected Sunday order",
                implies="position prior",
            )
        )
    if chosen[index] == "prayer":
        found.append(
            Evidence(
                timecode=block.start_seconds,
                finding="prayer, not the sermon",
                implies="not the sermon",
            )
        )
    return found


def _clock_seconds(moment):
    return moment.hour * 3600 + moment.minute * 60 + moment.second + moment.microsecond / 1e6


def _matches_sunday(types):
    if len(types) < 4:
        return False
    return (
        tuple(types[: len(SUNDAY_ORDER)]) == SUNDAY_ORDER[: len(types)]
        or tuple(types)[:8] == SUNDAY_ORDER[:8]
    )


@dataclass(frozen=True)
class SummarizesBlocks:
    store: Store
    summarizes: object = None

    def __call__(self, recording):
        doc = reads_json(self.store, recording, "transcript")
        if doc is None:
            raise stage_failed("summarization", "no transcript is stored for this Recording")
        summarizes = self.summarizes or self._summarizes()
        for block in self.store.lists(Block, recording_id=recording.recording_id):
            if block.type == "music":
                continue
            answered = summarizes(block, doc)
            if answered is None:
                continue
            summary, cue = answered
            self.store.saves(
                replace(
                    block,
                    summary=summary,
                    cue_start_seconds=round(cue[0], 3),
                    cue_end_seconds=round(cue[1], 3),
                )
            )
        SuggestsPublicationLabel(store=self.store)(recording, doc)
        return recording

    def _summarizes(self):
        from sermon.analysis.proposes_from_transcript import SummarizesOneBlock

        return SummarizesOneBlock()


@dataclass(frozen=True)
class SuggestsPublicationLabel:
    store: Store

    def __call__(self, recording, doc=None):
        doc = reads_json(self.store, recording, "transcript") if doc is None else doc
        if doc is None:
            return ()
        blocks = self.store.lists(Block, recording_id=recording.recording_id)
        suggested = []
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            if segment.label:
                continue
            label = self.suggests(segment, doc, blocks)
            if label:
                suggested.append(self.store.saves(replace(segment, label=label)))
        return tuple(suggested)

    def suggests(self, segment, doc, blocks):
        if segment.classification in LABELLED_BY_PASSAGE:
            return _passage_of(segment, doc, blocks)
        return _titled(segment.summary)


def _readings_before(blocks, punch_in):
    near = [
        block
        for block in blocks
        if block.type == "scripture_reading"
        and block.start_seconds < punch_in + READING_LEAD_S
        and block.end_seconds > punch_in - READING_LOOKBACK_S
    ]
    return sorted(near, key=lambda block: -block.start_seconds)


def _passage_of(segment, doc, blocks):
    utterances = doc.get("utterances", ())
    for block in _readings_before(blocks, segment.punch_in_seconds):
        announced = scripture.announced_passage(
            utterances, block.start_seconds, block.end_seconds
        )
        if announced:
            return announced
    return scripture.primary_passage(
        utterances, segment.punch_in_seconds, segment.punch_out_seconds
    )


def _titled(summary):
    if not summary:
        return None
    sentence = re.split(r"[.;:!?]", summary.strip(), maxsplit=1)[0]
    return " ".join(sentence.split())[:LABEL_LIMIT].strip(" ,-") or None


@dataclass(frozen=True)
class ProposesSegments:
    store: Store
    derives: object = None

    def __call__(self, recording):
        doc = reads_json(self.store, recording, "transcript")
        blocks = _ordered_blocks(self.store, recording.recording_id)
        if doc is None or not blocks:
            return ()
        derives = self.derives or self._derives()
        existing = self.store.lists(Segment, recording_id=recording.recording_id)
        preserved = [item for item in existing if _is_the_reviewers(item)]
        superseded = [item for item in existing if not _is_the_reviewers(item)]
        produced = list(preserved)
        for span in derives(_spans_of(blocks), doc):
            if any(_overlaps(span, kept) for kept in preserved):
                continue
            standing = next((item for item in superseded if _overlaps(span, item)), None)
            if standing is not None:
                superseded.remove(standing)
            produced.append(self._proposes(recording, span, blocks, doc, standing))
        SuggestsPublicationLabel(store=self.store)(recording, doc)
        return tuple(
            self.store.loads(Segment, item.segment_id) for item in produced
        )

    def _derives(self):
        from sermon.analysis.proposes_from_transcript import DerivesSpans

        return DerivesSpans()

    def _proposes(self, recording, span, blocks, doc, standing=None):
        seed = _seed_of(blocks, span)
        proposed = Segment(
            recording_id=recording.recording_id,
            seed_block_id=seed.block_id if seed else None,
            classification=(
                span["classification"]
                if span["classification"] in SEGMENT_CLASSIFICATIONS
                else "sermon"
            ),
            state="proposed",
            span_start_seconds=span["punch_in"],
            span_end_seconds=span["punch_out"],
            punch_in_seconds=span["punch_in"],
            punch_out_seconds=span["punch_out"],
            boundary_source="model",
        )
        if standing is not None:
            proposed = replace(proposed, segment_id=standing.segment_id)
        segment = self.store.saves(
            WidensProposedSpan(store=self.store)(proposed, recording.duration_seconds)
        )
        _replaces_proposal(
            self.store,
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence=_graded(span.get("confidence"), False),
                boundary_confidence="medium",
                punch_in_grade=grades_cut(span["punch_in"], doc),
                punch_out_grade=grades_cut(span["punch_out"], doc),
                evidence=tuple(_seeding_evidence(span, seed, blocks)),
            ),
        )
        return segment


def _is_the_reviewers(segment):
    return segment.boundary_source == "human" or segment.state in {
        "complete",
        "approved",
        "skipped",
    }


def _replaces_proposal(store, proposal):
    standing = store.lists(Proposal, segment_id=proposal.segment_id)
    return store.saves(
        proposal if not standing else replace(proposal, proposal_id=standing[0].proposal_id)
    )


def _ordered_blocks(store, recording_id):
    return sorted(
        store.lists(Block, recording_id=recording_id), key=lambda item: item.start_seconds
    )


def _spans_of(blocks):
    return [
        {
            "start": item.start_seconds,
            "end": item.end_seconds,
            "type": item.type,
            "confidence": item.self_reported_confidence or 0.5,
        }
        for item in blocks
    ]


def _overlaps(span, segment):
    return (
        min(segment.punch_out_seconds, span["punch_out"])
        - max(segment.punch_in_seconds, span["punch_in"])
        > 0
    )


def _seed_of(blocks, span):
    for block in blocks:
        if block.type == span["classification"] and block.start_seconds < span["punch_out"]:
            if block.end_seconds > span["punch_in"]:
                return block
    return None


def _seeding_evidence(span, seed, blocks):
    found = [
        Evidence(
            timecode=span["punch_in"],
            finding=f"seeded on the {span['classification']} block",
            implies="seed",
        )
    ]
    following = next(
        (item for item in blocks if item.start_seconds >= span["punch_out"] - 0.001), None
    )
    if following is not None:
        found.append(
            Evidence(
                timecode=following.start_seconds,
                finding=f"stopped before {following.type.replace('_', ' ')}",
                implies="stop",
            )
        )
    return found


@dataclass(frozen=True)
class RefinesPunchIn:
    store: Store
    chooses: object = None

    def __call__(self, recording=None, segment=None):
        refined = [
            self._refines(item, chosen, doc)
            for item, chosen, doc in _boundaries(self.store, self.chooses, recording, segment)
        ]
        return refined[0] if segment is not None and refined else refined

    def _refines(self, item, chosen, doc):
        if chosen is None:
            return item
        punch = chosen["punch_in"]
        warnings = list(item.warnings)
        if grades_cut(punch, doc) == "hard" and "no clean cut point found at punch-in" not in warnings:
            warnings.append("no clean cut point found at punch-in")
        spoken = min(
            (
                utterance["start"]
                for utterance in doc.get("utterances", ())
                if utterance["start"] >= punch
            ),
            default=punch,
        )
        saved = self.store.saves(
            replace(
                item,
                punch_in_seconds=punch,
                leading_silence_seconds=round(spoken - punch, 3),
                warnings=tuple(warnings),
                boundary_source=chosen["boundary_source"],
            )
        )
        self._records_punch_in_evidence(saved, doc, spoken)
        return saved

    def _records_punch_in_evidence(self, item, doc, spoken):
        found = []
        opening = text_between(doc, spoken - 1.0, spoken + CUE_NEAR_S)
        if cues.any_hit(opening, cues.GREETING_OPENERS):
            found.append(
                Evidence(
                    timecode=item.punch_in_seconds,
                    finding="starts on the usual greeting",
                    implies="punch-in",
                )
            )
        considered = (
            (
                Candidate(
                    timecode=item.span_start_seconds,
                    considered_because="the start of the seeded block",
                ),
            )
            if abs(item.span_start_seconds - item.punch_in_seconds) > 0.001
            else ()
        )
        if not found and not considered:
            return
        _updates_proposal(
            self.store, item, evidence=tuple(found), punch_in_candidates=considered
        )


@dataclass(frozen=True)
class RefinesPunchOut:
    store: Store
    chooses: object = None

    def __call__(self, recording=None, segment=None):
        refined = [
            self._refines(item, chosen, doc)
            for item, chosen, doc in _boundaries(self.store, self.chooses, recording, segment)
        ]
        return refined[0] if segment is not None and refined else refined

    def _refines(self, item, chosen, doc):
        if chosen is None:
            return item
        punch = chosen["punch_out"]
        warnings = list(item.warnings)
        if (
            grades_cut(punch, doc) == "hard"
            and "no clean cut point found at punch-out" not in warnings
        ):
            warnings.append("no clean cut point found at punch-out")
        saved = self.store.saves(
            replace(
                item,
                punch_out_seconds=punch,
                warnings=tuple(warnings),
                boundary_source=chosen["boundary_source"],
            )
        )
        if "amen" in text_between(doc, punch - CUE_NEAR_S, punch):
            _updates_proposal(
                self.store,
                saved,
                evidence=(
                    Evidence(
                        timecode=punch,
                        finding="after the closing amen",
                        implies="punch-out",
                    ),
                ),
            )
        return saved


def _boundaries(store, chooses, recording, segment):
    if segment is not None:
        targets = [segment]
    elif recording is not None:
        targets = store.lists(Segment, recording_id=recording.recording_id)
    else:
        targets = store.lists(Segment)
    chosen_by_recording = {}
    for item in targets:
        if item.boundary_source == "human":
            yield item, None, None
            continue
        if item.recording_id not in chosen_by_recording:
            chosen_by_recording[item.recording_id] = _chooses(store, chooses, item.recording_id)
        chosen, doc = chosen_by_recording[item.recording_id]
        yield item, _matching(chosen, item), doc


def _chooses(store, chooses, recording_id):
    recording = store.loads(Recording, recording_id)
    doc = reads_json(store, recording, "transcript") if recording is not None else None
    blocks = _ordered_blocks(store, recording_id)
    if doc is None or not blocks:
        return (), doc
    if chooses is None:
        from sermon.analysis.proposes_from_transcript import ChoosesBoundaries

        chooses = ChoosesBoundaries()
    return tuple(chooses(_spans_of(blocks), doc)), doc


def _matching(chosen, segment):
    best, widest = None, 0.0
    for item in chosen:
        shared = min(segment.span_end_seconds, item["punch_out"]) - max(
            segment.span_start_seconds, item["punch_in"]
        )
        if shared > widest:
            best, widest = item, shared
    return best


def _updates_proposal(store, segment, **payload):
    existing = store.lists(Proposal, segment_id=segment.segment_id)
    if not existing:
        return store.saves(
            Proposal(
                segment_id=segment.segment_id,
                classification_confidence="medium",
                boundary_confidence="medium",
                punch_in_grade="moderate",
                punch_out_grade="moderate",
                **payload,
            )
        )
    kept = existing[0]
    merged = dict(payload)
    if payload.get("evidence"):
        merged["evidence"] = kept.evidence + payload["evidence"]
    if not payload.get("punch_in_candidates"):
        merged.pop("punch_in_candidates", None)
    return store.saves(replace(kept, **merged))


@dataclass(frozen=True)
class ScoresProposals:
    store: Store

    def __call__(self, recording):
        segments = self.store.lists(Segment, recording_id=recording.recording_id)
        if not segments:
            return ()
        doc = reads_json(self.store, recording, "transcript") or {"utterances": []}
        return tuple(self._scores(recording, item, doc) for item in segments)

    def _scores(self, recording, segment, doc):
        length = segment.punch_out_seconds - segment.punch_in_seconds
        wall = _clock_seconds(recording.started_at)
        expected = abs(wall - USUAL_SERVICE_S) <= USUAL_SERVICE_WINDOW_S
        publishable = PUBLISHABLE_MIN_S <= length <= PUBLISHABLE_MAX_S
        has_in_cue = cues.any_hit(
            text_between(doc, segment.punch_in_seconds - CUE_NEAR_S, segment.punch_in_seconds),
            cues.SCRIPTURE,
        ) or cues.any_hit(
            text_between(doc, segment.punch_in_seconds, segment.punch_in_seconds + CUE_NEAR_S),
            cues.GREETING_OPENERS,
        )
        has_out_cue = "amen" in text_between(
            doc, segment.punch_out_seconds - CUE_NEAR_S, segment.punch_out_seconds
        )
        missing = []
        if not has_in_cue:
            missing.append("no opening cue")
        if not has_out_cue:
            missing.append("closing prayer")
        if not (reads_json(self.store, recording, "diarization") or {}).get("turns"):
            missing.append("no speaker evidence")
        existing = self.store.lists(Proposal, segment_id=segment.segment_id)
        kept = list(existing[0].evidence) if existing else []
        payload = dict(
            classification_confidence="high" if expected or publishable else "medium",
            boundary_confidence=(
                "high" if has_in_cue and has_out_cue else "low" if not (has_in_cue or has_out_cue) else "medium"
            ),
            punch_in_grade=grades_cut(segment.punch_in_seconds, doc),
            punch_out_grade=grades_cut(segment.punch_out_seconds, doc),
            evidence=tuple(_deduplicated(kept)),
            missing_evidence=tuple(missing),
            punch_in_candidates=(
                existing[0].punch_in_candidates
                if existing and existing[0].punch_in_candidates
                else (
                    Candidate(
                        timecode=segment.span_start_seconds,
                        considered_because="the start of the seeded block",
                    ),
                )
            ),
        )
        if existing:
            return self.store.saves(replace(existing[0], **payload))
        return self.store.saves(Proposal(segment_id=segment.segment_id, **payload))


def _deduplicated(found):
    seen = set()
    unique = []
    for entry in found:
        key = (entry.finding, entry.implies)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)
    return unique


READ_FROM_THE_AUDIO = ("drift_ppm", "punch_in_difficulty", "punch_out_difficulty")


@dataclass(frozen=True)
class DerivesGroundTruth:
    store: Store

    def __call__(
        self,
        recording_id,
        *,
        punch_in,
        punch_out,
        classification="sermon",
        drift_ppm=None,
        alignment="aligned",
        provenance="human",
        punch_in_difficulty="easy",
        punch_out_difficulty="easy",
    ):
        existing = [
            item
            for item in self.store.lists(CorpusPair, recording_id=recording_id)
            if item.classification == classification and item.provenance == provenance
        ]
        if provenance != "human":
            alignment = None
            punch_in = None
            punch_out = None
            drift_ppm = None
        carried = dict(
            alignment=alignment,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            drift_ppm=drift_ppm,
            punch_in_difficulty=None if punch_in is None else punch_in_difficulty,
            punch_out_difficulty=None if punch_out is None else punch_out_difficulty,
        )
        if existing:
            return self.store.saves(replace(existing[0], **self.merges(existing[0], carried)))
        return self.store.saves(
            CorpusPair(
                recording_id=recording_id,
                classification=classification,
                provenance=provenance,
                covers_more_than_95_percent=self.covers_most_of(
                    recording_id, punch_in, punch_out
                ),
                **carried,
            )
        )

    def merges(self, held, carried):
        kept = dict(carried)
        if kept["punch_in_seconds"] is not None:
            for field in READ_FROM_THE_AUDIO:
                if kept[field] is None:
                    kept[field] = getattr(held, field)
            for boundary in ("punch_in", "punch_out"):
                if kept[f"{boundary}_seconds"] != getattr(held, f"{boundary}_seconds"):
                    kept[f"{boundary}_difficulty"] = carried[f"{boundary}_difficulty"]
        return dict(
            kept,
            covers_more_than_95_percent=self.covers_most_of(
                held.recording_id, kept["punch_in_seconds"], kept["punch_out_seconds"]
            ),
        )

    def covers_most_of(self, recording_id, punch_in, punch_out):
        if punch_in is None or punch_out is None:
            return False
        source = self.store.loads(Recording, recording_id)
        duration = None if source is None else source.duration_seconds
        if not duration:
            return False
        return (punch_out - punch_in) / duration > MOST_OF_THE_SOURCE


@dataclass(frozen=True)
class CorrectsBlockSummary:
    store: Store

    def __call__(self, block, text):
        evidence = block.evidence + (
            Evidence(
                timecode=block.start_seconds,
                finding=block.summary or "",
                implies="machine summary",
            ),
        )
        return self.store.saves(replace(block, summary=text, evidence=evidence))


def seeds_segment(block_type):
    return block_type in TEACHING
