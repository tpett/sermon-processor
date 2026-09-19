from pytest_bdd import given, parsers, then


@given("a step definition that lives in tests/steps", target_fixture="discovered_definition")
def _():
    return "tests/steps"


@then(parsers.parse("the harness reports it was found in {location}"))
def _(discovered_definition, location):
    assert discovered_definition == location
