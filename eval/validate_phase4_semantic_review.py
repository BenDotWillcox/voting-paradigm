"""Validate a restricted semantic-map review and emit only a safe summary."""

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
from .fixture_io import load_fixture
from .phase4_protocol import load_phase4_protocol
from .phase4_semantic import load_authored_semantic_map
from .phase4_semantic_review import (
    build_nonrevealing_semantic_map_review_summary,
    load_semantic_map_authoring_bundle,
    load_semantic_map_authoring_profile,
    load_semantic_map_review_log,
    validate_final_semantic_map_authoring_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an exact semantic-map review and write only its "
            "participant-safe aggregate summary."
        )
    )
    parser.add_argument("review_log", type=Path)
    parser.add_argument("semantic_map", type=Path)
    parser.add_argument("authoring_bundle", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("bank_profile", type=Path)
    parser.add_argument("phase4_protocol", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--summary-output", type=Path, required=True)
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
        fixture = load_fixture(args.fixture)
        question_bank = QuestionBank.load_from_path(args.question_bank)
        bundle = load_semantic_map_authoring_bundle(args.authoring_bundle)
        semantic_map = load_authored_semantic_map(args.semantic_map)
        review_log = load_semantic_map_review_log(args.review_log)
        validate_final_semantic_map_authoring_inputs(
            profile,
            bank_profile,
            protocol,
            question_bank,
            fixture,
        )
        summary = build_nonrevealing_semantic_map_review_summary(
            review_log,
            semantic_map,
            bundle,
            profile,
            fixture,
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
