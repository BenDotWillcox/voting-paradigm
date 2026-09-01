from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from eval.fixture_io import load_fixture
from eval.phase4_qualification_attempt import (
    QualificationAttemptStage,
    load_qualification_attempt_v2_plan,
    load_qualification_attempt_v2_source_proof,
)
from eval.phase4_qualification_attempt_runtime import (
    ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD,
    ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD,
    ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD,
    QualificationAttemptV2ExecutionStatus,
    build_qualification_attempt_v2_authorization,
    execute_qualification_attempt_v2,
    validate_qualification_attempt_v2_authorization,
    validate_qualification_attempt_v2_candidate_state,
    validate_qualification_attempt_v2_execution_states,
)
from eval.phase4_provider_semantics import (
    PROVIDER_RESPONSE_READOUT_VALIDATOR_VERSION,
)
from eval.phase4_readiness import (
    load_readiness_bundle,
    rebuild_qualification_call,
)
from eval.phase4_robustness import load_phase4_robustness_profile
from eval.phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
)
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
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
def attempt_inputs():
    proof = load_qualification_attempt_v2_source_proof(
        FIXTURES / "preference_eval_phase4_qualification_attempt_source_proof_v2.json"
    )
    plan = load_qualification_attempt_v2_plan(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_attempt_v2.json"
    )
    scope = load_two_deployment_qualification_scope(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_scope_v1.json"
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
        bundle_id="qualification_attempt_v2_authorization_test",
        approval_id="qualification_attempt_v2_approval_test",
        approved_at=approval_time,
        expires_at=approval_time + timedelta(hours=1),
    )
    return {
        "proof": proof,
        "plan": plan,
        "scope": scope,
        "suite": suite,
        "readiness": readiness,
        "profile": profile,
        "fixture": fixture,
        "session": session,
        "semantic_map": semantic_map,
        "catalog": catalog,
        "approval_time": approval_time,
        "authorization": authorization,
    }


def test_attempt_v2_authorization_rebuilds_exact_paired_surface(
    attempt_inputs,
) -> None:
    authorization = attempt_inputs["authorization"]
    plan = attempt_inputs["plan"]

    assert len(authorization.authorized_requests) == 304
    assert [item.call_id for item in authorization.authorized_requests] == (
        plan.execution_order_call_ids
    )
    assert authorization.prior_actual_spend_microusd == (
        ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    )
    assert authorization.new_authorized_max_spend_microusd == (
        ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
    )
    assert authorization.cumulative_authorized_worst_case_microusd == (
        ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
    )
    calls = {
        item.call_id: item
        for candidate in plan.candidate_plans
        for item in candidate.calls
    }
    assert all(
        calls[call_id].execution_stage
        is QualificationAttemptStage.READOUT_CONFORMANCE
        for call_id in plan.execution_order_call_ids[:4]
    )
    for index, call_id in enumerate(plan.execution_order_call_ids[:4]):
        entry = calls[call_id].source_entry
        rebuilt = rebuild_qualification_call(
            attempt_inputs["suite"],
            attempt_inputs["profile"],
            attempt_inputs["fixture"],
            attempt_inputs["session"],
            attempt_inputs["semantic_map"],
            entry,
            created_at=attempt_inputs["approval_time"]
            + timedelta(microseconds=index + 1),
        )
        assert rebuilt.request.response_validator is not None
        assert rebuilt.request.response_validator.validator_version == (
            PROVIDER_RESPONSE_READOUT_VALIDATOR_VERSION
        )


def test_attempt_v2_authorization_rejects_tamper_and_stale_catalog(
    attempt_inputs,
) -> None:
    authorization = attempt_inputs["authorization"]
    requests = list(authorization.authorized_requests)
    requests[10] = requests[10].model_copy(
        update={"request_content_sha256": "0" * 64}
    )
    tampered = authorization.model_copy(update={"authorized_requests": requests})

    with pytest.raises(ValueError, match="exact requests do not rebuild"):
        validate_qualification_attempt_v2_authorization(
            tampered,
            attempt_inputs["plan"],
            attempt_inputs["proof"],
            attempt_inputs["scope"],
            attempt_inputs["suite"],
            attempt_inputs["profile"],
            attempt_inputs["readiness"],
            attempt_inputs["fixture"],
            attempt_inputs["session"],
            attempt_inputs["semantic_map"],
            attempt_inputs["catalog"],
            now=attempt_inputs["approval_time"] + timedelta(minutes=1),
        )

    stale_time = attempt_inputs["approval_time"] - timedelta(minutes=31)
    stale_catalog = _catalog_at(attempt_inputs["suite"], stale_time)
    with pytest.raises(ValueError, match="catalog preflight is not fresh"):
        build_qualification_attempt_v2_authorization(
            attempt_inputs["plan"],
            attempt_inputs["proof"],
            attempt_inputs["scope"],
            attempt_inputs["suite"],
            attempt_inputs["profile"],
            attempt_inputs["readiness"],
            attempt_inputs["fixture"],
            attempt_inputs["session"],
            attempt_inputs["semantic_map"],
            stale_catalog,
            bundle_id="qualification_attempt_v2_stale_authorization",
            approval_id="qualification_attempt_v2_stale_approval",
            approved_at=attempt_inputs["approval_time"],
            expires_at=attempt_inputs["approval_time"] + timedelta(hours=1),
        )

    wrong_scope = attempt_inputs["scope"].model_copy(
        update={
            "runnable_candidate_ids": list(
                reversed(attempt_inputs["scope"].runnable_candidate_ids)
            )
        }
    )
    with pytest.raises(ValueError, match="scope or runnable roster differs"):
        validate_qualification_attempt_v2_authorization(
            authorization,
            attempt_inputs["plan"],
            attempt_inputs["proof"],
            wrong_scope,
            attempt_inputs["suite"],
            attempt_inputs["profile"],
            attempt_inputs["readiness"],
            attempt_inputs["fixture"],
            attempt_inputs["session"],
            attempt_inputs["semantic_map"],
            attempt_inputs["catalog"],
            now=attempt_inputs["approval_time"] + timedelta(minutes=1),
        )


