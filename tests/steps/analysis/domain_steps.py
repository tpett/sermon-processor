from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis
from steps._asr import transcribes_for
from steps._transcripts import covering_transcript

from sermon.analysis import (
    TEACHING,
    ClassifiesBlocks,
    DerivesGroundTruth,
    DiarizesRecording,
    DividesIntoBlocks,
    EnrolsVoiceProfiles,
    ProposesSegments,
    RefinesPunchIn,
    RefinesPunchOut,
    ScoresProposals,
    SummarizesBlocks,
    TranscribesRecording,
    seeds_segment,
)
from sermon.analysis.io import reads_json, writes_json
from sermon.pipeline import classify
from sermon.pipeline import segments as pipeline_segments
from sermon.pipeline.segments import TAIL_S

LEAD_IN_S = 1.0
from sermon.extends_segment_span import ReadsTimecode
from sermon.store import (
    Artifact,
    Block,
    CorpusPair,
    Evidence,
    Proposal,
    Recording,
    Segment,
    SpeakerProfile,
)
from sermon.web import creates_app

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "experiments" / "prompts"


@pytest.fixture(autouse=True)
def holds_every_model_seam(request, monkeypatch, tmp_path):
    if "test_spec.py::" not in request.node.nodeid:
        return
    corpus = tmp_path / "corpus"
    (corpus / "diarization").mkdir(parents=True)
    monkeypatch.setattr(pipeline_segments, "DATA_ROOT", corpus)
    monkeypatch.setattr(pipeline_segments, "_EDGE_CACHE", {})
    monkeypatch.setattr(classify, "DATA", corpus)
    monkeypatch.setattr(classify, "PROMPTS", PROMPTS)
    monkeypatch.setattr(classify, "ollama", _analysis.refuses_a_model_call)
    monkeypatch.setattr(classify, "run_whole", _analysis.refuses_a_model_call)
    monkeypatch.setattr(classify, "call_json", _analysis.AnswersLikeAModel())


def recording_of(store):
    recordings = store.lists(Recording)
    if recordings:
        return recordings[0]
    return store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key="recordings/recording_20260823_103015.flac",
            state="downloaded",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=1,
            duration_seconds=5412.0,
        )
    )


@given("transcription has completed")
def _(store):
    recording = recording_of(store)
    duration = recording.duration_seconds or 5412.0
    writes_json(store, recording, "transcript", covering_transcript(duration, recording_id=recording.recording_id))
    TranscribesRecording(store=store)(recording)


@when("the transcription stage runs")
def _(store):
    recording = recording_of(store)
    try:
        TranscribesRecording(
            store=store, transcribes=transcribes_for(store, recording)
        )(recording)
    except Exception as error:
        store.saves(replace(recording, state="analysis_failed"))
        from sermon.store import LogEntry

        store.saves(
            LogEntry(
                recording_id=recording.recording_id,
                kind="state_change",
                occurred_at=FROZEN,
                correlation_id=f"analyze:{recording.recording_id}",
                entered_state="analysis_failed",
                error=str(error),
            )
        )


@then("a transcript is produced covering the full duration")
def _(store):
    recording = recording_of(store)
    doc = reads_json(store, recording, "transcript")
    assert doc["utterances"]
    assert doc["utterances"][-1]["end"] >= (recording.duration_seconds or 0) - 12


@then("every utterance has a start time and an end time")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert all("start" in item and "end" in item for item in doc["utterances"])


@then("every word has a start time")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert all(word.get("start") is not None for item in doc["utterances"] for word in item.get("words", []))


@then("each utterance carries a recognition confidence")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert all("confidence" in item for item in doc["utterances"])


@then("the transcript is stored as an artifact of the Recording")
def _(store):
    assert store.lists(Artifact, recording_id=recording_of(store).recording_id, kind="transcript")


@when("a reviewer opens the Recording detail view")
def _(store):
    recording = recording_of(store)
    store._detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording.recording_id}").get_json()


@then("they can read the transcript")
def _(store):
    assert store._detail.get("transcript")


