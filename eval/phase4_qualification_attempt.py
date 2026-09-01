"""Precommitted second two-deployment qualification attempt.

Attempt v1 remains a completed, immutable no-winner result. This module binds
that result as evidence and schedules all 304 coordinates under one repaired
raw-JSON and readout contract. Historical raw response bodies were not retained,
so no prior output can prove duplicate-key conformance and none carries forward.
It performs no network request and authorizes no spend.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_provider import (
    PROVIDER_RESPONSE_JSON_DECODER_POLICY,
    ProviderCallOutcome,
    provider_response_json_decoder_implementation_sha256,
)
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3,
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3,
    provider_response_readout_validator_implementation_sha256,
)
from .phase4_qualification_execution import (
    QualificationCallDisposition,
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY,
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentQualificationExecutionPlan,
)
from .phase4_qualification_runtime import (
    QUALIFICATION_SEGMENT_CAP_MICROUSD,
    TwoDeploymentCandidateExecutionState,
    TwoDeploymentQualificationAuthorizationBundle,
    validate_two_deployment_candidate_state,
)
from .phase4_qualification_result_assembly import (
    build_new_qualification_observations,
)
from .phase4_qualification_scope import (
    FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256,
    TwoDeploymentQualificationScopeAmendment,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    QualificationCallPlanEntry,
    QualificationVariant,
)
from .phase4_robustness import LLMRole, Phase4ERobustnessProfile
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import (
    together_json_decoder_integration_sha256,
)
from .phase4_two_deployment_result import (
    QualificationCoordinateDisposition,
    QualificationObservationSource,
    QualificationResultStatus,
    TwoDeploymentQualificationAggregateReceipt,
    TwoDeploymentQualificationResult,
    validate_two_deployment_qualification_result,
    validate_two_deployment_qualification_aggregate_receipt,
)
from .prequential import PrequentialSessionScript


PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]

ATTEMPT_V2_RUNNABLE_CANDIDATE_COUNT = 2
ATTEMPT_V2_RUNNABLE_CANDIDATE_IDS = (
    "together_glm_5_2",
    "together_gpt_oss_120b",
)
ATTEMPT_V2_COORDINATE_COUNT = 304
ATTEMPT_V2_CARRY_PER_CANDIDATE = 0
ATTEMPT_V2_CARRY_COUNT = 0
ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE = 152
ATTEMPT_V2_PROVIDER_CALL_COUNT = 304
ATTEMPT_V2_CONFORMANCE_CALL_COUNT = 4
ATTEMPT_V1_HISTORICAL_SPEND_MICROUSD = 51_042
ATTEMPT_V1_PROVIDER_SPEND_MICROUSD = 46_245
ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD = (
    ATTEMPT_V1_HISTORICAL_SPEND_MICROUSD
    + ATTEMPT_V1_PROVIDER_SPEND_MICROUSD
)
ATTEMPT_V2_READOUT_ROLES = frozenset(
    {LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT}
)


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


QualificationAttemptDisposition = QualificationCallDisposition


class QualificationAttemptStage(str, Enum):
    """Frozen execution order for early readout-contract feedback."""

    READOUT_CONFORMANCE = "readout_conformance"
    FULL_QUALIFICATION = "full_qualification"


class QualificationAttemptV2Policy(ContractModel):
    """Reviewed interpretation and stopping rules for attempt v2."""

    record_version: Literal[
        "phase4_two_deployment_qualification_attempt_policy.v2"
    ] = "phase4_two_deployment_qualification_attempt_policy.v2"
    policy_id: Literal[
        "phase4_two_deployment_qualification_attempt_policy"
    ] = "phase4_two_deployment_qualification_attempt_policy"
    policy_version: Literal[2] = 2
    prior_attempt_result_is_immutable: Literal[True] = True
    prior_attempt_reinterpretation_forbidden: Literal[True] = True
    all_prior_successes_cannot_carry: Literal[True] = True
    historical_raw_provider_json_unavailable: Literal[True] = True
    cross_decoder_carry_forbidden: Literal[True] = True
    materially_invalid_probability_repair_forbidden: Literal[True] = True
    probability_acceptance_tolerance_unchanged: Literal[1e-9] = 1e-9
    duplicate_json_object_keys_rejected: Literal[True] = True
    exact_option_coverage_required: Literal[True] = True
    eligible_evidence_grounding_required: Literal[True] = True
    contradictory_assumptions_rejected: Literal[True] = True
    conformance_stage_call_count: Literal[4] = ATTEMPT_V2_CONFORMANCE_CALL_COUNT
    conformance_stage_roles: list[
        Literal[LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT]
    ] = Field(
        default_factory=lambda: [
            LLMRole.DIRECT_READOUT,
            LLMRole.HYBRID_READOUT,
        ]
    )
    candidate_hard_failure_is_candidate_local: Literal[True] = True
    provider_or_harness_pause_blocks_selection: Literal[True] = True
    both_candidate_attempts_terminal_before_selection: Literal[True] = True
    paired_candidate_interleave_required: Literal[True] = True
    within_stage_candidate_first_position_counterbalanced: Literal[True] = True
    frozen_metric_and_banded_selection_policy_unchanged: Literal[True] = True
    one_passing_candidate_may_win: Literal[True] = True
    winner_not_guaranteed: Literal[True] = True
    outcome_is_empirical: Literal[True] = True
    automatic_retry_forbidden: Literal[True] = True
    fallback_and_replacement_forbidden: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_conformance_stage(self) -> Self:
        if self.conformance_stage_roles != [
            LLMRole.DIRECT_READOUT,
            LLMRole.HYBRID_READOUT,
        ]:
            raise ValueError("qualification v2 conformance roles differ")
        return self


QUALIFICATION_ATTEMPT_V2_POLICY = QualificationAttemptV2Policy()


def _expected_execution_order(
    candidate_plans: Sequence["QualificationAttemptV2CandidatePlan"],
) -> list[str]:
    ordered_candidates = sorted(candidate_plans, key=lambda item: item.candidate_id)
    if len(ordered_candidates) != ATTEMPT_V2_RUNNABLE_CANDIDATE_COUNT:
        raise ValueError("qualification v2 execution candidates differ")
    execution_order: list[str] = []
    for stage in QualificationAttemptStage:
        local_indexes = [
            index
            for index, call in enumerate(ordered_candidates[0].calls)
            if call.execution_stage is stage
        ]
        for stage_pair_index, local_index in enumerate(local_indexes):
            pair = (
                ordered_candidates
                if stage_pair_index % 2 == 0
                else list(reversed(ordered_candidates))
            )
            for candidate in pair:
                call = candidate.calls[local_index]
                if call.execution_stage is not stage:
                    raise ValueError("qualification v2 execution stages misalign")
                execution_order.append(call.call_id)
    return execution_order


class QualificationAttemptV2SourceProof(ContractModel):
    """Aggregate-only proof binding the completed v1 result to attempt v2."""

    schema_version: Literal[
        "preference_eval_phase4_qualification_attempt_source_proof.v2"
    ] = "preference_eval_phase4_qualification_attempt_source_proof.v2"
    proof_id: StableId
    proof_version: Literal[2] = 2
    validated_at: datetime
    prior_execution_plan_sha256: Sha256Digest
    prior_carry_bundle_sha256: Sha256Digest
    prior_authorization_bundle_sha256: Sha256Digest
    prior_private_result_sha256: Sha256Digest
    prior_safe_receipt_sha256: Sha256Digest
    prior_scope_sha256: Sha256Digest
    prior_candidate_state_sha256s: dict[StableId, Sha256Digest]
    prior_result_status: Literal[
        QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
    ] = QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
    prior_selected_candidate_id: Literal[None] = None
    prior_observation_count: Literal[28] = 28
    prior_unattempted_coordinate_count: Literal[276] = 276
    prior_invalid_output_count: Literal[2] = 2
    prior_unlocalized_root_error_count: Literal[2] = 2
    prior_failure_cause_resolved: Literal[False] = False
    prior_historical_spend_microusd: Literal[51_042] = (
        ATTEMPT_V1_HISTORICAL_SPEND_MICROUSD
    )
    prior_attempt_spend_microusd: Literal[46_245] = (
        ATTEMPT_V1_PROVIDER_SPEND_MICROUSD
    )
    prior_cumulative_spend_microusd: Literal[97_287] = (
        ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD
    )
    source_together_suite_sha256: Sha256Digest
    source_readiness_sha256: Sha256Digest
    corrected_together_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    response_invariant_manifest_sha256: Sha256Digest
    response_behavior_spec_sha256: Sha256Digest
    readout_validator_implementation_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    exact_candidate_roster_preserved: Literal[True] = True
    metric_and_selection_policy_unchanged: Literal[True] = True
    v1_result_remains_valid: Literal[True] = True
    v1_result_reinterpretation_forbidden: Literal[True] = True
    provider_request_or_response_content_omitted: Literal[True] = True
    participant_content_present: Literal[False] = False
    prior_result_rebuild_passed: Literal[True] = True
    prior_candidate_state_audits_passed: Literal[True] = True
    prior_carry_observation_bindings_passed: Literal[True] = True
    prior_new_observation_bindings_passed: Literal[True] = True
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification v2 proof time")

    @model_validator(mode="after")
    def require_exact_prior_arithmetic(self) -> Self:
        if self.prior_observation_count + (
            self.prior_unattempted_coordinate_count
        ) != ATTEMPT_V2_COORDINATE_COUNT:
            raise ValueError("qualification v1 coordinate totals differ")
        if self.prior_historical_spend_microusd + (
            self.prior_attempt_spend_microusd
        ) != self.prior_cumulative_spend_microusd:
            raise ValueError("qualification v1 spend totals differ")
        if len(self.prior_candidate_state_sha256s) != (
            ATTEMPT_V2_RUNNABLE_CANDIDATE_COUNT
        ):
            raise ValueError("qualification v1 candidate states differ")
        if tuple(sorted(self.prior_candidate_state_sha256s)) != (
            ATTEMPT_V2_RUNNABLE_CANDIDATE_IDS
        ) or self.prior_scope_sha256 != FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256:
            raise ValueError("qualification v2 frozen scope differs")
        if (
            self.response_invariant_manifest_sha256
            != content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3)
            or self.response_behavior_spec_sha256
            != content_sha256(PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3)
            or self.readout_validator_implementation_sha256
            != provider_response_readout_validator_implementation_sha256()
            or self.json_decoder_policy_sha256
            != content_sha256(PROVIDER_RESPONSE_JSON_DECODER_POLICY)
            or self.json_decoder_implementation_sha256
            != provider_response_json_decoder_implementation_sha256()
            or self.together_json_decoder_integration_sha256
            != together_json_decoder_integration_sha256()
        ):
            raise ValueError("qualification v2 JSON decoder differs")
        return self


class QualificationAttemptV2CallPlan(ContractModel):
    """One namespaced v6 source-manifest coordinate."""

    record_version: Literal[
        "phase4_two_deployment_qualification_attempt_call.v2"
    ] = "phase4_two_deployment_qualification_attempt_call.v2"
    source_manifest_ordinal: PositiveCount
    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    measure_id: StableId
    measure_version: PositiveCount
    variant_id: QualificationVariant
    disposition: QualificationAttemptDisposition
    execution_stage: QualificationAttemptStage | None = None
    source_entry_sha256: Sha256Digest
    source_entry: QualificationCallPlanEntry
    projected_cost_microusd: Microusd
    authorized_max_cost_microusd: Microusd

    @model_validator(mode="after")
    def require_exact_source_and_disposition(self) -> Self:
        coordinate = self.source_entry.coordinate
        actual = (
            self.source_manifest_ordinal,
            self.call_id,
            self.candidate_id,
            self.role,
            self.measure_id,
            self.measure_version,
            self.variant_id,
            self.source_entry_sha256,
            self.projected_cost_microusd,
            self.authorized_max_cost_microusd,
        )
        expected = (
            coordinate.ordinal,
            coordinate.call_id,
            coordinate.candidate_id,
            coordinate.role,
            coordinate.measure_id,
            coordinate.measure_version,
            coordinate.variant_id,
            content_sha256(self.source_entry),
            self.source_entry.projected_cost_microusd,
            self.source_entry.authorized_max_cost_microusd,
        )
        if actual != expected:
            raise ValueError("qualification v2 call does not bind source entry")
        if self.disposition is not QualificationAttemptDisposition.EXECUTE_PROVIDER:
            raise ValueError("qualification v2 call cannot carry")
        if self.execution_stage is None:
            raise ValueError("qualification v2 provider call lacks a stage")
        return self


class QualificationAttemptV2CandidatePlan(ContractModel):
    """One 152-coordinate candidate surface with no historical carry."""

    record_version: Literal[
        "phase4_two_deployment_qualification_attempt_candidate.v2"
    ] = "phase4_two_deployment_qualification_attempt_candidate.v2"
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    calls: list[QualificationAttemptV2CallPlan] = Field(
        min_length=152,
        max_length=152,
    )
    carried_success_count: Literal[0] = ATTEMPT_V2_CARRY_PER_CANDIDATE
    provider_call_count: Literal[152] = (
        ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE
    )
    provider_call_ids_sha256: Sha256Digest
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd

    @model_validator(mode="after")
    def require_exact_partition(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.calls):
            raise ValueError("qualification v2 candidate plan mixes candidates")
        source_ordinals = [
            item.source_manifest_ordinal for item in self.calls
        ]
        call_ids = [item.call_id for item in self.calls]
        if source_ordinals != sorted(source_ordinals) or len(
            source_ordinals
        ) != len(set(source_ordinals)):
            raise ValueError("qualification v2 source ordinals differ")
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("qualification v2 call ids differ")
        provider = [
            item
            for item in self.calls
            if item.disposition is QualificationAttemptDisposition.EXECUTE_PROVIDER
        ]
        if len(provider) != self.provider_call_count:
            raise ValueError("qualification v2 candidate partition differs")
        conformance = [
            item
            for item in provider
            if item.execution_stage
            is QualificationAttemptStage.READOUT_CONFORMANCE
        ]
        if len(conformance) != 2 or {
            item.role for item in conformance
        } != ATTEMPT_V2_READOUT_ROLES:
            raise ValueError("qualification v2 conformance matrix differs")
        if self.provider_call_ids_sha256 != content_sha256(
            [item.call_id for item in provider]
        ):
            raise ValueError("qualification v2 candidate call-id hash differs")
        if (
            self.new_projected_cost_microusd,
            self.new_authorized_max_cost_microusd,
        ) != (
            sum(item.projected_cost_microusd for item in provider),
            sum(item.authorized_max_cost_microusd for item in provider),
        ):
            raise ValueError("qualification v2 candidate costs differ")
        return self


class QualificationAttemptV2Plan(ContractModel):
    """Tracked zero-spend plan for an exact 304-call fresh attempt."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_attempt.v2"
    ] = "preference_eval_phase4_two_deployment_qualification_attempt.v2"
    plan_id: StableId
    plan_version: Literal[2] = 2
    created_at: datetime
    source_proof_sha256: Sha256Digest
    prior_result_sha256: Sha256Digest
    prior_scope_sha256: Sha256Digest
    corrected_together_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    corrected_qualification_manifest_sha256: Sha256Digest
    response_invariant_manifest_sha256: Sha256Digest
    response_behavior_spec_sha256: Sha256Digest
    readout_validator_implementation_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    policy: QualificationAttemptV2Policy
    policy_sha256: Sha256Digest
    candidate_plans: list[QualificationAttemptV2CandidatePlan] = Field(
        min_length=2,
        max_length=2,
    )
    execution_order_call_ids: list[StableId] = Field(
        min_length=304,
        max_length=304,
    )
    scoped_coordinate_count: Literal[304] = ATTEMPT_V2_COORDINATE_COUNT
    carried_success_count: Literal[0] = ATTEMPT_V2_CARRY_COUNT
    provider_call_count: Literal[304] = ATTEMPT_V2_PROVIDER_CALL_COUNT
    conformance_stage_call_count: Literal[4] = ATTEMPT_V2_CONFORMANCE_CALL_COUNT
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd
    maximum_single_call_reservation_microusd: Microusd
    prior_actual_spend_microusd: Literal[97_287] = (
        ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD
    )
    qualification_segment_cap_microusd: Literal[4_000_000] = (
        QUALIFICATION_SEGMENT_CAP_MICROUSD
    )
    qualification_minimum_headroom_microusd: Microusd
    cumulative_authorized_worst_case_microusd: Microusd
    sequential_projected_headroom_microusd: Microusd
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification v2 plan time")

    @model_validator(mode="after")
    def require_exact_surface_and_budget(self) -> Self:
        if self.policy_sha256 != content_sha256(self.policy) or (
            self.policy != QUALIFICATION_ATTEMPT_V2_POLICY
        ):
            raise ValueError("qualification v2 policy differs")
        if (
            self.response_invariant_manifest_sha256
            != content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3)
            or self.response_behavior_spec_sha256
            != content_sha256(PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3)
            or self.readout_validator_implementation_sha256
            != provider_response_readout_validator_implementation_sha256()
            or self.json_decoder_policy_sha256
            != content_sha256(PROVIDER_RESPONSE_JSON_DECODER_POLICY)
            or self.json_decoder_implementation_sha256
            != provider_response_json_decoder_implementation_sha256()
            or self.together_json_decoder_integration_sha256
            != together_json_decoder_integration_sha256()
            or self.metric_policy_sha256
            != content_sha256(TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY)
        ):
            raise ValueError("qualification v2 implementation bindings differ")
        candidate_ids = [item.candidate_id for item in self.candidate_plans]
        if tuple(candidate_ids) != ATTEMPT_V2_RUNNABLE_CANDIDATE_IDS:
            raise ValueError("qualification v2 candidates differ")
        calls = [
            item for candidate in self.candidate_plans for item in candidate.calls
        ]
        call_ids = [item.call_id for item in calls]
        source_ordinals = [item.source_manifest_ordinal for item in calls]
        if len(call_ids) != len(set(call_ids)) or len(source_ordinals) != len(
            set(source_ordinals)
        ):
            raise ValueError("qualification v2 global coordinates differ")
        provider = [
            item
            for item in calls
            if item.disposition is QualificationAttemptDisposition.EXECUTE_PROVIDER
        ]
        if (len(calls), len(provider)) != (
            self.scoped_coordinate_count,
            self.provider_call_count,
        ):
            raise ValueError("qualification v2 totals differ")
        expected_order = _expected_execution_order(self.candidate_plans)
        if self.execution_order_call_ids != expected_order or len(
            set(self.execution_order_call_ids)
        ) != self.provider_call_count:
            raise ValueError("qualification v2 execution order differs")
        if sum(
            item.execution_stage is QualificationAttemptStage.READOUT_CONFORMANCE
            for item in provider
        ) != self.conformance_stage_call_count:
            raise ValueError("qualification v2 conformance stage differs")
        expected_costs = (
            sum(item.projected_cost_microusd for item in provider),
            sum(item.authorized_max_cost_microusd for item in provider),
            max(item.authorized_max_cost_microusd for item in provider),
        )
        if (
            self.new_projected_cost_microusd,
            self.new_authorized_max_cost_microusd,
            self.maximum_single_call_reservation_microusd,
        ) != expected_costs:
            raise ValueError("qualification v2 cost totals differ")
        if self.cumulative_authorized_worst_case_microusd != (
            self.prior_actual_spend_microusd
            + self.new_authorized_max_cost_microusd
        ) or self.cumulative_authorized_worst_case_microusd > (
            self.qualification_segment_cap_microusd
        ):
            raise ValueError("qualification v2 exceeds the segment cap")
        if self.sequential_projected_headroom_microusd != (
            self.qualification_segment_cap_microusd
            - self.prior_actual_spend_microusd
            - self.new_projected_cost_microusd
            - self.maximum_single_call_reservation_microusd
        ) or self.sequential_projected_headroom_microusd < (
            self.qualification_minimum_headroom_microusd
        ):
            raise ValueError("qualification v2 lacks sequential headroom")
        return self


