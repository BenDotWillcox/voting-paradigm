"""Zero-spend execution and carry-forward contracts for amended qualification.

This module deliberately stops before live authorization or provider execution.
It freezes the development-metric operationalization, derives the exact two-
deployment execution surface from reviewed public artifacts, and rebuilds the
ten private capability successes that the scope amendment permits carrying
forward without replay.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    Probability,
    ResponseState,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import TogetherCapabilityOutputRecord, TogetherCapabilityPlan
from .phase4_capability_aggregation import (
    CapabilityRoleEvidence,
    CapabilityRoleEvidenceStatus,
    Phase4CapabilityAggregation,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityExecutionState,
)
from .phase4_capability_recovery import TogetherDeltaCandidateExecutionState
from .phase4_provider import (
    ProviderCallOutcome,
    validate_provider_execution_journal,
)
from .phase4_qualification_scope import (
    CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE,
    CARRIED_SUCCESS_COUNT,
    NEW_PROVIDER_CALL_COUNT,
    QUALIFICATION_ENTRIES_PER_CANDIDATE,
    RUNNABLE_CANDIDATE_COUNT,
    QualificationDeploymentScopeStatus,
    TwoDeploymentQualificationScopeAmendment,
    TwoDeploymentQualificationScopeEvidenceProof,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    QualificationCallPlanEntry,
    QualificationVariant,
    rebuild_qualification_call,
)
from .phase4_robustness import (
    LLMRole,
    Phase4ERobustnessProfile,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .prequential import PrequentialSessionScript


NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]

FROZEN_TWO_DEPLOYMENT_QUALIFICATION_EXECUTION_PLAN_SHA256 = (
    "11b199fe5a7b2e312172b3c949a4f99c80ca58013a38be4ed76d98eb64c485a1"
)


class QualificationMetricAggregation(str, Enum):
    """How canonical readout roles contribute to development quality."""

    EQUAL_WEIGHT_ACROSS_ROLES = "equal_weight_across_roles"


class QualificationTopChoiceScoring(str, Enum):
    """Frozen accuracy convention for tied maximum probabilities."""

    FRACTIONAL_CREDIT_ACROSS_MAXIMUM_TIES = (
        "fractional_credit_across_maximum_probability_ties"
    )


class QualificationRobustnessSliceUnit(str, Enum):
    """Smallest unit retained before robustness aggregation."""

    CANDIDATE_ROLE_MEASURE = "candidate_role_measure"


class TwoDeploymentQualificationMetricPolicy(ContractModel):
    """Exact public-development metric operationalization for this run."""

    record_version: Literal[
        "phase4_two_deployment_qualification_metric_policy.v1"
    ] = "phase4_two_deployment_qualification_metric_policy.v1"
    eligible_response_states: list[ResponseState] = Field(
        default_factory=lambda: [ResponseState.CHOICE]
    )
    prediction_variant: Literal[QualificationVariant.CANONICAL] = (
        QualificationVariant.CANONICAL
    )
    quality_roles_in_order: list[LLMRole] = Field(
        default_factory=lambda: [
            LLMRole.DIRECT_READOUT,
            LLMRole.HYBRID_READOUT,
        ]
    )
    role_weights: dict[LLMRole, Probability] = Field(
        default_factory=lambda: {
            LLMRole.DIRECT_READOUT: 0.5,
            LLMRole.HYBRID_READOUT: 0.5,
        }
    )
    role_aggregation: Literal[
        QualificationMetricAggregation.EQUAL_WEIGHT_ACROSS_ROLES
    ] = QualificationMetricAggregation.EQUAL_WEIGHT_ACROSS_ROLES
    log_loss_probability_floor: Literal[1e-15] = 1e-15
    delegated_risk_thresholds: list[Probability] = Field(
        default_factory=lambda: [0.65, 0.75, 0.85, 0.95]
    )
    top_choice_scoring: Literal[
        QualificationTopChoiceScoring.FRACTIONAL_CREDIT_ACROSS_MAXIMUM_TIES
    ] = QualificationTopChoiceScoring.FRACTIONAL_CREDIT_ACROSS_MAXIMUM_TIES
    robustness_slice_unit: Literal[
        QualificationRobustnessSliceUnit.CANDIDATE_ROLE_MEASURE
    ] = QualificationRobustnessSliceUnit.CANDIDATE_ROLE_MEASURE
    robustness_slice_dimensions_in_order: list[Literal[
        "candidate_id",
        "role",
        "measure_id",
    ]] = Field(default_factory=lambda: ["candidate_id", "role", "measure_id"])
    participant_responses_used_for_model_or_prompt_selection: Literal[False] = False

    @model_validator(mode="after")
    def require_exact_operationalization(self) -> Self:
        if self.eligible_response_states != [ResponseState.CHOICE]:
            raise ValueError("qualification metrics must use CHOICE responses only")
        expected_roles = [
            LLMRole.DIRECT_READOUT,
            LLMRole.HYBRID_READOUT,
        ]
        if self.quality_roles_in_order != expected_roles:
            raise ValueError("qualification quality roles differ")
        if self.role_weights != {
            LLMRole.DIRECT_READOUT: 0.5,
            LLMRole.HYBRID_READOUT: 0.5,
        }:
            raise ValueError("qualification readout roles must be equally weighted")
        if self.delegated_risk_thresholds != [0.65, 0.75, 0.85, 0.95]:
            raise ValueError("qualification delegated-risk grid differs")
        if self.robustness_slice_dimensions_in_order != [
            "candidate_id",
            "role",
            "measure_id",
        ]:
            raise ValueError("qualification robustness slice differs")
        return self


TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY = (
    TwoDeploymentQualificationMetricPolicy()
)


class QualificationCallDisposition(str, Enum):
    """Whether an exact scoped call is reused or sent once."""

    CARRIED_SUCCESS = "carried_success"
    EXECUTE_PROVIDER = "execute_provider"


class TwoDeploymentQualificationCallPlan(ContractModel):
    """One original-manifest coordinate in the amended execution surface."""

    record_version: Literal[
        "phase4_two_deployment_qualification_call_plan.v1"
    ] = "phase4_two_deployment_qualification_call_plan.v1"
    candidate_ordinal: PositiveCount
    source_manifest_ordinal: PositiveCount
    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    measure_id: StableId
    measure_version: PositiveCount
    variant_id: QualificationVariant
    disposition: QualificationCallDisposition
    source_entry_sha256: Sha256Digest
    source_entry: QualificationCallPlanEntry
    projected_cost_microusd: Microusd
    authorized_max_cost_microusd: Microusd

    @model_validator(mode="after")
    def require_exact_source_entry(self) -> Self:
        coordinate = self.source_entry.coordinate
        if (
            self.source_manifest_ordinal,
            self.call_id,
            self.candidate_id,
            self.role,
            self.measure_id,
            self.measure_version,
            self.variant_id,
            self.projected_cost_microusd,
            self.authorized_max_cost_microusd,
            self.source_entry_sha256,
        ) != (
            coordinate.ordinal,
            coordinate.call_id,
            coordinate.candidate_id,
            coordinate.role,
            coordinate.measure_id,
            coordinate.measure_version,
            coordinate.variant_id,
            self.source_entry.projected_cost_microusd,
            self.source_entry.authorized_max_cost_microusd,
            content_sha256(self.source_entry),
        ):
            raise ValueError("qualification call does not bind its source entry")
        return self


class TwoDeploymentCandidateQualificationPlan(ContractModel):
    """Candidate-isolated 152-coordinate plan with a 5/147 partition."""

    record_version: Literal[
        "phase4_two_deployment_candidate_qualification_plan.v1"
    ] = "phase4_two_deployment_candidate_qualification_plan.v1"
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    source_manifest_entry_count: Literal[152] = QUALIFICATION_ENTRIES_PER_CANDIDATE
    carried_success_count: Literal[5] = CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
    provider_call_count: Literal[147] = (
        QUALIFICATION_ENTRIES_PER_CANDIDATE
        - CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
    )
    calls: list[TwoDeploymentQualificationCallPlan] = Field(
        min_length=QUALIFICATION_ENTRIES_PER_CANDIDATE,
        max_length=QUALIFICATION_ENTRIES_PER_CANDIDATE,
    )
    source_manifest_ordinals_sha256: Sha256Digest
    source_entry_sha256s_sha256: Sha256Digest
    carried_call_ids_sha256: Sha256Digest
    provider_call_ids_sha256: Sha256Digest
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd

    @model_validator(mode="after")
    def require_exact_candidate_partition(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.calls):
            raise ValueError("candidate qualification plan mixes candidates")
        if [item.candidate_ordinal for item in self.calls] != list(
            range(1, QUALIFICATION_ENTRIES_PER_CANDIDATE + 1)
        ):
            raise ValueError("candidate qualification ordinals differ")
        source_ordinals = [item.source_manifest_ordinal for item in self.calls]
        if source_ordinals != sorted(source_ordinals) or len(source_ordinals) != len(
            set(source_ordinals)
        ):
            raise ValueError("candidate source ordinals must be unique and ordered")
        carried = [
            item
            for item in self.calls
            if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
        ]
        provider = [
            item
            for item in self.calls
            if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
        ]
        if (len(carried), len(provider)) != (
            self.carried_success_count,
            self.provider_call_count,
        ):
            raise ValueError("candidate qualification partition differs")
        if self.source_manifest_ordinals_sha256 != content_sha256(source_ordinals):
            raise ValueError("candidate source-ordinal hash differs")
        if self.source_entry_sha256s_sha256 != content_sha256(
            [item.source_entry_sha256 for item in self.calls]
        ):
            raise ValueError("candidate source-entry hashes differ")
        if self.carried_call_ids_sha256 != content_sha256(
            [item.call_id for item in carried]
        ) or self.provider_call_ids_sha256 != content_sha256(
            [item.call_id for item in provider]
        ):
            raise ValueError("candidate qualification call-id hashes differ")
        if (
            self.new_projected_cost_microusd,
            self.new_authorized_max_cost_microusd,
        ) != (
            sum(item.projected_cost_microusd for item in provider),
            sum(item.authorized_max_cost_microusd for item in provider),
        ):
            raise ValueError("candidate qualification costs differ")
        return self


class TwoDeploymentQualificationExecutionPlan(ContractModel):
    """Deterministic zero-spend plan for the exact reviewed amended scope."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_execution_plan.v1"
    ] = "preference_eval_phase4_two_deployment_qualification_execution_plan.v1"
    plan_id: StableId
    plan_version: Literal[1] = 1
    created_at: datetime
    qualification_scope_sha256: Sha256Digest
    qualification_scope_evidence_proof_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    metric_policy_sha256: Sha256Digest
    candidate_plans: list[TwoDeploymentCandidateQualificationPlan] = Field(
        min_length=RUNNABLE_CANDIDATE_COUNT,
        max_length=RUNNABLE_CANDIDATE_COUNT,
    )
    scoped_entry_count: Literal[304] = 304
    carried_success_count: Literal[10] = CARRIED_SUCCESS_COUNT
    provider_call_count: Literal[294] = NEW_PROVIDER_CALL_COUNT
    source_manifest_ordinals_sha256: Sha256Digest
    carried_call_ids_sha256: Sha256Digest
    provider_call_ids_sha256: Sha256Digest
    new_projected_cost_microusd: Microusd
    new_authorized_max_cost_microusd: Microusd
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualification execution plan time needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_two_candidate_surface(self) -> Self:
        candidate_ids = [item.candidate_id for item in self.candidate_plans]
        if candidate_ids != sorted(candidate_ids) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError("qualification execution candidates differ")
        calls = sorted(
            (item for plan in self.candidate_plans for item in plan.calls),
            key=lambda item: item.source_manifest_ordinal,
        )
        carried = [
            item
            for item in calls
            if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
        ]
        provider = [
            item
            for item in calls
            if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
        ]
        if (len(calls), len(carried), len(provider)) != (
            self.scoped_entry_count,
            self.carried_success_count,
            self.provider_call_count,
        ):
            raise ValueError("qualification execution totals differ")
        if self.source_manifest_ordinals_sha256 != content_sha256(
            [item.source_manifest_ordinal for item in calls]
        ):
            raise ValueError("qualification source-ordinal hash differs")
        if self.carried_call_ids_sha256 != content_sha256(
            [item.call_id for item in carried]
        ) or self.provider_call_ids_sha256 != content_sha256(
            [item.call_id for item in provider]
        ):
            raise ValueError("qualification execution call-id hashes differ")
        if (
            self.new_projected_cost_microusd,
            self.new_authorized_max_cost_microusd,
        ) != (
            sum(item.projected_cost_microusd for item in provider),
            sum(item.authorized_max_cost_microusd for item in provider),
        ):
            raise ValueError("qualification execution costs differ")
        return self


