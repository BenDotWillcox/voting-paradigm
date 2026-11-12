#!/usr/bin/env python3
"""Build the curated scenario for the liquid democracy demo.

Writes delegation/data/scenario_v2.json from the router evaluation's
recorded answers (eval/benchmarks/delegation_router_v1/):

- the category pool, with each category's id and text
- which pool categories sit inside which, derived from the recorded
  containment judgments at the evaluation's nesting threshold
- a timeline of ballot papers that uses every labelled question once:
  eight papers that have closed, which give everyone a voting history, and
  four that are still open
- the account the viewer starts with: eight delegations from broad to
  narrow, and which closed questions they missed or voted on themself
- the recorded yes/no judgment for every question against every pool
  category

Nothing is judged here and no network is used: every number is copied from
an answer that is already recorded. The evaluation's labels (which
categories a question is "about") are deliberately left out, because the
demo routes on judgments alone.

Deterministic: the same recorded answers give a byte-identical file.

Usage:
    python scripts/build_delegation_scenario.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from delegation import (  # noqa: E402
    DEFAULT_THRESHOLD,
    JudgmentStore,
    NestingStore,
    gather_judgments,
    gather_nesting,
)
from delegation.jev import JEV_MODEL  # noqa: E402
from delegation.scenario import SCENARIO_PATH, SCENARIO_SCHEMA  # noqa: E402
from delegation.simulate import CITY, district_id  # noqa: E402
from eval.delegation_router import (  # noqa: E402
    RouterEvalConfig,
    load_fixture,
    ordered_pairs,
)

BENCHMARK = ROOT / "eval" / "benchmarks" / "delegation_router_v1"

# The papers, oldest first. closes_in_days counts from today: negative is a
# closed paper, positive an open one. Questions are named by their id in the
# evaluation fixture, and each is used once.
BALLOT_PAPERS: tuple[dict[str, Any], ...] = (
    {
        "id": "city-general-1",
        "title": "City general ballot",
        "jurisdiction": CITY,
        "closes_in_days": -330,
        "questions": (
            "q05",
            "q07",
            "q14",
            "q23",
            "q30",
            "q37",
            "q43",
            "q46",
            "q54",
            "q59",
        ),
    },
    {
        "id": "district-1-special-1",
        "title": "District 1 special ballot",
        "jurisdiction": district_id(1),
        "closes_in_days": -290,
        "questions": ("q29", "q36", "q61"),
    },
    {
        "id": "district-3-special-1",
        "title": "District 3 special ballot",
        "jurisdiction": district_id(3),
        "closes_in_days": -250,
        "questions": ("q18", "q22", "q65"),
    },
    {
        "id": "city-budget",
        "title": "City budget and revenue ballot",
        "jurisdiction": CITY,
        "closes_in_days": -200,
        "questions": ("q02", "q04", "q06", "q08", "q09", "q25", "q56"),
    },
    {
        "id": "district-2-special-1",
        "title": "District 2 special ballot",
        "jurisdiction": district_id(2),
        "closes_in_days": -160,
        "questions": ("q28", "q41", "q42", "q64"),
    },
    {
        "id": "city-general-2",
        "title": "City general ballot",
        "jurisdiction": CITY,
        "closes_in_days": -110,
        "questions": (
            "q11",
            "q15",
            "q17",
            "q20",
            "q24",
            "q27",
            "q31",
            "q35",
            "q40",
            "q44",
            "q47",
            "q50",
            "q55",
        ),
    },
    {
        "id": "district-1-special-2",
        "title": "District 1 special ballot",
        "jurisdiction": district_id(1),
        "closes_in_days": -60,
        "questions": ("q13", "q38"),
    },
    {
        "id": "city-advisory-1",
        "title": "City advisory ballot",
        "jurisdiction": CITY,
        "closes_in_days": -25,
        "questions": ("q49", "q51", "q53", "q63", "q67"),
    },
    {
        "id": "district-2-special-2",
        "title": "District 2 special ballot",
        "jurisdiction": district_id(2),
        "closes_in_days": 3,
        "questions": ("q34", "q57", "q60"),
    },
    {
        "id": "city-general-3",
        "title": "City general ballot",
        "jurisdiction": CITY,
        "closes_in_days": 6,
        "questions": (
            "q01",
            "q03",
            "q10",
            "q12",
            "q16",
            "q19",
            "q21",
            "q26",
            "q32",
            "q33",
            "q39",
            "q45",
            "q48",
            "q52",
        ),
    },
    {
        "id": "district-1-special-3",
        "title": "District 1 special ballot",
        "jurisdiction": district_id(1),
        "closes_in_days": 9,
        "questions": ("q58", "q62"),
    },
    {
        "id": "city-advisory-2",
        "title": "City advisory ballot",
        "jurisdiction": CITY,
        "closes_in_days": 16,
        "questions": ("q66", "q68"),
    },
)

# The account the viewer starts with. Four broad categories and four narrow
# ones, two of which sit inside a broad one the viewer also holds. Each
# delegate is a person in the seeded network: mostly someone well known for
# the category, one neighbour, and one person who lives outside the city.
VIEWER: dict[str, Any] = {
    "delegations": (
        ("public schools and education", "d1-078"),
        ("all things taxes", "out-16"),
        ("sales tax rates", "d2-007"),
        ("the environment and conservation", "d3-011"),
        ("the well-being of tree frogs in the Amazon", "d2-054"),
        ("housing and land use", "d2-016"),
        ("bike lanes and cycling safety", "d1-006"),
        ("ranked choice voting", "d2-057"),
    ),
    # Where the viewer sits in the spatial model, for their past votes only
    "position": 0.15,
    # Closed questions the viewer held and let lapse, and ones they voted on
    # themself although a delegation covered them
    "missed": ("q59", "q67"),
    "voted_directly": ("q25", "q30"),
}


def build() -> dict[str, Any]:
    """The scenario, from the evaluation's fixture and recorded answers."""
    fixture = load_fixture()
    config = RouterEvalConfig()
    categories = [entry.category for entry in fixture.categories]

    chosen = [
        fixture.labelled(question_id).question
        for paper in BALLOT_PAPERS
        for question_id in paper["questions"]
    ]
    judged = gather_judgments(
        chosen,
        categories,
        JudgmentStore(BENCHMARK / "judgments.jsonl"),
        model=JEV_MODEL,
    )
    if judged.missing:
        raise SystemExit(
            f"{len(judged.missing)} judgments are not recorded; run collect"
        )
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
            "benchmark": BENCHMARK.relative_to(ROOT).as_posix(),
            "judgments_sha256": _sha256(BENCHMARK / "judgments.jsonl"),
            "nesting_sha256": _sha256(BENCHMARK / "nesting.jsonl"),
        },
        "categories": [
            {"id": category.id, "text": category.text} for category in categories
        ],
        "nesting": sorted([narrow, broad] for narrow, broad in nested.nesting),
        "viewer": {
            "delegations": [
                {"category": category, "delegate": delegate}
                for category, delegate in VIEWER["delegations"]
            ],
            "position": VIEWER["position"],
            "missed": sorted(VIEWER["missed"]),
            "voted_directly": sorted(VIEWER["voted_directly"]),
        },
        "ballot_papers": [
            {
                "id": paper["id"],
                "title": paper["title"],
                "jurisdiction": paper["jurisdiction"],
                "closes_in_days": paper["closes_in_days"],
                "questions": [
                    {
                        "id": question.id,
                        "title": question.title,
                        "summary": question.summary,
                    }
                    for question in (
                        fixture.labelled(question_id).question
                        for question_id in paper["questions"]
                    )
                ],
            }
            for paper in BALLOT_PAPERS
        ],
        "judgments": {
            question.id: {
                category.id: judged.judgments[(question.id, category.id)]
                for category in categories
            }
            for question in chosen
        },
    }


def scenario_bytes() -> bytes:
    return (json.dumps(build(), indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    body = scenario_bytes()
    SCENARIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_PATH.write_bytes(body)
    print(f"{SCENARIO_PATH.relative_to(ROOT).as_posix()}: {len(body) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
