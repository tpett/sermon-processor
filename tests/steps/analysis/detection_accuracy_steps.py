import pytest
from pytest_bdd import given, then, when
from steps import _alignment

from sermon.cli import aligns
from sermon.store import CorpusPair

SUBJECT = "recording_20260927_095721"
ARCHIVED_WHOLE = "recording_20260628_130014"
CLOCK_PPM = -130.0
DRIFT_TOLERANCE_PPM = 15.0
FIT_TOLERANCE_S = 0.01
NORMALIZED_TOLERANCE_S = 0.1


@pytest.fixture
def corpus(tmp_path):
    return _alignment.Corpus(root=tmp_path)


def subject(corpus):
    return corpus.pairs["subject"]


def extracts(corpus):
    for key, pair in corpus.pairs.items():
        source, edit = _alignment.lays_down(corpus, pair)
        corpus.exits[key] = aligns(
            settings=_alignment.settings_for(corpus.root),
            arguments=[
                pair.recording_id,
                str(edit),
                "--source",
                str(source),
                "--classification",
                pair.classification,
                "--work",
                str(corpus.root / "align-work"),
            ],
            reads=corpus.reads,
            measures=corpus.measures,
            prints=corpus.printed.append,
        )


def derived(store, pair):
    rows = [
        row
        for row in store.lists(CorpusPair, recording_id=pair.recording_id)
        if row.classification == pair.classification and row.provenance == "human"
    ]
    assert len(rows) == 1, f"{len(rows)} human pairs stored for {pair.recording_id}"
    return rows[0]


@given("a corpus of source recordings paired with the human-edited output")
def _(store, corpus):
    corpus.pairs["subject"] = _alignment.Pair(SUBJECT, 5412.0, 1900.0, 2592.0)
    corpus.pairs["archive"] = _alignment.Pair(
        ARCHIVED_WHOLE, 5412.0, 1.0, 5400.0, classification="meeting", seed=11
    )
    for pair in corpus.pairs.values():
        _alignment.registers(store, pair)


@given("each pair has a known punch-in and punch-out derived from the pair itself")
def _(corpus):
    for pair in corpus.pairs.values():
        assert 0.0 <= pair.offset_seconds < pair.offset_seconds + pair.edit_seconds <= pair.source_seconds


@given("a source FLAC and the MP3 a human produced from it")
def _(store, corpus):
    pair = subject(corpus)
    pair.source_seconds, pair.offset_seconds, pair.edit_seconds = 3600.0, 1412.25, 1800.0
    _alignment.registers(store, pair)


@when("ground truth extraction runs")
def _(corpus):
    extracts(corpus)


@then("the offset of the MP3 within the FLAC is determined")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.alignment == "aligned"
    assert row.punch_in_seconds is not None


@then("the punch-in is that offset")
def _(store, corpus):
    pair = subject(corpus)
    assert derived(store, pair).punch_in_seconds == pytest.approx(pair.offset_seconds, abs=FIT_TOLERANCE_S)


@then("the punch-out is that offset plus the MP3 duration")
def _(store, corpus):
    pair = subject(corpus)
    expected = pair.offset_seconds + pair.edit_seconds
    assert derived(store, pair).punch_out_seconds == pytest.approx(expected, abs=FIT_TOLERANCE_S)


@then("the derived boundaries are stored as the expected answer for that pair")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.labelled
    assert row.punch_in_difficulty in {"easy", "moderate", "hard"}
    assert row.punch_out_difficulty in {"easy", "moderate", "hard"}


@given("the MP3 was normalized relative to the source")
def _(corpus):
    subject(corpus).gain = 3.7


@then("alignment still succeeds")
def _(store, corpus):
    assert corpus.exits["subject"] == 0
    assert derived(store, subject(corpus)).alignment == "aligned"


@then("the derived punch-in is accurate to within 100 ms")
def _(store, corpus):
    pair = subject(corpus)
    assert derived(store, pair).punch_in_seconds == pytest.approx(pair.offset_seconds, abs=NORMALIZED_TOLERANCE_S)


@given("alignment fails for a pair")
def _(store, corpus):
    subject(corpus).unrelated = True
    extracts(corpus)


@then("that pair is excluded from the corpus")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.alignment == "cannot be aligned"
    assert row.punch_in_seconds is None and row.punch_out_seconds is None
    assert not row.labelled


@then("the exclusion is reported rather than silently dropped")
def _(corpus):
    assert corpus.exits["subject"] == 1
    assert f"  {SUBJECT}: recorded as cannot be aligned; no boundaries derived" in corpus.printed


@given("a published output that runs at a slightly different rate to its source")
def _(corpus):
    pair = subject(corpus)
    pair.offset_seconds, pair.edit_seconds, pair.stretch_ppm = 151.5, 600.0, CLOCK_PPM


@then("the drift is measured rather than averaged away")
def _(store, corpus):
    assert derived(store, subject(corpus)).drift_ppm == pytest.approx(CLOCK_PPM, abs=DRIFT_TOLERANCE_PPM)


@then("the punch-in is the intercept of the fit, not the middle of it")
def _(store, corpus):
    pair = subject(corpus)
    middle = pair.offset_seconds + pair.edit_seconds / 2 * pair.stretch_ppm / 1e6
    assert abs(middle - pair.offset_seconds) > 2 * FIT_TOLERANCE_S
    assert derived(store, pair).punch_in_seconds == pytest.approx(pair.offset_seconds, abs=FIT_TOLERANCE_S)


@then("the punch-out accounts for the drift across the segment")
def _(store, corpus):
    pair = subject(corpus)
    drifted = pair.offset_seconds + pair.edit_seconds * (1 + pair.stretch_ppm / 1e6)
    naive = pair.offset_seconds + pair.edit_seconds
    assert abs(drifted - naive) > 2 * FIT_TOLERANCE_S
    assert derived(store, pair).punch_out_seconds == pytest.approx(drifted, abs=FIT_TOLERANCE_S)


@given("probes through the output disagree about the offset")
def _(corpus):
    pair = subject(corpus)
    pair.offset_seconds, pair.edit_seconds, pair.stretch_ppm = 151.5, 600.0, CLOCK_PPM


@when("they fall on a straight line")
def _(corpus):
    extracts(corpus)


@then("the pair is usable and the slope is the clock difference")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.labelled
    assert row.drift_ppm == pytest.approx(CLOCK_PPM, abs=DRIFT_TOLERANCE_PPM)


@when("they do not fall on a straight line")
def _(corpus):
    pair = subject(corpus)
    pair.stretch_ppm, pair.spliced_at = 0.0, 250.0
    extracts(corpus)


@then("the pair is excluded as not a contiguous excerpt")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.alignment == "not a contiguous excerpt"
    assert not row.labelled
    assert corpus.exits["subject"] == 1


@given("a Recording whose published output covers more than 95% of its source")
def _(store, corpus):
    pair = subject(corpus)
    pair.offset_seconds, pair.edit_seconds = 2.0, 5300.0
    extracts(corpus)


@then("it is flagged rather than silently accepted")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.alignment == "aligned"
    assert row.covers_more_than_95_percent


@then("it is excluded from boundary statistics")
def _(store, corpus):
    row = derived(store, subject(corpus))
    assert row.punch_in_seconds is not None
    assert not row.labelled


@then("a legitimate untrimmed archive is flagged the same way")
def _(store, corpus):
    row = derived(store, corpus.pairs["archive"])
    assert row.alignment == "aligned"
    assert row.covers_more_than_95_percent
    assert not row.labelled
