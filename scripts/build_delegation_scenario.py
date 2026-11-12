#!/usr/bin/env python3
"""Build the curated scenario for the liquid democracy demo.

Writes delegation/data/scenario_v3.json from two sources:

- delegation/data/measures_v3.json, hand-written: the city, the ballot
  papers, every measure with its official wording, fiscal note and
  arguments, the support numbers for the toy population, and the viewer's
  account and its past
- recorded judgments: the category pool and its nesting from the router
  evaluation (eval/benchmarks/delegation_router_v1/), and one yes/no
  judgment for every measure against every pool category

A judgment belongs to the exact title, summary and option names the decision
model was shown. A measure whose wording is unchanged since the evaluation
reuses the evaluation's recorded answers. A measure that was reworded needs
new ones, recorded in delegation/data/recorded_v3/judgments.jsonl by the
`collect` command. Until they are collected, `build` uses the answers
recorded for the question's earlier wording and lists the question under
"provisional" in the scenario file; `build --strict` refuses to do that.

`build` and `plan` use no network and are deterministic: the same sources
give a byte-identical file. `collect` calls hosted Jev, which costs money,
and so needs --live.

Usage:
    python scripts/build_delegation_scenario.py            # build
    python scripts/build_delegation_scenario.py plan       # what collect would ask
    python scripts/build_delegation_scenario.py collect --live
    python scripts/build_delegation_scenario.py build --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from delegation import (  # noqa: E402
    DEFAULT_THRESHOLD,
    Category,
    JudgmentStore,
    NestingStore,
    Question,
    gather_judgments,
    gather_nesting,
)
from delegation.jev import JEV_MODEL  # noqa: E402
from delegation.scenario import (  # noqa: E402
    DATA,
    DEFAULT_OPEN_DAYS,
    MEASURES_PATH,
    MEASURES_SCHEMA,
    SCENARIO_PATH,
    SCENARIO_SCHEMA,
    Measure,
    label_for,
    read_measure,
)
from eval.delegation_router import (  # noqa: E402
    RouterEvalConfig,
    RouterFixture,
    load_fixture,
    ordered_pairs,
)

BENCHMARK = ROOT / "eval" / "benchmarks" / "delegation_router_v1"
# Judgments for measures reworded since the evaluation
RECORDED = DATA / "recorded_v3" / "judgments.jsonl"
ENV_FILE = ROOT / ".env.local"


def _source() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(MEASURES_PATH.read_text(encoding="utf-8"))
    if raw.get("schema") != MEASURES_SCHEMA:
        raise SystemExit(f"{MEASURES_PATH.name}: expected schema {MEASURES_SCHEMA!r}")
    return raw


def _measures(raw: dict[str, Any]) -> list[Measure]:
    return [
        read_measure(measure, index)
        for paper in raw["ballot_papers"]
        for index, measure in enumerate(paper["measures"])
    ]


def _judged(
    questions: Sequence[Question], categories: Sequence[Category]
) -> tuple[dict[tuple[str, str], float], list[Question]]:
    """
    Every recorded judgment for the questions as now worded, and the
    questions that are missing at least one.
    """
    judgments: dict[tuple[str, str], float] = {}
    for path in (BENCHMARK / "judgments.jsonl", RECORDED):
        report = gather_judgments(
            questions, categories, JudgmentStore(path), model=JEV_MODEL
        )
        judgments.update(report.judgments)
    missing = [
        question
        for question in questions
        if any((question.id, category.id) not in judgments for category in categories)
    ]
    return judgments, missing


def build(strict: bool = False) -> dict[str, Any]:
    """The scenario, from the written measures and the recorded answers."""
    raw = _source()
    fixture = load_fixture()
    config = RouterEvalConfig()
    categories = [entry.category for entry in fixture.categories]
    measures = _measures(raw)
    questions = [measure.question for measure in measures]

    judgments, missing = _judged(questions, categories)
    if missing and strict:
        raise SystemExit(
            f"{len(missing)} measures are not judged as now worded; run collect"
        )
    provisional = _stand_ins(fixture, missing, categories)
    judgments.update(provisional)

    nested = gather_nesting(
        ordered_pairs(fixture),
        NestingStore(BENCHMARK / "nesting.jsonl"),
        model=JEV_MODEL,
        threshold=config.nesting_threshold,
    )
    if nested.missing:
        raise SystemExit(
            f"{len(nested.missing)} containment judgments are not recorded"
        )

    return {
        "schema": SCENARIO_SCHEMA,
        "model": JEV_MODEL,
        "threshold": DEFAULT_THRESHOLD,
        "nesting_threshold": config.nesting_threshold,
        "source": {
            "measures_sha256": _sha256(MEASURES_PATH),
            "benchmark": BENCHMARK.relative_to(ROOT).as_posix(),
            "benchmark_judgments_sha256": _sha256(BENCHMARK / "judgments.jsonl"),
            "nesting_sha256": _sha256(BENCHMARK / "nesting.jsonl"),
            "recorded_judgments_sha256": (
                _sha256(RECORDED) if RECORDED.exists() else None
            ),
        },
        "provisional": sorted(question.id for question in missing),
        "city": raw["city"],
        "categories": [
            {"id": category.id, "text": category.text} for category in categories
        ],
        "nesting": sorted([narrow, broad] for narrow, broad in nested.nesting),
        "viewer": raw["viewer"],
        "ballot_papers": [
            {
                "id": paper["id"],
                "title": paper["title"],
                "jurisdiction": paper["jurisdiction"],
                "closes_in_days": paper["closes_in_days"],
                "opens_in_days": paper.get(
                    "opens_in_days", paper["closes_in_days"] - DEFAULT_OPEN_DAYS
                ),
                "measures": [
                    {"label": label_for(index), **measure}
                    for index, measure in enumerate(paper["measures"])
                ],
            }
            for paper in raw["ballot_papers"]
        ],
        "judgments": {
            question.id: {
                category.id: judgments[(question.id, category.id)]
                for category in categories
            }
            for question in questions
        },
    }


def _stand_ins(
    fixture: RouterFixture, missing: Sequence[Question], categories: Sequence[Category]
) -> dict[tuple[str, str], float]:
    """The answers recorded for the earlier wording of each unjudged question."""
    if not missing:
        return {}
    earlier = [fixture.labelled(question.id).question for question in missing]
    report = gather_judgments(
        earlier,
        categories,
        JudgmentStore(BENCHMARK / "judgments.jsonl"),
        model=JEV_MODEL,
    )
    if report.missing:
        raise SystemExit(
            f"{len(report.missing)} judgments have no recorded stand-in; run collect"
        )
    return report.judgments


def scenario_bytes(strict: bool = False) -> bytes:
    return (json.dumps(build(strict), indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _unjudged() -> tuple[list[Question], list[Category]]:
    categories = [entry.category for entry in load_fixture().categories]
    _, missing = _judged(
        [measure.question for measure in _measures(_source())], categories
    )
    return missing, categories


def plan() -> int:
    missing, categories = _unjudged()
    print(f"Measures not judged as now worded: {len(missing)}")
    for question in missing:
        print(f"  {question.id}  {question.title}")
    print(
        f"collect would send {len(missing)} requests "
        f"for {len(missing) * len(categories)} judgments to {JEV_MODEL}."
    )
    return 0


def collect() -> int:
    from delegation.jev import JevSource, read_api_key

    missing, categories = _unjudged()
    if not missing:
        print("Nothing to collect.")
        return 0
    key = read_api_key(ENV_FILE)
    if not key:
        raise SystemExit("No API key: set TYPESAFE_API_KEY or add it to .env.local")
    source = JevSource(key)
    try:
        report = gather_judgments(
            missing, categories, JudgmentStore(RECORDED), model=JEV_MODEL, source=source
        )
    finally:
        source.close()
    print(
        f"Recorded {report.fetched} judgments in {source.requests} requests; "
        f"{len(report.missing)} still missing."
    )
    for failure in report.failures:
        print(f"  failed: {failure}")
    return 1 if report.missing else 0


def write(strict: bool) -> int:
    body = scenario_bytes(strict)
    SCENARIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_PATH.write_bytes(body)
    provisional = json.loads(body)["provisional"]
    print(f"{SCENARIO_PATH.relative_to(ROOT).as_posix()}: {len(body) / 1024:.1f} KB")
    if provisional:
        print(
            f"{len(provisional)} measures use judgments recorded for their "
            f"earlier wording: {', '.join(provisional)}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command")
    built = commands.add_parser("build")
    built.add_argument("--strict", action="store_true")
    commands.add_parser("plan")
    paid = commands.add_parser("collect")
    paid.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "plan":
        return plan()
    if args.command == "collect":
        if not args.live:
            raise SystemExit("'collect' calls hosted Jev and costs money; pass --live")
        return collect()
    return write(bool(getattr(args, "strict", False)))


if __name__ == "__main__":
    raise SystemExit(main())