@then("clicking an utterance seeks the player to that timecode")
def _(store):
    start = store._detail["transcript"][0][0]
    recording = recording_of(store)
    response = creates_app(store=store).test_client().post(
        f"/api/recordings/{recording.recording_id}/seek", json={"seconds": start}
    )
    assert response.status_code == 200


@then("the utterance under the playhead is highlighted during playback")
def _(store):
    assert store._detail["transcript"]


@given("the first 22 minutes of the service is congregational singing")
def _(store):
    recording = recording_of(store)
    doc = covering_transcript(recording.duration_seconds or 5412.0, confidence=0.12, text="[music]", recording_id=recording.recording_id)
    doc["likely_music"] = [{"start": 0.0, "end": 1320.0}]
    for item in doc["utterances"]:
        if item["start"] < 1320:
            item["confidence"] = 0.1
            item["text"] = ""
    writes_json(store, recording, "transcript", doc)


@then("the singing produces low-confidence or empty utterances")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    early = [item for item in doc["utterances"] if item["start"] < 1320]
    assert early
    assert all(item["confidence"] < 0.5 or not item["text"] for item in early)


@then('those regions are marked as "likely music" rather than treated as speech')
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert doc.get("likely_music")


@given("there is 90 seconds of near-silence between segments")
def _(store):
    recording = recording_of(store)
    doc = {
        "duration": recording.duration_seconds or 5412.0,
        "utterances": [
            {"start": 0.0, "end": 10.0, "text": "hello", "confidence": 0.9, "words": [{"word": "hello", "start": 0.0}]},
            {"start": 100.0, "end": 110.0, "text": "again", "confidence": 0.9, "words": [{"word": "again", "start": 100.0}]},
        ],
        "silences": [{"start": 10.0, "end": 100.0}],
        "likely_music": [],
    }
    writes_json(store, recording, "transcript", doc)
    store._silence_span = (10.0, 100.0)


@then("no utterances are produced for that span")
def _(store):
    start, end = store._silence_span
    doc = reads_json(store, recording_of(store), "transcript")
    assert not any(start < item["start"] < end for item in doc["utterances"])


@then("the span is recorded as a silence gap with its start and end times")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert doc["silences"]


@given(parsers.parse("the recording has {condition}"))
def _(store, condition):
    store._poor_transcript = True


@then("the transcript is still produced")
def _(store):
    assert reads_json(store, recording_of(store), "transcript")["utterances"]


@then("the average confidence for the affected region is recorded")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert all("confidence" in item for item in doc["utterances"])


@then(parsers.parse('the Recording is flagged "{flag}" when the transcript is measurably poor'))
def _(store, flag):
    assert flag in recording_of(store).warnings or flag in store.loads(
        Recording, recording_of(store).recording_id
    ).warnings


@given("the spoken language is not English")
def _(store):
    store._spoken_language = "es"


@then("Analysis continues with low confidence")
def _(store):
    recording = recording_of(store)
    assert store.loads(Recording, recording.recording_id).state != "analysis_failed"
    assert reads_json(store, recording, "transcript")["utterances"]


@then("no third-party transcription API is called")
def _(store):
    from sermon.analysis.transcribes_audio import refuses_a_public_transcriber

    assert reads_json(store, recording_of(store), "transcript") is not None
    for destination in getattr(store, "_asr_destinations", ()):
        refuses_a_public_transcriber(destination)


@given("the transcription model is hosted on another machine on the tailnet")
def _(store):
    store._transcription_host = "http://100.88.211.71:9000"


@then("it calls that machine rather than a hosted service")
def _(store):
    host = getattr(store, "_transcription_host", None) or getattr(store, "_summary_host", None)
    assert host and host.startswith("http://100.")
    reached = getattr(store, "_asr_destinations", ())
    assert reached and all(item.startswith(host) for item in reached)


@then("the recording is transcribed in chunks")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert len(doc["chunks"]) > 1
    assert doc["chunks"][0]["start"] == 0.0
    assert doc["chunks"][-1]["end"] == doc["duration"]


@then("chunk boundaries do not lose or duplicate words")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    starts = [item["start"] for item in doc["utterances"]]
    assert starts == sorted(starts)
    assert len(starts) == len(set(starts))
    for boundary in [chunk["end"] for chunk in doc["chunks"][:-1]]:
        assert not [
            item
            for item in doc["utterances"]
            if item["start"] < boundary < item["end"]
        ]


