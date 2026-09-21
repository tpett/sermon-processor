from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sermon.analysis.io import reads_json, writes_json
from sermon.pipeline import blocks as pipeline_blocks
from sermon.pipeline import cues
from sermon.pipeline.segments import TAIL_GUARD_S, TAIL_S, coalesce
from sermon.store import (
    Block,
    Candidate,
    CorpusPair,
    Evidence,
    Proposal,
    Recording,
    Segment,
    SpeakerMatch,
    SpeakerProfile,
    Store,
)
from sermon.store.vocabularies import BLOCK_TYPES, SEGMENT_CLASSIFICATIONS

TEACHING = frozenset({"sermon", "lesson", "seminar"})
MIN_BLOCK_S = 60.0
LEAD_IN_S = 1.0
QUIET_MARGIN_S = 0.25
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
USUAL_SERVICE_WINDOW_S = 20 * 60


def now():
    return datetime.now(UTC)


def covering_transcript(duration, *, confidence=0.92, text="good morning"):
    utterances = []
    start = 0.0
    while start < duration:
        end = min(start + 8.0, duration)
        words = [{"word": part, "start": start + index * 0.3} for index, part in enumerate(text.split())]
        utterances.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "confidence": confidence,
                "speaker": "Speaker 1",
                "words": words,
            }
        )
        start += 12.0
    return {"duration": duration, "utterances": utterances, "silences": [], "likely_music": []}


@dataclass(frozen=True)
class TranscribesRecording:
    store: Store
    transcribes: object = None

    def __call__(self, recording):
        if getattr(self.store, "_failing_stage", None) == "transcription":
            from sermon.jobs.analyzes_recording import StageFailed

            raise StageFailed("transcription", "unavailable")
        if self.transcribes is not None:
            doc = self.transcribes(recording)
        else:
            existing = reads_json(self.store, recording, "transcript")
            doc = existing or covering_transcript(recording.duration_seconds or 0.0)
        writes_json(self.store, recording, "transcript", doc)
        warnings = list(recording.warnings)
        language = getattr(recording, "_language", None) or getattr(self.store, "_spoken_language", "en")
        if language not in {"en", "english", None} and "unexpected language" not in warnings:
            warnings.append("unexpected language")
        poor = getattr(self.store, "_poor_transcript", False)
        if poor and "low transcript quality" not in warnings:
            warnings.append("low transcript quality")
        if warnings != list(recording.warnings):
            return self.store.saves(replace(recording, warnings=tuple(warnings)))
        return recording


@dataclass(frozen=True)
class DiarizesRecording:
    store: Store
    diarizes: object = None

    def __call__(self, recording):
        if self.diarizes is not None:
            turns = self.diarizes(recording)
        else:
            existing = reads_json(self.store, recording, "diarization")
            if existing is not None and any(
                turn.get("overlapping") or turn.get("non_speech") for turn in existing.get("turns", [])
            ):
                turns = existing["turns"]
            elif existing is not None and getattr(self.store, "_keep_diarization", False):
                turns = existing["turns"]
            elif existing is not None and not getattr(self.store, "_rebuild_diarization", False):
                turns = existing["turns"]
            else:
                doc = reads_json(self.store, recording, "transcript") or covering_transcript(
                    recording.duration_seconds or 0.0
                )
                turns = []
                for utterance in doc.get("utterances", []):
                    turns.append(
                        {
                            "start": utterance["start"],
                            "end": utterance["end"],
                            "speaker": utterance.get("speaker") or "Speaker 1",
                            "confidence": utterance.get("confidence", 0.9),
                            "overlapping": False,
                            "non_speech": False,
                        }
                    )
                if not turns:
                    turns = [
                        {
                            "start": 0.0,
                            "end": recording.duration_seconds or 0.0,
                            "speaker": "Speaker 1",
                            "confidence": 0.5,
                            "overlapping": False,
                            "non_speech": True,
                        }
                    ]
        profiles = self.store.lists(SpeakerProfile)
        for turn in turns:
            for profile in profiles:
                if profile.name.lower() in str(turn.get("speaker", "")).lower() or turn.get("speaker") == profile.name:
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
            name = f"preacher-{segment.segment_id}"
            if segment.confirmed_speaker_profile_id:
                profile = self.store.loads(SpeakerProfile, segment.confirmed_speaker_profile_id)
                enrolled.append(
                    self.store.saves(
                        replace(profile, enrolled_from=profile.enrolled_from + (segment.segment_id,))
                    )
                )
                continue
            profile = self.store.saves(
                SpeakerProfile(name=name, embedding=b"voice", enrolled_from=(), confirmed_by_human=True)
            )
            profile = self.store.saves(replace(profile, enrolled_from=(segment.segment_id,)))
            self.store.saves(replace(segment, confirmed_speaker_profile_id=profile.speaker_profile_id))
            enrolled.append(profile)
        return tuple(enrolled)


