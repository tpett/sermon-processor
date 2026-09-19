from pathlib import Path

from pytest_bdd import scenarios

SPEC_ROOT = Path(__file__).resolve().parents[1] / "features"

scenarios(str(SPEC_ROOT))
