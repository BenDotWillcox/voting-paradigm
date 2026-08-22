"""Validate the capability adjudication policy against its private state."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_adjudication import (
    capability_adjudication_summary,
    load_capability_adjudication_policy,
    validate_capability_adjudication_policy,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_together import load_together_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the zero-spend capability adjudication policy."
    )
    parser.add_argument("policy", type=Path)
    parser.add_argument("continuation", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("provisional_authorization", type=Path)
    parser.add_argument("provisional_state", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = load_capability_adjudication_policy(args.policy)
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
        validate_capability_adjudication_policy(
            policy,
            continuation,
            corrected_plan,
            suite,
            profile,
            authorization,
            state,
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
