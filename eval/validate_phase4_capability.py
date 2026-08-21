"""Validate the tracked zero-spend Together capability-preflight plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_capability import (
    TogetherCapabilityPlan,
    capability_plan_summary,
    validate_capability_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the exact zero-spend Together capability plan."
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = TogetherCapabilityPlan.model_validate_json(
            args.plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
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
        print(json.dumps(capability_plan_summary(plan), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
