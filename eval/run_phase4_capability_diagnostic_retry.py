"""Execute the explicitly approved one-call Nemotron diagnostic retry."""

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
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_aggregation import load_capability_aggregation
from .phase4_capability_io import (
    acquire_authorization_consumption_claim,
    checkpoint_candidate_state,
    private_capability_output,
    provider_error_diagnostic_path,
    validate_authorization_consumption_claim,
    write_provider_error_diagnostic,
)
from .phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
)
from .phase4_capability_retry import (
    DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD,
    capability_diagnostic_retry_summary,
    execute_capability_diagnostic_retry,
    load_capability_diagnostic_retry_authorization_bundle,
    load_capability_diagnostic_retry_execution_state,
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
    validate_capability_diagnostic_retry_authorization_bundle,
    validate_capability_diagnostic_retry_execution_state,
)
from .phase4_readiness import (
    TogetherExactTokenCounterSet,
    load_exact_tokenizers,
    load_readiness_bundle,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_selector_recovery import load_selector_recovery_delta
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .phase4_together_live import (
    TogetherCatalogPreflightBundle,
    TogetherHTTPTransport,
    load_together_api_key,
)
from .prequential import load_session_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute exactly one public-development Nemotron diagnostic retry."
        )
    )
    parser.add_argument("retry_plan", type=Path)
    parser.add_argument("retry_source_proof", type=Path)
    parser.add_argument("aggregation", type=Path)
    parser.add_argument("delta", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("source_catalog_preflight", type=Path)
    parser.add_argument("catalog_preflight", type=Path)
    parser.add_argument("source_authorization", type=Path)
    parser.add_argument("source_state", type=Path)
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("state_output", type=Path)
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--execute-paid-diagnostic-retry", action="store_true")
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.execute_paid_diagnostic_retry:
            raise ValueError("paid diagnostic retry execution is not confirmed")
        if (
            args.confirm_max_spend_microusd
            != DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
        ):
            raise ValueError("diagnostic retry spend confirmation differs")
        state_output = private_capability_output(args.state_output)
        source_authorization_path = private_capability_output(
            args.source_authorization
        )
        source_state_path = private_capability_output(args.source_state)
        authorization_bundle_path = private_capability_output(
            args.authorization_bundle
        )
        plan = load_capability_diagnostic_retry_plan(args.retry_plan)
        proof = load_capability_diagnostic_retry_source_proof(
            args.retry_source_proof
        )
        aggregation = load_capability_aggregation(args.aggregation)
        delta = load_selector_recovery_delta(args.delta)
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        readiness = load_readiness_bundle(args.readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        source_catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.source_catalog_preflight.read_text(encoding="utf-8")
        )
        fresh_catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight.read_text(encoding="utf-8")
        )
        source_authorization = (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                source_authorization_path.read_text(encoding="utf-8")
            )
        )
        source_state = TogetherDeltaCandidateExecutionState.model_validate_json(
            source_state_path.read_text(encoding="utf-8")
        )
        authorization = (
            load_capability_diagnostic_retry_authorization_bundle(
                authorization_bundle_path
            )
        )
        if state_output.exists():
            existing = load_capability_diagnostic_retry_execution_state(
                state_output
            )
            validate_capability_diagnostic_retry_execution_state(
                existing,
                plan,
                proof,
                authorization,
                source_state,
                suite,
                profile,
            )
            validate_authorization_consumption_claim(
                plan,
                authorization,
                state_output,
            )
            if existing.provider_error_diagnostic is not None:
                write_provider_error_diagnostic(
                    provider_error_diagnostic_path(state_output),
                    existing.provider_error_diagnostic,
                )
            print(
                json.dumps(
                    capability_diagnostic_retry_summary(existing),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        now = datetime.now(timezone.utc)
        validate_capability_diagnostic_retry_authorization_bundle(
            authorization,
            plan,
            proof,
            suite,
            profile,
            readiness,
            fresh_catalog,
            now=now,
        )
        acquire_authorization_consumption_claim(
            plan,
            authorization,
            state_output,
            claimed_at=now,
        )
        counters = load_exact_tokenizers(
            suite,
            args.tokenizer_cache,
            allow_download=False,
        )
        api_key = load_together_api_key(local_env_file=args.api_key_file)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        with httpx.Client(follow_redirects=False, trust_env=False) as client:
            transport = TogetherHTTPTransport(
                suite,
                profile,
                fresh_catalog,
                readiness.token_readiness_receipt,
                readiness.headroom_policy,
                authorization.live_authorization,
                api_key,
                client=client,
                token_counter=TogetherExactTokenCounterSet(counters),
                now=now,
            )
            state = execute_capability_diagnostic_retry(
                plan,
                proof,
                authorization,
                aggregation,
                delta,
                corrected_plan,
                suite,
                profile,
                readiness,
                fixture,
                session,
                semantic_map,
                source_catalog,
                fresh_catalog,
                source_authorization,
                source_state,
                transport,
                state_id=f"nemotron_diagnostic_retry_state_{timestamp}",
                clock=lambda: datetime.now(timezone.utc),
                checkpoint=lambda value: checkpoint_candidate_state(
                    state_output,
                    value,
                ),
            )
        if state.provider_error_diagnostic is not None:
            write_provider_error_diagnostic(
                provider_error_diagnostic_path(state_output),
                state.provider_error_diagnostic,
            )
        print(
            json.dumps(
                capability_diagnostic_retry_summary(state),
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
