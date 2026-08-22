from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from eval.fixture_io import content_sha256
from eval.phase4_capability import TogetherCapabilityPlan
from eval.phase4_capability_adjudication import (
    build_adjudicated_candidate_authorization,
    build_capability_adjudication_policy,
    load_capability_adjudication_policy,
    validate_adjudicated_candidate_authorization,
    validate_capability_adjudication_policy,
)
from eval.phase4_capability_continuation import (
    CapabilityAttemptFailureKind,
    TogetherCapabilityContinuationPlan,
    build_candidate_capability_authorization_bundle,
    build_capability_continuation_plan,
    candidate_plan_for,
    execute_candidate_capability_preflight,
    validate_candidate_capability_execution_state,
    validate_capability_continuation_plan,
)
from eval.phase4_robustness import LLMRole
from eval.phase4_readiness import load_readiness_bundle
from eval.phase4_together import load_together_suite
from eval.phase4_together_live import (
    TogetherLiveAuthorization,
    TogetherPaidStage,
    validate_live_authorization,
)
from eval.run_phase4_together_candidate_capability import main as run_main
from eval.tests.test_phase4_capability import (
    NOW,
    DeterministicCapabilityTransport,
    TickClock,
    capability_authorization,
    capability_plan,
    execute_with,
    public_inputs,
)
from eval.tests.test_phase4_together_live import catalog_bundle


CONTINUATION_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_together_capability_continuation_v2.json"
)
CORRECTED_PLAN_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_together_capability_v2.json"
)
CORRECTED_SUITE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_together_v3.json"
)
CORRECTED_READINESS_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_together_readiness_v3.json"
)
ADJUDICATION_POLICY_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_together_capability_adjudication_v1.json"
)


def corrected_plan():
    return TogetherCapabilityPlan.model_validate_json(
        CORRECTED_PLAN_PATH.read_text(encoding="utf-8")
    )


def corrected_inputs():
    _, profile, _, fixture, session, semantic_map = public_inputs()
    return (
        load_together_suite(CORRECTED_SUITE_PATH),
        profile,
        load_readiness_bundle(CORRECTED_READINESS_PATH),
        fixture,
        session,
        semantic_map,
    )


def failed_source_attempts():
    provider_clock = TickClock(NOW)
    provider_checkpoints = []
    with pytest.raises(ValueError, match="did not succeed"):
        execute_with(
            DeterministicCapabilityTransport(provider_clock, fail_at=2),
            provider_clock,
            checkpoints=provider_checkpoints,
        )

    capability_clock = TickClock(NOW + timedelta(minutes=1))
    capability_checkpoints = []
    with pytest.raises(ValueError, match="did not call a tool"):
        execute_with(
            DeterministicCapabilityTransport(
                capability_clock,
                omit_interviewer_tool=True,
            ),
            capability_clock,
            checkpoints=capability_checkpoints,
        )
    return [
        (capability_authorization(), provider_checkpoints[-1]),
        (capability_authorization(), capability_checkpoints[-1]),
    ]


def continuation_plan():
    historical_suite, profile, _, _, _, _ = public_inputs()
    return build_capability_continuation_plan(
        capability_plan(),
        corrected_plan(),
        failed_source_attempts(),
        historical_suite,
        profile,
        continuation_id="capability_continuation_test",
        continuation_version=2,
        created_at=NOW + timedelta(minutes=2),
    )


