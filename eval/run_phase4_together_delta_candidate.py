"""Execute one candidate's exact reviewed capability-delta subset."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_capability import CapabilityInterviewerTools, TogetherCapabilityPlan
from .phase4_capability_io import (
    checkpoint_candidate_state,
    private_capability_output,
    validation_diagnostic_path,
    write_validation_diagnostic,
)
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    delta_candidate_plan_for,
    delta_candidate_state_summary,
    execute_delta_candidate_capability_preflight,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
    validate_capability_delta_execution_inputs,
    validate_delta_candidate_authorization_bundle,
)
from .phase4_readiness import (
    TogetherExactTokenCounterSet,
    load_exact_tokenizers,
    load_readiness_bundle,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .phase4_together_live import (
    TogetherCatalogPreflightBundle,
    TogetherHTTPTransport,
    TogetherInterviewerToolExecutor,
    load_together_api_key,
)
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one reviewed capability role-delta subset."
    )
    parser.add_argument("delta", type=Path)
    parser.add_argument("source_proof", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("candidate_id")
    parser.add_argument("state_output", type=Path)
    parser.add_argument(
        "--prior-authorization",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument(
        "--prior-state",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--execute-paid-delta-capability", action="store_true")
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.execute_paid_delta_capability:
            raise ValueError("paid delta capability execution is not confirmed")
        state_output = private_capability_output(args.state_output)
        diagnostic_output = private_capability_output(
            validation_diagnostic_path(state_output)
        )
        delta = load_capability_delta_plan(args.delta)
        source_proof = load_capability_delta_source_proof(args.source_proof)
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.corrected_readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(args.development_semantic_map)
        validate_capability_delta_execution_inputs(
            delta,
            source_proof,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            args.candidate_id,
        )
        if (
            args.confirm_max_spend_microusd
            != plan.candidate_capability_max_spend_microusd
        ):
            raise ValueError("delta capability spend confirmation differs")
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight_bundle.read_text(encoding="utf-8")
        )
        authorization = (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                args.authorization_bundle.read_text(encoding="utf-8")
            )
        )
        if len(args.prior_authorization) != len(args.prior_state):
            raise ValueError("prior delta authorization/state counts differ")
        prior_attempts = [
            (
                TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                    authorization_path.read_text(encoding="utf-8")
                ),
                TogetherDeltaCandidateExecutionState.model_validate_json(
                    state_path.read_text(encoding="utf-8")
                ),
            )
            for authorization_path, state_path in zip(
                args.prior_authorization,
                args.prior_state,
                strict=True,
            )
        ]
        now = datetime.now(timezone.utc)
        validate_delta_candidate_authorization_bundle(
            authorization,
            delta,
            source_proof,
            plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog,
            prior_attempts=prior_attempts,
            now=now,
        )
        prior_state = None
        if state_output.exists():
            prior_state = TogetherDeltaCandidateExecutionState.model_validate_json(
                state_output.read_text(encoding="utf-8")
            )
        elif diagnostic_output.exists():
            raise ValueError("candidate diagnostic exists without execution state")
        counters = load_exact_tokenizers(
            suite,
            args.tokenizer_cache,
            allow_download=False,
        )
        api_key = load_together_api_key(local_env_file=args.api_key_file)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        state_id = (
            prior_state.state_id
            if prior_state is not None
            else f"delta_candidate_state_{timestamp}"
        )
        tool_provider = CapabilityInterviewerTools(
            list(semantic_map.ontology.item_ids)
        )
        with httpx.Client(follow_redirects=False, trust_env=False) as client:
            transport = TogetherHTTPTransport(
                suite,
                profile,
                catalog,
                readiness.token_readiness_receipt,
                readiness.headroom_policy,
                authorization.live_authorization,
                api_key,
                client=client,
                token_counter=TogetherExactTokenCounterSet(counters),
                tool_executor=TogetherInterviewerToolExecutor(tool_provider),
                now=now,
            )
            state = execute_delta_candidate_capability_preflight(
                delta,
                source_proof,
                corrected_plan,
                plan,
                authorization,
                suite,
                profile,
                readiness,
                fixture,
                session,
                semantic_map,
                catalog,
                transport,
                state_id=state_id,
                ledger_id=f"{state_id}_ledger",
                journal_id=f"{state_id}_journal",
                clock=lambda: datetime.now(timezone.utc),
                prior_attempts=prior_attempts,
                prior_state=prior_state,
                checkpoint=lambda value: checkpoint_candidate_state(
                    state_output,
                    value,
                ),
                validation_diagnostic_sink=lambda value: (
                    write_validation_diagnostic(diagnostic_output, value)
                ),
            )
        print(
            json.dumps(
                delta_candidate_state_summary(state),
                indent=2,
                sort_keys=True,
            )
        )
    except (
        OSError,
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