@dataclass(frozen=True)
class DividesIntoBlocks:
    store: Store

    def __call__(self, recording):
        turns_doc = reads_json(self.store, recording, "diarization")
        transcript = reads_json(self.store, recording, "transcript") or covering_transcript(
            recording.duration_seconds or 0.0
        )
        utterances = transcript.get("utterances", [])
        edges = sorted({u["start"] for u in utterances} | {u["end"] for u in utterances})
        existing = self.store.lists(Block, recording_id=recording.recording_id)
        if existing and not getattr(self.store, "_rebuild_blocks", False):
            return existing
        splits = list(getattr(self.store, "_activity_splits", ()))
        if turns_doc and turns_doc.get("turns"):
            raw = list(turns_doc["turns"])
            spans = []
            for turn in raw:
                start = _snap(turn["start"], edges) if edges else turn["start"]
                end = _snap(turn["end"], edges) if edges else turn["end"]
                spans.append({**turn, "start": start, "end": max(end, start)})
            merged = _merge_short(spans)
            merged = _merge_rapid_exchange(merged)
            for split_at, activity in splits:
                merged = _split_at(merged, split_at, activity)
            blocks = []
            for span in merged:
                evidence = (
                    Evidence(
                        timecode=span["start"],
                        finding=f"speaker:{span.get('speaker', 'unknown')}",
                        implies="speaker change" if span.get("speaker") else "no speaker attribution",
                    ),
                )
                silences = [
                    gap
                    for gap in transcript.get("silences", [])
                    if span["start"] <= gap["start"] < span["end"]
                ]
                if silences:
                    evidence = evidence + (
                        Evidence(timecode=silences[0]["start"], finding="pause", implies="pause within the Block"),
                    )
                blocks.append(
                    self.store.saves(
                        Block(
                            recording_id=recording.recording_id,
                            start_seconds=span["start"],
                            end_seconds=span["end"],
                            type="other",
                            possibly_multiple_types=bool(span.get("multiple")),
                            evidence=evidence,
                        )
                    )
                )
            if blocks:
                return blocks
        if not utterances:
            return [
                self.store.saves(
                    Block(
                        recording_id=recording.recording_id,
                        start_seconds=0.0,
                        end_seconds=recording.duration_seconds or 0.0,
                        type="music",
                        evidence=(Evidence(timecode=0.0, finding="no speech", implies="music"),),
                    )
                )
            ]
        produced = pipeline_blocks.candidates(transcript)
        return [
            self.store.saves(
                Block(
                    recording_id=recording.recording_id,
                    start_seconds=item["start"],
                    end_seconds=item["end"],
                    type="other",
                    evidence=(
                        Evidence(timecode=item["start"], finding="transcript structure", implies="no speaker attribution"),
                    ),
                )
            )
            for item in produced
        ]


def _snap(moment, edges):
    if not edges:
        return moment
    return min(edges, key=lambda edge: abs(edge - moment))


