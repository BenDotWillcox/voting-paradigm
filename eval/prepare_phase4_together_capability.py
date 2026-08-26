"""Build the tracked zero-spend Together capability-preflight plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_capability import (
    build_capability_plan,
    capability_plan_summary,
    validate_capability_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


CAPABILITY_PLAN_V1_CREATED_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
CAPABILITY_PLAN_V2_CREATED_AT = datetime(2026, 8, 21, 23, 0, tzinfo=UTC)
CAPABILITY_PLAN_V3_CREATED_AT = datetime(2026, 8, 22, 5, 10, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the exact zero-spend 15-call Together capability plan."
        )
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        if suite.suite_version >= 4:
            plan_version = 3
            created_at = CAPABILITY_PLAN_V3_CREATED_AT
        elif suite.suite_version >= 3:
            plan_version = 2
            created_at = CAPABILITY_PLAN_V2_CREATED_AT
        else:
            plan_version = 1
            created_at = CAPABILITY_PLAN_V1_CREATED_AT
        plan = build_capability_plan(
            suite,
            profile,
            readiness,
            plan_id=f"phase4_together_capability_plan_v{plan_version}",
            plan_version=plan_version,
            created_at=created_at,
        )
        validate_capability_plan(
            plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{plan.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(json.dumps(capability_plan_summary(plan), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
