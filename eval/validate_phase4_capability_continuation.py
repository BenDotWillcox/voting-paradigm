"""Validate the tracked capability continuation against private attempts."""

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
)
from .phase4_capability_continuation import (
    TogetherCapabilityContinuationPlan,
    capability_continuation_summary,
    load_capability_source_attempts,
    validate_capability_continuation_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a zero-spend capability continuation plan."
    )
    parser.add_argument("continuation", type=Path)
    parser.add_argument("historical_plan", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("historical_suite", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("historical_readiness", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument(
        "--attempt",
        action="append",
        nargs=2,
        metavar=("AUTHORIZATION", "STATE"),
        required=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        continuation = TogetherCapabilityContinuationPlan.model_validate_json(
            args.continuation.read_text(encoding="utf-8")
        )
        historical_plan = TogetherCapabilityPlan.model_validate_json(
            args.historical_plan.read_text(encoding="utf-8")
        )
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        attempts = load_capability_source_attempts(
            [
                (Path(authorization), Path(state))
                for authorization, state in args.attempt
            ]
        )
        historical_suite = load_together_suite(args.historical_suite)
        corrected_suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        historical_readiness = load_readiness_bundle(args.historical_readiness)
        corrected_readiness = load_readiness_bundle(args.corrected_readiness)
        validate_capability_continuation_plan(
            continuation,
            historical_plan,
            corrected_plan,
            attempts,
            historical_suite,
            corrected_suite,
            profile,
            historical_readiness,
            corrected_readiness,
            load_fixture(args.development_fixture),
            load_session_script(args.development_session),
            load_authored_semantic_map(args.development_semantic_map),
        )
        print(
            json.dumps(
                capability_continuation_summary(continuation),
                indent=2,
                sort_keys=True,
            )
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
