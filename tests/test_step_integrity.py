import textwrap
from functools import cache

import pytest

from step_integrity import (
    HOLLOW_THEN,
    HOLLOW_WHEN,
    INERT_THEN,
    INERT_WHEN,
    NEUTERED_STEP,
    PERMITTED_EMPTY_GIVENS,
    REGENERATION,
    REPORT_PATH,
    TRUE_OPERAND,
    UNENUMERATED_GIVEN,
    UNFALSIFIABLE_ASSERTION,
    UNREADABLE_NAME,
    UNTYPED_DECORATOR,
    VIEW_MODEL_THEN,
    finds_stale_permissions,
    judges_step_tree,
    measures_spec_damage,
    renders_report,
)

SOUND_MODULE = '''
from pytest_bdd import given, parsers, then, when

from sermon.store import Recording


def checks_the_state(store, state):
    assert store.lists(Recording)[0].state == state


@given("I am on the tailnet")
def _():
    return None


@given("a downloaded Recording")
def _(store):
    store.saves(Recording(state="downloaded"))


@when("the reviewer approves it")
def _(store):
    store.approves(store.lists(Recording)[0])


@then(parsers.parse('the Recording is "{state}"'))
def _(store, state):
    checks_the_state(store, state)
'''

HOLLOW_PREAMBLE = '''
import pytest
from pytest_bdd import given, parsers, step, then, when

TRUTH = True
ELSEWHERE = "it holds"


def checks_it():
    pass


def pretends_to_check(store):
    assert True
'''

EVASIONS = (
    ('@then("it holds")\ndef _():\n    return None\n', HOLLOW_THEN),
    ('@then("it holds")\ndef _(store):\n    store.lists()\n', INERT_THEN),
    ('@then("it holds")\ndef _():\n    checks_it()\n', INERT_THEN),
    (
        '@then("it holds")\ndef _(store):\n    pretends_to_check(store)\n',
        UNFALSIFIABLE_ASSERTION,
    ),
    ('@then("it holds")\ndef _():\n    assert True\n', UNFALSIFIABLE_ASSERTION),
    ('@then("it holds")\ndef _():\n    assert 1 == 1\n', UNFALSIFIABLE_ASSERTION),
    ('@then("it holds")\ndef _():\n    assert not False\n', UNFALSIFIABLE_ASSERTION),
    ('@then("it holds")\ndef _():\n    assert TRUTH\n', UNFALSIFIABLE_ASSERTION),
    (
        '@then(parsers.parse(\'it holds "{claim}"\'))\ndef _(claim):\n    assert claim\n',
        UNFALSIFIABLE_ASSERTION,
    ),
    ('@then("it holds")\ndef _(store):\n    assert store.count() or True\n', TRUE_OPERAND),
    ('@then("it holds")\ndef _():\n    pytest.skip("later")\n', NEUTERED_STEP),
    ('@when("it happens")\ndef _():\n    return None\n', HOLLOW_WHEN),
    ('@when("it happens", target_fixture="view")\ndef _():\n    return {"seen": 1}\n', INERT_WHEN),
    ('@given("the ledger holds three entries")\ndef _():\n    return None\n', UNENUMERATED_GIVEN),
    ('@step("it holds")\ndef _():\n    assert 0\n', UNTYPED_DECORATOR),
    ('@then(ELSEWHERE)\ndef _():\n    assert 0\n', UNREADABLE_NAME),
)

RENDERED_MODULE = '''
from pytest_bdd import then, when

from sermon.store import Recording
from sermon.web import creates_app


@when("I open the Recording detail view", target_fixture="detail_page")
def _(store):
    recording = store.lists(Recording)[0]
    response = creates_app(store=store).test_client().get(f"/recordings/{recording.recording_id}")
    return response.get_data(as_text=True)


@when("I visit the recordings list", target_fixture="view_model")
def _(store):
    return creates_app(store=store).test_client().get("/api/recordings").get_json()


@then("the Segments are listed in order")
def _(detail_page):
    assert "lesson" in detail_page


@then("the Segments came back in order")
def _(view_model):
    assert view_model["segments"]


@then("the rows came back")
def _(store):
    body = creates_app(store=store).test_client().get("/api/recordings").get_json()
    assert body["recordings"]
'''

VIEW_MODEL_READERS = ("the Segments came back in order", "the rows came back")


def plants_an_interface_module(tmp_path, source):
    nested = tmp_path / "interface"
    nested.mkdir()
    (nested / "planted_steps.py").write_text(textwrap.dedent(source))
    return judges_step_tree(tmp_path, tmp_path)


@cache
def reads_the_tree():
    return judges_step_tree()


@cache
def measures_the_spec():
    return measures_spec_damage(reads_the_tree())


def plants(tmp_path, source):
    (tmp_path / "planted_steps.py").write_text(textwrap.dedent(source))
    return judges_step_tree(tmp_path, tmp_path)


