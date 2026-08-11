"""Validate a restricted retest review and emit only its safe summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .bank_profile import (
    load_bank_profile,
    load_retest_variant_registry,
)
from .fixture_io import load_fixture
from .retest_review import (
    build_nonrevealing_retest_review_summary,
    load_retest_review_log,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an exact retest-variant review and write only its "
            "participant-safe aggregate summary."
        )
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("retest_registry", type=Path)
    parser.add_argument("review_log", type=Path)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        fixture = load_fixture(args.fixture)
        registry = load_retest_variant_registry(args.retest_registry)
        log = load_retest_review_log(args.review_log)
        summary = build_nonrevealing_retest_review_summary(
            log,
            registry,
            fixture,
            profile,
        )
        rendered = json.dumps(
            summary.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(f"{rendered}\n", encoding="utf-8")
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
