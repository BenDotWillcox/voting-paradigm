"""Reviewed two-deployment amendment to the Phase 4E qualification scope.

The frozen Phase 4E profile and the historical three-candidate qualification
contract remain unchanged.  This module records the narrower deployment scope
made necessary by one provider/deployment-inconclusive capability attempt.  It
does not authorize a provider call.  A later paid runner must consume this
exact amendment through a new scope-aware authorization and result contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, NamedTuple, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_aggregation import (
    CandidateCapabilityDisposition,
    CapabilityRoleEvidenceStatus,
    Phase4CapabilityAggregation,
    Phase4CapabilityAggregationSourceProof,
)
from .phase4_capability_retry import (
    CapabilityDiagnosticRetryDisposition,
    TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    TogetherCapabilityDiagnosticRetryExecutionState,
    TogetherCapabilityDiagnosticRetryPlan,
    TogetherCapabilityDiagnosticRetrySourceProof,
    validate_capability_diagnostic_retry_authorization_bundle,
    validate_capability_diagnostic_retry_execution_state,
    validate_capability_diagnostic_retry_plan_public,
    validate_capability_diagnostic_retry_source_proof,
)
from .phase4_capability_recovery import (
    TogetherCapabilityDeltaPlan,
    TogetherCapabilityDeltaSourceProof,
    TogetherDeltaCandidateExecutionState,
)
from .phase4_provider import (
    ProviderCallOutcome,
    ProviderHTTPErrorCode,
    ProviderHTTPErrorEnvelopeState,
    ProviderHTTPErrorType,
    ProviderRejectedRequestField,
)
from .phase4_provider_semantics import ProviderResponseInvariantManifest
from .phase4_qualification import (
    PHASE4_QUALIFICATION_SELECTION_POLICY,
    PROVIDER_FAILURE_OUTCOMES,
    QualificationSelectionPolicy,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    QualificationCallPlanEntry,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    Phase4ERobustnessProfile,
    QualificationCriterion,
)
from .phase4_selector_recovery import (
    TogetherSelectorRecoveryDeltaPlan,
    TogetherSelectorRecoverySourceProof,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .prequential import PrequentialSessionScript


NonNegativeCount = Annotated[int, Field(ge=0)]
Microusd = Annotated[int, Field(ge=0)]

ORIGINAL_CANDIDATE_COUNT = 3
RUNNABLE_CANDIDATE_COUNT = 2
QUALIFICATION_ENTRIES_PER_CANDIDATE = 152
CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE = 5
SCOPED_QUALIFICATION_ENTRY_COUNT = 304
CARRIED_SUCCESS_COUNT = 10
NEW_PROVIDER_CALL_COUNT = 294
FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256 = (
    "42010288efd4dcba8bec9cd8aa9c4cef8c94d7e32e8e17b6b4a812e419708b46"
)
FROZEN_TWO_DEPLOYMENT_SCOPE_EVIDENCE_PROOF_SHA256 = (
    "d7dc3c435570c438cdd4c851273ed3a28f6c9a37180c095246cd393666836dff"
)
LEGACY_QUALIFICATION_HARD_FAILURE_REASONS = (
    "required_role_missing",
    "provider_call_failure",
    "invalid_structured_output",
    "role_contract_failure",
    "interviewer_tool_call_failure",
    "interviewer_tool_replay_failure",
    "interviewer_tool_not_exercised",
    "robustness_invalid_output",
    "strict_transform_top_choice_flip",
    "projected_study_cost_over_cap",
)
AMENDED_QUALIFICATION_HARD_FAILURE_REASONS = tuple(
    reason
    for reason in LEGACY_QUALIFICATION_HARD_FAILURE_REASONS
    if reason != "provider_call_failure"
)
AMENDED_SCOPE_PAUSE_OUTCOMES = (
    ProviderCallOutcome.PROVIDER_ERROR,
    ProviderCallOutcome.TRANSPORT_ERROR,
    ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
    ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
    ProviderCallOutcome.CANCELLED,
)


class QualificationScopePublicInputs(NamedTuple):
    """Typed adapter for the existing 15-artifact public validation chain."""

    selector_delta: TogetherSelectorRecoveryDeltaPlan
    selector_source_proof: TogetherSelectorRecoverySourceProof
    parent_delta: TogetherCapabilityDeltaPlan
    parent_delta_source_proof: TogetherCapabilityDeltaSourceProof
    parent_capability_plan: TogetherCapabilityPlan
    parent_suite: Phase4TogetherSuite
    parent_readiness: Phase4TogetherReadinessBundle
    corrected_capability_plan: TogetherCapabilityPlan
    corrected_suite: Phase4TogetherSuite
    corrected_readiness: Phase4TogetherReadinessBundle
    robustness_profile: Phase4ERobustnessProfile
    response_semantics_manifest: ProviderResponseInvariantManifest
    development_fixture: EvaluationFixture
    development_session: PrequentialSessionScript
    development_semantic_map: AuthoredSemanticMapBundle


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


def _dump_entries(
    entries: list[QualificationCallPlanEntry],
) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in entries]


class QualificationDeploymentScopeStatus(str, Enum):
    """Whether one frozen candidate/deployment can enter qualification."""

    RUNNABLE = "runnable"
    DEPLOYMENT_INCONCLUSIVE_NOT_RUN = (
        "provider_deployment_inconclusive_not_run"
    )


class QualificationExecutionFailurePolicy(str, Enum):
    """Predeclared treatment of provider failures during qualification."""

    PAUSE_WITHOUT_SELECTION_PENDING_REVIEW = (
        "pause_without_selection_pending_review"
    )


class QualificationScopeCandidate(ContractModel):
    """Exact scope and cost surface for one member of the frozen roster."""

    record_version: Literal[
        "phase4_qualification_scope_candidate.v1"
    ] = "phase4_qualification_scope_candidate.v1"
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    capability_outcome_sha256: Sha256Digest
    capability_disposition: CandidateCapabilityDisposition
    scope_status: QualificationDeploymentScopeStatus
    source_manifest_entry_count: Literal[152] = (
        QUALIFICATION_ENTRIES_PER_CANDIDATE
    )
    scoped_qualification_entry_count: NonNegativeCount
    scoped_entries_sha256: Sha256Digest | None = None
    scoped_call_ids_sha256: Sha256Digest | None = None
    carried_success_count: NonNegativeCount
    carried_success_evidence_sha256: Sha256Digest | None = None
    carried_call_ids_sha256: Sha256Digest | None = None
    new_provider_call_count: NonNegativeCount
    new_provider_entries_sha256: Sha256Digest | None = None
    new_provider_call_ids_sha256: Sha256Digest | None = None
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd
    included_in_comparison_and_selection: bool
    model_family_capability_rejected: Literal[False] = False

    @model_validator(mode="after")
    def require_status_shape(self) -> Self:
        optional_hashes = (
            self.scoped_entries_sha256,
            self.scoped_call_ids_sha256,
            self.carried_success_evidence_sha256,
            self.carried_call_ids_sha256,
            self.new_provider_entries_sha256,
            self.new_provider_call_ids_sha256,
        )
        if self.scope_status is QualificationDeploymentScopeStatus.RUNNABLE:
            if (
                self.capability_disposition
                is not CandidateCapabilityDisposition.CAPABILITY_PASSED
                or not self.included_in_comparison_and_selection
                or self.scoped_qualification_entry_count
                != QUALIFICATION_ENTRIES_PER_CANDIDATE
                or self.carried_success_count
                != CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
                or self.new_provider_call_count
                != QUALIFICATION_ENTRIES_PER_CANDIDATE
                - CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
                or any(value is None for value in optional_hashes)
            ):
                raise ValueError("runnable qualification candidate has wrong shape")
        elif (
            self.capability_disposition
            is not CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            or self.included_in_comparison_and_selection
            or self.scoped_qualification_entry_count != 0
            or self.carried_success_count != 0
            or self.new_provider_call_count != 0
            or self.new_projected_cost_microusd != 0
            or self.new_authorized_max_cost_microusd != 0
            or any(value is not None for value in optional_hashes)
        ):
            raise ValueError("excluded qualification deployment has wrong shape")
        return self


class TwoDeploymentQualificationAuthorizationPolicy(ContractModel):
    """Frozen constraints for the later scope-aware paid authorization."""

    record_version: Literal[
        "phase4_two_deployment_qualification_authorization_policy.v1"
    ] = "phase4_two_deployment_qualification_authorization_policy.v1"
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )
    scoped_qualification_entry_count: Literal[304] = (
        SCOPED_QUALIFICATION_ENTRY_COUNT
    )
    carried_success_count: Literal[10] = CARRIED_SUCCESS_COUNT
    new_provider_call_count: Literal[294] = NEW_PROVIDER_CALL_COUNT
    new_provider_role_call_counts: dict[LLMRole, NonNegativeCount]
    exact_request_authorization_required: Literal[True] = True
    original_manifest_ordinals_preserved: Literal[True] = True
    carried_success_hash_identity_required: Literal[True] = True
    carried_success_replay_forbidden: Literal[True] = True
    fresh_catalog_preflight_required: Literal[True] = True
    fresh_explicit_user_approval_required: Literal[True] = True
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    sequential_execution_required: Literal[True] = True
    candidate_isolated_execution_states_required: Literal[True] = True
    one_candidate_failure_cannot_suppress_other_attempt: Literal[True] = True
    checkpoint_after_every_call: Literal[True] = True
    automatic_retry_forbidden: Literal[True] = True
    fallback_deployment_forbidden: Literal[True] = True
    replacement_candidate_forbidden: Literal[True] = True
    scope_aware_authorization_schema_required: Literal[True] = True
    legacy_live_authorization_forbidden: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_new_call_matrix(self) -> Self:
        expected = {
            LLMRole.INTERVIEWER: 14,
            LLMRole.EVIDENCE_EXTRACTOR: 14,
            LLMRole.ONTOLOGY_PROPOSER: 14,
            LLMRole.DIRECT_READOUT: 126,
            LLMRole.HYBRID_READOUT: 126,
        }
        if self.new_provider_role_call_counts != expected:
            raise ValueError("amended qualification role counts differ")
        if sum(self.new_provider_role_call_counts.values()) != (
            self.new_provider_call_count
        ):
            raise ValueError("amended qualification call count differs")
        return self


class TwoDeploymentQualificationResultPolicy(ContractModel):
    """Frozen interpretation and selection rules for the amended result."""

    record_version: Literal[
        "phase4_two_deployment_qualification_result_policy.v1"
    ] = "phase4_two_deployment_qualification_result_policy.v1"
    expected_result_schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification.v1"
    ] = "preference_eval_phase4_two_deployment_qualification.v1"
    exact_runnable_candidate_results_required: Literal[2] = 2
    complete_runnable_deployment_execution_required_before_selection: Literal[
        True
    ] = True
    legacy_provider_failure_policy: Literal[
        QualificationExecutionFailurePolicy.PAUSE_WITHOUT_SELECTION_PENDING_REVIEW
    ] = (
        QualificationExecutionFailurePolicy.PAUSE_WITHOUT_SELECTION_PENDING_REVIEW
    )
    legacy_hard_failure_reasons_in_order: list[StableId] = Field(
        default_factory=lambda: list(LEGACY_QUALIFICATION_HARD_FAILURE_REASONS)
    )
    legacy_provider_failure_outcomes_in_order: list[ProviderCallOutcome] = Field(
        default_factory=lambda: list(AMENDED_SCOPE_PAUSE_OUTCOMES)
    )
    amended_candidate_hard_failure_reasons_in_order: list[StableId] = Field(
        default_factory=lambda: list(AMENDED_QUALIFICATION_HARD_FAILURE_REASONS)
    )
    provider_call_failure_is_sole_legacy_hard_gate_override: Literal[True] = True
    required_role_missing_is_candidate_hard_failure: Literal[True] = True
    invalid_output_is_candidate_hard_failure: Literal[True] = True
    role_contract_failure_is_candidate_hard_failure: Literal[True] = True
    interviewer_tool_call_failure_is_candidate_hard_failure: Literal[True] = True
    interviewer_tool_replay_failure_is_candidate_hard_failure: Literal[
        True
    ] = True
    interviewer_tool_not_exercised_is_candidate_hard_failure: Literal[
        True
    ] = True
    robustness_invalid_output_is_candidate_hard_failure: Literal[True] = True
    strict_order_or_label_flip_is_candidate_hard_failure: Literal[True] = True
    projected_study_cost_over_cap_is_candidate_hard_failure: Literal[True] = True
    one_passing_candidate_may_be_selected_after_both_complete: Literal[
        True
    ] = True
    both_passing_candidates_use_frozen_banded_selection: Literal[True] = True
    same_selected_model_used_for_every_llm_role: Literal[True] = True
    conclusion_limited_to_compared_deployments: Literal[True] = True
    excluded_deployment_remains_inconclusive: Literal[True] = True
    excluded_model_family_rejection_forbidden: Literal[True] = True
    post_hoc_replacement_forbidden: Literal[True] = True
    legacy_three_candidate_qualification_bundle_forbidden: Literal[True] = True
    selection_criteria_in_priority_order: list[QualificationCriterion]
    selection_policy: QualificationSelectionPolicy

    @model_validator(mode="after")
    def require_frozen_selection_rules(self) -> Self:
        if self.legacy_hard_failure_reasons_in_order != list(
            LEGACY_QUALIFICATION_HARD_FAILURE_REASONS
        ):
            raise ValueError("legacy qualification hard gates differ")
        if self.amended_candidate_hard_failure_reasons_in_order != list(
            AMENDED_QUALIFICATION_HARD_FAILURE_REASONS
        ):
            raise ValueError("amended qualification hard gates differ")
        if (
            self.legacy_provider_failure_outcomes_in_order
            != list(AMENDED_SCOPE_PAUSE_OUTCOMES)
            or set(self.legacy_provider_failure_outcomes_in_order)
            != PROVIDER_FAILURE_OUTCOMES
        ):
            raise ValueError("amended qualification pause outcomes differ")
        if self.selection_criteria_in_priority_order != list(
            QualificationCriterion
        ):
            raise ValueError("amended qualification criteria differ")
        if self.selection_policy != PHASE4_QUALIFICATION_SELECTION_POLICY:
            raise ValueError("amended qualification selection policy differs")
        return self


class TwoDeploymentQualificationScopeEvidenceProof(ContractModel):
    """Public-safe proof of the private retry evidence behind the amendment."""

    record_version: Literal[
        "phase4_two_deployment_qualification_scope_evidence_proof.v1"
    ] = "phase4_two_deployment_qualification_scope_evidence_proof.v1"
    proof_id: StableId
    proof_version: Literal[1] = 1
    validated_at: datetime
    capability_aggregation_sha256: Sha256Digest
    capability_aggregation_source_proof_sha256: Sha256Digest
    diagnostic_retry_plan_sha256: Sha256Digest
    diagnostic_retry_source_proof_sha256: Sha256Digest
    diagnostic_retry_authorization_sha256: Sha256Digest
    diagnostic_retry_state_sha256: Sha256Digest
    diagnostic_retry_source_state_sha256: Sha256Digest
    diagnostic_retry_fresh_catalog_sha256: Sha256Digest
    diagnostic_retry_provider_usage_sha256: Sha256Digest
    diagnostic_retry_finalization_sha256: Sha256Digest
    diagnostic_retry_http_diagnostic_sha256: Sha256Digest
    candidate_id: StableId
    disposition: Literal[
        CapabilityDiagnosticRetryDisposition.PROVIDER_OR_TRANSPORT_INCONCLUSIVE
    ] = CapabilityDiagnosticRetryDisposition.PROVIDER_OR_TRANSPORT_INCONCLUSIVE
    provider_outcome: Literal[ProviderCallOutcome.PROVIDER_ERROR] = (
        ProviderCallOutcome.PROVIDER_ERROR
    )
    failure_code: Literal["together_http_500"] = "together_http_500"
    http_status_code: Literal[500] = 500
    error_envelope_state: Literal[
        ProviderHTTPErrorEnvelopeState.STANDARD
    ] = ProviderHTTPErrorEnvelopeState.STANDARD
    error_type: Literal[ProviderHTTPErrorType.SERVER_ERROR] = (
        ProviderHTTPErrorType.SERVER_ERROR
    )
    error_code: Literal[ProviderHTTPErrorCode.NOT_PRESENT] = (
        ProviderHTTPErrorCode.NOT_PRESENT
    )
    rejected_request_field: Literal[
        ProviderRejectedRequestField.NOT_PRESENT
    ] = ProviderRejectedRequestField.NOT_PRESENT
    retry_input_tokens: Literal[0] = 0
    retry_output_tokens: Literal[0] = 0
    retry_provider_spend_microusd: Literal[0] = 0
    cumulative_capability_spend_microusd: Microusd
    model_output_present: Literal[False] = False
    provider_request_or_response_content_omitted: Literal[True] = True
    values_messages_and_context_omitted: Literal[True] = True
    full_public_source_validation_passed: Literal[True] = True
    full_private_retry_validation_passed: Literal[True] = True
    candidate_roster_unchanged: Literal[True] = True
    model_capability_rejection_recorded: Literal[False] = False
    model_selection_performed: Literal[False] = False
    provider_inference_calls_executed_by_proof_creation: Literal[0] = 0
    provider_spend_microusd_by_proof_creation: Literal[0] = 0

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        _require_aware(value, "qualification scope proof validated_at")
        return value


class TwoDeploymentQualificationScopeAmendment(ContractModel):
    """Reviewed no-spend scope for comparing two runnable deployments."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_scope.v1"
    ] = "preference_eval_phase4_two_deployment_qualification_scope.v1"
    amendment_id: StableId
    amendment_version: Literal[1] = 1
    created_at: datetime
    robustness_profile_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    capability_aggregation_sha256: Sha256Digest
    capability_aggregation_source_proof_sha256: Sha256Digest
    diagnostic_retry_plan_sha256: Sha256Digest
    diagnostic_retry_source_proof_sha256: Sha256Digest
    diagnostic_retry_scope_evidence_proof_sha256: Sha256Digest
    original_candidate_ids: list[StableId]
    runnable_candidate_ids: list[StableId]
    excluded_deployment_candidate_id: StableId
    deployment_scopes: list[QualificationScopeCandidate]
    runnable_entries_sha256: Sha256Digest
    runnable_entry_sha256s_sha256: Sha256Digest
    runnable_call_ids_sha256: Sha256Digest
    carried_entries_sha256: Sha256Digest
    carried_success_evidence_sha256: Sha256Digest
    carried_call_ids_sha256: Sha256Digest
    new_provider_entries_sha256: Sha256Digest
    new_provider_call_ids_sha256: Sha256Digest
    original_candidate_count: Literal[3] = ORIGINAL_CANDIDATE_COUNT
    runnable_candidate_count: Literal[2] = RUNNABLE_CANDIDATE_COUNT
    scoped_qualification_entry_count: Literal[304] = (
        SCOPED_QUALIFICATION_ENTRY_COUNT
    )
    carried_success_count: Literal[10] = CARRIED_SUCCESS_COUNT
    new_provider_call_count: Literal[294] = NEW_PROVIDER_CALL_COUNT
    scoped_projected_cost_microusd: Microusd
    scoped_authorized_max_cost_microusd: Microusd
    carried_projected_cost_microusd: Microusd
    carried_authorized_max_cost_microusd: Microusd
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd
    maximum_single_call_reservation_microusd: Microusd
    prior_capability_spend_microusd: Microusd
    qualification_segment_cap_microusd: Microusd
    cumulative_qualification_worst_case_microusd: Microusd
    remaining_qualification_segment_microusd: Microusd
    sequential_projected_headroom_microusd: Microusd
    authorization_policy: TwoDeploymentQualificationAuthorizationPolicy
    result_policy: TwoDeploymentQualificationResultPolicy
    original_candidate_roster_preserved: Literal[True] = True
    excluded_candidate_is_deployment_not_model_family_finding: Literal[True] = True
    replacement_candidate_ids: list[StableId] = Field(default_factory=list)
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0
    model_selection_performed: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "qualification scope amendment created_at")
        return value

    @model_validator(mode="after")
    def require_exact_scope_and_budget(self) -> Self:
        if self.replacement_candidate_ids:
            raise ValueError("qualification scope cannot replace a candidate")
        if (
            len(self.original_candidate_ids) != ORIGINAL_CANDIDATE_COUNT
            or self.original_candidate_ids != sorted(self.original_candidate_ids)
            or len(set(self.original_candidate_ids)) != ORIGINAL_CANDIDATE_COUNT
        ):
            raise ValueError("qualification scope original roster differs")
        if (
            len(self.runnable_candidate_ids) != RUNNABLE_CANDIDATE_COUNT
            or self.runnable_candidate_ids != sorted(self.runnable_candidate_ids)
            or not set(self.runnable_candidate_ids)
            < set(self.original_candidate_ids)
        ):
            raise ValueError("qualification scope runnable roster differs")
        if set(self.original_candidate_ids) - set(self.runnable_candidate_ids) != {
            self.excluded_deployment_candidate_id
        }:
            raise ValueError("qualification scope excluded deployment differs")
        if [item.candidate_id for item in self.deployment_scopes] != (
            self.original_candidate_ids
        ):
            raise ValueError("qualification scope candidate order differs")
        runnable = [
            item
            for item in self.deployment_scopes
            if item.scope_status is QualificationDeploymentScopeStatus.RUNNABLE
        ]
        excluded = [
            item
            for item in self.deployment_scopes
            if item.scope_status is not QualificationDeploymentScopeStatus.RUNNABLE
        ]
        if [item.candidate_id for item in runnable] != self.runnable_candidate_ids:
            raise ValueError("qualification runnable candidates do not reconcile")
        if len(excluded) != 1 or (
            excluded[0].candidate_id != self.excluded_deployment_candidate_id
        ):
            raise ValueError("qualification excluded deployment does not reconcile")
        totals = (
            sum(item.scoped_qualification_entry_count for item in runnable),
            sum(item.carried_success_count for item in runnable),
            sum(item.new_provider_call_count for item in runnable),
            sum(item.new_projected_cost_microusd for item in runnable),
            sum(item.new_authorized_max_cost_microusd for item in runnable),
        )
        if totals != (
            self.scoped_qualification_entry_count,
            self.carried_success_count,
            self.new_provider_call_count,
            self.new_projected_cost_microusd,
            self.new_authorized_max_cost_microusd,
        ):
            raise ValueError("qualification scope totals do not reconcile")
        if self.scoped_projected_cost_microusd != (
            self.carried_projected_cost_microusd
            + self.new_projected_cost_microusd
        ) or self.scoped_authorized_max_cost_microusd != (
            self.carried_authorized_max_cost_microusd
            + self.new_authorized_max_cost_microusd
        ):
            raise ValueError("qualification scope carried costs do not reconcile")
        if self.cumulative_qualification_worst_case_microusd != (
            self.prior_capability_spend_microusd
            + self.new_authorized_max_cost_microusd
        ):
            raise ValueError("qualification scope cumulative budget differs")
        if self.cumulative_qualification_worst_case_microusd > (
            self.qualification_segment_cap_microusd
        ):
            raise ValueError("qualification scope exceeds segment cap")
        if self.remaining_qualification_segment_microusd != (
            self.qualification_segment_cap_microusd
            - self.cumulative_qualification_worst_case_microusd
        ):
            raise ValueError("qualification scope remaining budget differs")
        if self.sequential_projected_headroom_microusd != (
            self.qualification_segment_cap_microusd
            - self.prior_capability_spend_microusd
            - self.new_projected_cost_microusd
            - self.maximum_single_call_reservation_microusd
        ):
            raise ValueError("qualification sequential headroom differs")
        return self


