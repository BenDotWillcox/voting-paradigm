"""Execute one explicitly authorized paid candidate capability plan."""

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
from .phase4_capability import (
    CapabilityInterviewerTools,
    TogetherCapabilityPlan,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
    candidate_capability_state_summary,
    candidate_plan_for,
    execute_candidate_capability_preflight,
    load_capability_source_attempts,
    validate_candidate_capability_authorization_bundle,
    validate_capability_continuation_plan,
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()


def _private_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("candidate capability state must stay under private_runs")
    return resolved


def _checkpoint(
    path: Path,
    state: TogetherCandidateCapabilityExecutionState,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        f"{state.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one five-call public-development capability plan."
    )
    parser.add_argument("continuation", type=Path)
    parser.add_argument("historical_plan", type=Path)
    parser.add_argument("corrected_plan", type=Path)
    parser.add_argument("historical_suite", type=Path)
    parser.add_argument("corrected_suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("historical_readiness", type=Path)
    parser.add_argument("corrected_readiness", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("catalog_preflight_bundle", type=Path)
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("candidate_id")
    parser.add_argument("state_output", type=Path)
    parser.add_argument(
        "--attempt",
        action="append",
        nargs=2,
        metavar=("AUTHORIZATION", "STATE"),
        required=True,
    )
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument(
        "--execute-paid-candidate-capability",
        action="store_true",
    )
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.execute_paid_candidate_capability:
            raise ValueError("paid candidate capability execution is not confirmed")
        state_output = _private_output(args.state_output)
        continuation = TogetherCapabilityContinuationPlan.model_validate_json(
            args.continuation.read_text(encoding="utf-8")
        )
        historical_plan = TogetherCapabilityPlan.model_validate_json(
            args.historical_plan.read_text(encoding="utf-8")
        )
        corrected_plan = TogetherCapabilityPlan.model_validate_json(
            args.corrected_plan.read_text(encoding="utf-8")
        )
        attempts = load_capability_source_attempts(
            [
                (Path(authorization), Path(state))
                for authorization, state in args.attempt
            ]
        )
        historical_suite = load_together_suite(args.historical_suite)
        suite = load_together_suite(args.corrected_suite)
        profile = load_phase4_robustness_profile(args.profile)
        historical_readiness = load_readiness_bundle(args.historical_readiness)
        readiness = load_readiness_bundle(args.corrected_readiness)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        validate_capability_continuation_plan(
            continuation,
            historical_plan,
            corrected_plan,
            attempts,
            historical_suite,
            suite,
            profile,
            historical_readiness,
            readiness,
            fixture,
            session,
            semantic_map,
        )
        plan = candidate_plan_for(continuation, args.candidate_id)
        if args.confirm_max_spend_microusd != (
            plan.candidate_capability_max_spend_microusd
        ):
            raise ValueError("candidate capability spend confirmation differs")
        catalog = TogetherCatalogPreflightBundle.model_validate_json(
            args.catalog_preflight_bundle.read_text(encoding="utf-8")
        )
        authorization = (
            TogetherCandidateCapabilityAuthorizationBundle.model_validate_json(
                args.authorization_bundle.read_text(encoding="utf-8")
            )
        )
        now = datetime.now(timezone.utc)
        validate_candidate_capability_authorization_bundle(
            authorization,
            continuation,
            plan,
            suite,
            profile,
            readiness,
            catalog,
            now=now,
        )
        prior_state = None
        if state_output.exists():
            prior_state = (
                TogetherCandidateCapabilityExecutionState.model_validate_json(
                    state_output.read_text(encoding="utf-8")
                )
            )
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
            else f"candidate_capability_state_{timestamp}"
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
            state = execute_candidate_capability_preflight(
                continuation,
                historical_plan,
                corrected_plan,
                attempts,
                historical_suite,
                historical_readiness,
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
                prior_state=prior_state,
                checkpoint=lambda value: _checkpoint(state_output, value),
            )
        print(
            json.dumps(
                candidate_capability_state_summary(state),
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
