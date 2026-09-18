#!/usr/bin/env python3
"""Guardrail for the specification's portability.

This file is not part of the spec. It exists because the spec is the primary
artifact — the thing that survives a rewrite in another language — and that only
stays true if something checks it. Four Gherkin syntax errors sat in these files
for weeks (2026-09-18) purely because nobody had ever run a parser over them.

Run it from `features/`:

    python3 validate_spec.py

It checks four things:

1. **Every file parses**, using `gherkin-official` — the same parser
   cucumber-ruby and cucumber-js use. Passing here means any Cucumber
   implementation can read these files, which is the whole point.
2. **No implementation vocabulary has leaked.** The spec may name what the system
   *talks to* (HTTP, S3, ffmpeg, ollama, a tailnet) because those are part of the
   contract. It may not name what the system is *built with* — a framework, a
   database, a language, a job library — because that is exactly what a rewrite
   changes. Technology names are allowed inside `#` comments, where they cite
   measurements.
3. **Every tag is declared** in README.md's tag table, so tags stay a closed
   vocabulary rather than accumulating synonyms.
4. **Every Rule has at least one Scenario**, since an empty Rule is a heading
   that looks like a requirement.
"""

from __future__ import annotations

import pathlib
import re
import sys

# What the system is built with. A rewrite changes all of these, so none may
# appear in a scenario.
FORBIDDEN = [
    "django", "rails", "flask", "fastapi", "sinatra", "express", "next.js",
    "sqlite", "postgres", "postgresql", "mysql", "redis", "celery", "sidekiq",
    "solid queue", "huey", "activerecord", "queryset", "orm", "migration",
    "python", "ruby", "javascript", "typescript", "react", "vue", "svelte",
    "htmx", "tailwind", "pytest", "rspec", "docker", "kubernetes",
]

TAG_RE = re.compile(r"@[a-z0-9-]+")
RULE_RE = re.compile(r"^\s*Rule:")
SCENARIO_RE = re.compile(r"^\s*Scenario")


def declared_tags(readme: pathlib.Path) -> set[str]:
    section = readme.read_text().split("## Tag conventions", 1)
    if len(section) < 2:
        return set()
    return set(TAG_RE.findall(section[1].split("## Reading order")[0]))


def main() -> int:
    here = pathlib.Path(__file__).parent
    features = sorted(here.rglob("*.feature"))
    if not features:
        print("no feature files found", file=sys.stderr)
        return 1

    problems: list[str] = []

    # 1. Parse with the official parser.
    try:
        from gherkin.errors import CompositeParserException
        from gherkin.parser import Parser
    except ImportError:
        print("gherkin-official is not installed:  pip install gherkin-official",
              file=sys.stderr)
        return 2

    scenarios = rules = 0
    for f in features:
        try:
            Parser().parse(f.read_text())
        except CompositeParserException as e:
            problems.append(f"{f.relative_to(here)}: will not parse — {e}")
            continue
        lines = f.read_text().splitlines()
        rules += sum(1 for ln in lines if RULE_RE.match(ln))
        scenarios += sum(1 for ln in lines if SCENARIO_RE.match(ln))

    # 2. No implementation vocabulary outside comments.
    for f in features:
        for i, ln in enumerate(f.read_text().splitlines(), 1):
            if ln.lstrip().startswith("#"):
                continue
            low = ln.lower()
            for word in FORBIDDEN:
                if re.search(rf"\b{re.escape(word)}\b", low):
                    problems.append(
                        f"{f.relative_to(here)}:{i}: implementation vocabulary "
                        f"{word!r} — the spec names what the system talks to, "
                        f"not what it is built with")

    # 3. Tags are a closed vocabulary.
    known = declared_tags(here / "README.md")
    for f in features:
        for i, ln in enumerate(f.read_text().splitlines(), 1):
            s = ln.strip()
            if not s.startswith("@"):
                continue
            for tag in TAG_RE.findall(s):
                if tag not in known:
                    problems.append(
                        f"{f.relative_to(here)}:{i}: tag {tag} is not declared "
                        f"in README.md's tag table")

    # 4. No empty Rules.
    for f in features:
        lines = f.read_text().splitlines()
        for i, ln in enumerate(lines):
            if not RULE_RE.match(ln):
                continue
            rest = lines[i + 1:]
            nxt = next((x for x in rest if RULE_RE.match(x) or SCENARIO_RE.match(x)), None)
            if nxt is None or RULE_RE.match(nxt):
                problems.append(
                    f"{f.relative_to(here)}:{i+1}: Rule has no Scenario — "
                    f"a heading that reads like a requirement")

    if problems:
        print(f"{len(problems)} problem(s):\n")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"spec OK — {len(features)} files, {scenarios} scenarios, {rules} rules")
    print("parsed with gherkin-official; portable to any Cucumber implementation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
