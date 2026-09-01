from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_qualification_attempt import (
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
)
from eval.phase4_qualification_attempt_result import (
    QualificationAttemptV2AggregateReceipt,
    build_qualification_attempt_v2_aggregate_receipt,
    build_qualification_attempt_v2_result,
    validate_qualification_attempt_v2_aggregate_receipt,
    validate_qualification_attempt_v2_result,
)
from eval.phase4_qualification_attempt_runtime import (
    QualificationAttemptV2ExecutionStatus,
    build_qualification_attempt_v2_authorization,
    execute_qualification_attempt_v2,
)
from eval.phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
)
from eval.phase4_readiness import load_readiness_bundle
from eval.phase4_robustness import load_phase4_robustness_profile
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
from eval.phase4_together_live import TogetherAmbiguousDeliveryError
from eval.phase4_two_deployment_result import (
    QualificationCoordinateDisposition,
    QualificationResultStatus,
)
from eval.prequential import load_session_script
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_qualification_runtime import (
    _InvalidFirstOutputTransport,
    _ProviderErrorWithDiagnosticTransport,
    _SyntheticToolAuditor,
)
from eval.tests.test_phase4_selector_recovery import (
    SelectorDeltaTransport,
    _catalog_at,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "eval" / "fixtures"


@pytest.fixture(scope="module")
def result_inputs():
    proof = load_qualification_attempt_v2_source_proof(
        FIXTURES / "preference_eval_phase4_qualification_attempt_source_proof_v2.json"
    )
    plan = load_qualification_attempt_v2_plan(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_attempt_v2.json"
    )
    suite = load_together_suite(
        FIXTURES / "preference_eval_phase4_together_v6.json"
    )
    readiness = load_readiness_bundle(
        FIXTURES / "preference_eval_phase4_together_readiness_v6.json"
    )
    profile = load_phase4_robustness_profile(
        FIXTURES / "preference_eval_phase4_robustness_v1.json"
    )
    fixture = load_fixture(FIXTURES / "preference_eval_dev_v1.json")
    session = load_session_script(
        FIXTURES / "preference_eval_dev_session_v1.json"
    )
    semantic_map = load_authored_semantic_map(
        FIXTURES / "preference_eval_dev_semantic_map_v1.json"
    )
    scope = load_two_deployment_qualification_scope(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_scope_v1.json"
    )
    approval_time = plan.created_at + timedelta(minutes=5)
    catalog = _catalog_at(suite, approval_time)
    authorization = build_qualification_attempt_v2_authorization(
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
        bundle_id="qualification_attempt_v2_result_authorization_test",
        approval_id="qualification_attempt_v2_result_approval_test",
        approved_at=approval_time,
        expires_at=approval_time + timedelta(hours=1),
    )
    return {
        "proof": proof,
        "plan": plan,
        "suite": suite,
        "readiness": readiness,
        "profile": profile,
        "fixture": fixture,
        "session": session,
        "semantic_map": semantic_map,
        "scope": scope,
        "catalog": catalog,
        "approval_time": approval_time,
        "authorization": authorization,
    }


def _execute(result_inputs, transport):
    return execute_qualification_attempt_v2(
        result_inputs["plan"],
        result_inputs["proof"],
        result_inputs["scope"],
        result_inputs["authorization"],
        result_inputs["suite"],
        result_inputs["profile"],
        result_inputs["readiness"],
        result_inputs["fixture"],
        result_inputs["session"],
        result_inputs["semantic_map"],
        transport,
        _SyntheticToolAuditor(),
        clock=transport.clock,
        checkpoint=lambda *_: None,
    )


def _build(result_inputs, states, *, suffix):
    completed_at = max(
        state.receipt.completed_at
        for state in states.values()
        if state.receipt is not None
    )
    return build_qualification_attempt_v2_result(
        result_inputs["proof"],
        result_inputs["plan"],
        result_inputs["authorization"],
        states,
        result_inputs["scope"],
        result_inputs["suite"],
        result_inputs["readiness"],
        result_inputs["profile"],
        result_inputs["fixture"],
        result_inputs["session"],
        result_inputs["semantic_map"],
        result_inputs["catalog"],
        qualification_id=f"qualification_attempt_v2_{suffix}_test",
        created_at=completed_at + timedelta(seconds=1),
    )


@pytest.fixture(scope="module")
def successful_result(result_inputs):
    clock = TickClock(result_inputs["approval_time"] + timedelta(minutes=1))
    states = _execute(result_inputs, SelectorDeltaTransport(clock))
    return states, _build(result_inputs, states, suffix="success")


def test_attempt_v2_success_selects_with_frozen_banded_policy(
    result_inputs,
    successful_result,
) -> None:
    states, result = successful_result

    validate_qualification_attempt_v2_result(
        result,
        result_inputs["proof"],
        result_inputs["plan"],
        result_inputs["authorization"],
        states,
        result_inputs["scope"],
        result_inputs["suite"],
        result_inputs["readiness"],
        result_inputs["profile"],
        result_inputs["fixture"],
        result_inputs["session"],
        result_inputs["semantic_map"],
        result_inputs["catalog"],
    )
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id is not None
    assert len(result.observations) == 304
    assert all(item.passed_hard_gates for item in result.candidate_results)
    assert all(item.carried_success_count == 0 for item in result.candidate_results)


def test_attempt_v2_one_hard_failure_allows_qualifying_sibling_selection(
    result_inputs,
) -> None:
    clock = TickClock(result_inputs["approval_time"] + timedelta(minutes=1))
    states = _execute(result_inputs, _InvalidFirstOutputTransport(clock))
    result = _build(result_inputs, states, suffix="one_hard_failure")
    failed, passed = result.candidate_results

    assert failed.attempt_status is (
        QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
    )
    assert failed.passed_hard_gates is False
    assert passed.passed_hard_gates is True
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id == passed.candidate_id


class _InvalidFirstPerCandidateTransport(SelectorDeltaTransport):
    def __init__(self, clock):
        super().__init__(clock)
        self._failed_candidates: set[str] = set()

    def _output(self, request):
        candidate_id = request.binding.model_candidate_id
        if candidate_id not in self._failed_candidates:
            self._failed_candidates.add(candidate_id)
            return {"unexpected": "content omitted by diagnostic"}
        return super()._output(request)


def test_attempt_v2_both_substantive_failures_produce_no_winner(
    result_inputs,
) -> None:
    clock = TickClock(result_inputs["approval_time"] + timedelta(minutes=1))
    states = _execute(
        result_inputs,
        _InvalidFirstPerCandidateTransport(clock),
    )
    result = _build(result_inputs, states, suffix="both_hard_failure")

    assert result.status is (
        QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
    )
    assert result.selected_candidate_id is None
    assert all(item.passed_hard_gates is False for item in result.candidate_results)


def test_attempt_v2_global_provider_pause_blocks_selection_and_findings(
    result_inputs,
) -> None:
    clock = TickClock(result_inputs["approval_time"] + timedelta(minutes=1))
    states = _execute(
        result_inputs,
        _ProviderErrorWithDiagnosticTransport(clock, fail_at=1),
    )
    result = _build(result_inputs, states, suffix="provider_pause")
    owner_id, sibling_id = result_inputs["authorization"].authorized_candidate_ids
    by_id = {item.candidate_id: item for item in result.candidate_results}

    assert result.status is (
        QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
    )
    assert result.selected_candidate_id is None
    assert by_id[owner_id].attempt_status is (
        QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
    )
    assert by_id[sibling_id].attempt_status is (
        QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE
    )
    assert by_id[sibling_id].observation_sha256s == []
    assert by_id[sibling_id].p95_latency_ms == 0.0
    assert by_id[sibling_id].qualification_cost_microusd == 0
    assert all(item.hard_failure_reasons == [] for item in by_id.values())
    assert all(item.passed_hard_gates is None for item in by_id.values())


class _AmbiguousFirstTransport(SelectorDeltaTransport):
    def invoke(self, request):
        raise TogetherAmbiguousDeliveryError(
            request.binding.call_id,
            "test_ambiguous_delivery",
        )


def test_attempt_v2_ambiguous_stop_call_is_not_labeled_unattempted(
    result_inputs,
) -> None:
    clock = TickClock(result_inputs["approval_time"] + timedelta(minutes=1))
    states = _execute(result_inputs, _AmbiguousFirstTransport(clock))
    result = _build(result_inputs, states, suffix="ambiguous")
    owner = next(
        item
        for item in states.values()
        if item.status
        is QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
    )
    stop = next(
        item
        for item in result.coordinate_results
        if item.call_id == owner.global_stop_call_id
    )

    assert stop.disposition is QualificationCoordinateDisposition.AMBIGUOUS_DELIVERY
    assert stop.observation_sha256 is None
    assert result.status is (
        QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
    )


def test_attempt_v2_result_and_receipt_tampering_fail_closed(
    result_inputs,
    successful_result,
) -> None:
    states, result = successful_result
    wrong = next(
        item.candidate_id
        for item in result.candidate_results
        if item.candidate_id != result.selected_candidate_id
    )
    tampered = result.model_copy(update={"selected_candidate_id": wrong})

    with pytest.raises(ValueError, match="does not rebuild"):
        validate_qualification_attempt_v2_result(
            tampered,
            result_inputs["proof"],
            result_inputs["plan"],
            result_inputs["authorization"],
            states,
            result_inputs["scope"],
            result_inputs["suite"],
            result_inputs["readiness"],
            result_inputs["profile"],
            result_inputs["fixture"],
            result_inputs["session"],
            result_inputs["semantic_map"],
            result_inputs["catalog"],
        )
    receipt = build_qualification_attempt_v2_aggregate_receipt(
        result,
        receipt_id="qualification_attempt_v2_tamper_receipt_test",
    )
    forged = receipt.model_copy(update={"private_result_sha256": "0" * 64})
    with pytest.raises(ValueError, match="does not rebuild"):
        validate_qualification_attempt_v2_aggregate_receipt(forged, result)


def test_attempt_v2_receipt_omits_planted_payloads_and_private_paths(
    successful_result,
) -> None:
    _, result = successful_result
    marker = "PLANTED_PROVIDER_OUTPUT_MUST_STAY_PRIVATE"
    first = result.observations[0].model_copy(
        update={"parsed_output": {"planted": marker}}
    )
    planted = result.model_copy(
        update={"observations": [first, *result.observations[1:]]}
    )
    receipt = build_qualification_attempt_v2_aggregate_receipt(
        planted,
        receipt_id="qualification_attempt_v2_privacy_receipt_test",
    )
    serialized = receipt.model_dump_json()

    assert marker not in serialized
    assert '"parsed_output"' not in serialized
    assert '"request_binding"' not in serialized
    assert '"finalization"' not in serialized
    assert '"usage"' not in serialized
    assert "private_runs" not in serialized
    assert QualificationAttemptV2AggregateReceipt.model_validate_json(
        serialized
    ) == receipt
    assert receipt.private_result_sha256 == content_sha256(planted)
