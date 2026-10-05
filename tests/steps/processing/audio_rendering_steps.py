"""What the render chain produces, measured on the MP3 it wrote."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from pytest_bdd import given, parsers, then, when

from steps import _rendering

from sermon.extends_segment_span import ReadsTimecode
from sermon.jobs.renders_mp3 import CEILING_TP, PUBLISHED_I, TOLERANCE_LU
from sermon.pipeline.render import TARGET_I, TARGET_LRA, TARGET_TP
from sermon.store import Artifact, Job, Recording, RemovedSpan, Reviewer, Segment, layout

READS = ReadsTimecode()
STARTED_AT = datetime(2026, 8, 23, 10, 29, tzinfo=UTC)
PUBLISHED_ON = date(2026, 8, 23)
LABEL = "Hebrews 12.4-11"
LEVEL_TOLERANCE_DB = 1.5
LOUDNESS_TOLERANCE_LU = 1.0
FULL_SCALE_DBFS = 0.0
LOUDNESS_KEYS = ("loudness_lufs", "true_peak_dbtp", "loudness_range_lu")
CONSTANT_RATE_FRAME_SIZES = 2
REFERENCE_SECONDS = 1.0
FADE_ATTENUATION_DB = 3.0
FADE_HEADROOM_DB = 2.5
ORDERED_MARGIN_DB = 6.0
CLIPPING_TOLERANCE_DB = 0.3


@pytest.fixture
def rendering():
    return {}


def _registers(store, recording_id, object_key):
    return store.saves(
        Recording(
            recording_id=recording_id,
            object_key=object_key,
            state="reviewed",
            started_at=STARTED_AT,
            started_at_source="key",
            size_bytes=1,
        )
    )


def _approves(store, recording, punch_in, punch_out, label=LABEL):
    segment = store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=punch_in,
            span_end_seconds=punch_out,
            punch_in_seconds=punch_in,
            punch_out_seconds=punch_out,
            publication_date=PUBLISHED_ON,
            label=label,
            boundary_source="human",
        )
    )
    store.saves(
        Job(
            recording_id=recording.recording_id,
            segment_id=segment.segment_id,
            kind="render",
            state="queued",
            max_attempts=5,
            dedupe_key=f"render:{segment.segment_id}",
            queued_at=STARTED_AT,
        )
    )
    return segment


def _stages(store, recording, variant, rendering):
    held = _rendering.source(variant)
    placed = store.saves(replace(recording, local_path=layout.source_path(recording)))
    _rendering.places(held, store.resolves(placed))
    probed = _rendering.probes(store, placed)
    rendering["variant"] = variant
    rendering["source"] = store.resolves(probed)
    return probed


def _renders(store, rendering, reuse=True):
    produced = _rendering.renders(store, reuse=reuse)
    if produced is None:
        raise AssertionError("no render job ran")
    rendering.setdefault("renders", []).append(produced)
    return produced


def _restages(store, rendering, variant):
    recording = store.lists(Recording)[0]
    return _stages(store, recording, variant, rendering)


def _taken(source):
    return _rendering.loudness(source, filters="pan=mono|c0=c0")


def _after(segment):
    return segment.punch_in_seconds


def _speech_level(path, after, offset=0.0):
    start, length = _rendering.speech_window(after)
    return _rendering.level_db(path, start - offset, length)


def _quiet_level(path, after, offset=0.0):
    start, length = _rendering.quiet_window(after)
    return _rendering.level_db(path, start - offset, length)


def _floor_level(path, after, offset=0.0):
    start, length = _rendering.floor_window(after)
    return _rendering.level_db(path, start - offset, length)


def _carries_the_structure(path, after, offset=0.0):
    """Silence, then a quiet passage, then speech, where the source puts them."""
    floor = _floor_level(path, after, offset)
    quiet = _quiet_level(path, after, offset)
    speech = _speech_level(path, after, offset)
    return floor <= quiet - ORDERED_MARGIN_DB and quiet <= speech - ORDERED_MARGIN_DB


@given(
    parsers.parse('an approved Segment with punch-in "{punch_in}" and punch-out "{punch_out}"'),
    target_fixture="segment",
)
def _(store, punch_in, punch_out):
    store.saves(Reviewer(actor=_rendering.REVIEWER, receives_notifications=True))
    recording = _registers(
        store, "recording_20260823_102900", "recordings/recording_20260823_102900.flac"
    )
    return _approves(store, recording, READS(punch_in), READS(punch_out))


@given("the source is FLAC 44.1 kHz stereo 32-bit")
def _(store, rendering):
    probed = _stages(store, store.lists(Recording)[0], "default", rendering)
    if (probed.sample_rate, probed.channels) != (44100, 2):
        raise AssertionError(f"staged {probed.sample_rate} Hz, {probed.channels} channels")
    store.saves(replace(probed, bits_per_raw_sample=32))


@given("channel 2 of the source is silent")
def _(store):
    recording = store.lists(Recording)[0]
    quiet = [level.channel for level in recording.channel_levels if level.rms_db <= -80.0]
    if quiet != [2] or recording.mono_source != "channel 1":
        raise AssertionError(f"{recording.channel_levels} chose {recording.mono_source}")


@when("the render runs", target_fixture="rendered")
def _(store, rendering):
    return _renders(store, rendering)


@then("the output takes channel 1 only")
def _(rendered, rendering):
    assert abs(rendered.input_loudness_lufs - _taken(rendering["source"])["I"]) <= LOUDNESS_TOLERANCE_LU


@then("channel 2 is discarded without being mixed in")
def _(rendered, rendering):
    mixed = _rendering.loudness(rendering["source"], filters="pan=mono|c0=0.5*c0+0.5*c1")
    assert rendered.input_loudness_lufs - mixed["I"] >= 5.0


@then("the output level matches channel 1's level, not half of it")
def _(rendered, rendering):
    mixed = _rendering.loudness(rendering["source"], filters="pan=mono|c0=0.5*c0+0.5*c1")
    taken = _taken(rendering["source"])
    assert abs(rendered.input_loudness_lufs - taken["I"]) < abs(
        rendered.input_loudness_lufs - mixed["I"]
    )


@then("the output is mono")
def _(rendered):
    assert rendered.channels == 1


@then("the output begins at the approved punch-in")
def _(segment, rendered, rendering):
    after = _after(segment)
    assert _carries_the_structure(rendering["source"], after)
    assert _carries_the_structure(rendered.path, after, offset=segment.punch_in_seconds)


@then("the output ends at the approved punch-out")
def _(segment, rendered, rendering):
    punch_out = segment.punch_out_seconds
    after = punch_out - 2 * _rendering.CYCLE_SECONDS - 1
    assert _carries_the_structure(rendering["source"], after)
    assert _carries_the_structure(
        rendered.path, after, offset=punch_out - rendered.duration_seconds
    )


@then("the output duration matches the approved span within 100 ms")
def _(segment, rendered):
    span = segment.punch_out_seconds - segment.punch_in_seconds
    assert abs(rendered.duration_seconds - span) <= 0.1


@then("the trim is sample-accurate rather than snapped to a frame boundary")
def _(segment, rendered, rendering):
    frames = segment.punch_in_seconds / _rendering.MP3_FRAME_SECONDS
    assert abs(frames - round(frames)) > 0.1
    snapped = round(frames) * _rendering.MP3_FRAME_SECONDS
    assert _rendering.renders_span(
        rendering["source"], snapped, snapped + rendered.duration_seconds
    ).read_bytes() != rendered.path.read_bytes()


def _opening_attenuation(rendered, source, punch_in, length):
    """How much quieter the output's first `length` is than the same source audio."""
    return (
        _rendering.level_db(rendered.path, 0.0, length)
        - _rendering.level_db(rendered.path, 0.0, REFERENCE_SECONDS)
    ) - (
        _rendering.level_db(source, punch_in, length)
        - _rendering.level_db(source, punch_in, REFERENCE_SECONDS)
    )