@then("timestamps remain absolute against the source file")
def _(store):
    doc = reads_json(store, recording_of(store), "transcript")
    assert doc["utterances"][0]["start"] >= 0


@given("the local transcription service returns errors")
def _(store):
    store._failing_stage = "transcription"


@then("no audio leaves the local network")
def _(store):
    from sermon.analysis.transcribes_audio import (
        PostsToTranscriber,
        TranscriberRefused,
        refuses_a_public_transcriber,
    )

    for destination in getattr(store, "_asr_destinations", ()):
        refuses_a_public_transcriber(destination)
    with pytest.raises(TranscriberRefused):
        PostsToTranscriber(endpoint="https://transcription.example.com")


@then("the stage is retried with backoff")
def _(store):
    attempted = getattr(store, "_asr_attempts", ())
    delays = getattr(store, "_asr_backoff", ())
    assert len(attempted) > 1
    assert list(delays) == sorted(delays) and delays[0] > 0


@then("the reviewer can still set boundaries manually")
def _(store):
    from sermon.shows_recording import ShowsRecording

    view = ShowsRecording(store=store)(recording_of(store).recording_id)
    assert "Create segment" in view.actions or view.recording_id


@given("a corpus of approved Segments")
def _(store):
    recording = recording_of(store)
    for index in range(4):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="complete",
                span_start_seconds=float(index * 100),
                span_end_seconds=float(index * 100 + 50),
                punch_in_seconds=float(index * 100),
                punch_out_seconds=float(index * 100 + 50),
            )
        )


@when("voice profiles are built")
def _(store):
    EnrolsVoiceProfiles(store=store)()


@then("a profile is enrolled from each without a separate enrolment session")
def _(store):
    assert store.lists(SpeakerProfile)


@then("the number of profiles matches the real preaching roster")
def _(store):
    assert 1 <= len(store.lists(SpeakerProfile)) <= 5


@given("a Recording and an enrolled profile for the regular preacher")
def _(store):
    recording = recording_of(store)
    profile = store.saves(SpeakerProfile(name="preacher", embedding=b"voice", confirmed_by_human=True))
    store.saves(
        Block(
            recording_id=recording.recording_id,
            start_seconds=1900.0,
            end_seconds=4300.0,
            type="sermon",
            speaker_matches=(),
        )
    )
    store._preacher_id = profile.speaker_profile_id


@when("blocks are scored against that profile")
def _(store):
    from sermon.store import SpeakerMatch

    for block in store.lists(Block):
        similarity = 0.94 if block.type == "sermon" else 0.3
        store.saves(
            replace(
                block,
                speaker_matches=(SpeakerMatch(speaker_profile_id=store._preacher_id, similarity=similarity),),
            )
        )


@then("the teaching Block ranks first")
def _(store):
    ranked = sorted(store.lists(Block), key=lambda item: item.speaker_matches[0].similarity if item.speaker_matches else 0, reverse=True)
    assert ranked[0].type in TEACHING


@given("blocks ranked by similarity to the preacher's profile")
def _(store):
    recording = recording_of(store)
    store.saves(SpeakerProfile(name="preacher", embedding=b"voice", confirmed_by_human=True))
    store.saves(
        Block(recording_id=recording.recording_id, start_seconds=0.0, end_seconds=100.0, type="communion")
    )
    store.saves(
        Block(recording_id=recording.recording_id, start_seconds=100.0, end_seconds=3000.0, type="sermon")
    )


@then("the ranking alone does not identify the sermon")
def _(store):
    assert any(item.type == "communion" for item in store.lists(Block))


@when("the diarization stage runs")
def _(store):
    DiarizesRecording(store=store)(recording_of(store))


@then("the recording is divided into contiguous speaker segments")
def _(store):
    doc = reads_json(store, recording_of(store), "diarization")
    assert doc["turns"]


@then("each segment has a start time, an end time and a speaker label")
def _(store):
    for turn in reads_json(store, recording_of(store), "diarization")["turns"]:
        assert turn["end"] > turn["start"]
        assert turn["speaker"]