def _prior_new_spend(states: Sequence[TwoDeploymentCandidateExecutionState]) -> int:
    return sum(
        call.billed_cost_microusd
        for state in states
        for call in state.provider_ledger.calls
    )


def build_qualification_attempt_v2_source_proof(
    prior_plan: TwoDeploymentQualificationExecutionPlan,
    prior_carry: TwoDeploymentQualificationCarryBundle,
    prior_authorization: TwoDeploymentQualificationAuthorizationBundle,
    prior_result: TwoDeploymentQualificationResult,
    prior_receipt: TwoDeploymentQualificationAggregateReceipt,
    prior_states: Sequence[TwoDeploymentCandidateExecutionState],
    source_suite: Phase4TogetherSuite,
    source_readiness: Phase4TogetherReadinessBundle,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    scope: TwoDeploymentQualificationScopeAmendment,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    *,
    proof_id: str,
    validated_at: datetime,
) -> QualificationAttemptV2SourceProof:
    """Validate the completed v1 chain and emit only aggregate bindings."""

    validate_two_deployment_qualification_aggregate_receipt(
        prior_receipt,
        prior_result,
    )
    validate_two_deployment_qualification_result(
        prior_result,
        scope,
        source_readiness,
        profile,
        source_suite,
        fixture,
        session,
        prior_plan,
    )
    if (
        prior_receipt.private_result_sha256 != content_sha256(prior_result)
        or prior_result.scope_amendment_sha256 != content_sha256(scope)
        or prior_result.execution_plan_sha256 != content_sha256(prior_plan)
        or prior_result.result_source_bindings.carry_bundle_sha256
        != content_sha256(prior_carry)
        or prior_result.result_source_bindings.authorization_bundle_sha256
        != content_sha256(prior_authorization)
        or prior_result.status
        is not QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
        or prior_result.selected_candidate_id is not None
    ):
        raise ValueError("qualification v1 result bindings differ")
    unattempted_dispositions = {
        QualificationCoordinateDisposition.UNATTEMPTED_HARD_FAILURE,
        QualificationCoordinateDisposition.UNATTEMPTED_PROVIDER_PAUSE,
        QualificationCoordinateDisposition.UNATTEMPTED_AMBIGUOUS,
        QualificationCoordinateDisposition.UNATTEMPTED_HARNESS_PAUSE,
    }
    if (
        len(prior_result.observations) != 28
        or sum(
            item.disposition in unattempted_dispositions
            for item in prior_result.coordinate_results
        )
        != 276
        or sum(
            item.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
            for item in prior_result.observations
        )
        != 2
        or prior_result.robustness_profile_sha256 != content_sha256(profile)
    ):
        raise ValueError("qualification v1 result evidence differs")
    states_by_id = {item.candidate_id: item for item in prior_states}
    if (
        len(prior_states) != ATTEMPT_V2_RUNNABLE_CANDIDATE_COUNT
        or len(states_by_id) != ATTEMPT_V2_RUNNABLE_CANDIDATE_COUNT
    ) or {
        key: content_sha256(value) for key, value in states_by_id.items()
    } != prior_result.result_source_bindings.candidate_state_sha256s:
        raise ValueError("qualification v1 candidate states differ")
    scoped_candidate_ids = tuple(scope.runnable_candidate_ids)
    if (
        content_sha256(scope) != FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256
        or scoped_candidate_ids != ATTEMPT_V2_RUNNABLE_CANDIDATE_IDS
        or tuple(sorted(states_by_id)) != scoped_candidate_ids
    ):
        raise ValueError("qualification v2 frozen scope differs")
    for state in states_by_id.values():
        validate_two_deployment_candidate_state(
            state,
            prior_plan,
            prior_authorization,
            prior_carry,
            source_suite,
            profile,
        )
    diagnostics = [
        diagnostic
        for state in states_by_id.values()
        for diagnostic in state.validation_diagnostics
    ]
    if (
        len(diagnostics) != 2
        or any(
            diagnostic.error_count != 1
            or len(diagnostic.issues) != 1
            or diagnostic.issues[0].path
            or diagnostic.issues[0].error_type != "value_error"
            for diagnostic in diagnostics
        )
    ):
        raise ValueError("qualification v1 failure evidence differs")
    observations_by_id = {
        item.call_id: item for item in prior_result.observations
    }
    for record in prior_carry.records:
        observation = observations_by_id.get(record.call_id)
        if observation is None or (
            observation.candidate_id,
            observation.role,
            observation.source_manifest_ordinal,
            observation.source_entry_sha256,
            observation.request_binding_sha256,
            observation.usage_sha256,
            observation.finalization_sha256,
            observation.output_sha256,
            content_sha256(observation.parsed_output),
        ) != (
            record.candidate_id,
            record.role,
            record.source_manifest_ordinal,
            record.source_entry_sha256,
            record.request_binding_sha256,
            record.provider_usage_sha256,
            record.finalization_sha256,
            record.source_output_sha256,
            record.source_output_sha256,
        ):
            raise ValueError("qualification v1 carry observation differs")
    rebuilt_new_observations = sorted(
        build_new_qualification_observations(prior_plan, prior_states),
        key=lambda item: item.source_manifest_ordinal,
    )
    recorded_new_observations = [
        item
        for item in prior_result.observations
        if item.source is QualificationObservationSource.NEW_QUALIFICATION_CALL
    ]
    if rebuilt_new_observations != recorded_new_observations:
        raise ValueError("qualification v1 new-call observations differ")
    if _prior_new_spend(prior_states) != ATTEMPT_V1_PROVIDER_SPEND_MICROUSD or (
        prior_authorization.prior_qualification_spend_microusd
        != ATTEMPT_V1_HISTORICAL_SPEND_MICROUSD
    ):
        raise ValueError("qualification v1 spend evidence differs")
    if (
        source_readiness.together_suite_sha256 != content_sha256(source_suite)
        or corrected_readiness.together_suite_sha256
        != content_sha256(corrected_suite)
        or source_suite.suite_version != 5
        or corrected_suite.suite_version != 6
    ):
        raise ValueError("qualification v2 suite progression differs")
    source_roster = [
        (
            item.candidate.candidate_id,
            content_sha256(item.candidate),
            content_sha256(item.price_card),
        )
        for item in source_suite.candidates
    ]
    corrected_roster = [
        (
            item.candidate.candidate_id,
            content_sha256(item.candidate),
            content_sha256(item.price_card),
        )
        for item in corrected_suite.candidates
    ]
    if source_roster != corrected_roster:
        raise ValueError("qualification v2 candidate roster differs")
    return QualificationAttemptV2SourceProof(
        proof_id=proof_id,
        validated_at=validated_at,
        prior_execution_plan_sha256=content_sha256(prior_plan),
        prior_carry_bundle_sha256=content_sha256(prior_carry),
        prior_authorization_bundle_sha256=content_sha256(prior_authorization),
        prior_private_result_sha256=content_sha256(prior_result),
        prior_safe_receipt_sha256=content_sha256(prior_receipt),
        prior_scope_sha256=content_sha256(scope),
        prior_candidate_state_sha256s={
            key: content_sha256(value)
            for key, value in sorted(states_by_id.items())
        },
        source_together_suite_sha256=content_sha256(source_suite),
        source_readiness_sha256=content_sha256(source_readiness),
        corrected_together_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        response_invariant_manifest_sha256=content_sha256(
            PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3
        ),
        response_behavior_spec_sha256=content_sha256(
            PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3
        ),
        readout_validator_implementation_sha256=(
            provider_response_readout_validator_implementation_sha256()
        ),
        json_decoder_policy_sha256=content_sha256(
            PROVIDER_RESPONSE_JSON_DECODER_POLICY
        ),
        json_decoder_implementation_sha256=(
            provider_response_json_decoder_implementation_sha256()
        ),
        together_json_decoder_integration_sha256=(
            together_json_decoder_integration_sha256()
        ),
    )