def _closing_attenuation(rendered, source, punch_out, length):
    return (
        _rendering.tail_level_db(rendered.path, length)
        - _rendering.tail_level_db(rendered.path, REFERENCE_SECONDS)
    ) - (
        _rendering.level_db(source, punch_out - length, length)
        - _rendering.level_db(source, punch_out - REFERENCE_SECONDS, REFERENCE_SECONDS)
    )


@then("a short fade-in is applied at the start")
def _(segment, rendered, rendering):
    faded = _opening_attenuation(
        rendered, rendering["source"], segment.punch_in_seconds, rendered.settings["fade_seconds"]
    )
    assert faded <= -FADE_ATTENUATION_DB


@then("a short fade-out is applied at the end")
def _(segment, rendered, rendering):
    faded = _closing_attenuation(
        rendered, rendering["source"], segment.punch_out_seconds, rendered.settings["fade_seconds"]
    )
    assert faded <= -FADE_ATTENUATION_DB


@then("neither fade is long enough to swallow a spoken word")
def _(segment, rendered, rendering):
    word = _rendering.SPOKEN_WORD_SECONDS
    assert rendered.settings["fade_seconds"] < word
    opening = _opening_attenuation(rendered, rendering["source"], segment.punch_in_seconds, word)
    closing = _closing_attenuation(rendered, rendering["source"], segment.punch_out_seconds, word)
    assert abs(opening) <= FADE_HEADROOM_DB and abs(closing) <= FADE_HEADROOM_DB


