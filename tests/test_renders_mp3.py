import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

from sermon.jobs.renders_mp3 import (
    CEILING_TP,
    HIGHEST_KBPS,
    LOWEST_KBPS,
    PUBLISHED_I,
    TOLERANCE_LU,
    ChannelsNeedReview,
    RenderProducedNothing,
    RenderedAudio,
    RendersMp3,
    reads_source_channel,
)
from sermon.jobs.renders_segment import RendersSegment
from sermon.pipeline import render as chain
from sermon.sends_notification import SendsNotification
from sermon.store import Artifact, ChannelLevel, Recording, Reviewer, Segment, opens_store

SAMPLE_RATE = 44100
SECONDS = 20.0
OBJECT_KEY = "recordings/recording_20260823_103015.flac"
FROZEN = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
PUNCH_IN = 2.0
PUNCH_OUT = 18.0


@pytest.fixture
def store(tmp_path):
    opened = opens_store(tmp_path)
    yield opened
    opened.close()


def phrases(amplitude, seed=11):
    generator = np.random.default_rng(seed)
    samples = int(SECONDS * SAMPLE_RATE)
    noise = generator.standard_normal(samples).astype(np.float32)
    smoothed = np.convolve(noise, np.ones(24, dtype=np.float32) / 24, mode="same")
    spoken = np.zeros(samples, dtype=np.float32)
    silence = int(0.4 * SAMPLE_RATE)
    for phrase, start in enumerate(range(0, samples, SAMPLE_RATE)):
        spoken[start + silence:start + SAMPLE_RATE] = 0.15 + 0.85 * ((phrase * 3 % 5) / 4.0)
    return smoothed * spoken * amplitude / max(float(np.abs(smoothed).max()), 1e-9)


def writes_flac(path, channels):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.with_suffix(".raw")
    frames = np.stack(channels, axis=1)
    raw.write_bytes((frames * (2 ** 31 - 1)).astype(np.int32).tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "s32le", "-ar", str(SAMPLE_RATE),
         "-ac", str(len(channels)), "-i", str(raw),
         "-c:a", "flac", "-sample_fmt", "s32", str(path)],
        check=True,
    )
    raw.unlink()
    return path


def silent():
    return np.zeros(int(SECONDS * SAMPLE_RATE), dtype=np.float32)


def source(tmp_path, live_channel=1):
    channels = [phrases(0.5), silent()]
    if live_channel == 2:
        channels.reverse()
    return writes_flac(tmp_path / OBJECT_KEY, channels)


class RecordsCommands:
    def __init__(self, runs):
        self.runs = runs
        self.commands = []

    def __call__(self, command):
        self.commands.append(list(command))
        return self.runs(command)


@pytest.fixture
def recorded(monkeypatch):
    recorder = RecordsCommands(chain._run)
    monkeypatch.setattr(chain, "_run", recorder)
    return recorder


def chain_of(command):
    return command[command.index("-af") + 1]