def _dump_entries(
    entries: Sequence[QualificationCallPlanEntry],
) -> list[dict[str, object]]:
    return [item.model_dump(mode="json") for item in entries]


def _candidate_plan(
    candidate_id: str,
    amendment: TwoDeploymentQualificationScopeAmendment,
    readiness: Phase4TogetherReadinessBundle,
) -> TwoDeploymentCandidateQualificationPlan:
    source_scope = next(
        item
        for item in amendment.deployment_scopes
        if item.candidate_id == candidate_id
    )
    source_entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id == candidate_id
    ]
    capability_ids = set(readiness.capability_preflight_call_ids)
    calls = [
        TwoDeploymentQualificationCallPlan(
            candidate_ordinal=index,
            source_manifest_ordinal=entry.coordinate.ordinal,
            call_id=entry.coordinate.call_id,
            candidate_id=entry.coordinate.candidate_id,
            role=entry.coordinate.role,
            measure_id=entry.coordinate.measure_id,
            measure_version=entry.coordinate.measure_version,
            variant_id=entry.coordinate.variant_id,
            disposition=(
                QualificationCallDisposition.CARRIED_SUCCESS
                if entry.coordinate.call_id in capability_ids
                else QualificationCallDisposition.EXECUTE_PROVIDER
            ),
            source_entry_sha256=content_sha256(entry),
            source_entry=entry.model_copy(deep=True),
            projected_cost_microusd=entry.projected_cost_microusd,
            authorized_max_cost_microusd=entry.authorized_max_cost_microusd,
        )
        for index, entry in enumerate(source_entries, start=1)
    ]
    carried = [
        item
        for item in calls
        if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
    ]
    provider = [
        item
        for item in calls
        if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    ]
    plan = TwoDeploymentCandidateQualificationPlan(
        candidate_id=candidate_id,
        candidate_sha256=source_scope.candidate_sha256,
        price_card_sha256=source_scope.price_card_sha256,
        calls=calls,
        source_manifest_ordinals_sha256=content_sha256(
            [item.source_manifest_ordinal for item in calls]
        ),
        source_entry_sha256s_sha256=content_sha256(
            [item.source_entry_sha256 for item in calls]
        ),
        carried_call_ids_sha256=content_sha256(
            [item.call_id for item in carried]
        ),
        provider_call_ids_sha256=content_sha256(
            [item.call_id for item in provider]
        ),
        new_projected_cost_microusd=sum(
            item.projected_cost_microusd for item in provider
        ),
        new_authorized_max_cost_microusd=sum(
            item.authorized_max_cost_microusd for item in provider
        ),
    )
    if (
        source_scope.scoped_entries_sha256
        != content_sha256(_dump_entries(source_entries))
        or source_scope.carried_call_ids_sha256 != plan.carried_call_ids_sha256
        or source_scope.new_provider_call_ids_sha256 != plan.provider_call_ids_sha256
        or source_scope.new_projected_cost_microusd
        != plan.new_projected_cost_microusd
        or source_scope.new_authorized_max_cost_microusd
        != plan.new_authorized_max_cost_microusd
    ):
        raise ValueError("qualification candidate plan differs from reviewed scope")
    return plan