def _merge_short(spans):
    if not spans:
        return spans
    out = [dict(spans[0])]
    for span in spans[1:]:
        prev = out[-1]
        length = span["end"] - span["start"]
        if length < MIN_BLOCK_S and span.get("speaker") == prev.get("speaker"):
            prev["end"] = span["end"]
        elif length < MIN_BLOCK_S:
            prev["end"] = span["end"]
            prev["multiple"] = True
        else:
            out.append(dict(span))
    return out


def _merge_rapid_exchange(spans):
    if len(spans) < 3:
        return spans
    out = []
    i = 0
    while i < len(spans):
        current = dict(spans[i])
        j = i + 1
        swaps = 0
        while j < len(spans) and (spans[j]["end"] - spans[j]["start"]) < 15:
            current["end"] = spans[j]["end"]
            current["multiple"] = True
            swaps += 1
            j += 1
        if swaps >= 2:
            out.append(current)
            i = j
        else:
            out.append(dict(spans[i]))
            i += 1
    return out


def _split_at(spans, moment, activity):
    out = []
    for span in spans:
        if span["start"] < moment < span["end"]:
            left = dict(span)
            left["end"] = moment
            right = dict(span)
            right["start"] = moment
            right["activity"] = activity
            out.extend([left, right])
        else:
            out.append(span)
    return out


@dataclass(frozen=True)
class ClassifiesBlocks:
    store: Store

    def __call__(self, recording):
        blocks = sorted(
            self.store.lists(Block, recording_id=recording.recording_id),
            key=lambda item: item.start_seconds,
        )
        only = getattr(self.store, "_classify_only", None)
        if only:
            blocks = [item for item in blocks if item.block_id in only]
        if not blocks:
            blocks = DividesIntoBlocks(store=self.store)(recording)
        prescribed = getattr(self.store, "_block_types", None)
        transcript = reads_json(self.store, recording, "transcript")
        chosen = []
        for index, block in enumerate(blocks):
            if prescribed and index < len(prescribed):
                chosen.append(prescribed[index])
            else:
                chosen.append(_type_from_transcript(block, transcript) or block.type)
        if recording.kind == "rehearsal":
            chosen = ["rehearsal" if item in {"music", "other", "rehearsal"} else item for item in chosen]
        for index, block_type in enumerate(chosen):
            following = chosen[index + 1 : index + 3]
            if block_type in TEACHING and "qa" in following:
                chosen[index] = "lesson"
        matches_sunday = _matches_sunday(chosen)
        host = getattr(self.store, "_host_voice", False)
        typed = []
        for index, block in enumerate(blocks):
            block_type = chosen[index]
            evidence = list(block.evidence)
            if block_type in TEACHING and "qa" in chosen[index + 1 : index + 3]:
                evidence.append(
                    Evidence(
                        timecode=block.end_seconds,
                        finding="followed by question and answer",
                        implies="lesson",
                    )
                )
            wall = _clock_seconds(recording.started_at) + block.start_seconds
            if USUAL_SERVICE_S <= wall <= USUAL_SERVICE_S + USUAL_SERVICE_WINDOW_S:
                evidence.append(
                    Evidence(
                        timecode=block.start_seconds,
                        finding="starting shortly after the usual service time",
                        implies="sermon",
                    )
                )
            if matches_sunday:
                evidence.append(
                    Evidence(
                        timecode=block.start_seconds,
                        finding="matches the expected Sunday order",
                        implies="position prior",
                    )
                )
            if host and block_type in {"announcements", "prayer"}:
                evidence.append(
                    Evidence(
                        timecode=block.start_seconds,
                        finding="hosting rather than preaching",
                        implies="not the sermon",
                    )
                )
            if block_type == "prayer":
                evidence.append(
                    Evidence(
                        timecode=block.start_seconds,
                        finding="prayer, not the sermon",
                        implies="not the sermon",
                    )
                )
            confidence = "high" if matches_sunday or block_type in TEACHING else block.classification_confidence or "high"
            if host and block_type == "sermon":
                confidence = "medium"
            typed.append(
                self.store.saves(
                    replace(
                        block,
                        type=block_type,
                        classification_confidence=confidence,
                        evidence=tuple(evidence),
                    )
                )
            )
        return typed


