"""Validate the tracked selector-recovery chain without private run inputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_recovery import (
    load_capability_delta_plan,
    load_capability_delta_source_proof,
)
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_selector_recovery import (
    load_selector_recovery_delta,
    load_selector_recovery_source_proof,
    selector_recovery_summary,
    validate_selector_recovery_public_artifacts,
)
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the public selector-recovery chain without loading "
            "private provider attempts."
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
    return parser


def _require_public_path(path: Path) -> None:
    resolved = path.resolve()
    if any(part.casefold() == "private_runs" for part in resolved.parts):
        raise ValueError(
            "selector recovery public validation cannot read private runs"
        )


def load_selector_recovery_public_inputs(args: argparse.Namespace):
    """Load only the tracked/public inputs accepted by the public validator."""

    paths = (
        args.delta,
        args.source_proof,
        args.parent_delta,
        args.parent_source_proof,
        args.parent_plan,
        args.parent_suite,
        args.parent_readiness,
        args.corrected_plan,
        args.corrected_suite,
        args.corrected_readiness,
        args.profile,
        args.development_fixture,
        args.development_session,
        args.development_semantic_map,
    )
    for path in paths:
        _require_public_path(path)

    return (
        load_selector_recovery_delta(args.delta),
        load_selector_recovery_source_proof(args.source_proof),
        load_capability_delta_plan(args.parent_delta),
        load_capability_delta_source_proof(args.parent_source_proof),
        TogetherCapabilityPlan.model_validate_json(
            args.parent_plan.read_text(encoding="utf-8")
        ),
        load_together_suite(args.parent_suite),
        load_readiness_bundle(args.parent_readiness),
        TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        ),
        load_together_suite(args.corrected_suite),
        load_readiness_bundle(args.corrected_readiness),
        load_phase4_robustness_profile(args.profile),
        PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
        load_fixture(args.development_fixture),
        load_session_script(args.development_session),
        load_authored_semantic_map(args.development_semantic_map),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = load_selector_recovery_public_inputs(args)
        delta, proof = inputs[:2]
        validate_selector_recovery_public_artifacts(*inputs)
        summary = selector_recovery_summary(delta)
        summary["source_proof_sha256"] = content_sha256(proof)
        summary["public_input_count"] = 14
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