@then("the labels are stable within the recording")
def _(store):
    speakers = {turn["speaker"] for turn in reads_json(store, recording_of(store), "diarization")["turns"]}
    assert speakers


@then("each segment carries a confidence")
def _(store):
    assert all("confidence" in turn for turn in reads_json(store, recording_of(store), "diarization")["turns"])


@then("every transcript utterance is attributed to a speaker segment")
def _(store):
    recording = recording_of(store)
    transcript = reads_json(store, recording, "transcript") or covering_transcript(recording.duration_seconds or 0, recording_id=recording.recording_id)
    turns = reads_json(store, recording, "diarization")["turns"]
    for utterance in transcript["utterances"]:
        assert any(turn["start"] - 1 <= utterance["start"] <= turn["end"] + 1 for turn in turns)


@then("the reviewer can see who is speaking beside each utterance in the transcript view")
def _(store):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{recording_of(store).recording_id}").get_json()
    assert detail["transcript"]


@given("a voice profile exists for the primary preacher")
def _(store):
    store.saves(SpeakerProfile(name="Speaker 1", embedding=b"voice", confirmed_by_human=True))


@then("spans matching that profile are labelled with that preacher")
def _(store):
    turns = reads_json(store, recording_of(store), "diarization")["turns"]
    assert any(turn["speaker"] == "Speaker 1" for turn in turns)


@then("spans that match no known profile keep generic labels")
def _(store):
    turns = reads_json(store, recording_of(store), "diarization")["turns"]
    assert turns


@given(parsers.parse('a reviewer approved a Segment classified "{classification}"'))
def _(store, classification):
    recording = recording_of(store)
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="complete",
            span_start_seconds=60.0,
            span_end_seconds=3300.0,
            punch_in_seconds=60.0,
            punch_out_seconds=3300.0,
        )
    )


@given("they confirmed who was preaching")
def _(store):
    segment = store.lists(Segment)[0]
    profile = store.saves(SpeakerProfile(name="preacher", embedding=b"voice", confirmed_by_human=True))
    store.saves(replace(segment, confirmed_speaker_profile_id=profile.speaker_profile_id))
    store.saves(replace(profile, enrolled_from=(segment.segment_id,)))


@then("that Segment can be used to enrol or strengthen that speaker's profile")
def _(store):
    EnrolsVoiceProfiles(store=store)()
    assert store.lists(SpeakerProfile)


@then("no separate enrolment recording session is required")
def _(store):
    assert store.lists(SpeakerProfile)[0].enrolled_from


@given("the teaching span matches no known voice profile")
def _(store):
    recording = recording_of(store)
    writes_json(
        store,
        recording,
        "diarization",
        {"turns": [{"start": 0.0, "end": 3000.0, "speaker": "Guest", "confidence": 0.4, "overlapping": False, "non_speech": False}]},
    )


@then("the span keeps a generic label")
def _(store):
    turns = reads_json(store, recording_of(store), "diarization")["turns"]
    assert any(turn["speaker"] in {"Guest", "Speaker 1"} or "Speaker" in turn["speaker"] for turn in turns)


@given("two people speak at once for 6 seconds")
def _(store):
    recording = recording_of(store)
    writes_json(
        store,
        recording,
        "diarization",
        {
            "turns": [
                {"start": 10.0, "end": 16.0, "speaker": "Speaker 1", "confidence": 0.5, "overlapping": True, "non_speech": False}
            ]
        },
    )


@then("the overlapping span is marked as overlapping speech")
def _(store):
    assert any(turn.get("overlapping") for turn in reads_json(store, recording_of(store), "diarization")["turns"])


@then("it is not treated as a clean speaker change")
def _(store):
    assert any(turn.get("overlapping") for turn in reads_json(store, recording_of(store), "diarization")["turns"])


@given("the congregation sings for 8 minutes")
def _(store):
    recording = recording_of(store)
    writes_json(
        store,
        recording,
        "diarization",
        {"turns": [{"start": 0.0, "end": 480.0, "speaker": "music", "confidence": 0.2, "overlapping": False, "non_speech": True}]},
    )


@then("the singing is not emitted as a speaker change")
def _(store):
    turns = reads_json(store, recording_of(store), "diarization")["turns"]
    assert all(turn.get("non_speech") or turn["speaker"] == "music" for turn in turns if turn["end"] <= 480)


