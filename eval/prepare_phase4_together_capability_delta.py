"""Build the zero-spend capability delta plan."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_adjudication import (
    TogetherAdjudicatedCandidateCapabilityAuthorization,
    load_capability_adjudication_policy,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
)
from .phase4_capability_recovery import (
    build_capability_delta_plan,
    build_capability_delta_source_proof,
    capability_delta_summary,
    validate_capability_delta_plan,
)
from .phase4_provider import ProviderStructuredOutputDiagnostic
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


DELTA_CREATED_AT = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind all three harness-inconclusive attempts and build the "
            "zero-spend candidate role-delta plan."
        )
    )
    parser.add_argument("source_adjudication", type=Path)
    parser.add_argument("source_continuation", type=Path)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("source_suite", type=Path)
    parser.add_argument("source_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("provisional_authorization", type=Path)
    parser.add_argument("provisional_state", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("source_proof_output", type=Path)
    parser.add_argument(
        "--harness-attempt",
        action="append",
        nargs=3,
        metavar=("AUTHORIZATION", "STATE", "DIAGNOSTIC"),
        required=True,
    )
    return parser


def load_delta_authoring_inputs(args):
    policy = load_capability_adjudication_policy(args.source_adjudication)
    continuation = TogetherCapabilityContinuationPlan.model_validate_json(
        args.source_continuation.read_text(encoding="utf-8")
    )
    source_plan = TogetherCapabilityPlan.model_validate_json(
        args.source_plan.read_text(encoding="utf-8")
    )
    source_suite = load_together_suite(args.source_suite)
    source_readiness = load_readiness_bundle(args.source_readiness)
    profile = load_phase4_robustness_profile(args.profile)
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
    attempts = [(provisional_authorization, provisional_state, None)]
    for authorization_path, state_path, diagnostic_path in args.harness_attempt:
        attempts.append(
            (
                TogetherAdjudicatedCandidateCapabilityAuthorization.model_validate_json(
                    Path(authorization_path).read_text(encoding="utf-8")
                ),
                TogetherCandidateCapabilityExecutionState.model_validate_json(
                    Path(state_path).read_text(encoding="utf-8")
                ),
                ProviderStructuredOutputDiagnostic.model_validate_json(
                    Path(diagnostic_path).read_text(encoding="utf-8")
                ),
            )
        )
    corrected_plan = TogetherCapabilityPlan.model_validate_json(
        args.corrected_plan.read_text(encoding="utf-8")
    )
    corrected_suite = load_together_suite(args.corrected_suite)
    corrected_readiness = load_readiness_bundle(args.corrected_readiness)
    fixture = load_fixture(args.development_fixture)
    session = load_session_script(args.development_session)
    semantic_map = load_authored_semantic_map(args.development_semantic_map)
    return (
        policy,
        continuation,
        source_plan,
        source_suite,
        profile,
        attempts,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        source_readiness,
        PROVIDER_RESPONSE_INVARIANT_MANIFEST,
        fixture,
        session,
        semantic_map,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = load_delta_authoring_inputs(args)
        delta = build_capability_delta_plan(
            *inputs,
            plan_id="phase4_together_capability_delta_v1",
            plan_version=1,
            created_at=DELTA_CREATED_AT,
        )
        validate_capability_delta_plan(delta, *inputs)
        source_proof = build_capability_delta_source_proof(
            delta,
            *inputs,
            proof_id="phase4_together_capability_delta_source_proof_v1",
            proof_version=1,
            validated_at=DELTA_CREATED_AT,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{delta.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        args.source_proof_output.parent.mkdir(parents=True, exist_ok=True)
        args.source_proof_output.write_text(
            f"{source_proof.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        summary = capability_delta_summary(delta)
        summary["source_proof_sha256"] = content_sha256(source_proof)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
