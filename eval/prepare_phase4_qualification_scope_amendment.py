"""Build the reviewed two-deployment qualification scope with zero spend."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .phase4_capability_aggregation import (
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from .phase4_capability_recovery import TogetherDeltaCandidateExecutionState
from .phase4_capability_retry import (
    load_capability_diagnostic_retry_authorization_bundle,
    load_capability_diagnostic_retry_execution_state,
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
)
from .phase4_qualification_scope import (
    QualificationScopePublicInputs,
    build_two_deployment_qualification_scope,
    build_two_deployment_scope_evidence_proof,
    qualification_scope_summary,
)
from .phase4_together_live import TogetherCatalogPreflightBundle
from .validate_phase4_selector_recovery import (
    build_parser as build_public_chain_parser,
    load_selector_recovery_public_inputs,
)


SCOPE_PROOF_VALIDATED_AT = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
SCOPE_AMENDMENT_CREATED_AT = datetime(2026, 8, 28, 1, 1, tzinfo=UTC)


def _require_safe_output_paths(args: argparse.Namespace) -> None:
    output_names = {"output", "scope_evidence_proof_output"}
    outputs = {
        name: value.resolve()
        for name, value in vars(args).items()
        if name in output_names and isinstance(value, Path)
    }
    inputs = {
        value.resolve()
        for name, value in vars(args).items()
        if name not in output_names and isinstance(value, Path)
    }
    if len(set(outputs.values())) != len(output_names):
        raise ValueError("qualification scope outputs must be distinct")
    if any(path in inputs for path in outputs.values()):
        raise ValueError("qualification scope output cannot overwrite an input")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the two-runnable-deployment qualification amendment from "
            "reviewed public artifacts and the exact ignored retry audit."
        ),
        parents=[build_public_chain_parser()],
        conflict_handler="resolve",
    )
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("aggregation_source_proof", type=Path)
    parser.add_argument("retry_plan", type=Path)
    parser.add_argument("retry_source_proof", type=Path)
    parser.add_argument("retry_authorization", type=Path)
    parser.add_argument("retry_state", type=Path)
    parser.add_argument("retry_source_state", type=Path)
    parser.add_argument("retry_fresh_catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("scope_evidence_proof_output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_safe_output_paths(args)
        public_inputs = QualificationScopePublicInputs(
            *load_selector_recovery_public_inputs(args)
        )
        suite = public_inputs.corrected_suite
        readiness = public_inputs.corrected_readiness
        profile = public_inputs.robustness_profile
        aggregation = load_capability_aggregation(args.aggregation)
        aggregation_proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        retry_plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        retry_proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        retry_authorization = (
            load_capability_diagnostic_retry_authorization_bundle(
                args.retry_authorization
            )
        )
        retry_state = load_capability_diagnostic_retry_execution_state(
            args.retry_state
        )
        retry_source_state = TogetherDeltaCandidateExecutionState.model_validate_json(
            args.retry_source_state.read_text(encoding="utf-8")
        )
        fresh_catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.retry_fresh_catalog.read_text(encoding="utf-8")
        )
        evidence_proof = build_two_deployment_scope_evidence_proof(
            aggregation,
            aggregation_proof,
            retry_plan,
            retry_proof,
            retry_authorization,
            retry_state,
            retry_source_state,
            suite,
            readiness,
            profile,
            fresh_catalog,
            public_inputs,
            proof_id="phase4_two_deployment_qualification_scope_proof_v1",
            validated_at=SCOPE_PROOF_VALIDATED_AT,
        )
        amendment = build_two_deployment_qualification_scope(
            aggregation,
            aggregation_proof,
            retry_plan,
            retry_proof,
            evidence_proof,
            suite,
            readiness,
            profile,
            public_inputs,
            amendment_id="phase4_two_deployment_qualification_scope_v1",
            created_at=SCOPE_AMENDMENT_CREATED_AT,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{amendment.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        args.scope_evidence_proof_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.scope_evidence_proof_output.write_text(
            f"{evidence_proof.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                qualification_scope_summary(amendment, evidence_proof),
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
