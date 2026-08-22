"""Create a private authorization for one candidate capability plan.

This command makes no network or provider call.  The output stays ignored and
is consumed only by the separate paid candidate runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_capability import (
    TogetherCapabilityPlan,
)
from .phase4_capability_adjudication import (
    build_adjudicated_candidate_authorization,
    load_capability_adjudication_policy,
    validate_capability_adjudication_policy,
)
from .phase4_capability_continuation import (
    CANDIDATE_CAPABILITY_CALL_COUNT,
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
    build_candidate_capability_authorization_bundle,
    candidate_plan_for,
    load_capability_source_attempts,
    validate_capability_continuation_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .prequential import load_session_script


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()


def _private_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("candidate authorization must stay under private_runs")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private authorization for one five-call candidate "
            "capability plan. This command spends nothing."
        )
    )
    parser.add_argument("continuation", type=Path)
    parser.add_argument("adjudication_policy", type=Path)
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
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("provisional_authorization", type=Path)
    parser.add_argument("provisional_state", type=Path)
    parser.add_argument("candidate_id")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--attempt",
        action="append",
        nargs=2,
        metavar=("AUTHORIZATION", "STATE"),
        required=True,
    )
    parser.add_argument("--approve-call-count", type=int, required=True)
    parser.add_argument("--approve-max-spend-microusd", type=int, required=True)
    parser.add_argument("--confirm-public-development-only", action="store_true")
    parser.add_argument("--confirm-no-participant-content", action="store_true")
    parser.add_argument("--valid-minutes", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = _private_output(args.output)
        continuation = TogetherCapabilityContinuationPlan.model_validate_json(
            args.continuation.read_text(encoding="utf-8")
        )
        adjudication_policy = load_capability_adjudication_policy(
            args.adjudication_policy
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
        suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        historical_readiness = load_readiness_bundle(args.historical_readiness)
        readiness = load_readiness_bundle(args.corrected_readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        provisional_authorization = (
            TogetherCandidateCapabilityAuthorizationBundle.model_validate_json(
                args.provisional_authorization.read_text(encoding="utf-8")
            )
        )
        provisional_state = (
            TogetherCandidateCapabilityExecutionState.model_validate_json(
                args.provisional_state.read_text(encoding="utf-8")
            )
        )
        validate_capability_continuation_plan(
            continuation,
            historical_plan,
            corrected_plan,
            attempts,
            historical_suite,
            suite,
            profile,
            historical_readiness,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        validate_capability_adjudication_policy(
            adjudication_policy,
            continuation,
            corrected_plan,
            suite,
            profile,
            provisional_authorization,
            provisional_state,
        )
        if args.candidate_id not in adjudication_policy.remaining_candidate_ids:
            raise ValueError("candidate is outside adjudication continuation")
        candidate_plan = candidate_plan_for(continuation, args.candidate_id)
        if (
            args.approve_call_count != CANDIDATE_CAPABILITY_CALL_COUNT
            or args.approve_max_spend_microusd
            != candidate_plan.candidate_capability_max_spend_microusd
            or not args.confirm_public_development_only
            or not args.confirm_no_participant_content
            or not 1 <= args.valid_minutes <= 240
        ):
            raise ValueError("candidate capability manual approval is incomplete")
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight_bundle.read_text(encoding="utf-8")
        )
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        candidate_bundle = build_candidate_capability_authorization_bundle(
            continuation,
            candidate_plan,
            suite,
            profile,
            readiness,
            catalog,
            bundle_id=f"candidate_capability_authorization_{timestamp}",
            approval_id=f"candidate_capability_approval_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=args.valid_minutes),
        )
        bundle = build_adjudicated_candidate_authorization(
            adjudication_policy,
            candidate_bundle,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            f"{bundle.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "schema_version": bundle.schema_version,
                    "bundle_sha256": content_sha256(bundle),
                    "approved_call_count": CANDIDATE_CAPABILITY_CALL_COUNT,
                    "approved_max_spend_microusd": (
                        candidate_plan.candidate_capability_max_spend_microusd
                    ),
                    "provider_inference_calls_executed": 0,
                    "provider_spend_microusd": 0,
                },
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
