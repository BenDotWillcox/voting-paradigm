"""Build the restricted runtime map from a reviewed coarse authoring bundle."""

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
from .phase4_semantic_review import (
    build_authored_semantic_map,
    load_semantic_map_authoring_bundle,
    load_semantic_map_authoring_profile,
    semantic_map_authoring_summary,
    validate_final_semantic_map_authoring_inputs,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESTRICTED_OUTPUT_ROOT = REPOSITORY_ROOT / "eval" / "restricted_bank"


def require_safe_semantic_map_output(
    output_path: Path,
    *,
    development_only: bool,
) -> None:
    """Keep a held-out map out of every tracked repository path."""

    if development_only:
        return
    resolved_output = output_path.resolve(strict=False)
    resolved_restricted_root = RESTRICTED_OUTPUT_ROOT.resolve(strict=False)
    if not resolved_output.is_relative_to(resolved_restricted_root):
        raise ValueError(
            "final semantic map output must stay under eval/restricted_bank"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive an exact semantic map from restricted packet-grounded "
            "authoring and print only aggregate metadata."
        )
    )
    parser.add_argument("authoring_bundle", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("bank_profile", type=Path)
    parser.add_argument("phase4_protocol", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
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
        validate_final_semantic_map_authoring_inputs(
            profile,
            bank_profile,
            protocol,
            question_bank,
            fixture,
        )
        semantic_map = build_authored_semantic_map(
            bundle,
            profile,
            fixture,
        )
        require_safe_semantic_map_output(
            args.output,
            development_only=semantic_map.development_only,
        )
        rendered_map = json.dumps(
            semantic_map.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered_map}\n", encoding="utf-8")
        print(
            json.dumps(
                semantic_map_authoring_summary(
                    semantic_map,
                    bundle,
                    profile,
                ),
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
