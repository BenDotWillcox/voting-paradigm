"""Assemble eight Phase 3B domain batches into the final evaluation fixture.

The command writes exact packet content only to ``--output``.  Stdout contains
an aggregate manifest summary that is safe for the packet-blind participant.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import aware_datetime_arg, safe_authoring_error
from .bank_authoring import (
    assemble_final_fixture,
    load_domain_bank_batch,
)
from .bank_profile import load_bank_profile
from .fixture_io import build_fixture_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and assemble eight Phase 3B domain batches without "
            "printing exact packet content."
        )
    )
    parser.add_argument("profile", type=Path, help="Frozen bank profile JSON.")
    parser.add_argument(
        "batches",
        type=Path,
        nargs="+",
        help="The eight authored domain-batch JSON files.",
    )
    parser.add_argument(
        "--fixture-id",
        required=True,
        help="Stable identifier for the assembled final fixture.",
    )
    parser.add_argument(
        "--fixture-version",
        type=int,
        default=1,
        help="Positive final-fixture version. Defaults to 1.",
    )
    parser.add_argument(
        "--created-at",
        type=aware_datetime_arg,
        required=True,
        help="Frozen timezone-aware ISO-8601 fixture timestamp.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for exact final-fixture JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        batches = [
            load_domain_bank_batch(path) for path in args.batches
        ]
        fixture = assemble_final_fixture(
            profile,
            batches,
            fixture_id=args.fixture_id,
            fixture_version=args.fixture_version,
            created_at=args.created_at,
        )
        rendered = json.dumps(
            fixture.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")

        manifest = build_fixture_manifest(fixture)
        print(
            json.dumps(
                {
                    "schema_version": manifest.schema_version,
                    "fixture_id": manifest.fixture_id,
                    "fixture_version": manifest.fixture_version,
                    "fixture_sha256": manifest.fixture_sha256,
                    "jurisdiction_sha256": (
                        manifest.jurisdiction_sha256
                    ),
                    "measure_count": len(manifest.measures),
                    "output": str(args.output),
                    "exact_packet_content_omitted": True,
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