@then(parsers.parse('the output integrated loudness is "{target}" within {tolerance:d} LU'))
def _(rendered, target, tolerance):
    asked = float(target.split()[0])
    achieved = _rendering.loudness(rendered.path)
    assert abs(achieved["I"] - asked) <= tolerance


@then(
    parsers.parse(
        'the output true peak, measured on the decoded MP3, does not exceed "{ceiling}"'
    )
)
def _(rendered, ceiling):
    assert _rendering.loudness(rendered.path)["Peak"] <= float(ceiling.split()[0])


@then("the measured input and output loudness are recorded on the Segment")
def _(store, segment, rendered):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    achieved = _rendering.loudness(rendered.path)
    assert [
        (one.input_loudness_lufs, one.output_loudness_lufs) for one in artifacts
    ] == [(rendered.input_loudness_lufs, achieved["I"])]


@given("two Segments whose sources differ in loudness by 8 LU")
def _(store, segment, rendering):
    louder = rendering["source"]
    other = _registers(
        store, "recording_20260830_102900", "recordings/recording_20260830_102900.flac"
    )
    quieter = _stages(store, other, "quieter", rendering)
    _approves(
        store,
        quieter,
        segment.punch_in_seconds,
        segment.punch_out_seconds,
        label="Hebrews 12.12-17",
    )
    apart = _taken(louder)["I"] - _taken(rendering["source"])["I"]
    if abs(apart - 8.0) > LEVEL_TOLERANCE_DB:
        raise AssertionError(f"the two sources are {apart:.1f} LU apart")


@when("both are rendered", target_fixture="rendered")
def _(store, rendering):
    while store.lists(Job, kind="render", state="queued"):
        _renders(store, rendering)
    return rendering["renders"][-1]


@then("their output integrated loudness values are within 1 LU of each other")
def _(rendering):
    achieved = [_rendering.loudness(one.path)["I"] for one in rendering["renders"]]
    assert len(achieved) == 2 and abs(achieved[0] - achieved[1]) <= LOUDNESS_TOLERANCE_LU


@given("the Segment contains one isolated peak 12 dB above the speech level")
def _(store, segment, rendering):
    staged = _restages(store, rendering, "isolated peak")
    after = _after(segment)
    source = store.resolves(staged)
    isolated = _rendering.peak_db(source, *_rendering.isolated_peak_window())
    speech = _rendering.peak_db(source, *_rendering.speech_window(after))
    if abs((isolated - speech) - 12.0) > LEVEL_TOLERANCE_DB:
        raise AssertionError(f"the isolated peak stands {isolated - speech:.1f} dB above speech")


@then("the output integrated loudness still meets the target")
def _(rendered):
    achieved = _rendering.loudness(rendered.path)
    assert abs(achieved["I"] - PUBLISHED_I) <= TOLERANCE_LU