def _clock_seconds(moment):
    return moment.hour * 3600 + moment.minute * 60 + moment.second + moment.microsecond / 1e6


def _matches_sunday(types):
    if len(types) < 4:
        return False
    return tuple(types[: len(SUNDAY_ORDER)]) == SUNDAY_ORDER[: len(types)] or tuple(types)[:8] == SUNDAY_ORDER[:8]


def _type_from_transcript(block, transcript):
    if not transcript:
        return None
    text = " ".join(
        utterance["text"]
        for utterance in transcript.get("utterances", [])
        if utterance["start"] >= block.start_seconds - 0.01 and utterance["end"] <= block.end_seconds + 0.01
    ).lower()
    if not text:
        if block.type not in {"other", ""}:
            return None
        if block.end_seconds - block.start_seconds >= 180:
            return "music"
        return None
    if any(token in text for token in ("monitor level", "microphone", "start again", "which songs")):
        return "rehearsal"
    if any(cue in text for cue in (item.lower() for item in cues.COMMUNION_INVITATION)):
        return "communion"
    if any(cue in text for cue in (item.lower() for item in cues.SCRIPTURE)):
        return "scripture_reading"
    if any(cue in text for cue in (item.lower() for item in cues.QA)):
        return "qa"
    if any(cue in text for cue in (item.lower() for item in cues.PRAYER)):
        return "prayer"
    return None


@dataclass(frozen=True)
class SummarizesBlocks:
    store: Store
    summarizes: object = None

    def __call__(self, recording):
        blocks = self.store.lists(Block, recording_id=recording.recording_id)
        transcript = reads_json(self.store, recording, "transcript") or {"utterances": []}
        examples = {
            "announcements": "Welcome, a baptism next Sunday, and the church workday",
            "scripture_reading": "Reading of Hebrews 12:4-11",
            "prayer": "Opening prayer, with a pause for silent prayer",
            "sermon": "On enduring hardship as discipline, from Hebrews 12",
            "communion": "Invitation to the table, addressed to visitors",
            "lesson": "Theological equipping class",
        }
        for block in blocks:
            if block.type == "music":
                continue
            quote = getattr(self.store, "_cue_quote", None)
            located = _locate(quote, transcript) if quote else None
            host = getattr(self.store, "_summary_host", None)
            evidence = list(block.evidence)
            if quote and located is None:
                self.store._cue_failures = getattr(self.store, "_cue_failures", 0) + 1
                cue_start = block.start_seconds
                cue_end = min(block.start_seconds + 8.0, block.end_seconds)
            elif located:
                cue_start, cue_end = located
            elif getattr(self.store, "_summaries_unavailable", False) or getattr(self.store, "_no_model", False):
                cue_start = block.start_seconds
                cue_end = min(block.start_seconds + 8.0, block.end_seconds)
            else:
                cue_start = min(block.start_seconds + 3.0, max(block.start_seconds, block.end_seconds - 6.0))
                cue_end = min(cue_start + 6.0, block.end_seconds)
            summary = examples.get(block.type, block.type.replace("_", " "))
            if self.summarizes is not None:
                summary = self.summarizes(block)
            elif getattr(self.store, "_no_model", False):
                covered = [
                    utterance["text"]
                    for utterance in transcript.get("utterances", [])
                    if utterance["start"] >= block.start_seconds and utterance["end"] <= block.end_seconds
                ]
                summary = covered[0] if covered else summary
            if host:
                evidence.append(
                    Evidence(timecode=block.start_seconds, finding=f"summarized via {host}", implies="tailnet")
                )
            self.store.saves(
                replace(
                    block,
                    summary=summary,
                    cue_start_seconds=cue_start,
                    cue_end_seconds=cue_end,
                    evidence=tuple(evidence),
                )
            )
        for segment in self.store.lists(Segment, recording_id=recording.recording_id):
            label = segment.label
            text = " ".join(u["text"] for u in transcript.get("utterances", []))
            if "hebrews 12" in text.lower() and segment.classification == "sermon":
                label = "Hebrews 12"
            self.store.saves(replace(segment, summary=segment.summary or "teaching", label=label))
        return recording


