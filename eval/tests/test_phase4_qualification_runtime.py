from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from eval.fixture_io import content_sha256
from eval.phase4_capability import CapabilityInterviewerTools
from eval.phase4_provider import (
    ProviderCallOutcome,
    ProviderDataScope,
    provider_committed_totals,
    provider_request_content_sha256,
)
from eval.phase4_qualification_execution import (
    QualificationCallDisposition,
    QualificationCarryRecord,
    TwoDeploymentQualificationCarryBundle,
    build_two_deployment_qualification_plan,
)
from eval.phase4_qualification_runtime import (
    AuditedQualificationInterviewerToolExecutor,
    QualificationExecutionStatus,
    QualificationOutputRecord,
    QualificationToolReplayRecord,
    ScopedQualificationTogetherTransport,
    build_two_deployment_qualification_authorization,
    execute_two_deployment_qualification,
    validate_two_deployment_candidate_state,
    validate_two_deployment_qualification_authorization,
)
from eval.phase4_readiness import rebuild_qualification_call
from eval.phase4_robustness import BudgetSegment, LLMRole
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_qualification_scope import _tracked_inputs
from eval.tests.test_phase4_selector_recovery import (
    SelectorDeltaTransport,
    _catalog_at,
    _public_inputs,
)


APPROVAL_TIME = datetime(2026, 8, 28, 1, 6, tzinfo=timezone.utc)


def _synthetic_carry_bundle(plan, scope, proof, aggregation, public):
    records = []
    for candidate_plan in plan.candidate_plans:
        state_sha256 = content_sha256(
            {"candidate_id": candidate_plan.candidate_id, "source": "test"}
        )
        for call in candidate_plan.calls:
            if call.disposition is not QualificationCallDisposition.CARRIED_SUCCESS:
                continue
            output_payload = {
                "candidate_id": call.candidate_id,
                "role": call.role.value,
                "call_id": call.call_id,
            }
            output_sha256 = content_sha256(output_payload)
            digest = content_sha256(
                {
                    "candidate_id": call.candidate_id,
                    "role": call.role.value,
                    "ordinal": call.source_manifest_ordinal,
                }
            )
            records.append(
                QualificationCarryRecord(
                    candidate_id=call.candidate_id,
                    role=call.role,
                    call_id=call.call_id,
                    source_manifest_ordinal=call.source_manifest_ordinal,
                    source_entry_sha256=call.source_entry_sha256,
                    corrected_capability_call_sha256=digest,
                    aggregation_role_evidence_sha256=digest,
                    source_state_schema_version="synthetic_test_state.v1",
                    source_state_sha256=state_sha256,
                    source_authorization_sha256=digest,
                    source_provider_ledger_sha256=digest,
                    source_provider_journal_sha256=digest,
                    request_binding_sha256=digest,
                    provider_authorization_sha256=digest,
                    provider_usage_sha256=digest,
                    finalization_sha256=digest,
                    source_output_sha256=output_sha256,
                    current_response_schema_sha256=digest,
                    current_response_validator_sha256=digest,
                    current_revalidated_output_sha256=output_sha256,
                    output_payload=output_payload,
                    tool_call_count=(
                        1 if call.role is LLMRole.INTERVIEWER else 0
                    ),
                )
            )
    records.sort(key=lambda item: (item.candidate_id, item.source_manifest_ordinal))
    return TwoDeploymentQualificationCarryBundle(
        bundle_id="synthetic_two_deployment_carry_test",
        created_at=APPROVAL_TIME - timedelta(minutes=1),
        execution_plan_sha256=content_sha256(plan),
        qualification_scope_sha256=content_sha256(scope),
        qualification_scope_evidence_proof_sha256=content_sha256(proof),
        capability_aggregation_sha256=content_sha256(aggregation),
        corrected_capability_plan_sha256=content_sha256(public[7]),
        together_suite_sha256=content_sha256(public[8]),
        robustness_profile_sha256=content_sha256(public[10]),
        readiness_sha256=content_sha256(public[9]),
        development_fixture_sha256=content_sha256(public[12]),
        development_session_sha256=content_sha256(public[13]),
        development_semantic_map_sha256=content_sha256(public[14]),
        source_state_sha256s=sorted(
            {item.source_state_sha256 for item in records}
        ),
        records=records,
    )