@then("the isolated peak is limited rather than allowed to set the level")
def _(segment, rendered, rendering):
    source = rendering["source"]
    punch_in = segment.punch_in_seconds
    peaked = _rendering.isolated_peak_window()
    assert _rendering.peak_db(rendered.path, peaked[0] - punch_in, peaked[1]) < FULL_SCALE_DBFS
    after = _after(segment)
    applied = _speech_level(rendered.path, after, offset=punch_in) - _speech_level(source, after)
    assert applied > TARGET_TP - _rendering.peak_db(source, *peaked)


@given("the Segment contains passages 18 dB quieter than the loudest passage")
def _(segment, rendering):
    source = rendering["source"]
    after = _after(segment)
    apart = _speech_level(source, after) - _quiet_level(source, after)
    if apart < 18.0:
        raise AssertionError(f"the quiet passages are only {apart:.1f} dB down")


@then("the quiet passages are audible at a normal listening volume")
def _(segment, rendered, rendering):
    source = rendering["source"]
    punch_in = segment.punch_in_seconds
    after = _after(segment)
    applied = _speech_level(rendered.path, after, offset=punch_in) - _speech_level(source, after)
    lifted = _quiet_level(rendered.path, after, offset=punch_in) - _quiet_level(source, after)
    assert applied > 0.0 and lifted >= applied


@then("the loudest passages are not clipped")
def _(rendered):
    assert _rendering.peak_db(rendered.path) < FULL_SCALE_DBFS
    assert _rendering.loudness(rendered.path)["Peak"] <= CEILING_TP


@then("no separate compression stage is applied")
def _(segment, rendered, rendering):
    span = _rendering.loudness(
        rendering["source"],
        segment.punch_in_seconds,
        rendered.duration_seconds,
        filters="pan=mono|c0=c0",
    )
    assert _rendering.loudness(rendered.path)["LRA"] >= span["LRA"] - LOUDNESS_TOLERANCE_LU


@given(parsers.parse('the source true peak is "{peak}" with samples at full scale'))
def _(store, rendering, peak):
    staged = _restages(store, rendering, "clipped")
    measured = _rendering.loudness(rendering["source"])
    if abs(measured["Peak"] - float(peak.split()[0])) > CLIPPING_TOLERANCE_DB:
        raise AssertionError(f"the staged source peaks at {measured['Peak']} dBTP")
    if _rendering.peak_db(rendering["source"]) < FULL_SCALE_DBFS:
        raise AssertionError("no sample reaches full scale")
    if "source clipping detected" not in staged.warnings:
        raise AssertionError(f"the probe raised {staged.warnings}")


@given(parsers.parse('the source integrated loudness is "{loudness}"'))
def _(store, rendering, loudness):
    staged = _restages(store, rendering, "very quiet")
    asked = float(loudness.split()[0])
    if abs(staged.integrated_loudness_lufs - asked) > LOUDNESS_TOLERANCE_LU:
        raise AssertionError(f"the staged source measures {staged.integrated_loudness_lufs} LUFS")


@then("the output is brought down to the target loudness and peak ceiling")
def _(rendered, rendering):
    achieved = _rendering.loudness(rendered.path)
    assert achieved["Peak"] < _rendering.loudness(rendering["source"])["Peak"]
    assert abs(achieved["I"] - PUBLISHED_I) <= TOLERANCE_LU
    assert achieved["Peak"] <= CEILING_TP


@then("no attempt is made to reconstruct the clipped peaks")
def _(segment, rendered, rendering):
    source = rendering["source"]
    clipped = _rendering.clipped_window()
    offset = clipped[0] - segment.punch_in_seconds
    flattened = _rendering.peak_db(source, *clipped) - _rendering.level_db(source, *clipped)
    survives = _rendering.peak_db(
        rendered.path, offset, clipped[1]
    ) - _rendering.level_db(rendered.path, offset, clipped[1])
    assert survives <= flattened + LEVEL_TOLERANCE_DB


@then("the output reaches the target loudness")
def _(rendered):
    achieved = _rendering.loudness(rendered.path)
    assert abs(achieved["I"] - PUBLISHED_I) <= TOLERANCE_LU