def build_two_deployment_qualification_plan(
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    readiness: Phase4TogetherReadinessBundle,
    *,
    plan_id: str,
    created_at: datetime,
) -> TwoDeploymentQualificationExecutionPlan:
    """Derive the 304-coordinate 10-carry/294-send plan without private input."""

    if (
        amendment.diagnostic_retry_scope_evidence_proof_sha256
        != content_sha256(evidence_proof)
        or amendment.readiness_sha256 != content_sha256(readiness)
        or amendment.source_qualification_manifest_sha256
        != content_sha256(readiness.qualification_manifest)
    ):
        raise ValueError("qualification execution source bindings differ")
    runnable_scopes = [
        item
        for item in amendment.deployment_scopes
        if item.scope_status is QualificationDeploymentScopeStatus.RUNNABLE
    ]
    if [item.candidate_id for item in runnable_scopes] != (
        amendment.runnable_candidate_ids
    ):
        raise ValueError("qualification execution runnable roster differs")
    candidate_plans = [
        _candidate_plan(candidate_id, amendment, readiness)
        for candidate_id in amendment.runnable_candidate_ids
    ]
    calls = sorted(
        (item for plan in candidate_plans for item in plan.calls),
        key=lambda item: item.source_manifest_ordinal,
    )
    carried = [
        item
        for item in calls
        if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
    ]
    provider = [
        item
        for item in calls
        if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    ]
    if (
        amendment.runnable_entries_sha256
        != content_sha256(_dump_entries([item.source_entry for item in calls]))
        or amendment.carried_call_ids_sha256
        != content_sha256([item.call_id for item in carried])
        or amendment.new_provider_call_ids_sha256
        != content_sha256([item.call_id for item in provider])
    ):
        raise ValueError("qualification execution plan differs from amendment")
    return TwoDeploymentQualificationExecutionPlan(
        plan_id=plan_id,
        created_at=created_at,
        qualification_scope_sha256=content_sha256(amendment),
        qualification_scope_evidence_proof_sha256=content_sha256(evidence_proof),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        metric_policy_sha256=content_sha256(
            TWO_DEPLOYMENT_QUALIFICATION_METRIC_POLICY
        ),
        candidate_plans=candidate_plans,
        source_manifest_ordinals_sha256=content_sha256(
            [item.source_manifest_ordinal for item in calls]
        ),
        carried_call_ids_sha256=content_sha256(
            [item.call_id for item in carried]
        ),
        provider_call_ids_sha256=content_sha256(
            [item.call_id for item in provider]
        ),
        new_projected_cost_microusd=sum(
            item.projected_cost_microusd for item in provider
        ),
        new_authorized_max_cost_microusd=sum(
            item.authorized_max_cost_microusd for item in provider
        ),
    )


