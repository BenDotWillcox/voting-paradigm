"""Build a restricted Phase 3C presentation plan with aggregate-only stdout."""

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
    load_retest_variant_registry,
)
from .fixture_io import content_sha256, load_fixture
from .presentation_plan import build_presentation_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the deterministic six-wave and retest presentation plan "
            "without printing exact measure or option identifiers."
        )
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("retest_registry", type=Path)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--plan-version", type=int, default=1)
    parser.add_argument(
        "--created-at",
        type=aware_datetime_arg,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        fixture = load_fixture(args.fixture)
        registry = load_retest_variant_registry(args.retest_registry)
        plan = build_presentation_plan(
            fixture,
            profile,
            registry,
            plan_id=args.plan_id,
            plan_version=args.plan_version,
            created_at=args.created_at,
        )
        rendered = json.dumps(
            plan.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
        wave_counts = {
            str(wave_index): sum(
                entry.wave_index == wave_index
                for entry in plan.initial_presentations
            )
            for wave_index in range(
                profile.presentation_order_policy.wave_count
            )
        }
        print(
            json.dumps(
                {
                    "schema_version": plan.schema_version,
                    "plan_id": plan.plan_id,
                    "plan_version": plan.plan_version,
                    "plan_sha256": content_sha256(plan),
                    "initial_presentation_count": len(
                        plan.initial_presentations
                    ),
                    "retest_presentation_count": len(
                        plan.retest_presentations
                    ),
                    "wave_counts": wave_counts,
                    "exact_plan_content_omitted": True,
                },
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