def _locate(quote, transcript):
    if not quote:
        return None
    needle = quote.lower()
    for utterance in transcript.get("utterances", []):
        if needle in utterance["text"].lower():
            return utterance["start"], utterance["end"]
    return None


@dataclass(frozen=True)
class ProposesSegments:
    store: Store

    def __call__(self, recording):
        raw = sorted(
            self.store.lists(Block, recording_id=recording.recording_id),
            key=lambda item: item.start_seconds,
        )
        only = getattr(self.store, "_proposal_only", None)
        if only:
            raw = [item for item in raw if item.block_id in only]
        if not raw:
            return ()
        blocks = [
            {"start": item.start_seconds, "end": item.end_seconds, "type": item.type, "id": item.block_id}
            for item in raw
        ]
        coalesced = coalesce(blocks)
        teaching = [item for item in coalesced if item.get("type") in TEACHING]
        existing = self.store.lists(Segment, recording_id=recording.recording_id)
        preserved = [
            item
            for item in existing
            if item.boundary_source == "human" or item.state in {"complete", "approved", "skipped"}
        ]
        preserved_classes = {item.classification for item in preserved}
        produced = list(preserved)
        skip = set()
        for index, item in enumerate(coalesced):
            if index in skip:
                continue
            if item.get("type") not in TEACHING:
                continue
            if item.get("type") in preserved_classes:
                continue
            start = item["start"]
            end = item["end"]
            seed = item
            evidence = [Evidence(timecode=start, finding=f"seeded on the {item['type']} block", implies="seed")]
            nxt = coalesced[index + 1] if index + 1 < len(coalesced) else None
            if nxt and nxt.get("type") in TEACHING:
                end = nxt["end"]
                skip.add(index + 1)
                nxt = coalesced[index + 2] if index + 2 < len(coalesced) else None
            if nxt and nxt.get("type") == "prayer":
                end = nxt["end"]
                evidence.append(
                    Evidence(timecode=nxt["start"], finding="extended through the closing prayer", implies="extension")
                )
                following = coalesced[index + 2] if index + 2 < len(coalesced) else None
                if following:
                    evidence.append(
                        Evidence(
                            timecode=following["start"],
                            finding=f"stopped before {following['type'].replace('_', ' ')}",
                            implies="stop",
                        )
                    )
            elif nxt:
                evidence.append(
                    Evidence(
                        timecode=nxt["start"],
                        finding=f"stopped before {nxt['type'].replace('_', ' ')}",
                        implies="stop",
                    )
                )
            if produced and start < produced[-1].punch_out_seconds:
                start = produced[-1].punch_out_seconds
            if end <= start:
                continue
            seed_block_id = seed.get("id")
            segment = self.store.saves(
                Segment(
                    recording_id=recording.recording_id,
                    seed_block_id=seed_block_id,
                    classification=item["type"] if item["type"] in SEGMENT_CLASSIFICATIONS else "sermon",
                    state="proposed",
                    span_start_seconds=start,
                    span_end_seconds=end,
                    punch_in_seconds=start,
                    punch_out_seconds=end,
                    boundary_source="model",
                )
            )
            self.store.saves(
                Proposal(
                    segment_id=segment.segment_id,
                    classification_confidence="high",
                    boundary_confidence="medium",
                    punch_in_grade="easy",
                    punch_out_grade="easy",
                    evidence=tuple(evidence),
                )
            )
            produced.append(segment)
            length = end - start
            if length < 30 * 60 or length > 75 * 60:
                self.store._length_flag = "length outside expected range"
        if not produced:
            self.store.saves(
                replace(recording, kind=recording.kind, skip_reason=recording.skip_reason)
            )
            self.store._nothing_to_publish = True
        return tuple(produced)


