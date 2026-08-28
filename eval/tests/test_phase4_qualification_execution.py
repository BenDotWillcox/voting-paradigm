from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_qualification_execution import (
    FROZEN_TWO_DEPLOYMENT_QUALIFICATION_EXECUTION_PLAN_SHA256,
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY,
    QualificationCarryRecord,
    QualificationCallDisposition,
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentQualificationExecutionPlan,
    build_two_deployment_carry_bundle,
    build_two_deployment_qualification_plan,
    load_two_deployment_qualification_plan,
    validate_two_deployment_qualification_plan,
)
from eval.phase4_robustness import LLMRole
from eval.tests.test_phase4_qualification_scope import _tracked_inputs
from eval.tests.test_phase4_selector_recovery import _public_inputs


EXECUTION_PLAN_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_phase4_two_deployment_qualification_execution_v1.json"
)


def _tracked_execution_plan():
    amendment, proof, *_, readiness, _, _ = _tracked_inputs()
    return (
        build_two_deployment_qualification_plan(
            amendment,
            proof,
            readiness,
            plan_id="phase4_two_deployment_execution_test",
            created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        ),
        amendment,
        proof,
        readiness,
    )


def test_metric_policy_freezes_equal_weight_choice_operationalization() -> None:
    policy = TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY

    assert [item.value for item in policy.eligible_response_states] == ["choice"]
    assert policy.quality_roles_in_order == [
        LLMRole.DIRECT_READOUT,
        LLMRole.HYBRID_READOUT,
    ]
    assert policy.role_weights == {
        LLMRole.DIRECT_READOUT: 0.5,
        LLMRole.HYBRID_READOUT: 0.5,
    }
    assert policy.log_loss_probability_floor == 1e-15
    assert policy.delegated_risk_thresholds == [0.65, 0.75, 0.85, 0.95]
    assert policy.robustness_slice_dimensions_in_order == [
        "candidate_id",
        "role",
        "measure_id",
    ]


def test_plan_derives_exact_two_candidate_304_10_294_partition() -> None:
    plan, amendment, proof, readiness = _tracked_execution_plan()

    validate_two_deployment_qualification_plan(
        plan,
        amendment,
        proof,
        readiness,
    )

    assert len(plan.candidate_plans) == 2
    assert [len(item.calls) for item in plan.candidate_plans] == [152, 152]
    assert [item.carried_success_count for item in plan.candidate_plans] == [5, 5]
    assert [item.provider_call_count for item in plan.candidate_plans] == [147, 147]
    calls = sorted(
        (
            call
            for candidate_plan in plan.candidate_plans
            for call in candidate_plan.calls
        ),
        key=lambda item: item.source_manifest_ordinal,
    )
    assert [item.source_manifest_ordinal for item in calls] == [
        *range(1, 11),
        *range(16, 310),
    ]
    assert sum(
        item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
        for item in calls
    ) == 10
    assert sum(
        item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
        for item in calls
    ) == 294
    assert plan.new_projected_cost_microusd == 1_421_524
    assert plan.new_authorized_max_cost_microusd == 2_297_400


def test_tracked_execution_plan_rebuilds_at_frozen_hash() -> None:
    plan = load_two_deployment_qualification_plan(EXECUTION_PLAN_PATH)
    amendment, proof, *_, readiness, _, _ = _tracked_inputs()

    validate_two_deployment_qualification_plan(
        plan,
        amendment,
        proof,
        readiness,
    )
    assert content_sha256(plan) == (
        FROZEN_TWO_DEPLOYMENT_QUALIFICATION_EXECUTION_PLAN_SHA256
    )


def test_plan_tampering_fails_rebuild_validation() -> None:
    plan, amendment, proof, readiness = _tracked_execution_plan()
    payload = plan.model_dump(mode="json")
    payload["candidate_plans"][0]["calls"][0][
        "source_entry_sha256"
    ] = "0" * 64

    with pytest.raises(ValidationError, match="source entry"):
        TwoDeploymentQualificationExecutionPlan.model_validate(payload)

    tampered = plan.model_copy(
        update={"qualification_scope_sha256": "0" * 64},
        deep=True,
    )
    with pytest.raises(ValueError, match="does not rebuild"):
        validate_two_deployment_qualification_plan(
            tampered,
            amendment,
            proof,
            readiness,
        )


def _carry_record(candidate_id: str, role: LLMRole, ordinal: int):
    output_payload = {
        "candidate_id": candidate_id,
        "role": role.value,
        "ordinal": ordinal,
    }
    output_sha256 = content_sha256(output_payload)
    digest = content_sha256(
        {"candidate_id": candidate_id, "role": role.value, "ordinal": ordinal}
    )
    state_sha256 = content_sha256({"candidate_id": candidate_id})
    return QualificationCarryRecord(
        candidate_id=candidate_id,
        role=role,
        call_id=f"carry_{candidate_id}_{role.value}",
        source_manifest_ordinal=ordinal,
        source_entry_sha256=digest,
        corrected_capability_call_sha256=digest,
        aggregation_role_evidence_sha256=digest,
        source_state_schema_version=(
            "preference_eval_phase4_delta_candidate_state.v1"
        ),
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
        tool_call_count=(1 if role is LLMRole.INTERVIEWER else 0),
    )


def _synthetic_carry_bundle() -> TwoDeploymentQualificationCarryBundle:
    candidates = ["candidate_alpha", "candidate_beta"]
    records = [
        _carry_record(candidate_id, role, ordinal)
        for ordinal, (candidate_id, role) in enumerate(
            (
                (candidate_id, role)
                for candidate_id in candidates
                for role in LLMRole
            ),
            start=1,
        )
    ]
    digest = "1" * 64
    return TwoDeploymentQualificationCarryBundle(
        bundle_id="synthetic_qualification_carry",
        created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        execution_plan_sha256=digest,
        qualification_scope_sha256=digest,
        qualification_scope_evidence_proof_sha256=digest,
        capability_aggregation_sha256=digest,
        corrected_capability_plan_sha256=digest,
        together_suite_sha256=digest,
        robustness_profile_sha256=digest,
        readiness_sha256=digest,
        development_fixture_sha256=digest,
        development_session_sha256=digest,
        development_semantic_map_sha256=digest,
        source_state_sha256s=sorted(
            {item.source_state_sha256 for item in records}
        ),
        records=records,
    )


def test_carry_bundle_requires_exact_two_by_five_matrix_and_payload_hashes() -> None:
    bundle = _synthetic_carry_bundle()

    assert len(bundle.records) == 10
    assert len(bundle.source_state_sha256s) == 2
    assert bundle.interviewer_record_count == 2
    assert bundle.interviewer_tool_result_transcripts_retained is False
    assert bundle.interviewer_tool_result_replay_verified is False

    payload = bundle.model_dump(mode="json")
    payload["records"][0]["output_payload"]["ordinal"] = 999
    with pytest.raises(ValidationError, match="payload hash"):
        TwoDeploymentQualificationCarryBundle.model_validate(payload)


def test_carry_builder_fails_closed_without_exact_private_source_states() -> None:
    plan, amendment, proof, readiness = _tracked_execution_plan()
    aggregation = _tracked_inputs()[2]
    public = _public_inputs()

    with pytest.raises(ValueError, match="source state is missing"):
        build_two_deployment_carry_bundle(
            plan,
            amendment,
            proof,
            aggregation,
            public[7],
            public[8],
            public[10],
            readiness,
            public[12],
            public[13],
            public[14],
            [],
            bundle_id="missing_source_state_test",
            created_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        )
