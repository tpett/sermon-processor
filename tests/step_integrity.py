"""Judges every step definition on whether it can fail."""

from __future__ import annotations

import ast
import builtins
import importlib
import inspect
from dataclasses import dataclass, field, replace
from functools import cache
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
EXISTENCE_THEN = "a Then whose every assertion only checks that some row exists"
EXISTENCE_DISJUNCT = "an assertion that any existing row satisfies"
ARGUMENT_TRUTH = "an assertion operand that some scenario's own arguments make true"
UNASSERTED_PATH = "a Then with a path through it that asserts nothing"
SELF_COMPARISON = "an assertion that compares a value with itself"
INVOKING_THEN = "a Then that constructs and invokes a unit of the system"
WRITING_THEN = "a Then that writes to the store"
STAGED_FLAG = "a Then that asserts on data a step put on the store as a flag, or on a flag nothing sets"
STAGING_WHEN = "a When that writes the outcome itself instead of invoking the system"
DUPLICATE_THEN = "a Then that asserts word for word what another Then in its scenario asserts"

FAULT_ORDER = (
    HOLLOW_THEN,
    INERT_THEN,
    VIEW_MODEL_THEN,
    UNFALSIFIABLE_ASSERTION,
    TRUE_OPERAND,
    EXISTENCE_THEN,
    EXISTENCE_DISJUNCT,
    ARGUMENT_TRUTH,
    UNASSERTED_PATH,
    SELF_COMPARISON,
    INVOKING_THEN,
    WRITING_THEN,
    STAGED_FLAG,
    DUPLICATE_THEN,
    HOLLOW_WHEN,
    INERT_WHEN,
    STAGING_WHEN,
    UNENUMERATED_GIVEN,
    NEUTERED_STEP,
    UNREADABLE_NAME,
    UNTYPED_DECORATOR,
)

PERMITTED_THEN_UNITS = {
    "ReadsTimecode": "parses the Gherkin's own timecode text; it observes nothing the system did",
}

STORE_FIXTURE = "store"
STORE_READERS = frozenset({"lists", "loads"})
STORE_WRITERS = frozenset({"saves", "forgets"})
STORE_PACKAGE = "sermon.store"
STEP_PACKAGE = "steps"
SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs", "all", "any", "bool", "float", "frozenset", "int", "len", "list",
        "max", "min", "round", "set", "sorted", "str", "tuple",
    )
}

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
    node: object = field(default=None, compare=False, repr=False)
    scope: object = field(default=None, compare=False, repr=False)

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
    if isinstance(node, ast.IfExp):
        test = evaluates_statically(node.test)
        if test is None:
            return None
        return evaluates_statically(node.body if test[0] else node.orelse)
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


@dataclass(frozen=True)
class ModuleScope:
    path: Path
    helpers: dict
    imported: dict
    namespaces: dict
    sermon_names: dict
    bound_units: dict
    constants: dict

    @property
    def units(self) -> frozenset[str]:
        return frozenset(
            name
            for name, module in self.sermon_names.items()
            if name[:1].isupper() and not name.isupper() and not module.startswith(STORE_PACKAGE)
        )


def locates_step_module(dotted: str) -> Path | None:
    parts = dotted.split(".")
    if not parts or parts[0] != STEP_PACKAGE:
        return None
    candidate = STEP_ROOT.joinpath(*parts[1:]).with_suffix(".py")
    return candidate if candidate.exists() else None


def resolves_sermon_value(module: str, name: str):
    try:
        value = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        return None
    if inspect.isclass(value):
        return None
    if inspect.isfunction(value) or isinstance(value, (str, int, float, tuple, frozenset, set, list, dict)):
        return (value,)
    return None


