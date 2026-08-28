"""Assemble the audited two-deployment qualification result without spend."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import aware_datetime_arg, safe_authoring_error
from .phase4_capability_aggregation import (
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from .phase4_capability_retry import (
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
)
from .phase4_qualification_execution import (
    load_capability_source_states,
    load_two_deployment_carry_bundle,
    load_two_deployment_qualification_plan,
)
from .phase4_qualification_io import (
    REPOSITORY_ROOT,
    load_private_qualification_contract,
    private_qualification_output,
    private_qualification_output_directory,
    validate_qualification_execution_claim,
)
from .phase4_qualification_result_assembly import (
    assemble_two_deployment_qualification_result,
)
from .phase4_qualification_runtime import (
    TwoDeploymentCandidateExecutionState,
    TwoDeploymentQualificationAuthorizationBundle,
)
from .phase4_qualification_scope import (
    QualificationScopePublicInputs,
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
)
from .phase4_together_live import TogetherCatalogPreflightBundle
from .phase4_two_deployment_result import (
    two_deployment_qualification_summary,
)
from .validate_phase4_qualification_scope_amendment import (
    build_parser as build_scope_parser,
)
from .validate_phase4_selector_recovery import (
    load_selector_recovery_public_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate both paid candidate audits and assemble one private "
            "qualification result plus a tracked-eligible aggregate receipt. "
            "This command makes no provider request and spends nothing."
        ),
        parents=[build_scope_parser()],
        conflict_handler="resolve",
    )
    parser.add_argument("execution_plan", type=Path)
    parser.add_argument("carry_bundle", type=Path)
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("run_output_directory", type=Path)
    parser.add_argument("private_result_output", type=Path)
    parser.add_argument("aggregate_receipt_output", type=Path)
    parser.add_argument(
        "--source-state",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--candidate-state",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--qualification-id", required=True)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--created-at", type=aware_datetime_arg, required=True)
    return parser


def _tracked_receipt_output(path: Path) -> Path:
    resolved = path.resolve()
    review_summary_root = (REPOSITORY_ROOT / "eval" / "review_summaries").resolve()
    if resolved.parent != review_summary_root:
        raise ValueError(
            "qualification aggregate receipt must stay in review_summaries"
        )
    return resolved


def _require_distinct_paths(
    args: argparse.Namespace,
    private_result: Path,
    aggregate_receipt: Path,
) -> None:
    inputs = {
        value.resolve()
        for name, value in vars(args).items()
        if name not in {"private_result_output", "aggregate_receipt_output"}
        and isinstance(value, Path)
    }
    inputs.update(path.resolve() for path in args.source_state)
    inputs.update(path.resolve() for path in args.candidate_state)
    if (
        private_result == aggregate_receipt
        or private_result in inputs
        or aggregate_receipt in inputs
    ):
        raise ValueError("qualification result output would overwrite an input")


def _require_new_outputs(private_result: Path, aggregate_receipt: Path) -> None:
    """Reject an existing destination before either result file is written."""

    if private_result.exists() or aggregate_receipt.exists():
        raise ValueError("qualification result output already exists")


def _write_once(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{payload}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError("qualification result output already exists") from error


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_directory = private_qualification_output_directory(
            args.run_output_directory
        )
        private_result = private_qualification_output(
            args.private_result_output
        )
        if private_result.parent != run_directory:
            raise ValueError(
                "qualification private result must stay in its run directory"
            )
        aggregate_receipt = _tracked_receipt_output(
            args.aggregate_receipt_output
        )
        _require_distinct_paths(
            args,
            private_result,
            aggregate_receipt,
        )
        _require_new_outputs(private_result, aggregate_receipt)
        for path in args.candidate_state:
            resolved = private_qualification_output(path)
            if resolved.parent != run_directory:
                raise ValueError(
                    "qualification candidate states must stay in the run directory"
                )
        public_inputs = QualificationScopePublicInputs(
            *load_selector_recovery_public_inputs(args)
        )
        scope = load_two_deployment_qualification_scope(args.amendment)
        scope_proof = load_two_deployment_scope_evidence_proof(
            args.scope_evidence_proof
        )
        aggregation = load_capability_aggregation(args.aggregation)
        aggregation_proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        retry_plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        retry_proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        plan = load_two_deployment_qualification_plan(args.execution_plan)
        carry = load_two_deployment_carry_bundle(
            private_qualification_output(args.carry_bundle)
        )
        authorization = load_private_qualification_contract(
            args.authorization_bundle,
            TwoDeploymentQualificationAuthorizationBundle,
        )
        catalog = load_private_qualification_contract(
            args.catalog_preflight_bundle,
            TogetherCatalogPreflightBundle,
        )
        source_states = load_capability_source_states(
            [private_qualification_output(path) for path in args.source_state]
        )
        candidate_states = [
            load_private_qualification_contract(
                path,
                TwoDeploymentCandidateExecutionState,
            )
            for path in args.candidate_state
        ]
        validate_qualification_execution_claim(
            plan,
            authorization,
            run_directory,
        )
        result, receipt = assemble_two_deployment_qualification_result(
            scope,
            scope_proof,
            aggregation,
            aggregation_proof,
            retry_plan,
            retry_proof,
            public_inputs,
            plan,
            carry,
            authorization,
            catalog,
            source_states,
            candidate_states,
            qualification_id=args.qualification_id,
            receipt_id=args.receipt_id,
            created_at=args.created_at,
        )
        _write_once(private_result, result.model_dump_json(indent=2))
        _write_once(aggregate_receipt, receipt.model_dump_json(indent=2))
        print(
            json.dumps(
                two_deployment_qualification_summary(result),
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
