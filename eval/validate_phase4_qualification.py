"""Validate an aggregate-only Phase 4E candidate qualification bundle.

Usage:
    python -m eval.validate_phase4_qualification \
        qualification.json robustness-profile.json usage-ledger.json \
        execution-journal.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .phase4_qualification import (
    load_phase4_qualification_bundle,
    phase4_qualification_summary,
    validate_phase4_qualification_bundle,
)
from .phase4_provider import ProviderExecutionJournal
from .phase4_robustness import (
    ProviderUsageLedger,
    load_phase4_robustness_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate exact three-candidate Phase 4E qualification bindings "
            "and print an aggregate-only summary."
        )
    )
    parser.add_argument("bundle", type=Path)
    parser.add_argument("robustness_profile", type=Path)
    parser.add_argument("provider_usage_ledger", type=Path)
    parser.add_argument("provider_execution_journal", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = load_phase4_qualification_bundle(args.bundle)
        profile = load_phase4_robustness_profile(args.robustness_profile)
        ledger = ProviderUsageLedger.model_validate_json(
            args.provider_usage_ledger.read_text(encoding="utf-8")
        )
        journal = ProviderExecutionJournal.model_validate_json(
            args.provider_execution_journal.read_text(encoding="utf-8")
        )
        validate_phase4_qualification_bundle(
            bundle,
            profile,
            ledger,
            journal,
        )
        print(
            json.dumps(
                phase4_qualification_summary(bundle),
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