def builds_scope(path: Path, tree: ast.Module) -> ModuleScope:
    helpers = finds_module_helpers(tree)
    imported, namespaces, sermon_names = {}, {}, {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == SERMON_PACKAGE:
                for alias in node.names:
                    sermon_names[alias.asname or alias.name] = node.module
                continue
            source = locates_step_module(node.module)
            for alias in node.names:
                nested = locates_step_module(f"{node.module}.{alias.name}")
                if nested is not None:
                    namespaces[alias.asname or alias.name] = nested
                elif source is not None:
                    imported[alias.asname or alias.name] = (source, alias.name)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                pass
    for name, module in sermon_names.items():
        resolved = resolves_sermon_value(module, name)
        if resolved is not None:
            constants[name] = resolved[0]
    scope = ModuleScope(path, helpers, imported, namespaces, sermon_names, {}, constants)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in scope.units:
                scope.bound_units[node.targets[0].id] = value.func.id
    return scope


@cache
def reads_scope(path: Path) -> ModuleScope:
    return builds_scope(path, ast.parse(path.read_text()))


def resolves_callee(func: ast.expr, scope: ModuleScope):
    if isinstance(func, ast.Name):
        if func.id in scope.helpers:
            return scope.helpers[func.id], scope
        if func.id in scope.imported:
            source, name = scope.imported[func.id]
            other = reads_scope(source)
            found = other.helpers.get(name)
            return (found, other) if found is not None else None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        source = scope.namespaces.get(func.value.id)
        if source is not None:
            other = reads_scope(source)
            found = other.helpers.get(func.attr)
            return (found, other) if found is not None else None
    return None


def reaches_everything(node, scope: ModuleScope):
    reached = [(node, scope)]
    seen = {id(node)}
    position = 0
    while position < len(reached):
        body, where = reached[position]
        position += 1
        for call in ast.walk(body):
            if not isinstance(call, ast.Call):
                continue
            found = resolves_callee(call.func, where)
            if found is not None and id(found[0]) not in seen:
                seen.add(id(found[0]))
                reached.append(found)
    return reached


def binds_locals(node) -> dict[str, ast.expr]:
    counted: dict[str, int] = {}
    bound: dict[str, ast.expr] = {}
    for statement in ast.walk(node):
        targets = []
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, (ast.AnnAssign, ast.AugAssign, ast.For, ast.NamedExpr)):
            targets = [statement.target]
        for target in targets:
            for name in ast.walk(target):
                if isinstance(name, ast.Name):
                    counted[name.id] = counted.get(name.id, 0) + 1
                    if isinstance(statement, ast.Assign) and target is name:
                        bound[name.id] = statement.value
    return {name: value for name, value in bound.items() if counted.get(name) == 1}


ZERO_OR_ONE = (0, 1)


def checks_existence(node: ast.expr, bound: dict, depth: int = 0) -> bool:
    if depth > 4:
        return False
    if isinstance(node, ast.Call):
        called = node.func
        if isinstance(called, ast.Attribute) and called.attr in STORE_READERS:
            return True
        if isinstance(called, ast.Name) and called.id in {"len", "any", "bool", "list", "tuple"} and node.args:
            return checks_existence(node.args[0], bound, depth + 1)
        return False
    if isinstance(node, ast.Subscript):
        return checks_existence(node.value, bound, depth + 1)
    if isinstance(node, ast.Name) and node.id in bound:
        return checks_existence(bound[node.id], bound, depth + 1)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return all(checks_existence(value, bound, depth + 1) for value in node.values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        operator, other = node.ops[0], node.comparators[0]
        if not checks_existence(node.left, bound, depth + 1):
            return False
        literal = evaluates_statically(other)
        if isinstance(operator, ast.IsNot) and literal == (None,):
            return True
        if literal is None or literal[0] not in ZERO_OR_ONE:
            return False
        return (
            (isinstance(operator, ast.Gt) and literal[0] == 0)
            or (isinstance(operator, ast.GtE) and literal[0] == 1)
            or (isinstance(operator, ast.NotEq) and literal[0] == 0)
        )
    return False


def disjoins_existence(test: ast.expr, bound: dict) -> bool:
    return (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.Or)
        and any(checks_existence(value, bound) for value in test.values)
    )