def _scope_candidate(
    candidate_id: str,
    *,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    aggregation: Phase4CapabilityAggregation,
    runnable: bool,
) -> QualificationScopeCandidate:
    suite_candidate = next(
        item
        for item in suite.candidates
        if item.candidate.candidate_id == candidate_id
    )
    outcome = next(
        item
        for item in aggregation.candidate_outcomes
        if item.candidate_id == candidate_id
    )
    source_entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id == candidate_id
    ]
    if len(source_entries) != QUALIFICATION_ENTRIES_PER_CANDIDATE:
        raise ValueError("qualification source candidate entry count differs")
    if not runnable:
        return QualificationScopeCandidate(
            candidate_id=candidate_id,
            candidate_sha256=content_sha256(suite_candidate.candidate),
            price_card_sha256=content_sha256(suite_candidate.price_card),
            capability_outcome_sha256=content_sha256(outcome),
            capability_disposition=outcome.disposition,
            scope_status=(
                QualificationDeploymentScopeStatus.DEPLOYMENT_INCONCLUSIVE_NOT_RUN
            ),
            scoped_qualification_entry_count=0,
            carried_success_count=0,
            new_provider_call_count=0,
            new_projected_cost_microusd=0,
            new_authorized_max_cost_microusd=0,
            included_in_comparison_and_selection=False,
        )
    capability_ids = set(readiness.capability_preflight_call_ids)
    carried_entries = [
        item for item in source_entries if item.coordinate.call_id in capability_ids
    ]
    new_entries = [
        item for item in source_entries if item.coordinate.call_id not in capability_ids
    ]
    carried_evidence = [
        item
        for item in outcome.role_evidence
        if item.status
        in {
            CapabilityRoleEvidenceStatus.CARRIED_SUCCESS,
            CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS,
        }
    ]
    if (
        len(carried_entries) != CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
        or len(carried_evidence) != CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
        or {item.coordinate.call_id for item in carried_entries}
        != {item.call_id for item in carried_evidence}
    ):
        raise ValueError("qualification carried capability successes differ")
    return QualificationScopeCandidate(
        candidate_id=candidate_id,
        candidate_sha256=content_sha256(suite_candidate.candidate),
        price_card_sha256=content_sha256(suite_candidate.price_card),
        capability_outcome_sha256=content_sha256(outcome),
        capability_disposition=outcome.disposition,
        scope_status=QualificationDeploymentScopeStatus.RUNNABLE,
        scoped_qualification_entry_count=len(source_entries),
        scoped_entries_sha256=content_sha256(_dump_entries(source_entries)),
        scoped_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in source_entries]
        ),
        carried_success_count=len(carried_evidence),
        carried_success_evidence_sha256=content_sha256(
            [item.model_dump(mode="json") for item in carried_evidence]
        ),
        carried_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in carried_entries]
        ),
        new_provider_call_count=len(new_entries),
        new_provider_entries_sha256=content_sha256(_dump_entries(new_entries)),
        new_provider_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in new_entries]
        ),
        new_projected_cost_microusd=sum(
            item.projected_cost_microusd for item in new_entries
        ),
        new_authorized_max_cost_microusd=sum(
            item.authorized_max_cost_microusd for item in new_entries
        ),
        included_in_comparison_and_selection=True,
    )


