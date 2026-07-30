"""Validate one Phase 3B domain batch without printing exact packet content."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .bank_authoring import (
    load_domain_bank_batch,
    validate_domain_bank_batch,
)
from .bank_profile import load_bank_profile
from .fixture_io import content_sha256


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one Phase 3B domain batch and emit aggregate hashes "
            "without exact packet content."
        )
    )
    parser.add_argument("profile", type=Path, help="Frozen bank profile JSON.")
    parser.add_argument("batch", type=Path, help="Domain-batch JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_bank_profile(args.profile)
        batch = load_domain_bank_batch(args.batch)
        validate_domain_bank_batch(batch, profile)
        print(
            json.dumps(
                {
                    "schema_version": batch.schema_version,
                    "batch_id": batch.batch_id,
                    "batch_version": batch.batch_version,
                    "batch_sha256": content_sha256(batch),
                    "domain": batch.domain.value,
                    "measure_count": len(batch.items),
                    "source_capture_count": sum(
                        len(item.source_evidence.source_captures)
                        for item in batch.items
                    ),
                    "content_trace_count": sum(
                        len(item.source_evidence.content_traces)
                        for item in batch.items
                    ),
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
