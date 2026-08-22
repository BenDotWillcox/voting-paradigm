"""Build the zero-spend capability schema-failure adjudication policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_adjudication import (
    build_capability_adjudication_policy,
    capability_adjudication_summary,
    validate_capability_adjudication_policy,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_together import load_together_suite


POLICY_CREATED_AT = datetime(2026, 8, 22, 2, 0, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Predeclare the zero-spend disposition of repeated exact-schema "
            "capability failures."
        )
    )
    parser.add_argument("continuation", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("provisional_authorization", type=Path)
    parser.add_argument("provisional_state", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        continuation = TogetherCapabilityContinuationPlan.model_validate_json(
            args.continuation.read_text(encoding="utf-8")
        )
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        authorization = (
            TogetherCandidateCapabilityAuthorizationBundle.model_validate_json(
                args.provisional_authorization.read_text(encoding="utf-8")
            )
        )
        state = TogetherCandidateCapabilityExecutionState.model_validate_json(
            args.provisional_state.read_text(encoding="utf-8")
        )
        policy = build_capability_adjudication_policy(
            continuation,
            corrected_plan,
            suite,
            profile,
            authorization,
            state,
            policy_id="phase4_together_capability_adjudication_v1",
            policy_version=1,
            created_at=POLICY_CREATED_AT,
        )
        validate_capability_adjudication_policy(
            policy,
            continuation,
            corrected_plan,
            suite,
            profile,
            authorization,
            state,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{policy.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                capability_adjudication_summary(policy),
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
