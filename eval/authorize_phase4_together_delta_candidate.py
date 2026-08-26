"""Authorize one candidate's exact reviewed capability-delta subset."""

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
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    build_delta_candidate_authorization_bundle,
    delta_candidate_plan_for,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
    validate_capability_delta_execution_inputs,
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
        raise ValueError("delta authorization must stay under private_runs")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private authorization for one reviewed role-delta "
            "subset. This command spends nothing."
        )
    )
    parser.add_argument("delta", type=Path)
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("candidate_id")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--prior-authorization",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument(
        "--prior-state",
        action="append",
        default=[],
        type=Path,
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
        delta = load_capability_delta_plan(args.delta)
        source_proof = load_capability_delta_source_proof(args.source_proof)
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.corrected_readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(args.development_semantic_map)
        validate_capability_delta_execution_inputs(
            delta,
            source_proof,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        candidate_plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            args.candidate_id,
        )
        if (
            args.approve_call_count != len(candidate_plan.calls)
            or args.approve_max_spend_microusd
            != candidate_plan.candidate_capability_max_spend_microusd
            or not args.confirm_public_development_only
            or not args.confirm_no_participant_content
            or not 1 <= args.valid_minutes <= 240
        ):
            raise ValueError("delta capability manual approval is incomplete")
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight_bundle.read_text(encoding="utf-8")
        )
        if len(args.prior_authorization) != len(args.prior_state):
            raise ValueError("prior delta authorization/state counts differ")
        prior_attempts = [
            (
                TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                    authorization_path.read_text(encoding="utf-8")
                ),
                TogetherDeltaCandidateExecutionState.model_validate_json(
                    state_path.read_text(encoding="utf-8")
                ),
            )
            for authorization_path, state_path in zip(
                args.prior_authorization,
                args.prior_state,
                strict=True,
            )
        ]
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        bundle = build_delta_candidate_authorization_bundle(
            delta,
            source_proof,
            candidate_plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog,
            prior_attempts=prior_attempts,
            bundle_id=f"delta_candidate_authorization_{timestamp}",
            approval_id=f"delta_candidate_approval_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=args.valid_minutes),
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
                    "approved_call_count": len(candidate_plan.calls),
                    "approved_max_spend_microusd": (
                        candidate_plan.candidate_capability_max_spend_microusd
                    ),
                    "prior_candidate_count": len(
                        bundle.prior_candidate_progress
                    ),
                    "cumulative_worst_case_spend_microusd": (
                        bundle.cumulative_worst_case_spend_microusd
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
