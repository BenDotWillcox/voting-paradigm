"""Build the tracked one-call capability diagnostic-retry plan and proof."""

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
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
)
from .phase4_capability_retry import (
    build_capability_diagnostic_retry_plan,
    build_capability_diagnostic_retry_source_proof,
)
from .phase4_together_live import TogetherCatalogPreflightBundle
from .validate_phase4_selector_recovery import (
    load_selector_recovery_public_inputs,
)


RETRY_PLAN_CREATED_AT = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)
RETRY_PROOF_VALIDATED_AT = datetime(2026, 8, 27, 1, 1, tzinfo=UTC)
RETRY_CALL_ID = (
    "retry_together_nemotron_3_ultra_550b_a55b_"
    "dev_fiscal_reserve_evidence_extractor_http_400"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one content-free exact-request diagnostic retry from the "
            "reviewed capability aggregate and ignored source audit."
        )
    )
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
    parser.add_argument("source_catalog_preflight", type=Path)
    parser.add_argument("source_authorization", type=Path)
    parser.add_argument("source_state", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("retry_source_proof_output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        public_inputs = load_selector_recovery_public_inputs(args)
        (
            delta,
            delta_proof,
            parent_delta,
            parent_delta_proof,
            parent_plan,
            parent_suite,
            parent_readiness,
            corrected_plan,
            corrected_suite,
            corrected_readiness,
            profile,
            response_semantics_manifest,
            fixture,
            session,
            semantic_map,
        ) = public_inputs
        aggregation = load_capability_aggregation(args.aggregation)
        aggregation_proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        source_catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.source_catalog_preflight.read_text(encoding="utf-8")
        )
        source_authorization = (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                args.source_authorization.read_text(encoding="utf-8")
            )
        )
        source_state = TogetherDeltaCandidateExecutionState.model_validate_json(
            args.source_state.read_text(encoding="utf-8")
        )
        plan = build_capability_diagnostic_retry_plan(
            aggregation,
            aggregation_proof,
            delta,
            delta_proof,
            parent_delta,
            parent_delta_proof,
            parent_plan,
            parent_suite,
            parent_readiness,
            corrected_plan,
            corrected_suite,
            corrected_readiness,
            profile,
            response_semantics_manifest,
            fixture,
            session,
            semantic_map,
            source_catalog,
            source_authorization,
            source_state,
            plan_id="phase4_together_nemotron_http_diagnostic_retry_v1",
            retry_call_id=RETRY_CALL_ID,
            created_at=RETRY_PLAN_CREATED_AT,
        )
        proof = build_capability_diagnostic_retry_source_proof(
            plan,
            aggregation,
            delta,
            corrected_plan,
            corrected_suite,
            corrected_readiness,
            profile,
            fixture,
            session,
            semantic_map,
            source_catalog,
            source_authorization,
            source_state,
            proof_id="phase4_together_nemotron_http_retry_source_proof_v1",
            validated_at=RETRY_PROOF_VALIDATED_AT,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{plan.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        args.retry_source_proof_output.parent.mkdir(parents=True, exist_ok=True)
        args.retry_source_proof_output.write_text(
            f"{proof.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "schema_version": plan.schema_version,
                    "plan_sha256": content_sha256(plan),
                    "source_proof_sha256": content_sha256(proof),
                    "retry_call_count": plan.retry_call_count,
                    "projected_cost_microusd": (
                        plan.retry_projected_cost_microusd
                    ),
                    "authorized_max_cost_microusd": (
                        plan.retry_authorized_max_cost_microusd
                    ),
                    "cumulative_worst_case_spend_microusd": (
                        plan.cumulative_worst_case_spend_microusd
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
