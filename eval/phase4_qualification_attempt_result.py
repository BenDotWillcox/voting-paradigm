"""Assemble the audited result of qualification attempt v2.

The completed v1 result remains immutable.  This module consumes only the
reviewed v2 proof, plan, authorization, and terminal candidate states.  It
reuses the frozen development metrics, robustness comparisons, and banded
selection order without treating any historical output as carried evidence.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    Probability,
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
from .phase4_qualification import (
    PHASE4_QUALIFICATION_SELECTION_POLICY,
    QualificationSelectionPolicy,
)
from .phase4_qualification_attempt import (
    ATTEMPT_V2_COORDINATE_COUNT,
    ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE,
    QualificationAttemptV2CallPlan,
    QualificationAttemptV2Plan,
    QualificationAttemptV2SourceProof,
)
from .phase4_qualification_attempt_runtime import (
    GLOBAL_PAUSE_STATUSES,
    QualificationAttemptV2AuthorizationBundle,
    QualificationAttemptV2CandidateState,
    QualificationAttemptV2ExecutionStatus,
    validate_qualification_attempt_v2_authorization,
    validate_qualification_attempt_v2_execution_states,
)
from .phase4_qualification_execution import (
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY,
)
from .phase4_qualification_scope import (
    AMENDED_SCOPE_PAUSE_OUTCOMES,
    TwoDeploymentQualificationScopeAmendment,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    QualificationCallPlanEntry,
    QualificationVariant,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    OpenWeightModelCandidate,
    Phase4ERobustnessProfile,
    QualificationCriterion,
    RobustnessPerturbationKind,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .phase4_together_live import together_json_decoder_integration_sha256
from .phase4_two_deployment_result import (
    ExcludedDeploymentProvenance,
    InterviewerToolReplayStatus,
    QualificationCallObservation,
    QualificationCoordinateDisposition,
    QualificationCoordinateResult,
    QualificationDevelopmentMetrics,
    QualificationObservationSource,
    QualificationResultStatus,
    QualificationRobustnessSlice,
    build_qualification_development_metrics,
    build_qualification_robustness_slice,
    qualification_candidate_hard_failure_reasons,
    qualification_p95,
    select_two_deployment_candidate,
)
from .prequential import (
    PrequentialSessionScript,
    validate_session_script_against_fixture,
)


NonNegativeCount = Annotated[int, Field(ge=0)]
Microusd = Annotated[int, Field(ge=0)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]

ATTEMPT_V2_CANDIDATE_COUNT = 2
ATTEMPT_V2_ROBUSTNESS_SLICE_COUNT = 32
ATTEMPT_V2_ROBUSTNESS_SLICES_PER_CANDIDATE = 16
ATTEMPT_V2_COMPLETE_ROBUSTNESS_AGGREGATES_PER_CANDIDATE = 64
ATTEMPT_V2_EXPECTED_ROLE_COUNTS = {
    LLMRole.INTERVIEWER: 8,
    LLMRole.EVIDENCE_EXTRACTOR: 8,
    LLMRole.ONTOLOGY_PROPOSER: 8,
    LLMRole.DIRECT_READOUT: 64,
    LLMRole.HYBRID_READOUT: 64,
}
ATTEMPT_V2_PENDING_STATUSES = frozenset(
    {
        *GLOBAL_PAUSE_STATUSES,
        QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE,
    }
)


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


class QualificationAttemptV2ResultSourceBindings(ContractModel):
    """Exact private audits consumed by the v2 result assembler."""

    record_version: Literal[
        "phase4_qualification_attempt_result_sources.v2"
    ] = "phase4_qualification_attempt_result_sources.v2"
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    candidate_state_sha256s: dict[StableId, Sha256Digest]
    candidate_receipt_sha256s: dict[StableId, Sha256Digest]
    candidate_execution_statuses: dict[
        StableId,
        QualificationAttemptV2ExecutionStatus,
    ]

    @model_validator(mode="after")
    def require_exact_candidate_inventory(self) -> Self:
        inventories = (
            set(self.candidate_state_sha256s),
            set(self.candidate_receipt_sha256s),
            set(self.candidate_execution_statuses),
        )
        if any(item != inventories[0] for item in inventories[1:]) or len(
            inventories[0]
        ) != ATTEMPT_V2_CANDIDATE_COUNT:
            raise ValueError("qualification v2 result source inventory differs")
        return self


class QualificationAttemptV2CandidateResult(ContractModel):
    """Aggregate decision evidence for one runnable deployment."""

    record_version: Literal[
        "phase4_two_deployment_candidate_result.v2"
    ] = "phase4_two_deployment_candidate_result.v2"
    candidate_id: StableId
    candidate_version: Annotated[int, Field(ge=1)]
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    candidate_state_sha256: Sha256Digest
    attempt_status: QualificationAttemptV2ExecutionStatus
    coordinate_result_sha256s: list[Sha256Digest] = Field(
        min_length=ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE,
        max_length=ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE,
    )
    observation_sha256s: list[Sha256Digest] = Field(
        default_factory=list,
        max_length=ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE,
    )
    role_call_counts: dict[LLMRole, NonNegativeCount]
    carried_success_count: Literal[0] = 0
    new_provider_call_count: NonNegativeCount
    non_observed_coordinate_count: NonNegativeCount
    provider_pause_outcome_count: NonNegativeCount
    invalid_output_count: NonNegativeCount
    role_contract_failure_count: NonNegativeCount
    interviewer_tool_call_count: NonNegativeCount
    interviewer_tool_call_failure_count: NonNegativeCount
    interviewer_tool_replay_failure_count: NonNegativeCount
    historical_interviewer_replay_unverifiable_count: Literal[0] = 0
    robustness_slice_sha256s: list[Sha256Digest] = Field(
        min_length=ATTEMPT_V2_ROBUSTNESS_SLICES_PER_CANDIDATE,
        max_length=ATTEMPT_V2_ROBUSTNESS_SLICES_PER_CANDIDATE,
    )
    robustness_aggregate_count: NonNegativeCount
    robustness_invalid_output_count: NonNegativeCount
    strict_transform_top_choice_flip_count: NonNegativeCount
    direct_development_metrics: QualificationDevelopmentMetrics | None = None
    hybrid_development_metrics: QualificationDevelopmentMetrics | None = None
    selection_mean_log_loss: NonNegativeFiniteFloat | None = None
    prompt_and_stochastic_mean_jsd: Probability | None = None
    held_out_projected_cost_microusd: Microusd
    held_out_cap_microusd: Microusd
    qualification_cost_microusd: Microusd
    p95_latency_ms: NonNegativeFiniteFloat
    hard_failure_reasons: list[StableId]
    passed_hard_gates: bool | None

    @model_validator(mode="after")
    def require_exact_candidate_surface(self) -> Self:
        if len(self.coordinate_result_sha256s) != len(
            set(self.coordinate_result_sha256s)
        ) or len(self.observation_sha256s) != len(
            set(self.observation_sha256s)
        ):
            raise ValueError("qualification v2 candidate evidence is duplicated")
        if set(self.role_call_counts) != set(ATTEMPT_V2_EXPECTED_ROLE_COUNTS):
            raise ValueError("qualification v2 role inventory differs")
        if any(
            self.role_call_counts[role] > maximum
            for role, maximum in ATTEMPT_V2_EXPECTED_ROLE_COUNTS.items()
        ):
            raise ValueError("qualification v2 role count exceeds its matrix")
        observed = len(self.observation_sha256s)
        if (
            sum(self.role_call_counts.values()) != observed
            or self.new_provider_call_count != observed
            or self.non_observed_coordinate_count
            != ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE - observed
        ):
            raise ValueError("qualification v2 candidate counts differ")
        if self.attempt_status is QualificationAttemptV2ExecutionStatus.COMPLETED and (
            self.non_observed_coordinate_count != 0
        ):
            raise ValueError("completed qualification v2 candidate is partial")
        if len(self.robustness_slice_sha256s) != len(
            set(self.robustness_slice_sha256s)
        ):
            raise ValueError("qualification v2 robustness slices are duplicated")
        metrics = (
            self.direct_development_metrics,
            self.hybrid_development_metrics,
        )
        if all(item is not None for item in metrics):
            direct, hybrid = metrics
            if direct is None or hybrid is None:  # pragma: no cover
                raise ValueError("qualification v2 metrics differ")
            if (
                direct.candidate_id != self.candidate_id
                or hybrid.candidate_id != self.candidate_id
                or direct.readout_role is not LLMRole.DIRECT_READOUT
                or hybrid.readout_role is not LLMRole.HYBRID_READOUT
            ):
                raise ValueError("qualification v2 metric binding differs")
            expected_log_loss = fmean(
                [direct.mean_log_loss, hybrid.mean_log_loss]
            )
            if self.selection_mean_log_loss is None or not math.isclose(
                self.selection_mean_log_loss,
                expected_log_loss,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("qualification v2 selection log loss differs")
        elif any(item is not None for item in metrics) or (
            self.selection_mean_log_loss is not None
        ):
            raise ValueError("qualification v2 metrics are partial")
        expected_reasons: list[str] = []
        if any(count == 0 for count in self.role_call_counts.values()):
            expected_reasons.append("required_role_missing")
        if self.invalid_output_count:
            expected_reasons.append("invalid_structured_output")
        if self.role_contract_failure_count:
            expected_reasons.append("role_contract_failure")
        if self.interviewer_tool_call_failure_count:
            expected_reasons.append("interviewer_tool_call_failure")
        if self.interviewer_tool_replay_failure_count:
            expected_reasons.append("interviewer_tool_replay_failure")
        if self.interviewer_tool_call_count == 0:
            expected_reasons.append("interviewer_tool_not_exercised")
        if self.robustness_invalid_output_count:
            expected_reasons.append("robustness_invalid_output")
        if self.strict_transform_top_choice_flip_count:
            expected_reasons.append("strict_transform_top_choice_flip")
        if self.held_out_projected_cost_microusd > self.held_out_cap_microusd:
            expected_reasons.append("projected_study_cost_over_cap")
        if (
            self.attempt_status
            is QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
        ) != bool(self.provider_pause_outcome_count):
            raise ValueError("qualification v2 provider-pause count differs")
        pending = self.attempt_status in ATTEMPT_V2_PENDING_STATUSES
        if pending:
            if self.passed_hard_gates is not None or self.hard_failure_reasons:
                raise ValueError("paused qualification v2 candidate has a verdict")
        elif self.hard_failure_reasons != expected_reasons:
            raise ValueError("qualification v2 hard-failure reasons differ")
        elif (
            self.attempt_status
            is QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
        ):
            if self.passed_hard_gates is not False or not self.hard_failure_reasons:
                raise ValueError("qualification v2 hard failure lacks a reason")
        elif self.passed_hard_gates != (not self.hard_failure_reasons):
            raise ValueError("qualification v2 candidate gate verdict differs")
        if self.passed_hard_gates and (
            self.attempt_status is not QualificationAttemptV2ExecutionStatus.COMPLETED
            or self.role_call_counts != ATTEMPT_V2_EXPECTED_ROLE_COUNTS
            or self.selection_mean_log_loss is None
            or self.prompt_and_stochastic_mean_jsd is None
            or self.robustness_aggregate_count
            != ATTEMPT_V2_COMPLETE_ROBUSTNESS_AGGREGATES_PER_CANDIDATE
        ):
            raise ValueError("passing qualification v2 candidate lacks metrics")
        return self


class QualificationAttemptV2Result(ContractModel):
    """Private result over the two reviewed, runnable deployments."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_attempt_result.v2"
    ] = "preference_eval_phase4_two_deployment_qualification_attempt_result.v2"
    qualification_id: StableId
    qualification_version: Literal[2] = 2
    created_at: datetime
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    result_source_bindings_sha256: Sha256Digest
    result_source_bindings: QualificationAttemptV2ResultSourceBindings
    prior_scope_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    public_development_semantic_map_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    response_invariant_manifest_sha256: Sha256Digest
    response_behavior_spec_sha256: Sha256Digest
    readout_validator_implementation_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    candidates: list[OpenWeightModelCandidate] = Field(
        min_length=ATTEMPT_V2_CANDIDATE_COUNT,
        max_length=ATTEMPT_V2_CANDIDATE_COUNT,
    )
    excluded_deployment: ExcludedDeploymentProvenance
    coordinate_results: list[QualificationCoordinateResult] = Field(
        min_length=ATTEMPT_V2_COORDINATE_COUNT,
        max_length=ATTEMPT_V2_COORDINATE_COUNT,
    )
    observations: list[QualificationCallObservation] = Field(
        default_factory=list,
        max_length=ATTEMPT_V2_COORDINATE_COUNT,
    )
    robustness_slices: list[QualificationRobustnessSlice] = Field(
        min_length=ATTEMPT_V2_ROBUSTNESS_SLICE_COUNT,
        max_length=ATTEMPT_V2_ROBUSTNESS_SLICE_COUNT,
    )
    candidate_results: list[QualificationAttemptV2CandidateResult] = Field(
        min_length=ATTEMPT_V2_CANDIDATE_COUNT,
        max_length=ATTEMPT_V2_CANDIDATE_COUNT,
    )
    selection_criteria_in_priority_order: list[QualificationCriterion]
    selection_policy: QualificationSelectionPolicy
    status: QualificationResultStatus
    selected_candidate_id: StableId | None = None
    conclusion_limited_to_compared_deployments: Literal[True] = True
    excluded_deployment_remains_inconclusive: Literal[True] = True
    excluded_model_family_rejection_forbidden: Literal[True] = True
    post_hoc_replacement_forbidden: Literal[True] = True
    winner_not_guaranteed: Literal[True] = True
    participant_content_visible_to_provider: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification v2 result time")

    @model_validator(mode="after")
    def require_exact_bindings_and_selection(self) -> Self:
        if self.result_source_bindings_sha256 != content_sha256(
            self.result_source_bindings
        ) or (
            self.source_proof_sha256,
            self.execution_plan_sha256,
            self.authorization_bundle_sha256,
        ) != (
            self.result_source_bindings.source_proof_sha256,
            self.result_source_bindings.execution_plan_sha256,
            self.result_source_bindings.authorization_bundle_sha256,
        ):
            raise ValueError("qualification v2 result-source binding differs")
        implementation_bindings = (
            self.response_invariant_manifest_sha256,
            self.response_behavior_spec_sha256,
            self.readout_validator_implementation_sha256,
            self.json_decoder_policy_sha256,
            self.json_decoder_implementation_sha256,
            self.together_json_decoder_integration_sha256,
            self.metric_policy_sha256,
        )
        current_bindings = (
            content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3),
            content_sha256(PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3),
            provider_response_readout_validator_implementation_sha256(),
            content_sha256(PROVIDER_RESPONSE_JSON_DECODER_POLICY),
            provider_response_json_decoder_implementation_sha256(),
            together_json_decoder_integration_sha256(),
            content_sha256(TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY),
        )
        if implementation_bindings != current_bindings:
            raise ValueError("qualification v2 result implementation differs")
        candidate_ids = [item.candidate_id for item in self.candidates]
        if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != 2:
            raise ValueError("qualification v2 result candidates differ")
        if self.excluded_deployment.candidate_id in candidate_ids:
            raise ValueError("qualification v2 includes excluded deployment")
        observation_ids = [item.call_id for item in self.observations]
        coordinate_ids = [item.call_id for item in self.coordinate_results]
        if len(observation_ids) != len(set(observation_ids)) or len(
            coordinate_ids
        ) != len(set(coordinate_ids)):
            raise ValueError("qualification v2 result coordinates are duplicated")
        if any(
            item.source is not QualificationObservationSource.NEW_QUALIFICATION_CALL
            for item in self.observations
        ) or any(
            item.disposition is QualificationCoordinateDisposition.CARRIED_SUCCESS
            for item in self.coordinate_results
        ):
            raise ValueError("qualification v2 result cannot carry observations")
        coordinate_observations = {
            item.call_id: item.observation_sha256
            for item in self.coordinate_results
            if item.observation_sha256 is not None
        }
        if coordinate_observations != {
            item.call_id: content_sha256(item) for item in self.observations
        }:
            raise ValueError("qualification v2 coordinate evidence differs")
        if [item.candidate_id for item in self.candidate_results] != candidate_ids:
            raise ValueError("qualification v2 candidate results differ")
        if {
            item.candidate_id: item.candidate_state_sha256
            for item in self.candidate_results
        } != self.result_source_bindings.candidate_state_sha256s or {
            item.candidate_id: item.attempt_status
            for item in self.candidate_results
        } != self.result_source_bindings.candidate_execution_statuses:
            raise ValueError("qualification v2 candidate-state results differ")
        for candidate_result in self.candidate_results:
            candidate_id = candidate_result.candidate_id
            if candidate_result.coordinate_result_sha256s != [
                content_sha256(item)
                for item in self.coordinate_results
                if item.candidate_id == candidate_id
            ] or candidate_result.observation_sha256s != [
                content_sha256(item)
                for item in self.observations
                if item.candidate_id == candidate_id
            ]:
                raise ValueError("qualification v2 candidate evidence differs")
        slice_keys = [
            (item.candidate_id, item.readout_role, item.measure_id)
            for item in self.robustness_slices
        ]
        if len(slice_keys) != len(set(slice_keys)) or set(
            item.candidate_id for item in self.robustness_slices
        ) != set(candidate_ids):
            raise ValueError("qualification v2 robustness slices differ")
        if self.selection_criteria_in_priority_order != list(
            QualificationCriterion
        ) or self.selection_policy != PHASE4_QUALIFICATION_SELECTION_POLICY:
            raise ValueError("qualification v2 selection criteria differ")
        paused = any(
            status in ATTEMPT_V2_PENDING_STATUSES
            for status in (
                self.result_source_bindings.candidate_execution_statuses.values()
            )
        )
        eligible = [
            item for item in self.candidate_results if item.passed_hard_gates is True
        ]
        if paused:
            if (
                self.status
                is not QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
                or self.selected_candidate_id is not None
            ):
                raise ValueError("qualification v2 pause cannot select")
        elif not eligible:
            if (
                self.status
                is not QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
                or self.selected_candidate_id is not None
            ):
                raise ValueError("qualification v2 failures cannot select")
        else:
            selected = select_two_deployment_candidate(
                eligible,
                self.selection_policy,
            )
            if (
                self.status is not QualificationResultStatus.SELECTED
                or self.selected_candidate_id != selected.candidate_id
            ):
                raise ValueError("qualification v2 selection differs")
        return self


