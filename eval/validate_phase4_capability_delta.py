"""Validate the tracked capability delta against its private attempts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_capability_recovery import (
    capability_delta_summary,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
    validate_capability_delta_plan,
    validate_capability_delta_source_proof,
)
from .prepare_phase4_together_capability_delta import (
    load_delta_authoring_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the zero-spend capability role-delta plan."
    )
    parser.add_argument("delta", type=Path)
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("source_adjudication", type=Path)
    parser.add_argument("source_continuation", type=Path)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("source_suite", type=Path)
    parser.add_argument("source_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("provisional_authorization", type=Path)
    parser.add_argument("provisional_state", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument(
        "--harness-attempt",
        action="append",
        nargs=3,
        metavar=("AUTHORIZATION", "STATE", "DIAGNOSTIC"),
        required=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        delta = load_capability_delta_plan(args.delta)
        source_proof = load_capability_delta_source_proof(args.source_proof)
        inputs = load_delta_authoring_inputs(args)
        validate_capability_delta_plan(delta, *inputs)
        validate_capability_delta_source_proof(source_proof, delta)
        summary = capability_delta_summary(delta)
        summary["source_proof_sha256"] = content_sha256(source_proof)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
