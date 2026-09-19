"""A behavioural net over the moved pipeline library.

The fingerprint was captured from the code as it stands, so it pins *current*
behaviour. The move itself is proved byte-identical elsewhere; this file is a
regression net for later refactors, not independent evidence about the pre-move
code. Nothing here reads a source recording, calls a model host, or writes under
experiments/data.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
import urllib.error
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from sermon.config import ModelEndpointUnreachable, UnusableConfiguration

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "pipeline"
FINGERPRINT = Path(__file__).parent / "pipeline_behaviour_fingerprint.json"
PROMPTS = PROJECT_ROOT / "experiments" / "prompts"
SEARCHED = (PROJECT_ROOT / "src" / "sermon", PROJECT_ROOT / "experiments" / "src",
            PROJECT_ROOT / "experiments" / "baseline.py")

MOVED = ("acoustic", "audio", "blocks", "classify", "cues", "features",
         "render", "rules", "segments")

INJECTED = {
    ("classify", "DATA"),
    ("classify", "PROMPTS"),
    ("classify", "ENDPOINT"),
    ("segments", "DATA_ROOT"),
}

RECORDINGS = ("service", "class")


def imports_moved(name):
    return importlib.import_module(f"sermon.pipeline.{name}")


def renders_canonically(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digests(value):
    return hashlib.sha256(renders_canonically(value).encode("utf-8")).hexdigest()[:32]


def reads_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def rounds(value, places=3):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, dict):
        return {key: rounds(held, places) for key, held in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounds(held, places) for held in value]
    number = float(value)
    return None if math.isnan(number) else round(number, places)


@pytest.fixture(scope="module")
def expected():
    return json.loads(FINGERPRINT.read_text())


@pytest.fixture(autouse=True)
def forgets_cached_edges():
    cache = imports_moved("segments")._EDGE_CACHE
    cache.clear()
    yield
    cache.clear()


def matches_the_fingerprint(expected, key, found):
    assert key in expected, f"{key} is not in the fingerprint"
    assert renders_canonically(rounds(found)) == renders_canonically(rounds(expected[key]))




def reads_recording(name):
    return reads_fixture(f"{name}.transcript.json")


def plants_diarization(root, name, carried=True):
    under = root / "diarization"
    under.mkdir(parents=True, exist_ok=True)
    if carried:
        (under / f"fixture_{name}.json").write_text(
            (FIXTURES / f"{name}.diarization.json").read_text()
        )
    return root


@pytest.fixture
def diarized(tmp_path):
    root = tmp_path / "data"
    for name in RECORDINGS:
        plants_diarization(root, name)
    return root


@pytest.fixture
def undiarized(tmp_path):
    return plants_diarization(tmp_path / "bare", "unused", carried=False)


@pytest.fixture
def rooted_segments(diarized, monkeypatch):
    segments = imports_moved("segments")
    monkeypatch.setattr(segments, "DATA_ROOT", diarized)
    return segments




@pytest.mark.parametrize("name", RECORDINGS)
def test_splitting_a_recording_into_candidate_blocks_reproduces_the_fingerprint(
    name, expected
):
    blocks = imports_moved("blocks")
    doc = reads_recording(name)
    found = [
        {
            "start": candidate["start"],
            "end": candidate["end"],
            "speech_start": candidate["speech_start"],
            "speech_end": candidate["speech_end"],
            "utterances": len(candidate["utterances"]),
            "text": digests(blocks.text_of(candidate)),
            "stats": blocks.stats(candidate),
        }
        for candidate in blocks.candidates(doc)
    ]
    matches_the_fingerprint(expected, f"blocks.candidates.{name}", found)


def test_grouping_utterances_ends_a_run_only_on_a_gap_longer_than_the_threshold():
    blocks = imports_moved("blocks")
    utterances = [
        {"start": 0.0, "end": 1.0},
        {"start": 13.0, "end": 14.0},
        {"start": 26.01, "end": 27.0},
    ]
    runs = blocks.speech_runs(utterances)
    assert [(run["start"], run["end"]) for run in runs] == [(0.0, 14.0), (26.01, 27.0)]


def test_folding_short_runs_absorbs_them_into_the_neighbour_before_them():
    blocks = imports_moved("blocks")
    runs = [
        {"start": 0.0, "end": 400.0, "utterances": [1]},
        {"start": 500.0, "end": 510.0, "utterances": [2]},
        {"start": 600.0, "end": 1000.0, "utterances": [3]},
    ]
    folded = blocks.merge_short(runs)
    assert [(run["start"], run["end"]) for run in folded] == [(0.0, 510.0), (600.0, 1000.0)]
    assert folded[0]["utterances"] == [1, 2]


def test_a_recording_with_no_speech_still_yields_one_block_covering_it():
    blocks = imports_moved("blocks")
    assert blocks.candidates({"utterances": [], "duration": 42.0}) == [
        {"start": 0.0, "end": 42.0, "utterances": []}
    ]


def test_elided_block_text_keeps_both_ends_and_marks_the_cut():
    blocks = imports_moved("blocks")
    block = {"utterances": [{"text": "ab" * 200}]}
    elided = blocks.text_of(block, max_chars=40)
    assert elided.startswith("ab" * 10)
    assert elided.endswith("ab" * 10)
    assert "\n[...]\n" in elided


def test_the_statistics_of_a_silent_block_report_no_speech_at_all():
    blocks = imports_moved("blocks")
    assert blocks.stats({"start": 0.0, "end": 10.0, "utterances": []}) == {
        "duration": 10.0, "words": 0, "words_per_min": 0.0,
        "avg_logprob": -10.0, "no_speech_prob": 1.0, "speech_frac": 0.0,
    }




@pytest.mark.parametrize("name", RECORDINGS)
def test_running_the_rules_rung_reproduces_the_fingerprint(name, expected):
    rules = imports_moved("rules")
    matches_the_fingerprint(expected, f"rules.run.{name}", rules.run(reads_recording(name)))


@pytest.mark.parametrize(
    ("duration", "wpm", "kind"),
    [
        (899.0, 200, "other"),
        (901.0, 200, "sermon"),
        (901.0, 89, "other"),
        (901.0, 90, "sermon"),
    ],
)
def test_teaching_is_claimed_only_above_both_the_length_and_the_density_floor(
    duration, wpm, kind
):
    rules = imports_moved("rules")
    block = {"start": 0.0, "end": duration, "utterances": [{"text": "word " * 40}]}
    statistics = {"duration": duration, "words_per_min": wpm, "words": 400,
                  "avg_logprob": -0.2, "no_speech_prob": 0.01}
    assert rules.classify_block(block, statistics)[0] == kind


def test_the_rules_punch_in_lands_after_the_last_scripture_cue_near_the_opening():
    rules = imports_moved("rules")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "Turn with me in your Bible."},
        {"start": 5.0, "end": 9.0, "text": "This is the word of the Lord."},
        {"start": 10.0, "end": 14.0, "text": "Now, the argument runs like this."},
    ]
    assert rules.refine_punch_in(utterances) == 10.0


def test_the_rules_punch_out_prefers_the_communion_invitation_over_a_later_amen():
    rules = imports_moved("rules")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "In Jesus' name, amen."},
        {"start": 5.0, "end": 9.0, "text": "We take communion together."},
        {"start": 10.0, "end": 14.0, "text": "Amen and amen."},
    ]
    assert rules.refine_punch_out(utterances) == 5.0


def test_the_rules_punch_out_falls_back_to_the_closing_amen():
    rules = imports_moved("rules")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "And so we close."},
        {"start": 5.0, "end": 9.0, "text": "In Christ's name, amen."},
        {"start": 10.0, "end": 14.0, "text": "Please stand."},
    ]
    assert rules.refine_punch_out(utterances) == 9.0


def test_neither_rules_refinement_claims_a_boundary_in_an_empty_block():
    rules = imports_moved("rules")
    assert rules.refine_punch_in([]) is None
    assert rules.refine_punch_out([]) is None




@pytest.mark.parametrize("name", RECORDINGS)
@pytest.mark.parametrize("refine", [True, False], ids=["refined", "unrefined"])
def test_deriving_segments_from_model_blocks_reproduces_the_fingerprint(
    name, refine, rooted_segments, expected
):
    fixture = reads_fixture(f"{name}.blocks.json")
    doc = reads_recording(name)
    derived = rooted_segments.derive(
        json.loads(renders_canonically(fixture["blocks"])), doc, refine=refine
    )
    chosen = rooted_segments.choose(fixture["model_segments"], derived, doc)
    label = "refined" if refine else "unrefined"
    matches_the_fingerprint(
        expected, f"segments.derive.{label}.{name}", {"derived": derived, "chosen": chosen}
    )


@pytest.mark.parametrize("name", RECORDINGS)
def test_the_unrefined_derivation_moves_when_the_diarization_root_is_empty(
    name, undiarized, diarized, monkeypatch
):
    segments = imports_moved("segments")
    fixture = reads_fixture(f"{name}.blocks.json")
    doc = reads_recording(name)

    def derives(root):
        monkeypatch.setattr(segments, "DATA_ROOT", root)
        segments._EDGE_CACHE.clear()
        return segments.derive(
            json.loads(renders_canonically(fixture["blocks"])), doc, refine=False
        )

    assert derives(diarized) != derives(undiarized)


def test_candidate_edges_carry_the_union_of_transcript_and_speaker_edges(
    tmp_path, monkeypatch
):
    segments = imports_moved("segments")
    root = tmp_path / "data"
    (root / "diarization").mkdir(parents=True)
    (root / "diarization" / "rec1.json").write_text(
        json.dumps({"turns": [{"start": 4.321, "end": 9.5}]})
    )
    monkeypatch.setattr(segments, "DATA_ROOT", root)
    doc = {"recording_id": "rec1", "duration": 20.0,
           "utterances": [{"start": 1.0, "end": 2.0}]}
    assert segments.candidate_edges(doc) == [1.0, 2.0, 4.321, 9.5]


def test_snapping_reaches_a_speaker_edge_no_transcript_edge_can_beat(
    tmp_path, monkeypatch
):
    segments = imports_moved("segments")
    root = tmp_path / "data"
    (root / "diarization").mkdir(parents=True)
    (root / "diarization" / "rec1.json").write_text(
        json.dumps({"turns": [{"start": 4.321, "end": 9.5}]})
    )
    doc = {"recording_id": "rec1", "duration": 20.0,
           "utterances": [{"start": 1.0, "end": 2.0}]}

    def snaps(root):
        monkeypatch.setattr(segments, "DATA_ROOT", root)
        segments._EDGE_CACHE.clear()
        return segments.snap(4.4, doc)

    bare = tmp_path / "bare"
    (bare / "diarization").mkdir(parents=True)
    assert snaps(root) == 4.321
    assert snaps(bare) == 2.0


def test_the_edge_cache_keeps_the_root_it_first_read_for_a_recording(
    tmp_path, monkeypatch
):
    segments = imports_moved("segments")
    root = tmp_path / "data"
    (root / "diarization").mkdir(parents=True)
    (root / "diarization" / "rec1.json").write_text(
        json.dumps({"turns": [{"start": 4.321, "end": 9.5}]})
    )
    doc = {"recording_id": "rec1", "duration": 20.0,
           "utterances": [{"start": 1.0, "end": 2.0}]}
    monkeypatch.setattr(segments, "DATA_ROOT", root)
    assert segments.candidate_edges(doc) == [1.0, 2.0, 4.321, 9.5]
    bare = tmp_path / "bare"
    (bare / "diarization").mkdir(parents=True)
    monkeypatch.setattr(segments, "DATA_ROOT", bare)
    assert segments.candidate_edges(doc) == [1.0, 2.0, 4.321, 9.5]


def test_the_sermon_punch_in_waits_for_the_speaker_change_after_the_reading():
    segments = imports_moved("segments")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "This is the word of the Lord."},
        {"start": 5.0, "end": 9.0, "text": "Let us pray before we begin."},
        {"start": 20.0, "end": 24.0, "text": "Now, look at what Paul is doing."},
    ]
    assert segments.refine_in(utterances, 0.0, "sermon") == 5.0
    assert segments.refine_in(utterances, 0.0, "sermon", speaker_changes=[19.0]) == 20.0


def test_a_lesson_punch_in_is_the_top_of_the_session_not_the_teaching():
    segments = imports_moved("segments")
    utterances = [
        {"start": 3.0, "end": 7.0, "text": "Good morning, grab a handout."},
        {"start": 9.0, "end": 13.0, "text": "This is the word of the Lord."},
        {"start": 15.0, "end": 19.0, "text": "So the doctrine we are after is this."},
    ]
    assert segments.refine_in(utterances, 0.0, "lesson") == 3.0


def test_the_punch_out_steps_back_from_the_invitation_to_the_closing_amen():
    segments = imports_moved("segments")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "And that is the verdict."},
        {"start": 5.0, "end": 9.0, "text": "In Jesus' name, amen."},
        {"start": 11.0, "end": 15.0, "text": "If you're a visitor with us this morning."},
    ]
    assert segments.refine_out(utterances, "sermon") == 9.0


def test_the_punch_out_ignores_an_amen_too_early_to_be_the_closing_one():
    segments = imports_moved("segments")
    utterances = [
        {"start": 0.0, "end": 4.0, "text": "Amen, and now to the second point."},
        {"start": 5.0, "end": 400.0, "text": "A long stretch of teaching with no close."},
    ]
    assert segments.refine_out(utterances, "sermon") == 400.0


def test_neither_refinement_claims_a_boundary_in_an_empty_span():
    segments = imports_moved("segments")
    assert segments.refine_in([]) is None
    assert segments.refine_out([]) is None


def test_the_tail_stops_short_of_whatever_speaks_next():
    segments = imports_moved("segments")
    doc = {"duration": 100.0, "utterances": [{"start": 0.0, "end": 10.0},
                                             {"start": 10.9, "end": 20.0}]}
    assert segments.add_tail(10.0, doc) == 10.5
    assert segments.add_tail(20.0, doc) == 21.5


def test_coalescing_merges_neighbours_of_one_type_and_keeps_both_reasons():
    segments = imports_moved("segments")
    merged = segments.coalesce([
        {"start": 0.0, "end": 10.0, "type": "sermon", "confidence": 0.5, "evidence": "first"},
        {"start": 10.0, "end": 20.0, "type": "sermon", "confidence": 0.9, "evidence": "second"},
        {"start": 20.0, "end": 30.0, "type": "prayer", "confidence": 0.4, "evidence": "third"},
    ])
    assert [(block["start"], block["end"], block["type"]) for block in merged] == [
        (0.0, 20.0, "sermon"), (20.0, 30.0, "prayer")
    ]
    assert merged[0]["confidence"] == 0.9
    assert merged[0]["evidence"] == "first; second"


def test_a_model_segment_outside_the_plausible_length_band_loses_to_refinement():
    segments = imports_moved("segments")
    doc = {"duration": 10_000.0, "utterances": []}
    derived = [{"punch_in": 100.0, "punch_out": 3000.0,
                "classification": "sermon", "confidence": 0.9}]
    wild = segments.choose([{"punch_in": 90.0, "punch_out": 200.0}], derived, doc)
    assert wild[0]["boundary_source"] == "refined"
    assert wild[0]["punch_in"] == 100.0
    plausible = segments.choose([{"punch_in": 90.0, "punch_out": 2900.0}], derived, doc)
    assert plausible[0]["boundary_source"] == "model-in/refined-out"
    assert (plausible[0]["punch_in"], plausible[0]["punch_out"]) == (90.0, 3000.0)


def test_choosing_pairs_a_model_segment_with_the_derived_span_it_overlaps():
    segments = imports_moved("segments")
    doc = {"duration": 10_000.0, "utterances": []}
    derived = [
        {"punch_in": 100.0, "punch_out": 2100.0,
         "classification": "sermon", "confidence": 0.9},
        {"punch_in": 5000.0, "punch_out": 7000.0,
         "classification": "lesson", "confidence": 0.8},
    ]
    chosen = segments.choose(
        [{"punch_in": 4900.0, "punch_out": 6900.0}, {"punch_in": 90.0, "punch_out": 2000.0}],
        derived, doc,
    )
    assert [pick["punch_in"] for pick in chosen] == [90.0, 4900.0]




@pytest.mark.parametrize("name", RECORDINGS)
def test_blocking_a_recording_by_speaker_reproduces_the_fingerprint(name, expected):
    features = imports_moved("features")
    doc = reads_recording(name)
    dia = reads_fixture(f"{name}.diarization.json")
    blocks = features.blocks_from_diarization(doc, dia)
    found = {
        "blocks": [
            {"start": block["start"], "end": block["end"], "speaker": block["speaker"],
             "utterances": len(block["utterances"])}
            for block in blocks
        ],
        "described": [features.describe(block, doc, dia) for block in blocks],
        "table": {
            "digest": hashlib.sha256(
                features.render_table(blocks, doc, dia).encode("utf-8")
            ).hexdigest()[:32],
            "characters": len(features.render_table(blocks, doc, dia)),
        },
    }
    matches_the_fingerprint(expected, f"features.table.{name}", found)


def test_a_recording_with_no_speaker_turns_yields_no_blocks():
    features = imports_moved("features")
    assert features.blocks_from_diarization({"utterances": [], "duration": 1.0},
                                            {"turns": []}) == []


def test_a_turn_too_short_to_be_a_section_is_absorbed_by_its_own_voice():
    features = imports_moved("features")
    doc = {"duration": 300.0,
           "utterances": [{"start": start, "end": start + 4.0, "text": "a word",
                           "avg_logprob": -0.2, "no_speech_prob": 0.01}
                          for start in range(0, 300, 10)],
           "started_at": "2026-04-05T10:00:00"}
    dia = {"turns": [
        {"start": 0.0, "end": 100.0, "speaker": "S0"},
        {"start": 100.0, "end": 110.0, "speaker": "S1"},
        {"start": 110.0, "end": 300.0, "speaker": "S0"},
    ]}
    blocks = features.blocks_from_diarization(doc, dia)
    assert [block["speaker"] for block in blocks] == ["S0"]


def test_a_speaker_boundary_snaps_to_the_speech_edge_inside_the_snap_window():
    features = imports_moved("features")
    doc = {"duration": 200.0,
           "utterances": [{"start": 0.0, "end": 60.0}, {"start": 100.0, "end": 190.0}]}
    dia = {"turns": [{"start": 0.0, "end": 80.5, "speaker": "S0"},
                     {"start": 80.5, "end": 200.0, "speaker": "S1"}]}
    blocked = features.blocks_from_diarization(doc, dia)
    assert [(block["start"], block["end"]) for block in blocked] == [
        (0.0, 100.0), (100.0, 200.0)
    ]


def test_an_unreadable_start_time_leaves_the_wall_clock_unknown():
    features = imports_moved("features")
    described = features.describe(
        {"start": 0.0, "end": 10.0, "utterances": []}, {"started_at": "not a time"}, None
    )
    assert described["wall"] == "?"
    assert described["speaker"] == "?"
    assert described["likely_music"] is True




def test_counting_cues_is_case_insensitive_and_counts_phrases_not_occurrences():
    cues = imports_moved("cues")
    assert cues.count_hits("LET US PRAY. Let us pray. Amen.", cues.PRAYER) == 2
    assert cues.any_hit("AMEN", cues.PRAYER) is True
    assert cues.any_hit("nothing here", cues.PRAYER) is False


def test_the_cue_lists_reproduce_the_fingerprint(expected):
    cues = imports_moved("cues")
    named = ("SCRIPTURE", "PRAYER", "COMMUNION", "COMMUNION_INVITATION", "QA",
             "ANNOUNCEMENTS", "GREETING_OPENERS", "PREAMBLE")
    matches_the_fingerprint(
        expected, "cues.lists",
        {"version": cues.VERSION, **{name: getattr(cues, name) for name in named}},
    )


def test_the_chapter_cue_stays_out_of_the_scripture_list():
    cues = imports_moved("cues")
    assert cues.count_hits("wait a couple of chapters to flesh it out", cues.SCRIPTURE) == 0




def builds_envelope_levels():
    spec = reads_fixture("service.envelope.json")
    doc = reads_recording("service")
    hz = spec["hz"]
    frames = int(doc["duration"] * hz)
    level = np.full(frames, spec["floor_db"], dtype=np.float64)
    for start, end, loud in spec["sections"]:
        speaking = [
            utterance for utterance in doc["utterances"]
            if utterance["start"] >= start and utterance["end"] <= end
        ]
        for utterance in speaking:
            level[int(utterance["start"] * hz):int(utterance["end"] * hz)] = loud
    ripple = spec["ripple_db"] * np.sin(np.arange(frames) / 7.0)
    return hz, level + ripple


def builds_envelope():
    hz, level = builds_envelope_levels()
    return hz, np.power(10.0, level / 20.0).astype(np.float32)


def writes_raw_signal(path):
    hz, envelope = builds_envelope()
    win = 16_000 // hz
    amplitude = np.round(envelope.astype(np.float64) * 32_767.0).astype(np.int16)
    sign = np.tile(np.array([1, -1], dtype=np.int16), win // 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.outer(amplitude, sign).astype(np.int16).tobytes())
    return amplitude


def test_the_envelope_of_a_synthesised_signal_reports_its_frame_energy(tmp_path, expected):
    audio = imports_moved("audio")
    raw = tmp_path / "signal.raw"
    amplitude = writes_raw_signal(raw)
    found = audio.envelope(raw, 100)
    assert len(found) == len(amplitude)
    assert np.abs(found - amplitude.astype(np.float64)).max() < 0.5
    matches_the_fingerprint(expected, "audio.envelope", {
        "frames": int(len(found)),
        "head": [round(float(value), 3) for value in found[:8]],
        "percentiles": [round(float(np.percentile(found, at)), 3)
                        for at in (5, 25, 50, 75, 95)],
    })


def test_a_gain_scaled_excerpt_correlates_at_the_offset_it_was_cut_from(expected):
    audio = imports_moved("audio")
    _, envelope = builds_envelope()
    long = envelope[:120_000].astype(np.float64)
    short = long[61_000:67_000] * 0.37
    correlation = audio.ncc(long, short)
    offset, best, ratio = audio.peak_and_ratio(correlation, guard=500)
    assert offset == 61_000
    assert best == pytest.approx(1.0, abs=1e-6)
    matches_the_fingerprint(expected, "audio.ncc", {
        "length": int(len(correlation)),
        "offset": offset,
        "best": round(best, 5),
        "ratio_exceeds": ratio > 1.001,
    })


def test_correlating_refuses_an_excerpt_longer_than_the_recording():
    audio = imports_moved("audio")
    with pytest.raises(ValueError, match="longer than long"):
        audio.ncc(np.ones(5), np.ones(6))


def test_correlating_refuses_a_flat_excerpt():
    audio = imports_moved("audio")
    with pytest.raises(ValueError, match="flat"):
        audio.ncc(np.ones(50), np.ones(6))


def test_the_runner_up_is_zero_when_the_guard_masks_the_whole_correlation():
    audio = imports_moved("audio")
    offset, best, ratio = audio.peak_and_ratio(np.array([0.1, 0.9, 0.2]), guard=10)
    assert (offset, best) == (1, 0.9)
    assert ratio == float("inf")


def test_the_quiet_spans_of_the_synthesised_signal_reproduce_the_fingerprint(expected):
    audio = imports_moved("audio")
    hz, envelope = builds_envelope()
    mask, threshold = audio.quiet_mask(envelope)
    runs = audio.quiet_runs(envelope, hz)
    matches_the_fingerprint(expected, "audio.quiet", {
        "threshold": round(float(threshold), 3),
        "quiet_frames": int(mask.sum()),
        "runs": runs,
    })


def test_a_quiet_span_shorter_than_the_minimum_is_not_a_place_to_cut():
    audio = imports_moved("audio")
    levels = np.full(10_000, -10.0)
    levels[:5_000] = -60.0
    levels[9_900:9_950] = -60.0
    assert audio.quiet_runs(np.power(10.0, levels / 20.0), 100) == [
        {"start": 0.0, "end": 50.0}
    ]


class DecodesLikeFfmpeg:
    def __init__(self, samples=b"\x01\x00\x02\x00"):
        self.samples = samples
        self.commands = []

    def __call__(self, command, **options):
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(self.samples)
        return subprocess.CompletedProcess(command, 0)


def test_decoding_builds_the_command_the_fingerprint_pins(
    tmp_path, monkeypatch, expected
):
    audio = imports_moved("audio")
    decoder = DecodesLikeFfmpeg()
    monkeypatch.setattr(audio.subprocess, "run", decoder)
    produced = audio.decode(Path("/src/a.flac"), tmp_path / "raw" / "a.raw")
    assert produced.read_bytes() == decoder.samples
    matches_the_fingerprint(expected, "audio.decode", [
        [part.replace(str(tmp_path), "TMP") for part in command]
        for command in decoder.commands
    ])


def test_an_uncached_envelope_is_decoded_once_and_kept_for_the_next_call(
    tmp_path, monkeypatch
):
    audio = imports_moved("audio")
    decoder = DecodesLikeFfmpeg(np.arange(1_600, dtype=np.int16).tobytes())
    monkeypatch.setattr(audio.subprocess, "run", decoder)
    work = tmp_path / "work"
    first = audio.cached_envelope(Path("/src/a.flac"), work, 100, "tag")
    assert len(decoder.commands) == 1
    assert (work / "env" / "tag.100hz.npy").exists()
    second = audio.cached_envelope(Path("/src/a.flac"), work, 100, "tag")
    assert len(decoder.commands) == 1
    assert second.tolist() == first.tolist()


def test_decoding_reuses_an_output_that_is_already_there(tmp_path):
    audio = imports_moved("audio")
    already = tmp_path / "already.raw"
    already.write_bytes(b"\x01\x02")
    assert audio.decode(tmp_path / "missing.flac", already) == already


def test_a_cached_envelope_is_read_back_rather_than_recomputed(tmp_path):
    audio = imports_moved("audio")
    work = tmp_path / "work"
    (work / "env").mkdir(parents=True)
    np.save(work / "env" / "tag.50hz.npy", np.arange(4, dtype=np.float32))
    found = audio.cached_envelope(tmp_path / "missing.flac", work, 50, "tag")
    assert found.tolist() == [0.0, 1.0, 2.0, 3.0]




def builds_decibels():
    acoustic = imports_moved("acoustic")
    _, envelope = builds_envelope()
    return acoustic.to_db(envelope)


def test_the_decibel_conversion_floors_silence_rather_than_diverging():
    acoustic = imports_moved("acoustic")
    converted = acoustic.to_db(np.array([0.0, 1e-9, 1.0], dtype=np.float32))
    assert converted.tolist() == pytest.approx([-120.0, -120.0, 0.0])


def test_the_pauses_in_the_synthesised_envelope_reproduce_the_fingerprint(expected):
    acoustic = imports_moved("acoustic")
    found = acoustic.find_pauses(builds_decibels(), 2400.0, 3000.0)
    matches_the_fingerprint(expected, "acoustic.find_pauses", found)


def test_a_window_too_short_for_its_own_context_finds_no_pauses():
    acoustic = imports_moved("acoustic")
    assert acoustic.find_pauses(builds_decibels(), 2400.0, 2440.0) == []


def test_the_level_rises_in_the_synthesised_envelope_reproduce_the_fingerprint(expected):
    acoustic = imports_moved("acoustic")
    rises = acoustic.level_rise(builds_decibels(), 2400.0, 3000.0)
    matches_the_fingerprint(expected, "acoustic.level_rise", {
        "count": len(rises),
        "top": [{"t": round(rise["t"], 3), "step": round(rise["step"], 4)}
                for rise in rises[:5]],
    })


def test_an_empty_window_yields_no_level_rise():
    acoustic = imports_moved("acoustic")
    assert acoustic.level_rise(builds_decibels(), 2400.0, 2400.0) == []


def test_the_ranked_punch_outs_reproduce_the_fingerprint(expected):
    acoustic = imports_moved("acoustic")
    matches_the_fingerprint(
        expected, "acoustic.punch_out_candidates",
        acoustic.punch_out_candidates(builds_decibels(), 2400.0, 3000.0),
    )


def test_no_level_rise_leaves_no_punch_out_candidate():
    acoustic = imports_moved("acoustic")
    assert acoustic.punch_out_candidates(builds_decibels(), 2400.0, 2400.0) == []




class RecordsCommands:
    def __init__(self, reply=""):
        self.reply = reply
        self.commands = []

    def __call__(self, command):
        self.commands.append(list(command))
        return self.reply


MEASURED = json.dumps({
    "input_i": "-23.10", "input_tp": "-6.20", "input_lra": "9.40",
    "input_thresh": "-33.30", "target_offset": "0.30",
})


@pytest.fixture
def recorded_ffmpeg(monkeypatch):
    render = imports_moved("render")
    recorder = RecordsCommands(f"some log\n{MEASURED}\ntrailing log\n")
    monkeypatch.setattr(render, "_run", recorder)
    return render, recorder


def test_the_measurement_pass_builds_the_command_the_fingerprint_pins(
    recorded_ffmpeg, expected
):
    render, recorder = recorded_ffmpeg
    measured = render.measure(Path("/src/a.flac"), 12.5, 3600.0)
    assert measured["input_i"] == "-23.10"
    matches_the_fingerprint(expected, "render.measure", recorder.commands)


def test_a_measurement_pass_that_printed_no_json_is_refused(monkeypatch):
    render = imports_moved("render")
    monkeypatch.setattr(render, "_run", RecordsCommands("no json at all"))
    with pytest.raises(RuntimeError, match="no JSON"):
        render.measure(Path("/src/a.flac"), 0.0, 1.0)


@pytest.mark.parametrize(
    ("loudness", "fades"),
    [(True, True), (True, False), (False, True), (False, False)],
    ids=["both", "loudness-only", "fades-only", "neither"],
)
def test_the_render_pass_builds_the_command_the_fingerprint_pins(
    loudness, fades, recorded_ffmpeg, tmp_path, expected
):
    render, recorder = recorded_ffmpeg
    render.render(Path("/src/a.flac"), 12.5, 3612.5, tmp_path / "out" / "a.mp3",
                  loudness=loudness, fades=fades)
    label = f"{'loud' if loudness else 'flat'}-{'faded' if fades else 'hard'}"
    matches_the_fingerprint(
        expected, f"render.render.{label}",
        [[part.replace(str(tmp_path), "TMP") for part in command]
         for command in recorder.commands],
    )


def test_the_render_pass_creates_the_directory_its_output_goes_in(
    recorded_ffmpeg, tmp_path
):
    render, _ = recorded_ffmpeg
    destination = tmp_path / "deep" / "deeper" / "a.mp3"
    render.render(Path("/src/a.flac"), 0.0, 1.0, destination, loudness=False)
    assert destination.parent.is_dir()


def test_the_loudness_probe_reads_the_last_summary_ffmpeg_printed(monkeypatch, expected):
    render = imports_moved("render")
    monkeypatch.setattr(render, "_run", RecordsCommands(
        "  I:         -20.0 LUFS\n  LRA:         9.0 LU\n"
        "Summary:\n  I:         -16.1 LUFS\n  Threshold: -26.4 LUFS\n"
        "  LRA:         7.3 LU\n  Peak:       -1.6 dBFS\n"
    ))
    matches_the_fingerprint(expected, "render.probe_loudness",
                            render.probe_loudness(Path("/out/a.mp3")))


def test_a_loudness_summary_ffmpeg_never_printed_reports_nothing(monkeypatch):
    render = imports_moved("render")
    monkeypatch.setattr(render, "_run", RecordsCommands("nothing useful here"))
    assert render.probe_loudness(Path("/out/a.mp3")) == {}


def test_an_unreadable_loudness_figure_is_dropped_rather_than_raising(monkeypatch):
    render = imports_moved("render")
    monkeypatch.setattr(render, "_run", RecordsCommands("  I:  not-a-number LUFS\n"))
    assert render.probe_loudness(Path("/out/a.mp3")) == {}


def test_the_format_probe_reads_what_ffprobe_reported(monkeypatch, expected):
    render = imports_moved("render")
    probed = json.dumps({
        "streams": [{"channels": 1, "sample_rate": "44100"}],
        "format": {"duration": "3600.123", "bit_rate": "101456", "size": "45678901"},
    })
    recorded = []

    def runs(command, **options):
        recorded.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout=probed, stderr="")

    monkeypatch.setattr(render.subprocess, "run", runs)
    matches_the_fingerprint(expected, "render.probe_format", {
        "command": recorded[0] if recorded else None,
        "probed": render.probe_format(Path("/out/a.mp3")),
    })




@pytest.mark.parametrize(
    ("seconds", "rendered"),
    [(0.0, "0:00:00"), (59.9, "0:00:59"), (3600.0, "1:00:00"), (5747.058, "1:35:47")],
)
def test_the_clock_renders_seconds_as_hours_minutes_seconds(seconds, rendered):
    classify = imports_moved("classify")
    assert classify.hms(seconds) == rendered


@pytest.mark.parametrize("name", RECORDINGS)
def test_rendering_a_transcript_for_a_prompt_reproduces_the_fingerprint(name, expected):
    classify = imports_moved("classify")
    rendered = classify.render_transcript(reads_recording(name))
    matches_the_fingerprint(expected, f"classify.render_transcript.{name}", {
        "digest": hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:32],
        "lines": rendered.count("\n") + 1,
        "silences": rendered.count("--- silence "),
        "head": rendered.split("\n")[:3],
    })


@pytest.mark.parametrize(
    ("reply", "parsed"),
    [
        ("fenced", {"blocks": [{"start": 1, "end": 2, "type": "sermon"}]}),
        ("fenced_with_trailer", {"blocks": [], "segments": []}),
        ("thought", {"blocks": []}),
        ("prose", {"blocks": [], "segments": []}),
        ("bare", {"blocks": [], "segments": []}),
        ("unparseable", None),
        ("truncated", None),
    ],
)
def test_parsing_a_model_reply_recovers_the_object_or_reports_nothing(reply, parsed):
    classify = imports_moved("classify")
    assert classify.parse_json(reads_fixture("model_replies.json")[reply]) == parsed


def test_coercing_a_model_reply_into_range_reproduces_the_fingerprint(expected):
    classify = imports_moved("classify")
    matches_the_fingerprint(expected, "classify.coerce_blocks", classify.coerce_blocks(
        reads_fixture("model_replies.json")["coercible"], reads_recording("service")
    ))


class AnswersLikeAModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, model, prompt, think=False):
        self.prompts.append({"model": model, "prompt": prompt, "think": think})
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


def test_an_unparseable_reply_is_retried_up_to_the_repair_budget(monkeypatch):
    classify = imports_moved("classify")
    host = AnswersLikeAModel(["not json"])
    monkeypatch.setattr(classify, "ollama", host)
    assert classify.call_json("a-model", "ask") == (None, 2)
    assert len(host.prompts) == 3
    assert [
        "was not valid JSON" in asked["prompt"] for asked in host.prompts
    ] == [False, True, True]


def test_a_reply_that_parses_on_a_retry_reports_how_many_repairs_it_cost(monkeypatch):
    classify = imports_moved("classify")
    monkeypatch.setattr(classify, "ollama", AnswersLikeAModel(["not json", '{"ok": 1}']))
    assert classify.call_json("a-model", "ask") == ({"ok": 1}, 1)


def test_a_host_that_cannot_be_reached_is_not_retried(monkeypatch):
    classify = imports_moved("classify")
    calls = []

    def refuses(model, prompt, think=False):
        calls.append(prompt)
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(classify, "ollama", refuses)
    assert classify.call_json("a-model", "ask") == (None, 0)
    assert len(calls) == 1


class AnswersLikeAHost:
    def __init__(self, replies, refuse_format=False):
        self.replies = list(replies)
        self.refuse_format = refuse_format
        self.bodies = []
        self.urls = []
        self.requests = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.bodies.append(body)
        self.urls.append(request.full_url)
        self.requests.append(request)
        if self.refuse_format and "format" in body:
            raise urllib.error.HTTPError(
                request.full_url, 501, "structured output is unavailable", {}, None
            )
        return self

    def __enter__(self):
        return self

    def __exit__(self, *failure):
        return False

    def read(self):
        return json.dumps(
            {"response": self.replies[min(len(self.bodies) - 1, len(self.replies) - 1)]}
        ).encode()


CONFIGURED_ENDPOINT = "http://mac-m1:11434"
HARDCODED_HOST = re.compile(r"https?://|localhost|mac-m1", re.I)
UNANSWERED_HOST = [
    ConnectionRefusedError(61, "Connection refused"),
    TimeoutError("timed out"),
    urllib.error.URLError("connection refused"),
    OSError(65, "No route to host"),
]


@pytest.mark.parametrize("think", [False, True], ids=["unthinking", "thinking"])
def test_one_generation_sends_the_body_the_fingerprint_pins(think, monkeypatch, expected):
    classify = imports_moved("classify")
    host = AnswersLikeAHost(['{"ok": 1}'])
    monkeypatch.setattr(classify, "ENDPOINT", CONFIGURED_ENDPOINT)
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    assert classify.ollama("a-model", "ask", think=think) == '{"ok": 1}'
    label = "thinking" if think else "unthinking"
    matches_the_fingerprint(expected, f"classify.ollama.{label}", host.bodies)


def test_a_host_refusing_structured_output_is_retried_without_the_constraint(
    monkeypatch, capsys
):
    classify = imports_moved("classify")
    host = AnswersLikeAHost(['{"ok": 1}'], refuse_format=True)
    monkeypatch.setattr(classify, "ENDPOINT", CONFIGURED_ENDPOINT)
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    assert classify.ollama("a-model", "ask") == '{"ok": 1}'
    assert [("format" in body) for body in host.bodies] == [True, False]
    assert "structured output refused" in capsys.readouterr().out


def test_a_host_failure_that_is_not_a_refused_constraint_is_raised(monkeypatch):
    classify = imports_moved("classify")
    monkeypatch.setattr(classify, "ENDPOINT", CONFIGURED_ENDPOINT)

    def fails(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(classify.urllib.request, "urlopen", fails)
    with pytest.raises(urllib.error.HTTPError):
        classify.ollama("a-model", "ask")


def posts_one_generation(classify, monkeypatch, endpoint, host=None):
    host = host or AnswersLikeAHost(['{"ok": 1}'])
    monkeypatch.setattr(classify, "ENDPOINT", endpoint)
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    assert classify.ollama("a-model", "ask") == '{"ok": 1}'
    return host


@pytest.mark.parametrize(
    ("endpoint", "posted"),
    [
        ("http://mac-m1:11434", "http://mac-m1:11434/api/generate"),
        ("http://mac-m1:11434/", "http://mac-m1:11434/api/generate"),
        ("https://mac-m1:11434/v1", "https://mac-m1:11434/api/generate"),
    ],
)
def test_one_generation_posts_to_api_generate_on_the_configured_host(
    endpoint, posted, monkeypatch
):
    classify = imports_moved("classify")
    host = posts_one_generation(classify, monkeypatch, endpoint)
    assert host.urls == [posted]
    assert all("localhost" not in url for url in host.urls)


def test_a_substituted_model_endpoint_needs_no_change_to_the_process_environment(monkeypatch):
    classify = imports_moved("classify")
    substitute = "http://127.0.0.1:1"
    host = posts_one_generation(classify, monkeypatch, substitute)
    assert host.urls == ["http://127.0.0.1:1/api/generate"]
    assert "SERMON_MODEL_ENDPOINT" not in os.environ


def test_nothing_in_the_pipeline_hardcodes_a_host():
    pipeline = PROJECT_ROOT / "src" / "sermon" / "pipeline"
    offenders = []
    for path in sorted(pipeline.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if HARDCODED_HOST.search(node.value):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{node.value}"
                    )
    assert offenders == []


def test_generation_holds_no_credentials_for_the_machine_serving_the_model(monkeypatch):
    classify = imports_moved("classify")
    host = posts_one_generation(classify, monkeypatch, CONFIGURED_ENDPOINT)
    headers = {
        key.lower(): value for key, value in host.requests[0].header_items()
    }
    assert "authorization" not in headers
    assert {key for key in headers if any(part in key for part in ("auth", "token", "key"))} == set()


SHELL_MODULES = {"subprocess", "paramiko", "pexpect", "fabric", "shlex"}
SHELL_ATTRS = {("os", "system"), ("os", "popen"), ("posix", "system")}
REACHES_THE_MODEL = (
    PROJECT_ROOT / "src" / "sermon" / "pipeline" / "classify.py",
    PROJECT_ROOT / "src" / "sermon" / "binds_model_endpoint.py",
)


def modules_bound_in(tree):
    bound = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound[alias.asname or alias.name.split(".")[0]] = (
                    alias.name.split(".")[0],
                    None,
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module.split(".")[0]
            for alias in node.names:
                bound[alias.asname or alias.name] = (module, alias.name)
    return bound


def callee_of(node, bound):
    if isinstance(node, ast.Name):
        return bound.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        held = bound.get(node.value.id)
        return ((held[0] if held else node.value.id), node.attr)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        held = callee_of(node.args[0], bound)
        module = held[0] if held else (
            node.args[0].id if isinstance(node.args[0], ast.Name) else None
        )
        if module:
            return (module, node.args[1].value)
    return None


def is_ssh_program(value):
    if not isinstance(value, str) or not value.strip():
        return False
    program = value.strip().split()[0]
    return program == "ssh" or program.endswith("/ssh")


def carries_ssh(node):
    if isinstance(node, ast.Constant):
        return is_ssh_program(node.value)
    if isinstance(node, ast.JoinedStr):
        return any(carries_ssh(part) for part in node.values)
    if isinstance(node, ast.FormattedValue):
        return carries_ssh(node.value)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(carries_ssh(elt) for elt in node.elts)
    return False


def names_a_shell(callee):
    return callee is not None and (callee[0] in SHELL_MODULES or callee in SHELL_ATTRS)


def opens_a_shell_on_the_model_host(tree):
    bound = modules_bound_in(tree)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                f"{node.lineno}:import {alias.name.split('.')[0]}"
                for alias in node.names
                if alias.name.split(".")[0] in SHELL_MODULES
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module.split(".")[0]
            if module in SHELL_MODULES:
                offenders.append(f"{node.lineno}:from {module}")
            offenders.extend(
                f"{node.lineno}:from {module} import {alias.name}"
                for alias in node.names
                if (module, alias.name) in SHELL_ATTRS
            )
        elif isinstance(node, ast.Call):
            named = callee_of(node.func, bound)
            if names_a_shell(named):
                offenders.append(f"{node.lineno}:{named[0]}.{named[1]}")
            elif any(
                carries_ssh(arg)
                for arg in (*node.args, *(kw.value for kw in node.keywords))
            ):
                offenders.append(f"{node.lineno}:ssh")
    return offenders


def test_classification_never_opens_a_shell_on_the_model_host():
    offenders = []
    for path in REACHES_THE_MODEL:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(
            f"{path.relative_to(PROJECT_ROOT)}:{found}"
            for found in opens_a_shell_on_the_model_host(tree)
        )
    assert offenders == []


@pytest.mark.parametrize(
    "source",
    [
        'import os\nos.system("ssh mac-m1")\n',
        'import os\nos.popen("ssh mac-m1")\n',
        'import posix\nposix.system("ssh mac-m1")\n',
        'import subprocess\nsubprocess.run(["ssh", "mac-m1"])\n',
        'from os import system\nsystem("echo hi")\n',
        'import os\ngetattr(os, "system")("ssh mac-m1")\n',
        'run("/usr/bin/ssh", "mac-m1")\n',
    ],
)
def test_a_shell_out_to_the_model_host_fails_the_http_only_guard(source):
    assert opens_a_shell_on_the_model_host(ast.parse(source))


@pytest.mark.parametrize("path", REACHES_THE_MODEL, ids=lambda path: path.name)
def test_the_http_only_guard_reads_call_sites_not_just_imports(path):
    source = path.read_text(encoding="utf-8")
    assert opens_a_shell_on_the_model_host(ast.parse(source)) == []
    mutated = source + '\nimport os\nos.system("ssh mac-m1 ollama run")\n'
    assert opens_a_shell_on_the_model_host(ast.parse(mutated))


@pytest.mark.parametrize("unanswered", UNANSWERED_HOST, ids=lambda one: type(one).__name__)
def test_an_unanswered_model_endpoint_is_named_rather_than_a_generic_model_error(
    unanswered, monkeypatch
):
    classify = imports_moved("classify")
    monkeypatch.setattr(classify, "ENDPOINT", CONFIGURED_ENDPOINT)

    def does_not_answer(request, timeout=None):
        raise unanswered

    monkeypatch.setattr(classify.urllib.request, "urlopen", does_not_answer)
    with pytest.raises(ModelEndpointUnreachable) as unreachable:
        classify.ollama("a-model", "ask")
    assert CONFIGURED_ENDPOINT in str(unreachable.value)
    assert unreachable.value.endpoint == CONFIGURED_ENDPOINT
    assert unreachable.value.__cause__ is unanswered


def test_an_unset_endpoint_is_named_rather_than_posted_to_a_hardcoded_host(monkeypatch):
    classify = imports_moved("classify")
    host = AnswersLikeAHost(['{"ok": 1}'])
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    with pytest.raises(UnusableConfiguration) as refused:
        classify.ollama("a-model", "ask")
    assert "ENDPOINT" in str(refused.value)
    assert host.bodies == []


@pytest.mark.parametrize("endpoint", ["ssh://mac-m1", "mac-m1:11434", "file:///models"])
def test_generation_refuses_an_endpoint_reached_over_anything_but_http(endpoint, monkeypatch):
    classify = imports_moved("classify")
    host = AnswersLikeAHost(['{"ok": 1}'])
    monkeypatch.setattr(classify, "ENDPOINT", endpoint)
    monkeypatch.setattr(classify.urllib.request, "urlopen", host)
    with pytest.raises(UnusableConfiguration):
        classify.ollama("a-model", "ask")
    assert host.bodies == []


@pytest.fixture
def prompted(monkeypatch, diarized):
    classify = imports_moved("classify")
    segments = imports_moved("segments")
    monkeypatch.setattr(classify, "PROMPTS", PROMPTS)
    monkeypatch.setattr(classify, "DATA", diarized)
    monkeypatch.setattr(segments, "DATA_ROOT", diarized)
    return classify


def summarises_prompts(host):
    return [
        {"model": asked["model"], "think": asked["think"],
         "characters": len(asked["prompt"]),
         "digest": hashlib.sha256(asked["prompt"].encode("utf-8")).hexdigest()[:32]}
        for asked in host.prompts
    ]


def test_the_whole_transcript_strategy_reproduces_the_fingerprint(
    prompted, monkeypatch, expected
):
    fixture = reads_fixture("service.blocks.json")
    host = AnswersLikeAModel([json.dumps({"blocks": fixture["blocks"],
                                          "segments": fixture["model_segments"]})])
    monkeypatch.setattr(prompted, "ollama", host)
    produced = prompted.run_whole("a-model", reads_recording("service"))
    matches_the_fingerprint(expected, "classify.run_whole",
                            {"prompts": summarises_prompts(host), "produced": produced})


def test_a_whole_transcript_reply_that_never_parses_reports_invalid_json(
    prompted, monkeypatch
):
    monkeypatch.setattr(prompted, "ollama", AnswersLikeAModel(["not json"]))
    produced = prompted.run_whole("a-model", reads_recording("service"))
    assert produced["status"] == "invalid-json"
    assert produced["repairs"] == prompted.MAX_REPAIRS


def test_the_structured_strategy_reproduces_the_fingerprint(
    prompted, monkeypatch, expected
):
    host = AnswersLikeAModel([json.dumps({
        "blocks": [{"index": 3, "type": "sermon", "confidence": 0.95,
                    "evidence": "the teaching"}],
        "segments": [{"punch_in": 600.0, "punch_out": 2700.0}],
    })])
    monkeypatch.setattr(prompted, "ollama", host)
    produced = prompted.run_structured("a-model", reads_recording("service"))
    matches_the_fingerprint(expected, "classify.run_structured",
                            {"prompts": summarises_prompts(host), "produced": produced})


def test_the_structured_strategy_stops_when_the_recording_was_never_diarized(
    prompted, undiarized, monkeypatch
):
    monkeypatch.setattr(prompted, "DATA", undiarized)
    monkeypatch.setattr(prompted, "ollama", AnswersLikeAModel(["{}"]))
    produced = prompted.run_structured("a-model", reads_recording("service"))
    assert produced["status"] == "no-diarization"


def test_the_per_block_strategy_reproduces_the_fingerprint(
    prompted, monkeypatch, expected
):
    host = AnswersLikeAModel([json.dumps(
        {"type": "sermon", "confidence": 0.8, "evidence": "teaching"}
    )])
    monkeypatch.setattr(prompted, "ollama", host)
    produced = prompted.run_perblock("a-model", reads_recording("service"))
    matches_the_fingerprint(expected, "classify.run_perblock",
                            {"prompts": summarises_prompts(host), "produced": produced})


def test_a_recording_that_exhausts_its_budget_reports_the_blocks_never_reached(
    prompted, monkeypatch
):
    monkeypatch.setattr(prompted, "RECORDING_BUDGET_S", -1)
    monkeypatch.setattr(prompted, "ollama", AnswersLikeAModel(["{}"]))
    produced = prompted.run_perblock("a-model", reads_recording("service"))
    assert produced["status"].startswith("budget-exhausted:")
    assert all(block["confidence"] == 0.0 for block in produced["blocks"])




def renders_constant(value):
    if isinstance(value, (set, frozenset)):
        return f"{{{', '.join(sorted(repr(held) for held in value))}}}"
    return repr(value)


def is_a_constant(module, name, value):
    return (
        name.isupper()
        and not name.startswith("_")
        and not isinstance(value, ModuleType)
        and (module, name) not in INJECTED
    )


def constants_of(module):
    carried = imports_moved(module)
    return {
        name: renders_constant(getattr(carried, name))
        for name in sorted(vars(carried))
        if is_a_constant(module, name, getattr(carried, name))
    }


def test_every_constant_in_the_moved_library_reproduces_the_fingerprint(expected):
    matches_the_fingerprint(
        expected, "constants", {module: constants_of(module) for module in MOVED}
    )


def is_not_first_party(directory):
    return (
        directory.name in ("__pycache__", "site-packages", "node_modules")
        or directory.name.endswith(".egg-info")
        or (directory / "pyvenv.cfg").is_file()
    )


def first_party_sources(path):
    if path.is_file():
        if path.suffix == ".py":
            yield path
    elif path.is_dir() and not is_not_first_party(path):
        for held in sorted(path.iterdir()):
            yield from first_party_sources(held)


def names_read_anywhere():
    read = set()
    for root in SEARCHED:
        for path in first_party_sources(root):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    read.add(node.id)
                elif isinstance(node, ast.Attribute):
                    read.add(node.attr)
    return read


def test_the_constants_no_code_reads_are_the_ones_the_fingerprint_names(expected):
    read = names_read_anywhere()
    unread = sorted(
        f"{module}.{name}"
        for module in MOVED
        for name in constants_of(module)
        if name not in read
    )
    matches_the_fingerprint(expected, "constants.unread", unread)
