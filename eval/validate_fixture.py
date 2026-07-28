"""CLI for validating and hashing a preference-evaluation fixture.

Usage:
    python -m eval.validate_fixture eval/fixtures/preference_eval_dev_v1.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .fixture_io import (
    build_fixture_manifest,
    load_fixture,
    validate_development_fixture,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a preference-evaluation fixture and emit hashes."
    )
    parser.add_argument("fixture", type=Path, help="Path to the fixture JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional manifest output path. Defaults to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fixture = load_fixture(args.fixture)
    if fixture.development_only:
        validate_development_fixture(fixture)
    manifest = build_fixture_manifest(fixture)
    rendered = json.dumps(
        manifest.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