def _execute(attempt_inputs, transport):
    checkpoints = []
    states = execute_qualification_attempt_v2(
        attempt_inputs["plan"],
        attempt_inputs["proof"],
        attempt_inputs["scope"],
        attempt_inputs["authorization"],
        attempt_inputs["suite"],
        attempt_inputs["profile"],
        attempt_inputs["readiness"],
        attempt_inputs["fixture"],
        attempt_inputs["session"],
        attempt_inputs["semantic_map"],
        transport,
        _SyntheticToolAuditor(),
        clock=transport.clock,
        checkpoint=lambda candidate_id, state: checkpoints.append(
            (candidate_id, state)
        ),
    )
    return states, checkpoints


def test_attempt_v2_full_execution_follows_all_304_paired_calls(
    attempt_inputs,
) -> None:
    clock = TickClock(attempt_inputs["approval_time"] + timedelta(minutes=1))
    transport = SelectorDeltaTransport(clock)
    states, checkpoints = _execute(attempt_inputs, transport)

    assert [item.binding.call_id for item in transport.requests] == (
        attempt_inputs["plan"].execution_order_call_ids
    )
    assert [item.binding.call_id for item in transport.requests[:4]] == (
        attempt_inputs["plan"].execution_order_call_ids[:4]
    )
    assert len(checkpoints) == 304
    assert sum(len(state.provider_ledger.calls) for state in states.values()) == 304
    assert all(
        state.status is QualificationAttemptV2ExecutionStatus.COMPLETED
        for state in states.values()
    )
    validate_qualification_attempt_v2_execution_states(
        states,
        attempt_inputs["plan"],
        attempt_inputs["proof"],
        attempt_inputs["authorization"],
        attempt_inputs["suite"],
        attempt_inputs["profile"],
    )


def test_attempt_v2_invalid_output_is_candidate_local(
    attempt_inputs,
) -> None:
    clock = TickClock(attempt_inputs["approval_time"] + timedelta(minutes=1))
    states, _ = _execute(attempt_inputs, _InvalidFirstOutputTransport(clock))
    first, second = attempt_inputs["authorization"].authorized_candidate_ids

    assert states[first].status is (
        QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
    )
    assert len(states[first].provider_ledger.calls) == 1
    assert states[second].status is (
        QualificationAttemptV2ExecutionStatus.COMPLETED
    )
    assert len(states[second].provider_ledger.calls) == 152

    tampered = states[first].model_copy(deep=True)
    before_approval = (
        attempt_inputs["authorization"].manual_approval.approved_at
        - timedelta(microseconds=1)
    )
    tampered.provider_journal.request_bindings[0] = (
        tampered.provider_journal.request_bindings[0].model_copy(
            update={"created_at": before_approval}
        )
    )
    tampered.provider_ledger.authorizations[0] = (
        tampered.provider_ledger.authorizations[0].model_copy(
            update={"created_at": before_approval}
        )
    )
    with pytest.raises(ValueError, match="created outside approval"):
        validate_qualification_attempt_v2_candidate_state(
            tampered,
            attempt_inputs["plan"],
            attempt_inputs["proof"],
            attempt_inputs["authorization"],
            attempt_inputs["suite"],
            attempt_inputs["profile"],
            require_terminal=True,
        )


def test_attempt_v2_provider_pause_stops_both_candidates(
    attempt_inputs,
) -> None:
    clock = TickClock(attempt_inputs["approval_time"] + timedelta(minutes=1))
    states, _ = _execute(
        attempt_inputs,
        _ProviderErrorWithDiagnosticTransport(clock, fail_at=1),
    )
    first, second = attempt_inputs["authorization"].authorized_candidate_ids

    assert states[first].status is (
        QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
    )
    assert len(states[first].provider_ledger.calls) == 1
    assert states[second].status is (
        QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE
    )
    assert states[second].provider_ledger.calls == []


def test_attempt_v2_shared_budget_pause_occurs_before_send(
    attempt_inputs,
) -> None:
    clock = TickClock(attempt_inputs["approval_time"] + timedelta(minutes=1))
    transport = SelectorDeltaTransport(clock)
    with patch(
        "eval.phase4_qualification_attempt_runtime."
        "_shared_committed_microusd",
        return_value=4_000_000,
    ):
        states, _ = _execute(attempt_inputs, transport)

    assert transport.requests == []
    assert {
        state.status for state in states.values()
    } == {
        QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE,
        QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE,
    }