@then("the noise floor is not raised to a distracting level")
def _(segment, rendered, rendering):
    source = rendering["source"]
    punch_in = segment.punch_in_seconds
    after = _after(segment)
    before = _speech_level(source, after) - _floor_level(source, after)
    kept = _speech_level(rendered.path, after, offset=punch_in) - _floor_level(
        rendered.path, after, offset=punch_in
    )
    assert kept >= before - LEVEL_TOLERANCE_DB


@then("the output is an MP3")
def _(store, segment, rendered):
    artifacts = store.lists(Artifact, segment_id=segment.segment_id, kind="rendered_mp3")
    assert [one.path.endswith(".mp3") for one in artifacts] == [True]
    assert rendered.size_bytes == rendered.path.stat().st_size


@then("the channel layout is mono")
def _(rendered):
    assert rendered.channels == 1


@then(parsers.parse("the sample rate is {rate:d} Hz"))
def _(rendered, rate):
    assert rendered.sample_rate == rate


@then(
    parsers.parse(
        "the bitrate is variable, averaging between {lowest:d} and {highest:d} kbps"
    )
)
def _(rendered, lowest, highest):
    assert _rendering.frame_sizes(rendered.path) > CONSTANT_RATE_FRAME_SIZES
    assert lowest <= rendered.kbps <= highest


@given(parsers.parse("the Segment is {minutes:d} minutes long"))
def _(segment, minutes):
    span = (segment.punch_out_seconds - segment.punch_in_seconds) / 60.0
    if abs(span - minutes) > 0.5:
        raise AssertionError(f"the approved span is {span:.1f} minutes")


@then(parsers.parse("the resulting MP3 is between {lowest:d} MB and {highest:d} MB"))
def _(rendered, lowest, highest):
    assert lowest <= rendered.size_bytes / 1e6 <= highest


@then("the full span is converted without trimming refinement")
def _(store, segment, rendered):
    stored = store.loads(Segment, segment.segment_id)
    assert (stored.punch_in_seconds, stored.punch_out_seconds) == (
        stored.span_start_seconds,
        stored.span_end_seconds,
    )
    assert abs(rendered.duration_seconds - (stored.span_end_seconds - stored.span_start_seconds)) <= 0.1


@then("channel 1 extraction is still applied")
def _(rendered, rendering):
    assert rendered.channels == 1
    assert abs(rendered.input_loudness_lufs - _taken(rendering["source"])["I"]) <= LOUDNESS_TOLERANCE_LU


@then("loudness normalization is still applied")
def _(rendered):
    achieved = _rendering.loudness(rendered.path)
    assert abs(achieved["I"] - PUBLISHED_I) <= TOLERANCE_LU


@then("the same single loudness treatment is applied")
def _(rendered):
    assert [rendered.settings[name] for name in LOUDNESS_KEYS] == [
        TARGET_I,
        TARGET_TP,
        TARGET_LRA,
    ]


@given("a Segment has been rendered", target_fixture="rendered")
def _(store, rendering):
    return _renders(store, rendering)


@when("it is rendered again with identical settings", target_fixture="rerendered")
def _(store, segment, rendering):
    store.saves(
        Job(
            recording_id=segment.recording_id,
            segment_id=segment.segment_id,
            kind="render",
            state="queued",
            max_attempts=5,
            dedupe_key=f"render:{segment.segment_id}:again",
            queued_at=STARTED_AT,
        )
    )
    return _renders(store, rendering, reuse=False)


@then("the output is byte-identical apart from embedded timestamps")
def _(rendering):
    once, again = (one.path.read_bytes() for one in rendering["renders"][-2:])
    assert once == again


@then("the recorded render settings are unchanged")
def _(rendering):
    once, again = rendering["renders"][-2:]
    assert once.settings == again.settings


JOIN_DIP_DB = 12.0
JOIN_RECOVERY_DB = 2.0
JOIN_EDGE_SECONDS = 0.003
JOIN_SETTLED_SECONDS = 0.025
JOIN_WINDOW_SECONDS = 0.025
NEAR_JOIN_SECONDS = 0.25
SHIPPED_PEAK_TOLERANCE_DB = 0.5