def excuses_emptiness(test: ast.expr, bound: dict) -> bool:
    if not (isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or)):
        return False
    return any(
        isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not) and checks_existence(value.operand, bound)
        for value in test.values
    )


def lists_assertions(reached) -> list[tuple[ast.Assert, dict]]:
    found = []
    for body, _ in reached:
        bound = binds_locals(body)
        found += [(one, bound) for one in ast.walk(body) if isinstance(one, ast.Assert)]
    return found


def raises_or_fails(reached) -> bool:
    for body, _ in reached:
        for one in ast.walk(body):
            if isinstance(one, ast.Raise):
                return True
            if isinstance(one, ast.Call) and calls_pytest(one, ASSERTING_PYTEST_CALLS):
                return True
    return False


def asserts_only_existence(reached) -> bool:
    assertions = lists_assertions(reached)
    if not assertions or raises_or_fails(reached):
        return False
    return all(
        checks_existence(one.test, bound) or disjoins_existence(one.test, bound) for one, bound in assertions
    )


def asserts_a_disjoined_existence(reached) -> bool:
    return any(disjoins_existence(one.test, bound) for one, bound in lists_assertions(reached))


def inlines(node: ast.expr, bound: dict, depth: int = 0) -> ast.expr:
    class Inlines(ast.NodeTransformer):
        def visit_Name(self, name):
            if depth < 3 and name.id in bound and isinstance(name.ctx, ast.Load):
                return inlines(bound[name.id], bound, depth + 1)
            return name

    return Inlines().visit(ast.parse(ast.unparse(node), mode="eval").body)


def substitutes(node: ast.expr, bound: dict) -> str:
    return ast.dump(inlines(node, bound))


REFLEXIVE = (ast.Eq, ast.Is, ast.LtE, ast.GtE)


def compares_with_itself(reached) -> bool:
    for one, bound in lists_assertions(reached):
        for compare in ast.walk(one.test):
            if not isinstance(compare, ast.Compare):
                continue
            operands = [compare.left, *compare.comparators]
            for operator, left, right in zip(compare.ops, operands, operands[1:]):
                if isinstance(operator, REFLEXIVE) and substitutes(left, bound) == substitutes(right, bound):
                    return True
    return False


def asserts_by_call(call: ast.Call, scope: ModuleScope, seen: frozenset) -> bool:
    if calls_pytest(call, ASSERTING_PYTEST_CALLS):
        return True
    if isinstance(call.func, ast.Attribute) and call.func.attr.startswith("assert"):
        return True
    found = resolves_callee(call.func, scope)
    if found is None or id(found[0]) in seen:
        return False
    return always_asserts(found[0], found[1], seen | {id(found[0])})


def holds_an_asserting_call(node: ast.AST, scope: ModuleScope, seen: frozenset) -> bool:
    return any(
        isinstance(one, ast.Call) and asserts_by_call(one, scope, seen) for one in ast.walk(node)
    )


