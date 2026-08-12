"""Validate and hash the public Phase 4A architecture protocol.

Usage:
    python -m eval.validate_phase4_protocol \
        eval/fixtures/preference_eval_phase4_protocol_v1.json \
        eval/fixtures/preference_eval_bank_profile_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .bank_profile import load_bank_profile
from .phase4_protocol import (
    build_phase4_protocol_manifest,
    load_phase4_protocol,
    phase4_protocol_summary,
    validate_phase4_protocol_against_bank_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the Phase 4A architecture and comparison protocol, bind "
            "it to the public Phase 3A bank profile, and emit content hashes."
        )
    )
    parser.add_argument("protocol", type=Path, help="Path to the protocol JSON.")
    parser.add_argument(
        "bank_profile",
        type=Path,
        help="Path to the public Phase 3A bank profile JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional manifest output path. Defaults to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        protocol = load_phase4_protocol(args.protocol)
        bank_profile = load_bank_profile(args.bank_profile)
        validate_phase4_protocol_against_bank_profile(protocol, bank_profile)
        manifest = build_phase4_protocol_manifest(protocol)
        payload = manifest.model_dump(mode="json")
        payload["summary"] = phase4_protocol_summary(protocol)
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
