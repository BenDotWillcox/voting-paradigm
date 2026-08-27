"""Validate the tracked capability aggregate without private run inputs."""

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
    capability_aggregation_summary,
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
    validate_capability_aggregation_public_artifacts,
)
from .validate_phase4_selector_recovery import (
    load_selector_recovery_public_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the content-free capability aggregation without "
            "loading private provider attempts."
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
    return parser


def _require_public_path(path: Path) -> None:
    resolved = path.resolve()
    if any(part.casefold() == "private_runs" for part in resolved.parts):
        raise ValueError(
            "capability aggregation public validation cannot read private runs"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for path in (args.aggregation, args.aggregation_source_proof):
            _require_public_path(path)
        public_inputs = load_selector_recovery_public_inputs(args)
        aggregation = load_capability_aggregation(args.aggregation)
        proof = load_capability_aggregation_source_proof(
            args.aggregation_source_proof
        )
        validate_capability_aggregation_public_artifacts(
            aggregation,
            proof,
            *public_inputs,
        )
        summary = capability_aggregation_summary(aggregation)
        summary["source_proof_sha256"] = content_sha256(proof)
        summary["public_input_count"] = 16
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