def merges_paths(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return first and second


def iterates_a_nonempty_literal(loop) -> bool:
    if not isinstance(loop, (ast.For, ast.AsyncFor)):
        return False
    value = evaluates_statically(loop.iter)
    return value is not None and bool(value[0])


def follows_paths(statements, entering, scope, seen, bound):
    current, safe = entering, True
    for statement in statements:
        if current is None:
            break
        if isinstance(statement, ast.Assert):
            if not excuses_emptiness(statement.test, bound):
                current = True
            continue
        if isinstance(statement, ast.Raise):
            current = None
            continue
        if isinstance(statement, ast.Return):
            asserted = current or (
                statement.value is not None and holds_an_asserting_call(statement.value, scope, seen)
            )
            safe = safe and bool(asserted)
            current = None
            continue
        if isinstance(statement, ast.If):
            if holds_an_asserting_call(statement.test, scope, seen):
                current = True
            body = follows_paths(statement.body, current, scope, seen, bound)
            orelse = follows_paths(statement.orelse, current, scope, seen, bound)
            safe = safe and body[1] and orelse[1]
            current = merges_paths(body[0], orelse[0])
            continue
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            if holds_an_asserting_call(statement.iter if hasattr(statement, "iter") else statement.test, scope, seen):
                current = True
            body = follows_paths(statement.body, current, scope, seen, bound)
            safe = safe and body[1]
            if iterates_a_nonempty_literal(statement) and body[0] is not None:
                current = body[0]
            continue
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            raising = any(
                isinstance(item.context_expr, ast.Call) and calls_pytest(item.context_expr, ASSERTING_PYTEST_CALLS)
                for item in statement.items
            )
            body = follows_paths(statement.body, current, scope, seen, bound)
            safe = safe and body[1]
            current = True if raising else body[0]
            continue
        if isinstance(statement, ast.Try):
            body = follows_paths(statement.body, current, scope, seen, bound)
            ending = follows_paths(statement.orelse, body[0], scope, seen, bound) if body[0] is not None else body
            outcomes = [ending]
            for handler in statement.handlers:
                outcomes.append(follows_paths(handler.body, current, scope, seen, bound))
            safe = safe and body[1] and all(one[1] for one in outcomes)
            current = outcomes[0][0]
            for one in outcomes[1:]:
                current = merges_paths(current, one[0])
            if statement.finalbody and current is not None:
                final = follows_paths(statement.finalbody, current, scope, seen, bound)
                safe = safe and final[1]
                current = final[0]
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if holds_an_asserting_call(statement, scope, seen):
            current = True
    return current, safe


def always_asserts(node, scope: ModuleScope, seen: frozenset = frozenset()) -> bool:
    ending, safe = follows_paths(strips_docstring(node.body), False, scope, seen | {id(node)}, binds_locals(node))
    return safe and ending is not False


def invokes_units(reached) -> frozenset[str]:
    invoked = set()
    for body, scope in reached:
        units = scope.units
        constructed = {}
        for statement in ast.walk(body):
            if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call):
                built = statement.value.func
                if isinstance(built, ast.Name) and built.id in units:
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            constructed[target.id] = built.id
        for call in ast.walk(body):
            if not isinstance(call, ast.Call):
                continue
            called = call.func
            if isinstance(called, ast.Call) and isinstance(called.func, ast.Name) and called.func.id in units:
                invoked.add(called.func.id)
            elif isinstance(called, ast.Name) and called.id in constructed:
                invoked.add(constructed[called.id])
            elif isinstance(called, ast.Name) and called.id in scope.bound_units:
                invoked.add(scope.bound_units[called.id])
    return frozenset(name for name in invoked if name not in PERMITTED_THEN_UNITS)


def names_store_flag(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == STORE_FIXTURE and node.attr.startswith("_") and not node.attr.startswith("__"):
            return node.attr
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"getattr", "hasattr", "setattr"}:
        arguments = node.args
        if len(arguments) >= 2 and isinstance(arguments[0], ast.Name) and arguments[0].id == STORE_FIXTURE:
            if isinstance(arguments[1], ast.Constant) and str(arguments[1].value).startswith("_"):
                return arguments[1].value
    return None


