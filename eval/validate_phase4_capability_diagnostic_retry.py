"""Validate the one-call capability diagnostic retry without private inputs."""

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
    validate_capability_diagnostic_retry_plan_public,
    validate_capability_diagnostic_retry_source_proof,
)
from .validate_phase4_selector_recovery import (
    load_selector_recovery_public_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the exact one-call diagnostic retry without reading "
            "ignored provider state."
        )
    )
    parser.add_argument("retry_plan", type=Path)
    parser.add_argument("retry_source_proof", type=Path)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("aggregation_source_proof", type=Path)
    parser.add_argument("delta", type=Path)
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("parent_delta", type=Path)
    parser.add_argument("parent_source_proof", type=Path)
    parser.add_argument("parent_plan", type=Path)
    parser.add_argument("parent_suite", type=Path)
    parser.add_argument("parent_readiness", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    return parser


def _require_public_path(path: Path) -> None:
    if any(part.casefold() == "private_runs" for part in path.resolve().parts):
        raise ValueError("diagnostic retry validation cannot read private runs")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for path in (
            args.retry_plan,
            args.retry_source_proof,
            args.aggregation,
            args.aggregation_source_proof,
        ):
            _require_public_path(path)
        public_inputs = load_selector_recovery_public_inputs(args)
        plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        aggregation = load_capability_aggregation(args.aggregation)
        aggregation_proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        validate_capability_diagnostic_retry_plan_public(
            plan,
            aggregation,
            aggregation_proof,
            *public_inputs,
        )
        validate_capability_diagnostic_retry_source_proof(proof, plan)
        print(
            json.dumps(
                {
                    "schema_version": plan.schema_version,
                    "plan_sha256": content_sha256(plan),
                    "source_proof_sha256": content_sha256(proof),
                    "retry_call_count": plan.retry_call_count,
                    "authorized_max_cost_microusd": (
                        plan.retry_authorized_max_cost_microusd
                    ),
                    "public_input_count": 18,
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