@pytest.fixture(scope="module")
def runtime_inputs():
    scope, proof, aggregation, *_, suite, readiness, profile, _ = _tracked_inputs()
    public = _public_inputs()
    plan = build_two_deployment_qualification_plan(
        scope,
        proof,
        readiness,
        plan_id="two_deployment_runtime_test",
        created_at=APPROVAL_TIME - timedelta(minutes=2),
    )
    carry = _synthetic_carry_bundle(plan, scope, proof, aggregation, public)
    catalog = _catalog_at(suite, APPROVAL_TIME)
    with patch(
        "eval.phase4_qualification_runtime."
        "validate_two_deployment_carry_bundle"
    ):
        authorization = build_two_deployment_qualification_authorization(
            scope,
            proof,
            plan,
            carry,
            aggregation,
            public[7],
            suite,
            profile,
            readiness,
            public[12],
            public[13],
            public[14],
            [],
            catalog,
            bundle_id="two_deployment_runtime_authorization_test",
            approval_id="two_deployment_runtime_approval_test",
            approved_at=APPROVAL_TIME,
            expires_at=APPROVAL_TIME + timedelta(hours=1),
        )
    return {
        "scope": scope,
        "proof": proof,
        "aggregation": aggregation,
        "corrected_capability_plan": public[7],
        "suite": suite,
        "readiness": readiness,
        "profile": profile,
        "fixture": public[12],
        "session": public[13],
        "semantic_map": public[14],
        "plan": plan,
        "carry": carry,
        "catalog": catalog,
        "authorization": authorization,
    }