def writes_store_flags(reached) -> dict[str, list[ast.expr]]:
    written: dict[str, list[ast.expr]] = {}
    for body, _ in reached:
        for statement in ast.walk(body):
            if isinstance(statement, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    for part in ast.walk(target):
                        flag = names_store_flag(part) if isinstance(part, ast.Attribute) else None
                        if flag is not None and isinstance(part.ctx, ast.Store):
                            written.setdefault(flag, []).append(statement.value)
            elif isinstance(statement, ast.Call) and isinstance(statement.func, ast.Name):
                if statement.func.id == "setattr":
                    flag = names_store_flag(statement)
                    if flag is not None and len(statement.args) > 2:
                        written.setdefault(flag, []).append(statement.args[2])
    return written


VALUE_CONTEXTS = (ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Assert, ast.Assign, ast.IfExp, ast.FormattedValue)


def reads_store_flags(reached) -> frozenset[str]:
    read = set()
    own = reached[0][0] if reached else None
    for body, _ in reached:
        parents = {id(child): parent for parent in ast.walk(body) for child in ast.iter_child_nodes(parent)}
        searched = [body] if body is own else [one for one in ast.walk(body) if isinstance(one, ast.Assert)]
        for statement in (node for root in searched for node in ast.walk(root)):
            flag = None
            if isinstance(statement, ast.Attribute) and isinstance(statement.ctx, ast.Load):
                flag = names_store_flag(statement)
            elif isinstance(statement, ast.Call) and isinstance(statement.func, ast.Name):
                if statement.func.id in {"getattr", "hasattr"}:
                    flag = names_store_flag(statement)
            if flag is not None and isinstance(parents.get(id(statement)), VALUE_CONTEXTS):
                read.add(flag)
    return frozenset(read)


def writes_the_store(reached) -> bool:
    for body, scope in reached:
        for statement in ast.walk(body):
            if isinstance(statement, ast.Call):
                called = statement.func
                if isinstance(called, ast.Attribute) and called.attr in STORE_WRITERS:
                    return True
                if isinstance(called, ast.Name) and called.id in scope.sermon_names and called.id.startswith("writes_"):
                    return True
        if writes_store_flags([(body, scope)]):
            return True
    return False


def roots_expression(node: ast.expr) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


SYSTEM_MODULES = frozenset({"subprocess"})


def invokes_the_system(reached, parameters: frozenset[str]) -> bool:
    if invokes_units(reached):
        return True
    for body, scope in reached:
        sermon = {
            name for name, module in scope.sermon_names.items() if not module.startswith(STORE_PACKAGE)
        }
        callers = (set(parameters) - {STORE_FIXTURE}) | sermon | SYSTEM_MODULES | set(scope.bound_units)
        for _ in range(2):
            for statement in ast.walk(body):
                if isinstance(statement, ast.Assign) and roots_expression(statement.value) in callers:
                    callers |= {target.id for target in statement.targets if isinstance(target, ast.Name)}
        for call in ast.walk(body):
            if not isinstance(call, ast.Call):
                continue
            root = roots_expression(call.func)
            if root in callers and not (isinstance(call.func, ast.Name) and call.func.id in sermon and call.func.id.startswith("writes_")):
                return True
    return False


def binds_gherkin_names(parser) -> frozenset[str]:
    return names_gherkin_arguments(parser) - GHERKIN_BLOCK_ARGUMENTS


def proposes_operands(test: ast.expr):
    yield test, False
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        for value in test.values:
            yield value, True


OPAQUE_NODES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Attribute, ast.Subscript)


def holds_for_some_binding(
    operand: ast.expr, gherkin: frozenset[str], scope: ModuleScope, bindings, disjunct: bool
) -> bool:
    if any(isinstance(one, OPAQUE_NODES) for one in ast.walk(operand)):
        return False
    used = {one.id for one in ast.walk(operand) if isinstance(one, ast.Name)}
    known = gherkin | set(SAFE_BUILTINS) | (set(scope.constants) if disjunct else set())
    if not used or not used <= known:
        return False
    if not used & gherkin:
        if not any(isinstance(one, ast.Call) for one in ast.walk(operand)):
            return False
        bindings = [{}]
    if not bindings:
        return False
    compiled = compile(ast.Expression(body=operand), "<operand>", "eval")
    for binding in bindings:
        namespace = {"__builtins__": SAFE_BUILTINS, **scope.constants, **binding}
        try:
            if eval(compiled, namespace):
                return True
        except Exception:
            continue
    return False


def finds_argument_truths(definition, bindings) -> bool:
    gherkin = binds_gherkin_names(definition.parser)
    for statement in ast.walk(definition.node):
        if not isinstance(statement, ast.Assert):
            continue
        for operand, disjunct in proposes_operands(statement.test):
            if disjunct and tests_membership_of_a_vocabulary(operand, gherkin, definition.scope):
                return True
            if holds_for_some_binding(operand, gherkin, definition.scope, bindings, disjunct):
                return True
    return False


