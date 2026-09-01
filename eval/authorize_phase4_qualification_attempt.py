"""Create the private exact authorization for qualification attempt v2.

This command performs no network request, loads no credential, and spends
nothing.  It binds a fresh v6 catalog preflight and explicit user approval to
the exact 304-request paired execution plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_qualification_attempt import (
    ATTEMPT_V2_PROVIDER_CALL_COUNT,
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
)
from .phase4_qualification_attempt_runtime import (
    ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD,
    ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD,
    ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD,
    build_qualification_attempt_v2_authorization,
    qualification_attempt_v2_authorization_summary,
)
from .phase4_qualification_io import (
    checkpoint_qualification_candidate_state,
    private_qualification_output,
)
from .phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
)
from .phase4_readiness import load_readiness_bundle
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private exact authorization for 304 public-development "
            "qualification-attempt-v2 calls. This command spends nothing."
        )
    )
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("execution_plan", type=Path)
    parser.add_argument("prior_scope", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--approve-call-count", type=int, required=True)
    parser.add_argument("--approve-max-spend-microusd", type=int, required=True)
    parser.add_argument(
        "--confirm-prior-actual-spend-microusd",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--confirm-cumulative-authorized-max-microusd",
        type=int,
        required=True,
    )
    parser.add_argument("--confirm-public-development-only", action="store_true")
    parser.add_argument("--confirm-no-participant-content", action="store_true")
    parser.add_argument("--confirm-paired-execution-order", action="store_true")
    parser.add_argument("--confirm-no-automatic-retry", action="store_true")
    parser.add_argument("--confirm-no-fallback-or-replacement", action="store_true")
    parser.add_argument("--valid-minutes", type=int, default=60)
    return parser


def _require_manual_approval(args: argparse.Namespace) -> None:
    if (
        args.approve_call_count != ATTEMPT_V2_PROVIDER_CALL_COUNT
        or args.approve_max_spend_microusd
        != ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
        or args.confirm_prior_actual_spend_microusd
        != ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
        or args.confirm_cumulative_authorized_max_microusd
        != ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
        or not args.confirm_public_development_only
        or not args.confirm_no_participant_content
        or not args.confirm_paired_execution_order
        or not args.confirm_no_automatic_retry
        or not args.confirm_no_fallback_or_replacement
        or not 1 <= args.valid_minutes <= 120
    ):
        raise ValueError("qualification attempt manual approval is incomplete")


def _require_private_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    catalog = private_qualification_output(args.catalog_preflight_bundle)
    output = private_qualification_output(args.output)
    if catalog == output:
        raise ValueError("qualification attempt authorization overwrites input")
    return catalog, output


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Approval is checked before any artifact is read.
        _require_manual_approval(args)
        catalog_path, output = _require_private_paths(args)
        proof = load_qualification_attempt_v2_source_proof(args.source_proof)
        plan = load_qualification_attempt_v2_plan(args.execution_plan)
        scope = load_two_deployment_qualification_scope(args.prior_scope)
        suite = load_together_suite(args.corrected_suite)
        readiness = load_readiness_bundle(args.corrected_readiness)
        profile = load_phase4_robustness_profile(args.profile)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        authorization = build_qualification_attempt_v2_authorization(
            plan,
            proof,
            scope,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog,
            bundle_id=f"qualification_attempt_v2_authorization_{timestamp}",
            approval_id=f"qualification_attempt_v2_approval_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=args.valid_minutes),
        )
        checkpoint_qualification_candidate_state(output, authorization)
        print(
            json.dumps(
                qualification_attempt_v2_authorization_summary(authorization),
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
