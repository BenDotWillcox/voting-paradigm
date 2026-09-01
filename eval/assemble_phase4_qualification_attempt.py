"""Assemble qualification-attempt-v2 results without network access or spend."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import aware_datetime_arg, safe_authoring_error
from .fixture_io import load_fixture
from .phase4_qualification_attempt import (
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
)
from .phase4_qualification_attempt_result import (
    build_qualification_attempt_v2_aggregate_receipt,
    build_qualification_attempt_v2_result,
    qualification_attempt_v2_result_summary,
    validate_qualification_attempt_v2_aggregate_receipt,
    validate_qualification_attempt_v2_result,
)
from .phase4_qualification_attempt_runtime import (
    QualificationAttemptV2AuthorizationBundle,
    QualificationAttemptV2CandidateState,
)
from .phase4_qualification_io import (
    REPOSITORY_ROOT,
    load_private_qualification_contract,
    private_qualification_output,
    private_qualification_output_directory,
    validate_qualification_execution_claim,
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
            "Validate both terminal attempt-v2 audits and assemble one private "
            "result plus a tracked-eligible aggregate receipt. This command "
            "makes no provider request and spends nothing."
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
    parser.add_argument("private_result_output", type=Path)
    parser.add_argument("aggregate_receipt_output", type=Path)
    parser.add_argument(
        "--candidate-state",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--qualification-id", required=True)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--created-at", type=aware_datetime_arg, required=True)
    return parser


def tracked_qualification_attempt_receipt_output(path: Path) -> Path:
    resolved = path.resolve()
    expected_parent = (REPOSITORY_ROOT / "eval" / "review_summaries").resolve()
    if resolved.parent != expected_parent:
        raise ValueError(
            "qualification attempt receipt must stay in review_summaries"
        )
    return resolved


def _require_new_distinct_outputs(
    private_result: Path,
    aggregate_receipt: Path,
    inputs: Sequence[Path],
) -> None:
    resolved_inputs = {item.resolve() for item in inputs}
    if (
        private_result == aggregate_receipt
        or private_result in resolved_inputs
        or aggregate_receipt in resolved_inputs
    ):
        raise ValueError("qualification attempt result would overwrite an input")
    if private_result.exists() or aggregate_receipt.exists():
        raise ValueError("qualification attempt result output already exists")


def _write_once(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{payload}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(
            "qualification attempt result output already exists"
        ) from error


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_directory = private_qualification_output_directory(
            args.private_output_directory
        )
        private_result = private_qualification_output(
            args.private_result_output
        )
        if private_result.parent != run_directory:
            raise ValueError(
                "qualification attempt private result must stay in its run directory"
            )
        receipt_output = tracked_qualification_attempt_receipt_output(
            args.aggregate_receipt_output
        )
        candidate_paths = [
            private_qualification_output(path) for path in args.candidate_state
        ]
        if any(path.parent != run_directory for path in candidate_paths):
            raise ValueError(
                "qualification attempt states must stay in their run directory"
            )
        input_paths = [
            value
            for name, value in vars(args).items()
            if name
            not in {
                "private_result_output",
                "aggregate_receipt_output",
                "candidate_state",
            }
            and isinstance(value, Path)
        ]
        _require_new_distinct_outputs(
            private_result,
            receipt_output,
            [*input_paths, *candidate_paths],
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
        catalog = load_private_qualification_contract(
            args.catalog_preflight_bundle,
            TogetherCatalogPreflightBundle,
        )
        authorization = load_private_qualification_contract(
            args.authorization_bundle,
            QualificationAttemptV2AuthorizationBundle,
        )
        candidate_states = [
            load_private_qualification_contract(
                path,
                QualificationAttemptV2CandidateState,
            )
            for path in candidate_paths
        ]
        states = {item.candidate_id: item for item in candidate_states}
        if len(states) != len(candidate_states):
            raise ValueError("qualification attempt candidate states are duplicated")
        validate_qualification_execution_claim(
            plan,
            authorization,
            run_directory,
        )
        result = build_qualification_attempt_v2_result(
            proof,
            plan,
            authorization,
            states,
            scope,
            suite,
            readiness,
            profile,
            fixture,
            session,
            semantic_map,
            catalog,
            qualification_id=args.qualification_id,
            created_at=args.created_at,
        )
        validate_qualification_attempt_v2_result(
            result,
            proof,
            plan,
            authorization,
            states,
            scope,
            suite,
            readiness,
            profile,
            fixture,
            session,
            semantic_map,
            catalog,
        )
        receipt = build_qualification_attempt_v2_aggregate_receipt(
            result,
            receipt_id=args.receipt_id,
        )
        validate_qualification_attempt_v2_aggregate_receipt(receipt, result)
        _write_once(private_result, result.model_dump_json(indent=2))
        _write_once(receipt_output, receipt.model_dump_json(indent=2))
        print(
            json.dumps(
                qualification_attempt_v2_result_summary(result),
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
