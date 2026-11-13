#!/usr/bin/env python3
"""Build the curated scenario for the liquid democracy demo.

Writes delegation/data/scenario_v3.json from two sources:

- delegation/data/measures_v3.json, hand-written: the city, the ballot
  papers, every measure with its official wording, fiscal note and
  arguments, the support numbers for the toy population, and the viewer's
  account and its past
- recorded judgments: the category pool and its nesting from the router
  evaluation (eval/benchmarks/delegation_router_v1/), and one yes/no
  judgment for every measure against every category

The measures file also lists other wordings some residents use for a pool
category. Each is a category of its own and needs the same judgments: one
against every measure, and containment against every other category both
ways (recorded_v3/nesting.jsonl). Nesting and the groups of wordings that
mean the same thing are both derived from the containment answers. A
wording that is not fully judged is left out of the scenario.

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
    create_category,
    derive_nesting,
    gather_judgments,
    gather_nesting,
    normalize_category_text,
)
from delegation.grouping import derive_groups  # noqa: E402
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
)

BENCHMARK = ROOT / "eval" / "benchmarks" / "delegation_router_v1"
# Judgments for measures reworded since the evaluation
RECORDED = DATA / "recorded_v3" / "judgments.jsonl"
# Containment judgments that involve a wording outside the evaluation's pool
RECORDED_NESTING = DATA / "recorded_v3" / "nesting.jsonl"
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
    pool = [entry.category for entry in fixture.categories]
    measures = _measures(raw)
    questions = [measure.question for measure in measures]

    judgments, missing = _judged(questions, pool)
    if missing and strict:
        raise SystemExit(
            f"{len(missing)} measures are not judged as now worded; run collect"
        )
    provisional = _stand_ins(fixture, missing, pool)
    judgments.update(provisional)

    # Other wordings join the scenario only once they are fully judged
    authored = _wordings(raw, pool)
    wording_judgments, unjudged = _wordings_judged(questions, pool, authored)
    if unjudged and strict:
        raise SystemExit(
            f"{len(unjudged)} wordings are not fully judged; run collect"
        )
    wording_of = {
        wording.id: base
        for base, others in authored.items()
        for wording in others
        if wording.id not in unjudged
    }
    categories = pool + [
        wording
        for others in authored.values()
        for wording in others
        if wording.id in wording_of
    ]
    judgments.update(wording_judgments)

    contained = _containment(categories)
    wanted = [
        (first.id, second.id)
        for first in categories
        for second in categories
        if first.id != second.id
    ]
    absent = [pair for pair in wanted if pair not in contained]
    if absent:
        raise SystemExit(f"{len(absent)} containment judgments are not recorded")
    nesting = derive_nesting(contained, config.nesting_threshold)
    groups = derive_groups(
        [category.id for category in categories], contained, config.nesting_threshold
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
            "recorded_nesting_sha256": (
                _sha256(RECORDED_NESTING) if RECORDED_NESTING.exists() else None
            ),
        },
        "provisional": sorted(question.id for question in missing),
        "city": raw["city"],
        "categories": [
            {"id": category.id, "text": category.text}
            | (
                {"wording_of": wording_of[category.id]}
                if category.id in wording_of
                else {}
            )
            for category in categories
        ],
        "unjudged_wordings": sorted(
            wording.text
            for others in authored.values()
            for wording in others
            if wording.id in unjudged
        ),
        "groups": [list(group) for group in groups],
        "nesting": sorted([narrow, broad] for narrow, broad in nesting),
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


def _wordings(
    raw: dict[str, Any], pool: Sequence[Category]
) -> dict[str, list[Category]]:
    """The other wordings written for pool categories, by pool category id."""
    by_text = {normalize_category_text(category.text): category for category in pool}
    taken = set(by_text)
    wordings: dict[str, list[Category]] = {}
    for entry in raw.get("wordings", []):
        base = by_text.get(normalize_category_text(entry["of"]))
        if base is None:
            raise SystemExit(f"wordings: {entry['of']!r} is not a pool category")
        for text in entry["also"]:
            wording = create_category(text)
            if normalize_category_text(wording.text) in taken:
                raise SystemExit(f"wordings: {text!r} is written twice")
            taken.add(normalize_category_text(wording.text))
            wordings.setdefault(base.id, []).append(wording)
    return wordings


def _wordings_judged(
    questions: Sequence[Question],
    pool: Sequence[Category],
    wordings: dict[str, list[Category]],
) -> tuple[dict[tuple[str, str], float], set[str]]:
    """
    The recorded judgments for the other wordings, and the ids of the
    wordings that are missing one: against a measure, or against another
    category either way round.
    """
    others = [wording for group in wordings.values() for wording in group]
    report = gather_judgments(
        questions, others, JudgmentStore(RECORDED), model=JEV_MODEL
    )
    unjudged = {category_id for _, category_id in report.missing}
    contained = _containment([*pool, *others])
    everyone = [*pool, *others]
    for wording in others:
        for other in everyone:
            if other.id == wording.id:
                continue
            if (wording.id, other.id) not in contained or (
                other.id,
                wording.id,
            ) not in contained:
                unjudged.add(wording.id)
    return report.judgments, unjudged


def _containment(categories: Sequence[Category]) -> dict[tuple[str, str], float]:
    """Every recorded containment judgment between these categories."""
    pairs = [
        (first, second)
        for first in categories
        for second in categories
        if first.id != second.id
    ]
    contained: dict[tuple[str, str], float] = {}
    for path in (BENCHMARK / "nesting.jsonl", RECORDED_NESTING):
        report = gather_nesting(pairs, NestingStore(path), model=JEV_MODEL)
        contained.update(report.probabilities)
    return contained


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


# The most containment pairs sent in one request
NESTING_BATCH = 60


class _Wanted:
    """What is not yet recorded for the scenario as now written."""

    def __init__(self) -> None:
        raw = _source()
        self.pool = [entry.category for entry in load_fixture().categories]
        self.questions = [measure.question for measure in _measures(raw)]
        # Measures reworded since the evaluation, against the pool
        _, self.reworded = _judged(self.questions, self.pool)
        # Every measure against the other wordings
        self.wordings = [
            wording for group in _wordings(raw, self.pool).values() for wording in group
        ]
        report = gather_judgments(
            self.questions, self.wordings, JudgmentStore(RECORDED), model=JEV_MODEL
        )
        self.wording_judgments = len(report.missing)
        self.wording_questions = [
            question
            for question in self.questions
            if any(question_id == question.id for question_id, _ in report.missing)
        ]
        # Containment between every two categories, both ways
        everyone = [*self.pool, *self.wordings]
        contained = _containment(everyone)
        self.pairs = [
            (first, second)
            for first in everyone
            for second in everyone
            if first.id != second.id and (first.id, second.id) not in contained
        ]

    @property
    def requests(self) -> int:
        return (
            len(self.reworded)
            + len(self.wording_questions)
            + -(-len(self.pairs) // NESTING_BATCH)
        )

    @property
    def judgments(self) -> int:
        return (
            len(self.reworded) * len(self.pool)
            + self.wording_judgments
            + len(self.pairs)
        )


def plan() -> int:
    wanted = _Wanted()
    print(f"Measures not judged as now worded: {len(wanted.reworded)}")
    for question in wanted.reworded:
        print(f"  {question.id}  {question.title}")
    print(
        f"Other wordings: {len(wanted.wordings)}; "
        f"{wanted.wording_judgments} judgments against measures missing, "
        f"in {len(wanted.wording_questions)} requests"
    )
    print(
        f"Containment pairs missing: {len(wanted.pairs)}, "
        f"in {-(-len(wanted.pairs) // NESTING_BATCH)} requests"
    )
    print(
        f"collect would send {wanted.requests} requests "
        f"for {wanted.judgments} judgments to {JEV_MODEL}."
    )
    return 0


def collect() -> int:
    from delegation.jev import JevSource, read_api_key

    wanted = _Wanted()
    if not wanted.requests:
        print("Nothing to collect.")
        return 0
    key = read_api_key(ENV_FILE)
    if not key:
        raise SystemExit("No API key: set TYPESAFE_API_KEY or add it to .env.local")
    source = JevSource(key)
    fetched = 0
    missing = 0
    failures: list[str] = []
    try:
        for questions, categories in (
            (wanted.reworded, wanted.pool),
            (wanted.wording_questions, wanted.wordings),
        ):
            if not questions or not categories:
                continue
            report = gather_judgments(
                questions,
                categories,
                JudgmentStore(RECORDED),
                model=JEV_MODEL,
                source=source,
            )
            fetched += report.fetched
            missing += len(report.missing)
            failures += report.failures
        if wanted.pairs:
            nested = gather_nesting(
                wanted.pairs,
                NestingStore(RECORDED_NESTING),
                model=JEV_MODEL,
                source=source,
                batch_size=NESTING_BATCH,
            )
            fetched += nested.fetched
            missing += len(nested.missing)
            failures += nested.failures
    finally:
        source.close()
    print(
        f"Recorded {fetched} judgments in {source.requests} requests; "
        f"{missing} still missing."
    )
    for failure in failures:
        print(f"  failed: {failure}")
    return 1 if missing else 0


def write(strict: bool) -> int:
    body = scenario_bytes(strict)
    SCENARIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_PATH.write_bytes(body)
    provisional = json.loads(body)["provisional"]
    print(f"{SCENARIO_PATH.relative_to(ROOT).as_posix()}: {len(body) / 1024:.1f} KB")
    unjudged = json.loads(body)["unjudged_wordings"]
    if unjudged:
        print(f"{len(unjudged)} wordings are left out until they are judged")
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