def test_the_rendered_output_is_a_mono_mp3_at_the_source_sample_rate(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    assert (rendered.channels, rendered.sample_rate) == (1, SAMPLE_RATE)
    assert rendered.path.read_bytes()[:3] == b"ID3" or rendered.path.read_bytes()[:2] == b"\xff\xfb"


def test_the_rendered_output_covers_the_approved_span_within_100_ms(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    assert rendered.duration_seconds == pytest.approx(PUNCH_OUT - PUNCH_IN, abs=0.1)


def lopsided(tmp_path):
    return writes_flac(tmp_path / OBJECT_KEY, [phrases(0.5), phrases(0.05, seed=12)])


def test_each_channel_reaches_the_output_at_its_own_level_not_a_downmix(tmp_path):
    loud = RendersMp3()(lopsided(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "loud.mp3",
                        channel=0)
    quiet = RendersMp3()(lopsided(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "quiet.mp3",
                         channel=1)
    apart = loud.input_loudness_lufs - quiet.input_loudness_lufs
    assert apart == pytest.approx(20.0, abs=2.0)


def test_the_render_extracts_one_channel_rather_than_averaging_the_two(recorded, tmp_path):
    RendersMp3()(source(tmp_path, live_channel=2), PUNCH_IN, PUNCH_OUT,
                 tmp_path / "out.mp3", channel=1)
    chains = [chain_of(command) for command in recorded.commands if "-af" in command]
    assert chains and all(one.startswith("pan=mono|c0=c1") for one in chains)
    assert not any("amerge" in one or "amix" in one for one in chains)


def test_loudness_is_one_stage_that_measures_then_corrects(recorded, tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    measuring, rendering = (
        chain_of(command) for command in recorded.commands if "-af" in command
    )
    assert measuring.count("loudnorm") == 1
    assert rendering.count("loudnorm") == 1
    assert f"measured_I={rendered.input_loudness_lufs:.2f}" in rendering


def test_no_separate_compression_stage_is_applied(recorded, tmp_path):
    RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    for command in (one for one in recorded.commands if "-af" in one):
        assert "acompressor" not in chain_of(command)
        assert "compand" not in chain_of(command)


def test_a_short_fade_brackets_the_cut_at_both_ends(recorded, tmp_path):
    RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    rendering = chain_of([one for one in recorded.commands if "-af" in one][-1])
    assert f"afade=t=in:st=0:d={chain.FADE_S}" in rendering
    assert f"afade=t=out:st={PUNCH_OUT - PUNCH_IN - chain.FADE_S:.3f}:d={chain.FADE_S}" in rendering


def test_the_encode_asks_for_a_variable_bitrate(recorded, tmp_path):
    RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    encoding = [one for one in recorded.commands if "libmp3lame" in one][-1]
    assert "-q:a" in encoding
    assert "-b:a" not in encoding


def test_the_render_reports_the_loudness_it_measured_going_in_and_coming_out(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    assert rendered.input_loudness_lufs < -20.0
    assert rendered.achieved_loudness_lufs > rendered.input_loudness_lufs


def test_the_render_reports_the_true_peak_and_bitrate_it_achieved(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    assert rendered.achieved_true_peak_dbtp < 0.0
    assert rendered.kbps > 0


def test_a_render_that_produced_no_audio_is_refused_loudly(tmp_path):
    with pytest.raises(RenderProducedNothing):
        RendersMp3()(source(tmp_path), 600.0, 640.0, tmp_path / "out.mp3")


def test_the_render_names_every_published_target_the_output_missed(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    named = " ".join(rendered.misses())
    assert (f"{PUBLISHED_I}" in named) is not (
        abs(rendered.achieved_loudness_lufs - PUBLISHED_I) <= TOLERANCE_LU
    )
    assert (f"{CEILING_TP}" in named) is not (rendered.achieved_true_peak_dbtp <= CEILING_TP)
    assert (f"{LOWEST_KBPS}" in named) is not (LOWEST_KBPS <= rendered.kbps <= HIGHEST_KBPS)


def decodes_to(peak):
    return RenderedAudio(
        path=Path("out.mp3"),
        size_bytes=36_000_000,
        duration_seconds=2940.0,
        channels=1,
        sample_rate=SAMPLE_RATE,
        kbps=102,
        input_loudness_lufs=-26.4,
        achieved_loudness_lufs=PUBLISHED_I,
        achieved_true_peak_dbtp=peak,
        achieved_loudness_range_lu=7.0,
        settings={},
    )


@pytest.mark.parametrize(("peak", "missed"), [(-0.98, False), (-0.3, True)])
def test_the_ceiling_leaves_the_encoder_room_to_overshoot_the_peak_it_was_asked_for(
    peak, missed
):
    named = decodes_to(peak).misses()
    assert any("true peak" in one for one in named) is missed
    assert not any("loudness" in one or "bitrate" in one for one in named)


def test_the_settings_recorded_are_the_ones_the_encode_was_given(tmp_path):
    rendered = RendersMp3()(source(tmp_path), PUNCH_IN, PUNCH_OUT, tmp_path / "out.mp3")
    assert rendered.settings["loudness_lufs"] == chain.TARGET_I
    assert rendered.settings["true_peak_dbtp"] == chain.TARGET_TP
    assert rendered.settings["lame_quality"] == chain.LAME_Q
    assert rendered.settings["fade_seconds"] == chain.FADE_S
    assert rendered.settings["source_channel"] == 1


@pytest.mark.parametrize(
    ("named", "channel"),
    [("channel 1", 0), ("channel 2", 1), (None, 0)],
)
def test_the_channel_a_probe_named_becomes_the_channel_the_render_takes(named, channel):
    assert reads_source_channel(named) == channel


def approved(store, tmp_path, *, live_channel=1, warnings=(), confirmed=None):
    writes = source(tmp_path, live_channel=live_channel)
    store.saves(Reviewer(actor="reviewer", receives_notifications=True))
    recording = store.saves(
        Recording(
            recording_id="recording_20260823_103015",
            object_key=OBJECT_KEY,
            state="awaiting_review",
            started_at=datetime(2026, 8, 23, 10, 30, 15, tzinfo=UTC),
            started_at_source="key",
            size_bytes=writes.stat().st_size,
            local_path=OBJECT_KEY,
            duration_seconds=SECONDS,
            channels=2,
            sample_rate=SAMPLE_RATE,
            mono_source=f"channel {live_channel}",
            mono_source_confirmed=confirmed,
            channel_levels=(
                ChannelLevel(channel=1, rms_db=-24.0 if live_channel == 1 else -120.0),
                ChannelLevel(channel=2, rms_db=-24.0 if live_channel == 2 else -120.0),
            ),
            warnings=tuple(warnings),
        )
    )
    return store.saves(
        Segment(
            recording_id=recording.recording_id,
            classification="sermon",
            state="approved",
            span_start_seconds=PUNCH_IN,
            span_end_seconds=PUNCH_OUT,
            punch_in_seconds=PUNCH_IN,
            punch_out_seconds=PUNCH_OUT,
            intent="publish",
            publication_date=date(2026, 8, 23),
            label="Hebrews 12.4-11",
        )
    )


def renders(store):
    return RendersSegment(
        store=store,
        steps=lambda _name: None,
        notifies=SendsNotification(store=store),
        clock=lambda: FROZEN,
        renders=RendersMp3(),
    )


def test_a_hand_specified_cut_becomes_a_playable_mp3(store, tmp_path):
    segment = approved(store, tmp_path)
    renders(store)(segment)
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    assert artifact.path == "2026-08-23 - Hebrews 12.4-11.mp3"
    assert store.resolves(artifact).stat().st_size == artifact.size_bytes > 1000


def test_the_render_takes_the_channel_the_probe_named(store, tmp_path):
    segment = approved(store, tmp_path, live_channel=2)
    renders(store)(segment)
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    assert artifact.render_settings["source_channel"] == 2


def test_the_measured_input_and_output_loudness_are_recorded_on_the_render(store, tmp_path):
    segment = approved(store, tmp_path)
    renders(store)(segment)
    artifact = store.lists(Artifact, kind="rendered_mp3")[0]
    assert artifact.input_loudness_lufs < -20.0
    assert artifact.output_loudness_lufs > artifact.input_loudness_lufs
    assert artifact.output_true_peak_dbtp < 0.0


def test_a_recording_whose_channels_were_never_settled_does_not_render(store, tmp_path):
    segment = approved(store, tmp_path, warnings=("unexpected stereo content",))
    with pytest.raises(ChannelsNeedReview):
        renders(store)(segment)
    assert store.lists(Artifact, kind="rendered_mp3") == []


def test_a_recording_whose_channels_a_reviewer_settled_does_render(store, tmp_path):
    segment = approved(
        store, tmp_path, warnings=("unexpected stereo content",), confirmed=True
    )
    renders(store)(segment)
    assert store.lists(Artifact, kind="rendered_mp3") != []


def test_a_segment_left_unrendered_by_a_refusal_does_not_claim_to_be_complete(store, tmp_path):
    segment = approved(store, tmp_path, warnings=("unexpected stereo content",))
    with pytest.raises(ChannelsNeedReview):
        renders(store)(segment)
    assert store.loads(Segment, segment.segment_id).state == "approved"
