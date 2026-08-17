"""Validate an authored Phase 4D semantic map with aggregate-only output."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_semantic import (
    authored_semantic_map_summary,
    load_authored_semantic_map,
    validate_authored_semantic_map,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an exact fixture-bound authored semantic map and emit "
            "aggregate metadata without option mappings."
        )
    )
    parser.add_argument("semantic_map", type=Path, help="Semantic map JSON.")
    parser.add_argument("fixture", type=Path, help="Evaluation fixture JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fixture = load_fixture(args.fixture)
        semantic_map = load_authored_semantic_map(args.semantic_map)
        validate_authored_semantic_map(
            semantic_map,
            fixture,
            semantic_map.ontology,
        )
        print(
            json.dumps(
                authored_semantic_map_summary(semantic_map),
                indent=2,
                sort_keys=True,
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
