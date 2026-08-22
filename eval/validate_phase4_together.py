"""Validate the no-spend Together candidate suite and cost envelopes.

Usage:
    python -m eval.validate_phase4_together \
        eval/fixtures/preference_eval_phase4_together_v3.json \
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
    validate_together_suite,
)


LEGACY_V1_SUITE_SHA256 = (
    "cb7793244ec640fa336a839d198b8f8e5650cfd20a7a2b9f51a3affc15afa11c"
)
LEGACY_V2_SUITE_SHA256 = (
    "dce672dada8a80cb87f57235ca4b9b44da5c13d44e597b89a63e29d01f67a2a5"
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
        suite_sha256 = content_sha256(suite)
        if suite.suite_version == 1:
            if suite_sha256 != LEGACY_V1_SUITE_SHA256:
                raise ValueError("Together legacy v1 audit hash differs")
            validate_together_suite(suite, profile)
        elif suite.suite_version == 2:
            if suite_sha256 != LEGACY_V2_SUITE_SHA256:
                raise ValueError("Together legacy v2 audit hash differs")
            validate_together_suite(suite, profile)
        elif suite.suite_version == 3:
            expected = build_default_together_suite(profile)
            if suite_sha256 != content_sha256(expected):
                raise ValueError("Together suite differs from frozen v3 builder")
        else:
            raise ValueError("Together suite version is unsupported")
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