def build_two_deployment_scope_evidence_proof(
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    retry_plan: TogetherCapabilityDiagnosticRetryPlan,
    retry_proof: TogetherCapabilityDiagnosticRetrySourceProof,
    retry_authorization: TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    retry_state: TogetherCapabilityDiagnosticRetryExecutionState,
    retry_source_state: TogetherDeltaCandidateExecutionState,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    fresh_catalog: TogetherCatalogPreflightBundle,
    public_retry_inputs: QualificationScopePublicInputs,
    *,
    proof_id: str,
    validated_at: datetime,
) -> TwoDeploymentQualificationScopeEvidenceProof:
    """Validate the private retry once, then emit only finite metadata."""

    validate_capability_diagnostic_retry_plan_public(
        retry_plan,
        aggregation,
        aggregation_proof,
        *public_retry_inputs,
    )
    validate_capability_diagnostic_retry_source_proof(retry_proof, retry_plan)
    validate_capability_diagnostic_retry_authorization_bundle(
        retry_authorization,
        retry_plan,
        retry_proof,
        suite,
        profile,
        readiness,
        fresh_catalog,
        now=retry_authorization.manual_approval.approved_at,
    )
    validate_capability_diagnostic_retry_execution_state(
        retry_state,
        retry_plan,
        retry_proof,
        retry_authorization,
        retry_source_state,
        suite,
        profile,
    )
    if retry_state.completed_at is None or validated_at < retry_state.completed_at:
        raise ValueError("qualification scope proof predates diagnostic retry")
    finalization = retry_state.provider_journal.finalizations[-1]
    usage = retry_state.provider_ledger.calls[-1]
    diagnostic = retry_state.provider_error_diagnostic
    if (
        retry_state.disposition
        is not CapabilityDiagnosticRetryDisposition.PROVIDER_OR_TRANSPORT_INCONCLUSIVE
        or finalization.outcome is not ProviderCallOutcome.PROVIDER_ERROR
        or finalization.failure_code != "together_http_500"
        or diagnostic is None
        or diagnostic.http_status_code != 500
        or diagnostic.envelope_state
        is not ProviderHTTPErrorEnvelopeState.STANDARD
        or diagnostic.error_type is not ProviderHTTPErrorType.SERVER_ERROR
        or diagnostic.error_code is not ProviderHTTPErrorCode.NOT_PRESENT
        or diagnostic.rejected_request_field
        is not ProviderRejectedRequestField.NOT_PRESENT
        or usage.input_tokens != 0
        or usage.output_tokens != 0
        or retry_state.retry_provider_spend_microusd != 0
        or retry_state.retry_output is not None
    ):
        raise ValueError("diagnostic retry does not support two-deployment scope")
    return TwoDeploymentQualificationScopeEvidenceProof(
        proof_id=proof_id,
        validated_at=validated_at,
        capability_aggregation_sha256=content_sha256(aggregation),
        capability_aggregation_source_proof_sha256=content_sha256(
            aggregation_proof
        ),
        diagnostic_retry_plan_sha256=content_sha256(retry_plan),
        diagnostic_retry_source_proof_sha256=content_sha256(retry_proof),
        diagnostic_retry_authorization_sha256=content_sha256(
            retry_authorization
        ),
        diagnostic_retry_state_sha256=content_sha256(retry_state),
        diagnostic_retry_source_state_sha256=content_sha256(retry_source_state),
        diagnostic_retry_fresh_catalog_sha256=content_sha256(fresh_catalog),
        diagnostic_retry_provider_usage_sha256=content_sha256(usage),
        diagnostic_retry_finalization_sha256=content_sha256(finalization),
        diagnostic_retry_http_diagnostic_sha256=content_sha256(diagnostic),
        candidate_id=retry_plan.candidate_id,
        cumulative_capability_spend_microusd=(
            retry_state.cumulative_capability_spend_microusd
        ),
    )


