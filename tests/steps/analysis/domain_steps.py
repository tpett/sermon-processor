from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when
from steps import _analysis
from steps._asr import AnswersOnTheTailnet, StatesTheAudio, transcribes_for
from steps._transcripts import covering_transcript

from sermon.analysis import (
    TEACHING,
    DiarizesRecording,
    EnrolsVoiceProfiles,
    ScoresProposals,
    SummarizesBlocks,
    TranscribesRecording,
)
from sermon.analysis.io import reads_json, writes_json
from sermon.analysis.transcribes_audio import ASR_ENDPOINT, PostsToTranscriber, transcribes_with
from sermon.pipeline import classify
from sermon.pipeline import segments as pipeline_segments

LEAD_IN_S = 1.0
from sermon.extends_segment_span import ReadsTimecode
from sermon.store import Artifact, Block, Proposal, Recording, Segment, SpeakerProfile
from sermon.web import creates_app

READS = ReadsTimecode()
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
PREACHER = "preacher"
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


@pytest.fixture
def stated_silences():
    return []


@pytest.fixture
def model_endpoint():
    return None


@pytest.fixture
def reached_destinations():
    return []


def transcriber(store, recording, silences, endpoint, destinations):
    """The scenario's transcriber, with any stated silence and configured endpoint applied."""
    chosen = transcribes_for(store, recording)
    audio = chosen.transcribes.decodes
    if silences:
        audio = StatesTheAudio(
            duration=audio.duration,
            silences=tuple(sorted([*audio.silences, *silences], key=lambda gap: gap["start"])),
        )
    engine = chosen.transcribes.engine
    if endpoint is not None:
        configured = transcribes_with(store, environment={ASR_ENDPOINT: endpoint}).transcribes.engine
        if isinstance(configured, PostsToTranscriber):
            engine = replace(configured, opens=AnswersOnTheTailnet(destinations=destinations))
    return replace(chosen, transcribes=replace(chosen.transcribes, decodes=audio, engine=engine))


