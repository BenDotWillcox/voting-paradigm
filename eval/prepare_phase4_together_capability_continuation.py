"""Build the zero-spend candidate-isolated capability continuation plan."""

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
    TogetherCapabilityPlan,
)
from .phase4_capability_continuation import (
    build_capability_continuation_plan,
    capability_continuation_summary,
    load_capability_source_attempts,
    validate_capability_continuation_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


CONTINUATION_CREATED_AT = datetime(2026, 8, 21, 23, 30, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind historical capability attempts and build corrected, "
            "independent plans for every non-rejected candidate. This "
            "command spends nothing."
        )
    )
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
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--attempt",
        action="append",
        nargs=2,
        metavar=("AUTHORIZATION", "STATE"),
        required=True,
        help="Preserved private authorization/state pair in attempt order.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        historical_plan = TogetherCapabilityPlan.model_validate_json(
            args.historical_plan.read_text(encoding="utf-8")
        )
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        historical_suite = load_together_suite(args.historical_suite)
        corrected_suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        historical_readiness = load_readiness_bundle(args.historical_readiness)
        corrected_readiness = load_readiness_bundle(args.corrected_readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        attempts = load_capability_source_attempts(
            [
                (Path(authorization), Path(state))
                for authorization, state in args.attempt
            ]
        )
        continuation = build_capability_continuation_plan(
            historical_plan,
            corrected_plan,
            attempts,
            historical_suite,
            profile,
            continuation_id="phase4_together_capability_continuation_v2",
            continuation_version=2,
            created_at=CONTINUATION_CREATED_AT,
        )
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
            fixture,
            session,
            semantic_map,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{continuation.model_dump_json(indent=2)}\n",
            encoding="utf-8",
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
