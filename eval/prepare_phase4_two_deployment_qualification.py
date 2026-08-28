"""Build the reviewed two-deployment qualification plan and private carry.

This command performs no provider calls and authorizes no spend.  It derives a
tracked, content-free execution plan from reviewed public artifacts, then
rehydrates the exact ten capability outputs approved for carry-forward into a
Git-ignored private bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_capability_aggregation import load_capability_aggregation
from .phase4_qualification_execution import (
    CapabilitySourceState,
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentQualificationExecutionPlan,
    build_two_deployment_carry_bundle,
    build_two_deployment_qualification_plan,
    load_capability_source_state,
    validate_two_deployment_carry_bundle,
    validate_two_deployment_qualification_plan,
)
from .phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
)
from .validate_phase4_selector_recovery import (
    build_parser as build_public_chain_parser,
    load_selector_recovery_public_inputs,
)


QUALIFICATION_EXECUTION_PLAN_CREATED_AT = datetime(
    2026,
    8,
    28,
    3,
    0,
    tzinfo=UTC,
)
QUALIFICATION_CARRY_CREATED_AT = datetime(
    2026,
    8,
    28,
    3,
    1,
    tzinfo=UTC,
)
QUALIFICATION_EXECUTION_PLAN_ID = (
    "phase4_two_deployment_qualification_execution_v1"
)
QUALIFICATION_CARRY_BUNDLE_ID = (
    "phase4_two_deployment_qualification_carry_v1"
)
PRIVATE_RUNS_ROOT = Path(__file__).resolve().parent / "private_runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the tracked two-deployment qualification plan and the "
            "ignored capability carry bundle without provider calls or spend."
        ),
        parents=[build_public_chain_parser()],
        conflict_handler="resolve",
    )
    parser.add_argument("scope", type=Path)
    parser.add_argument("scope_evidence_proof", type=Path)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("plan_output", type=Path)
    parser.add_argument("carry_output", type=Path)
    parser.add_argument(
        "--source-state",
        action="append",
        type=Path,
        required=True,
        help=(
            "One ignored capability source state. Repeat for every state "
            "referenced by the ten reviewed carry-forward successes."
        ),
    )
    return parser


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _all_input_paths(args: argparse.Namespace) -> set[Path]:
    result: set[Path] = set()
    for name, value in vars(args).items():
        if name in {"plan_output", "carry_output"}:
            continue
        if isinstance(value, Path):
            result.add(value.resolve())
        elif isinstance(value, list):
            result.update(
                item.resolve() for item in value if isinstance(item, Path)
            )
    return result


def _require_safe_output_paths(args: argparse.Namespace) -> None:
    plan_output = args.plan_output.resolve()
    carry_output = args.carry_output.resolve()
    private_root = PRIVATE_RUNS_ROOT.resolve()
    if plan_output == carry_output:
        raise ValueError("qualification outputs must be distinct")
    if _is_within(plan_output, private_root) or any(
        part.casefold() == "private_runs" for part in plan_output.parts
    ):
        raise ValueError("qualification execution plan must remain public")
    if not _is_within(carry_output, private_root):
        raise ValueError("qualification carry must remain under eval/private_runs")
    inputs = _all_input_paths(args)
    if plan_output in inputs or carry_output in inputs:
        raise ValueError("qualification output cannot overwrite an input")


def _load_source_states(paths: Sequence[Path]) -> list[CapabilitySourceState]:
    if not paths:
        raise ValueError("qualification carry needs source states")
    return [load_capability_source_state(path) for path in paths]


def _summary(
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
) -> dict[str, object]:
    return {
        "execution_plan_sha256": content_sha256(plan),
        "carry_bundle_sha256": content_sha256(carry),
        "candidate_count": len(plan.candidate_plans),
        "scoped_entry_count": plan.scoped_entry_count,
        "carried_success_count": plan.carried_success_count,
        "provider_call_count": plan.provider_call_count,
        "new_projected_cost_microusd": plan.new_projected_cost_microusd,
        "new_authorized_max_cost_microusd": (
            plan.new_authorized_max_cost_microusd
        ),
        "private_source_state_count": len(carry.source_state_sha256s),
        "interviewer_tool_result_replay_verified": (
            carry.interviewer_tool_result_replay_verified
        ),
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_safe_output_paths(args)
        public_inputs = load_selector_recovery_public_inputs(args)
        corrected_plan = public_inputs[7]
        suite = public_inputs[8]
        readiness = public_inputs[9]
        profile = public_inputs[10]
        fixture = public_inputs[12]
        session = public_inputs[13]
        semantic_map = public_inputs[14]
        scope = load_two_deployment_qualification_scope(args.scope)
        scope_proof = load_two_deployment_scope_evidence_proof(
            args.scope_evidence_proof
        )
        aggregation = load_capability_aggregation(args.aggregation)
        source_states = _load_source_states(args.source_state)

        plan = build_two_deployment_qualification_plan(
            scope,
            scope_proof,
            readiness,
            plan_id=QUALIFICATION_EXECUTION_PLAN_ID,
            created_at=QUALIFICATION_EXECUTION_PLAN_CREATED_AT,
        )
        carry = build_two_deployment_carry_bundle(
            plan,
            scope,
            scope_proof,
            aggregation,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            source_states,
            bundle_id=QUALIFICATION_CARRY_BUNDLE_ID,
            created_at=QUALIFICATION_CARRY_CREATED_AT,
        )

        # Both complete rebuild validations precede either filesystem write.
        validate_two_deployment_qualification_plan(
            plan,
            scope,
            scope_proof,
            readiness,
        )
        validate_two_deployment_carry_bundle(
            carry,
            plan,
            scope,
            scope_proof,
            aggregation,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            source_states,
        )

        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.write_text(
            f"{plan.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        args.carry_output.parent.mkdir(parents=True, exist_ok=True)
        args.carry_output.write_text(
            f"{carry.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(json.dumps(_summary(plan, carry), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