def _removed(segment):
    return [(span.start_seconds, span.end_seconds) for span in segment.removed_spans]


def _joins(segment):
    """Each join's place in the output, and its removed span's end in the source."""
    gone = 0.0
    placed = []
    for start, end in _removed(segment):
        placed.append((start - segment.punch_in_seconds - gone, end))
        gone += end - start
    return placed


def _kept_pieces(segment):
    edges = [segment.punch_in_seconds]
    for start, end in _removed(segment):
        edges += [start, end]
    edges.append(segment.punch_out_seconds)
    return list(zip(edges[::2], edges[1::2]))


@given(
    parsers.parse(
        'the reviewer removed the spans from "{first_start}" to "{first_end}" '
        'and from "{second_start}" to "{second_end}"'
    ),
    target_fixture="segment",
)
def _(store, segment, first_start, first_end, second_start, second_end):
    return store.saves(
        replace(
            store.loads(Segment, segment.segment_id),
            removed_spans=(
                RemovedSpan(start_seconds=READS(first_start), end_seconds=READS(first_end)),
                RemovedSpan(start_seconds=READS(second_start), end_seconds=READS(second_end)),
            ),
        )
    )


@then(
    parsers.parse(
        "the output duration is the approved span less the removed spans, within {frames:d} MP3 frames"
    )
)
def _(segment, rendered, frames):
    kept = sum(end - start for start, end in _kept_pieces(segment))
    assert abs(rendered.duration_seconds - kept) <= frames * _rendering.MP3_FRAME_SECONDS


@then("the isolated peak is not in the output")
def _(segment, rendered):
    (join, _), _ = _joins(segment)
    around = _rendering.peak_db(rendered.path, join - NEAR_JOIN_SECONDS, 2 * NEAR_JOIN_SECONDS)
    before = _rendering.peak_db(rendered.path, join - 1.5, 1.0)
    assert around <= before + LEVEL_TOLERANCE_DB


@then("the audio after each removed span follows the audio before it")
def _(segment, rendered, rendering):
    removed = _removed(segment)
    assert removed
    gone = 0.0
    for start, end in removed:
        gone += end - start
        after = end + 1.0
        assert _carries_the_structure(rendering["source"], after)
        assert _carries_the_structure(
            rendered.path, after, offset=segment.punch_in_seconds + gone
        )


@then("the output dips to near silence at each join and is back to speech level within 50 ms")
def _(segment, rendered):
    joins = _joins(segment)
    assert joins
    for join, _ in joins:
        at_the_join = _rendering.level_db(
            rendered.path, join - JOIN_EDGE_SECONDS, 2 * JOIN_EDGE_SECONDS
        )
        before = _rendering.level_db(
            rendered.path, join - JOIN_SETTLED_SECONDS - JOIN_WINDOW_SECONDS, JOIN_WINDOW_SECONDS
        )
        after = _rendering.level_db(rendered.path, join + JOIN_SETTLED_SECONDS, JOIN_WINDOW_SECONDS)
        assert at_the_join <= min(before, after) - JOIN_DIP_DB
        assert abs(before - after) <= JOIN_DIP_DB - JOIN_RECOVERY_DB


@then("the loudness measurement saw the audio that ships and not the removed spans")
def _(segment, rendered, rendering):
    source = rendering["source"]
    shipped = max(
        _rendering.loudness(source, start, end - start, filters="pan=mono|c0=c0")["Peak"]
        for start, end in _kept_pieces(segment)
    )
    whole = _rendering.loudness(
        source,
        segment.punch_in_seconds,
        segment.punch_out_seconds - segment.punch_in_seconds,
        filters="pan=mono|c0=c0",
    )["Peak"]
    assert abs(rendered.input_true_peak_dbtp - shipped) <= SHIPPED_PEAK_TOLERANCE_DB
    assert rendered.input_true_peak_dbtp <= whole - ORDERED_MARGIN_DB


@then("the output still meets the loudness and true-peak targets")
def _(rendered):
    achieved = _rendering.loudness(rendered.path)
    assert abs(achieved["I"] - PUBLISHED_I) <= TOLERANCE_LU
    assert achieved["Peak"] <= CEILING_TP