def validate_qualification_attempt_v2_source_proof(
    proof: QualificationAttemptV2SourceProof,
    prior_plan: TwoDeploymentQualificationExecutionPlan,
    prior_carry: TwoDeploymentQualificationCarryBundle,
    prior_authorization: TwoDeploymentQualificationAuthorizationBundle,
    prior_result: TwoDeploymentQualificationResult,
    prior_receipt: TwoDeploymentQualificationAggregateReceipt,
    prior_states: Sequence[TwoDeploymentCandidateExecutionState],
    source_suite: Phase4TogetherSuite,
    source_readiness: Phase4TogetherReadinessBundle,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    scope: TwoDeploymentQualificationScopeAmendment,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
) -> None:
    """Rebuild the aggregate proof from its exact private v1 sources."""

    rebuilt = build_qualification_attempt_v2_source_proof(
        prior_plan,
        prior_carry,
        prior_authorization,
        prior_result,
        prior_receipt,
        prior_states,
        source_suite,
        source_readiness,
        corrected_suite,
        corrected_readiness,
        profile,
        scope,
        fixture,
        session,
        proof_id=proof.proof_id,
        validated_at=proof.validated_at,
    )
    if rebuilt != proof:
        raise ValueError("qualification v2 source proof differs from rebuild")


def _v2_call_stage(
    entry: QualificationCallPlanEntry,
    capability_call_ids: set[str],
) -> QualificationAttemptStage:
    if (
        entry.coordinate.role in ATTEMPT_V2_READOUT_ROLES
        and entry.coordinate.variant_id is QualificationVariant.CANONICAL
        and entry.coordinate.call_id in capability_call_ids
    ):
        return QualificationAttemptStage.READOUT_CONFORMANCE
    return QualificationAttemptStage.FULL_QUALIFICATION