def tests_membership_of_a_vocabulary(operand: ast.expr, gherkin: frozenset[str], scope: ModuleScope) -> bool:
    if not (isinstance(operand, ast.Compare) and len(operand.ops) == 1 and isinstance(operand.ops[0], ast.In)):
        return False
    member, vocabulary = operand.left, operand.comparators[0]
    return (
        isinstance(member, ast.Name)
        and member.id in gherkin
        and isinstance(vocabulary, ast.Name)
        and vocabulary.id in scope.sermon_names
        and vocabulary.id in scope.constants
    )


def judges_definition(
    kind, parser, node, helpers, truths, sermon_names, payloads=frozenset(), rendered=False, scope=None
) -> tuple[str, ...]:
    faults = []
    gherkin = names_gherkin_arguments(parser)
    bodies = reaches_bodies(node, helpers)
    reached = reaches_everything(node, scope) if scope is not None else [(node, None)]
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
        elif scope is not None:
            faults += judges_a_then(node, scope, reached)
        if rendered and reads_the_view_model(node, helpers, payloads):
            faults.append(VIEW_MODEL_THEN)
    elif kind == "when":
        if omits_a_body(node):
            faults.append(HOLLOW_WHEN)
        elif not acts_on_something(node, helpers, sermon_names, names_parameters(node)):
            faults.append(INERT_WHEN)
        elif scope is not None and writes_the_store(reached):
            if not invokes_the_system(reached, names_parameters(node)):
                faults.append(STAGING_WHEN)
    elif omits_a_body(node) and (parser is None or parser.name not in PERMITTED_EMPTY_GIVENS):
        faults.append(UNENUMERATED_GIVEN)
    return tuple(faults)


def judges_a_then(node, scope, reached) -> list[str]:
    faults = []
    if asserts_only_existence(reached):
        faults.append(EXISTENCE_THEN)
    if asserts_a_disjoined_existence(reached):
        faults.append(EXISTENCE_DISJUNCT)
    if not always_asserts(node, scope):
        faults.append(UNASSERTED_PATH)
    if compares_with_itself(reached):
        faults.append(SELF_COMPARISON)
    if invokes_units(reached):
        faults.append(INVOKING_THEN)
    if writes_the_store(reached):
        faults.append(WRITING_THEN)
    return faults


def judges_step_module(path: Path, root: Path, payloads=frozenset()) -> list[Definition]:
    tree = ast.parse(path.read_text())
    helpers = finds_module_helpers(tree)
    truths = finds_module_truths(tree)
    sermon_names = finds_sermon_names(tree)
    scope = builds_scope(path, tree)
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
                        kind, parser, node, helpers, truths, sermon_names, payloads, rendered, scope
                    ),
                    omitted=omits_a_body(node),
                    parser=parser,
                    node=node,
                    scope=scope,
                )
            )
    return found


RECORDING_METHODS = frozenset({"append", "extend", "add", "update", "setdefault", "insert"})


def records_into_flags(reached) -> frozenset[str]:
    recorded = set()
    for body, _ in reached:
        for call in ast.walk(body):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                if call.func.attr in RECORDING_METHODS:
                    flag = names_store_flag(call.func.value)
                    if flag is not None:
                        recorded.add(flag)
    return frozenset(recorded)


def holds_data(value: ast.expr, gherkin: frozenset[str], bound: dict, depth: int = 0) -> bool:
    """A value made only of literals and the step's own Gherkin arguments, not an object the system fills."""
    if depth > 4:
        return False
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, ast.Name):
        if value.id in gherkin:
            return True
        return value.id in bound and holds_data(bound[value.id], gherkin, bound, depth + 1)
    if isinstance(value, ast.Call):
        arguments = [*value.args, *(keyword.value for keyword in value.keywords)]
        return bool(arguments) and all(holds_data(one, gherkin, bound, depth + 1) for one in arguments)
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return all(holds_data(one, gherkin, bound, depth + 1) for one in value.elts)
    if isinstance(value, ast.BinOp):
        return holds_data(value.left, gherkin, bound, depth + 1) and holds_data(value.right, gherkin, bound, depth + 1)
    if isinstance(value, ast.UnaryOp):
        return holds_data(value.operand, gherkin, bound, depth + 1)
    return False