def candidate_authorization(continuation, candidate_id):
    suite, profile, readiness, _, _, _ = corrected_inputs()
    plan = candidate_plan_for(continuation, candidate_id)
    return build_candidate_capability_authorization_bundle(
        continuation,
        plan,
        suite,
        profile,
        readiness,
        catalog_bundle(suite),
        bundle_id=f"{candidate_id}_authorization_test",
        approval_id=f"{candidate_id}_approval_test",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


class InvalidOntologyCapabilityTransport(DeterministicCapabilityTransport):
    def _output(self, request):
        if request.binding.role is LLMRole.ONTOLOGY_PROPOSER:
            return {"planted_sensitive_value": "must_not_be_retained"}
        return super()._output(request)


def provisional_schema_failure(
    diagnostic_sink=None,
    *,
    expected_error="did not succeed",
):
    continuation = continuation_plan()
    plan = continuation.candidate_plans[0]
    authorization = candidate_authorization(continuation, plan.candidate_id)
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()
    clock = TickClock(NOW)
    checkpoints = []
    diagnostics = []
    sink = diagnostics.append if diagnostic_sink is None else diagnostic_sink

    with pytest.raises(ValueError, match=expected_error):
        execute_candidate_capability_preflight(
            continuation,
            capability_plan(),
            corrected_plan(),
            failed_source_attempts(),
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
            catalog_bundle(suite),
            InvalidOntologyCapabilityTransport(clock),
            state_id="provisional_schema_failure_state",
            ledger_id="provisional_schema_failure_ledger",
            journal_id="provisional_schema_failure_journal",
            clock=clock,
            checkpoint=checkpoints.append,
            validation_diagnostic_sink=sink,
        )
    return continuation, authorization, checkpoints[-1], diagnostics


def test_tracked_continuation_is_hash_pinned_and_content_free():
    continuation = TogetherCapabilityContinuationPlan.model_validate_json(
        CONTINUATION_PATH.read_text(encoding="utf-8")
    )

    assert content_sha256(continuation) == (
        "afa317dc2618001028c855bc4f1656e1ba57358a5eb5a5c92574010e2419d75e"
    )
    assert continuation.prior_provider_spend_microusd == 13_143
    assert continuation.cumulative_worst_case_spend_microusd == 142_143
    assert continuation.provider_spend_microusd_by_plan_creation == 0


def test_tracked_adjudication_policy_is_hash_pinned_and_zero_spend():
    policy = load_capability_adjudication_policy(ADJUDICATION_POLICY_PATH)

    assert content_sha256(policy) == (
        "939134d659d35a93aafb6a6fd11fec8fda25326681a93434ef918247f50ac581"
    )
    assert policy.provisional_state_sha256 == (
        "5dc62a9aded1215d3050809f6964fd0398231115167f28ab92eafd239b6b8213"
    )
    assert policy.provisional_candidate_rejection_final is False
    assert policy.provider_inference_calls_executed_by_policy_creation == 0
    assert policy.provider_spend_microusd_by_policy_creation == 0


def test_continuation_preserves_failure_and_partitions_remaining_candidates():
    continuation = continuation_plan()
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()

    validate_capability_continuation_plan(
        continuation,
        capability_plan(),
        corrected_plan(),
        failed_source_attempts(),
        historical_suite,
        suite,
        profile,
        historical_readiness,
        readiness,
        fixture,
        session,
        semantic_map,
    )

    assert [item.failure_kind for item in continuation.attempts] == [
        CapabilityAttemptFailureKind.TRANSIENT_PROVIDER_FAILURE,
        CapabilityAttemptFailureKind.HARNESS_INCONCLUSIVE,
    ]
    assert continuation.rejected_candidate_ids == []
    assert continuation.inconclusive_candidate_ids == ["together_glm_5_2"]
    assert len(continuation.candidate_plans) == 3
    assert sum(len(item.calls) for item in continuation.candidate_plans) == 15
    assert continuation.additional_projected_cost_microusd == 71_091
    assert continuation.additional_authorized_max_cost_microusd == 129_000
    assert continuation.cumulative_worst_case_spend_microusd < (
        continuation.original_capability_max_spend_microusd
    )
    assert continuation.qualification_authorization_permitted is False


def test_candidate_plan_is_exact_source_slice_with_its_own_ceiling():
    continuation = continuation_plan()
    plan = continuation.candidate_plans[0]
    source_calls = [
        item for item in corrected_plan().calls
        if item.candidate_id == plan.candidate_id
    ]

    assert plan.calls == source_calls
    assert {item.role for item in plan.calls} == set(LLMRole)
    expected_ceiling = {
        "together_glm_5_2": 78_000,
        "together_gpt_oss_120b": 9_000,
        "together_nemotron_3_ultra_550b_a55b": 42_000,
    }[plan.candidate_id]
    assert plan.candidate_capability_max_spend_microusd == expected_ceiling
    assert candidate_authorization(
        continuation,
        plan.candidate_id,
    ).live_authorization.authorized_candidate_ids == [plan.candidate_id]


def test_tampered_attempt_binding_cannot_authorize_continuation():
    continuation = continuation_plan()
    payload = continuation.model_dump(mode="json")
    payload["attempts"][0]["state_sha256"] = "0" * 64
    tampered = TogetherCapabilityContinuationPlan.model_validate(payload)
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()

    with pytest.raises(ValueError, match="does not rebuild"):
        validate_capability_continuation_plan(
            tampered,
            capability_plan(),
            corrected_plan(),
            failed_source_attempts(),
            historical_suite,
            suite,
            profile,
            historical_readiness,
            readiness,
            fixture,
            session,
            semantic_map,
        )


def test_corrected_plan_cannot_reuse_the_historical_plan_hash():
    payload = continuation_plan().model_dump(mode="json")
    payload["corrected_capability_plan_sha256"] = payload[
        "historical_capability_plan_sha256"
    ]

    with pytest.raises(
        ValueError,
        match="corrected capability plan must differ",
    ):
        TogetherCapabilityContinuationPlan.model_validate(payload)


def test_all_candidate_schema_failure_disposition_is_predeclared():
    continuation = continuation_plan()

    assert continuation.all_candidate_round2_schema_failure_disposition == (
        "shared_provider_schema_incompatibility_requires_versioned_schema_revision"
    )


def test_invalid_candidate_output_emits_only_content_free_diagnostics():
    _, _, state, diagnostics = provisional_schema_failure()

    assert state.receipt is None
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.role is LLMRole.ONTOLOGY_PROPOSER
    assert diagnostic.error_count == 1
    assert diagnostic.issues[0].path == []
    serialized = diagnostic.model_dump_json()
    assert "planted_sensitive_value" not in serialized
    assert "must_not_be_retained" not in serialized


def test_diagnostic_write_failure_keeps_the_paid_state_checkpoint():
    def fail_diagnostic_write(_diagnostic):
        raise ValueError("diagnostic write failed")

    _, _, state, diagnostics = provisional_schema_failure(
        fail_diagnostic_write,
        expected_error="diagnostic write failed",
    )

    assert diagnostics == []
    assert len(state.provider_ledger.calls) == len(LLMRole)
    assert state.provider_journal.finalizations[-1].outcome.value == (
        "invalid_output"
    )


def test_adjudication_policy_keeps_failure_provisional_until_comparison():
    continuation, authorization, state, _ = provisional_schema_failure()
    suite, profile, _, _, _, _ = corrected_inputs()
    policy = build_capability_adjudication_policy(
        continuation,
        corrected_plan(),
        suite,
        profile,
        authorization,
        state,
        policy_id="capability_adjudication_test",
        policy_version=1,
        created_at=NOW + timedelta(minutes=5),
    )

    validate_capability_adjudication_policy(
        policy,
        continuation,
        corrected_plan(),
        suite,
        profile,
        authorization,
        state,
    )
    assert policy.provisional_candidate_rejection_final is False
    assert policy.uniform_failure_required_candidate_count == 3
    assert set(policy.remaining_candidate_ids) == (
        set(policy.all_candidate_ids) - {policy.provisional_candidate_id}
    )
    assert policy.uniform_failure_disposition == (
        "shared_harness_review_before_candidate_rejection"
    )
    comparison_id = policy.remaining_candidate_ids[0]
    wrapper = build_adjudicated_candidate_authorization(
        policy,
        candidate_authorization(continuation, comparison_id),
    )
    validate_adjudicated_candidate_authorization(wrapper, policy)
    assert wrapper.adjudication_policy_sha256 == content_sha256(policy)
    assert wrapper.provisional_state_sha256 == content_sha256(state)


def test_successful_candidate_attempt_builds_one_complete_receipt():
    continuation = continuation_plan()
    plan = continuation.candidate_plans[0]
    authorization = candidate_authorization(continuation, plan.candidate_id)
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()
    clock = TickClock(NOW)
    checkpoints = []

    state = execute_candidate_capability_preflight(
        continuation,
        capability_plan(),
        corrected_plan(),
        failed_source_attempts(),
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
        catalog_bundle(suite),
        DeterministicCapabilityTransport(clock),
        state_id="candidate_capability_state_test",
        ledger_id="candidate_capability_ledger_test",
        journal_id="candidate_capability_journal_test",
        clock=clock,
        checkpoint=checkpoints.append,
    )

    validate_candidate_capability_execution_state(
        state,
        continuation,
        plan,
        authorization,
        suite,
        profile,
    )
    assert state.receipt is not None
    assert len(state.receipt.checks) == len(LLMRole)
    assert len(checkpoints) == len(LLMRole) + 1
    assert state.receipt.candidate_id == plan.candidate_id


def test_one_candidate_failure_does_not_block_the_other_candidate_plan():
    continuation = continuation_plan()
    first, second = continuation.candidate_plans[:2]
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()
    failed_clock = TickClock(NOW)
    failed_checkpoints = []

    with pytest.raises(ValueError, match="did not succeed"):
        execute_candidate_capability_preflight(
            continuation,
            capability_plan(),
            corrected_plan(),
            failed_source_attempts(),
            historical_suite,
            historical_readiness,
            first,
            candidate_authorization(continuation, first.candidate_id),
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog_bundle(suite),
            DeterministicCapabilityTransport(failed_clock, fail_at=2),
            state_id="first_candidate_state",
            ledger_id="first_candidate_ledger",
            journal_id="first_candidate_journal",
            clock=failed_clock,
            checkpoint=failed_checkpoints.append,
        )
    assert failed_checkpoints[-1].receipt is None

    second_clock = TickClock(NOW)
    second_state = execute_candidate_capability_preflight(
        continuation,
        capability_plan(),
        corrected_plan(),
        failed_source_attempts(),
        historical_suite,
        historical_readiness,
        second,
        candidate_authorization(continuation, second.candidate_id),
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        catalog_bundle(suite),
        DeterministicCapabilityTransport(second_clock),
        state_id="second_candidate_state",
        ledger_id="second_candidate_ledger",
        journal_id="second_candidate_journal",
        clock=second_clock,
    )
    assert second_state.receipt is not None


def test_partial_candidate_receipt_cannot_authorize_qualification():
    continuation = continuation_plan()
    plan = continuation.candidate_plans[0]
    authorization = candidate_authorization(continuation, plan.candidate_id)
    historical_suite, profile, historical_readiness, fixture, session, semantic_map = (
        public_inputs()
    )
    suite, _, readiness, _, _, _ = corrected_inputs()
    clock = TickClock(NOW)
    state = execute_candidate_capability_preflight(
        continuation,
        capability_plan(),
        corrected_plan(),
        failed_source_attempts(),
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
        catalog_bundle(suite),
        DeterministicCapabilityTransport(clock),
        state_id="partial_receipt_state",
        ledger_id="partial_receipt_ledger",
        journal_id="partial_receipt_journal",
        clock=clock,
    )
    assert state.receipt is not None
    payload = authorization.live_authorization.model_dump(mode="json")
    payload["stage"] = TogetherPaidStage.QUALIFICATION.value
    payload["authorized_candidate_ids"] = sorted(
        item.candidate.candidate_id for item in suite.candidates
    )
    payload["capability_preflight_receipt_sha256"] = content_sha256(
        state.receipt
    )
    qualification = TogetherLiveAuthorization.model_validate(payload)

    with pytest.raises(ValueError, match="matrix is incomplete"):
        validate_live_authorization(
            suite,
            profile,
            catalog_bundle(suite),
            readiness.token_readiness_receipt,
            readiness.headroom_policy,
            qualification,
            capability_receipt=state.receipt,  # type: ignore[arg-type]
            now=NOW + timedelta(minutes=1),
        )


def test_paid_candidate_cli_reads_nothing_without_execution_confirmation(
    monkeypatch,
):
    def reject_file_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("candidate runner read before paid confirmation")

    monkeypatch.setattr("pathlib.Path.read_text", reject_file_read)
    missing = "missing.json"
    result = run_main(
        [
            *([missing] * 16),
            "missing_candidate",
            missing,
            "--attempt",
            missing,
            missing,
            "--confirm-max-spend-microusd",
            "9000",
        ]
    )

    assert result == 1