def test_exact_authorization_rebuilds_all_294_noncarried_calls(
    runtime_inputs,
) -> None:
    authorization = runtime_inputs["authorization"]
    plan = runtime_inputs["plan"]
    carry = runtime_inputs["carry"]

    assert len(authorization.authorized_requests) == 294
    assert sum(
        item.authorized_max_cost_microusd
        for item in authorization.authorized_requests
    ) == 2_297_400
    assert [
        item.source_manifest_ordinal
        for item in authorization.authorized_requests
    ] == [*range(16, 310)]
    assert not (
        {item.call_id for item in authorization.authorized_requests}
        & {item.call_id for item in carry.records}
    )
    assert {item.call_id for item in authorization.authorized_requests} == {
        call.call_id
        for candidate in plan.candidate_plans
        for call in candidate.calls
        if call.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    }

    with patch(
        "eval.phase4_qualification_runtime."
        "validate_two_deployment_carry_bundle"
    ):
        validate_two_deployment_qualification_authorization(
            authorization,
            runtime_inputs["scope"],
            runtime_inputs["proof"],
            plan,
            carry,
            runtime_inputs["aggregation"],
            runtime_inputs["corrected_capability_plan"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
            runtime_inputs["readiness"],
            runtime_inputs["fixture"],
            runtime_inputs["session"],
            runtime_inputs["semantic_map"],
            [],
            runtime_inputs["catalog"],
            now=APPROVAL_TIME + timedelta(minutes=1),
        )


def test_exact_authorization_rejects_request_hash_tampering(runtime_inputs) -> None:
    authorization = runtime_inputs["authorization"]
    requests = list(authorization.authorized_requests)
    requests[17] = requests[17].model_copy(
        update={"request_content_sha256": "0" * 64}
    )
    tampered = authorization.model_copy(update={"authorized_requests": requests})

    with patch(
        "eval.phase4_qualification_runtime."
        "validate_two_deployment_carry_bundle"
    ), pytest.raises(ValueError, match="exact requests do not rebuild"):
        validate_two_deployment_qualification_authorization(
            tampered,
            runtime_inputs["scope"],
            runtime_inputs["proof"],
            runtime_inputs["plan"],
            runtime_inputs["carry"],
            runtime_inputs["aggregation"],
            runtime_inputs["corrected_capability_plan"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
            runtime_inputs["readiness"],
            runtime_inputs["fixture"],
            runtime_inputs["session"],
            runtime_inputs["semantic_map"],
            [],
            runtime_inputs["catalog"],
            now=APPROVAL_TIME + timedelta(minutes=1),
        )


def _uninitialized_scoped_transport(runtime_inputs):
    authorization = runtime_inputs["authorization"]
    suite = runtime_inputs["suite"]
    transport = object.__new__(ScopedQualificationTogetherTransport)
    transport._authorization = authorization.model_copy(deep=True)
    transport._profile_sha256 = content_sha256(runtime_inputs["profile"])
    transport._price_cards = {
        item.candidate.candidate_id: item.price_card
        for item in suite.candidates
        if item.candidate.candidate_id in authorization.authorized_candidate_ids
    }
    transport._exact = {
        item.call_id: item for item in authorization.authorized_requests
    }
    transport._clock = lambda: APPROVAL_TIME + timedelta(minutes=1)
    transport._core = SimpleNamespace(
        count_initial_payload=lambda request: SimpleNamespace(
            input_token_count=0
        )
    )
    return transport


def _first_new_request(runtime_inputs):
    first = runtime_inputs["authorization"].authorized_requests[0]
    entry = next(
        item
        for item in runtime_inputs["readiness"].qualification_manifest.entries
        if item.coordinate.ordinal == first.source_manifest_ordinal
    )
    return rebuild_qualification_call(
        runtime_inputs["suite"],
        runtime_inputs["profile"],
        runtime_inputs["fixture"],
        runtime_inputs["session"],
        runtime_inputs["semantic_map"],
        entry,
        created_at=APPROVAL_TIME + timedelta(seconds=1),
    ).request


def test_scoped_transport_requires_public_exact_request(runtime_inputs) -> None:
    transport = _uninitialized_scoped_transport(runtime_inputs)
    request = _first_new_request(runtime_inputs)

    transport.validate_execution(request, segment=BudgetSegment.QUALIFICATION)

    private_request = request.model_copy(
        update={
            "binding": request.binding.model_copy(
                update={
                    "data_scope": ProviderDataScope.PSEUDONYMOUS_PARTICIPANT
                }
            )
        }
    )
    with pytest.raises(ValueError, match="not public development"):
        transport.validate_execution(
            private_request,
            segment=BudgetSegment.QUALIFICATION,
        )

    wrong_request = request.model_copy(
        update={
            "binding": request.binding.model_copy(
                update={"call_id": "qualification_unapproved_call"}
            )
        }
    )
    with pytest.raises(ValueError, match="not exactly authorized"):
        transport.validate_execution(
            wrong_request,
            segment=BudgetSegment.QUALIFICATION,
        )


def test_tool_auditor_replays_deterministic_result_and_binds_payloads() -> None:
    auditor = AuditedQualificationInterviewerToolExecutor(
        CapabilityInterviewerTools(["item_a", "item_b"])
    )
    auditor.begin_call("qualification_interviewer_tool_test")
    result = auditor.execute("read_evidence_coverage", {})
    records = auditor.end_call()

    assert len(records) == 1
    assert records[0].replay_matches is True
    assert records[0].result_payload == result
    assert records[0].replay_result_payload == result
    assert records[0].result_sha256 == content_sha256(result)


class _SyntheticToolAuditor:
    def __init__(self) -> None:
        self.active_call_id: str | None = None

    def begin_call(self, call_id: str) -> None:
        assert self.active_call_id is None
        self.active_call_id = call_id

    def end_call(self) -> list[QualificationToolReplayRecord]:
        call_id = self.active_call_id
        assert call_id is not None
        self.active_call_id = None
        arguments = {"record_version": "read_evidence_coverage_request.v1"}
        result = {
            "record_version": "read_evidence_coverage_result.v1",
            "evidence_count": 0,
        }
        return [
            QualificationToolReplayRecord(
                call_id=call_id,
                tool_call_index=1,
                tool_name="read_evidence_coverage",
                arguments_sha256=content_sha256(arguments),
                result_sha256=content_sha256(result),
                replay_result_sha256=content_sha256(result),
                arguments_payload=arguments,
                result_payload=result,
                replay_result_payload=result,
            )
        ]


def _execute(runtime_inputs, transport):
    clock = transport.clock
    checkpoints = []
    states = execute_two_deployment_qualification(
        runtime_inputs["plan"],
        runtime_inputs["authorization"],
        runtime_inputs["carry"],
        runtime_inputs["suite"],
        runtime_inputs["profile"],
        runtime_inputs["readiness"],
        runtime_inputs["fixture"],
        runtime_inputs["session"],
        runtime_inputs["semantic_map"],
        transport,
        _SyntheticToolAuditor(),
        clock=clock,
        checkpoint=lambda candidate_id, state: checkpoints.append(
            (candidate_id, state)
        ),
    )
    return states, checkpoints


class _ProviderErrorWithDiagnosticTransport(SelectorDeltaTransport):
    def invoke(self, request):
        result = super().invoke(request)
        if result.outcome is not ProviderCallOutcome.PROVIDER_ERROR:
            return result
        payload = result.model_dump(mode="python")
        payload.update(
            {
                "record_version": "phase4_provider_transport_result.v3",
                "failure_code": "together_http_500",
                "provider_http_error_metadata": {
                    "http_status_code": 500,
                    "envelope_state": "standard",
                    "error_type": "server_error",
                    "error_code": "not_present",
                    "rejected_request_field": "not_present",
                },
            }
        )
        return type(result).model_validate(payload)


def test_full_scripted_294_call_execution_completes_and_audits(
    runtime_inputs,
) -> None:
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, checkpoints = _execute(
        runtime_inputs,
        SelectorDeltaTransport(clock),
    )

    assert set(states) == set(
        runtime_inputs["authorization"].authorized_candidate_ids
    )
    assert sum(len(state.provider_ledger.calls) for state in states.values()) == 294
    assert sum(len(state.outputs) for state in states.values()) == 294
    assert all(
        state.status is QualificationExecutionStatus.COMPLETED
        for state in states.values()
    )
    assert all(len(state.tool_replay_records) == 7 for state in states.values())
    assert len(checkpoints) == 294
    committed = sum(
        provider_committed_totals(state.provider_ledger)[
            BudgetSegment.QUALIFICATION
        ]
        for state in states.values()
    )
    assert 51_042 + committed <= 4_000_000


def test_provider_pause_does_not_suppress_sibling_candidate(runtime_inputs) -> None:
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, _ = _execute(
        runtime_inputs,
        _ProviderErrorWithDiagnosticTransport(clock, fail_at=1),
    )
    first, second = runtime_inputs["authorization"].authorized_candidate_ids

    assert states[first].status is QualificationExecutionStatus.PROVIDER_PAUSED
    assert len(states[first].provider_ledger.calls) == 1
    assert states[second].status is QualificationExecutionStatus.COMPLETED
    assert len(states[second].provider_ledger.calls) == 147

    missing_diagnostic = states[first].model_copy(
        update={"provider_error_diagnostics": []}
    )
    with pytest.raises(ValueError, match="provider diagnostic differs"):
        validate_two_deployment_candidate_state(
            missing_diagnostic,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    provider_diagnostic = states[first].provider_error_diagnostics[0]
    unknown_diagnostic = states[first].model_copy(
        update={
            "provider_error_diagnostics": [
                provider_diagnostic.model_copy(
                    update={"call_id": "unknown_qualification_call"}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="provider diagnostic differs"):
        validate_two_deployment_candidate_state(
            unknown_diagnostic,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )


class _InvalidFirstOutputTransport(SelectorDeltaTransport):
    def _output(self, request):
        if len(self.requests) == 1:
            return {"unexpected": "content omitted by diagnostic"}
        return super()._output(request)


def test_invalid_output_is_candidate_hard_failure_only(runtime_inputs) -> None:
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, _ = _execute(runtime_inputs, _InvalidFirstOutputTransport(clock))
    first, second = runtime_inputs["authorization"].authorized_candidate_ids

    assert states[first].status is (
        QualificationExecutionStatus.CANDIDATE_HARD_FAILURE
    )
    assert states[first].provider_journal.finalizations[-1].outcome is (
        ProviderCallOutcome.INVALID_OUTPUT
    )
    assert len(states[first].validation_diagnostics) == 1
    assert states[second].status is QualificationExecutionStatus.COMPLETED

    diagnostic = states[first].validation_diagnostics[0]
    unknown_diagnostic = states[first].model_copy(
        update={
            "validation_diagnostics": [
                diagnostic.model_copy(
                    update={"call_id": "unknown_qualification_call"}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="validation diagnostic differs"):
        validate_two_deployment_candidate_state(
            unknown_diagnostic,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )


def test_terminal_state_tampering_fails_closed(runtime_inputs) -> None:
    clock = TickClock(APPROVAL_TIME + timedelta(minutes=2))
    states, _ = _execute(runtime_inputs, SelectorDeltaTransport(clock))
    state = states[runtime_inputs["authorization"].authorized_candidate_ids[0]]

    missing_output = state.model_copy(update={"outputs": state.outputs[:-1]})
    with pytest.raises(ValueError, match="outputs do not cover"):
        validate_two_deployment_candidate_state(
            missing_output,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    assert state.receipt is not None
    forged_receipt = state.receipt.model_copy(
        update={
            "provider_spend_microusd": (
                state.receipt.provider_spend_microusd + 1
            )
        }
    )
    receipt_tampered = state.model_copy(update={"receipt": forged_receipt})
    with pytest.raises(ValueError, match="receipt does not rebuild"):
        validate_two_deployment_candidate_state(
            receipt_tampered,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    expired_at = (
        runtime_inputs["authorization"].manual_approval.expires_at
        + timedelta(seconds=1)
    )
    expired_ledger = state.provider_ledger.model_copy(deep=True)
    expired_journal = state.provider_journal.model_copy(deep=True)
    expired_ledger.authorizations[-1] = (
        expired_ledger.authorizations[-1].model_copy(
            update={"created_at": expired_at}
        )
    )
    expired_journal.request_bindings[-1] = (
        expired_journal.request_bindings[-1].model_copy(
            update={"created_at": expired_at}
        )
    )
    post_expiry_tamper = state.model_copy(
        update={
            "provider_ledger": expired_ledger,
            "provider_journal": expired_journal,
        }
    )
    with pytest.raises(ValueError, match="outside the manual approval window"):
        validate_two_deployment_candidate_state(
            post_expiry_tamper,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    mismatched_journal = state.provider_journal.model_copy(deep=True)
    mismatched_journal.request_bindings[-1] = (
        mismatched_journal.request_bindings[-1].model_copy(
            update={
                "created_at": (
                    mismatched_journal.request_bindings[-1].created_at
                    + timedelta(microseconds=1)
                )
            }
        )
    )
    chronology_tamper = state.model_copy(
        update={"provider_journal": mismatched_journal}
    )
    with pytest.raises(ValueError, match="request and authorization times differ"):
        validate_two_deployment_candidate_state(
            chronology_tamper,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    first_output = state.outputs[0]
    forged_output = QualificationOutputRecord.model_construct(
        **{
            **first_output.model_dump(mode="python"),
            "output_sha256": "0" * 64,
        }
    )
    output_tampered = state.model_copy(
        update={"outputs": [forged_output, *state.outputs[1:]]}
    )
    with pytest.raises(ValueError, match="provider audit"):
        validate_two_deployment_candidate_state(
            output_tampered,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    ledger = state.provider_ledger.model_copy(deep=True)
    journal = state.provider_journal.model_copy(deep=True)
    first_binding = journal.request_bindings[0]
    altered_binding = first_binding.model_copy(
        update={"request_seed": first_binding.request_seed + 999}
    )
    journal.request_bindings[0] = altered_binding
    altered_request_sha256 = provider_request_content_sha256(altered_binding)
    altered_authorization = ledger.authorizations[0].model_copy(
        update={"request_sha256": altered_request_sha256}
    )
    ledger.authorizations[0] = altered_authorization
    altered_usage = ledger.calls[0].model_copy(
        update={
            "request_sha256": altered_request_sha256,
            "authorization_sha256": content_sha256(altered_authorization),
        }
    )
    ledger.calls[0] = altered_usage
    journal.finalizations[0] = journal.finalizations[0].model_copy(
        update={
            "request_binding_sha256": content_sha256(altered_binding),
            "authorization_sha256": content_sha256(altered_authorization),
            "usage_sha256": content_sha256(altered_usage),
        }
    )
    assert state.receipt is not None
    altered_receipt = state.receipt.model_copy(
        update={
            "provider_ledger_sha256": content_sha256(ledger),
            "provider_journal_sha256": content_sha256(journal),
        }
    )
    locally_consistent_request_tamper = state.model_copy(
        update={
            "provider_ledger": ledger,
            "provider_journal": journal,
            "receipt": altered_receipt,
        }
    )
    with pytest.raises(
        ValueError,
        match="recorded request differs from exact authorization",
    ):
        validate_two_deployment_candidate_state(
            locally_consistent_request_tamper,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )

    unknown_replay = state.tool_replay_records[0].model_copy(
        update={"call_id": "unknown_qualification_call"}
    )
    replay_tampered = state.model_copy(
        update={
            "tool_replay_records": [
                *state.tool_replay_records,
                unknown_replay,
            ]
        }
    )
    with pytest.raises(ValueError, match="tool replay lacks a finalization"):
        validate_two_deployment_candidate_state(
            replay_tampered,
            runtime_inputs["plan"],
            runtime_inputs["authorization"],
            runtime_inputs["carry"],
            runtime_inputs["suite"],
            runtime_inputs["profile"],
        )
