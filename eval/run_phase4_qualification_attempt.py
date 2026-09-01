"""Execute the one-shot paid public-development qualification attempt v2."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256, load_fixture
from .phase4_capability import CapabilityInterviewerTools
from .phase4_qualification_attempt import (
    ATTEMPT_V2_PROVIDER_CALL_COUNT,
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
)
from .phase4_qualification_attempt_runtime import (
    ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD,
    ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD,
    ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD,
    QualificationAttemptV2AuthorizationBundle,
    QualificationAttemptV2TogetherTransport,
    execute_qualification_attempt_v2,
    qualification_attempt_v2_candidate_state_summary,
    validate_qualification_attempt_v2_authorization,
)
from .phase4_qualification_io import (
    acquire_qualification_execution_claim,
    checkpoint_qualification_candidate_state,
    load_private_qualification_contract,
    private_qualification_output,
    private_qualification_output_directory,
)
from .phase4_qualification_runtime import (
    AuditedQualificationInterviewerToolExecutor,
)
from .phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
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
    load_together_api_key,
)
from .prequential import load_session_script


class _StrictUTCClock:
    """Return aware, strictly increasing local receipt times."""

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
            "Execute the exact paired 304-call public-development "
            "qualification attempt v2. Frozen stop gates may end it early."
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
    parser.add_argument("authorization_bundle", type=Path)
    parser.add_argument("private_output_directory", type=Path)
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--execute-paid-qualification-attempt-v2", action="store_true")
    parser.add_argument("--confirm-call-count", type=int, required=True)
    parser.add_argument("--confirm-max-spend-microusd", type=int, required=True)
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
    return parser


def _require_exact_execution_confirmation(args: argparse.Namespace) -> None:
    if (
        not args.execute_paid_qualification_attempt_v2
        or args.confirm_call_count != ATTEMPT_V2_PROVIDER_CALL_COUNT
        or args.confirm_max_spend_microusd
        != ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
        or args.confirm_prior_actual_spend_microusd
        != ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
        or args.confirm_cumulative_authorized_max_microusd
        != ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
    ):
        raise ValueError("paid qualification attempt v2 is not confirmed")


def _state_path(output_directory: Path, candidate_id: str) -> Path:
    return output_directory / f"{candidate_id}_qualification_attempt_state_v2.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Literal confirmations precede every file, key, and network object.
        _require_exact_execution_confirmation(args)
        output_directory = private_qualification_output_directory(
            args.private_output_directory
        )
        catalog_path = private_qualification_output(
            args.catalog_preflight_bundle
        )
        authorization_path = private_qualification_output(
            args.authorization_bundle
        )
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
        authorization = load_private_qualification_contract(
            authorization_path,
            QualificationAttemptV2AuthorizationBundle,
        )
        now = datetime.now(UTC)
        validate_qualification_attempt_v2_authorization(
            authorization,
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
            now=now,
        )
        state_paths = {
            candidate_id: _state_path(output_directory, candidate_id)
            for candidate_id in authorization.authorized_candidate_ids
        }
        if any(path.exists() for path in state_paths.values()):
            raise ValueError(
                "qualification attempt state exists; manual review required"
            )
        counters = load_exact_tokenizers(
            suite,
            args.tokenizer_cache,
            allow_download=False,
        )
        tool_auditor = AuditedQualificationInterviewerToolExecutor(
            CapabilityInterviewerTools(list(semantic_map.ontology.item_ids))
        )
        clock = _StrictUTCClock()

        # This durable claim is the final local action before credential load
        # and before an HTTP client can exist.
        acquire_qualification_execution_claim(
            plan,
            authorization,
            output_directory,
            claimed_at=clock(),
        )
        api_key = load_together_api_key(local_env_file=args.api_key_file)
        with httpx.Client(follow_redirects=False, trust_env=False) as client:
            transport = QualificationAttemptV2TogetherTransport(
                authorization,
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
                api_key,
                client=client,
                token_counter=TogetherExactTokenCounterSet(counters),
                tool_executor=tool_auditor,
                now=now,
                clock=clock,
            )
            states = execute_qualification_attempt_v2(
                plan,
                proof,
                scope,
                authorization,
                suite,
                profile,
                readiness,
                fixture,
                session,
                semantic_map,
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
            qualification_attempt_v2_candidate_state_summary(state)
            for state in states.values()
        ]
        status_counts = Counter(item["status"] for item in summaries)
        print(
            json.dumps(
                {
                    "execution_plan_sha256": content_sha256(plan),
                    "authorization_bundle_sha256": content_sha256(
                        authorization
                    ),
                    "candidate_state_count": len(summaries),
                    "status_counts": dict(sorted(status_counts.items())),
                    "completed_call_count": sum(
                        int(item["completed_call_count"])
                        for item in summaries
                    ),
                    "provider_spend_microusd": sum(
                        int(item["provider_spend_microusd"])
                        for item in summaries
                    ),
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
