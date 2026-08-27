from __future__ import annotations

from copy import deepcopy
import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pytest

from eval.fixture_io import content_sha256
from eval.phase4_capability_aggregation import (
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from eval.phase4_capability_retry import (
    CapabilityDiagnosticRetryDisposition,
    TogetherCapabilityDiagnosticRetryPlan,
    build_capability_diagnostic_retry_authorization_bundle,
    build_capability_diagnostic_retry_plan,
    build_capability_diagnostic_retry_source_proof,
    capability_diagnostic_retry_summary,
    execute_capability_diagnostic_retry,
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
    validate_capability_diagnostic_retry_plan_public,
    validate_capability_diagnostic_retry_source_proof,
)
from eval.phase4_provider import (
    ProviderCallOutcome,
    ProviderHTTPErrorEnvelopeState,
    ProviderHTTPErrorMetadata,
    ProviderHTTPErrorType,
    ProviderSeedStatus,
    ProviderTransportResult,
    ScriptedProviderTransport,
)
from eval.phase4_robustness import BudgetSegment, LLMRole
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_capability_aggregation import _built_result
from eval.tests.test_phase4_selector_recovery import (
    SelectorDeltaTransport,
    _public_cli_argv,
    _public_inputs,
)
from eval import authorize_phase4_capability_diagnostic_retry as authorize_cli
from eval import prepare_phase4_capability_diagnostic_retry as prepare_cli
from eval import run_phase4_capability_diagnostic_retry as run_cli
from eval import validate_phase4_capability_diagnostic_retry as validate_cli


FIXTURES = Path(__file__).parents[1] / "fixtures"
PLAN_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_diagnostic_retry_v1.json"
)
PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_diagnostic_retry_source_proof_v1.json"
)
AGGREGATION_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_aggregation_v1.json"
)
AGGREGATION_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_aggregation_source_proof_v1.json"
)


class RetrySelectorDeltaTransport(SelectorDeltaTransport):
    def validate_execution(self, request, *, segment) -> None:
        del request
        assert segment is BudgetSegment.RETRY_RESERVE


def _fresh_catalog(source_catalog, *, checked_at):
    authorization = source_catalog.authorization.model_copy(
        update={
            "authorization_id": "fresh_retry_catalog_authorization",
            "approved_at": checked_at - timedelta(seconds=1),
            "expires_at": checked_at + timedelta(minutes=5),
        }
    )
    receipt = source_catalog.receipt.model_copy(
        update={
            "receipt_id": "fresh_retry_catalog_receipt",
            "authorization_sha256": content_sha256(authorization),
            "checked_at": checked_at,
        }
    )
    return source_catalog.model_copy(
        update={
            "bundle_id": "fresh_retry_catalog_bundle",
            "authorization": authorization,
            "receipt": receipt,
        }
    )


def test_tracked_retry_plan_validates_without_private_inputs() -> None:
    plan = load_capability_diagnostic_retry_plan(PLAN_PATH)
    proof = load_capability_diagnostic_retry_source_proof(PROOF_PATH)
    aggregation = load_capability_aggregation(AGGREGATION_PATH)
    aggregation_proof = load_capability_aggregation_source_proof(
        AGGREGATION_PROOF_PATH
    )

    validate_capability_diagnostic_retry_plan_public(
        plan,
        aggregation,
        aggregation_proof,
        *_public_inputs(),
    )
    validate_capability_diagnostic_retry_source_proof(proof, plan)

    assert content_sha256(plan) == (
        "bb357556cd6b67a8f96d2a19e56d537bf511c3a9940dd1fb7072e10c98d0239b"
    )
    assert content_sha256(proof) == (
        "3b0d3de1d85819ea7f233c923cee83600670e289f8bf50df9492695736a4b3cc"
    )
    assert plan.retry_call_count == 1
    assert plan.retry_projected_cost_microusd == 5_096
    assert plan.retry_authorized_max_cost_microusd == 7_200
    assert plan.cumulative_worst_case_spend_microusd == 58_242


