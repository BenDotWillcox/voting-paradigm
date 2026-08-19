"""Validate the public Phase 4E robustness and qualification profile.

Usage:
    python -m eval.validate_phase4_robustness \
        eval/fixtures/preference_eval_phase4_robustness_v1.json \
        eval/fixtures/preference_eval_phase4_protocol_v1.json \
        eval/review_summaries/semantic_map_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .phase4_protocol import load_phase4_protocol
from .phase4_robustness import (
    load_phase4_robustness_profile,
    load_semantic_review_summary,
    phase4_robustness_profile_summary,
    validate_phase4_robustness_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the public Phase 4E qualification, privacy, budget, "
            "robustness, and metric precommitment."
        )
    )
    parser.add_argument(
        "profile",
        type=Path,
        help="Path to the Phase 4E robustness profile JSON.",
    )
    parser.add_argument(
        "phase4_protocol",
        type=Path,
        help="Path to the public Phase 4 protocol JSON.",
    )
    parser.add_argument(
        "semantic_review_summary",
        type=Path,
        help="Path to the approved participant-safe semantic-map summary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_phase4_robustness_profile(args.profile)
        protocol = load_phase4_protocol(args.phase4_protocol)
        semantic_summary = load_semantic_review_summary(
            args.semantic_review_summary
        )
        validate_phase4_robustness_profile(
            profile,
            protocol,
            semantic_summary,
        )
        print(
            json.dumps(
                phase4_robustness_profile_summary(profile),
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
