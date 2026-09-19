from pytest_bdd import given


@given(
    "a step definition that lives in a subdirectory of tests/steps",
    target_fixture="discovered_definition",
)
def _():
    return "tests/steps/nested"