def build_two_deployment_qualification_scope(
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    retry_plan: TogetherCapabilityDiagnosticRetryPlan,
    retry_proof: TogetherCapabilityDiagnosticRetrySourceProof,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    public_retry_inputs: QualificationScopePublicInputs,
    *,
    amendment_id: str,
    created_at: datetime,
) -> TwoDeploymentQualificationScopeAmendment:
    """Derive the exact two-deployment scope from reviewed public evidence."""

    validate_capability_diagnostic_retry_plan_public(
        retry_plan,
        aggregation,
        aggregation_proof,
        *public_retry_inputs,
    )
    validate_capability_diagnostic_retry_source_proof(retry_proof, retry_plan)
    if (
        evidence_proof.validated_at > created_at
        or evidence_proof.validated_at < retry_proof.validated_at
        or evidence_proof.capability_aggregation_sha256
        != content_sha256(aggregation)
        or evidence_proof.capability_aggregation_source_proof_sha256
        != content_sha256(aggregation_proof)
        or evidence_proof.diagnostic_retry_plan_sha256
        != content_sha256(retry_plan)
        or evidence_proof.diagnostic_retry_source_proof_sha256
        != content_sha256(retry_proof)
        or evidence_proof.diagnostic_retry_source_state_sha256
        != retry_plan.source_state_sha256
        or evidence_proof.diagnostic_retry_fresh_catalog_sha256
        == retry_plan.source_catalog_preflight_bundle_sha256
        or evidence_proof.candidate_id != retry_plan.candidate_id
        or evidence_proof.cumulative_capability_spend_microusd
        != aggregation.cumulative_provider_spend_microusd
    ):
        raise ValueError("qualification scope evidence proof bindings differ")
    original_ids = sorted(
        item.candidate.candidate_id for item in suite.candidates
    )
    if len(original_ids) != ORIGINAL_CANDIDATE_COUNT:
        raise ValueError("qualification scope requires original three candidates")
    runnable_ids = sorted(
        item.candidate_id
        for item in aggregation.candidate_outcomes
        if item.disposition is CandidateCapabilityDisposition.CAPABILITY_PASSED
    )
    if (
        len(runnable_ids) != RUNNABLE_CANDIDATE_COUNT
        or retry_plan.candidate_id in runnable_ids
        or set(original_ids) - set(runnable_ids) != {retry_plan.candidate_id}
    ):
        raise ValueError("qualification scope source dispositions differ")
    scopes = [
        _scope_candidate(
            candidate_id,
            suite=suite,
            readiness=readiness,
            aggregation=aggregation,
            runnable=candidate_id in runnable_ids,
        )
        for candidate_id in original_ids
    ]
    runnable_entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id in runnable_ids
    ]
    capability_ids = set(readiness.capability_preflight_call_ids)
    carried_entries = [
        item
        for item in runnable_entries
        if item.coordinate.call_id in capability_ids
    ]
    new_entries = [
        item
        for item in runnable_entries
        if item.coordinate.call_id not in capability_ids
    ]
    carried_evidence = [
        item
        for outcome in aggregation.candidate_outcomes
        if outcome.candidate_id in runnable_ids
        for item in outcome.role_evidence
        if item.status
        in {
            CapabilityRoleEvidenceStatus.CARRIED_SUCCESS,
            CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS,
        }
    ]
    segment_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.QUALIFICATION
    ]
    prior_spend = evidence_proof.cumulative_capability_spend_microusd
    new_authorized = sum(
        item.authorized_max_cost_microusd for item in new_entries
    )
    carried_projected = sum(
        item.projected_cost_microusd for item in carried_entries
    )
    carried_authorized = sum(
        item.authorized_max_cost_microusd for item in carried_entries
    )
    new_projected = sum(item.projected_cost_microusd for item in new_entries)
    maximum_reservation = max(
        item.authorized_max_cost_microusd for item in new_entries
    )
    amendment = TwoDeploymentQualificationScopeAmendment(
        amendment_id=amendment_id,
        created_at=created_at,
        robustness_profile_sha256=content_sha256(profile),
        together_suite_sha256=content_sha256(suite),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        capability_aggregation_sha256=content_sha256(aggregation),
        capability_aggregation_source_proof_sha256=content_sha256(
            aggregation_proof
        ),
        diagnostic_retry_plan_sha256=content_sha256(retry_plan),
        diagnostic_retry_source_proof_sha256=content_sha256(retry_proof),
        diagnostic_retry_scope_evidence_proof_sha256=content_sha256(
            evidence_proof
        ),
        original_candidate_ids=original_ids,
        runnable_candidate_ids=runnable_ids,
        excluded_deployment_candidate_id=retry_plan.candidate_id,
        deployment_scopes=scopes,
        runnable_entries_sha256=content_sha256(_dump_entries(runnable_entries)),
        runnable_entry_sha256s_sha256=content_sha256(
            [content_sha256(item) for item in runnable_entries]
        ),
        runnable_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in runnable_entries]
        ),
        carried_entries_sha256=content_sha256(_dump_entries(carried_entries)),
        carried_success_evidence_sha256=content_sha256(
            [item.model_dump(mode="json") for item in carried_evidence]
        ),
        carried_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in carried_entries]
        ),
        new_provider_entries_sha256=content_sha256(_dump_entries(new_entries)),
        new_provider_call_ids_sha256=content_sha256(
            [item.coordinate.call_id for item in new_entries]
        ),
        scoped_projected_cost_microusd=(
            carried_projected + new_projected
        ),
        scoped_authorized_max_cost_microusd=(
            carried_authorized + new_authorized
        ),
        carried_projected_cost_microusd=carried_projected,
        carried_authorized_max_cost_microusd=carried_authorized,
        new_projected_cost_microusd=new_projected,
        new_authorized_max_cost_microusd=new_authorized,
        maximum_single_call_reservation_microusd=maximum_reservation,
        prior_capability_spend_microusd=prior_spend,
        qualification_segment_cap_microusd=segment_cap,
        cumulative_qualification_worst_case_microusd=(
            prior_spend + new_authorized
        ),
        remaining_qualification_segment_microusd=(
            segment_cap - prior_spend - new_authorized
        ),
        sequential_projected_headroom_microusd=(
            segment_cap - prior_spend - new_projected - maximum_reservation
        ),
        authorization_policy=TwoDeploymentQualificationAuthorizationPolicy(
            new_provider_role_call_counts={
                role: sum(
                    item.coordinate.role is role for item in new_entries
                )
                for role in LLMRole
            }
        ),
        result_policy=TwoDeploymentQualificationResultPolicy(
            selection_criteria_in_priority_order=list(QualificationCriterion),
            selection_policy=PHASE4_QUALIFICATION_SELECTION_POLICY,
        ),
    )
    return amendment


