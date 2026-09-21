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
'''

EVASIONS = (
    ('@then("it holds")\ndef _():\n    return None\n', HOLLOW_THEN),
    ('@then("it holds")\ndef _(store):\n    store.lists()\n', INERT_THEN),
    ('@then("it holds")\ndef _():\n    checks_it()\n', INERT_THEN),
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


def test_the_spec_rests_on_no_condemned_step():
    damage = measures_the_spec()
    assert damage.unverified_templates == 0, (
        f"{damage.unverified_templates} of {damage.templates} non-deferred scenarios rest on a "
        f"condemned step; {len(damage.unwitnessed)} of them check nothing at all. "
        f"See {REPORT_PATH.name}."
    )