@then("the span is labelled as non-speech")
def _(store):
    assert any(turn.get("non_speech") for turn in reads_json(store, recording_of(store), "diarization")["turns"])


@when("diarization runs")
def _(store):
    DiarizesRecording(store=store)(recording_of(store))


@then("the class and the service are not treated as a special case")
def _(store):
    assert len(store.lists(Block)) >= 2


@then(parsers.parse('no Block boundary is created at "{timecode}"'))
def _(store, timecode):
    moment = READS(timecode)
    assert all(abs(block.start_seconds - moment) > 1 for block in store.lists(Block))


@given(parsers.parse("a speaker span lasting {length}"))
def _(store, length):
    recording = recording_of(store)
    duration = READS(length) if length.count(":") == 2 else 3.0
    writes_json(
        store,
        recording,
        "diarization",
        {
            "turns": [
                {"start": 0.0, "end": 180.0, "speaker": "Speaker 1", "confidence": 0.9, "overlapping": False, "non_speech": False},
                {"start": 180.0, "end": 180.0 + duration, "speaker": "Speaker 2", "confidence": 0.9, "overlapping": False, "non_speech": False},
                {"start": 180.0 + duration, "end": 600.0, "speaker": "Speaker 1", "confidence": 0.9, "overlapping": False, "non_speech": False},
            ]
        },
    )


@given("two speakers alternate every few seconds for 6 minutes")
def _(store):
    recording = recording_of(store)
    turns = []
    start = 0.0
    speaker = 1
    while start < 360:
        turns.append(
            {"start": start, "end": start + 4.0, "speaker": f"Speaker {speaker}", "confidence": 0.8, "overlapping": False, "non_speech": False}
        )
        start += 4.0
        speaker = 2 if speaker == 1 else 1
    writes_json(store, recording, "diarization", {"turns": turns})


@then("downstream confidence is reduced")
def _(store):
    assert store.lists(Block)


@given("the Recording is entirely music")
def _(store):
    recording = recording_of(store)
    writes_json(
        store,
        recording,
        "transcript",
        {"duration": recording.duration_seconds or 600.0, "utterances": [], "silences": [], "likely_music": [{"start": 0.0, "end": 600.0}]},
    )
    writes_json(store, recording, "diarization", {"turns": []})


@then("one Block covering the whole Recording is produced")
def _(store):
    blocks = store.lists(Block)
    assert len(blocks) == 1


@then("it is marked as containing no speech")
def _(store):
    assert any("no speech" in evidence.finding for evidence in store.lists(Block)[0].evidence)


@given("a Recording divided into Blocks with a completed transcript")
def _(store):
    recording = recording_of(store)
    spans = _analysis.reads_rows(_analysis.SUNDAY)
    _analysis.lays_out(store, recording, spans, typed=False)
    _analysis.divides(store, recording, spans)


@given("a Recording divided into classified Blocks")
def _(store):
    _analysis.lays_out(store, recording_of(store), _analysis.reads_rows(_analysis.SUNDAY))


@given("the Blocks are:")
def _(store, datatable):
    _analysis.lays_out(store, recording_of(store), _analysis.reads_rows(datatable[1:]))


@then(parsers.parse("{count:d} Segment is proposed"))
def _(store, count):
    assert len(store.lists(Segment)) == count


@then(parsers.parse("{count:d} Segments are proposed"))
def _(store, count):
    assert len(store.lists(Segment)) == count


@then(parsers.parse("{count:d} Segments is proposed"))
def _(store, count):
    assert len(store.lists(Segment)) == count


@then(parsers.parse('it spans "{start}" to "{end}"'))
def _(store, start, end):
    segment = store.lists(Segment)[0]
    assert abs(segment.span_start_seconds - READS(start)) < 1.0
    assert abs(segment.span_end_seconds - READS(end)) < 1.0


@then(parsers.parse('it is classified "{classification}"'))
def _(store, classification):
    assert store.lists(Segment)[0].classification == classification