def validate_two_deployment_qualification_plan(
    plan: TwoDeploymentQualificationExecutionPlan,
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    readiness: Phase4TogetherReadinessBundle,
) -> None:
    rebuilt = build_two_deployment_qualification_plan(
        amendment,
        evidence_proof,
        readiness,
        plan_id=plan.plan_id,
        created_at=plan.created_at,
    )
    if rebuilt != plan:
        raise ValueError("two-deployment qualification plan does not rebuild")


CapabilitySourceState: TypeAlias = (
    TogetherCandidateCapabilityExecutionState | TogetherDeltaCandidateExecutionState
)


class QualificationCarryRecord(ContractModel):
    """One private capability output revalidated under the current adapter."""

    record_version: Literal[
        "phase4_two_deployment_qualification_carry_record.v1"
    ] = "phase4_two_deployment_qualification_carry_record.v1"
    candidate_id: StableId
    role: LLMRole
    call_id: StableId
    source_manifest_ordinal: PositiveCount
    source_entry_sha256: Sha256Digest
    corrected_capability_call_sha256: Sha256Digest
    aggregation_role_evidence_sha256: Sha256Digest
    source_state_schema_version: str
    source_state_sha256: Sha256Digest
    source_authorization_sha256: Sha256Digest
    source_provider_ledger_sha256: Sha256Digest
    source_provider_journal_sha256: Sha256Digest
    request_binding_sha256: Sha256Digest
    provider_authorization_sha256: Sha256Digest
    provider_usage_sha256: Sha256Digest
    finalization_sha256: Sha256Digest
    source_output_sha256: Sha256Digest
    current_response_schema_sha256: Sha256Digest
    current_response_validator_sha256: Sha256Digest | None = None
    current_revalidated_output_sha256: Sha256Digest
    output_payload: JsonValue
    provider_outcome: Literal[ProviderCallOutcome.SUCCESS] = (
        ProviderCallOutcome.SUCCESS
    )
    tool_call_count: NonNegativeCount
    tool_call_failure_count: Literal[0] = 0
    response_validation_context_sha256: Sha256Digest | None = None
    interviewer_tool_result_transcript_retained: Literal[False] = False
    interviewer_tool_result_replay_verified: Literal[False] = False

    @model_validator(mode="after")
    def require_success_and_payload_bindings(self) -> Self:
        if self.source_output_sha256 != content_sha256(self.output_payload):
            raise ValueError("carried output payload hash differs")
        if self.current_revalidated_output_sha256 != self.source_output_sha256:
            raise ValueError("carried output changes under current adapter")
        if self.role is LLMRole.INTERVIEWER:
            if self.tool_call_count <= 0:
                raise ValueError("carried interviewer lacks a successful tool call")
        elif self.tool_call_count != 0:
            raise ValueError("non-interviewer carry cannot report tool calls")
        return self


