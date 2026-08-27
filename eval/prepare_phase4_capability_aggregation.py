"""Build the content-free capability aggregation from exact private audits."""

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
from .phase4_capability_aggregation import (
    CapabilityAttempt,
    build_capability_aggregation,
    build_capability_aggregation_source_proof,
    capability_aggregation_summary,
)
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
)
from .phase4_together_live import TogetherCatalogPreflightBundle
from .validate_phase4_selector_recovery import (
    load_selector_recovery_public_inputs,
)


CAPABILITY_AGGREGATION_CREATED_AT = datetime(
    2026,
    8,
    27,
    0,
    10,
    tzinfo=UTC,
)
CAPABILITY_AGGREGATION_PROOF_VALIDATED_AT = datetime(
    2026,
    8,
    27,
    0,
    11,
    tzinfo=UTC,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate the reviewed capability attempts without provider "
            "calls, credentials, participant content, or model selection."
        )
    )
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
    parser.add_argument("catalog_preflight", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("aggregation_source_proof_output", type=Path)
    parser.add_argument(
        "--attempt",
        action="append",
        nargs=2,
        metavar=("AUTHORIZATION", "STATE"),
        type=Path,
        required=True,
        help=(
            "One ignored authorization/state pair in corrected-plan "
            "candidate order; provide exactly three."
        ),
    )
    return parser


def _load_attempts(args: argparse.Namespace) -> list[CapabilityAttempt]:
    if len(args.attempt) != 3:
        raise ValueError("capability aggregation needs exactly three attempts")
    return [
        (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                authorization_path.read_text(encoding="utf-8")
            ),
            TogetherDeltaCandidateExecutionState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            ),
        )
        for authorization_path, state_path in args.attempt
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        public_inputs = load_selector_recovery_public_inputs(args)
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight.read_text(encoding="utf-8")
        )
        attempts = _load_attempts(args)
        aggregation = build_capability_aggregation(
            *public_inputs,
            catalog,
            attempts,
            aggregation_id="phase4_together_capability_aggregation_v1",
            created_at=CAPABILITY_AGGREGATION_CREATED_AT,
        )
        proof = build_capability_aggregation_source_proof(
            aggregation,
            *public_inputs,
            catalog,
            attempts,
            proof_id="phase4_together_capability_aggregation_source_proof_v1",
            validated_at=CAPABILITY_AGGREGATION_PROOF_VALIDATED_AT,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{aggregation.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        args.aggregation_source_proof_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.aggregation_source_proof_output.write_text(
            f"{proof.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        summary = capability_aggregation_summary(aggregation)
        summary["source_proof_sha256"] = content_sha256(proof)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