class QualificationAttemptV2CandidateAggregate(ContractModel):
    """Tracked-eligible candidate summary without per-call payloads."""

    candidate_id: StableId
    candidate_sha256: Sha256Digest
    candidate_state_sha256: Sha256Digest
    attempt_status: QualificationAttemptV2ExecutionStatus
    observed_call_count: NonNegativeCount
    unattempted_call_count: NonNegativeCount
    provider_spend_microusd: Microusd
    invalid_output_count: NonNegativeCount
    robustness_aggregate_count: NonNegativeCount
    selection_mean_log_loss: NonNegativeFiniteFloat | None = None
    prompt_and_stochastic_mean_jsd: Probability | None = None
    held_out_projected_cost_microusd: Microusd
    p95_latency_ms: NonNegativeFiniteFloat
    hard_failure_reasons: list[StableId]
    passed_hard_gates: bool | None

    @model_validator(mode="after")
    def require_reconciled_coordinate_count(self) -> Self:
        if self.observed_call_count + self.unattempted_call_count != (
            ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE
        ):
            raise ValueError("qualification v2 aggregate calls differ")
        pending = self.attempt_status in ATTEMPT_V2_PENDING_STATUSES
        if pending and (
            self.passed_hard_gates is not None or self.hard_failure_reasons
        ):
            raise ValueError("qualification v2 aggregate pause has a verdict")
        if (
            self.attempt_status
            is QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
        ) and (
            self.passed_hard_gates is not False or not self.hard_failure_reasons
        ):
            raise ValueError("qualification v2 aggregate hard failure differs")
        return self


