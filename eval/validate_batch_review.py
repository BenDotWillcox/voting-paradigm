"""Validate a restricted review log and write its participant-safe summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .bank_authoring import load_domain_bank_batch
from .bank_profile import load_bank_profile
from .review_artifacts import (
    build_nonrevealing_review_summary,
    load_domain_batch_review_log,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one exact-content review log and emit only its "
            "participant-safe aggregate summary."
        )
    )
    parser.add_argument("profile", type=Path, help="Frozen bank profile JSON.")
    parser.add_argument("batch", type=Path, help="Reviewed domain-batch JSON.")
    parser.add_argument(
        "review_log",
        type=Path,
        help="Restricted exact-content review-log JSON.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        required=True,
        help="Path for the participant-safe summary JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        batch = load_domain_bank_batch(args.batch)
        log = load_domain_batch_review_log(args.review_log)
        summary = build_nonrevealing_review_summary(
            log,
            batch,
            profile,
        )
        rendered = json.dumps(
            summary.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            f"{rendered}\n",
            encoding="utf-8",
        )
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
