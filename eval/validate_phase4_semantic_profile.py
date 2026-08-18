"""Validate the public Phase 4 semantic-map authoring precommitment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from preferences.questions.bank import DEFAULT_SEED_PATH, QuestionBank

from .authoring_cli import safe_authoring_error
from .bank_profile import load_bank_profile
from .phase4_protocol import load_phase4_protocol
from .phase4_semantic_review import (
    load_semantic_map_authoring_profile,
    semantic_map_authoring_profile_summary,
    validate_semantic_map_authoring_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the public semantic-map authoring profile and emit "
            "content-free aggregate metadata."
        )
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("bank_profile", type=Path)
    parser.add_argument("phase4_protocol", type=Path)
    parser.add_argument(
        "--question-bank",
        type=Path,
        default=DEFAULT_SEED_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_semantic_map_authoring_profile(args.profile)
        bank_profile = load_bank_profile(args.bank_profile)
        protocol = load_phase4_protocol(args.phase4_protocol)
        question_bank = QuestionBank.load_from_path(args.question_bank)
        validate_semantic_map_authoring_profile(
            profile,
            bank_profile,
            protocol,
            question_bank,
        )
        print(
            json.dumps(
                semantic_map_authoring_profile_summary(profile),
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