def validate_two_deployment_qualification_scope(
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    retry_plan: TogetherCapabilityDiagnosticRetryPlan,
    retry_proof: TogetherCapabilityDiagnosticRetrySourceProof,
    suite: Phase4TogetherSuite,
    readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    public_retry_inputs: QualificationScopePublicInputs,
) -> None:
    rebuilt = build_two_deployment_qualification_scope(
        aggregation,
        aggregation_proof,
        retry_plan,
        retry_proof,
        evidence_proof,
        suite,
        readiness,
        profile,
        public_retry_inputs,
        amendment_id=amendment.amendment_id,
        created_at=amendment.created_at,
    )
    if rebuilt != amendment:
        raise ValueError("two-deployment qualification scope does not rebuild")


def qualification_scope_summary(
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
) -> dict[str, object]:
    return {
        "schema_version": amendment.schema_version,
        "amendment_sha256": content_sha256(amendment),
        "evidence_proof_sha256": content_sha256(evidence_proof),
        "original_candidate_count": amendment.original_candidate_count,
        "runnable_candidate_count": amendment.runnable_candidate_count,
        "excluded_deployment_count": 1,
        "scoped_qualification_entry_count": (
            amendment.scoped_qualification_entry_count
        ),
        "carried_success_count": amendment.carried_success_count,
        "new_provider_call_count": amendment.new_provider_call_count,
        "scoped_projected_cost_microusd": (
            amendment.scoped_projected_cost_microusd
        ),
        "scoped_authorized_max_cost_microusd": (
            amendment.scoped_authorized_max_cost_microusd
        ),
        "new_projected_cost_microusd": amendment.new_projected_cost_microusd,
        "new_authorized_max_cost_microusd": (
            amendment.new_authorized_max_cost_microusd
        ),
        "cumulative_qualification_worst_case_microusd": (
            amendment.cumulative_qualification_worst_case_microusd
        ),
        "sequential_projected_headroom_microusd": (
            amendment.sequential_projected_headroom_microusd
        ),
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
        "model_selection_performed": False,
        "participant_content_omitted": True,
    }


def load_two_deployment_qualification_scope(
    path: str | Path,
) -> TwoDeploymentQualificationScopeAmendment:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TwoDeploymentQualificationScopeAmendment.model_validate(payload)


def load_two_deployment_scope_evidence_proof(
    path: str | Path,
) -> TwoDeploymentQualificationScopeEvidenceProof:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TwoDeploymentQualificationScopeEvidenceProof.model_validate(payload)