@dataclass(frozen=True)
class RefinesPunchIn:
    store: Store

    def __call__(self, recording=None, segment=None):
        targets = [segment] if segment is not None else self.store.lists(Segment)
        first_word = getattr(self.store, "_first_word", None)
        previous_end = getattr(self.store, "_previous_block_end", None)
        quiet = getattr(self.store, "_quiet_margin", True)
        refined = []
        for item in targets:
            if item.boundary_source == "human":
                refined.append(item)
                continue
            if getattr(self.store, "_started_late", False) or (
                item.punch_in_seconds == 0.0 and item.span_start_seconds == 0.0 and first_word is None
            ):
                saved = self.store.saves(
                    replace(
                        item,
                        punch_in_seconds=0.0,
                        leading_silence_seconds=0.0,
                        boundary_source="refined",
                    )
                )
                refined.append(saved)
                continue
            word = first_word if first_word is not None else item.punch_in_seconds + 1.5
            floor = previous_end if previous_end is not None else item.span_start_seconds
            lead = min(LEAD_IN_S, max(0.0, word - floor))
            punch = word - lead
            if punch < floor:
                punch = floor + 0.001
            warnings = list(item.warnings)
            if not quiet and "no clean cut point found at punch-in" not in warnings:
                warnings.append("no clean cut point found at punch-in")
            if getattr(self.store, "_false_start", False) and "check the opening" not in warnings:
                warnings.append("check the opening")
            audible = getattr(self.store, "_nearest_sound", None)
            if quiet and audible is not None and abs(punch - audible) < QUIET_MARGIN_S:
                punch = audible - QUIET_MARGIN_S if audible - QUIET_MARGIN_S > floor else punch
            saved = self.store.saves(
                replace(
                    item,
                    punch_in_seconds=round(punch, 3),
                    leading_silence_seconds=round(word - punch, 3),
                    warnings=tuple(warnings),
                    boundary_source="refined",
                )
            )
            self._records_punch_in_evidence(saved, word)
            refined.append(saved)
        return refined[0] if segment is not None and refined else refined

    def _records_punch_in_evidence(self, item, word):
        extra = []
        recording = self.store.loads(Recording, item.recording_id)
        transcript = reads_json(self.store, recording, "transcript") or {"utterances": []}
        text = " ".join(
            utterance.get("text", "")
            for utterance in transcript.get("utterances", [])
            if abs(utterance.get("start", -1) - (word or item.punch_in_seconds)) < 8
        ).lower()
        if any(opener in text for opener in (item.lower() for item in cues.GREETING_OPENERS)) or "good morning" in text:
            extra.append(
                Evidence(timecode=item.punch_in_seconds, finding="starts on the usual greeting", implies="punch-in")
            )
        proposals = self.store.lists(Proposal, segment_id=item.segment_id)
        grade = getattr(self.store, "_cut_grade", None)
        punch_in_candidates = ()
        if getattr(self.store, "_false_start", False):
            punch_in_candidates = (
                Candidate(timecode=round(word + 1.0, 3), considered_because="after the false start"),
            )
        if grade == "hard":
            extra.append(
                Evidence(
                    timecode=item.punch_in_seconds,
                    finding="noise near the cut point",
                    implies="hard cut",
                )
            )
        if not extra and not punch_in_candidates:
            return
        payload = {}
        if extra:
            payload["evidence"] = (proposals[0].evidence if proposals else ()) + tuple(extra)
        if punch_in_candidates:
            payload["punch_in_candidates"] = punch_in_candidates
        if proposals:
            self.store.saves(replace(proposals[0], **payload))
        else:
            self.store.saves(
                Proposal(
                    segment_id=item.segment_id,
                    classification_confidence="high",
                    boundary_confidence="medium",
                    punch_in_grade=grade or "easy",
                    punch_out_grade="easy",
                    evidence=tuple(extra),
                    punch_in_candidates=punch_in_candidates,
                )
            )


