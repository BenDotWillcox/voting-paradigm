"""Distinct result contract for the amended two-deployment qualification.

The historical three-candidate qualification bundle remains frozen.  This
module consumes the reviewed two-deployment scope and the exact 304-call
public-development observation set, derives readout robustness and prediction
quality from the parsed provider outputs, and applies the scope's frozen
selection policy.  It has no provider client and cannot authorize spend.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from statistics import fmean
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    PositiveVersion,
    Probability,
    ResponseState,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_llm_readout import LLMReadoutResponseDraft
from .phase4_prediction import expected_top_option_id
from .phase4_provider import (
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderRequestBinding,
    provider_request_content_sha256,
)
from .phase4_qualification import QualificationSelectionPolicy
from .phase4_qualification_execution import (
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY,
    QualificationCallDisposition,
    TwoDeploymentQualificationExecutionPlan,
)
from .phase4_qualification_scope import (
    AMENDED_SCOPE_PAUSE_OUTCOMES,
    AMENDED_QUALIFICATION_HARD_FAILURE_REASONS,
    CARRIED_SUCCESS_COUNT,
    NEW_PROVIDER_CALL_COUNT,
    QUALIFICATION_ENTRIES_PER_CANDIDATE,
    RUNNABLE_CANDIDATE_COUNT,
    SCOPED_QUALIFICATION_ENTRY_COUNT,
    QualificationDeploymentScopeStatus,
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
    ProviderCallUsage,
    QualificationCriterion,
    RobustnessAggregate,
    RobustnessComparison,
    RobustnessPerturbationKind,
    RobustnessPrediction,
    aggregate_robustness_comparisons,
    build_robustness_evaluation_binding,
    compare_robustness_predictions,
)
from .phase4_together import Phase4TogetherSuite
from .prequential import (
    PrequentialSessionScript,
    validate_session_script_against_fixture,
)


NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]
BoundedBrierScore = Annotated[
    float,
    Field(ge=0.0, le=2.0, allow_inf_nan=False),
]

DEVELOPMENT_LOG_LOSS_EPSILON = (
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY.log_loss_probability_floor
)
DEVELOPMENT_RISK_THRESHOLDS = tuple(
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY.delegated_risk_thresholds
)
READOUT_ROLES = tuple(
    TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY.quality_roles_in_order
)
SUCCESS_OUTCOMES = frozenset(
    {ProviderCallOutcome.SUCCESS, ProviderCallOutcome.CACHE_HIT}
)
VARIANT_ORDER = tuple(QualificationVariant)
PERTURBATION_ORDER = tuple(RobustnessPerturbationKind)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class QualificationObservationSource(str, Enum):
    """Whether a call is replay-forbidden evidence or a newly paid call."""

    CARRIED_CAPABILITY_SUCCESS = "carried_capability_success"
    NEW_QUALIFICATION_CALL = "new_qualification_call"


class InterviewerToolReplayStatus(str, Enum):
    """Truthful replay status without upgrading historical evidence."""

    NOT_APPLICABLE = "not_applicable"
    VERIFIED = "verified"
    FAILED = "failed"
    HISTORICAL_UNVERIFIABLE = "historical_unverifiable"


class QualificationCandidateAttemptStatus(str, Enum):
    """Terminal runtime status copied without importing private state types."""

    COMPLETED = "completed"
    CANDIDATE_HARD_FAILURE = "candidate_hard_failure"
    PROVIDER_PAUSED = "provider_pause_pending_review"
    AMBIGUOUS_DELIVERY = "ambiguous_delivery_pending_reconciliation"
    HARNESS_PAUSED = "harness_pause_pending_review"


class QualificationCoordinateDisposition(str, Enum):
    """Terminal accounting for every one of the 304 scoped coordinates."""

    CARRIED_SUCCESS = "carried_success"
    OBSERVED = "observed"
    AMBIGUOUS_DELIVERY = "ambiguous_delivery"
    UNATTEMPTED_HARD_FAILURE = (
        "unattempted_after_candidate_hard_failure"
    )
    UNATTEMPTED_PROVIDER_PAUSE = "unattempted_after_provider_pause"
    UNATTEMPTED_AMBIGUOUS = (
        "unattempted_after_ambiguous_delivery"
    )
    UNATTEMPTED_HARNESS_PAUSE = "unattempted_after_harness_pause"


class QualificationResultSourceBindings(ContractModel):
    """Private execution artifacts the result assembler validated upstream."""

    record_version: Literal[
        "phase4_two_deployment_result_sources.v1"
    ] = "phase4_two_deployment_result_sources.v1"
    execution_plan_sha256: Sha256Digest
    carry_bundle_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    candidate_state_sha256s: dict[StableId, Sha256Digest]
    candidate_attempt_statuses: dict[
        StableId,
        QualificationCandidateAttemptStatus,
    ]

    @model_validator(mode="after")
    def require_matching_candidate_states(self) -> Self:
        if set(self.candidate_state_sha256s) != set(
            self.candidate_attempt_statuses
        ) or len(self.candidate_state_sha256s) != RUNNABLE_CANDIDATE_COUNT:
            raise ValueError("qualification result candidate-state bindings differ")
        return self


class QualificationCallObservation(ContractModel):
    """Exact content-free lineage plus a private parsed success payload."""

    record_version: Literal[
        "phase4_two_deployment_call_observation.v1"
    ] = "phase4_two_deployment_call_observation.v1"
    source_manifest_ordinal: PositiveCount
    source_entry_sha256: Sha256Digest
    call_id: StableId
    candidate_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    role: LLMRole
    variant_id: QualificationVariant
    source: QualificationObservationSource
    request_binding: ProviderRequestBinding
    request_binding_sha256: Sha256Digest
    request_content_sha256: Sha256Digest
    usage: ProviderCallUsage
    usage_sha256: Sha256Digest
    finalization: ProviderCallFinalization
    finalization_sha256: Sha256Digest
    output_sha256: Sha256Digest | None = None
    parsed_output: JsonValue | None = Field(default=None, repr=False)
    exact_role_contract_valid: bool | None = None
    interviewer_tool_replay_status: InterviewerToolReplayStatus

    @model_validator(mode="after")
    def require_exact_lineage_and_truthful_replay_status(self) -> Self:
        if self.request_binding_sha256 != content_sha256(self.request_binding):
            raise ValueError("qualification request-binding hash differs")
        if self.request_content_sha256 != provider_request_content_sha256(
            self.request_binding
        ):
            raise ValueError("qualification request-content hash differs")
        if self.usage_sha256 != content_sha256(self.usage):
            raise ValueError("qualification usage hash differs")
        if self.finalization_sha256 != content_sha256(self.finalization):
            raise ValueError("qualification finalization hash differs")
        identity = (self.call_id, self.candidate_id, self.role)
        if (
            self.request_binding.call_id,
            self.request_binding.model_candidate_id,
            self.request_binding.role,
        ) != identity:
            raise ValueError("qualification request identity differs")
        if self.request_binding.data_scope is not ProviderDataScope.PUBLIC_DEVELOPMENT:
            raise ValueError("qualification observation is not public development")
        if (
            self.usage.call_id,
            self.usage.model_candidate_id,
            self.usage.request_sha256,
        ) != (self.call_id, self.candidate_id, self.request_content_sha256):
            raise ValueError("qualification usage identity differs")
        if self.usage.segment is not BudgetSegment.QUALIFICATION or (
            self.usage.retry_of_call_id is not None
        ):
            raise ValueError("qualification observation cannot be a retry")
        if (
            self.finalization.call_id,
            self.finalization.request_binding_sha256,
            self.finalization.usage_sha256,
        ) != (self.call_id, self.request_binding_sha256, self.usage_sha256):
            raise ValueError("qualification finalization lineage differs")
        successful = self.finalization.outcome in SUCCESS_OUTCOMES
        if successful:
            if (
                self.parsed_output is None
                or self.output_sha256 is None
                or self.output_sha256 != content_sha256(self.parsed_output)
                or self.finalization.response_sha256 != self.output_sha256
                or self.exact_role_contract_valid is None
            ):
                raise ValueError("successful qualification observation is incomplete")
        elif (
            self.parsed_output is not None
            or self.output_sha256 is not None
            or self.finalization.response_sha256 is not None
        ):
            raise ValueError("failed qualification observation must omit output")
        if self.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT:
            if self.exact_role_contract_valid is not False:
                raise ValueError("invalid output must fail the role contract")
        elif not successful and self.exact_role_contract_valid is not None:
            raise ValueError("provider failure cannot claim role conformance")
        if self.source is QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS:
            if not successful or self.exact_role_contract_valid is not True:
                raise ValueError("carried qualification evidence must be successful")
            expected_replay = (
                InterviewerToolReplayStatus.HISTORICAL_UNVERIFIABLE
                if self.role is LLMRole.INTERVIEWER
                else InterviewerToolReplayStatus.NOT_APPLICABLE
            )
            if self.interviewer_tool_replay_status is not expected_replay:
                raise ValueError("carried tool-replay status overclaims evidence")
        elif self.role is LLMRole.INTERVIEWER:
            if self.interviewer_tool_replay_status not in {
                InterviewerToolReplayStatus.VERIFIED,
                InterviewerToolReplayStatus.FAILED,
            }:
                raise ValueError("new interviewer call requires replay proof")
        elif (
            self.interviewer_tool_replay_status
            is not InterviewerToolReplayStatus.NOT_APPLICABLE
        ):
            raise ValueError("non-interviewer call cannot report tool replay")
        if (
            self.interviewer_tool_replay_status
            is InterviewerToolReplayStatus.VERIFIED
            and (
                self.finalization.tool_call_count == 0
                or self.finalization.tool_call_failure_count != 0
            )
        ):
            raise ValueError("verified interviewer replay lacks a clean tool call")
        return self


class QualificationCoordinateResult(ContractModel):
    """One exact planned coordinate, observed or explicitly unattempted."""

    record_version: Literal[
        "phase4_two_deployment_coordinate_result.v1"
    ] = "phase4_two_deployment_coordinate_result.v1"
    source_manifest_ordinal: PositiveCount
    source_entry_sha256: Sha256Digest
    call_id: StableId
    candidate_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    role: LLMRole
    variant_id: QualificationVariant
    disposition: QualificationCoordinateDisposition
    observation_sha256: Sha256Digest | None = None

    @model_validator(mode="after")
    def require_observation_only_for_observed_coordinates(self) -> Self:
        observed = self.disposition in {
            QualificationCoordinateDisposition.CARRIED_SUCCESS,
            QualificationCoordinateDisposition.OBSERVED,
        }
        if observed != (self.observation_sha256 is not None):
            raise ValueError("qualification coordinate observation binding differs")
        return self


class QualificationRiskCoveragePoint(ContractModel):
    """Delegated error among choice labels at one frozen confidence threshold."""

    threshold: Probability
    eligible_choice_count: Literal[6] = 6
    automatic_vote_count: NonNegativeCount
    coverage: Probability
    wrong_vote_count: NonNegativeCount
    risk: Probability | None = None

    @model_validator(mode="after")
    def require_reconciled_rate(self) -> Self:
        if self.automatic_vote_count > self.eligible_choice_count or (
            self.wrong_vote_count > self.automatic_vote_count
        ):
            raise ValueError("qualification delegated-risk counts differ")
        if not math.isclose(
            self.coverage,
            self.automatic_vote_count / self.eligible_choice_count,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("qualification delegated coverage differs")
        expected_risk = (
            self.wrong_vote_count / self.automatic_vote_count
            if self.automatic_vote_count
            else None
        )
        if expected_risk is None:
            if self.risk is not None:
                raise ValueError("zero coverage cannot report delegated risk")
        elif self.risk is None or not math.isclose(
            self.risk,
            expected_risk,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("qualification delegated risk differs")
        return self


class QualificationDevelopmentMetrics(ContractModel):
    """Canonical public-development metrics for one readout family."""

    record_version: Literal[
        "phase4_two_deployment_development_metrics.v1"
    ] = "phase4_two_deployment_development_metrics.v1"
    candidate_id: StableId
    readout_role: Literal[LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT]
    fixture_sha256: Sha256Digest
    session_sha256: Sha256Digest
    choice_measure_ids: list[StableId] = Field(min_length=6, max_length=6)
    sample_count: Literal[6] = 6
    log_loss_epsilon: Literal[1e-15] = DEVELOPMENT_LOG_LOSS_EPSILON
    mean_log_loss: NonNegativeFiniteFloat
    multiclass_brier: BoundedBrierScore
    top_choice_accuracy: Probability
    risk_coverage: list[QualificationRiskCoveragePoint] = Field(
        min_length=4,
        max_length=4,
    )
    fractional_probability_tie_credit: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_metric_surface(self) -> Self:
        if len(set(self.choice_measure_ids)) != self.sample_count:
            raise ValueError("qualification choice measures must be unique")
        if [item.threshold for item in self.risk_coverage] != list(
            DEVELOPMENT_RISK_THRESHOLDS
        ):
            raise ValueError("qualification delegated-risk grid differs")
        return self


class QualificationRobustnessSlice(ContractModel):
    """Canonical plus seven shadows for one candidate/readout/measure cell."""

    record_version: Literal[
        "phase4_two_deployment_robustness_slice.v1"
    ] = "phase4_two_deployment_robustness_slice.v1"
    candidate_id: StableId
    readout_role: Literal[LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT]
    measure_id: StableId
    measure_version: PositiveVersion
    coordinate_result_sha256s: list[Sha256Digest] = Field(
        min_length=8,
        max_length=8,
    )
    prediction_sha256s: list[Sha256Digest]
    predictions: list[RobustnessPrediction]
    comparison_sha256s: list[Sha256Digest]
    comparisons: list[RobustnessComparison]
    aggregate_sha256s: list[Sha256Digest]
    aggregates: list[RobustnessAggregate]
    complete: bool
    canonical_output_valid: bool | None = None

    @model_validator(mode="after")
    def require_exact_slice_matrix(self) -> Self:
        if self.prediction_sha256s != [
            content_sha256(item) for item in self.predictions
        ] or self.comparison_sha256s != [
            content_sha256(item) for item in self.comparisons
        ] or self.aggregate_sha256s != [
            content_sha256(item) for item in self.aggregates
        ]:
            raise ValueError("qualification robustness slice hashes differ")
        if len(self.coordinate_result_sha256s) != len(
            set(self.coordinate_result_sha256s)
        ):
            raise ValueError("qualification robustness coordinates must be unique")
        if len(self.predictions) > len(VARIANT_ORDER):
            raise ValueError("qualification robustness slice has extra predictions")
        if self.complete != (len(self.predictions) == len(VARIANT_ORDER)):
            raise ValueError("qualification robustness completeness differs")
        canonical = [
            item for item in self.predictions if item.variant_binding is None
        ]
        if not canonical:
            if self.canonical_output_valid is not None:
                raise ValueError("unobserved canonical output cannot claim validity")
            if self.comparisons or self.aggregates:
                raise ValueError("unobserved canonical cannot claim robustness")
        elif len(canonical) != 1 or (
            self.canonical_output_valid != canonical[0].output_valid
        ):
            raise ValueError("qualification canonical output validity differs")
        if self.canonical_output_valid:
            if len(self.comparisons) != len(self.predictions) - 1:
                raise ValueError("qualification robustness comparisons differ")
            if [item.perturbation_kind for item in self.aggregates] != sorted(
                [item.perturbation_kind for item in self.aggregates],
                key=PERTURBATION_ORDER.index,
            ):
                raise ValueError("qualification robustness aggregate order differs")
            if self.complete and len(self.aggregates) != 4:
                raise ValueError("qualification robustness slice is incomplete")
        elif self.canonical_output_valid is False and (
            self.comparisons or self.aggregates
        ):
            raise ValueError("invalid canonical output cannot claim comparisons")
        return self


class TwoDeploymentCandidateResult(ContractModel):
    """One exact deployment result without legacy three-candidate semantics."""

    record_version: Literal[
        "phase4_two_deployment_candidate_result.v1"
    ] = "phase4_two_deployment_candidate_result.v1"
    candidate_id: StableId
    candidate_version: PositiveVersion
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    candidate_state_sha256: Sha256Digest
    attempt_status: QualificationCandidateAttemptStatus
    coordinate_result_sha256s: list[Sha256Digest] = Field(
        min_length=QUALIFICATION_ENTRIES_PER_CANDIDATE,
        max_length=QUALIFICATION_ENTRIES_PER_CANDIDATE,
    )
    observation_sha256s: list[Sha256Digest] = Field(
        min_length=CARRIED_SUCCESS_COUNT // RUNNABLE_CANDIDATE_COUNT,
        max_length=QUALIFICATION_ENTRIES_PER_CANDIDATE,
    )
    role_call_counts: dict[LLMRole, NonNegativeCount]
    carried_success_count: Literal[5] = 5
    new_provider_call_count: NonNegativeCount
    non_observed_coordinate_count: NonNegativeCount
    provider_pause_outcome_count: NonNegativeCount
    invalid_output_count: NonNegativeCount
    role_contract_failure_count: NonNegativeCount
    interviewer_tool_call_count: NonNegativeCount
    interviewer_tool_call_failure_count: NonNegativeCount
    interviewer_tool_replay_failure_count: NonNegativeCount
    historical_interviewer_replay_unverifiable_count: Literal[1] = 1
    robustness_slice_sha256s: list[Sha256Digest] = Field(
        min_length=16,
        max_length=16,
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
    def require_complete_candidate_shape(self) -> Self:
        if len(self.coordinate_result_sha256s) != len(
            set(self.coordinate_result_sha256s)
        ):
            raise ValueError("qualification coordinate hashes must be unique")
        if len(self.observation_sha256s) != len(set(self.observation_sha256s)):
            raise ValueError("qualification observation hashes must be unique")
        expected_roles = {
            LLMRole.INTERVIEWER: 8,
            LLMRole.EVIDENCE_EXTRACTOR: 8,
            LLMRole.ONTOLOGY_PROPOSER: 8,
            LLMRole.DIRECT_READOUT: 64,
            LLMRole.HYBRID_READOUT: 64,
        }
        if set(self.role_call_counts) != set(expected_roles) or any(
            self.role_call_counts[role] > maximum
            for role, maximum in expected_roles.items()
        ):
            raise ValueError("qualification candidate role counts differ")
        if sum(self.role_call_counts.values()) != len(self.observation_sha256s):
            raise ValueError("qualification candidate observation count differs")
        if self.carried_success_count + self.new_provider_call_count != len(
            self.observation_sha256s
        ):
            raise ValueError("qualification candidate call partition differs")
        if self.new_provider_call_count > NEW_PROVIDER_CALL_COUNT // 2:
            raise ValueError("qualification candidate has extra provider calls")
        if self.non_observed_coordinate_count != (
            QUALIFICATION_ENTRIES_PER_CANDIDATE - len(self.observation_sha256s)
        ):
            raise ValueError("qualification non-observed count differs")
        if (
            self.attempt_status is QualificationCandidateAttemptStatus.COMPLETED
            and self.non_observed_coordinate_count != 0
        ):
            raise ValueError("completed qualification candidate is partial")
        if len(self.robustness_slice_sha256s) != len(
            set(self.robustness_slice_sha256s)
        ):
            raise ValueError("qualification robustness slice hashes differ")
        metrics = (
            self.direct_development_metrics,
            self.hybrid_development_metrics,
        )
        if all(item is not None for item in metrics):
            direct, hybrid = metrics
            if direct is None or hybrid is None:  # pragma: no cover
                raise ValueError("qualification development metrics differ")
            if (
                direct.candidate_id != self.candidate_id
                or hybrid.candidate_id != self.candidate_id
                or direct.readout_role is not LLMRole.DIRECT_READOUT
                or hybrid.readout_role is not LLMRole.HYBRID_READOUT
            ):
                raise ValueError("qualification development metric binding differs")
            expected_log_loss = fmean(
                [direct.mean_log_loss, hybrid.mean_log_loss]
            )
            if self.selection_mean_log_loss is None or not math.isclose(
                self.selection_mean_log_loss,
                expected_log_loss,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("qualification selection log loss differs")
        elif any(item is not None for item in metrics) or (
            self.selection_mean_log_loss is not None
        ):
            raise ValueError("qualification development metrics are partial")
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
        if self.hard_failure_reasons != expected_reasons:
            raise ValueError("qualification candidate hard-failure reasons differ")
        pending_status = self.attempt_status in {
            QualificationCandidateAttemptStatus.PROVIDER_PAUSED,
            QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY,
            QualificationCandidateAttemptStatus.HARNESS_PAUSED,
        }
        if (
            self.attempt_status is QualificationCandidateAttemptStatus.PROVIDER_PAUSED
        ) != bool(self.provider_pause_outcome_count):
            raise ValueError("qualification provider-pause status differs")
        if pending_status:
            if self.passed_hard_gates is not None:
                raise ValueError("pending attempt cannot decide candidate gates")
        elif (
            self.attempt_status
            is QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE
        ):
            if self.passed_hard_gates is not False or not self.hard_failure_reasons:
                raise ValueError("candidate hard failure lacks a substantive reason")
        elif self.passed_hard_gates != (not self.hard_failure_reasons):
            raise ValueError("qualification candidate hard gates differ")
        if self.passed_hard_gates and (
            self.non_observed_coordinate_count
            or self.role_call_counts != expected_roles
            or self.selection_mean_log_loss is None
            or self.prompt_and_stochastic_mean_jsd is None
            or self.robustness_aggregate_count != 64
        ):
            raise ValueError("passing qualification candidate lacks metrics")
        return self


class QualificationResultStatus(str, Enum):
    SELECTED = "selected"
    NO_RUNNABLE_CANDIDATE_QUALIFIED = "no_runnable_candidate_qualified"
    PAUSED_PENDING_PROVIDER_REVIEW = "pause_without_selection_pending_review"


class ExcludedDeploymentProvenance(ContractModel):
    """Preserved deployment-only nonfinding for the frozen third candidate."""

    record_version: Literal[
        "phase4_excluded_deployment_provenance.v1"
    ] = "phase4_excluded_deployment_provenance.v1"
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    capability_outcome_sha256: Sha256Digest
    scope_status: Literal[
        QualificationDeploymentScopeStatus.DEPLOYMENT_INCONCLUSIVE_NOT_RUN
    ] = QualificationDeploymentScopeStatus.DEPLOYMENT_INCONCLUSIVE_NOT_RUN
    included_in_comparison_and_selection: Literal[False] = False
    model_family_capability_rejected: Literal[False] = False
    replacement_candidate_id: Literal[None] = None


class TwoDeploymentQualificationResult(ContractModel):
    """Auditable amended selection over exactly two runnable deployments."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification.v1"
    ] = "preference_eval_phase4_two_deployment_qualification.v1"
    qualification_id: StableId
    qualification_version: PositiveVersion
    created_at: datetime
    scope_amendment_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    result_source_bindings_sha256: Sha256Digest
    result_source_bindings: QualificationResultSourceBindings
    robustness_profile_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    candidates: list[OpenWeightModelCandidate] = Field(
        min_length=RUNNABLE_CANDIDATE_COUNT,
        max_length=RUNNABLE_CANDIDATE_COUNT,
    )
    excluded_deployment: ExcludedDeploymentProvenance
    coordinate_results: list[QualificationCoordinateResult] = Field(
        min_length=SCOPED_QUALIFICATION_ENTRY_COUNT,
        max_length=SCOPED_QUALIFICATION_ENTRY_COUNT,
    )
    observations: list[QualificationCallObservation] = Field(
        min_length=CARRIED_SUCCESS_COUNT,
        max_length=SCOPED_QUALIFICATION_ENTRY_COUNT,
    )
    robustness_slices: list[QualificationRobustnessSlice] = Field(
        min_length=32,
        max_length=32,
    )
    candidate_results: list[TwoDeploymentCandidateResult] = Field(
        min_length=RUNNABLE_CANDIDATE_COUNT,
        max_length=RUNNABLE_CANDIDATE_COUNT,
    )
    selection_criteria_in_priority_order: list[QualificationCriterion]
    selection_policy: QualificationSelectionPolicy
    status: QualificationResultStatus
    selected_candidate_id: StableId | None = None
    conclusion_limited_to_compared_deployments: Literal[True] = True
    excluded_deployment_remains_inconclusive: Literal[True] = True
    post_hoc_replacement_forbidden: Literal[True] = True
    participant_content_visible_to_provider: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "two-deployment qualification created_at")
        return value

    @model_validator(mode="after")
    def require_exact_matrix_and_selection(self) -> Self:
        candidate_ids = [item.candidate_id for item in self.candidates]
        if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != 2:
            raise ValueError("two-deployment candidates must be canonical")
        if self.excluded_deployment.candidate_id in candidate_ids:
            raise ValueError("excluded deployment appears in candidate results")
        observation_ids = [item.call_id for item in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("qualification observations must be unique")
        coordinate_ids = [item.call_id for item in self.coordinate_results]
        if len(coordinate_ids) != len(set(coordinate_ids)):
            raise ValueError("qualification coordinate results must be unique")
        coordinate_observations = {
            item.call_id: item.observation_sha256
            for item in self.coordinate_results
            if item.observation_sha256 is not None
        }
        if coordinate_observations != {
            item.call_id: content_sha256(item) for item in self.observations
        }:
            raise ValueError("qualification coordinate observations differ")
        if self.result_source_bindings_sha256 != content_sha256(
            self.result_source_bindings
        ) or self.execution_plan_sha256 != (
            self.result_source_bindings.execution_plan_sha256
        ):
            raise ValueError("qualification result-source binding differs")
        if self.metric_policy_sha256 != content_sha256(
            TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY
        ):
            raise ValueError("qualification result metric policy differs")
        if [item.candidate_id for item in self.candidate_results] != candidate_ids:
            raise ValueError("qualification candidate results differ")
        if {
            item.candidate_id: item.candidate_state_sha256
            for item in self.candidate_results
        } != self.result_source_bindings.candidate_state_sha256s or {
            item.candidate_id: item.attempt_status
            for item in self.candidate_results
        } != self.result_source_bindings.candidate_attempt_statuses:
            raise ValueError("qualification candidate-state results differ")
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
                raise ValueError("qualification candidate evidence hashes differ")
        slice_keys = [
            (item.candidate_id, item.readout_role, item.measure_id)
            for item in self.robustness_slices
        ]
        if len(slice_keys) != len(set(slice_keys)):
            raise ValueError("qualification robustness slices must be unique")
        if set(item.candidate_id for item in self.robustness_slices) != set(
            candidate_ids
        ):
            raise ValueError("qualification robustness candidates differ")
        if self.selection_criteria_in_priority_order != list(
            QualificationCriterion
        ):
            raise ValueError("qualification selection criteria differ")
        paused = any(
            status
            in {
                QualificationCandidateAttemptStatus.PROVIDER_PAUSED,
                QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY,
                QualificationCandidateAttemptStatus.HARNESS_PAUSED,
            }
            for status in (
                self.result_source_bindings.candidate_attempt_statuses.values()
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
                raise ValueError("provider pause cannot select a candidate")
        elif not eligible:
            if (
                self.status
                is not QualificationResultStatus.NO_RUNNABLE_CANDIDATE_QUALIFIED
                or self.selected_candidate_id is not None
            ):
                raise ValueError("failed qualification cannot select a candidate")
        else:
            selected = _select_candidate(eligible, self.selection_policy)
            if (
                self.status is not QualificationResultStatus.SELECTED
                or self.selected_candidate_id != selected.candidate_id
            ):
                raise ValueError("qualification selection differs from policy")
        return self


class TwoDeploymentQualificationAggregateReceipt(ContractModel):
    """Tracked-eligible result surface with no provider or parsed payloads."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_receipt.v1"
    ] = "preference_eval_phase4_two_deployment_qualification_receipt.v1"
    receipt_id: StableId
    receipt_version: Literal[1] = 1
    created_at: datetime
    private_result_sha256: Sha256Digest
    scope_amendment_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    result_source_bindings_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    candidate_results: list[TwoDeploymentCandidateResult] = Field(
        min_length=RUNNABLE_CANDIDATE_COUNT,
        max_length=RUNNABLE_CANDIDATE_COUNT,
    )
    excluded_deployment: ExcludedDeploymentProvenance
    coordinate_result_count: Literal[304] = SCOPED_QUALIFICATION_ENTRY_COUNT
    observation_count: NonNegativeCount
    unattempted_coordinate_count: NonNegativeCount
    robustness_slice_count: Literal[32] = 32
    robustness_aggregate_count: NonNegativeCount
    status: QualificationResultStatus
    selected_candidate_id: StableId | None = None
    parsed_provider_outputs_omitted: Literal[True] = True
    provider_request_and_response_text_omitted: Literal[True] = True
    participant_content_present: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "two-deployment qualification receipt created_at")
        return value

    @model_validator(mode="after")
    def require_reconciled_aggregate(self) -> Self:
        if self.observation_count + self.unattempted_coordinate_count != (
            self.coordinate_result_count
        ):
            raise ValueError("qualification receipt coordinate counts differ")
        candidate_ids = [item.candidate_id for item in self.candidate_results]
        if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != 2:
            raise ValueError("qualification receipt candidates differ")
        if self.excluded_deployment.candidate_id in candidate_ids:
            raise ValueError("qualification receipt includes excluded deployment")
        if self.status is QualificationResultStatus.SELECTED:
            if self.selected_candidate_id not in candidate_ids:
                raise ValueError("qualification receipt selection differs")
        elif self.selected_candidate_id is not None:
            raise ValueError("unselected qualification receipt names a candidate")
        return self


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _scoped_entries(
    scope: TwoDeploymentQualificationScopeAmendment,
    readiness: Phase4TogetherReadinessBundle,
    execution_plan: TwoDeploymentQualificationExecutionPlan,
) -> list[QualificationCallPlanEntry]:
    if (
        execution_plan.qualification_scope_sha256 != content_sha256(scope)
        or execution_plan.readiness_sha256 != content_sha256(readiness)
        or execution_plan.source_qualification_manifest_sha256
        != content_sha256(readiness.qualification_manifest)
        or execution_plan.metric_policy_sha256
        != content_sha256(TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY)
    ):
        raise ValueError("qualification execution plan binding differs")
    if [item.candidate_id for item in execution_plan.candidate_plans] != (
        scope.runnable_candidate_ids
    ):
        raise ValueError("qualification execution plan roster differs")
    planned_calls = sorted(
        (
            call
            for candidate_plan in execution_plan.candidate_plans
            for call in candidate_plan.calls
        ),
        key=lambda item: item.source_manifest_ordinal,
    )
    readiness_entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id in scope.runnable_candidate_ids
    ]
    if (
        len(planned_calls) != SCOPED_QUALIFICATION_ENTRY_COUNT
        or [item.source_entry for item in planned_calls] != readiness_entries
    ):
        raise ValueError("qualification execution plan entries differ")
    return [item.source_entry for item in planned_calls]


def _validate_observation_against_entry(
    observation: QualificationCallObservation,
    entry: QualificationCallPlanEntry,
    *,
    profile: Phase4ERobustnessProfile,
    carried_call_ids: set[str],
) -> None:
    coordinate = entry.coordinate
    expected_identity = (
        coordinate.ordinal,
        content_sha256(entry),
        coordinate.call_id,
        coordinate.candidate_id,
        coordinate.measure_id,
        coordinate.measure_version,
        coordinate.role,
        coordinate.variant_id,
    )
    actual_identity = (
        observation.source_manifest_ordinal,
        observation.source_entry_sha256,
        observation.call_id,
        observation.candidate_id,
        observation.measure_id,
        observation.measure_version,
        observation.role,
        observation.variant_id,
    )
    if actual_identity != expected_identity:
        raise ValueError("qualification observation source coordinate differs")
    binding = observation.request_binding
    if (
        binding.robustness_profile_id,
        binding.robustness_profile_version,
        binding.robustness_profile_sha256,
        binding.model_candidate_sha256,
        binding.price_card_sha256,
        binding.request_seed,
        binding.input_token_upper_bound,
        binding.output_token_upper_bound,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
        entry.candidate_sha256,
        entry.price_card_sha256,
        coordinate.request_seed,
        entry.input_token_upper_bound,
        entry.output_token_upper_bound,
    ):
        raise ValueError("qualification observation request binding differs")
    if observation.request_content_sha256 != entry.request_template_sha256:
        raise ValueError("qualification observation request does not match plan")
    if observation.usage.input_tokens > entry.input_token_upper_bound or (
        observation.usage.output_tokens > entry.output_token_upper_bound
    ):
        raise ValueError("qualification observation exceeds token envelope")
    expected_source = (
        QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS
        if coordinate.call_id in carried_call_ids
        else QualificationObservationSource.NEW_QUALIFICATION_CALL
    )
    if observation.source is not expected_source:
        raise ValueError("qualification observation carry status differs")


def _build_coordinate_results(
    execution_plan: TwoDeploymentQualificationExecutionPlan,
    entries: list[QualificationCallPlanEntry],
    observations_by_call_id: dict[str, QualificationCallObservation],
    source_bindings: QualificationResultSourceBindings,
) -> list[QualificationCoordinateResult]:
    plan_calls = {
        item.call_id: item
        for candidate_plan in execution_plan.candidate_plans
        for item in candidate_plan.calls
    }
    if set(plan_calls) != {item.coordinate.call_id for item in entries}:
        raise ValueError("qualification coordinate plan differs")
    disposition_by_call_id: dict[str, QualificationCoordinateDisposition] = {}
    for candidate_plan in execution_plan.candidate_plans:
        candidate_id = candidate_plan.candidate_id
        status = source_bindings.candidate_attempt_statuses[candidate_id]
        carried = [
            item
            for item in candidate_plan.calls
            if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
        ]
        provider = [
            item
            for item in candidate_plan.calls
            if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
        ]
        if any(item.call_id not in observations_by_call_id for item in carried):
            raise ValueError("qualification carried evidence is incomplete")
        observed_provider_ids = [
            item.call_id for item in provider if item.call_id in observations_by_call_id
        ]
        if observed_provider_ids != [
            item.call_id for item in provider[: len(observed_provider_ids)]
        ]:
            raise ValueError("qualification provider observations are not a prefix")
        observed_provider = provider[: len(observed_provider_ids)]
        complete = len(observed_provider) == len(provider)
        last_observation = (
            observations_by_call_id[observed_provider[-1].call_id]
            if observed_provider
            else None
        )
        observed_provider_observations = [
            observations_by_call_id[item.call_id] for item in observed_provider
        ]
        if any(
            item.finalization.outcome not in SUCCESS_OUTCOMES
            for item in observed_provider_observations[:-1]
        ):
            raise ValueError("qualification failure is not terminal")
        if status is QualificationCandidateAttemptStatus.COMPLETED:
            if not complete:
                raise ValueError("completed qualification candidate is partial")
            if any(
                item.finalization.outcome not in SUCCESS_OUTCOMES
                for item in observed_provider_observations
            ):
                raise ValueError("completed qualification candidate has a failure")
        elif status is QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE:
            if last_observation is None or (
                last_observation.finalization.outcome
                is not ProviderCallOutcome.INVALID_OUTPUT
            ):
                raise ValueError("candidate hard failure lacks terminal invalid output")
        elif status is QualificationCandidateAttemptStatus.PROVIDER_PAUSED:
            if last_observation is None or (
                last_observation.finalization.outcome
                not in AMENDED_SCOPE_PAUSE_OUTCOMES
            ):
                raise ValueError("provider pause lacks terminal provider outcome")
        elif status in {
            QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY,
            QualificationCandidateAttemptStatus.HARNESS_PAUSED,
        }:
            if complete:
                raise ValueError(
                    "paused qualification candidate has no unattempted call"
                )
            if any(
                item.finalization.outcome not in SUCCESS_OUTCOMES
                for item in observed_provider_observations
            ):
                raise ValueError("paused qualification prefix includes a failure")
        for item in carried:
            disposition_by_call_id[item.call_id] = (
                QualificationCoordinateDisposition.CARRIED_SUCCESS
            )
        for index, item in enumerate(provider):
            if index < len(observed_provider):
                disposition = QualificationCoordinateDisposition.OBSERVED
            elif status is QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE:
                disposition = (
                    QualificationCoordinateDisposition.UNATTEMPTED_HARD_FAILURE
                )
            elif status is QualificationCandidateAttemptStatus.PROVIDER_PAUSED:
                disposition = (
                    QualificationCoordinateDisposition.UNATTEMPTED_PROVIDER_PAUSE
                )
            elif status is QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY:
                disposition = (
                    QualificationCoordinateDisposition.AMBIGUOUS_DELIVERY
                    if index == len(observed_provider)
                    else QualificationCoordinateDisposition.UNATTEMPTED_AMBIGUOUS
                )
            elif status is QualificationCandidateAttemptStatus.HARNESS_PAUSED:
                disposition = (
                    QualificationCoordinateDisposition.UNATTEMPTED_HARNESS_PAUSE
                )
            else:  # pragma: no cover - completion was checked above
                raise ValueError("qualification coordinate disposition is missing")
            disposition_by_call_id[item.call_id] = disposition
    results: list[QualificationCoordinateResult] = []
    for entry in entries:
        coordinate = entry.coordinate
        observation = observations_by_call_id.get(coordinate.call_id)
        results.append(
            QualificationCoordinateResult(
                source_manifest_ordinal=coordinate.ordinal,
                source_entry_sha256=content_sha256(entry),
                call_id=coordinate.call_id,
                candidate_id=coordinate.candidate_id,
                measure_id=coordinate.measure_id,
                measure_version=coordinate.measure_version,
                role=coordinate.role,
                variant_id=coordinate.variant_id,
                disposition=disposition_by_call_id[coordinate.call_id],
                observation_sha256=(
                    content_sha256(observation) if observation is not None else None
                ),
            )
        )
    return results


def _readout_response(
    observation: QualificationCallObservation,
) -> LLMReadoutResponseDraft | None:
    if observation.finalization.outcome not in SUCCESS_OUTCOMES:
        return None
    return LLMReadoutResponseDraft.model_validate(observation.parsed_output)


def _robustness_prediction(
    observation: QualificationCallObservation,
    entry: QualificationCallPlanEntry,
    *,
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
    option_ids: list[str],
) -> RobustnessPrediction:
    response = _readout_response(observation)
    output_valid = response is not None
    if not output_valid:
        return RobustnessPrediction(
            prediction_id=f"qualification_prediction_{observation.call_id}",
            evaluation_binding=build_robustness_evaluation_binding(
                profile,
                candidate,
            ),
            variant_binding=entry.robustness_variant,
            request_sha256=observation.request_content_sha256,
            canonical_option_order=option_ids,
            output_valid=False,
            failure_code=(
                observation.finalization.failure_code
                or observation.finalization.outcome.value
            ),
        )
    if set(response.option_probabilities) != set(option_ids):
        raise ValueError("qualification readout options differ from measure")
    top_option_id = expected_top_option_id(option_ids, response.option_probabilities)
    return RobustnessPrediction(
        prediction_id=f"qualification_prediction_{observation.call_id}",
        evaluation_binding=build_robustness_evaluation_binding(
            profile,
            candidate,
        ),
        variant_binding=entry.robustness_variant,
        request_sha256=observation.request_content_sha256,
        response_sha256=observation.output_sha256,
        canonical_option_order=option_ids,
        option_probabilities=response.option_probabilities,
        top_option_id=top_option_id,
        unsupported_assumption_count=len(response.unsupported_assumptions),
        output_valid=True,
    )


def _build_robustness_slice(
    observations_by_call_id: dict[str, QualificationCallObservation],
    coordinate_results_by_call_id: dict[str, QualificationCoordinateResult],
    entries: list[QualificationCallPlanEntry],
    *,
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
    option_ids: list[str],
) -> QualificationRobustnessSlice:
    ordered_entries = sorted(
        entries,
        key=lambda item: VARIANT_ORDER.index(item.coordinate.variant_id),
    )
    observed_entries = [
        item
        for item in ordered_entries
        if item.coordinate.call_id in observations_by_call_id
    ]
    predictions = [
        _robustness_prediction(
            observations_by_call_id[item.coordinate.call_id],
            item,
            profile=profile,
            candidate=candidate,
            option_ids=option_ids,
        )
        for item in observed_entries
    ]
    canonical = next(
        (item for item in predictions if item.variant_binding is None),
        None,
    )
    comparisons: list[RobustnessComparison] = []
    aggregates: list[RobustnessAggregate] = []
    if canonical is not None and canonical.output_valid:
        comparisons = [
            compare_robustness_predictions(
                canonical,
                prediction,
                comparison_id=(
                    f"qualification_comparison_{prediction.prediction_id}"
                ),
            )
            for prediction in predictions
            if prediction.variant_binding is not None
        ]
        required_count = {
            RobustnessPerturbationKind.PROMPT_PARAPHRASE: 2,
            RobustnessPerturbationKind.OPTION_ORDER: 1,
            RobustnessPerturbationKind.OPTION_LABEL: 1,
            RobustnessPerturbationKind.STOCHASTIC_REPEAT: 3,
        }
        for kind in PERTURBATION_ORDER:
            kind_comparisons = [
                item for item in comparisons if item.perturbation_kind is kind
            ]
            if len(kind_comparisons) == required_count[kind]:
                aggregates.append(
                    aggregate_robustness_comparisons(kind_comparisons)
                )
    coordinate = ordered_entries[0].coordinate
    return QualificationRobustnessSlice(
        candidate_id=candidate.candidate_id,
        readout_role=coordinate.role,
        measure_id=coordinate.measure_id,
        measure_version=coordinate.measure_version,
        coordinate_result_sha256s=[
            content_sha256(
                coordinate_results_by_call_id[item.coordinate.call_id]
            )
            for item in ordered_entries
        ],
        prediction_sha256s=[content_sha256(item) for item in predictions],
        predictions=predictions,
        comparison_sha256s=[content_sha256(item) for item in comparisons],
        comparisons=comparisons,
        aggregate_sha256s=[content_sha256(item) for item in aggregates],
        aggregates=aggregates,
        complete=len(predictions) == len(VARIANT_ORDER),
        canonical_output_valid=(
            canonical.output_valid if canonical is not None else None
        ),
    )


def _build_development_metrics(
    candidate_id: str,
    role: LLMRole,
    slices: list[QualificationRobustnessSlice],
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
) -> QualificationDevelopmentMetrics | None:
    canonical_by_measure = {
        item.measure_id: next(
            prediction
            for prediction in item.predictions
            if prediction.variant_binding is None
        )
        for item in slices
        if item.readout_role is role and item.canonical_output_valid
    }
    choices = [
        item
        for item in session.responses
        if item.response_state is ResponseState.CHOICE
    ]
    if len(choices) != 6 or any(
        item.measure_id not in canonical_by_measure for item in choices
    ):
        return None
    log_losses: list[float] = []
    brier_scores: list[float] = []
    top_choice_credit = 0.0
    outcomes: list[tuple[dict[str, float], str, str]] = []
    for choice in choices:
        selected = choice.selected_option_id
        if selected is None:
            raise ValueError("development choice lacks a selected option")
        prediction = canonical_by_measure[choice.measure_id]
        probabilities = prediction.option_probabilities
        top = prediction.top_option_id
        if probabilities is None or top is None or selected not in probabilities:
            raise ValueError("development prediction is incomplete")
        log_losses.append(
            -math.log(max(probabilities[selected], DEVELOPMENT_LOG_LOSS_EPSILON))
        )
        brier_scores.append(
            math.fsum(
                (probability - (1.0 if option_id == selected else 0.0)) ** 2
                for option_id, probability in probabilities.items()
            )
        )
        top_probability = max(probabilities.values())
        tied = [
            option_id
            for option_id, probability in probabilities.items()
            if math.isclose(
                probability,
                top_probability,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ]
        if selected in tied:
            top_choice_credit += 1.0 / len(tied)
        outcomes.append((probabilities, selected, top))
    risk_points = []
    for threshold in DEVELOPMENT_RISK_THRESHOLDS:
        covered = [
            item for item in outcomes if max(item[0].values()) >= threshold
        ]
        wrong = sum(top != selected for _, selected, top in covered)
        risk_points.append(
            QualificationRiskCoveragePoint(
                threshold=threshold,
                automatic_vote_count=len(covered),
                coverage=len(covered) / len(outcomes),
                wrong_vote_count=wrong,
                risk=(wrong / len(covered) if covered else None),
            )
        )
    return QualificationDevelopmentMetrics(
        candidate_id=candidate_id,
        readout_role=role,
        fixture_sha256=content_sha256(fixture),
        session_sha256=content_sha256(session),
        choice_measure_ids=[item.measure_id for item in choices],
        mean_log_loss=fmean(log_losses),
        multiclass_brier=fmean(brier_scores),
        top_choice_accuracy=top_choice_credit / len(choices),
        risk_coverage=risk_points,
    )


def _candidate_hard_failure_reasons(
    *,
    role_counts: dict[LLMRole, int],
    invalid_output_count: int,
    role_contract_failure_count: int,
    interviewer_tool_call_failure_count: int,
    interviewer_tool_replay_failure_count: int,
    interviewer_tool_call_count: int,
    robustness_invalid_output_count: int,
    strict_transform_top_choice_flip_count: int,
    held_out_projected_cost_microusd: int,
    profile: Phase4ERobustnessProfile,
) -> list[str]:
    reasons: list[str] = []
    if any(role_counts.get(role, 0) == 0 for role in LLMRole):
        reasons.append("required_role_missing")
    if invalid_output_count:
        reasons.append("invalid_structured_output")
    if role_contract_failure_count:
        reasons.append("role_contract_failure")
    if interviewer_tool_call_failure_count:
        reasons.append("interviewer_tool_call_failure")
    if interviewer_tool_replay_failure_count:
        reasons.append("interviewer_tool_replay_failure")
    if interviewer_tool_call_count == 0:
        reasons.append("interviewer_tool_not_exercised")
    if robustness_invalid_output_count:
        reasons.append("robustness_invalid_output")
    if strict_transform_top_choice_flip_count:
        reasons.append("strict_transform_top_choice_flip")
    held_out_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.HELD_OUT_STUDY
    ]
    if held_out_projected_cost_microusd > held_out_cap:
        reasons.append("projected_study_cost_over_cap")
    if any(
        reason not in AMENDED_QUALIFICATION_HARD_FAILURE_REASONS
        for reason in reasons
    ):
        raise ValueError("qualification emitted an undeclared hard failure")
    return reasons


def _build_candidate_result(
    candidate: OpenWeightModelCandidate,
    observations: list[QualificationCallObservation],
    coordinate_results: list[QualificationCoordinateResult],
    slices: list[QualificationRobustnessSlice],
    *,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    price_card_sha256: str,
    candidate_state_sha256: str,
    attempt_status: QualificationCandidateAttemptStatus,
) -> TwoDeploymentCandidateResult:
    role_counts = Counter(item.role for item in observations)
    normalized_role_counts = {role: role_counts[role] for role in LLMRole}
    pause_count = sum(
        item.finalization.outcome in AMENDED_SCOPE_PAUSE_OUTCOMES
        for item in observations
    )
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
    direct_metrics = _build_development_metrics(
        candidate.candidate_id,
        LLMRole.DIRECT_READOUT,
        slices,
        fixture,
        session,
    )
    hybrid_metrics = _build_development_metrics(
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
    reasons = _candidate_hard_failure_reasons(
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
    pending_status = attempt_status in {
        QualificationCandidateAttemptStatus.PROVIDER_PAUSED,
        QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY,
        QualificationCandidateAttemptStatus.HARNESS_PAUSED,
    }
    return TwoDeploymentCandidateResult(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.artifact_version,
        candidate_sha256=content_sha256(candidate),
        price_card_sha256=price_card_sha256,
        candidate_state_sha256=candidate_state_sha256,
        attempt_status=attempt_status,
        coordinate_result_sha256s=[
            content_sha256(item) for item in coordinate_results
        ],
        observation_sha256s=[content_sha256(item) for item in observations],
        role_call_counts=normalized_role_counts,
        carried_success_count=sum(
            item.source is QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS
            for item in observations
        ),
        new_provider_call_count=sum(
            item.source is QualificationObservationSource.NEW_QUALIFICATION_CALL
            for item in observations
        ),
        non_observed_coordinate_count=(
            QUALIFICATION_ENTRIES_PER_CANDIDATE - len(observations)
        ),
        provider_pause_outcome_count=pause_count,
        invalid_output_count=invalid_count,
        role_contract_failure_count=role_failures,
        interviewer_tool_call_count=tool_calls,
        interviewer_tool_call_failure_count=tool_failures,
        interviewer_tool_replay_failure_count=replay_failures,
        historical_interviewer_replay_unverifiable_count=sum(
            item.interviewer_tool_replay_status
            is InterviewerToolReplayStatus.HISTORICAL_UNVERIFIABLE
            for item in interviewer
        ),
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
            if len(sensitivity_by_slice) == 16
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
        p95_latency_ms=_p95(
            [item.finalization.latency_ms for item in observations]
        ),
        hard_failure_reasons=reasons,
        passed_hard_gates=(
            None
            if pending_status
            else (
                False
                if attempt_status
                is QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE
                else not reasons
            )
        ),
    )


def _select_candidate(
    eligible: list[TwoDeploymentCandidateResult],
    policy: QualificationSelectionPolicy,
) -> TwoDeploymentCandidateResult:
    if not eligible:
        raise ValueError("two-deployment selection needs an eligible candidate")
    if any(
        item.prompt_and_stochastic_mean_jsd is None
        or item.selection_mean_log_loss is None
        for item in eligible
    ):
        raise ValueError("eligible candidate lacks selection metrics")
    remaining = list(eligible)
    criteria = (
        (
            lambda item: float(item.prompt_and_stochastic_mean_jsd),
            policy.prompt_and_stochastic_mean_jsd_tolerance,
        ),
        (
            lambda item: float(item.selection_mean_log_loss),
            policy.development_mean_log_loss_tolerance,
        ),
        (
            lambda item: float(item.held_out_projected_cost_microusd),
            float(policy.projected_cost_tolerance_microusd),
        ),
        (
            lambda item: item.p95_latency_ms,
            policy.p95_latency_tolerance_ms,
        ),
    )
    for value_of, tolerance in criteria:
        best = min(value_of(item) for item in remaining)
        remaining = [
            item for item in remaining if value_of(item) <= best + tolerance
        ]
    return min(remaining, key=lambda item: item.candidate_id)


def build_two_deployment_qualification_result(
    scope: TwoDeploymentQualificationScopeAmendment,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    suite: Phase4TogetherSuite,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    execution_plan: TwoDeploymentQualificationExecutionPlan,
    source_bindings: QualificationResultSourceBindings,
    observations: list[QualificationCallObservation],
    *,
    qualification_id: str,
    qualification_version: int,
    created_at: datetime,
) -> TwoDeploymentQualificationResult:
    """Derive the full amended result from exact observations and public inputs."""

    validate_session_script_against_fixture(session, fixture)
    expected_bindings = (
        content_sha256(profile),
        content_sha256(suite),
        content_sha256(readiness),
        content_sha256(readiness.qualification_manifest),
        content_sha256(fixture),
        content_sha256(session),
    )
    actual_bindings = (
        scope.robustness_profile_sha256,
        scope.together_suite_sha256,
        scope.readiness_sha256,
        scope.source_qualification_manifest_sha256,
        readiness.public_development_fixture_sha256,
        readiness.public_development_session_sha256,
    )
    if expected_bindings != actual_bindings:
        raise ValueError("qualification result public bindings differ")
    metric_policy = TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY
    if scope.result_policy.expected_result_schema_version != (
        "preference_eval_phase4_two_deployment_qualification.v1"
    ):
        raise ValueError("qualification scope expects another result schema")
    if source_bindings.execution_plan_sha256 != content_sha256(
        execution_plan
    ) or set(source_bindings.candidate_state_sha256s) != set(
        scope.runnable_candidate_ids
    ):
        raise ValueError("qualification result source bindings differ")
    entries = _scoped_entries(scope, readiness, execution_plan)
    observations_by_call_id = {item.call_id: item for item in observations}
    planned_call_ids = {item.coordinate.call_id for item in entries}
    if len(observations_by_call_id) != len(observations) or not set(
        observations_by_call_id
    ).issubset(planned_call_ids):
        raise ValueError("qualification observation call set differs")
    plan_calls = [
        call
        for candidate_plan in execution_plan.candidate_plans
        for call in candidate_plan.calls
    ]
    carried_call_ids = {
        item.call_id
        for item in plan_calls
        if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
    }
    if len(carried_call_ids) != CARRIED_SUCCESS_COUNT:
        raise ValueError("qualification carried call set differs")
    ordered_observations = [
        observations_by_call_id[item.coordinate.call_id]
        for item in entries
        if item.coordinate.call_id in observations_by_call_id
    ]
    entries_by_call_id = {
        item.coordinate.call_id: item for item in entries
    }
    for observation in ordered_observations:
        _validate_observation_against_entry(
            observation,
            entries_by_call_id[observation.call_id],
            profile=profile,
            carried_call_ids=carried_call_ids,
        )
    coordinate_results = _build_coordinate_results(
        execution_plan,
        entries,
        observations_by_call_id,
        source_bindings,
    )
    coordinate_results_by_call_id = {
        item.call_id: item for item in coordinate_results
    }
    candidate_container_by_id = {
        item.candidate.candidate_id: item for item in suite.candidates
    }
    candidates = [
        candidate_container_by_id[item].candidate
        for item in scope.runnable_candidate_ids
    ]
    entries_by_slice: dict[
        tuple[str, LLMRole, str],
        list[QualificationCallPlanEntry],
    ] = defaultdict(list)
    for entry in entries:
        if entry.coordinate.role in READOUT_ROLES:
            entries_by_slice[
                (
                    entry.coordinate.candidate_id,
                    entry.coordinate.role,
                    entry.coordinate.measure_id,
                )
            ].append(entry)
    slices: list[QualificationRobustnessSlice] = []
    for candidate in candidates:
        for role in READOUT_ROLES:
            for measure in fixture.measures:
                slice_entries = entries_by_slice[
                    (candidate.candidate_id, role, measure.measure_id)
                ]
                if len(slice_entries) != len(VARIANT_ORDER):
                    raise ValueError("qualification robustness source slice differs")
                slices.append(
                    _build_robustness_slice(
                        observations_by_call_id,
                        coordinate_results_by_call_id,
                        slice_entries,
                        profile=profile,
                        candidate=candidate,
                        option_ids=[item.option_id for item in measure.options],
                    )
                )
    results: list[TwoDeploymentCandidateResult] = []
    for candidate in candidates:
        candidate_observations = [
            item
            for item in ordered_observations
            if item.candidate_id == candidate.candidate_id
        ]
        candidate_slices = [
            item for item in slices if item.candidate_id == candidate.candidate_id
        ]
        candidate_coordinates = [
            item
            for item in coordinate_results
            if item.candidate_id == candidate.candidate_id
        ]
        container = candidate_container_by_id[candidate.candidate_id]
        results.append(
            _build_candidate_result(
                candidate,
                candidate_observations,
                candidate_coordinates,
                candidate_slices,
                profile=profile,
                readiness=readiness,
                fixture=fixture,
                session=session,
                price_card_sha256=content_sha256(container.price_card),
                candidate_state_sha256=(
                    source_bindings.candidate_state_sha256s[
                        candidate.candidate_id
                    ]
                ),
                attempt_status=(
                    source_bindings.candidate_attempt_statuses[
                        candidate.candidate_id
                    ]
                ),
            )
        )
    excluded_scope = next(
        item
        for item in scope.deployment_scopes
        if item.candidate_id == scope.excluded_deployment_candidate_id
    )
    excluded = ExcludedDeploymentProvenance(
        candidate_id=excluded_scope.candidate_id,
        candidate_sha256=excluded_scope.candidate_sha256,
        price_card_sha256=excluded_scope.price_card_sha256,
        capability_outcome_sha256=excluded_scope.capability_outcome_sha256,
    )
    paused = any(
        item.attempt_status
        in {
            QualificationCandidateAttemptStatus.PROVIDER_PAUSED,
            QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY,
            QualificationCandidateAttemptStatus.HARNESS_PAUSED,
        }
        for item in results
    )
    eligible = [item for item in results if item.passed_hard_gates is True]
    selected = (
        _select_candidate(eligible, scope.result_policy.selection_policy)
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
    return TwoDeploymentQualificationResult(
        qualification_id=qualification_id,
        qualification_version=qualification_version,
        created_at=created_at,
        scope_amendment_sha256=content_sha256(scope),
        execution_plan_sha256=content_sha256(execution_plan),
        result_source_bindings_sha256=content_sha256(source_bindings),
        result_source_bindings=source_bindings,
        robustness_profile_sha256=content_sha256(profile),
        together_suite_sha256=content_sha256(suite),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        metric_policy_sha256=content_sha256(metric_policy),
        public_development_fixture_sha256=content_sha256(fixture),
        public_development_session_sha256=content_sha256(session),
        candidates=candidates,
        excluded_deployment=excluded,
        coordinate_results=coordinate_results,
        observations=ordered_observations,
        robustness_slices=slices,
        candidate_results=results,
        selection_criteria_in_priority_order=(
            scope.result_policy.selection_criteria_in_priority_order
        ),
        selection_policy=scope.result_policy.selection_policy,
        status=status,
        selected_candidate_id=(selected.candidate_id if selected is not None else None),
    )


def validate_two_deployment_qualification_result(
    result: TwoDeploymentQualificationResult,
    scope: TwoDeploymentQualificationScopeAmendment,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    suite: Phase4TogetherSuite,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    execution_plan: TwoDeploymentQualificationExecutionPlan,
) -> None:
    rebuilt = build_two_deployment_qualification_result(
        scope,
        readiness,
        profile,
        suite,
        fixture,
        session,
        execution_plan,
        result.result_source_bindings,
        result.observations,
        qualification_id=result.qualification_id,
        qualification_version=result.qualification_version,
        created_at=result.created_at,
    )
    if rebuilt != result:
        raise ValueError("two-deployment qualification result does not rebuild")


def two_deployment_qualification_summary(
    result: TwoDeploymentQualificationResult,
) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "qualification_sha256": content_sha256(result),
        "runnable_candidate_count": len(result.candidates),
        "excluded_deployment_count": 1,
        "coordinate_result_count": len(result.coordinate_results),
        "observation_count": len(result.observations),
        "unattempted_coordinate_count": sum(
            item.observation_sha256 is None for item in result.coordinate_results
        ),
        "robustness_slice_count": len(result.robustness_slices),
        "robustness_aggregate_count": sum(
            item.robustness_aggregate_count for item in result.candidate_results
        ),
        "qualified_candidate_count": sum(
            item.passed_hard_gates is True for item in result.candidate_results
        ),
        "status": result.status.value,
        "selected_candidate_id": result.selected_candidate_id,
        "qualification_cost_microusd": sum(
            item.qualification_cost_microusd for item in result.candidate_results
        ),
        "participant_content_omitted": True,
    }


def build_two_deployment_qualification_aggregate_receipt(
    result: TwoDeploymentQualificationResult,
    *,
    receipt_id: str,
) -> TwoDeploymentQualificationAggregateReceipt:
    """Remove every parsed/provider payload from the tracked result surface."""

    return TwoDeploymentQualificationAggregateReceipt(
        receipt_id=receipt_id,
        created_at=result.created_at,
        private_result_sha256=content_sha256(result),
        scope_amendment_sha256=result.scope_amendment_sha256,
        execution_plan_sha256=result.execution_plan_sha256,
        result_source_bindings_sha256=result.result_source_bindings_sha256,
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
        candidate_results=result.candidate_results,
        excluded_deployment=result.excluded_deployment,
        observation_count=len(result.observations),
        unattempted_coordinate_count=sum(
            item.observation_sha256 is None for item in result.coordinate_results
        ),
        robustness_aggregate_count=sum(
            item.robustness_aggregate_count for item in result.candidate_results
        ),
        status=result.status,
        selected_candidate_id=result.selected_candidate_id,
    )


def validate_two_deployment_qualification_aggregate_receipt(
    receipt: TwoDeploymentQualificationAggregateReceipt,
    result: TwoDeploymentQualificationResult,
) -> None:
    rebuilt = build_two_deployment_qualification_aggregate_receipt(
        result,
        receipt_id=receipt.receipt_id,
    )
    if rebuilt != receipt:
        raise ValueError("two-deployment qualification receipt does not rebuild")


def load_two_deployment_qualification_result(
    path: str | Path,
) -> TwoDeploymentQualificationResult:
    return TwoDeploymentQualificationResult.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_two_deployment_qualification_aggregate_receipt(
    path: str | Path,
) -> TwoDeploymentQualificationAggregateReceipt:
    return TwoDeploymentQualificationAggregateReceipt.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