class QualificationAttemptV2AggregateReceipt(ContractModel):
    """Aggregate-only public result with no provider or model payloads."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_attempt_receipt.v2"
    ] = "preference_eval_phase4_two_deployment_qualification_attempt_receipt.v2"
    receipt_id: StableId
    receipt_version: Literal[2] = 2
    created_at: datetime
    private_result_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    result_source_bindings_sha256: Sha256Digest
    prior_scope_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    public_development_semantic_map_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    response_invariant_manifest_sha256: Sha256Digest
    response_behavior_spec_sha256: Sha256Digest
    readout_validator_implementation_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    candidate_results: list[QualificationAttemptV2CandidateAggregate] = Field(
        min_length=ATTEMPT_V2_CANDIDATE_COUNT,
        max_length=ATTEMPT_V2_CANDIDATE_COUNT,
    )
    excluded_deployment: ExcludedDeploymentProvenance
    coordinate_result_count: Literal[304] = ATTEMPT_V2_COORDINATE_COUNT
    observation_count: NonNegativeCount
    unattempted_coordinate_count: NonNegativeCount
    robustness_slice_count: Literal[32] = ATTEMPT_V2_ROBUSTNESS_SLICE_COUNT
    robustness_aggregate_count: NonNegativeCount
    qualified_candidate_count: NonNegativeCount
    qualification_cost_microusd: Microusd
    prior_actual_spend_microusd: Literal[97_287] = 97_287
    cumulative_actual_spend_microusd: Microusd
    status: QualificationResultStatus
    selected_candidate_id: StableId | None = None
    conclusion_limited_to_compared_deployments: Literal[True] = True
    excluded_deployment_remains_inconclusive: Literal[True] = True
    parsed_provider_outputs_omitted: Literal[True] = True
    provider_request_and_response_text_omitted: Literal[True] = True
    private_paths_omitted: Literal[True] = True
    participant_content_present: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification v2 receipt time")

    @model_validator(mode="after")
    def require_reconciled_aggregate(self) -> Self:
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
            raise ValueError("qualification v2 receipt implementation differs")
        if self.observation_count + self.unattempted_coordinate_count != (
            self.coordinate_result_count
        ) or self.qualification_cost_microusd + (
            self.prior_actual_spend_microusd
        ) != self.cumulative_actual_spend_microusd:
            raise ValueError("qualification v2 receipt totals differ")
        candidate_ids = [item.candidate_id for item in self.candidate_results]
        if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != 2:
            raise ValueError("qualification v2 receipt candidates differ")
        if self.excluded_deployment.candidate_id in candidate_ids:
            raise ValueError("qualification v2 receipt includes excluded deployment")
        if self.qualified_candidate_count != sum(
            item.passed_hard_gates is True for item in self.candidate_results
        ) or self.observation_count != sum(
            item.observed_call_count for item in self.candidate_results
        ) or self.robustness_aggregate_count != sum(
            item.robustness_aggregate_count for item in self.candidate_results
        ) or self.qualification_cost_microusd != sum(
            item.provider_spend_microusd for item in self.candidate_results
        ):
            raise ValueError("qualification v2 receipt qualified count differs")
        paused = any(
            item.attempt_status in ATTEMPT_V2_PENDING_STATUSES
            for item in self.candidate_results
        )
        eligible = [
            item for item in self.candidate_results if item.passed_hard_gates is True
        ]
        if paused:
            if (
                self.status
                is not QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
                or self.selected_candidate_id is not None
            ):
                raise ValueError("qualification v2 receipt pause differs")
        elif not eligible:
            if (
                self.status
                is not QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
                or self.selected_candidate_id is not None
            ):
                raise ValueError("qualification v2 receipt failures differ")
        else:
            selected = select_two_deployment_candidate(
                eligible,
                PHASE4_QUALIFICATION_SELECTION_POLICY,
            )
            if (
                self.status is not QualificationResultStatus.SELECTED
                or self.selected_candidate_id != selected.candidate_id
            ):
                raise ValueError("qualification v2 receipt selection differs")
        return self


def _plan_calls_by_id(
    plan: QualificationAttemptV2Plan,
) -> dict[str, QualificationAttemptV2CallPlan]:
    calls = {
        call.call_id: call
        for candidate in plan.candidate_plans
        for call in candidate.calls
    }
    if len(calls) != ATTEMPT_V2_COORDINATE_COUNT:
        raise ValueError("qualification v2 result plan calls differ")
    return calls


def _state_observations(
    plan: QualificationAttemptV2Plan,
    states: Sequence[QualificationAttemptV2CandidateState],
) -> list[QualificationCallObservation]:
    calls = _plan_calls_by_id(plan)
    observations: list[QualificationCallObservation] = []
    for state in states:
        bindings = {
            item.call_id: item for item in state.provider_journal.request_bindings
        }
        authorizations = {
            item.call_id: item for item in state.provider_ledger.authorizations
        }
        usages = {item.call_id: item for item in state.provider_ledger.calls}
        outputs = {item.call_id: item for item in state.outputs}
        replay_counts = Counter(
            item.call_id for item in state.tool_replay_records
        )
        for finalization in state.provider_journal.finalizations:
            call = calls.get(finalization.call_id)
            if call is None or call.candidate_id != state.candidate_id:
                raise ValueError("qualification v2 observation is unplanned")
            try:
                binding = bindings[call.call_id]
                authorization = authorizations[call.call_id]
                usage = usages[call.call_id]
            except KeyError as error:  # pragma: no cover - state validator owns it
                raise ValueError(
                    "qualification v2 provider audit is incomplete"
                ) from error
            if (
                finalization.authorization_sha256
                != content_sha256(authorization)
                or usage.authorization_sha256 != content_sha256(authorization)
            ):
                raise ValueError("qualification v2 authorization lineage differs")
            successful = finalization.outcome in {
                ProviderCallOutcome.SUCCESS,
                ProviderCallOutcome.CACHE_HIT,
            }
            output = outputs.get(call.call_id)
            if successful != (output is not None):
                raise ValueError("qualification v2 output coverage differs")
            if call.role is LLMRole.INTERVIEWER:
                replay_status = (
                    InterviewerToolReplayStatus.VERIFIED
                    if (
                        finalization.tool_call_count > 0
                        and finalization.tool_call_failure_count == 0
                        and replay_counts[call.call_id]
                        == finalization.tool_call_count
                    )
                    else InterviewerToolReplayStatus.FAILED
                )
            else:
                replay_status = InterviewerToolReplayStatus.NOT_APPLICABLE
            observations.append(
                QualificationCallObservation(
                    source_manifest_ordinal=call.source_manifest_ordinal,
                    source_entry_sha256=call.source_entry_sha256,
                    call_id=call.call_id,
                    candidate_id=call.candidate_id,
                    measure_id=call.measure_id,
                    measure_version=call.measure_version,
                    role=call.role,
                    variant_id=call.variant_id,
                    source=QualificationObservationSource.NEW_QUALIFICATION_CALL,
                    request_binding=binding,
                    request_binding_sha256=content_sha256(binding),
                    request_content_sha256=usage.request_sha256,
                    usage=usage,
                    usage_sha256=content_sha256(usage),
                    finalization=finalization,
                    finalization_sha256=content_sha256(finalization),
                    output_sha256=(output.output_sha256 if output else None),
                    parsed_output=(output.output_payload if output else None),
                    exact_role_contract_valid=(
                        True
                        if successful
                        else (
                            False
                            if finalization.outcome
                            is ProviderCallOutcome.INVALID_OUTPUT
                            else None
                        )
                    ),
                    interviewer_tool_replay_status=replay_status,
                )
            )
    observations.sort(key=lambda item: item.source_manifest_ordinal)
    if len({item.call_id for item in observations}) != len(observations):
        raise ValueError("qualification v2 observations are duplicated")
    return observations


def _coordinate_disposition(
    state: QualificationAttemptV2CandidateState,
) -> QualificationCoordinateDisposition:
    if state.status is (
        QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
    ):
        return QualificationCoordinateDisposition.UNATTEMPTED_HARD_FAILURE
    global_status = state.global_stop_status
    if global_status is QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE:
        return QualificationCoordinateDisposition.UNATTEMPTED_PROVIDER_PAUSE
    if global_status is (
        QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
    ):
        return QualificationCoordinateDisposition.UNATTEMPTED_AMBIGUOUS
    if global_status is QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE:
        return QualificationCoordinateDisposition.UNATTEMPTED_HARNESS_PAUSE
    raise ValueError("qualification v2 terminal state misses a coordinate")


def _build_coordinate_results(
    plan: QualificationAttemptV2Plan,
    states: Mapping[str, QualificationAttemptV2CandidateState],
    observations: Sequence[QualificationCallObservation],
) -> list[QualificationCoordinateResult]:
    observations_by_id = {item.call_id: item for item in observations}
    results: list[QualificationCoordinateResult] = []
    calls = sorted(
        _plan_calls_by_id(plan).values(),
        key=lambda item: item.source_manifest_ordinal,
    )
    for call in calls:
        observation = observations_by_id.get(call.call_id)
        if observation is not None:
            disposition = QualificationCoordinateDisposition.OBSERVED
        elif (
            states[call.candidate_id].global_stop_status
            is QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
            and states[call.candidate_id].global_stop_call_id == call.call_id
        ):
            disposition = QualificationCoordinateDisposition.AMBIGUOUS_DELIVERY
        else:
            disposition = _coordinate_disposition(states[call.candidate_id])
        results.append(
            QualificationCoordinateResult(
                source_manifest_ordinal=call.source_manifest_ordinal,
                source_entry_sha256=call.source_entry_sha256,
                call_id=call.call_id,
                candidate_id=call.candidate_id,
                measure_id=call.measure_id,
                measure_version=call.measure_version,
                role=call.role,
                variant_id=call.variant_id,
                disposition=disposition,
                observation_sha256=(
                    content_sha256(observation) if observation is not None else None
                ),
            )
        )
    return results


def _build_candidate_result(
    candidate: OpenWeightModelCandidate,
    observations: list[QualificationCallObservation],
    coordinate_results: list[QualificationCoordinateResult],
    slices: list[QualificationRobustnessSlice],
    *,
    state: QualificationAttemptV2CandidateState,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    price_card_sha256: str,
) -> QualificationAttemptV2CandidateResult:
    role_counts = Counter(item.role for item in observations)
    normalized_role_counts = {role: role_counts[role] for role in LLMRole}
    invalid_count = sum(
        item.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
        for item in observations
    )
    role_failures = sum(
        item.exact_role_contract_valid is False for item in observations
    )
    interviewer = [item for item in observations if item.role is LLMRole.INTERVIEWER]
    replay_failures = sum(
        item.interviewer_tool_replay_status is InterviewerToolReplayStatus.FAILED
        for item in interviewer
    )
    tool_calls = sum(item.finalization.tool_call_count for item in interviewer)
    tool_failures = sum(
        item.finalization.tool_call_failure_count for item in interviewer
    )
    robustness_invalid = sum(
        not prediction.output_valid
        for item in slices
        for prediction in item.predictions
    )
    strict_flips = sum(
        aggregate.top_choice_flip_count
        for item in slices
        for aggregate in item.aggregates
        if aggregate.perturbation_kind
        in {
            RobustnessPerturbationKind.OPTION_ORDER,
            RobustnessPerturbationKind.OPTION_LABEL,
        }
    )
    direct_metrics = build_qualification_development_metrics(
        candidate.candidate_id,
        LLMRole.DIRECT_READOUT,
        slices,
        fixture,
        session,
    )
    hybrid_metrics = build_qualification_development_metrics(
        candidate.candidate_id,
        LLMRole.HYBRID_READOUT,
        slices,
        fixture,
        session,
    )
    sensitivity_by_slice: list[float] = []
    for item in slices:
        by_kind = {
            aggregate.perturbation_kind: aggregate
            for aggregate in item.aggregates
        }
        prompt = by_kind.get(RobustnessPerturbationKind.PROMPT_PARAPHRASE)
        stochastic = by_kind.get(RobustnessPerturbationKind.STOCHASTIC_REPEAT)
        if (
            prompt is None
            or stochastic is None
            or prompt.mean_jensen_shannon_divergence is None
            or stochastic.mean_jensen_shannon_divergence is None
        ):
            sensitivity_by_slice = []
            break
        sensitivity_by_slice.append(
            fmean(
                [
                    prompt.mean_jensen_shannon_divergence,
                    stochastic.mean_jensen_shannon_divergence,
                ]
            )
        )
    projection = next(
        item
        for item in readiness.token_readiness_receipt.candidate_projections
        if item.candidate_id == candidate.candidate_id
    )
    derived_reasons = qualification_candidate_hard_failure_reasons(
        role_counts=normalized_role_counts,
        invalid_output_count=invalid_count,
        role_contract_failure_count=role_failures,
        interviewer_tool_call_failure_count=tool_failures,
        interviewer_tool_replay_failure_count=replay_failures,
        interviewer_tool_call_count=tool_calls,
        robustness_invalid_output_count=robustness_invalid,
        strict_transform_top_choice_flip_count=strict_flips,
        held_out_projected_cost_microusd=(
            projection.held_out_projected_cost_microusd
        ),
        profile=profile,
    )
    pending = state.status in ATTEMPT_V2_PENDING_STATUSES
    reasons = [] if pending else derived_reasons
    return QualificationAttemptV2CandidateResult(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.artifact_version,
        candidate_sha256=content_sha256(candidate),
        price_card_sha256=price_card_sha256,
        candidate_state_sha256=content_sha256(state),
        attempt_status=state.status,
        coordinate_result_sha256s=[
            content_sha256(item) for item in coordinate_results
        ],
        observation_sha256s=[content_sha256(item) for item in observations],
        role_call_counts=normalized_role_counts,
        new_provider_call_count=len(observations),
        non_observed_coordinate_count=(
            ATTEMPT_V2_PROVIDER_CALLS_PER_CANDIDATE - len(observations)
        ),
        provider_pause_outcome_count=sum(
            item.finalization.outcome in set(AMENDED_SCOPE_PAUSE_OUTCOMES)
            for item in observations
        ),
        invalid_output_count=invalid_count,
        role_contract_failure_count=role_failures,
        interviewer_tool_call_count=tool_calls,
        interviewer_tool_call_failure_count=tool_failures,
        interviewer_tool_replay_failure_count=replay_failures,
        robustness_slice_sha256s=[content_sha256(item) for item in slices],
        robustness_aggregate_count=sum(len(item.aggregates) for item in slices),
        robustness_invalid_output_count=robustness_invalid,
        strict_transform_top_choice_flip_count=strict_flips,
        direct_development_metrics=direct_metrics,
        hybrid_development_metrics=hybrid_metrics,
        selection_mean_log_loss=(
            fmean([direct_metrics.mean_log_loss, hybrid_metrics.mean_log_loss])
            if direct_metrics is not None and hybrid_metrics is not None
            else None
        ),
        prompt_and_stochastic_mean_jsd=(
            fmean(sensitivity_by_slice)
            if len(sensitivity_by_slice)
            == ATTEMPT_V2_ROBUSTNESS_SLICES_PER_CANDIDATE
            else None
        ),
        held_out_projected_cost_microusd=(
            projection.held_out_projected_cost_microusd
        ),
        held_out_cap_microusd=profile.budget_policy.segment_caps_microusd[
            BudgetSegment.HELD_OUT_STUDY
        ],
        qualification_cost_microusd=sum(
            item.usage.billed_cost_microusd for item in observations
        ),
        p95_latency_ms=qualification_p95(
            [item.finalization.latency_ms for item in observations]
        ),
        hard_failure_reasons=reasons,
        passed_hard_gates=(
            None
            if pending
            else (
                False
                if state.status
                is QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
                else not reasons
            )
        ),
    )


def _result_source_bindings(
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    authorization: QualificationAttemptV2AuthorizationBundle,
    states: Mapping[str, QualificationAttemptV2CandidateState],
) -> QualificationAttemptV2ResultSourceBindings:
    receipt_hashes: dict[str, str] = {}
    for candidate_id, state in states.items():
        if state.receipt is None:
            raise ValueError("qualification v2 result requires terminal receipts")
        receipt_hashes[candidate_id] = content_sha256(state.receipt)
    return QualificationAttemptV2ResultSourceBindings(
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        candidate_state_sha256s={
            candidate_id: content_sha256(state)
            for candidate_id, state in sorted(states.items())
        },
        candidate_receipt_sha256s={
            candidate_id: receipt_hashes[candidate_id]
            for candidate_id in sorted(receipt_hashes)
        },
        candidate_execution_statuses={
            candidate_id: state.status
            for candidate_id, state in sorted(states.items())
        },
    )


def _excluded_deployment(
    scope: TwoDeploymentQualificationScopeAmendment,
) -> ExcludedDeploymentProvenance:
    excluded = next(
        item
        for item in scope.deployment_scopes
        if item.candidate_id == scope.excluded_deployment_candidate_id
    )
    return ExcludedDeploymentProvenance(
        candidate_id=excluded.candidate_id,
        candidate_sha256=excluded.candidate_sha256,
        price_card_sha256=excluded.price_card_sha256,
        capability_outcome_sha256=excluded.capability_outcome_sha256,
    )


def build_qualification_attempt_v2_result(
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    authorization: QualificationAttemptV2AuthorizationBundle,
    states: Mapping[str, QualificationAttemptV2CandidateState],
    scope: TwoDeploymentQualificationScopeAmendment,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    catalog: TogetherCatalogPreflightBundle,
    *,
    qualification_id: str,
    created_at: datetime,
) -> QualificationAttemptV2Result:
    """Derive selection solely from the two exact terminal v2 state audits."""

    _require_aware(created_at, "qualification v2 result time")
    validate_session_script_against_fixture(session, fixture)
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
        now=authorization.manual_approval.approved_at,
    )
    validate_qualification_attempt_v2_execution_states(
        states,
        plan,
        proof,
        authorization,
        suite,
        profile,
    )
    if any(
        state.receipt is None or state.receipt.completed_at > created_at
        for state in states.values()
    ):
        raise ValueError("qualification v2 result predates terminal evidence")
    artifact_bindings = (
        plan.source_proof_sha256,
        plan.prior_scope_sha256,
        plan.corrected_together_suite_sha256,
        plan.corrected_readiness_sha256,
        plan.corrected_qualification_manifest_sha256,
        plan.metric_policy_sha256,
        authorization.robustness_profile_sha256,
        authorization.development_fixture_sha256,
        authorization.development_session_sha256,
        authorization.development_semantic_map_sha256,
    )
    expected_bindings = (
        content_sha256(proof),
        content_sha256(scope),
        content_sha256(suite),
        content_sha256(readiness),
        content_sha256(readiness.qualification_manifest),
        content_sha256(TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY),
        content_sha256(profile),
        content_sha256(fixture),
        content_sha256(session),
        content_sha256(semantic_map),
    )
    if artifact_bindings != expected_bindings or (
        proof.prior_scope_sha256 != content_sha256(scope)
    ):
        raise ValueError("qualification v2 result public bindings differ")
    candidate_ids = [item.candidate_id for item in plan.candidate_plans]
    if candidate_ids != scope.runnable_candidate_ids or set(states) != set(
        candidate_ids
    ):
        raise ValueError("qualification v2 result candidate scope differs")
    suite_by_id = {
        item.candidate.candidate_id: item for item in suite.candidates
    }
    candidates = [suite_by_id[item].candidate for item in candidate_ids]
    observations = _state_observations(plan, list(states.values()))
    coordinate_results = _build_coordinate_results(plan, states, observations)
    observations_by_id = {item.call_id: item for item in observations}
    coordinate_results_by_id = {
        item.call_id: item for item in coordinate_results
    }
    entries_by_slice: dict[
        tuple[str, LLMRole, str],
        list[QualificationCallPlanEntry],
    ] = defaultdict(list)
    for call in _plan_calls_by_id(plan).values():
        if call.role in {LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT}:
            entries_by_slice[(call.candidate_id, call.role, call.measure_id)].append(
                call.source_entry
            )
    slices: list[QualificationRobustnessSlice] = []
    for candidate in candidates:
        for role in (LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT):
            for measure in fixture.measures:
                entries = entries_by_slice[
                    (candidate.candidate_id, role, measure.measure_id)
                ]
                if len(entries) != len(QualificationVariant):
                    raise ValueError("qualification v2 robustness matrix differs")
                slices.append(
                    build_qualification_robustness_slice(
                        observations_by_id,
                        coordinate_results_by_id,
                        entries,
                        profile=profile,
                        candidate=candidate,
                        option_ids=[item.option_id for item in measure.options],
                    )
                )
    source_bindings = _result_source_bindings(
        proof,
        plan,
        authorization,
        states,
    )
    candidate_results: list[QualificationAttemptV2CandidateResult] = []
    for candidate in candidates:
        candidate_id = candidate.candidate_id
        candidate_results.append(
            _build_candidate_result(
                candidate,
                [
                    item for item in observations if item.candidate_id == candidate_id
                ],
                [
                    item
                    for item in coordinate_results
                    if item.candidate_id == candidate_id
                ],
                [item for item in slices if item.candidate_id == candidate_id],
                state=states[candidate_id],
                profile=profile,
                readiness=readiness,
                fixture=fixture,
                session=session,
                price_card_sha256=content_sha256(
                    suite_by_id[candidate_id].price_card
                ),
            )
        )
    paused = any(
        item.attempt_status in ATTEMPT_V2_PENDING_STATUSES
        for item in candidate_results
    )
    eligible = [
        item for item in candidate_results if item.passed_hard_gates is True
    ]
    selected = (
        select_two_deployment_candidate(
            eligible,
            scope.result_policy.selection_policy,
        )
        if eligible and not paused
        else None
    )
    status = (
        QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
        if paused
        else (
            QualificationResultStatus.SELECTED
            if selected is not None
            else QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
        )
    )
    return QualificationAttemptV2Result(
        qualification_id=qualification_id,
        created_at=created_at,
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        result_source_bindings_sha256=content_sha256(source_bindings),
        result_source_bindings=source_bindings,
        prior_scope_sha256=content_sha256(scope),
        robustness_profile_sha256=content_sha256(profile),
        together_suite_sha256=content_sha256(suite),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        metric_policy_sha256=content_sha256(
            TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY
        ),
        public_development_fixture_sha256=content_sha256(fixture),
        public_development_session_sha256=content_sha256(session),
        public_development_semantic_map_sha256=content_sha256(semantic_map),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        response_invariant_manifest_sha256=(
            plan.response_invariant_manifest_sha256
        ),
        response_behavior_spec_sha256=plan.response_behavior_spec_sha256,
        readout_validator_implementation_sha256=(
            plan.readout_validator_implementation_sha256
        ),
        json_decoder_policy_sha256=plan.json_decoder_policy_sha256,
        json_decoder_implementation_sha256=(
            plan.json_decoder_implementation_sha256
        ),
        together_json_decoder_integration_sha256=(
            plan.together_json_decoder_integration_sha256
        ),
        candidates=candidates,
        excluded_deployment=_excluded_deployment(scope),
        coordinate_results=coordinate_results,
        observations=observations,
        robustness_slices=slices,
        candidate_results=candidate_results,
        selection_criteria_in_priority_order=(
            scope.result_policy.selection_criteria_in_priority_order
        ),
        selection_policy=scope.result_policy.selection_policy,
        status=status,
        selected_candidate_id=(selected.candidate_id if selected else None),
    )


def validate_qualification_attempt_v2_result(
    result: QualificationAttemptV2Result,
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    authorization: QualificationAttemptV2AuthorizationBundle,
    states: Mapping[str, QualificationAttemptV2CandidateState],
    scope: TwoDeploymentQualificationScopeAmendment,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    catalog: TogetherCatalogPreflightBundle,
) -> None:
    """Rebuild the full result from its exact audited inputs."""

    rebuilt = build_qualification_attempt_v2_result(
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
        qualification_id=result.qualification_id,
        created_at=result.created_at,
    )
    if rebuilt != result:
        raise ValueError("qualification v2 result does not rebuild")


def _candidate_aggregate(
    result: QualificationAttemptV2CandidateResult,
) -> QualificationAttemptV2CandidateAggregate:
    return QualificationAttemptV2CandidateAggregate(
        candidate_id=result.candidate_id,
        candidate_sha256=result.candidate_sha256,
        candidate_state_sha256=result.candidate_state_sha256,
        attempt_status=result.attempt_status,
        observed_call_count=len(result.observation_sha256s),
        unattempted_call_count=result.non_observed_coordinate_count,
        provider_spend_microusd=result.qualification_cost_microusd,
        invalid_output_count=result.invalid_output_count,
        robustness_aggregate_count=result.robustness_aggregate_count,
        selection_mean_log_loss=result.selection_mean_log_loss,
        prompt_and_stochastic_mean_jsd=(
            result.prompt_and_stochastic_mean_jsd
        ),
        held_out_projected_cost_microusd=(
            result.held_out_projected_cost_microusd
        ),
        p95_latency_ms=result.p95_latency_ms,
        hard_failure_reasons=result.hard_failure_reasons,
        passed_hard_gates=result.passed_hard_gates,
    )


def build_qualification_attempt_v2_aggregate_receipt(
    result: QualificationAttemptV2Result,
    *,
    receipt_id: str,
) -> QualificationAttemptV2AggregateReceipt:
    """Project a tracked-eligible receipt from the exact private result."""

    candidate_results = [
        _candidate_aggregate(item) for item in result.candidate_results
    ]
    cost = sum(item.qualification_cost_microusd for item in result.candidate_results)
    return QualificationAttemptV2AggregateReceipt(
        receipt_id=receipt_id,
        created_at=result.created_at,
        private_result_sha256=content_sha256(result),
        source_proof_sha256=result.source_proof_sha256,
        execution_plan_sha256=result.execution_plan_sha256,
        authorization_bundle_sha256=result.authorization_bundle_sha256,
        result_source_bindings_sha256=result.result_source_bindings_sha256,
        prior_scope_sha256=result.prior_scope_sha256,
        robustness_profile_sha256=result.robustness_profile_sha256,
        together_suite_sha256=result.together_suite_sha256,
        readiness_sha256=result.readiness_sha256,
        source_qualification_manifest_sha256=(
            result.source_qualification_manifest_sha256
        ),
        metric_policy_sha256=result.metric_policy_sha256,
        public_development_fixture_sha256=(
            result.public_development_fixture_sha256
        ),
        public_development_session_sha256=(
            result.public_development_session_sha256
        ),
        public_development_semantic_map_sha256=(
            result.public_development_semantic_map_sha256
        ),
        catalog_preflight_bundle_sha256=result.catalog_preflight_bundle_sha256,
        response_invariant_manifest_sha256=(
            result.response_invariant_manifest_sha256
        ),
        response_behavior_spec_sha256=result.response_behavior_spec_sha256,
        readout_validator_implementation_sha256=(
            result.readout_validator_implementation_sha256
        ),
        json_decoder_policy_sha256=result.json_decoder_policy_sha256,
        json_decoder_implementation_sha256=(
            result.json_decoder_implementation_sha256
        ),
        together_json_decoder_integration_sha256=(
            result.together_json_decoder_integration_sha256
        ),
        candidate_results=candidate_results,
        excluded_deployment=result.excluded_deployment,
        observation_count=len(result.observations),
        unattempted_coordinate_count=sum(
            item.observation_sha256 is None for item in result.coordinate_results
        ),
        robustness_aggregate_count=sum(
            item.robustness_aggregate_count for item in result.candidate_results
        ),
        qualified_candidate_count=sum(
            item.passed_hard_gates is True for item in result.candidate_results
        ),
        qualification_cost_microusd=cost,
        cumulative_actual_spend_microusd=97_287 + cost,
        status=result.status,
        selected_candidate_id=result.selected_candidate_id,
    )


def validate_qualification_attempt_v2_aggregate_receipt(
    receipt: QualificationAttemptV2AggregateReceipt,
    result: QualificationAttemptV2Result,
) -> None:
    rebuilt = build_qualification_attempt_v2_aggregate_receipt(
        result,
        receipt_id=receipt.receipt_id,
    )
    if rebuilt != receipt:
        raise ValueError("qualification v2 aggregate receipt does not rebuild")


def qualification_attempt_v2_result_summary(
    result: QualificationAttemptV2Result,
) -> dict[str, JsonValue]:
    return {
        "schema_version": result.schema_version,
        "result_sha256": content_sha256(result),
        "candidate_count": len(result.candidate_results),
        "observation_count": len(result.observations),
        "unattempted_coordinate_count": sum(
            item.observation_sha256 is None for item in result.coordinate_results
        ),
        "qualified_candidate_count": sum(
            item.passed_hard_gates is True for item in result.candidate_results
        ),
        "status": result.status.value,
        "selected_candidate_id": result.selected_candidate_id,
        "qualification_cost_microusd": sum(
            item.qualification_cost_microusd for item in result.candidate_results
        ),
        "participant_content_present": False,
    }


def load_qualification_attempt_v2_result(
    path: str | Path,
) -> QualificationAttemptV2Result:
    return QualificationAttemptV2Result.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_qualification_attempt_v2_aggregate_receipt(
    path: str | Path,
) -> QualificationAttemptV2AggregateReceipt:
    return QualificationAttemptV2AggregateReceipt.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
