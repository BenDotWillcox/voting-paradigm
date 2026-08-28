"""Validate the two-deployment qualification amendment without private inputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_capability_aggregation import (
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from .phase4_capability_retry import (
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
)
from .phase4_qualification_scope import (
    FROZEN_TWO_DEPLOYMENT_SCOPE_EVIDENCE_PROOF_SHA256,
    FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256,
    QualificationScopePublicInputs,
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
    qualification_scope_summary,
    validate_two_deployment_qualification_scope,
)
from .validate_phase4_selector_recovery import (
    build_parser as build_public_chain_parser,
    load_selector_recovery_public_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the reviewed two-runnable-deployment qualification "
            "scope without reading ignored provider state."
        ),
        parents=[build_public_chain_parser()],
        conflict_handler="resolve",
    )
    parser.add_argument("amendment", type=Path)
    parser.add_argument("scope_evidence_proof", type=Path)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("aggregation_source_proof", type=Path)
    parser.add_argument("retry_plan", type=Path)
    parser.add_argument("retry_source_proof", type=Path)
    return parser


def _require_public_path(path: Path) -> None:
    if any(part.casefold() == "private_runs" for part in path.resolve().parts):
        raise ValueError("qualification scope validation cannot read private runs")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for path in (
            args.amendment,
            args.scope_evidence_proof,
            args.aggregation,
            args.aggregation_source_proof,
            args.retry_plan,
            args.retry_source_proof,
        ):
            _require_public_path(path)
        public_inputs = QualificationScopePublicInputs(
            *load_selector_recovery_public_inputs(args)
        )
        suite = public_inputs.corrected_suite
        readiness = public_inputs.corrected_readiness
        profile = public_inputs.robustness_profile
        amendment = load_two_deployment_qualification_scope(args.amendment)
        evidence_proof = load_two_deployment_scope_evidence_proof(
            args.scope_evidence_proof
        )
        if (
            content_sha256(amendment) != FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256
            or content_sha256(evidence_proof)
            != FROZEN_TWO_DEPLOYMENT_SCOPE_EVIDENCE_PROOF_SHA256
        ):
            raise ValueError("qualification scope frozen hashes differ")
        aggregation = load_capability_aggregation(args.aggregation)
        aggregation_proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        retry_plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        retry_proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        validate_two_deployment_qualification_scope(
            amendment,
            evidence_proof,
            aggregation,
            aggregation_proof,
            retry_plan,
            retry_proof,
            suite,
            readiness,
            profile,
            public_inputs,
        )
        summary = qualification_scope_summary(amendment, evidence_proof)
        summary["public_input_count"] = 20
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