def finds_staged_flags(definitions: list[Definition]):
    staged, written, recorded = set(), set(), set()
    for one in definitions:
        reached = reaches_everything(one.node, one.scope)
        flags = writes_store_flags(reached)
        recorded |= records_into_flags(reached)
        written |= set(flags)
        gherkin = binds_gherkin_names(one.parser) if one.parser is not None else frozenset()
        bound = binds_locals(one.node)
        for flag, values in flags.items():
            if any(holds_data(value, gherkin, bound) for value in values):
                staged.add(flag)
    return frozenset(staged - recorded), frozenset(written | recorded)


def collects_bindings(definitions: list[Definition], spec_root: Path):
    index = indexes_by_kind(definitions)
    bindings: dict[str, list[dict]] = {}
    scenarios: list[frozenset[Definition]] = []
    for _, template, tags in reads_scenario_templates(spec_root):
        for context, example_tags in expands_contexts(template):
            scenario = template.render(context)
            thens = set()
            for step in scenario.steps:
                for one in matches_step(index, step.type, step.name):
                    if one.kind == "then":
                        thens.add(one)
                    try:
                        arguments = one.parser.parse_arguments(step.name) or {}
                    except Exception:
                        continue
                    bindings.setdefault(one.location, []).append(dict(arguments))
            scenarios.append(frozenset(thens))
    return bindings, scenarios


def orders_faults(faults) -> tuple[str, ...]:
    return tuple(sorted(set(faults), key=FAULT_ORDER.index))


def normalises_assertions(one: Definition) -> frozenset[str]:
    bound = binds_locals(one.node)
    return frozenset(
        substitutes(statement.test, bound) for statement in ast.walk(one.node) if isinstance(statement, ast.Assert)
    )


def finds_duplicated_thens(scenarios) -> frozenset[str]:
    duplicated = set()
    for thens in set(scenarios):
        claims: dict[frozenset[str], set[str]] = {}
        for one in thens:
            if one.node is None or one.omitted:
                continue
            asserted = normalises_assertions(one)
            if asserted:
                claims.setdefault(asserted, set()).add(one.location)
        for locations in claims.values():
            if len(locations) > 1:
                duplicated |= locations
    return frozenset(duplicated)


def judges_across_steps(definitions: list[Definition], spec_root: Path | None) -> list[Definition]:
    staged, written = finds_staged_flags(definitions)
    bindings, scenarios = collects_bindings(definitions, spec_root) if spec_root is not None else ({}, [])
    duplicated = finds_duplicated_thens(scenarios)
    judged = []
    for one in definitions:
        added = [DUPLICATE_THEN] if one.location in duplicated else []
        if one.kind == "then" and one.node is not None and not one.omitted:
            read = reads_store_flags(reaches_everything(one.node, one.scope))
            if read & staged or read - written:
                added.append(STAGED_FLAG)
            if one.parser is not None and finds_argument_truths(one, bindings.get(one.location, [])):
                added.append(ARGUMENT_TRUTH)
        judged.append(replace(one, faults=orders_faults((*one.faults, *added))) if added else one)
    return judged


def judges_step_tree(
    step_root: Path = STEP_ROOT, root: Path | None = None, spec_root: Path | None = None
) -> list[Definition]:
    base = root if root is not None else PROJECT_ROOT
    if spec_root is None and step_root == STEP_ROOT:
        spec_root = SPEC_ROOT
    payloads = finds_payload_names(step_root)
    found = []
    for path in sorted(step_root.rglob("[!_]*.py")):
        found += judges_step_module(path, base, payloads)
    found = judges_across_steps(found, spec_root)
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
