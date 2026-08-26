"""Build the zero-spend chained selector-recovery delta and source proof."""

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
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityExecutionState,
)
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
)
from .phase4_provider import ProviderStructuredOutputDiagnostic
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_selector_recovery import (
    build_selector_recovery_delta_plan,
    build_selector_recovery_source_proof,
    selector_recovery_summary,
    validate_selector_recovery_delta_plan,
)
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


SELECTOR_RECOVERY_DELTA_CREATED_AT = datetime(
    2026,
    8,
    26,
    20,
    15,
    tzinfo=UTC,
)
SELECTOR_RECOVERY_PROOF_VALIDATED_AT = datetime(
    2026,
    8,
    26,
    20,
    20,
    tzinfo=UTC,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind the reviewed v1 delta, the later GLM selector attempt, "
            "and the corrected suite-v5 role partition without provider calls."
        )
    )
    parser.add_argument("parent_delta", type=Path)
    parser.add_argument("parent_source_proof", type=Path)
    parser.add_argument("parent_plan", type=Path)
    parser.add_argument("parent_suite", type=Path)
    parser.add_argument("parent_readiness", type=Path)
    parser.add_argument("latest_authorization", type=Path)
    parser.add_argument("latest_state", type=Path)
    parser.add_argument("latest_diagnostic", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("source_proof_output", type=Path)
    parser.add_argument(
        "--parent-source-state",
        action="append",
        type=Path,
        required=True,
        help="One ignored v1 source state; provide exactly three.",
    )
    return parser


def load_selector_recovery_authoring_inputs(args):
    parent_delta = load_capability_delta_plan(args.parent_delta)
    parent_proof = load_capability_delta_source_proof(
        args.parent_source_proof
    )
    if len(args.parent_source_state) != 3:
        raise ValueError("selector recovery needs exactly three parent states")
    parent_states = [
        TogetherCandidateCapabilityExecutionState.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        for path in args.parent_source_state
    ]
    latest_authorization = (
        TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
            args.latest_authorization.read_text(encoding="utf-8")
        )
    )
    latest_state = TogetherDeltaCandidateExecutionState.model_validate_json(
        args.latest_state.read_text(encoding="utf-8")
    )
    latest_diagnostic = ProviderStructuredOutputDiagnostic.model_validate_json(
        args.latest_diagnostic.read_text(encoding="utf-8")
    )
    parent_plan = TogetherCapabilityPlan.model_validate_json(
        args.parent_plan.read_text(encoding="utf-8")
    )
    parent_suite = load_together_suite(args.parent_suite)
    parent_readiness = load_readiness_bundle(args.parent_readiness)
    corrected_plan = TogetherCapabilityPlan.model_validate_json(
        args.corrected_plan.read_text(encoding="utf-8")
    )
    corrected_suite = load_together_suite(args.corrected_suite)
    corrected_readiness = load_readiness_bundle(args.corrected_readiness)
    profile = load_phase4_robustness_profile(args.profile)
    fixture = load_fixture(args.development_fixture)
    session = load_session_script(args.development_session)
    semantic_map = load_authored_semantic_map(args.development_semantic_map)
    return (
        parent_delta,
        parent_proof,
        parent_states,
        latest_authorization,
        latest_state,
        latest_diagnostic,
        parent_plan,
        parent_suite,
        parent_readiness,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        profile,
        PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
        fixture,
        session,
        semantic_map,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = load_selector_recovery_authoring_inputs(args)
        delta = build_selector_recovery_delta_plan(
            *inputs,
            plan_id="phase4_together_selector_recovery_delta_v2",
            created_at=SELECTOR_RECOVERY_DELTA_CREATED_AT,
        )
        validate_selector_recovery_delta_plan(delta, *inputs)
        source_proof = build_selector_recovery_source_proof(
            delta,
            *inputs,
            proof_id="phase4_together_selector_recovery_source_proof_v2",
            validated_at=SELECTOR_RECOVERY_PROOF_VALIDATED_AT,
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
        summary = selector_recovery_summary(delta)
        summary["source_proof_sha256"] = content_sha256(source_proof)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
