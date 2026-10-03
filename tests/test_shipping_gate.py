import os
from pathlib import Path

import pytest

from sermon.analysis.gates_shipping_cuts import (
    PRODUCTION_TAG,
    WORSENED,
    GatesShippingCuts,
    reads_baseline,
)
from sermon.analysis.judges_cut import JUDGE_DIGEST, WORSE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE = PROJECT_ROOT / "tests" / "shipping_baseline.json"
SPIKE_DATA = Path(os.environ.get("SERMON_SPIKE_DATA") or PROJECT_ROOT / "experiments" / "data")

requires_spike_data = pytest.mark.skipif(
    not any((SPIKE_DATA / "blocks").glob(f"*.{PRODUCTION_TAG}.json")),
    reason=(
        f"{SPIKE_DATA}/blocks and /transcripts are gitignored and exist only in the "
        "primary working tree; point SERMON_SPIKE_DATA at one that has them"
    ),
)


@pytest.fixture(scope="module")
def report():
    return GatesShippingCuts(corpus_root=SPIKE_DATA, baseline=reads_baseline(BASELINE))()


def test_the_accepted_reference_was_taken_under_this_judge():
    assert reads_baseline(BASELINE).judge == JUDGE_DIGEST, (
        "the judge changed since tests/shipping_baseline.json was accepted; "
        "run sermon-regrade, then --accept the judge on an unchanged pipeline"
    )


@requires_spike_data
def test_every_dev_recording_of_production_config_is_judged(report):
    assert len(report.recordings) == 7
    assert report.not_in_baseline == ()


@requires_spike_data
def test_no_dev_recording_is_further_from_the_human_cut_than_the_accepted_reference(report):
    worse = [one.recording_id for one in report.recordings if one.verdict in (WORSE, "mixed")]
    assert report.outcome != WORSENED, f"run sermon-regrade for the detail: {worse}"
