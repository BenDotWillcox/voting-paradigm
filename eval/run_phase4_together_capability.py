"""Execute the explicitly authorized paid Together capability preflight."""

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
    CAPABILITY_MAX_SPEND_MICROUSD,
    CapabilityInterviewerTools,
    TogetherCapabilityAuthorizationBundle,
    TogetherCapabilityExecutionState,
    TogetherCapabilityPlan,
    capability_state_summary,
    execute_capability_preflight,
    validate_capability_authorization_bundle,
    validate_capability_plan,
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
        raise ValueError("capability state must stay under private_runs")
    return resolved


def _checkpoint(path: Path, state: TogetherCapabilityExecutionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        f"{state.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute exactly 15 paid public-development capability calls."
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
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("state_output", type=Path)
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--execute-paid-capability", action="store_true")
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if (
            not args.execute_paid_capability
            or args.confirm_max_spend_microusd
            != CAPABILITY_MAX_SPEND_MICROUSD
        ):
            raise ValueError("paid capability execution is not confirmed")
        state_output = _private_output(args.state_output)
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
        authorization = TogetherCapabilityAuthorizationBundle.model_validate_json(
            args.authorization_bundle.read_text(encoding="utf-8")
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
        validate_capability_authorization_bundle(
            authorization,
            plan,
            suite,
            profile,
            readiness,
            catalog,
            now=now,
        )
        prior_state = None
        if state_output.exists():
            prior_state = TogetherCapabilityExecutionState.model_validate_json(
                state_output.read_text(encoding="utf-8")
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
            else f"together_capability_state_{timestamp}"
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
            state = execute_capability_preflight(
                plan,
                authorization,
                suite,
                profile,
                readiness,
                fixture,
                session,
                semantic_map,
                transport,
                state_id=state_id,
                ledger_id=f"{state_id}_ledger",
                journal_id=f"{state_id}_journal",
                clock=lambda: datetime.now(timezone.utc),
                prior_state=prior_state,
                checkpoint=lambda value: _checkpoint(state_output, value),
            )
        print(json.dumps(capability_state_summary(state), indent=2, sort_keys=True))
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
