#!/usr/bin/env python3
"""Build the curated scenario for the liquid democracy demo.

Writes delegation/data/scenario_v1.json from the router evaluation's
recorded answers (eval/benchmarks/delegation_router_v1/):

- the category pool, with each category's id and text
- which pool categories sit inside which, derived from the recorded
  containment judgments at the evaluation's nesting threshold
- two ballot papers drawn from the evaluation's labelled questions: a
  city-wide general ballot and a special ballot for one district
- the recorded yes/no judgment for every question on those papers against
  every pool category

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

# The questions on each paper, by their id in the evaluation fixture
BALLOT_PAPERS: tuple[dict[str, Any], ...] = (
    {
        "id": "city-general",
        "title": "City general ballot",
        "jurisdiction": CITY,
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
            "q66",
        ),
    },
    {
        "id": "district-2-special",
        "title": "District 2 special ballot",
        "jurisdiction": district_id(2),
        "questions": ("q28", "q34", "q41", "q57", "q64"),
    },
)


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
        "ballot_papers": [
            {
                "id": paper["id"],
                "title": paper["title"],
                "jurisdiction": paper["jurisdiction"],
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
