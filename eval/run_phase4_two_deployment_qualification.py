"""Run the exact paid public-development two-deployment qualification."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_capability import CapabilityInterviewerTools
from .phase4_capability_aggregation import load_capability_aggregation
from .phase4_qualification_execution import (
    load_capability_source_states,
    load_two_deployment_carry_bundle,
    load_two_deployment_qualification_plan,
)
from .phase4_qualification_io import (
    acquire_qualification_execution_claim,
    checkpoint_qualification_candidate_state,
    load_private_qualification_contract,
    private_qualification_output,
    private_qualification_output_directory,
)
from .phase4_qualification_runtime import (
    QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD,
    QUALIFICATION_PRIOR_SPEND_MICROUSD,
    AuditedQualificationInterviewerToolExecutor,
    ScopedQualificationTogetherTransport,
    TwoDeploymentQualificationAuthorizationBundle,
    execute_two_deployment_qualification,
    qualification_candidate_state_summary,
    validate_two_deployment_qualification_authorization,
)
from .phase4_qualification_scope import (
    NEW_PROVIDER_CALL_COUNT,
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
)
from .phase4_readiness import (
    TogetherExactTokenCounterSet,
    load_exact_tokenizers,
)
from .phase4_together_live import (
    TogetherCatalogPreflightBundle,
    load_together_api_key,
)
from .validate_phase4_selector_recovery import (
    build_parser as build_public_chain_parser,
    load_selector_recovery_public_inputs,
)


QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD = (
    QUALIFICATION_PRIOR_SPEND_MICROUSD
    + QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
)


class _StrictUTCClock:
    """Return timezone-aware, strictly increasing local receipt times."""

    def __init__(self) -> None:
        self._latest: datetime | None = None

    def __call__(self) -> datetime:
        observed = datetime.now(UTC)
        if self._latest is not None and observed <= self._latest:
            observed = self._latest + timedelta(microseconds=1)
        self._latest = observed
        return observed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the reviewed two-deployment public-development plan "
            "with up to 294 new provider calls. The authorization covers "
            "all 294 exact requests, while frozen stop gates may end an "
            "attempt early."
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
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("private_output_directory", type=Path)
    parser.add_argument(
        "--source-state",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument(
        "--execute-paid-two-deployment-qualification",
        action="store_true",
    )
    parser.add_argument("--confirm-call-count", type=int, required=True)
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
    parser.add_argument(
        "--confirm-cumulative-authorized-max-microusd",
        type=int,
        required=True,
    )
    return parser


def _require_exact_execution_confirmation(args: argparse.Namespace) -> None:
    if (
        not args.execute_paid_two_deployment_qualification
        or args.confirm_call_count != NEW_PROVIDER_CALL_COUNT
        or args.confirm_max_spend_microusd
        != QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
        or args.confirm_cumulative_authorized_max_microusd
        != QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD
    ):
        raise ValueError("paid two-deployment qualification is not confirmed")


def _state_path(output_directory: Path, candidate_id: str) -> Path:
    return output_directory / f"{candidate_id}_qualification_state_v1.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # These literal confirmations are checked before any file, key, or
        # network object is touched.
        _require_exact_execution_confirmation(args)
        output_directory = private_qualification_output_directory(
            args.private_output_directory
        )
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
        authorization = load_private_qualification_contract(
            private_qualification_output(args.authorization_bundle),
            TwoDeploymentQualificationAuthorizationBundle,
        )
        now = datetime.now(UTC)
        validate_two_deployment_qualification_authorization(
            authorization,
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
            now=now,
        )
        state_paths = {
            candidate_id: _state_path(output_directory, candidate_id)
            for candidate_id in authorization.authorized_candidate_ids
        }
        if any(path.exists() for path in state_paths.values()):
            raise ValueError(
                "qualification output state already exists; manual review required"
            )
        counters = load_exact_tokenizers(
            public[8],
            args.tokenizer_cache,
            allow_download=False,
        )
        tool_provider = CapabilityInterviewerTools(
            list(public[14].ontology.item_ids)
        )
        tool_auditor = AuditedQualificationInterviewerToolExecutor(
            tool_provider
        )
        clock = _StrictUTCClock()

        # The durable claim is deliberately the final local action before the
        # credential is loaded and an HTTP client can exist.
        acquire_qualification_execution_claim(
            plan,
            authorization,
            output_directory,
            claimed_at=clock(),
        )
        api_key = load_together_api_key(local_env_file=args.api_key_file)
        with httpx.Client(follow_redirects=False, trust_env=False) as client:
            transport = ScopedQualificationTogetherTransport(
                authorization,
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
                api_key,
                client=client,
                token_counter=TogetherExactTokenCounterSet(counters),
                tool_executor=tool_auditor,
                now=now,
                clock=clock,
            )
            states = execute_two_deployment_qualification(
                plan,
                authorization,
                carry,
                public[8],
                public[10],
                public[9],
                public[12],
                public[13],
                public[14],
                transport,
                tool_auditor,
                clock=clock,
                checkpoint=lambda candidate_id, state: (
                    checkpoint_qualification_candidate_state(
                        state_paths[candidate_id],
                        state,
                    )
                ),
            )
        summaries = [
            qualification_candidate_state_summary(states[candidate_id])
            for candidate_id in authorization.authorized_candidate_ids
        ]
        print(
            json.dumps(
                {
                    "execution_plan_sha256": authorization.execution_plan_sha256,
                    "authorization_bundle_sha256": (
                        content_sha256(authorization)
                    ),
                    "candidate_states": summaries,
                    "participant_content_present": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
    except (
        OSError,
        RuntimeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
        httpx.HTTPError,
    ) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