class TwoDeploymentQualificationCarryBundle(ContractModel):
    """Private bundle of the exact ten non-replayed capability successes."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_qualification_carry.v1"
    ] = "preference_eval_phase4_two_deployment_qualification_carry.v1"
    bundle_id: StableId
    bundle_version: Literal[1] = 1
    created_at: datetime
    execution_plan_sha256: Sha256Digest
    qualification_scope_sha256: Sha256Digest
    qualification_scope_evidence_proof_sha256: Sha256Digest
    capability_aggregation_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    development_fixture_sha256: Sha256Digest
    development_session_sha256: Sha256Digest
    development_semantic_map_sha256: Sha256Digest
    source_state_sha256s: list[Sha256Digest]
    records: list[QualificationCarryRecord] = Field(
        min_length=CARRIED_SUCCESS_COUNT,
        max_length=CARRIED_SUCCESS_COUNT,
    )
    carried_success_count: Literal[10] = CARRIED_SUCCESS_COUNT
    candidate_count: Literal[2] = RUNNABLE_CANDIDATE_COUNT
    interviewer_record_count: Literal[2] = RUNNABLE_CANDIDATE_COUNT
    interviewer_tool_result_transcripts_retained: Literal[False] = False
    interviewer_tool_result_replay_verified: Literal[False] = False
    provider_inference_calls_executed_by_bundle_creation: Literal[0] = 0
    provider_spend_microusd_by_bundle_creation: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualification carry bundle time needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_carry_matrix(self) -> Self:
        coordinates = [(item.candidate_id, item.role) for item in self.records]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("qualification carry records duplicate a role")
        counts = Counter(item.candidate_id for item in self.records)
        if len(counts) != self.candidate_count or set(counts.values()) != {
            CAPABILITY_SUCCESSES_PER_RUNNABLE_CANDIDATE
        }:
            raise ValueError("qualification carry candidate coverage differs")
        if Counter(item.role for item in self.records) != Counter(
            {role: RUNNABLE_CANDIDATE_COUNT for role in LLMRole}
        ):
            raise ValueError("qualification carry role matrix differs")
        if sum(item.role is LLMRole.INTERVIEWER for item in self.records) != (
            self.interviewer_record_count
        ):
            raise ValueError("qualification carried interviewer count differs")
        if self.source_state_sha256s != sorted(set(self.source_state_sha256s)):
            raise ValueError("qualification carry source states must be canonical")
        if self.source_state_sha256s != sorted(
            {item.source_state_sha256 for item in self.records}
        ):
            raise ValueError("qualification carry source-state inventory differs")
        return self


def _state_schema_version(state: CapabilitySourceState) -> str:
    return state.schema_version


def _successful_evidence_by_call(
    aggregation: Phase4CapabilityAggregation,
    runnable_candidate_ids: Sequence[str],
) -> dict[str, CapabilityRoleEvidence]:
    result: dict[str, CapabilityRoleEvidence] = {}
    for outcome in aggregation.candidate_outcomes:
        if outcome.candidate_id not in runnable_candidate_ids:
            continue
        for evidence in outcome.role_evidence:
            if evidence.status not in {
                CapabilityRoleEvidenceStatus.CARRIED_SUCCESS,
                CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS,
            }:
                continue
            if evidence.call_id in result:
                raise ValueError("qualification carry evidence duplicates a call")
            result[evidence.call_id] = evidence
    return result


def build_two_deployment_carry_bundle(
    plan: TwoDeploymentQualificationExecutionPlan,
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    aggregation: Phase4CapabilityAggregation,
    corrected_capability_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_states: Sequence[CapabilitySourceState],
    *,
    bundle_id: str,
    created_at: datetime,
) -> TwoDeploymentQualificationCarryBundle:
    """Validate and rehydrate the exact ten reviewed capability successes."""

    validate_two_deployment_qualification_plan(
        plan,
        amendment,
        evidence_proof,
        readiness,
    )
    if (
        amendment.capability_aggregation_sha256 != content_sha256(aggregation)
        or aggregation.corrected_capability_plan_sha256
        != content_sha256(corrected_capability_plan)
        or aggregation.corrected_together_suite_sha256 != content_sha256(suite)
        or aggregation.corrected_readiness_sha256 != content_sha256(readiness)
        or aggregation.robustness_profile_sha256 != content_sha256(profile)
        or corrected_capability_plan.qualification_manifest_sha256
        != content_sha256(readiness.qualification_manifest)
    ):
        raise ValueError("qualification carry public bindings differ")
    states_by_hash: dict[str, CapabilitySourceState] = {}
    candidates = [item.candidate for item in suite.candidates]
    price_cards = [item.price_card for item in suite.candidates]
    for state in source_states:
        state_sha256 = content_sha256(state)
        if state_sha256 in states_by_hash:
            raise ValueError("qualification carry source state is duplicated")
        validate_provider_execution_journal(
            state.provider_journal,
            state.provider_ledger,
            profile,
            candidates,
            price_cards,
            require_complete=True,
        )
        states_by_hash[state_sha256] = state
    evidence_by_call = _successful_evidence_by_call(
        aggregation,
        amendment.runnable_candidate_ids,
    )
    capability_calls = {
        item.call_id: item for item in corrected_capability_plan.calls
    }
    carried_calls = [
        item
        for candidate_plan in plan.candidate_plans
        for item in candidate_plan.calls
        if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
    ]
    records: list[QualificationCarryRecord] = []
    for call in carried_calls:
        evidence = evidence_by_call.get(call.call_id)
        capability_call = capability_calls.get(call.call_id)
        if evidence is None or capability_call is None:
            raise ValueError("qualification carry lacks reviewed role evidence")
        if (
            evidence.candidate_id,
            evidence.role,
            evidence.call_plan_sha256,
        ) != (
            call.candidate_id,
            call.role,
            content_sha256(capability_call),
        ):
            raise ValueError("qualification carry role evidence differs")
        state = states_by_hash.get(evidence.source_state_sha256)
        if state is None:
            raise ValueError("qualification carry source state is missing")
        if state.authorization_bundle_sha256 != evidence.source_authorization_sha256:
            raise ValueError("qualification carry source authorization differs")
        bindings = {
            item.call_id: item for item in state.provider_journal.request_bindings
        }
        authorizations = {
            item.call_id: item for item in state.provider_ledger.authorizations
        }
        usages = {item.call_id: item for item in state.provider_ledger.calls}
        finalizations = {
            item.call_id: item for item in state.provider_journal.finalizations
        }
        outputs = {item.call_id: item for item in state.outputs}
        try:
            binding = bindings[call.call_id]
            authorization = authorizations[call.call_id]
            usage = usages[call.call_id]
            finalization = finalizations[call.call_id]
            output: TogetherCapabilityOutputRecord = outputs[call.call_id]
        except KeyError as error:
            raise ValueError(
                "qualification carry source chain is incomplete"
            ) from error
        if (binding.model_candidate_id, binding.role) != (
            call.candidate_id,
            call.role,
        ):
            raise ValueError("qualification carry provider binding differs")
        if (
            usage.request_sha256 != authorization.request_sha256
            or usage.authorization_sha256 != content_sha256(authorization)
            or finalization.request_binding_sha256 != content_sha256(binding)
            or finalization.authorization_sha256 != content_sha256(authorization)
            or finalization.usage_sha256 != content_sha256(usage)
            or finalization.outcome is not ProviderCallOutcome.SUCCESS
            or finalization.response_sha256 != output.output_sha256
            or (output.candidate_id, output.role)
            != (call.candidate_id, call.role)
            or output.output_sha256 != evidence.output_sha256
        ):
            raise ValueError("qualification carry provider chain differs")
        if evidence.finalization_sha256 != content_sha256(finalization):
            raise ValueError("qualification carry finalization evidence differs")
        if evidence.provider_usage_sha256 is not None and (
            evidence.provider_usage_sha256 != content_sha256(usage)
        ):
            raise ValueError("qualification carry usage evidence differs")
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            call.source_entry,
            created_at=binding.created_at,
        )
        output_adapter = (
            rebuilt.response_adapter.output_adapter
            or rebuilt.response_adapter.adapter
        )
        revalidated = output_adapter.dump_python(
            output_adapter.validate_python(output.output_payload),
            mode="json",
        )
        revalidated_sha256 = content_sha256(revalidated)
        if revalidated_sha256 != output.output_sha256:
            raise ValueError("qualification carry output fails current adapter")
        records.append(
            QualificationCarryRecord(
                candidate_id=call.candidate_id,
                role=call.role,
                call_id=call.call_id,
                source_manifest_ordinal=call.source_manifest_ordinal,
                source_entry_sha256=call.source_entry_sha256,
                corrected_capability_call_sha256=content_sha256(capability_call),
                aggregation_role_evidence_sha256=content_sha256(evidence),
                source_state_schema_version=_state_schema_version(state),
                source_state_sha256=content_sha256(state),
                source_authorization_sha256=state.authorization_bundle_sha256,
                source_provider_ledger_sha256=content_sha256(state.provider_ledger),
                source_provider_journal_sha256=content_sha256(state.provider_journal),
                request_binding_sha256=content_sha256(binding),
                provider_authorization_sha256=content_sha256(authorization),
                provider_usage_sha256=content_sha256(usage),
                finalization_sha256=content_sha256(finalization),
                source_output_sha256=output.output_sha256,
                current_response_schema_sha256=(
                    rebuilt.request.binding.response_schema_sha256
                ),
                current_response_validator_sha256=(
                    rebuilt.request.binding.response_validator_sha256
                ),
                current_revalidated_output_sha256=revalidated_sha256,
                output_payload=output.output_payload,
                tool_call_count=finalization.tool_call_count,
                response_validation_context_sha256=(
                    finalization.response_validation_context_sha256
                ),
            )
        )
    records.sort(key=lambda item: (item.candidate_id, item.source_manifest_ordinal))
    bundle = TwoDeploymentQualificationCarryBundle(
        bundle_id=bundle_id,
        created_at=created_at,
        execution_plan_sha256=content_sha256(plan),
        qualification_scope_sha256=content_sha256(amendment),
        qualification_scope_evidence_proof_sha256=content_sha256(evidence_proof),
        capability_aggregation_sha256=content_sha256(aggregation),
        corrected_capability_plan_sha256=content_sha256(corrected_capability_plan),
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        readiness_sha256=content_sha256(readiness),
        development_fixture_sha256=content_sha256(fixture),
        development_session_sha256=content_sha256(session),
        development_semantic_map_sha256=content_sha256(semantic_map),
        source_state_sha256s=sorted(states_by_hash),
        records=records,
    )
    expected_evidence = [
        evidence_by_call[item.call_id].model_dump(mode="json")
        for item in carried_calls
    ]
    if amendment.carried_success_evidence_sha256 != content_sha256(
        expected_evidence
    ):
        raise ValueError("qualification carry evidence set differs from scope")
    return bundle


def validate_two_deployment_carry_bundle(
    bundle: TwoDeploymentQualificationCarryBundle,
    plan: TwoDeploymentQualificationExecutionPlan,
    amendment: TwoDeploymentQualificationScopeAmendment,
    evidence_proof: TwoDeploymentQualificationScopeEvidenceProof,
    aggregation: Phase4CapabilityAggregation,
    corrected_capability_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_states: Sequence[CapabilitySourceState],
) -> None:
    rebuilt = build_two_deployment_carry_bundle(
        plan,
        amendment,
        evidence_proof,
        aggregation,
        corrected_capability_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        source_states,
        bundle_id=bundle.bundle_id,
        created_at=bundle.created_at,
    )
    if rebuilt != bundle:
        raise ValueError("two-deployment qualification carry does not rebuild")


def load_two_deployment_qualification_plan(
    path: str | Path,
) -> TwoDeploymentQualificationExecutionPlan:
    return TwoDeploymentQualificationExecutionPlan.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_two_deployment_carry_bundle(
    path: str | Path,
) -> TwoDeploymentQualificationCarryBundle:
    return TwoDeploymentQualificationCarryBundle.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_source_state(path: str | Path) -> CapabilitySourceState:
    """Load one of the two reviewed capability-state contract shapes."""

    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("qualification source state must be a JSON object")
    schema_version = payload.get("schema_version")
    if schema_version == "preference_eval_phase4_candidate_capability_state.v1":
        return TogetherCandidateCapabilityExecutionState.model_validate(payload)
    if schema_version == "preference_eval_phase4_delta_candidate_state.v1":
        return TogetherDeltaCandidateExecutionState.model_validate(payload)
    raise ValueError("qualification source state has an unsupported schema")


def load_capability_source_states(
    paths: Sequence[str | Path],
) -> list[CapabilitySourceState]:
    if not paths:
        raise ValueError("qualification carry needs source states")
    return [load_capability_source_state(path) for path in paths]