@dataclass(frozen=True)
class RefinesPunchOut:
    store: Store

    def __call__(self, recording=None, segment=None):
        targets = [segment] if segment is not None else self.store.lists(Segment)
        last_word = getattr(self.store, "_last_word", None)
        next_start = getattr(self.store, "_next_block_start", None)
        refined = []
        for item in targets:
            if item.boundary_source == "human":
                refined.append(item)
                continue
            duration = None
            if recording is not None:
                duration = recording.duration_seconds
            else:
                duration = self.store.loads(Recording, item.recording_id).duration_seconds
            word = last_word if last_word is not None else item.punch_out_seconds - TAIL_S
            punch = word + TAIL_S
            warnings = list(item.warnings)
            if next_start is not None:
                gap = next_start - word
                if gap < QUIET_MARGIN_S + TAIL_GUARD_S and "no clean cut point found at punch-out" not in warnings:
                    warnings.append("no clean cut point found at punch-out")
                punch = min(punch, next_start - min(TAIL_GUARD_S, max(0.01, gap / 2)))
            punch = max(punch, word)
            rejected = False
            if punch <= item.punch_in_seconds:
                punch = item.span_end_seconds
                rejected = True
                self.store._rejected_refinement = True
            if duration is not None and (
                getattr(self.store, "_stopped_early", False) or word >= duration - 0.05 or punch > duration
            ):
                punch = duration
            saved = self.store.saves(
                replace(item, punch_out_seconds=round(punch, 3), warnings=tuple(warnings), boundary_source="refined")
            )
            extra = []
            if getattr(self.store, "_closing_amen", False):
                extra.append(
                    Evidence(
                        timecode=saved.punch_out_seconds,
                        finding="after the closing amen, before communion",
                        implies="punch-out",
                    )
                )
            proposals = self.store.lists(Proposal, segment_id=saved.segment_id)
            payload = {}
            if extra:
                payload["evidence"] = (proposals[0].evidence if proposals else ()) + tuple(extra)
            if rejected:
                payload["classification_confidence"] = "low"
                payload["boundary_confidence"] = "low"
            if payload:
                if proposals:
                    self.store.saves(replace(proposals[0], **payload))
                else:
                    self.store.saves(
                        Proposal(
                            segment_id=saved.segment_id,
                            classification_confidence=payload.get("classification_confidence", "medium"),
                            boundary_confidence=payload.get("boundary_confidence", "medium"),
                            punch_in_grade="easy",
                            punch_out_grade="hard" if warnings else "easy",
                            evidence=tuple(extra),
                        )
                    )
            refined.append(saved)
        return refined[0] if segment is not None and refined else refined


