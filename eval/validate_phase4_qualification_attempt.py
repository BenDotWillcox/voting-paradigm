"""Validate the public, zero-spend Phase 4 qualification-attempt-v2 chain.

This command can validate the tracked request contracts, readiness artifacts,
aggregate source proof, and exact 304-coordinate plan.  It deliberately cannot
rebuild the source proof from the ignored v1 provider states and result; that
private-source audit remains the responsibility of the preparation command.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_provider import (
    PROVIDER_RESPONSE_JSON_DECODER_POLICY,
    provider_response_json_decoder_implementation_sha256,
)
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3,
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3,
    provider_response_readout_validator_implementation_sha256,
)
from .phase4_qualification_attempt import (
    QualificationAttemptV2SourceProof,
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
    validate_qualification_attempt_v2_plan,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    load_readiness_bundle,
    validate_readiness_bundle,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import (
    Phase4TogetherSuite,
    build_default_together_suite,
    build_together_suite_v5,
    load_together_suite,
    validate_together_suite,
)
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the tracked qualification-attempt-v2 chain without "
            "reading ignored provider state or authorizing spend."
        )
    )
    parser.add_argument("source_suite", type=Path)
    parser.add_argument("source_readiness", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("execution_plan", type=Path)
    parser.add_argument("robustness_profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    return parser


def _require_public_paths(paths: Sequence[Path]) -> None:
    for path in paths:
        if any(part.casefold() == "private_runs" for part in path.resolve().parts):
            raise ValueError(
                "qualification-attempt public validation cannot read private runs"
            )


def _validate_public_source_proof_bindings(
    proof: QualificationAttemptV2SourceProof,
    source_suite: Phase4TogetherSuite,
    source_readiness: Phase4TogetherReadinessBundle,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
) -> None:
    expected = (
        content_sha256(source_suite),
        content_sha256(source_readiness),
        content_sha256(corrected_suite),
        content_sha256(corrected_readiness),
        content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3),
        content_sha256(PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3),
        provider_response_readout_validator_implementation_sha256(),
        content_sha256(PROVIDER_RESPONSE_JSON_DECODER_POLICY),
        provider_response_json_decoder_implementation_sha256(),
    )
    actual = (
        proof.source_together_suite_sha256,
        proof.source_readiness_sha256,
        proof.corrected_together_suite_sha256,
        proof.corrected_readiness_sha256,
        proof.response_invariant_manifest_sha256,
        proof.response_behavior_spec_sha256,
        proof.readout_validator_implementation_sha256,
        proof.json_decoder_policy_sha256,
        proof.json_decoder_implementation_sha256,
    )
    if actual != expected:
        raise ValueError("qualification-attempt public proof bindings differ")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = (
        args.source_suite,
        args.source_readiness,
        args.corrected_suite,
        args.corrected_readiness,
        args.source_proof,
        args.execution_plan,
        args.robustness_profile,
        args.development_fixture,
        args.development_session,
        args.development_semantic_map,
    )
    try:
        _require_public_paths(paths)
        profile = load_phase4_robustness_profile(args.robustness_profile)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        source_suite = load_together_suite(args.source_suite)
        source_readiness = load_readiness_bundle(args.source_readiness)
        corrected_suite = load_together_suite(args.corrected_suite)
        corrected_readiness = load_readiness_bundle(args.corrected_readiness)
        proof = load_qualification_attempt_v2_source_proof(args.source_proof)
        plan = load_qualification_attempt_v2_plan(args.execution_plan)

        if source_suite != build_together_suite_v5(profile):
            raise ValueError("qualification-attempt source suite differs")
        if corrected_suite != build_default_together_suite(profile):
            raise ValueError("qualification-attempt corrected suite differs")
        validate_together_suite(source_suite, profile)
        validate_together_suite(corrected_suite, profile)
        validate_readiness_bundle(
            source_readiness,
            source_suite,
            profile,
            fixture,
            session,
            semantic_map,
        )
        validate_readiness_bundle(
            corrected_readiness,
            corrected_suite,
            profile,
            fixture,
            session,
            semantic_map,
        )
        _validate_public_source_proof_bindings(
            proof,
            source_suite,
            source_readiness,
            corrected_suite,
            corrected_readiness,
        )
        validate_qualification_attempt_v2_plan(
            plan,
            proof,
            corrected_suite,
            corrected_readiness,
        )
        print(
            json.dumps(
                {
                    "source_suite_sha256": content_sha256(source_suite),
                    "source_readiness_sha256": content_sha256(source_readiness),
                    "corrected_suite_sha256": content_sha256(corrected_suite),
                    "corrected_readiness_sha256": content_sha256(
                        corrected_readiness
                    ),
                    "source_proof_sha256": content_sha256(proof),
                    "execution_plan_sha256": content_sha256(plan),
                    "candidate_count": len(plan.candidate_plans),
                    "scoped_coordinate_count": plan.scoped_coordinate_count,
                    "carried_success_count": plan.carried_success_count,
                    "provider_call_count": plan.provider_call_count,
                    "conformance_stage_call_count": (
                        plan.conformance_stage_call_count
                    ),
                    "new_projected_cost_microusd": (
                        plan.new_projected_cost_microusd
                    ),
                    "new_authorized_max_cost_microusd": (
                        plan.new_authorized_max_cost_microusd
                    ),
                    "prior_actual_spend_microusd": (
                        plan.prior_actual_spend_microusd
                    ),
                    "cumulative_authorized_worst_case_microusd": (
                        plan.cumulative_authorized_worst_case_microusd
                    ),
                    "sequential_projected_headroom_microusd": (
                        plan.sequential_projected_headroom_microusd
                    ),
                    "private_source_proof_rebuild_performed": False,
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
