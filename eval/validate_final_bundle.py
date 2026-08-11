"""Validate all frozen Phase 3C artifacts and emit a safe manifest."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import aware_datetime_arg, safe_authoring_error
from .bank_profile import (
    load_bank_profile,
    load_bank_review_ledger,
    load_retest_variant_registry,
)
from .final_bundle import build_final_execution_bundle_manifest
from .fixture_io import load_fixture
from .presentation_plan import load_presentation_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the final fixture, retest registry, review ledger, and "
            "presentation plan without printing exact content."
        )
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("retest_registry", type=Path)
    parser.add_argument("review_ledger", type=Path)
    parser.add_argument("presentation_plan", type=Path)
    parser.add_argument(
        "--created-at",
        type=aware_datetime_arg,
        required=True,
    )
    parser.add_argument("--manifest-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        fixture = load_fixture(args.fixture)
        registry = load_retest_variant_registry(args.retest_registry)
        ledger = load_bank_review_ledger(args.review_ledger)
        plan = load_presentation_plan(args.presentation_plan)
        manifest = build_final_execution_bundle_manifest(
            fixture,
            profile,
            registry,
            ledger,
            plan,
            created_at=args.created_at,
        )
        rendered = json.dumps(
            manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(f"{rendered}\n", encoding="utf-8")
        print(rendered)
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
