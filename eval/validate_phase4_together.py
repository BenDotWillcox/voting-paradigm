"""Validate the no-spend Together candidate suite and cost envelopes.

Usage:
    python -m eval.validate_phase4_together \
        eval/fixtures/preference_eval_phase4_together_v1.json \
        eval/fixtures/preference_eval_phase4_robustness_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_together import (
    build_default_together_suite,
    build_no_spend_report,
    load_together_suite,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the frozen three-candidate Together suite and print its "
            "zero-network budget projection."
        )
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("robustness_profile", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.robustness_profile)
        expected = build_default_together_suite(profile)
        if content_sha256(suite) != content_sha256(expected):
            raise ValueError("Together suite differs from frozen v1 builder")
        report = build_no_spend_report(suite, profile)
        print(
            json.dumps(
                report.model_dump(mode="json"),
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