def build_qualification_attempt_v2_plan(
    proof: QualificationAttemptV2SourceProof,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    *,
    plan_id: str,
    created_at: datetime,
) -> QualificationAttemptV2Plan:
    """Build the public 304-coordinate plan without private response content."""

    if (
        proof.corrected_together_suite_sha256 != content_sha256(corrected_suite)
        or proof.corrected_readiness_sha256 != content_sha256(corrected_readiness)
        or corrected_readiness.together_suite_sha256
        != content_sha256(corrected_suite)
    ):
        raise ValueError("qualification v2 corrected sources differ")
    runnable_ids = sorted(proof.prior_candidate_state_sha256s)
    capability_ids = set(corrected_readiness.capability_preflight_call_ids)
    suite_candidates = {
        item.candidate.candidate_id: item
        for item in corrected_suite.candidates
    }
    candidate_plans: list[QualificationAttemptV2CandidatePlan] = []
    for candidate_id in runnable_ids:
        suite_candidate = suite_candidates.get(candidate_id)
        if suite_candidate is None:
            raise ValueError("qualification v2 candidate is outside suite")
        entries = [
            item
            for item in corrected_readiness.qualification_manifest.entries
            if item.coordinate.candidate_id == candidate_id
        ]
        calls: list[QualificationAttemptV2CallPlan] = []
        for entry in entries:
            calls.append(
                QualificationAttemptV2CallPlan(
                    source_manifest_ordinal=entry.coordinate.ordinal,
                    call_id=entry.coordinate.call_id,
                    candidate_id=candidate_id,
                    role=entry.coordinate.role,
                    measure_id=entry.coordinate.measure_id,
                    measure_version=entry.coordinate.measure_version,
                    variant_id=entry.coordinate.variant_id,
                    disposition=QualificationAttemptDisposition.EXECUTE_PROVIDER,
                    execution_stage=_v2_call_stage(entry, capability_ids),
                    source_entry_sha256=content_sha256(entry),
                    source_entry=entry.model_copy(deep=True),
                    projected_cost_microusd=entry.projected_cost_microusd,
                    authorized_max_cost_microusd=(
                        entry.authorized_max_cost_microusd
                    ),
                )
            )
        provider_calls = [
            item
            for item in calls
            if item.disposition is QualificationAttemptDisposition.EXECUTE_PROVIDER
        ]
        candidate_plans.append(
            QualificationAttemptV2CandidatePlan(
                candidate_id=candidate_id,
                candidate_sha256=content_sha256(suite_candidate.candidate),
                price_card_sha256=content_sha256(suite_candidate.price_card),
                calls=calls,
                provider_call_ids_sha256=content_sha256(
                    [item.call_id for item in provider_calls]
                ),
                new_projected_cost_microusd=sum(
                    item.projected_cost_microusd for item in provider_calls
                ),
                new_authorized_max_cost_microusd=sum(
                    item.authorized_max_cost_microusd for item in provider_calls
                ),
            )
        )
    all_provider = [
        item
        for candidate in candidate_plans
        for item in candidate.calls
        if item.disposition is QualificationAttemptDisposition.EXECUTE_PROVIDER
    ]
    execution_order = _expected_execution_order(candidate_plans)
    projected = sum(item.projected_cost_microusd for item in all_provider)
    authorized = sum(
        item.authorized_max_cost_microusd for item in all_provider
    )
    maximum = max(item.authorized_max_cost_microusd for item in all_provider)
    return QualificationAttemptV2Plan(
        plan_id=plan_id,
        created_at=created_at,
        source_proof_sha256=content_sha256(proof),
        prior_result_sha256=proof.prior_private_result_sha256,
        prior_scope_sha256=proof.prior_scope_sha256,
        corrected_together_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        corrected_qualification_manifest_sha256=content_sha256(
            corrected_readiness.qualification_manifest
        ),
        response_invariant_manifest_sha256=(
            proof.response_invariant_manifest_sha256
        ),
        response_behavior_spec_sha256=proof.response_behavior_spec_sha256,
        readout_validator_implementation_sha256=(
            proof.readout_validator_implementation_sha256
        ),
        json_decoder_policy_sha256=proof.json_decoder_policy_sha256,
        json_decoder_implementation_sha256=(
            proof.json_decoder_implementation_sha256
        ),
        together_json_decoder_integration_sha256=(
            proof.together_json_decoder_integration_sha256
        ),
        metric_policy_sha256=content_sha256(
            TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY
        ),
        policy=QUALIFICATION_ATTEMPT_V2_POLICY,
        policy_sha256=content_sha256(QUALIFICATION_ATTEMPT_V2_POLICY),
        candidate_plans=candidate_plans,
        execution_order_call_ids=execution_order,
        new_projected_cost_microusd=projected,
        new_authorized_max_cost_microusd=authorized,
        maximum_single_call_reservation_microusd=maximum,
        qualification_minimum_headroom_microusd=(
            corrected_readiness.headroom_policy
            .qualification_minimum_headroom_microusd
        ),
        cumulative_authorized_worst_case_microusd=(
            ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD + authorized
        ),
        sequential_projected_headroom_microusd=(
            QUALIFICATION_SEGMENT_CAP_MICROUSD
            - ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD
            - projected
            - maximum
        ),
    )