@lru_cache(maxsize=1)
def _synthetic_retry_inputs():
    aggregation, aggregation_proof, public_inputs, source_catalog, attempts = (
        _built_result()
    )
    source_authorization, source_state = attempts[-1]
    plan = build_capability_diagnostic_retry_plan(
        aggregation,
        aggregation_proof,
        *public_inputs,
        source_catalog,
        source_authorization,
        source_state,
        plan_id="synthetic_nemotron_http_retry",
        retry_call_id="synthetic_nemotron_http_retry_call",
        created_at=aggregation.created_at + timedelta(seconds=2),
    )
    (
        delta,
        _,
        _,
        _,
        _,
        _,
        _,
        corrected_plan,
        suite,
        readiness,
        profile,
        _,
        fixture,
        session,
        semantic_map,
    ) = public_inputs
    proof = build_capability_diagnostic_retry_source_proof(
        plan,
        aggregation,
        delta,
        corrected_plan,
        suite,
        readiness,
        profile,
        fixture,
        session,
        semantic_map,
        source_catalog,
        source_authorization,
        source_state,
        proof_id="synthetic_nemotron_http_retry_proof",
        validated_at=plan.created_at + timedelta(seconds=1),
    )
    fresh_catalog = _fresh_catalog(
        source_catalog,
        checked_at=proof.validated_at + timedelta(seconds=1),
    )
    approved_at = fresh_catalog.receipt.checked_at + timedelta(seconds=1)
    authorization = build_capability_diagnostic_retry_authorization_bundle(
        plan,
        proof,
        suite,
        profile,
        readiness,
        fresh_catalog,
        bundle_id="synthetic_nemotron_http_retry_authorization",
        approval_id="synthetic_nemotron_http_retry_approval",
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=15),
    )
    return (
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
        approved_at,
    )


def _execute(transport, *, checkpoints=None, prior_state=None):
    (
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
        approved_at,
    ) = _synthetic_retry_inputs()
    clock = TickClock(approved_at + timedelta(seconds=1))
    return execute_capability_diagnostic_retry(
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
        state_id="synthetic_nemotron_http_retry_state",
        clock=clock,
        checkpoint=(checkpoints.append if checkpoints is not None else None),
        prior_state=prior_state,
    )


def test_successful_retry_adds_one_exact_link_without_mutating_source() -> None:
    inputs = _synthetic_retry_inputs()
    source_state = inputs[-2]
    source_payload = deepcopy(source_state.model_dump(mode="json"))
    clock = TickClock(inputs[-1] + timedelta(seconds=1))

    state = _execute(RetrySelectorDeltaTransport(clock))

    assert len(state.provider_ledger.calls) == (
        len(source_state.provider_ledger.calls) + 1
    )
    assert state.provider_ledger.calls[-1].retry_of_call_id == (
        inputs[0].source_call_id
    )
    assert state.disposition is CapabilityDiagnosticRetryDisposition.RETRY_SUCCEEDED
    assert state.retry_output is not None
    assert source_state.model_dump(mode="json") == source_payload
    assert state.model_capability_rejection_recorded is False
    assert state.model_selection_performed is False


def test_repeated_http_400_embeds_only_sanitized_metadata() -> None:
    inputs = _synthetic_retry_inputs()
    completed_at = inputs[-1] + timedelta(seconds=3)
    state = _execute(
        ScriptedProviderTransport(
            [
                ProviderTransportResult(
                    record_version="phase4_provider_transport_result.v3",
                    outcome=ProviderCallOutcome.PROVIDER_ERROR,
                    provider_http_error_metadata=ProviderHTTPErrorMetadata(
                        http_status_code=400,
                        envelope_state=ProviderHTTPErrorEnvelopeState.STANDARD,
                        error_type=ProviderHTTPErrorType.INVALID_REQUEST_ERROR,
                    ),
                    output_payload=None,
                    input_tokens=0,
                    output_tokens=0,
                    provider_request_id=None,
                    provider_request_sent=True,
                    provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
                    latency_ms=5.0,
                    failure_code="together_http_400",
                    completed_at=completed_at,
                )
            ]
        )
    )

    assert state.disposition is (
        CapabilityDiagnosticRetryDisposition.REPEATED_HTTP_400
    )
    assert state.provider_error_diagnostic is not None
    assert state.provider_error_diagnostic.http_status_code == 400
    assert state.retry_provider_spend_microusd == 0
    summary = capability_diagnostic_retry_summary(state)
    assert summary["retry_call_count"] == 1
    assert summary["error_type"] == "invalid_request_error"
    assert "together_nemotron" not in str(summary)


