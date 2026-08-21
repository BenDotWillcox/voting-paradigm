"""Create a private manual authorization for the paid capability preflight.

This command makes no network or provider call.  Its output is ignored and is
required by the separate paid runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_capability import (
    CAPABILITY_CALL_COUNT,
    CAPABILITY_MAX_SPEND_MICROUSD,
    TogetherCapabilityPlan,
    build_capability_authorization_bundle,
    validate_capability_plan,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .prequential import load_session_script


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()


def _private_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("capability authorization must stay under private_runs")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a time-limited private authorization for exactly 15 paid "
            "public-development capability calls. This command spends nothing."
        )
    )
    parser.add_argument("plan", type=Path)
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--approve-call-count", type=int, required=True)
    parser.add_argument("--approve-max-spend-microusd", type=int, required=True)
    parser.add_argument("--confirm-public-development-only", action="store_true")
    parser.add_argument("--confirm-no-participant-content", action="store_true")
    parser.add_argument("--valid-minutes", type=int, default=60)
    return parser


def _require_manual_approval(args: argparse.Namespace) -> None:
    if (
        args.approve_call_count != CAPABILITY_CALL_COUNT
        or args.approve_max_spend_microusd
        != CAPABILITY_MAX_SPEND_MICROUSD
        or not args.confirm_public_development_only
        or not args.confirm_no_participant_content
        or not 1 <= args.valid_minutes <= 240
    ):
        raise ValueError("capability manual approval is incomplete")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_manual_approval(args)
        output = _private_output(args.output)
        plan = TogetherCapabilityPlan.model_validate_json(
            args.plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight_bundle.read_text(encoding="utf-8")
        )
        validate_capability_plan(
            plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        bundle = build_capability_authorization_bundle(
            plan,
            suite,
            profile,
            readiness,
            catalog,
            bundle_id=f"together_capability_authorization_{timestamp}",
            approval_id=f"together_capability_approval_{timestamp}",
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
                    "approved_call_count": CAPABILITY_CALL_COUNT,
                    "approved_max_spend_microusd": (
                        CAPABILITY_MAX_SPEND_MICROUSD
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