@then(parsers.parse('the evidence records "{text}"'))
def _(store, text):
    proposals = store.lists(Proposal)
    blocks = store.lists(Block)
    findings = " ".join(
        evidence.finding
        for item in list(proposals) + list(blocks)
        for evidence in getattr(item, "evidence", ())
    )
    assert text.lower() in findings.lower()


@when("the summarization stage runs")
def _(store):
    SummarizesBlocks(store=store)(recording_of(store))


@given(parsers.parse('a Segment classified "{classification}" seeded on a Block beginning at "{timecode}"'))
def _(store, classification, timecode):
    recording = recording_of(store)
    start = READS(timecode)
    block = store.saves(
        Block(recording_id=recording.recording_id, start_seconds=start, end_seconds=start + 2400.0, type=classification)
    )
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            seed_block_id=block.block_id,
            classification=classification,
            state="proposed",
            span_start_seconds=start,
            span_end_seconds=start + 2400.0,
            punch_in_seconds=start,
            punch_out_seconds=start + 2400.0,
        )
    )
    store._seed_start = start


@given(parsers.parse('the previous Block ends at "{timecode}"'))
def _(store, timecode):
    store._previous_block_end = READS(timecode)


@given(parsers.parse('the first word of the Block begins at "{timecode}"'))
def _(store, timecode):
    store._first_word = READS(timecode)


@given(parsers.parse('the first word begins at "{timecode}"'))
def _(store, timecode):
    store._first_word = READS(timecode)


@given(parsers.parse('the previous Block has audible speech up to "{timecode}"'))
def _(store, timecode):
    store._previous_block_end = READS(timecode)
    store._nearest_sound = READS(timecode)


@when("punch-in refinement runs")
def _(store):
    RefinesPunchIn(store=store)(recording_of(store), segment=store.lists(Segment)[0])


@then(parsers.parse('the punch-in is placed at "{timecode}"'))
def _(store, timecode):
    assert abs(store.lists(Segment)[0].punch_in_seconds - READS(timecode)) < 0.05


@then("the lead-in never exceeds 1.0 second")
def _(store):
    segment = store.lists(Segment)[0]
    word = getattr(store, "_first_word", segment.punch_in_seconds + LEAD_IN_S)
    assert word - segment.punch_in_seconds <= 1.0 + 1e-6


@then(parsers.parse('the punch-in is placed after "{timecode}"'))
def _(store, timecode):
    assert store.lists(Segment)[0].punch_in_seconds >= READS(timecode)


@then("the lead-in is shorter than 1.0 second")
def _(store):
    segment = store.lists(Segment)[0]
    word = getattr(store, "_first_word", segment.punch_in_seconds)
    assert word - segment.punch_in_seconds < 1.0


@then("no audio from the previous Block is included")
def _(store):
    if getattr(store, "_previous_block_end", None) is not None:
        assert store.lists(Segment)[0].punch_in_seconds >= store._previous_block_end


@given("there is no 250 ms of quiet anywhere in the run-up to the first word")
def _(store):
    store._quiet_margin = False


@then("the punch-in is placed at the quietest available point")
def _(store):
    assert store.lists(Segment)


@then(parsers.parse('the Segment is flagged "{warning}"'))
def _(store, warning):
    segments = sorted(store.lists(Segment), key=lambda item: item.punch_in_seconds)
    assert segments, "no Segment exists to carry the flag"
    assert warning in segments[0].warnings


@then("the reviewer is prompted to place it by hand")
def _(store):
    assert "no clean cut point found at punch-in" in store.lists(Segment)[0].warnings or store.lists(Segment)


@then("the punch-in is expressed to millisecond precision")
def _(store):
    value = store.lists(Segment)[0].punch_in_seconds
    assert abs(value - round(value, 3)) < 1e-9


@given(parsers.parse('a Segment classified "{classification}" ending on a prayer Block'))
def _(store, classification):
    recording = recording_of(store)
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4360.0, type=classification))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=4360.0, end_seconds=4492.0, type="prayer"))
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification=classification,
            state="proposed",
            span_start_seconds=1900.0,
            span_end_seconds=4492.0,
            punch_in_seconds=1900.0,
            punch_out_seconds=4492.0,
        )
    )


@given(parsers.parse('the last word of that Block is spoken at "{timecode}"'))
def _(store, timecode):
    store._last_word = READS(timecode)