def test_ambiguous_delivery_checkpoints_once_and_never_resends() -> None:
    class AmbiguousTransport:
        def __init__(self) -> None:
            self.call_count = 0

        def validate_execution(self, request, *, segment) -> None:
            del request, segment

        def invoke(self, request):
            del request
            self.call_count += 1
            raise RuntimeError("ambiguous private transport detail")

    transport = AmbiguousTransport()
    checkpoints = []
    with pytest.raises(RuntimeError, match="ambiguous"):
        _execute(transport, checkpoints=checkpoints)

    assert transport.call_count == 1
    assert len(checkpoints) == 1
    pending = checkpoints[0]
    assert pending.disposition is None
    assert len(pending.provider_ledger.authorizations) == (
        len(_synthetic_retry_inputs()[-2].provider_ledger.authorizations) + 1
    )
    resumed = _execute(
        transport,
        checkpoints=checkpoints,
        prior_state=pending,
    )
    assert resumed == pending
    assert transport.call_count == 1


def test_retry_state_rejects_lineage_or_extra_call_tampering() -> None:
    inputs = _synthetic_retry_inputs()
    clock = TickClock(inputs[-1] + timedelta(seconds=1))
    state = _execute(RetrySelectorDeltaTransport(clock))
    payload = state.model_dump(mode="json")
    payload["provider_ledger"]["calls"][-1]["retry_of_call_id"] = (
        "another_source_call"
    )
    with pytest.raises(ValueError, match="does not match its authorization"):
        type(state).model_validate(payload)


