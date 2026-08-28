"""Create the private exact-request authorization for public qualification.

This command performs no network request, loads no credential, and spends
nothing.  It converts a fresh catalog preflight plus an explicit user approval
into the only authorization shape accepted by the two-deployment paid runner.
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
from .phase4_capability_aggregation import load_capability_aggregation
from .phase4_qualification_execution import (
    load_capability_source_states,
    load_two_deployment_carry_bundle,
    load_two_deployment_qualification_plan,
)
from .phase4_qualification_io import (
    checkpoint_qualification_candidate_state,
    private_qualification_output,
)
from .phase4_qualification_runtime import (
    QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD,
    QUALIFICATION_PRIOR_SPEND_MICROUSD,
    build_two_deployment_qualification_authorization,
    qualification_authorization_summary,
)
from .phase4_qualification_scope import (
    NEW_PROVIDER_CALL_COUNT,
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
)
from .phase4_together_live import TogetherCatalogPreflightBundle
from .validate_phase4_selector_recovery import (
    build_parser as build_public_chain_parser,
    load_selector_recovery_public_inputs,
)


QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD = (
    QUALIFICATION_PRIOR_SPEND_MICROUSD
    + QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a private exact authorization for 294 public-development "
            "qualification calls. This command spends nothing."
        ),
        parents=[build_public_chain_parser()],
        conflict_handler="resolve",
    )
    parser.add_argument("scope", type=Path)
    parser.add_argument("scope_evidence_proof", type=Path)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("execution_plan", type=Path)
    parser.add_argument("carry_bundle", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--source-state",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--approve-call-count", type=int, required=True)
    parser.add_argument("--approve-max-spend-microusd", type=int, required=True)
    parser.add_argument(
        "--confirm-cumulative-authorized-max-microusd",
        type=int,
        required=True,
    )
    parser.add_argument("--confirm-public-development-only", action="store_true")
    parser.add_argument("--confirm-no-participant-content", action="store_true")
    parser.add_argument("--confirm-no-automatic-retry", action="store_true")
    parser.add_argument("--confirm-no-fallback-or-replacement", action="store_true")
    parser.add_argument("--valid-minutes", type=int, default=120)
    return parser


def _require_manual_approval(args: argparse.Namespace) -> None:
    if (
        args.approve_call_count != NEW_PROVIDER_CALL_COUNT
        or args.approve_max_spend_microusd
        != QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
        or args.confirm_cumulative_authorized_max_microusd
        != QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD
        or not args.confirm_public_development_only
        or not args.confirm_no_participant_content
        or not args.confirm_no_automatic_retry
        or not args.confirm_no_fallback_or_replacement
        or not 1 <= args.valid_minutes <= 240
    ):
        raise ValueError("qualification manual approval is incomplete")


def _require_distinct_output(args: argparse.Namespace, output: Path) -> None:
    input_paths = {
        value.resolve()
        for name, value in vars(args).items()
        if name != "output" and isinstance(value, Path)
    }
    input_paths.update(path.resolve() for path in args.source_state)
    if output in input_paths:
        raise ValueError("qualification authorization cannot overwrite an input")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_manual_approval(args)
        output = private_qualification_output(args.output)
        _require_distinct_output(args, output)
        public = load_selector_recovery_public_inputs(args)
        scope = load_two_deployment_qualification_scope(args.scope)
        proof = load_two_deployment_scope_evidence_proof(
            args.scope_evidence_proof
        )
        aggregation = load_capability_aggregation(args.aggregation)
        plan = load_two_deployment_qualification_plan(args.execution_plan)
        carry = load_two_deployment_carry_bundle(
            private_qualification_output(args.carry_bundle)
        )
        source_states = load_capability_source_states(
            [private_qualification_output(path) for path in args.source_state]
        )
        catalog_path = private_qualification_output(
            args.catalog_preflight_bundle
        )
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            catalog_path.read_text(encoding="utf-8")
        )
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        authorization = build_two_deployment_qualification_authorization(
            scope,
            proof,
            plan,
            carry,
            aggregation,
            public[7],
            public[8],
            public[10],
            public[9],
            public[12],
            public[13],
            public[14],
            source_states,
            catalog,
            bundle_id=f"two_deployment_qualification_authorization_{timestamp}",
            approval_id=f"two_deployment_qualification_approval_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=args.valid_minutes),
        )
        checkpoint_qualification_candidate_state(output, authorization)
        print(
            json.dumps(
                qualification_authorization_summary(authorization),
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