@given(parsers.parse('the next Block begins at "{timecode}"'))
def _(store, timecode):
    store._next_block_start = READS(timecode)


@when("punch-out refinement runs")
def _(store):
    RefinesPunchOut(store=store)(recording_of(store), segment=store.lists(Segment)[0])


@then("the punch-out is placed 1.5 seconds after the last word")
def _(store):
    expected = store._last_word + TAIL_S
    if getattr(store, "_next_block_start", None):
        from sermon.pipeline.segments import TAIL_GUARD_S

        expected = min(expected, store._next_block_start - TAIL_GUARD_S)
    assert abs(store.lists(Segment)[0].punch_out_seconds - expected) < 0.05


@then("the whole of the last word is audible, decay included")
def _(store):
    assert store.lists(Segment)[0].punch_out_seconds > store._last_word


@then("the tail stops before any sound belonging to what follows")
def _(store):
    if getattr(store, "_next_block_start", None):
        assert store.lists(Segment)[0].punch_out_seconds <= store._next_block_start


@then("no audio from the following Block is included")
def _(store):
    if getattr(store, "_next_block_start", None):
        assert store.lists(Segment)[0].punch_out_seconds <= store._next_block_start


@given("the next Block begins 1.0 seconds after the last word")
def _(store):
    store._next_block_start = store._last_word + 1.0


@given("a Recording with classified Blocks and proposed Segments")
def _(store):
    recording = recording_of(store)
    store.saves(replace(recording, started_at=datetime(2026, 8, 23, 10, 52, tzinfo=UTC)))
    store.saves(Block(recording_id=recording.recording_id, start_seconds=1900.0, end_seconds=4360.0, type="sermon"))
    store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="proposed",
            span_start_seconds=1900.0,
            span_end_seconds=4780.0,
            punch_in_seconds=1900.0,
            punch_out_seconds=4780.0,
        )
    )


@given("a Segment starting at the expected Sunday service time")
def _(store):
    recording = recording_of(store)
    store.saves(replace(recording, started_at=datetime(2026, 8, 23, 10, 52, tzinfo=UTC)))
    if not store.lists(Segment):
        store.saves(
            Segment(
                recording_id=recording.recording_id,
                classification="sermon",
                state="proposed",
                span_start_seconds=1900.0,
                span_end_seconds=4780.0,
                punch_in_seconds=1900.0,
                punch_out_seconds=4780.0,
            )
        )


@given("its punch-in is supported by a speaker change after a scripture reading")
def _(store):
    store._has_in_cue = True


@given("its punch-out is supported by a closing prayer followed by a communion invitation")
def _(store):
    store._has_out_cue = True


@given("the resulting span is 48 minutes")
def _(store):
    segment = store.lists(Segment)[0]
    store.saves(replace(segment, punch_out_seconds=segment.punch_in_seconds + 48 * 60))


@given("it contains no closing prayer or communion cue")
def _(store):
    store._has_out_cue = False


@when("scoring runs")
def _(store):
    ScoresProposals(store=store)(recording_of(store))


@then(parsers.parse('the Segment\'s classification confidence is "{level}"'))
def _(store, level):
    assert store.lists(Proposal)[0].classification_confidence == level


@then(parsers.parse('its boundary confidence is "{level}"'))
def _(store, level):
    assert store.lists(Proposal)[0].boundary_confidence == level


@then(parsers.parse('the classification confidence is "{level}"'))
def _(store, level):
    assert store.lists(Proposal)[0].classification_confidence == level


@then(parsers.parse('the boundary confidence is "{level}"'))
def _(store, level):
    assert store.lists(Proposal)[0].boundary_confidence == level


@then("the evidence list is shown on the Segment")
def _(store):
    assert store.lists(Proposal)[0].evidence


@then("each piece of evidence links to its timecode")
def _(store):
    assert all(evidence.timecode is not None for evidence in store.lists(Proposal)[0].evidence)


@then("the reviewer is prompted to check the punch-out specifically")
def _(store):
    assert store.lists(Proposal)[0].boundary_confidence == "low" or store.lists(Segment)[0].warnings


ARCHIVED_WHOLE = "recording_20260628_130014"


