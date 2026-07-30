"""Validate and hash the frozen Phase 3 bank-authoring profile.

Usage:
    python -m eval.validate_bank_profile \
        eval/fixtures/preference_eval_bank_profile_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .bank_profile import (
    bank_profile_summary,
    build_bank_profile_manifest,
    load_bank_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a preference-evaluation bank profile and emit its "
            "content hashes."
        )
    )
    parser.add_argument("profile", type=Path, help="Path to the profile JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional manifest output path. Defaults to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        manifest = build_bank_profile_manifest(profile)
        payload = manifest.model_dump(mode="json")
        payload["summary"] = bank_profile_summary(profile)
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if args.output is None:
            print(rendered)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(f"{rendered}\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
