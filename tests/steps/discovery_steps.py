from pytest_bdd import given, then


@given("a step definition that lives in tests/steps", target_fixture="discovered_definition")
def _():
    return "tests/steps"


@then("the harness has discovered it")
def _(discovered_definition):
    assert discovered_definition == "tests/steps"