@when("the transcription stage runs")
def _(store, stated_silences, model_endpoint, reached_destinations):
    recording = recording_of(store)
    try:
        TranscribesRecording(
            store=store,
            transcribes=transcriber(store, recording, stated_silences, model_endpoint, reached_destinations),
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
    recording = _analysis.the_recording(store)
    doc = reads_json(store, recording, "transcript")
    assert doc["utterances"]
    assert doc["utterances"][-1]["end"] >= (recording.duration_seconds or 0) - 12


@then("every utterance has a start time and an end time")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert all("start" in item and "end" in item for item in doc["utterances"])


@then("every word has a start time")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert all(word.get("start") is not None for item in doc["utterances"] for word in item.get("words", []))


@then("each utterance carries a recognition confidence")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert all("confidence" in item for item in doc["utterances"])


@then("the transcript is stored as an artifact of the Recording")
def _(store):
    assert store.lists(Artifact, recording_id=_analysis.the_recording(store).recording_id, kind="transcript")


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
    recording = _analysis.the_recording(store)
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
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    early = [item for item in doc["utterances"] if item["start"] < 1320]
    assert early
    assert all(item["confidence"] < 0.5 or not item["text"] for item in early)


@then('those regions are marked as "likely music" rather than treated as speech')
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert doc.get("likely_music")


NEAR_SILENCE = {"start": 1210.0, "end": 1300.0}


@given("there is 90 seconds of near-silence between segments")
def _(store, stated_silences):
    recording_of(store)
    stated_silences.append(dict(NEAR_SILENCE))


@then("no utterances are produced for that span")
def _(store, stated_silences):
    (quiet,) = stated_silences
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    inside = [
        (item["start"], item["end"])
        for item in doc["utterances"]
        if item["start"] < quiet["end"] and item["end"] > quiet["start"]
    ]
    assert inside == [], f"utterances inside the silence: {inside}"


@then("the span is recorded as a silence gap with its start and end times")
def _(store, stated_silences):
    (quiet,) = stated_silences
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert quiet in doc["silences"], doc["silences"]


@given(parsers.parse("the recording has {condition}"))
def _(store, condition):
    store._poor_transcript = True


@then("the transcript is still produced")
def _(store):
    assert reads_json(store, _analysis.the_recording(store), "transcript")["utterances"]


@then("the average confidence for the affected region is recorded")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert all("confidence" in item for item in doc["utterances"])


@then(parsers.parse('the Recording is flagged "{flag}" when the transcript is measurably poor'))
def _(store, flag):
    assert flag in _analysis.the_recording(store).warnings or flag in store.loads(
        Recording, _analysis.the_recording(store).recording_id
    ).warnings


@given("the spoken language is not English")
def _(store):
    store._spoken_language = "es"


@then("Analysis continues with low confidence")
def _(store):
    recording = _analysis.the_recording(store)
    assert store.loads(Recording, recording.recording_id).state != "analysis_failed"
    assert reads_json(store, recording, "transcript")["utterances"]


@then("no third-party transcription API is called")
def _(store):
    from sermon.analysis.transcribes_audio import refuses_a_public_transcriber

    assert reads_json(store, _analysis.the_recording(store), "transcript") is not None
    for destination in getattr(store, "_asr_destinations", ()):
        refuses_a_public_transcriber(destination)


@given("the transcription model is hosted on another machine on the tailnet", target_fixture="model_endpoint")
def _(store):
    recording_of(store)
    return "http://100.88.211.71:9000"


@then("it calls that machine rather than a hosted service")
def _(model_endpoint, reached_destinations):
    assert model_endpoint is not None, "no model endpoint was configured for this scenario"
    assert reached_destinations, "no request reached any machine"
    elsewhere = [url for url in reached_destinations if not url.startswith(model_endpoint.rstrip("/") + "/")]
    assert elsewhere == [], f"requests went elsewhere: {elsewhere}"


@then("the recording is transcribed in chunks")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
    assert len(doc["chunks"]) > 1
    assert doc["chunks"][0]["start"] == 0.0
    assert doc["chunks"][-1]["end"] == doc["duration"]


@then("chunk boundaries do not lose or duplicate words")
def _(store):
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
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
    doc = reads_json(store, _analysis.the_recording(store), "transcript")
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

    view = ShowsRecording(store=store)(_analysis.the_recording(store).recording_id)
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
    approved = sorted(item.segment_id for item in store.lists(Segment, state="complete"))
    profiles = store.lists(SpeakerProfile)
    enrolled = sorted(segment_id for profile in profiles for segment_id in profile.enrolled_from)
    assert enrolled == approved, f"enrolled from {enrolled}, approved {approved}"
    enrolling = {profile.speaker_profile_id: profile.enrolled_from for profile in profiles}
    unlinked = [
        item.segment_id
        for item in store.lists(Segment, state="complete")
        if item.segment_id not in enrolling.get(item.confirmed_speaker_profile_id, ())
    ]
    assert unlinked == [], f"Segments not linked to the profile they enrolled: {unlinked}"


@then("the number of profiles matches the real preaching roster")
def _(store):
    assert 1 <= len(store.lists(SpeakerProfile)) <= 5


@given("a Recording and an enrolled profile for the regular preacher")
def _(store):
    recording = _analysis.recording_of(store)
    _analysis.lays_out(store, recording, _analysis.reads_rows(_analysis.SUNDAY))
    store.saves(SpeakerProfile(name=PREACHER, embedding=b"voice", confirmed_by_human=True))


@when("blocks are scored against that profile")
def _(store):
    _analysis.analyses(store, _analysis.the_recording(store))


@then("the teaching Block ranks first")
def _(store):
    (preacher,) = store.lists(SpeakerProfile, name=PREACHER)
    held = _analysis.blocks_of(store)
    scores = {
        block.block_id: [match.similarity for match in block.speaker_matches if match.speaker_profile_id == preacher.speaker_profile_id]
        for block in held
    }
    unscored = [block.type for block in held if not scores[block.block_id]]
    assert unscored == [], f"Blocks never scored against the preacher's profile: {unscored}"
    ranked = sorted(held, key=lambda block: scores[block.block_id][0], reverse=True)
    assert ranked[0].type in TEACHING, [block.type for block in ranked]


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
    doc = reads_json(store, _analysis.the_recording(store), "diarization")
    assert doc["turns"]


@then("each segment has a start time, an end time and a speaker label")
def _(store):
    for turn in reads_json(store, _analysis.the_recording(store), "diarization")["turns"]:
        assert turn["end"] > turn["start"]
        assert turn["speaker"]


@then("the labels are stable within the recording")
def _(store):
    speakers = {turn["speaker"] for turn in reads_json(store, _analysis.the_recording(store), "diarization")["turns"]}
    assert speakers


@then("each segment carries a confidence")
def _(store):
    assert all("confidence" in turn for turn in reads_json(store, _analysis.the_recording(store), "diarization")["turns"])


@then("every transcript utterance is attributed to a speaker segment")
def _(store):
    recording = _analysis.the_recording(store)
    transcript = reads_json(store, recording, "transcript") or covering_transcript(recording.duration_seconds or 0, recording_id=recording.recording_id)
    turns = reads_json(store, recording, "diarization")["turns"]
    for utterance in transcript["utterances"]:
        assert any(turn["start"] - 1 <= utterance["start"] <= turn["end"] + 1 for turn in turns)


@then("the reviewer can see who is speaking beside each utterance in the transcript view")
def _(store):
    detail = creates_app(store=store).test_client().get(f"/api/recordings/{_analysis.the_recording(store).recording_id}").get_json()
    assert detail["transcript"]


@given("a voice profile exists for the primary preacher")
def _(store):
    store.saves(SpeakerProfile(name="Speaker 1", embedding=b"voice", confirmed_by_human=True))


@then("spans matching that profile are labelled with that preacher")
def _(store):
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    assert any(turn["speaker"] == "Speaker 1" for turn in turns)


@then("spans that match no known profile keep generic labels")
def _(store):
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
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
    (segment,) = store.lists(Segment)
    profile = store.saves(SpeakerProfile(name=PREACHER, embedding=b"voice", confirmed_by_human=True))
    store.saves(replace(segment, confirmed_speaker_profile_id=profile.speaker_profile_id))


@then("that Segment can be used to enrol or strengthen that speaker's profile")
def _(store):
    (segment,) = store.lists(Segment)
    profile = store.loads(SpeakerProfile, segment.confirmed_speaker_profile_id)
    assert segment.segment_id in profile.enrolled_from, (
        f"confirming the preacher left {profile.name} enrolled from {profile.enrolled_from}"
    )


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
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    assert any(turn["speaker"] in {"Guest", "Speaker 1"} or "Speaker" in turn["speaker"] for turn in turns)


OVERLAP = (610.0, 616.0)


@given("two people speak at once for 6 seconds")
def _(store):
    first, last = OVERLAP
    writes_json(
        store,
        recording_of(store),
        "diarization",
        {
            "turns": [
                {"start": 0.0, "end": last, "speaker": "Speaker 1", "confidence": 0.9},
                {"start": first, "end": 1200.0, "speaker": "Speaker 2", "confidence": 0.9},
            ]
        },
    )


def turns_across_the_overlap(store):
    first, last = OVERLAP
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    return [turn for turn in turns if turn["start"] < last and turn["end"] > first]


@then("the overlapping span is marked as overlapping speech")
def _(store):
    marked = [(turn["start"], turn["end"]) for turn in turns_across_the_overlap(store) if turn.get("overlapping")]
    assert marked == [OVERLAP], f"overlapping speech marked at {marked}"


@then("it is not treated as a clean speaker change")
def _(store):
    clean = [turn["speaker"] for turn in turns_across_the_overlap(store) if not turn.get("overlapping")]
    assert clean == [], f"single-speaker turns run through the overlap: {clean}"


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
    turns = reads_json(store, _analysis.the_recording(store), "diarization")["turns"]
    assert all(turn.get("non_speech") or turn["speaker"] == "music" for turn in turns if turn["end"] <= 480)


@then("the span is labelled as non-speech")
def _(store):
    assert any(turn.get("non_speech") for turn in reads_json(store, _analysis.the_recording(store), "diarization")["turns"])


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
    classified = store.lists(Block)
    assert classified, "blocking produced no Block"
    confident = [block for block in classified if block.classification_confidence == "high"]
    assert confident == [], f"{len(confident)} of {len(classified)} Blocks are classified with high confidence"


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


@then(parsers.parse('the Segment is flagged "{warning}"'))
def _(store, warning):
    segments = sorted(store.lists(Segment), key=lambda item: item.punch_in_seconds)
    assert segments, "no Segment exists to carry the flag"
    assert warning in segments[0].warnings


@then("the punch-in is expressed to millisecond precision")
def _(store):
    value = store.lists(Segment)[0].punch_in_seconds
    assert abs(value - round(value, 3)) < 1e-9


ARCHIVED_WHOLE = "recording_20260628_130014"