def test_retry_plan_cannot_change_request_content() -> None:
    plan = _synthetic_retry_inputs()[0]
    payload = plan.model_dump(mode="json")
    payload["retry_request_content_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="request content differs"):
        TogetherCapabilityDiagnosticRetryPlan.model_validate(payload)


def test_retry_is_bound_to_the_evidence_extractor_only() -> None:
    plan = _synthetic_retry_inputs()[0]

    assert plan.role is LLMRole.EVIDENCE_EXTRACTOR
    assert plan.no_fallback_or_continuation is True
    assert plan.candidate_roster_preserved is True
    assert plan.model_selection_forbidden is True


def test_retry_authorization_requires_fresh_catalog_evidence() -> None:
    inputs = _synthetic_retry_inputs()
    with pytest.raises(ValueError, match="new catalog preflight"):
        build_capability_diagnostic_retry_authorization_bundle(
            inputs[0],
            inputs[1],
            inputs[6],
            inputs[7],
            inputs[8],
            inputs[12],
            bundle_id="historical_catalog_retry_authorization",
            approval_id="historical_catalog_retry_approval",
            approved_at=inputs[1].validated_at + timedelta(seconds=1),
            expires_at=inputs[1].validated_at + timedelta(minutes=15),
        )
    stale_approval = max(
        inputs[1].validated_at,
        inputs[13].receipt.checked_at + timedelta(minutes=31),
    )

    with pytest.raises(ValueError, match="fresh catalog preflight"):
        build_capability_diagnostic_retry_authorization_bundle(
            inputs[0],
            inputs[1],
            inputs[6],
            inputs[7],
            inputs[8],
            inputs[13],
            bundle_id="stale_catalog_retry_authorization",
            approval_id="stale_catalog_retry_approval",
            approved_at=stale_approval,
            expires_at=stale_approval + timedelta(minutes=15),
        )


def test_historical_source_and_fresh_live_catalogs_are_distinct() -> None:
    inputs = _synthetic_retry_inputs()
    plan, authorization = inputs[0], inputs[2]
    source_catalog, fresh_catalog = inputs[12], inputs[13]

    assert content_sha256(source_catalog) != content_sha256(fresh_catalog)
    assert plan.source_catalog_preflight_bundle_sha256 == content_sha256(
        source_catalog
    )
    assert authorization.fresh_catalog_preflight_bundle_sha256 == (
        content_sha256(fresh_catalog)
    )

    clock = TickClock(inputs[-1] + timedelta(seconds=1))
    state = _execute(RetrySelectorDeltaTransport(clock))
    assert state.disposition is CapabilityDiagnosticRetryDisposition.RETRY_SUCCEEDED


def test_prepare_cli_rebuilds_zero_spend_artifacts(
    tmp_path,
    capsys,
) -> None:
    aggregation, aggregation_proof, _, catalog, attempts = _built_result()
    aggregation_path = tmp_path / "aggregation.json"
    aggregation_proof_path = tmp_path / "aggregation_proof.json"
    catalog_path = tmp_path / "catalog.json"
    source_authorization_path = tmp_path / "source_authorization.json"
    source_state_path = tmp_path / "source_state.json"
    output_path = tmp_path / "retry_plan.json"
    proof_output_path = tmp_path / "retry_proof.json"
    aggregation_path.write_text(
        aggregation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    aggregation_proof_path.write_text(
        aggregation_proof.model_dump_json(indent=2),
        encoding="utf-8",
    )
    catalog_path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    source_authorization_path.write_text(
        attempts[-1][0].model_dump_json(indent=2),
        encoding="utf-8",
    )
    source_state_path.write_text(
        attempts[-1][1].model_dump_json(indent=2),
        encoding="utf-8",
    )

    assert prepare_cli.main(
        [
            str(aggregation_path),
            str(aggregation_proof_path),
            *_public_cli_argv(),
            str(catalog_path),
            str(source_authorization_path),
            str(source_state_path),
            str(output_path),
            str(proof_output_path),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert summary["retry_call_count"] == 1
    assert content_sha256(
        load_capability_diagnostic_retry_plan(output_path)
    ) == summary["plan_sha256"]
    assert content_sha256(
        load_capability_diagnostic_retry_source_proof(proof_output_path)
    ) == summary["source_proof_sha256"]
    assert "together_nemotron" not in captured.out


def test_public_validator_cli_is_aggregate_only(capsys) -> None:
    assert validate_cli.main(
        [
            str(PLAN_PATH),
            str(PROOF_PATH),
            str(AGGREGATION_PATH),
            str(AGGREGATION_PROOF_PATH),
            *_public_cli_argv(),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["retry_call_count"] == 1
    assert summary["authorized_max_cost_microusd"] == 7_200
    assert summary["provider_inference_calls_executed"] == 0
    assert "together_nemotron" not in captured.out
    assert "private_runs" not in captured.out


def test_public_validator_rejects_private_path_before_read(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    private_plan = tmp_path / "private_runs" / "planted.json"

    def forbidden_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("public validator read a file before path checks")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    assert validate_cli.main(
        [
            str(private_plan),
            str(PROOF_PATH),
            str(AGGREGATION_PATH),
            str(AGGREGATION_PROOF_PATH),
            *_public_cli_argv(),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "planted" not in captured.err


def test_paid_runner_gates_before_reading_any_artifact(monkeypatch, capsys) -> None:
    def forbidden_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("paid runner read an artifact before approval")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    positional = ["missing.json"] * 17
    assert run_cli.main(
        [
            *positional,
            "--confirm-max-spend-microusd",
            "7200",
        ]
    ) == 1
    assert run_cli.main(
        [
            *positional,
            "--execute-paid-diagnostic-retry",
            "--confirm-max-spend-microusd",
            "7201",
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing" not in captured.err


def test_authorizer_gates_before_reading_any_artifact(monkeypatch, capsys) -> None:
    def forbidden_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("authorizer read an artifact before approval")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    positional = ["missing.json"] * 7
    assert authorize_cli.main(
        [
            *positional,
            "--approve-call-count",
            "2",
            "--approve-max-spend-microusd",
            "7200",
        ]
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing" not in captured.err