def validate_qualification_attempt_v2_plan(
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
) -> None:
    """Validate the public v2 plan against its exact corrected manifest."""

    if (
        plan.source_proof_sha256 != content_sha256(proof)
        or plan.prior_result_sha256 != proof.prior_private_result_sha256
        or plan.prior_scope_sha256 != proof.prior_scope_sha256
        or plan.corrected_together_suite_sha256
        != content_sha256(corrected_suite)
        or plan.corrected_readiness_sha256
        != content_sha256(corrected_readiness)
        or plan.corrected_qualification_manifest_sha256
        != content_sha256(corrected_readiness.qualification_manifest)
        or plan.qualification_minimum_headroom_microusd
        != corrected_readiness.headroom_policy
        .qualification_minimum_headroom_microusd
        or plan.response_invariant_manifest_sha256
        != proof.response_invariant_manifest_sha256
        or plan.response_behavior_spec_sha256
        != proof.response_behavior_spec_sha256
        or plan.readout_validator_implementation_sha256
        != proof.readout_validator_implementation_sha256
        or plan.json_decoder_policy_sha256
        != proof.json_decoder_policy_sha256
        or plan.json_decoder_implementation_sha256
        != proof.json_decoder_implementation_sha256
        or plan.together_json_decoder_integration_sha256
        != proof.together_json_decoder_integration_sha256
        or plan.metric_policy_sha256
        != content_sha256(TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY)
    ):
        raise ValueError("qualification v2 plan source bindings differ")
    if corrected_readiness.together_suite_sha256 != content_sha256(
        corrected_suite
    ):
        raise ValueError("qualification v2 readiness suite differs")
    expected_entries = {
        item.coordinate.call_id: item
        for item in corrected_readiness.qualification_manifest.entries
        if item.coordinate.candidate_id
        in proof.prior_candidate_state_sha256s
    }
    planned_calls = {
        item.call_id: item
        for candidate in plan.candidate_plans
        for item in candidate.calls
    }
    if len(planned_calls) != ATTEMPT_V2_COORDINATE_COUNT or set(
        planned_calls
    ) != set(expected_entries):
        raise ValueError("qualification v2 plan manifest surface differs")
    capability_ids = set(corrected_readiness.capability_preflight_call_ids)
    for call_id, call in planned_calls.items():
        entry = expected_entries[call_id]
        if (
            call.source_entry != entry
            or call.disposition
            is not QualificationAttemptDisposition.EXECUTE_PROVIDER
            or call.execution_stage
            is not _v2_call_stage(entry, capability_ids)
        ):
            raise ValueError("qualification v2 plan call differs")
    suite_by_id = {
        item.candidate.candidate_id: item
        for item in corrected_suite.candidates
    }
    for candidate in plan.candidate_plans:
        suite_candidate = suite_by_id.get(candidate.candidate_id)
        if suite_candidate is None or (
            candidate.candidate_sha256,
            candidate.price_card_sha256,
        ) != (
            content_sha256(suite_candidate.candidate),
            content_sha256(suite_candidate.price_card),
        ):
            raise ValueError("qualification v2 candidate binding differs")


def load_qualification_attempt_v2_source_proof(
    path: str | Path,
) -> QualificationAttemptV2SourceProof:
    return QualificationAttemptV2SourceProof.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_qualification_attempt_v2_plan(
    path: str | Path,
) -> QualificationAttemptV2Plan:
    return QualificationAttemptV2Plan.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