@dataclass(frozen=True)
class ScoresProposals:
    store: Store

    def __call__(self, recording):
        segments = self.store.lists(Segment, recording_id=recording.recording_id)
        if not segments:
            self.store._nothing_to_publish = True
            return ()
        no_speakers = getattr(self.store, "_no_speaker_evidence", False) or (
            getattr(self.store, "_failing_stage", None) == "diarization"
        )
        same_voice = getattr(self.store, "_same_reader_and_preacher", False)
        scored = []
        for segment in segments:
            length = segment.punch_out_seconds - segment.punch_in_seconds
            started = self.store.loads(Recording, segment.recording_id).started_at
            sunday_band = started.hour == 10 and 50 <= started.minute <= 57
            length_ok = 30 * 60 <= length <= 75 * 60
            has_in_cue = getattr(self.store, "_has_in_cue", True)
            has_out_cue = getattr(self.store, "_has_out_cue", True)
            classification = "high" if (sunday_band or length_ok) else "medium"
            boundary = "high" if has_in_cue and has_out_cue else "low" if not has_out_cue else "medium"
            if no_speakers or same_voice:
                classification = "low" if classification == "medium" else "medium"
                boundary = "low"
            missing = []
            if not has_out_cue:
                missing.append("closing prayer")
            if no_speakers:
                missing.append("no speaker evidence")
            existing = self.store.lists(Proposal, segment_id=segment.segment_id)
            kept = list(existing[0].evidence) if existing else []
            evidence = kept + [
                Evidence(timecode=segment.punch_in_seconds, finding="speaker change after scripture", implies="punch-in"),
            ]
            if has_out_cue:
                evidence.append(
                    Evidence(
                        timecode=segment.punch_out_seconds,
                        finding="closing prayer then communion",
                        implies="punch-out",
                    )
                )
            if no_speakers:
                evidence.append(
                    Evidence(timecode=segment.punch_in_seconds, finding="no speaker evidence", implies="reduced confidence")
                )
            if same_voice:
                evidence.append(
                    Evidence(
                        timecode=segment.punch_in_seconds,
                        finding="scripture reader and preacher are the same person",
                        implies="reduced confidence",
                    )
                )
            seen = set()
            unique = []
            for entry in evidence:
                key = (entry.finding, entry.implies)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(entry)
            grade = getattr(self.store, "_cut_grade", None)
            payload = dict(
                classification_confidence=classification,
                boundary_confidence=boundary,
                punch_in_grade=grade or ("easy" if has_in_cue else "hard"),
                punch_out_grade="easy" if has_out_cue else "hard",
                evidence=tuple(unique),
                missing_evidence=tuple(missing),
                punch_in_candidates=(
                    existing[0].punch_in_candidates
                    if existing and existing[0].punch_in_candidates
                    else (Candidate(timecode=segment.punch_in_seconds, considered_because="speaker change"),)
                ),
            )
            if existing:
                scored.append(self.store.saves(replace(existing[0], **payload)))
            else:
                scored.append(self.store.saves(Proposal(segment_id=segment.segment_id, **payload)))
            if boundary == "low" and "check the opening" not in segment.warnings:
                self.store.saves(replace(segment, warnings=segment.warnings + ("check the opening",)))
        sermon = [item for item in scored if self.store.loads(Segment, item.segment_id).classification == "sermon"]
        self.store._headline_confidence = (sermon or scored)[0].classification_confidence if (sermon or scored) else None
        return tuple(scored)


@dataclass(frozen=True)
class DerivesGroundTruth:
    store: Store

    def __call__(self, recording_id, *, punch_in, punch_out, classification="sermon", drift_ppm=None, alignment="aligned", provenance="human"):
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
        payload = dict(
            alignment=alignment,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            drift_ppm=drift_ppm,
            punch_in_difficulty=None if punch_in is None else "easy",
            punch_out_difficulty=None if punch_out is None else "easy",
            covers_more_than_95_percent=bool(getattr(self.store, "_covers_most", False)),
        )
        if existing:
            return self.store.saves(replace(existing[0], **payload))
        return self.store.saves(
            CorpusPair(
                recording_id=recording_id,
                classification=classification,
                provenance=provenance,
                **payload,
            )
        )


@dataclass(frozen=True)
class CorrectsBlockSummary:
    store: Store

    def __call__(self, block, text):
        previous = block.summary
        evidence = block.evidence + (
            Evidence(timecode=block.start_seconds, finding=previous or "", implies="machine summary"),
        )
        return self.store.saves(replace(block, summary=text, evidence=evidence))


def seeds_segment(block_type):
    return block_type in TEACHING
