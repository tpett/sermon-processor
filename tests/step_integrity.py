"""Judges every step definition on whether it can fail."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from pytest_bdd import parsers
from pytest_bdd.feature import get_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEP_ROOT = Path(__file__).parent / "steps"
SPEC_ROOT = PROJECT_ROOT / "features"
REPORT_PATH = Path(__file__).parent / "step_integrity_report.md"
REGENERATION = ".venv/bin/python tests/step_integrity.py"

PERMITTED_EMPTY_GIVENS = {
    "I am on the tailnet": "the deployment runs NoAuth, so there is no session to establish",
    "I am using a desktop browser": "one layout is served; no client capability is negotiated",
    "I am using a phone": "one layout is served; no client capability is negotiated",
    "the Recorder reaches it over the tailnet": "reachability is the ambient condition of every test",
    'it contains a bucket "{name}"': (
        "the fake object store is the bucket; it models no second one"
    ),
    "the object store is a Garage S3 instance reachable over the tailnet": (
        "the fake object store stands in for Garage in every test"
    ),
    "I am looking for the right moment": "states the reviewer's intent, which holds no state",
    "I am placing the cut precisely": "states the reviewer's intent, which holds no state",
}

STEP_DECORATORS = ("given", "when", "then")
GENERIC_DECORATOR = "step"
PARSER_MAKERS = {
    "parse": parsers.parse,
    "cfparse": parsers.cfparse,
    "re": parsers.re,
    "string": parsers.string,
}
INTERFACE_DIRECTORY = "interface"
PAYLOAD_READER = "get_json"
ASSERTING_PYTEST_CALLS = frozenset({"raises", "warns", "fail"})
NEUTERING_PYTEST_CALLS = frozenset({"skip", "xfail", "importorskip"})
GHERKIN_BLOCK_ARGUMENTS = frozenset({"datatable", "docstring"})
SERMON_PACKAGE = "sermon"

HOLLOW_THEN = "a Then with an empty body"
INERT_THEN = "a Then whose body never asserts"
VIEW_MODEL_THEN = "an interface Then that reads the view model rather than the rendered page"
HOLLOW_WHEN = "a When with an empty body"
INERT_WHEN = "a When whose body never acts"
UNENUMERATED_GIVEN = "an empty Given that PERMITTED_EMPTY_GIVENS does not enumerate"
UNFALSIFIABLE_ASSERTION = "an assertion that cannot fail"
TRUE_OPERAND = "a boolean operand of True, which neutralises what it joins"
NEUTERED_STEP = "a step that skips or xfails instead of running"
UNREADABLE_NAME = "a step name the guard cannot read from the source"
UNTYPED_DECORATOR = "a step decorator that declares no Given, When or Then"

FAULT_ORDER = (
    HOLLOW_THEN,
    INERT_THEN,
    VIEW_MODEL_THEN,
    UNFALSIFIABLE_ASSERTION,
    TRUE_OPERAND,
    HOLLOW_WHEN,
    INERT_WHEN,
    UNENUMERATED_GIVEN,
    NEUTERED_STEP,
    UNREADABLE_NAME,
    UNTYPED_DECORATOR,
)

NAMED_HOLLOW_FILES = (
    "tests/steps/catch_all_thens.py",
    "tests/steps/remaining_steps.py",
    "tests/steps/generated_remaining.py",
    "tests/steps/generated_remaining2.py",
    "tests/steps/generated_remaining3.py",
    "tests/steps/last_fourteen.py",
)


@dataclass(frozen=True)
class Definition:
    kind: str
    text: str
    module: str
    line: int
    faults: tuple[str, ...]
    omitted: bool = False
    parser: object = None

    @property
    def location(self) -> str:
        return f"{self.module}:{self.line}"


def names_decorator(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    return getattr(node, "id", "")


def builds_step_parser(argument: ast.expr | None):
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return parsers.string(argument.value)
    if isinstance(argument, ast.Call):
        maker = PARSER_MAKERS.get(names_decorator(argument.func))
        first = argument.args[0] if argument.args else None
        if maker is not None and isinstance(first, ast.Constant) and isinstance(first.value, str):
            return maker(first.value)
    return None


def reads_step_decorators(node: ast.FunctionDef):
    found = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = names_decorator(decorator.func)
        if name not in (*STEP_DECORATORS, GENERIC_DECORATOR):
            continue
        argument = decorator.args[0] if decorator.args else None
        found.append((name, builds_step_parser(argument), decorator.lineno))
    return found


def names_target_fixture(node: ast.FunctionDef) -> str | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if names_decorator(decorator.func) not in (*STEP_DECORATORS, GENERIC_DECORATOR):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "target_fixture" and isinstance(keyword.value, ast.Constant):
                return keyword.value.value
    return None


def reads_a_payload(node: ast.FunctionDef, helpers: dict[str, ast.FunctionDef], depth: int = 0) -> bool:
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Call):
            continue
        called = statement.func
        if isinstance(called, ast.Attribute) and called.attr == PAYLOAD_READER:
            return True
        if depth == 0 and isinstance(called, ast.Name) and called.id in helpers:
            if reads_a_payload(helpers[called.id], helpers, depth + 1):
                return True
    return False


def finds_payload_names(step_root: Path) -> frozenset[str]:
    names = set()
    for path in sorted(step_root.rglob("*.py")):
        tree = ast.parse(path.read_text())
        helpers = finds_module_helpers(tree)
        hidden = path.name.startswith("_")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not reads_a_payload(node, helpers):
                continue
            if hidden:
                names.add(node.name)
            elif INTERFACE_DIRECTORY in path.parts:
                fixture = names_target_fixture(node)
                if fixture is not None:
                    names.add(fixture)
    return frozenset(names)


def reads_the_view_model(node, helpers, payloads: frozenset[str]) -> bool:
    if reads_a_payload(node, helpers):
        return True
    if names_parameters(node) & payloads:
        return True
    return any(
        isinstance(statement, ast.Call)
        and isinstance(statement.func, ast.Name)
        and statement.func.id in payloads
        for statement in ast.walk(node)
    )


def names_gherkin_arguments(parser) -> frozenset[str]:
    names = set(GHERKIN_BLOCK_ARGUMENTS)
    if parser is None:
        return frozenset(names)
    if isinstance(parser, parsers.re):
        names |= set(parser.regex.groupindex)
        return frozenset(names)
    inner = getattr(parser, "parser", None)
    declared = getattr(inner, "named_fields", None)
    if declared is not None:
        names |= set(declared)
        return frozenset(names)
    try:
        names |= {field for _, field, _, _ in Formatter().parse(parser.name) if field}
    except ValueError:
        pass
    return frozenset(names)


def finds_module_helpers(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not reads_step_decorators(node)
    }


def finds_module_truths(tree: ast.Module) -> frozenset[str]:
    truths = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not node.value.value:
            continue
        truths |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    return frozenset(truths)


def finds_sermon_names(tree: ast.Module) -> frozenset[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == SERMON_PACKAGE:
                names |= {alias.asname or alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            names |= {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] == SERMON_PACKAGE
            }
    return frozenset(names)


def roots_attribute(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def strips_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    head = body[0] if body else None
    if isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant):
        if isinstance(head.value.value, str):
            return body[1:]
    return body


def omits_a_body(node: ast.FunctionDef) -> bool:
    for statement in strips_docstring(node.body):
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            if statement.value.value is Ellipsis:
                continue
        if isinstance(statement, ast.Return):
            returned = statement.value
            if returned is None:
                continue
            if isinstance(returned, ast.Constant) and returned.value is None:
                continue
        return False
    return True


def calls_pytest(node: ast.Call, attributes: frozenset[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    return roots_attribute(node.func) == "pytest" and node.func.attr in attributes


def reaches_bodies(node: ast.FunctionDef, helpers: dict[str, ast.FunctionDef]):
    bodies = [node]
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Call) or not isinstance(statement.func, ast.Name):
            continue
        helper = helpers.get(statement.func.id)
        if helper is not None and helper not in bodies:
            bodies.append(helper)
    return bodies


def asserts_something(node: ast.FunctionDef, helpers: dict[str, ast.FunctionDef], depth: int = 0) -> bool:
    for statement in ast.walk(node):
        if isinstance(statement, (ast.Assert, ast.Raise)):
            return True
        if not isinstance(statement, ast.Call):
            continue
        if calls_pytest(statement, ASSERTING_PYTEST_CALLS):
            return True
        called = statement.func
        if depth == 0 and isinstance(called, ast.Name) and called.id in helpers:
            if asserts_something(helpers[called.id], helpers, depth + 1):
                return True
    return False


def acts_on_something(
    node: ast.FunctionDef,
    helpers: dict[str, ast.FunctionDef],
    sermon_names: frozenset[str],
    parameters: frozenset[str],
    depth: int = 0,
) -> bool:
    for statement in ast.walk(node):
        if isinstance(statement, ast.AugAssign):
            if isinstance(statement.target, (ast.Attribute, ast.Subscript)):
                return True
        if isinstance(statement, ast.Assign):
            if any(isinstance(target, (ast.Attribute, ast.Subscript)) for target in statement.targets):
                return True
        if not isinstance(statement, ast.Call):
            continue
        called = statement.func
        if isinstance(called, ast.Attribute):
            if roots_attribute(called) != "pytest":
                return True
            if called.attr in ASSERTING_PYTEST_CALLS:
                return True
        elif isinstance(called, ast.Name):
            if called.id in sermon_names or called.id in parameters:
                return True
            if depth == 0 and called.id in helpers:
                if acts_on_something(helpers[called.id], helpers, sermon_names, parameters, depth + 1):
                    return True
    return False


def evaluates_statically(node: ast.expr):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = evaluates_statically(node.operand)
        return None if inner is None else (not inner[0],)
    try:
        return (ast.literal_eval(node),)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def is_statically_true(node: ast.expr) -> bool:
    value = evaluates_statically(node)
    return value is not None and bool(value[0])


def restates_the_gherkin(node: ast.expr, gherkin: frozenset[str], truths: frozenset[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in gherkin or node.id in truths
    if isinstance(node, ast.BoolOp):
        return all(restates_the_gherkin(value, gherkin, truths) for value in node.values)
    if isinstance(node, ast.UnaryOp):
        return restates_the_gherkin(node.operand, gherkin, truths)
    return False


def compares_only_literals(node: ast.expr) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    operands = [node.left, *node.comparators]
    return all(evaluates_statically(operand) is not None for operand in operands)


def cannot_fail(test: ast.expr, gherkin: frozenset[str], truths: frozenset[str]) -> bool:
    if is_statically_true(test):
        return True
    if compares_only_literals(test):
        return True
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        if any(is_statically_true(value) for value in test.values):
            return True
    return restates_the_gherkin(test, gherkin, truths)


def finds_unfalsifiable_assertions(bodies, gherkin: frozenset[str], truths: frozenset[str]) -> bool:
    return any(
        cannot_fail(statement.test, gherkin, truths)
        for body in bodies
        for statement in ast.walk(body)
        if isinstance(statement, ast.Assert)
    )


def joins_a_literal_true(bodies) -> bool:
    for body in bodies:
        for statement in ast.walk(body):
            if not isinstance(statement, ast.BoolOp):
                continue
            if any(isinstance(one, ast.Constant) and one.value is True for one in statement.values):
                return True
    return False


def neuters_itself(bodies) -> bool:
    return any(
        isinstance(statement, ast.Call) and calls_pytest(statement, NEUTERING_PYTEST_CALLS)
        for body in bodies
        for statement in ast.walk(body)
    )


def names_parameters(node: ast.FunctionDef) -> frozenset[str]:
    arguments = node.args
    named = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    return frozenset(argument.arg for argument in named)


def judges_definition(
    kind, parser, node, helpers, truths, sermon_names, payloads=frozenset(), rendered=False
) -> tuple[str, ...]:
    faults = []
    gherkin = names_gherkin_arguments(parser)
    bodies = reaches_bodies(node, helpers)
    if neuters_itself(bodies):
        faults.append(NEUTERED_STEP)
    if joins_a_literal_true(bodies):
        faults.append(TRUE_OPERAND)
    if finds_unfalsifiable_assertions(bodies, gherkin, truths):
        faults.append(UNFALSIFIABLE_ASSERTION)
    if parser is None:
        faults.append(UNREADABLE_NAME)
    if kind == GENERIC_DECORATOR:
        faults.append(UNTYPED_DECORATOR)
    elif kind == "then":
        if omits_a_body(node):
            faults.append(HOLLOW_THEN)
        elif not asserts_something(node, helpers):
            faults.append(INERT_THEN)
        if rendered and reads_the_view_model(node, helpers, payloads):
            faults.append(VIEW_MODEL_THEN)
    elif kind == "when":
        if omits_a_body(node):
            faults.append(HOLLOW_WHEN)
        elif not acts_on_something(node, helpers, sermon_names, names_parameters(node)):
            faults.append(INERT_WHEN)
    elif omits_a_body(node) and (parser is None or parser.name not in PERMITTED_EMPTY_GIVENS):
        faults.append(UNENUMERATED_GIVEN)
    return tuple(faults)


def judges_step_module(path: Path, root: Path, payloads=frozenset()) -> list[Definition]:
    tree = ast.parse(path.read_text())
    helpers = finds_module_helpers(tree)
    truths = finds_module_truths(tree)
    sermon_names = finds_sermon_names(tree)
    module = path.relative_to(root).as_posix()
    rendered = INTERFACE_DIRECTORY in path.parts
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for kind, parser, line in reads_step_decorators(node):
            found.append(
                Definition(
                    kind=kind,
                    text=parser.name if parser is not None else ast.unparse(node.decorator_list[0]),
                    module=module,
                    line=line,
                    faults=judges_definition(
                        kind, parser, node, helpers, truths, sermon_names, payloads, rendered
                    ),
                    omitted=omits_a_body(node),
                    parser=parser,
                )
            )
    return found


def judges_step_tree(step_root: Path = STEP_ROOT, root: Path | None = None) -> list[Definition]:
    base = root if root is not None else PROJECT_ROOT
    payloads = finds_payload_names(step_root)
    found = []
    for path in sorted(step_root.rglob("[!_]*.py")):
        found += judges_step_module(path, base, payloads)
    return sorted(found, key=lambda one: (one.module, one.line, one.kind, one.text))


def condemns(definitions: list[Definition]) -> list[Definition]:
    return [one for one in definitions if one.faults]


def finds_stale_permissions(definitions: list[Definition], permitted=PERMITTED_EMPTY_GIVENS) -> list[str]:
    honoured = {
        one.text
        for one in definitions
        if one.kind == "given" and one.omitted and one.parser is not None
    }
    return sorted(name for name in permitted if name not in honoured)


def reads_scenario_templates(spec_root: Path = SPEC_ROOT):
    for feature in get_features([str(spec_root)]):
        for template in feature.scenarios.values():
            tags = set(feature.tags) | set(template.tags)
            if template.rule is not None:
                tags |= set(template.rule.tags)
            yield feature, template, tags


def expands_contexts(template):
    contexts = []
    for examples in template.examples:
        contexts += [(context, set(examples.tags)) for context in examples.as_contexts()]
    return contexts or [({}, set())]


def indexes_by_kind(definitions: list[Definition]) -> dict[str, list[Definition]]:
    index: dict[str, list[Definition]] = {"given": [], "when": [], "then": [], GENERIC_DECORATOR: []}
    for one in definitions:
        if one.parser is not None:
            index[one.kind].append(one)
    return index


def matches_step(index: dict[str, list[Definition]], kind: str, text: str) -> list[Definition]:
    candidates = index.get(kind, []) + index[GENERIC_DECORATOR]
    return [one for one in candidates if one.parser.is_matching(text)]


@dataclass(frozen=True)
class SpecDamage:
    templates: int
    unverified_templates: int
    tests: int
    unverified_tests: int
    hollow_templates: int
    unstaged_templates: int
    unwitnessed: tuple[tuple[str, str, str], ...]
    unmatched_steps: tuple[str, ...]
    ambiguous_steps: int


def condemns_step(index, step) -> bool | None:
    candidates = matches_step(index, step.type, step.name)
    return any(one.faults for one in candidates) if candidates else None


def measures_spec_damage(definitions: list[Definition], spec_root: Path = SPEC_ROOT) -> SpecDamage:
    index = indexes_by_kind(definitions)
    templates = unverified_templates = tests = unverified_tests = 0
    hollow_templates = unstaged_templates = 0
    unmatched: set[str] = set()
    ambiguous = 0
    unwitnessed: list[tuple[str, str, str]] = []
    for feature, template, tags in reads_scenario_templates(spec_root):
        if "deferred" in tags:
            continue
        templates += 1
        background = len(template.all_background_steps)
        touched = wholly = unstaged = blind = False
        for context, example_tags in expands_contexts(template):
            if "deferred" in tags | example_tags:
                continue
            tests += 1
            scenario = template.render(context)
            for step in scenario.steps:
                candidates = matches_step(index, step.type, step.name)
                if not candidates:
                    unmatched.add(f"{feature.rel_filename}:{step.line_number} {step.type} {step.name}")
                if len(candidates) > 1:
                    ambiguous += 1
            verdicts = [condemns_step(index, step) for step in scenario.steps]
            judged = [one for one in verdicts if one is not None]
            outcomes = [
                condemns_step(index, step) for step in scenario.steps if step.type == "then"
            ]
            outcomes = [one for one in outcomes if one is not None]
            own = [one for one in verdicts[background:] if one is not None]
            if any(judged):
                unverified_tests += 1
                touched = True
            wholly = wholly or (bool(judged) and all(judged))
            unstaged = unstaged or (bool(own) and all(own))
            blind = blind or (bool(outcomes) and all(outcomes))
        unverified_templates += touched
        hollow_templates += wholly
        unstaged_templates += unstaged
        if blind:
            unwitnessed.append((feature.rel_filename, template.name, str(template.line_number)))
    return SpecDamage(
        templates=templates,
        unverified_templates=unverified_templates,
        tests=tests,
        unverified_tests=unverified_tests,
        hollow_templates=hollow_templates,
        unstaged_templates=unstaged_templates,
        unwitnessed=tuple(sorted(unwitnessed)),
        unmatched_steps=tuple(sorted(unmatched)),
        ambiguous_steps=ambiguous,
    )


def counts_faults(definitions: list[Definition]) -> dict[str, int]:
    counted = {fault: 0 for fault in FAULT_ORDER}
    for one in definitions:
        for fault in one.faults:
            counted[fault] += 1
    return counted


def tallies_modules(definitions: list[Definition]) -> list[tuple[str, int, int]]:
    total: dict[str, int] = {}
    bad: dict[str, int] = {}
    for one in definitions:
        total[one.module] = total.get(one.module, 0) + 1
        bad[one.module] = bad.get(one.module, 0) + (1 if one.faults else 0)
    return sorted((module, total[module], bad[module]) for module in total)


def renders_report(definitions: list[Definition], damage: SpecDamage) -> str:
    condemned = condemns(definitions)
    counted = counts_faults(definitions)
    tallies = tallies_modules(definitions)
    named = set(NAMED_HOLLOW_FILES)
    lines = [
        "# Step integrity",
        "",
        f"Regenerate with `{REGENERATION}`. Hand edits are lost.",
        "",
        "## What the guard found",
        "",
        f"- {len(definitions)} step definitions read from `tests/steps`",
        f"- {len(condemned)} condemned",
        f"- {damage.unverified_templates} of {damage.templates} non-deferred scenarios "
        f"rest on at least one condemned step",
        f"- {damage.unverified_tests} of {damage.tests} expanded scenario tests likewise",
        f"- {len(damage.unwitnessed)} scenarios whose every Then is condemned, so nothing "
        f"they claim is checked",
        f"- {damage.unstaged_templates} scenarios whose every step outside the Background is condemned",
        f"- {damage.hollow_templates} scenarios whose every step, Background included, is condemned",
        f"- {damage.ambiguous_steps} Gherkin steps matched more than one definition",
        f"- {len(damage.unmatched_steps)} Gherkin steps matched no definition",
        "",
        "## Faults by kind",
        "",
        "| fault | count |",
        "| --- | --- |",
    ]
    lines += [f"| {fault} | {counted[fault]} |" for fault in FAULT_ORDER]
    lines += [
        "",
        "## Modules",
        "",
        "| module | definitions | condemned | verdict |",
        "| --- | --- | --- | --- |",
    ]
    for module, total, bad in tallies:
        verdict = "sound" if bad == 0 else ("wholly condemned" if bad == total else "partly condemned")
        flag = " (named)" if module in named else ""
        lines.append(f"| `{module}`{flag} | {total} | {bad} | {verdict} |")
    outside = [one for one in condemned if one.module not in named]
    lines += [
        "",
        "## Condemned outside the six named files",
        "",
        f"{len(outside)} definitions.",
        "",
        "| location | kind | step | faults |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| `{one.location}` | {one.kind} | `{one.text}` | {'; '.join(one.faults)} |" for one in outside
    ]
    lines += [
        "",
        "## Every condemned definition",
        "",
        "| location | kind | step | faults |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| `{one.location}` | {one.kind} | `{one.text}` | {'; '.join(one.faults)} |" for one in condemned
    ]
    lines += [
        "",
        "## Scenarios whose every Then is condemned",
        "",
        "| feature | line | scenario |",
        "| --- | --- | --- |",
    ]
    lines += [f"| `{where}` | {line} | {name} |" for where, name, line in damage.unwitnessed]
    if damage.unmatched_steps:
        lines += ["", "## Gherkin steps the guard could not match", ""]
        lines += [f"- `{one}`" for one in damage.unmatched_steps]
    return "\n".join(lines) + "\n"


def writes_report() -> str:
    definitions = judges_step_tree()
    text = renders_report(definitions, measures_spec_damage(definitions))
    REPORT_PATH.write_text(text)
    return text


if __name__ == "__main__":
    print(writes_report().splitlines()[4:11][0])
    print(f"wrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")