def names(fault):
    return [
        f"{one.location} {one.kind} {one.text!r}"
        for one in reads_the_tree()
        if fault in one.faults
    ]


def complains(found):
    listed = "\n".join(found[:25])
    return f"{len(found)} step definitions\n{listed}\n\nthe whole list is in {REPORT_PATH.name}"


def refuses(fault):
    found = names(fault)
    assert len(found) == 0, complains(found)


def test_every_then_asserts_something():
    found = names(HOLLOW_THEN) + names(INERT_THEN)
    assert len(found) == 0, complains(sorted(found))


def test_every_when_acts():
    found = names(HOLLOW_WHEN) + names(INERT_WHEN)
    assert len(found) == 0, complains(sorted(found))


def test_every_empty_given_is_enumerated():
    refuses(UNENUMERATED_GIVEN)


def test_no_assertion_is_true_by_construction():
    found = names(UNFALSIFIABLE_ASSERTION) + names(TRUE_OPERAND)
    assert len(found) == 0, complains(sorted(found))


def test_no_step_definition_skips_itself():
    refuses(NEUTERED_STEP)


def test_every_step_declares_a_readable_name_and_a_type():
    found = names(UNREADABLE_NAME) + names(UNTYPED_DECORATOR)
    assert len(found) == 0, complains(sorted(found))


def test_every_permitted_empty_given_is_still_an_empty_given():
    assert finds_stale_permissions(reads_the_tree()) == []


def test_every_permission_carries_a_reason():
    assert [name for name, reason in PERMITTED_EMPTY_GIVENS.items() if not reason.strip()] == []


def test_no_step_definition_hides_from_the_guard(pytestconfig):
    registered = sorted(
        (context.type or "step", context.parser.name)
        for plugin in pytestconfig.pluginmanager.get_plugins()
        if getattr(plugin, "__name__", "").startswith("steps.")
        for member in vars(plugin).values()
        for context in [getattr(member, "_pytest_bdd_step_context", None)]
        if context is not None
    )
    assert sorted((one.kind, one.text) for one in reads_the_tree()) == registered


def test_the_condemnation_report_is_current():
    assert REPORT_PATH.read_text() == renders_report(reads_the_tree(), measures_the_spec()), f"run {REGENERATION}"


def test_the_guard_refuses_a_permission_the_tree_does_not_earn(tmp_path):
    planted = plants(tmp_path, SOUND_MODULE)
    assert finds_stale_permissions(planted, {"I am on the tailnet": "ambient"}) == []
    assert finds_stale_permissions(planted, {"a downloaded Recording": "it sets up a row"}) == [
        "a downloaded Recording"
    ]


def test_the_guard_clears_a_step_module_that_asserts(tmp_path):
    assert [one for one in plants(tmp_path, SOUND_MODULE) if one.faults] == []


def test_the_guard_condemns_a_step_module_that_asserts_nothing(tmp_path):
    hollow = HOLLOW_PREAMBLE + "".join(f"\n\n{source}" for source, _ in EVASIONS)
    condemned = [one for one in plants(tmp_path, hollow) if one.faults]
    assert len(condemned) == len(EVASIONS)


@pytest.mark.parametrize("source,fault", EVASIONS, ids=[fault for _, fault in EVASIONS])
def test_the_guard_condemns_one_way_of_asserting_nothing(tmp_path, source, fault):
    found = plants(tmp_path, HOLLOW_PREAMBLE + "\n\n" + source)
    assert [fault in one.faults for one in found] == [True]


def test_no_interface_then_reads_the_view_model():
    refuses(VIEW_MODEL_THEN)


def test_the_guard_condemns_an_interface_then_that_reads_the_view_model(tmp_path):
    planted = plants_an_interface_module(tmp_path, RENDERED_MODULE)
    condemned = [one.text for one in planted if VIEW_MODEL_THEN in one.faults]
    assert sorted(condemned) == sorted(VIEW_MODEL_READERS)


def test_the_guard_clears_an_interface_then_that_reads_the_rendered_page(tmp_path):
    planted = plants_an_interface_module(tmp_path, RENDERED_MODULE)
    rendered = [one for one in planted if one.text == "the Segments are listed in order"]
    assert [one.faults for one in rendered] == [()]


def test_the_view_model_guard_leaves_steps_outside_the_interface_alone(tmp_path):
    (tmp_path / "planted_steps.py").write_text(textwrap.dedent(RENDERED_MODULE))
    planted = judges_step_tree(tmp_path, tmp_path)
    assert [one for one in planted if VIEW_MODEL_THEN in one.faults] == []


def test_the_spec_rests_on_no_condemned_step():
    damage = measures_the_spec()
    assert damage.unverified_templates == 0, (
        f"{damage.unverified_templates} of {damage.templates} non-deferred scenarios rest on a "
        f"condemned step; {len(damage.unwitnessed)} of them check nothing at all. "
        f"See {REPORT_PATH.name}."
    )
