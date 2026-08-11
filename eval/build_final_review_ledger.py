"""Assemble the restricted final review ledger with aggregate-only stdout."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import aware_datetime_arg, safe_authoring_error
from .bank_authoring import load_domain_bank_batch
from .bank_profile import (
    load_bank_profile,
    load_retest_variant_registry,
)
from .final_bundle import assemble_final_review_ledger
from .fixture_io import content_sha256, load_fixture
from .retest_review import load_retest_review_log
from .review_artifacts import load_domain_batch_review_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble exact canonical and retest approvals without printing "
            "measure-level review details."
        )
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("retest_registry", type=Path)
    parser.add_argument("retest_review", type=Path)
    parser.add_argument(
        "--batch-review",
        action="append",
        nargs=2,
        type=Path,
        metavar=("BATCH", "REVIEW_LOG"),
        required=True,
        help="Repeat once for each of the eight reviewed domain batches.",
    )
    parser.add_argument("--ledger-id", required=True)
    parser.add_argument("--ledger-version", type=int, default=1)
    parser.add_argument(
        "--created-at",
        type=aware_datetime_arg,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        fixture = load_fixture(args.fixture)
        registry = load_retest_variant_registry(args.retest_registry)
        retest_review = load_retest_review_log(args.retest_review)
        batch_reviews = [
            (
                load_domain_bank_batch(batch_path),
                load_domain_batch_review_log(review_path),
            )
            for batch_path, review_path in args.batch_review
        ]
        ledger = assemble_final_review_ledger(
            profile,
            fixture,
            registry,
            batch_reviews,
            retest_review,
            ledger_id=args.ledger_id,
            ledger_version=args.ledger_version,
            created_at=args.created_at,
        )
        rendered = json.dumps(
            ledger.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "schema_version": ledger.schema_version,
                    "ledger_id": ledger.ledger_id,
                    "ledger_version": ledger.ledger_version,
                    "ledger_sha256": content_sha256(ledger),
                    "measure_entry_count": len(ledger.measure_entries),
                    "retest_entry_count": len(ledger.retest_entries),
                    "exact_review_details_omitted": True,
                },
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
