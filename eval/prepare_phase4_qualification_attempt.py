"""Prepare the reviewed second qualification attempt without provider spend.

This command validates the completed-v1 result, candidate states, and every
carry/new-observation binding, then binds that evidence to the versioned v5/v6
request contracts. It emits a tracked content-free source proof and execution
plan. No v1 output is carried into v2. The command never loads a credential,
constructs an HTTP client, authorizes a call, or executes inference.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .contracts import ContractModel, EvaluationFixture
from .fixture_io import content_sha256, load_fixture
from .phase4_qualification_attempt import (
    QualificationAttemptV2Plan,
    QualificationAttemptV2SourceProof,
    build_qualification_attempt_v2_plan,
    build_qualification_attempt_v2_source_proof,
    validate_qualification_attempt_v2_plan,
    validate_qualification_attempt_v2_source_proof,
)
from .phase4_qualification_execution import (
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentQualificationExecutionPlan,
    load_two_deployment_carry_bundle,
    load_two_deployment_qualification_plan,
)
from .phase4_qualification_runtime import (
    TwoDeploymentCandidateExecutionState,
    TwoDeploymentQualificationAuthorizationBundle,
)
from .phase4_qualification_scope import (
    TwoDeploymentQualificationScopeAmendment,
    load_two_deployment_qualification_scope,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    load_readiness_bundle,
    validate_readiness_bundle,
)
from .phase4_robustness import (
    Phase4ERobustnessProfile,
    load_phase4_robustness_profile,
)
from .phase4_semantic import (
    AuthoredSemanticMapBundle,
    load_authored_semantic_map,
)
from .phase4_together import (
    Phase4TogetherSuite,
    build_default_together_suite,
    build_together_suite_v5,
    load_together_suite,
    validate_together_suite,
)
from .phase4_two_deployment_result import (
    TwoDeploymentQualificationAggregateReceipt,
    TwoDeploymentQualificationResult,
    load_two_deployment_qualification_aggregate_receipt,
    load_two_deployment_qualification_result,
)
from .prequential import PrequentialSessionScript, load_session_script


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_RUNS_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()
TRACKED_FIXTURES_ROOT = (REPOSITORY_ROOT / "eval" / "fixtures").resolve()

SOURCE_PROOF_ID = "phase4_two_deployment_qualification_attempt_source_proof_v2"
EXECUTION_PLAN_ID = "phase4_two_deployment_qualification_attempt_v2"
SOURCE_PROOF_VALIDATED_AT = datetime(2026, 8, 28, 20, 40, tzinfo=UTC)
EXECUTION_PLAN_CREATED_AT = datetime(2026, 8, 28, 20, 41, tzinfo=UTC)

PrivateContract = TypeVar("PrivateContract", bound=ContractModel)


@dataclass(frozen=True, slots=True)
class _PreparationInputs:
    prior_plan: TwoDeploymentQualificationExecutionPlan
    prior_carry: TwoDeploymentQualificationCarryBundle
    prior_authorization: TwoDeploymentQualificationAuthorizationBundle
    prior_result: TwoDeploymentQualificationResult
    prior_receipt: TwoDeploymentQualificationAggregateReceipt
    prior_scope: TwoDeploymentQualificationScopeAmendment
    prior_states: list[TwoDeploymentCandidateExecutionState]
    source_suite: Phase4TogetherSuite
    source_readiness: Phase4TogetherReadinessBundle
    corrected_suite: Phase4TogetherSuite
    corrected_readiness: Phase4TogetherReadinessBundle
    profile: Phase4ERobustnessProfile
    fixture: EvaluationFixture
    session: PrequentialSessionScript
    semantic_map: AuthoredSemanticMapBundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the tracked qualification-attempt-v2 source proof and plan "
            "without provider calls, carry-forward, or spend."
        )
    )
    parser.add_argument("prior_execution_plan", type=Path)
    parser.add_argument("prior_carry_bundle", type=Path)
    parser.add_argument("prior_authorization_bundle", type=Path)
    parser.add_argument("prior_private_result", type=Path)
    parser.add_argument("prior_safe_receipt", type=Path)
    parser.add_argument("prior_scope", type=Path)
    parser.add_argument("source_suite", type=Path)
    parser.add_argument("source_readiness", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("source_proof_output", type=Path)
    parser.add_argument("plan_output", type=Path)
    parser.add_argument(
        "--prior-candidate-state",
        action="append",
        type=Path,
        required=True,
        help="Repeat for the exact two private candidate states from attempt v1.",
    )
    return parser


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _public_input_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return tuple(
        getattr(args, name).resolve()
        for name in (
            "prior_execution_plan",
            "prior_safe_receipt",
            "prior_scope",
            "source_suite",
            "source_readiness",
            "corrected_suite",
            "corrected_readiness",
            "profile",
            "development_fixture",
            "development_session",
            "development_semantic_map",
        )
    )


def _private_input_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.prior_carry_bundle.resolve(),
        args.prior_authorization_bundle.resolve(),
        args.prior_private_result.resolve(),
        *(path.resolve() for path in args.prior_candidate_state),
    )


def _require_safe_paths(args: argparse.Namespace) -> None:
    private_root = PRIVATE_RUNS_ROOT.resolve()
    tracked_root = TRACKED_FIXTURES_ROOT.resolve()
    public_inputs = _public_input_paths(args)
    private_inputs = _private_input_paths(args)
    if len(args.prior_candidate_state) != 2:
        raise ValueError("qualification attempt v2 requires two prior states")
    if any(_is_within(path, private_root) for path in public_inputs):
        raise ValueError("qualification attempt public input is private")
    if any(not _is_within(path, private_root) for path in private_inputs):
        raise ValueError("qualification attempt private input left private_runs")

    source_proof = args.source_proof_output.resolve()
    plan = args.plan_output.resolve()
    if source_proof.parent != tracked_root or plan.parent != tracked_root:
        raise ValueError("qualification tracked outputs must stay in fixtures")
    outputs = {source_proof, plan}
    if len(outputs) != 2:
        raise ValueError("qualification attempt outputs must be distinct")
    if outputs.intersection({*public_inputs, *private_inputs}):
        raise ValueError("qualification attempt output would overwrite an input")


def _load_private_contract(
    path: Path,
    model_type: type[PrivateContract],
) -> PrivateContract:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def _load_inputs(args: argparse.Namespace) -> _PreparationInputs:
    return _PreparationInputs(
        prior_plan=load_two_deployment_qualification_plan(
            args.prior_execution_plan
        ),
        prior_carry=load_two_deployment_carry_bundle(args.prior_carry_bundle),
        prior_authorization=_load_private_contract(
            args.prior_authorization_bundle,
            TwoDeploymentQualificationAuthorizationBundle,
        ),
        prior_result=load_two_deployment_qualification_result(
            args.prior_private_result
        ),
        prior_receipt=load_two_deployment_qualification_aggregate_receipt(
            args.prior_safe_receipt
        ),
        prior_scope=load_two_deployment_qualification_scope(args.prior_scope),
        prior_states=[
            _load_private_contract(path, TwoDeploymentCandidateExecutionState)
            for path in args.prior_candidate_state
        ],
        source_suite=load_together_suite(args.source_suite),
        source_readiness=load_readiness_bundle(args.source_readiness),
        corrected_suite=load_together_suite(args.corrected_suite),
        corrected_readiness=load_readiness_bundle(args.corrected_readiness),
        profile=load_phase4_robustness_profile(args.profile),
        fixture=load_fixture(args.development_fixture),
        session=load_session_script(args.development_session),
        semantic_map=load_authored_semantic_map(args.development_semantic_map),
    )


def _build_artifacts(
    inputs: _PreparationInputs,
) -> tuple[
    QualificationAttemptV2SourceProof,
    QualificationAttemptV2Plan,
]:
    if inputs.source_suite != build_together_suite_v5(inputs.profile) or (
        inputs.corrected_suite != build_default_together_suite(inputs.profile)
    ):
        raise ValueError("qualification attempt suites differ from builders")
    validate_together_suite(inputs.source_suite, inputs.profile)
    validate_together_suite(inputs.corrected_suite, inputs.profile)
    validate_readiness_bundle(
        inputs.source_readiness,
        inputs.source_suite,
        inputs.profile,
        inputs.fixture,
        inputs.session,
        inputs.semantic_map,
    )
    validate_readiness_bundle(
        inputs.corrected_readiness,
        inputs.corrected_suite,
        inputs.profile,
        inputs.fixture,
        inputs.session,
        inputs.semantic_map,
    )
    proof = build_qualification_attempt_v2_source_proof(
        inputs.prior_plan,
        inputs.prior_carry,
        inputs.prior_authorization,
        inputs.prior_result,
        inputs.prior_receipt,
        inputs.prior_states,
        inputs.source_suite,
        inputs.source_readiness,
        inputs.corrected_suite,
        inputs.corrected_readiness,
        inputs.profile,
        inputs.prior_scope,
        inputs.fixture,
        inputs.session,
        proof_id=SOURCE_PROOF_ID,
        validated_at=SOURCE_PROOF_VALIDATED_AT,
    )
    validate_qualification_attempt_v2_source_proof(
        proof,
        inputs.prior_plan,
        inputs.prior_carry,
        inputs.prior_authorization,
        inputs.prior_result,
        inputs.prior_receipt,
        inputs.prior_states,
        inputs.source_suite,
        inputs.source_readiness,
        inputs.corrected_suite,
        inputs.corrected_readiness,
        inputs.profile,
        inputs.prior_scope,
        inputs.fixture,
        inputs.session,
    )
    plan = build_qualification_attempt_v2_plan(
        proof,
        inputs.corrected_suite,
        inputs.corrected_readiness,
        plan_id=EXECUTION_PLAN_ID,
        created_at=EXECUTION_PLAN_CREATED_AT,
    )
    validate_qualification_attempt_v2_plan(
        plan,
        proof,
        inputs.corrected_suite,
        inputs.corrected_readiness,
    )
    return proof, plan


def _atomic_write_contracts(
    outputs: Sequence[tuple[Path, ContractModel]],
) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for output, value in outputs:
            resolved = output.resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=resolved.parent,
                prefix=f".{resolved.name}.",
                suffix=".tmp",
                text=True,
            )
            temporary = Path(temporary_name)
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(f"{value.model_dump_json(indent=2)}\n")
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, resolved))
        for temporary, resolved in staged:
            os.replace(temporary, resolved)
    finally:
        for temporary, _resolved in staged:
            temporary.unlink(missing_ok=True)


def _summary(
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
) -> dict[str, object]:
    return {
        "source_proof_sha256": content_sha256(proof),
        "execution_plan_sha256": content_sha256(plan),
        "candidate_count": len(plan.candidate_plans),
        "scoped_coordinate_count": plan.scoped_coordinate_count,
        "carried_success_count": plan.carried_success_count,
        "provider_call_count": plan.provider_call_count,
        "conformance_stage_call_count": plan.conformance_stage_call_count,
        "new_projected_cost_microusd": plan.new_projected_cost_microusd,
        "new_authorized_max_cost_microusd": (
            plan.new_authorized_max_cost_microusd
        ),
        "prior_actual_spend_microusd": plan.prior_actual_spend_microusd,
        "cumulative_authorized_worst_case_microusd": (
            plan.cumulative_authorized_worst_case_microusd
        ),
        "sequential_projected_headroom_microusd": (
            plan.sequential_projected_headroom_microusd
        ),
        "prior_result_rebuild_passed": proof.prior_result_rebuild_passed,
        "prior_candidate_state_audits_passed": (
            proof.prior_candidate_state_audits_passed
        ),
        "prior_carry_observation_bindings_passed": (
            proof.prior_carry_observation_bindings_passed
        ),
        "prior_new_observation_bindings_passed": (
            proof.prior_new_observation_bindings_passed
        ),
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_safe_paths(args)
        proof, plan = _build_artifacts(_load_inputs(args))
        _atomic_write_contracts(
            (
                (args.source_proof_output, proof),
                (args.plan_output, plan),
            )
        )
        print(json.dumps(_summary(proof, plan), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
