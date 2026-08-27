"""Create a short-lived private authorization for one exact retry call."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_capability_io import private_capability_output
from .phase4_capability_retry import (
    DIAGNOSTIC_RETRY_CALL_COUNT,
    DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD,
    build_capability_diagnostic_retry_authorization_bundle,
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_together import load_together_suite
from .phase4_together_live import TogetherCatalogPreflightBundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private authorization for the reviewed one-call "
            "Nemotron diagnostic retry. This command spends nothing."
        )
    )
    parser.add_argument("retry_plan", type=Path)
    parser.add_argument("retry_source_proof", type=Path)
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("catalog_preflight", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--approve-call-count", type=int, required=True)
    parser.add_argument("--approve-max-spend-microusd", type=int, required=True)
    parser.add_argument("--confirm-public-development-only", action="store_true")
    parser.add_argument("--confirm-no-participant-content", action="store_true")
    parser.add_argument("--valid-minutes", type=int, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if (
            args.approve_call_count != DIAGNOSTIC_RETRY_CALL_COUNT
            or args.approve_max_spend_microusd
            != DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
            or not args.confirm_public_development_only
            or not args.confirm_no_participant_content
            or not 1 <= args.valid_minutes <= 30
        ):
            raise ValueError("diagnostic retry manual approval is incomplete")
        output = private_capability_output(args.output)
        plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.readiness)
        fresh_catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight.read_text(encoding="utf-8")
        )
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        bundle = build_capability_diagnostic_retry_authorization_bundle(
            plan,
            proof,
            suite,
            profile,
            readiness,
            fresh_catalog,
            bundle_id=f"nemotron_diagnostic_retry_authorization_{timestamp}",
            approval_id=f"nemotron_diagnostic_retry_approval_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=args.valid_minutes),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            f"{bundle.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "schema_version": bundle.schema_version,
                    "bundle_sha256": content_sha256(bundle),
                    "approved_call_count": DIAGNOSTIC_RETRY_CALL_COUNT,
                    "approved_max_spend_microusd": (
                        DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
                    ),
                    "provider_inference_calls_executed": 0,
                    "provider_spend_microusd": 0,
                },
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
