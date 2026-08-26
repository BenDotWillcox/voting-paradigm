"""Zero-spend role-delta plan after capability-harness corrections."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import (
    TogetherCapabilityCallPlan,
    TogetherCapabilityOutputRecord,
    TogetherCapabilityPlan,
    validate_capability_plan,
)
from .phase4_capability_adjudication import (
    TogetherAdjudicatedCandidateCapabilityAuthorization,
    TogetherCapabilityAdjudicationPolicy,
    validate_adjudicated_candidate_authorization,
    validate_capability_adjudication_policy,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
    candidate_plan_for,
    validate_candidate_capability_execution_state,
)
from .phase4_provider import (
    ProviderBudgetRuntime,
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderExecutionJournal,
    ProviderPriceCard,
    ProviderStructuredOutputDiagnostic,
    ProviderTransport,
    validate_terminal_provider_budget_breach_journal,
    validate_provider_execution_journal,
)
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST,
    ProviderResponseInvariantManifest,
    provider_response_invariant_manifest_sha256,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    QualificationCallPlanEntry,
    rebuild_qualification_call,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    OpenWeightModelCandidate,
    Phase4ERobustnessProfile,
    ProviderUsageLedger,
    provider_budget_limits_exceeded,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import (
    TogetherCapabilityProbeCheck,
    TogetherCatalogPreflightBundle,
    TogetherLiveAuthorization,
    TogetherPaidStage,
    validate_live_authorization,
)
from .prequential import PrequentialSessionScript


Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
SourceAuthorization = (
    TogetherCandidateCapabilityAuthorizationBundle
    | TogetherAdjudicatedCandidateCapabilityAuthorization
)
SourceAttemptInput = tuple[
    SourceAuthorization,
    TogetherCandidateCapabilityExecutionState,
    ProviderStructuredOutputDiagnostic | None,
]

_CARRY_FORWARD_ROLES = {
    LLMRole.DIRECT_READOUT,
    LLMRole.HYBRID_READOUT,
}


class CapabilitySourceAttempt(ContractModel):
    """Content-free binding to one historical candidate attempt."""

    record_version: Literal["phase4_capability_source_attempt.v1"] = (
        "phase4_capability_source_attempt.v1"
    )
    candidate_id: StableId
    authorization_sha256: Sha256Digest
    state_sha256: Sha256Digest
    diagnostic_sha256: Sha256Digest | None = None
    provider_call_count: Annotated[int, Field(ge=1)]
    provider_spend_microusd: Microusd
    terminal_at: datetime
    terminal_role: LLMRole
    terminal_outcome: ProviderCallOutcome
    terminal_failure_code: str
    response_schema_sha256: Sha256Digest
    validation_error_count: Annotated[int, Field(ge=0)]
    values_messages_and_context_omitted: Literal[True] = True
    disposition: Literal["harness_inconclusive"] = "harness_inconclusive"

    @field_validator("terminal_at")
    @classmethod
    def require_aware_terminal_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability source terminal_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_diagnostic_count(self) -> Self:
        if (self.diagnostic_sha256 is None) != (
            self.validation_error_count == 0
        ):
            raise ValueError("capability source diagnostic count differs")
        return self


class CarriedForwardCapabilitySuccess(ContractModel):
    """One unchanged successful role revalidated under corrected semantics."""

    record_version: Literal["phase4_capability_carried_success.v1"] = (
        "phase4_capability_carried_success.v1"
    )
    candidate_id: StableId
    role: Literal[
        LLMRole.DIRECT_READOUT,
        LLMRole.HYBRID_READOUT,
    ]
    source_state_sha256: Sha256Digest
    source_call_plan_sha256: Sha256Digest
    corrected_call_plan_sha256: Sha256Digest
    source_request_binding_sha256: Sha256Digest
    corrected_request_binding_sha256: Sha256Digest
    source_transmitted_payload_sha256: Sha256Digest
    corrected_transmitted_payload_sha256: Sha256Digest
    finalization_sha256: Sha256Digest
    source_output_sha256: Sha256Digest
    corrected_revalidated_output_sha256: Sha256Digest
    exact_transmitted_payload_unchanged: Literal[True] = True
    validator_provenance_added_to_corrected_request: Literal[True] = True
    output_revalidated_under_corrected_semantics: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_carry_forward(self) -> Self:
        if (
            self.source_transmitted_payload_sha256
            != self.corrected_transmitted_payload_sha256
        ):
            raise ValueError("carried capability wire payload changed")
        if (
            self.source_output_sha256
            != self.corrected_revalidated_output_sha256
        ):
            raise ValueError("carried capability output changed on revalidation")
        return self


class TogetherCapabilityDeltaPlan(ContractModel):
    """Reviewed zero-spend partition of carried and rerun role coordinates."""

    schema_version: Literal[
        "preference_eval_phase4_capability_delta.v1"
    ] = "preference_eval_phase4_capability_delta.v1"
    plan_id: StableId
    plan_version: PositiveVersion
    created_at: datetime
    source_adjudication_policy_sha256: Sha256Digest
    source_continuation_sha256: Sha256Digest
    source_suite_sha256: Sha256Digest
    source_readiness_sha256: Sha256Digest
    source_capability_plan_sha256: Sha256Digest
    corrected_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    source_attempts: list[CapabilitySourceAttempt] = Field(
        min_length=3,
        max_length=3,
    )
    carried_forward_successes: list[CarriedForwardCapabilitySuccess] = Field(
        min_length=4,
        max_length=4,
    )
    rerun_calls: list[TogetherCapabilityCallPlan] = Field(
        min_length=11,
        max_length=11,
    )
    preceding_provider_spend_microusd: Microusd
    prior_provider_spend_microusd: Microusd
    additional_projected_cost_microusd: Microusd
    additional_authorized_max_cost_microusd: Microusd
    original_capability_max_spend_microusd: Literal[150_000] = 150_000
    cumulative_worst_case_spend_microusd: Microusd
    qualification_authorization_permitted: Literal[False] = False
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    provider_inference_calls_executed_by_plan_creation: Literal[0] = 0
    provider_spend_microusd_by_plan_creation: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability delta created_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_partition_and_totals(self) -> Self:
        attempt_ids = [item.candidate_id for item in self.source_attempts]
        if attempt_ids != sorted(attempt_ids) or len(set(attempt_ids)) != 3:
            raise ValueError("capability delta attempts must cover candidates")
        carry_coordinates = [
            (item.candidate_id, item.role)
            for item in self.carried_forward_successes
        ]
        if carry_coordinates != sorted(
            carry_coordinates,
            key=lambda item: (item[0], item[1].value),
        ) or len(set(carry_coordinates)) != len(carry_coordinates):
            raise ValueError("capability carried coordinates must be canonical")
        source_states = {
            item.candidate_id: item.state_sha256 for item in self.source_attempts
        }
        if any(
            item.candidate_id not in source_states
            for item in self.carried_forward_successes
        ):
            raise ValueError("capability carried success binds another source")
        if any(
            item.source_state_sha256 != source_states[item.candidate_id]
            for item in self.carried_forward_successes
        ):
            raise ValueError("capability carried success binds another source")
        rerun_ordinals = [item.ordinal for item in self.rerun_calls]
        if rerun_ordinals != sorted(rerun_ordinals) or len(
            set(rerun_ordinals)
        ) != len(rerun_ordinals):
            raise ValueError("capability rerun calls must retain source order")
        rerun_coordinates = [
            (item.candidate_id, item.role) for item in self.rerun_calls
        ]
        if len(set(rerun_coordinates)) != len(rerun_coordinates):
            raise ValueError("capability rerun coordinates must be unique")
        expected = {
            (candidate_id, role)
            for candidate_id in attempt_ids
            for role in LLMRole
        }
        if set(carry_coordinates) & set(rerun_coordinates):
            raise ValueError("capability carry and rerun coordinates overlap")
        if set(carry_coordinates) | set(rerun_coordinates) != expected:
            raise ValueError("capability delta does not cover exact role matrix")
        if self.created_at < max(
            item.terminal_at for item in self.source_attempts
        ):
            raise ValueError("capability delta predates source attempts")
        source_spend = sum(
            item.provider_spend_microusd for item in self.source_attempts
        )
        if self.prior_provider_spend_microusd != (
            self.preceding_provider_spend_microusd + source_spend
        ):
            raise ValueError("capability delta prior spend does not reconcile")
        if self.additional_projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.rerun_calls
        ):
            raise ValueError("capability delta projected cost does not reconcile")
        if self.additional_authorized_max_cost_microusd != sum(
            item.authorized_max_cost_microusd for item in self.rerun_calls
        ):
            raise ValueError(
                "capability delta authorization total does not reconcile"
            )
        if self.cumulative_worst_case_spend_microusd != (
            self.prior_provider_spend_microusd
            + self.additional_authorized_max_cost_microusd
        ):
            raise ValueError("capability delta cumulative spend does not reconcile")
        if (
            self.cumulative_worst_case_spend_microusd
            > self.original_capability_max_spend_microusd
        ):
            raise ValueError("capability delta exceeds original spend ceiling")
        return self


class TogetherCapabilityDeltaSourceProof(ContractModel):
    """Content-free receipt proving the delta rebuilt from exact source audits."""

    record_version: Literal[
        "phase4_capability_delta_source_proof.v1"
    ] = "phase4_capability_delta_source_proof.v1"
    proof_id: StableId
    proof_version: PositiveVersion
    validated_at: datetime
    delta_plan_sha256: Sha256Digest
    source_adjudication_policy_sha256: Sha256Digest
    source_continuation_sha256: Sha256Digest
    source_capability_plan_sha256: Sha256Digest
    source_suite_sha256: Sha256Digest
    source_readiness_sha256: Sha256Digest
    source_attempts_sha256: Sha256Digest
    carried_forward_successes_sha256: Sha256Digest
    rerun_calls_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    full_private_source_rebuild_passed: Literal[True] = True
    values_messages_and_context_omitted: Literal[True] = True

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability delta source proof needs timezone")
        return value


class TogetherDeltaCandidatePlan(ContractModel):
    """One candidate's exact rerun subset from a reviewed delta plan."""

    schema_version: Literal[
        "preference_eval_phase4_delta_candidate_plan.v1"
    ] = "preference_eval_phase4_delta_candidate_plan.v1"
    plan_id: StableId
    plan_version: PositiveVersion
    created_at: datetime
    delta_plan_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_bundle_sha256: Sha256Digest
    qualification_manifest_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    candidate_id: StableId
    calls: list[TogetherCapabilityCallPlan] = Field(
        min_length=1,
        max_length=len(LLMRole),
    )
    projected_cost_microusd: Microusd
    all_calls_authorized_max_cost_microusd: Microusd
    candidate_capability_max_spend_microusd: Microusd
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )
    manual_paid_authorization_required: Literal[True] = True
    exact_delta_subset_required: Literal[True] = True
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("delta candidate plan created_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_candidate_subset_and_costs(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.calls):
            raise ValueError("delta candidate plan mixes candidates")
        coordinates = [(item.candidate_id, item.role) for item in self.calls]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("delta candidate plan duplicates a role")
        if [item.ordinal for item in self.calls] != sorted(
            item.ordinal for item in self.calls
        ):
            raise ValueError("delta candidate calls must retain source order")
        if self.projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.calls
        ):
            raise ValueError("delta candidate projected cost does not reconcile")
        authorized = sum(
            item.authorized_max_cost_microusd for item in self.calls
        )
        if self.all_calls_authorized_max_cost_microusd != authorized:
            raise ValueError(
                "delta candidate authorization total does not reconcile"
            )
        if self.candidate_capability_max_spend_microusd != authorized:
            raise ValueError(
                "delta candidate spend ceiling must equal exact reservations"
            )
        return self


class TogetherDeltaCandidateProgressRecord(ContractModel):
    """Content-free terminal binding for one earlier delta candidate."""

    record_version: Literal[
        "phase4_delta_candidate_progress.v1"
    ] = "phase4_delta_candidate_progress.v1"
    candidate_position: NonNegativeCount
    candidate_id: StableId
    candidate_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    terminal_state_sha256: Sha256Digest
    provider_spend_microusd: Microusd
    candidate_approved: bool
    manual_spend_ceiling_breached: bool
    provider_budget_limit_breached: bool


def _delta_candidate_progress_sha256(
    progress: Sequence[TogetherDeltaCandidateProgressRecord],
) -> str:
    return content_sha256(
        [item.model_dump(mode="json") for item in progress]
    )


class TogetherDeltaCandidateManualApproval(ContractModel):
    """Private approval for exactly one candidate's reviewed rerun subset."""

    record_version: Literal[
        "phase4_delta_candidate_capability_approval.v1"
    ] = "phase4_delta_candidate_capability_approval.v1"
    approval_id: StableId
    approval_version: PositiveVersion
    delta_plan_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    candidate_id: StableId
    candidate_order_sha256: Sha256Digest
    candidate_position: NonNegativeCount
    prior_candidate_progress_sha256: Sha256Digest
    prior_delta_provider_spend_microusd: Microusd
    remaining_authorized_max_cost_microusd: Microusd
    cumulative_worst_case_spend_microusd: Microusd
    original_capability_max_spend_microusd: Literal[150_000] = 150_000
    approved_roles: list[LLMRole] = Field(min_length=1, max_length=len(LLMRole))
    approved_call_count: PositiveCount
    approved_max_spend_microusd: Microusd
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("delta candidate approval time needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_approval_shape(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("delta candidate approval must expire later")
        if self.approved_roles != sorted(
            self.approved_roles,
            key=lambda item: item.value,
        ) or len(self.approved_roles) != len(set(self.approved_roles)):
            raise ValueError("delta candidate approval roles must be canonical")
        if self.approved_call_count != len(self.approved_roles):
            raise ValueError("delta candidate approval count differs from roles")
        return self


class TogetherDeltaCandidateAuthorizationBundle(ContractModel):
    """Private paid boundary for one candidate-specific delta subset."""

    schema_version: Literal[
        "preference_eval_phase4_delta_candidate_authorization.v1"
    ] = "preference_eval_phase4_delta_candidate_authorization.v1"
    bundle_id: StableId
    bundle_version: PositiveVersion
    delta_plan_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    candidate_order: list[StableId] = Field(min_length=1, max_length=3)
    candidate_position: NonNegativeCount
    prior_candidate_progress: list[TogetherDeltaCandidateProgressRecord] = Field(
        default_factory=list,
        max_length=2,
    )
    prior_delta_provider_spend_microusd: Microusd
    remaining_authorized_max_cost_microusd: Microusd
    cumulative_worst_case_spend_microusd: Microusd
    original_capability_max_spend_microusd: Literal[150_000] = 150_000
    manual_approval: TogetherDeltaCandidateManualApproval
    live_authorization: TogetherLiveAuthorization
    live_authorization_role_scope: Literal[
        "full_capability_stage_executor_restricted_to_delta_subset"
    ] = "full_capability_stage_executor_restricted_to_delta_subset"

    @model_validator(mode="after")
    def require_matching_approval(self) -> Self:
        if (
            self.manual_approval.delta_plan_sha256,
            self.manual_approval.source_proof_sha256,
            self.manual_approval.candidate_plan_sha256,
        ) != (
            self.delta_plan_sha256,
            self.source_proof_sha256,
            self.candidate_plan_sha256,
        ):
            raise ValueError("delta candidate approval hashes differ")
        if (
            self.manual_approval.candidate_order_sha256,
            self.manual_approval.candidate_position,
            self.manual_approval.prior_candidate_progress_sha256,
            self.manual_approval.prior_delta_provider_spend_microusd,
            self.manual_approval.remaining_authorized_max_cost_microusd,
            self.manual_approval.cumulative_worst_case_spend_microusd,
            self.manual_approval.original_capability_max_spend_microusd,
        ) != (
            content_sha256(self.candidate_order),
            self.candidate_position,
            _delta_candidate_progress_sha256(self.prior_candidate_progress),
            self.prior_delta_provider_spend_microusd,
            self.remaining_authorized_max_cost_microusd,
            self.cumulative_worst_case_spend_microusd,
            self.original_capability_max_spend_microusd,
        ):
            raise ValueError("delta candidate approval progress differs")
        if self.candidate_position != len(self.prior_candidate_progress):
            raise ValueError("delta candidate progress is not an exact prefix")
        if self.candidate_position >= len(self.candidate_order):
            raise ValueError("delta candidate position is outside the order")
        if (
            self.manual_approval.candidate_id
            != self.candidate_order[self.candidate_position]
        ):
            raise ValueError("delta candidate approval is outside the order")
        if (
            self.live_authorization.stage
            is not TogetherPaidStage.CAPABILITY_PREFLIGHT
            or self.live_authorization.budget_segment
            is not BudgetSegment.QUALIFICATION
        ):
            raise ValueError("delta candidate authorization uses wrong stage")
        if (
            self.live_authorization.approved_at
            != self.manual_approval.approved_at
            or self.live_authorization.expires_at
            != self.manual_approval.expires_at
        ):
            raise ValueError("delta candidate authorization windows differ")
        return self


class TogetherDeltaCandidateReceipt(ContractModel):
    """Content-free receipt for one exact candidate rerun subset."""

    record_version: Literal[
        "phase4_delta_candidate_capability_receipt.v1"
    ] = "phase4_delta_candidate_capability_receipt.v1"
    receipt_id: StableId
    receipt_version: PositiveVersion
    delta_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    candidate_id: StableId
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    completed_at: datetime
    checks: list[TogetherCapabilityProbeCheck] = Field(min_length=1)
    provider_spend_microusd: Microusd

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("delta candidate receipt time needs timezone")
        return value

    @model_validator(mode="after")
    def require_unique_candidate_checks(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.checks):
            raise ValueError("delta candidate receipt mixes candidates")
        coordinates = [(item.candidate_id, item.role) for item in self.checks]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("delta candidate receipt duplicates a role")
        return self


class TogetherDeltaCandidateExecutionState(ContractModel):
    """Private progressive state for one candidate's delta attempt."""

    schema_version: Literal[
        "preference_eval_phase4_delta_candidate_state.v1"
    ] = "preference_eval_phase4_delta_candidate_state.v1"
    state_id: StableId
    state_version: PositiveVersion
    delta_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    outputs: list[TogetherCapabilityOutputRecord]
    manual_spend_ceiling_breached: bool
    manual_spend_overrun_microusd: Microusd
    provider_budget_limit_breached: bool
    receipt: TogetherDeltaCandidateReceipt | None = None

    @model_validator(mode="after")
    def require_unique_outputs(self) -> Self:
        call_ids = [item.call_id for item in self.outputs]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("delta candidate outputs must be unique")
        return self


DeltaPriorAttempt = tuple[
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
]


def _delta_candidate_order(delta: TogetherCapabilityDeltaPlan) -> list[str]:
    order: list[str] = []
    for call in delta.rerun_calls:
        if call.candidate_id not in order:
            order.append(call.candidate_id)
    return order


def _provider_spend(state: TogetherCandidateCapabilityExecutionState) -> int:
    return sum(item.billed_cost_microusd for item in state.provider_ledger.calls)


def _terminal_parts(state: TogetherCandidateCapabilityExecutionState):
    if state.receipt is not None or not state.provider_journal.finalizations:
        raise ValueError("capability source must be one terminal failed state")
    finalization = state.provider_journal.finalizations[-1]
    bindings = {
        item.call_id: item for item in state.provider_journal.request_bindings
    }
    return finalization, bindings[finalization.call_id]


def _validate_source_attempt(
    policy: TogetherCapabilityAdjudicationPolicy,
    continuation: TogetherCapabilityContinuationPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    authorization: SourceAuthorization,
    state: TogetherCandidateCapabilityExecutionState,
    diagnostic: ProviderStructuredOutputDiagnostic | None,
) -> CapabilitySourceAttempt:
    if isinstance(
        authorization,
        TogetherAdjudicatedCandidateCapabilityAuthorization,
    ):
        validate_adjudicated_candidate_authorization(authorization, policy)
        candidate_id = authorization.candidate_id
        inner = authorization.candidate_authorization
        authorization_sha256 = content_sha256(authorization)
    else:
        candidate_id = authorization.manual_approval.candidate_id
        if candidate_id != policy.provisional_candidate_id:
            raise ValueError("direct source authorization is not provisional")
        inner = authorization
        authorization_sha256 = content_sha256(authorization)
    validate_candidate_capability_execution_state(
        state,
        continuation,
        candidate_plan_for(continuation, candidate_id),
        inner,
        suite,
        profile,
        authorization_binding_sha256=authorization_sha256,
    )
    finalization, binding = _terminal_parts(state)
    if binding.model_candidate_id != candidate_id:
        raise ValueError("capability source candidate differs")
    if (
        finalization.outcome is not ProviderCallOutcome.INVALID_OUTPUT
        or finalization.failure_code != "structured_output_invalid"
    ):
        raise ValueError("capability source is not schema-invalid")
    if diagnostic is not None and (
        diagnostic.call_id,
        diagnostic.role,
        diagnostic.response_schema_sha256,
        diagnostic.finalization_sha256,
    ) != (
        binding.call_id,
        binding.role,
        binding.response_schema_sha256,
        content_sha256(finalization),
    ):
        raise ValueError("capability source diagnostic bindings differ")
    return CapabilitySourceAttempt(
        candidate_id=candidate_id,
        authorization_sha256=authorization_sha256,
        state_sha256=content_sha256(state),
        diagnostic_sha256=(
            content_sha256(diagnostic) if diagnostic is not None else None
        ),
        provider_call_count=len(state.provider_ledger.calls),
        provider_spend_microusd=_provider_spend(state),
        terminal_at=finalization.created_at,
        terminal_role=binding.role,
        terminal_outcome=finalization.outcome,
        terminal_failure_code=finalization.failure_code,
        response_schema_sha256=binding.response_schema_sha256,
        validation_error_count=(
            len(diagnostic.issues) if diagnostic is not None else 0
        ),
    )


def _carried_successes(
    source_plan: TogetherCapabilityPlan,
    source_suite: Phase4TogetherSuite,
    source_readiness: Phase4TogetherReadinessBundle,
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    corrected_readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    states: Sequence[TogetherCandidateCapabilityExecutionState],
) -> list[CarriedForwardCapabilitySuccess]:
    source_calls = {
        (item.candidate_id, item.role): item for item in source_plan.calls
    }
    corrected_calls = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    corrected_entries = {
        item.coordinate.call_id: item
        for item in corrected_readiness.qualification_manifest.entries
    }
    source_entries = {
        item.coordinate.call_id: item
        for item in source_readiness.qualification_manifest.entries
    }
    carried: list[CarriedForwardCapabilitySuccess] = []
    for state in states:
        bindings = {
            item.call_id: item
            for item in state.provider_journal.request_bindings
        }
        finalizations = {
            item.call_id: item
            for item in state.provider_journal.finalizations
        }
        for output in state.outputs:
            if output.role not in _CARRY_FORWARD_ROLES:
                continue
            coordinate = (output.candidate_id, output.role)
            source_call = source_calls[coordinate]
            corrected_call = corrected_calls[coordinate]
            source_shape = source_call.model_dump(
                exclude={
                    "qualification_entry_sha256",
                    "request_template_sha256",
                }
            )
            corrected_shape = corrected_call.model_dump(
                exclude={
                    "qualification_entry_sha256",
                    "request_template_sha256",
                }
            )
            if source_shape != corrected_shape:
                continue
            finalization = finalizations[output.call_id]
            if finalization.outcome is not ProviderCallOutcome.SUCCESS:
                continue
            source_rebuilt = rebuild_qualification_call(
                source_suite,
                profile,
                fixture,
                session,
                semantic_map,
                source_entries[source_call.call_id],
                created_at=bindings[output.call_id].created_at,
            )
            corrected_rebuilt = rebuild_qualification_call(
                corrected_suite,
                profile,
                fixture,
                session,
                semantic_map,
                corrected_entries[corrected_call.call_id],
                created_at=bindings[output.call_id].created_at,
            )
            if source_rebuilt.request.binding != bindings[output.call_id]:
                continue
            source_transmitted = (
                source_rebuilt.request.privacy_attestation
                .transmitted_payload_sha256
            )
            corrected_transmitted = (
                corrected_rebuilt.request.privacy_attestation
                .transmitted_payload_sha256
            )
            if (
                source_transmitted != corrected_transmitted
                or source_rebuilt.request.response_validator is not None
                or corrected_rebuilt.request.response_validator is None
            ):
                continue
            revalidated = corrected_rebuilt.response_adapter.dump_python(
                corrected_rebuilt.response_adapter.validate_python(
                    output.output_payload
                ),
                mode="json",
            )
            corrected_output_sha256 = content_sha256(revalidated)
            if corrected_output_sha256 != output.output_sha256:
                continue
            carried.append(
                CarriedForwardCapabilitySuccess(
                    candidate_id=output.candidate_id,
                    role=output.role,
                    source_state_sha256=content_sha256(state),
                    source_call_plan_sha256=content_sha256(source_call),
                    corrected_call_plan_sha256=content_sha256(corrected_call),
                    source_request_binding_sha256=content_sha256(
                        bindings[output.call_id]
                    ),
                    corrected_request_binding_sha256=content_sha256(
                        corrected_rebuilt.request.binding
                    ),
                    source_transmitted_payload_sha256=source_transmitted,
                    corrected_transmitted_payload_sha256=(
                        corrected_transmitted
                    ),
                    finalization_sha256=content_sha256(finalization),
                    source_output_sha256=output.output_sha256,
                    corrected_revalidated_output_sha256=(
                        corrected_output_sha256
                    ),
                )
            )
    return sorted(carried, key=lambda item: (item.candidate_id, item.role.value))


def build_capability_delta_plan(
    source_policy: TogetherCapabilityAdjudicationPolicy,
    source_continuation: TogetherCapabilityContinuationPlan,
    source_plan: TogetherCapabilityPlan,
    source_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    source_attempt_inputs: Sequence[SourceAttemptInput],
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    source_readiness: Phase4TogetherReadinessBundle,
    response_semantics_manifest: ProviderResponseInvariantManifest,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    plan_id: str,
    plan_version: int,
    created_at: datetime,
) -> TogetherCapabilityDeltaPlan:
    direct_inputs = [
        item
        for item in source_attempt_inputs
        if isinstance(item[0], TogetherCandidateCapabilityAuthorizationBundle)
    ]
    if len(direct_inputs) != 1:
        raise ValueError("capability delta needs one provisional source")
    provisional_authorization, provisional_state, _ = direct_inputs[0]
    validate_capability_adjudication_policy(
        source_policy,
        source_continuation,
        source_plan,
        source_suite,
        profile,
        provisional_authorization,
        provisional_state,
    )
    if (
        source_policy.corrected_capability_plan_sha256
        != content_sha256(source_plan)
    ):
        raise ValueError("capability delta source plan differs")
    if source_suite.suite_version >= corrected_suite.suite_version:
        raise ValueError("capability delta suite correction is not newer")
    if (
        source_suite.robustness_profile_sha256,
        source_suite.catalog,
        source_suite.provider_terms,
        source_suite.candidates,
        source_suite.workload,
    ) != (
        corrected_suite.robustness_profile_sha256,
        corrected_suite.catalog,
        corrected_suite.provider_terms,
        corrected_suite.candidates,
        corrected_suite.workload,
    ):
        raise ValueError("capability delta changed non-contract suite inputs")
    validate_capability_plan(
        source_plan,
        source_suite,
        profile,
        source_readiness,
        fixture,
        session,
        semantic_map,
    )
    validate_capability_plan(
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
    )
    if response_semantics_manifest != PROVIDER_RESPONSE_INVARIANT_MANIFEST:
        raise ValueError("provider response semantics manifest differs")
    attempts = sorted(
        (
            _validate_source_attempt(
                source_policy,
                source_continuation,
                source_suite,
                profile,
                authorization,
                state,
                diagnostic,
            )
            for authorization, state, diagnostic in source_attempt_inputs
        ),
        key=lambda item: item.candidate_id,
    )
    expected_candidate_ids = sorted(source_policy.all_candidate_ids)
    if [item.candidate_id for item in attempts] != expected_candidate_ids:
        raise ValueError("capability delta must bind every candidate attempt")
    states = [item[1] for item in source_attempt_inputs]
    carried = _carried_successes(
        source_plan,
        source_suite,
        source_readiness,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
        states,
    )
    carried_coordinates = {
        (item.candidate_id, item.role) for item in carried
    }
    rerun_calls = [
        item.model_copy(deep=True)
        for item in corrected_plan.calls
        if (item.candidate_id, item.role) not in carried_coordinates
    ]
    preceding_spend = source_continuation.prior_provider_spend_microusd
    prior_spend = preceding_spend + sum(
        item.provider_spend_microusd for item in attempts
    )
    additional_projected = sum(
        item.projected_cost_microusd for item in rerun_calls
    )
    additional_authorized = sum(
        item.authorized_max_cost_microusd for item in rerun_calls
    )
    return TogetherCapabilityDeltaPlan(
        plan_id=plan_id,
        plan_version=plan_version,
        created_at=created_at,
        source_adjudication_policy_sha256=content_sha256(source_policy),
        source_continuation_sha256=content_sha256(source_continuation),
        source_suite_sha256=content_sha256(source_suite),
        source_readiness_sha256=content_sha256(source_readiness),
        source_capability_plan_sha256=content_sha256(source_plan),
        corrected_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        provider_response_semantics_manifest_sha256=(
            provider_response_invariant_manifest_sha256()
        ),
        source_attempts=attempts,
        carried_forward_successes=carried,
        rerun_calls=rerun_calls,
        preceding_provider_spend_microusd=preceding_spend,
        prior_provider_spend_microusd=prior_spend,
        additional_projected_cost_microusd=additional_projected,
        additional_authorized_max_cost_microusd=additional_authorized,
        cumulative_worst_case_spend_microusd=(
            prior_spend + additional_authorized
        ),
    )


def validate_capability_delta_plan(
    delta: TogetherCapabilityDeltaPlan,
    source_policy: TogetherCapabilityAdjudicationPolicy,
    source_continuation: TogetherCapabilityContinuationPlan,
    source_plan: TogetherCapabilityPlan,
    source_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    source_attempt_inputs: Sequence[SourceAttemptInput],
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    source_readiness: Phase4TogetherReadinessBundle,
    response_semantics_manifest: ProviderResponseInvariantManifest,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    rebuilt = build_capability_delta_plan(
        source_policy,
        source_continuation,
        source_plan,
        source_suite,
        profile,
        source_attempt_inputs,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        source_readiness,
        response_semantics_manifest,
        fixture,
        session,
        semantic_map,
        plan_id=delta.plan_id,
        plan_version=delta.plan_version,
        created_at=delta.created_at,
    )
    if delta != rebuilt:
        raise ValueError("capability delta plan does not rebuild")


def _contract_records_sha256(records: Sequence[ContractModel]) -> str:
    return content_sha256(
        [item.model_dump(mode="json") for item in records]
    )


def validate_capability_delta_source_proof(
    proof: TogetherCapabilityDeltaSourceProof,
    delta: TogetherCapabilityDeltaPlan,
) -> None:
    """Recompute every content-free source-proof binding from the delta."""

    if proof.validated_at < delta.created_at:
        raise ValueError("capability delta source proof predates the delta")
    actual = (
        proof.delta_plan_sha256,
        proof.source_adjudication_policy_sha256,
        proof.source_continuation_sha256,
        proof.source_capability_plan_sha256,
        proof.source_suite_sha256,
        proof.source_readiness_sha256,
        proof.source_attempts_sha256,
        proof.carried_forward_successes_sha256,
        proof.rerun_calls_sha256,
        proof.provider_response_semantics_manifest_sha256,
    )
    expected = (
        content_sha256(delta),
        delta.source_adjudication_policy_sha256,
        delta.source_continuation_sha256,
        delta.source_capability_plan_sha256,
        delta.source_suite_sha256,
        delta.source_readiness_sha256,
        _contract_records_sha256(delta.source_attempts),
        _contract_records_sha256(delta.carried_forward_successes),
        _contract_records_sha256(delta.rerun_calls),
        delta.provider_response_semantics_manifest_sha256,
    )
    if actual != expected:
        raise ValueError("capability delta source proof bindings differ")


def build_capability_delta_source_proof(
    delta: TogetherCapabilityDeltaPlan,
    source_policy: TogetherCapabilityAdjudicationPolicy,
    source_continuation: TogetherCapabilityContinuationPlan,
    source_plan: TogetherCapabilityPlan,
    source_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    source_attempt_inputs: Sequence[SourceAttemptInput],
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    source_readiness: Phase4TogetherReadinessBundle,
    response_semantics_manifest: ProviderResponseInvariantManifest,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    proof_id: str,
    proof_version: int,
    validated_at: datetime,
) -> TogetherCapabilityDeltaSourceProof:
    """Validate exact ignored sources, then emit their content-free receipt."""

    validate_capability_delta_plan(
        delta,
        source_policy,
        source_continuation,
        source_plan,
        source_suite,
        profile,
        source_attempt_inputs,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        source_readiness,
        response_semantics_manifest,
        fixture,
        session,
        semantic_map,
    )
    proof = TogetherCapabilityDeltaSourceProof(
        proof_id=proof_id,
        proof_version=proof_version,
        validated_at=validated_at,
        delta_plan_sha256=content_sha256(delta),
        source_adjudication_policy_sha256=(
            delta.source_adjudication_policy_sha256
        ),
        source_continuation_sha256=delta.source_continuation_sha256,
        source_capability_plan_sha256=delta.source_capability_plan_sha256,
        source_suite_sha256=delta.source_suite_sha256,
        source_readiness_sha256=delta.source_readiness_sha256,
        source_attempts_sha256=_contract_records_sha256(
            delta.source_attempts
        ),
        carried_forward_successes_sha256=_contract_records_sha256(
            delta.carried_forward_successes
        ),
        rerun_calls_sha256=_contract_records_sha256(delta.rerun_calls),
        provider_response_semantics_manifest_sha256=(
            delta.provider_response_semantics_manifest_sha256
        ),
    )
    validate_capability_delta_source_proof(proof, delta)
    return proof


def rerun_calls_for_candidate(
    delta: TogetherCapabilityDeltaPlan,
    candidate_id: str,
) -> list[TogetherCapabilityCallPlan]:
    calls = [
        item.model_copy(deep=True)
        for item in delta.rerun_calls
        if item.candidate_id == candidate_id
    ]
    if not calls:
        raise ValueError("candidate is not eligible for capability delta")
    return calls


def validate_capability_delta_execution_inputs(
    delta: TogetherCapabilityDeltaPlan,
    source_proof: TogetherCapabilityDeltaSourceProof,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    """Validate the public artifacts needed to execute the reviewed delta."""

    validate_capability_delta_source_proof(source_proof, delta)
    expected = (
        content_sha256(corrected_plan),
        content_sha256(suite),
        content_sha256(readiness),
        provider_response_invariant_manifest_sha256(),
    )
    actual = (
        delta.corrected_capability_plan_sha256,
        delta.corrected_suite_sha256,
        delta.corrected_readiness_sha256,
        delta.provider_response_semantics_manifest_sha256,
    )
    if actual != expected:
        raise ValueError("capability delta execution bindings differ")
    validate_capability_plan(
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    corrected_by_coordinate = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    for call in delta.rerun_calls:
        if corrected_by_coordinate.get((call.candidate_id, call.role)) != call:
            raise ValueError("capability delta rerun call differs from plan")


def delta_candidate_plan_for(
    delta: TogetherCapabilityDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    candidate_id: str,
) -> TogetherDeltaCandidatePlan:
    if (
        delta.corrected_capability_plan_sha256,
        delta.corrected_suite_sha256,
        delta.corrected_readiness_sha256,
        delta.provider_response_semantics_manifest_sha256,
    ) != (
        content_sha256(corrected_plan),
        content_sha256(suite),
        content_sha256(readiness),
        provider_response_invariant_manifest_sha256(),
    ):
        raise ValueError("delta candidate plan inputs differ from delta")
    calls = rerun_calls_for_candidate(delta, candidate_id)
    corrected_by_coordinate = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    if any(
        corrected_by_coordinate.get((item.candidate_id, item.role)) != item
        for item in calls
    ):
        raise ValueError("delta candidate calls differ from corrected plan")
    authorized = sum(item.authorized_max_cost_microusd for item in calls)
    return TogetherDeltaCandidatePlan(
        plan_id=f"{delta.plan_id}_{candidate_id}",
        plan_version=delta.plan_version,
        created_at=delta.created_at,
        delta_plan_sha256=content_sha256(delta),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        readiness_bundle_sha256=content_sha256(readiness),
        qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        provider_response_semantics_manifest_sha256=(
            provider_response_invariant_manifest_sha256()
        ),
        candidate_id=candidate_id,
        calls=calls,
        projected_cost_microusd=sum(
            item.projected_cost_microusd for item in calls
        ),
        all_calls_authorized_max_cost_microusd=authorized,
        candidate_capability_max_spend_microusd=authorized,
    )


def validate_delta_candidate_plan(
    candidate_plan: TogetherDeltaCandidatePlan,
    delta: TogetherCapabilityDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
) -> None:
    rebuilt = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        candidate_plan.candidate_id,
    )
    if candidate_plan != rebuilt:
        raise ValueError("delta candidate plan does not rebuild")


def _validated_prior_candidate_progress(
    delta: TogetherCapabilityDeltaPlan,
    source_proof: TogetherCapabilityDeltaSourceProof,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    prior_attempts: Sequence[DeltaPriorAttempt],
) -> tuple[list[str], list[TogetherDeltaCandidateProgressRecord]]:
    candidate_order = _delta_candidate_order(delta)
    if len(prior_attempts) >= len(candidate_order):
        raise ValueError("delta candidate progress already covers every candidate")
    progress: list[TogetherDeltaCandidateProgressRecord] = []
    for position, (authorization, state) in enumerate(prior_attempts):
        candidate_id = candidate_order[position]
        prior_plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            candidate_id,
        )
        validate_delta_candidate_authorization_bundle(
            authorization,
            delta,
            source_proof,
            prior_plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog_bundle,
            prior_attempts=prior_attempts[:position],
            now=authorization.manual_approval.approved_at,
        )
        validate_delta_candidate_execution_state(
            state,
            delta,
            prior_plan,
            authorization,
            suite,
            profile,
        )
        if (
            state.manual_spend_ceiling_breached
            or state.provider_budget_limit_breached
        ):
            raise ValueError(
                "prior delta candidate spend breach blocks further authorization"
            )
        authorization_ids = [
            item.call_id for item in state.provider_ledger.authorizations
        ]
        finalization_ids = [
            item.call_id for item in state.provider_journal.finalizations
        ]
        call_ids = [item.call_id for item in state.provider_ledger.calls]
        if not call_ids or not (
            authorization_ids == call_ids == finalization_ids
        ):
            raise ValueError("prior delta candidate attempt is not terminal")
        last_index = len(finalization_ids) - 1
        if state.receipt is None and _delta_call_passed(
            prior_plan.calls[last_index],
            state.provider_journal.finalizations[-1],
        ):
            raise ValueError("prior delta candidate attempt is only a prefix")
        progress.append(
            TogetherDeltaCandidateProgressRecord(
                candidate_position=position,
                candidate_id=candidate_id,
                candidate_plan_sha256=content_sha256(prior_plan),
                authorization_bundle_sha256=content_sha256(authorization),
                terminal_state_sha256=content_sha256(state),
                provider_spend_microusd=sum(
                    item.billed_cost_microusd
                    for item in state.provider_ledger.calls
                ),
                candidate_approved=state.receipt is not None,
                manual_spend_ceiling_breached=(
                    state.manual_spend_ceiling_breached
                ),
                provider_budget_limit_breached=(
                    state.provider_budget_limit_breached
                ),
            )
        )
    return candidate_order, progress


def _remaining_delta_authorized_max(
    delta: TogetherCapabilityDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    candidate_order: Sequence[str],
    candidate_position: int,
) -> int:
    return sum(
        delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            candidate_id,
        ).candidate_capability_max_spend_microusd
        for candidate_id in candidate_order[candidate_position:]
    )


def build_delta_candidate_authorization_bundle(
    delta: TogetherCapabilityDeltaPlan,
    source_proof: TogetherCapabilityDeltaSourceProof,
    candidate_plan: TogetherDeltaCandidatePlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    prior_attempts: Sequence[DeltaPriorAttempt] = (),
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TogetherDeltaCandidateAuthorizationBundle:
    validate_capability_delta_source_proof(source_proof, delta)
    validate_delta_candidate_plan(
        candidate_plan,
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
    )
    candidate_order, prior_progress = _validated_prior_candidate_progress(
        delta,
        source_proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        prior_attempts,
    )
    candidate_position = len(prior_progress)
    if candidate_plan.candidate_id != candidate_order[candidate_position]:
        raise ValueError("delta candidate authorization is outside exact order")
    prior_delta_spend = sum(
        item.provider_spend_microusd for item in prior_progress
    )
    remaining_authorized = _remaining_delta_authorized_max(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        candidate_order,
        candidate_position,
    )
    cumulative_worst_case = (
        delta.prior_provider_spend_microusd
        + prior_delta_spend
        + remaining_authorized
    )
    if cumulative_worst_case > delta.original_capability_max_spend_microusd:
        raise ValueError("delta candidate progress exceeds original spend ceiling")
    roles = sorted(
        (item.role for item in candidate_plan.calls),
        key=lambda item: item.value,
    )
    manual = TogetherDeltaCandidateManualApproval(
        approval_id=approval_id,
        approval_version=1,
        delta_plan_sha256=content_sha256(delta),
        source_proof_sha256=content_sha256(source_proof),
        candidate_plan_sha256=content_sha256(candidate_plan),
        candidate_id=candidate_plan.candidate_id,
        candidate_order_sha256=content_sha256(candidate_order),
        candidate_position=candidate_position,
        prior_candidate_progress_sha256=_delta_candidate_progress_sha256(
            prior_progress
        ),
        prior_delta_provider_spend_microusd=prior_delta_spend,
        remaining_authorized_max_cost_microusd=remaining_authorized,
        cumulative_worst_case_spend_microusd=cumulative_worst_case,
        approved_roles=roles,
        approved_call_count=len(candidate_plan.calls),
        approved_max_spend_microusd=(
            candidate_plan.candidate_capability_max_spend_microusd
        ),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    live = TogetherLiveAuthorization(
        authorization_id=f"{approval_id}_live",
        authorization_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        account_privacy_attestation_sha256=content_sha256(
            catalog_bundle.account_privacy_attestation
        ),
        catalog_preflight_receipt_sha256=content_sha256(
            catalog_bundle.receipt
        ),
        token_readiness_receipt_sha256=content_sha256(
            readiness.token_readiness_receipt
        ),
        headroom_policy_sha256=content_sha256(readiness.headroom_policy),
        stage=TogetherPaidStage.CAPABILITY_PREFLIGHT,
        budget_segment=BudgetSegment.QUALIFICATION,
        authorized_candidate_ids=[candidate_plan.candidate_id],
        authorized_roles=sorted(LLMRole, key=lambda item: item.value),
        approved_max_spend_microusd=(
            profile.budget_policy.segment_caps_microusd[
                BudgetSegment.QUALIFICATION
            ]
        ),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    bundle = TogetherDeltaCandidateAuthorizationBundle(
        bundle_id=bundle_id,
        bundle_version=1,
        delta_plan_sha256=content_sha256(delta),
        source_proof_sha256=content_sha256(source_proof),
        candidate_plan_sha256=content_sha256(candidate_plan),
        catalog_preflight_bundle_sha256=content_sha256(catalog_bundle),
        candidate_order=candidate_order,
        candidate_position=candidate_position,
        prior_candidate_progress=prior_progress,
        prior_delta_provider_spend_microusd=prior_delta_spend,
        remaining_authorized_max_cost_microusd=remaining_authorized,
        cumulative_worst_case_spend_microusd=cumulative_worst_case,
        manual_approval=manual,
        live_authorization=live,
    )
    validate_delta_candidate_authorization_bundle(
        bundle,
        delta,
        source_proof,
        candidate_plan,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        prior_attempts=prior_attempts,
        now=approved_at,
    )
    return bundle


def validate_delta_candidate_authorization_bundle(
    bundle: TogetherDeltaCandidateAuthorizationBundle,
    delta: TogetherCapabilityDeltaPlan,
    source_proof: TogetherCapabilityDeltaSourceProof,
    candidate_plan: TogetherDeltaCandidatePlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    prior_attempts: Sequence[DeltaPriorAttempt] = (),
    now: datetime,
) -> None:
    validate_capability_delta_source_proof(source_proof, delta)
    validate_delta_candidate_plan(
        candidate_plan,
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
    )
    candidate_order, prior_progress = _validated_prior_candidate_progress(
        delta,
        source_proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        prior_attempts,
    )
    candidate_position = len(prior_progress)
    if candidate_plan.candidate_id != candidate_order[candidate_position]:
        raise ValueError("delta candidate authorization is outside exact order")
    prior_delta_spend = sum(
        item.provider_spend_microusd for item in prior_progress
    )
    remaining_authorized = _remaining_delta_authorized_max(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        candidate_order,
        candidate_position,
    )
    cumulative_worst_case = (
        delta.prior_provider_spend_microusd
        + prior_delta_spend
        + remaining_authorized
    )
    if cumulative_worst_case > delta.original_capability_max_spend_microusd:
        raise ValueError("delta candidate progress exceeds original spend ceiling")
    if (
        bundle.delta_plan_sha256,
        bundle.source_proof_sha256,
        bundle.candidate_plan_sha256,
        bundle.catalog_preflight_bundle_sha256,
    ) != (
        content_sha256(delta),
        content_sha256(source_proof),
        content_sha256(candidate_plan),
        content_sha256(catalog_bundle),
    ):
        raise ValueError("delta candidate authorization hashes differ")
    if (
        bundle.candidate_order,
        bundle.candidate_position,
        bundle.prior_candidate_progress,
        bundle.prior_delta_provider_spend_microusd,
        bundle.remaining_authorized_max_cost_microusd,
        bundle.cumulative_worst_case_spend_microusd,
        bundle.original_capability_max_spend_microusd,
    ) != (
        candidate_order,
        candidate_position,
        prior_progress,
        prior_delta_spend,
        remaining_authorized,
        cumulative_worst_case,
        delta.original_capability_max_spend_microusd,
    ):
        raise ValueError("delta candidate authorization progress differs")
    roles = sorted(
        (item.role for item in candidate_plan.calls),
        key=lambda item: item.value,
    )
    approval = bundle.manual_approval
    if (
        approval.candidate_id,
        approval.approved_roles,
        approval.approved_call_count,
        approval.approved_max_spend_microusd,
    ) != (
        candidate_plan.candidate_id,
        roles,
        len(candidate_plan.calls),
        candidate_plan.candidate_capability_max_spend_microusd,
    ):
        raise ValueError("delta candidate manual approval differs from plan")
    if not approval.approved_at <= now <= approval.expires_at:
        raise ValueError("delta candidate manual approval is not active")
    validate_live_authorization(
        suite,
        profile,
        catalog_bundle,
        readiness.token_readiness_receipt,
        readiness.headroom_policy,
        bundle.live_authorization,
        capability_receipt=None,
        now=now,
    )
    if bundle.live_authorization.authorized_candidate_ids != [
        candidate_plan.candidate_id
    ]:
        raise ValueError("delta candidate live authorization is not isolated")


def _delta_candidate_parts(
    suite: Phase4TogetherSuite,
) -> tuple[list[OpenWeightModelCandidate], list[ProviderPriceCard]]:
    return (
        [item.candidate for item in suite.candidates],
        [item.price_card for item in suite.candidates],
    )


def _delta_call_passed(
    call: TogetherCapabilityCallPlan,
    finalization: ProviderCallFinalization,
) -> bool:
    if finalization.outcome is not ProviderCallOutcome.SUCCESS:
        return False
    if not call.actual_tool_call_required:
        return True
    return (
        finalization.tool_call_count > 0
        and finalization.tool_call_failure_count == 0
    )


def _build_delta_candidate_receipt(
    delta: TogetherCapabilityDeltaPlan,
    plan: TogetherDeltaCandidatePlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    outputs: list[TogetherCapabilityOutputRecord],
    *,
    receipt_id: str,
    completed_at: datetime,
) -> TogetherDeltaCandidateReceipt:
    candidates, price_cards = _delta_candidate_parts(suite)
    validate_provider_execution_journal(
        journal,
        ledger,
        profile,
        candidates,
        price_cards,
        require_complete=True,
    )
    bindings = {item.call_id: item for item in journal.request_bindings}
    finalizations = {item.call_id: item for item in journal.finalizations}
    outputs_by_id = {item.call_id: item for item in outputs}
    planned_ids = [item.call_id for item in plan.calls]
    if not (
        set(bindings)
        == set(finalizations)
        == set(outputs_by_id)
        == set(planned_ids)
    ):
        raise ValueError("delta candidate audit must cover exact plan")
    if completed_at < max(item.created_at for item in finalizations.values()):
        raise ValueError("delta candidate receipt predates provider completion")
    checks: list[TogetherCapabilityProbeCheck] = []
    for call in plan.calls:
        binding = bindings[call.call_id]
        finalization = finalizations[call.call_id]
        output = outputs_by_id[call.call_id]
        if (
            binding.model_candidate_id,
            binding.role,
            content_sha256(binding),
        ) != (
            call.candidate_id,
            call.role,
            finalization.request_binding_sha256,
        ) or (output.candidate_id, output.role) != (
            call.candidate_id,
            call.role,
        ):
            raise ValueError("delta candidate finalization binding differs")
        if not _delta_call_passed(call, finalization) or (
            finalization.response_sha256 != output.output_sha256
        ):
            raise ValueError("delta candidate probe did not succeed")
        checks.append(
            TogetherCapabilityProbeCheck(
                candidate_id=call.candidate_id,
                role=call.role,
                call_id=call.call_id,
                finalization_sha256=content_sha256(finalization),
                interviewer_tool_calling_passed=(
                    True if call.actual_tool_call_required else None
                ),
            )
        )
    spend = sum(item.billed_cost_microusd for item in ledger.calls)
    if spend > plan.candidate_capability_max_spend_microusd:
        raise ValueError("delta candidate spend exceeds manual ceiling")
    return TogetherDeltaCandidateReceipt(
        receipt_id=receipt_id,
        receipt_version=1,
        delta_plan_sha256=content_sha256(delta),
        candidate_plan_sha256=content_sha256(plan),
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        candidate_id=plan.candidate_id,
        provider_ledger_sha256=content_sha256(ledger),
        provider_journal_sha256=content_sha256(journal),
        completed_at=completed_at,
        checks=checks,
        provider_spend_microusd=spend,
    )


def validate_delta_candidate_execution_state(
    state: TogetherDeltaCandidateExecutionState,
    delta: TogetherCapabilityDeltaPlan,
    plan: TogetherDeltaCandidatePlan,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    if (
        state.delta_plan_sha256,
        state.candidate_plan_sha256,
        state.authorization_bundle_sha256,
    ) != (
        content_sha256(delta),
        content_sha256(plan),
        content_sha256(authorization),
    ):
        raise ValueError("delta candidate state bindings differ")
    candidates, price_cards = _delta_candidate_parts(suite)
    provider_limit_breached = provider_budget_limits_exceeded(
        state.provider_ledger,
        profile,
    )
    if state.provider_budget_limit_breached != provider_limit_breached:
        raise ValueError("delta candidate provider budget breach differs")
    if provider_limit_breached:
        validate_terminal_provider_budget_breach_journal(
            state.provider_journal,
            state.provider_ledger,
            profile,
            candidates,
            price_cards,
        )
    else:
        validate_provider_execution_journal(
            state.provider_journal,
            state.provider_ledger,
            profile,
            candidates,
            price_cards,
            require_complete=False,
        )
    planned_ids = [item.call_id for item in plan.calls]
    authorization_ids = [
        item.call_id for item in state.provider_ledger.authorizations
    ]
    if authorization_ids != planned_ids[: len(authorization_ids)]:
        raise ValueError("delta candidate state is not an exact plan prefix")
    finalization_ids = [
        item.call_id for item in state.provider_journal.finalizations
    ]
    if finalization_ids != authorization_ids[: len(finalization_ids)]:
        raise ValueError("delta candidate finalizations are not a prefix")
    if len(authorization_ids) - len(finalization_ids) > 1:
        raise ValueError("delta candidate may retain one outstanding call")
    if any(
        not _delta_call_passed(plan.calls[index], finalization)
        for index, finalization in enumerate(
            state.provider_journal.finalizations[:-1]
        )
    ):
        raise ValueError("delta candidate failure must terminate its attempt")
    successful_ids = {
        item.call_id
        for item in state.provider_journal.finalizations
        if item.outcome is ProviderCallOutcome.SUCCESS
    }
    expected_outputs = [
        (item.call_id, item.candidate_id, item.role)
        for item in plan.calls
        if item.call_id in successful_ids
    ]
    actual_outputs = [
        (item.call_id, item.candidate_id, item.role) for item in state.outputs
    ]
    if actual_outputs != expected_outputs:
        raise ValueError("delta candidate outputs must cover successful calls")
    finalizations = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    for output in state.outputs:
        if finalizations[output.call_id].response_sha256 != output.output_sha256:
            raise ValueError("delta candidate output differs from audit")
    provider_spend = sum(
        item.billed_cost_microusd for item in state.provider_ledger.calls
    )
    manual_overrun = max(
        0,
        provider_spend - plan.candidate_capability_max_spend_microusd,
    )
    if (
        state.manual_spend_ceiling_breached,
        state.manual_spend_overrun_microusd,
    ) != (manual_overrun > 0, manual_overrun):
        raise ValueError("delta candidate manual spend breach differs")
    if manual_overrun or provider_limit_breached:
        if (
            state.receipt is not None
            or not finalization_ids
            or authorization_ids != finalization_ids
            or _delta_call_passed(
                plan.calls[len(finalization_ids) - 1],
                state.provider_journal.finalizations[-1],
            )
        ):
            raise ValueError("delta candidate spend breach must be terminal")
    if state.receipt is not None:
        rebuilt = _build_delta_candidate_receipt(
            delta,
            plan,
            suite,
            profile,
            state.provider_ledger,
            state.provider_journal,
            state.outputs,
            receipt_id=state.receipt.receipt_id,
            completed_at=state.receipt.completed_at,
        )
        if state.receipt != rebuilt:
            raise ValueError("delta candidate receipt does not rebuild")


def _delta_execution_state(
    *,
    state_id: str,
    delta: TogetherCapabilityDeltaPlan,
    plan: TogetherDeltaCandidatePlan,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    runtime: ProviderBudgetRuntime,
    outputs: list[TogetherCapabilityOutputRecord],
    receipt: TogetherDeltaCandidateReceipt | None,
) -> TogetherDeltaCandidateExecutionState:
    ledger = runtime.ledger_snapshot()
    provider_spend = sum(
        item.billed_cost_microusd for item in ledger.calls
    )
    manual_overrun = max(
        0,
        provider_spend - plan.candidate_capability_max_spend_microusd,
    )
    return TogetherDeltaCandidateExecutionState(
        state_id=state_id,
        state_version=1,
        delta_plan_sha256=content_sha256(delta),
        candidate_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        provider_ledger=ledger,
        provider_journal=runtime.journal_snapshot(),
        outputs=outputs,
        manual_spend_ceiling_breached=manual_overrun > 0,
        manual_spend_overrun_microusd=manual_overrun,
        provider_budget_limit_breached=provider_budget_limits_exceeded(
            ledger,
            runtime.profile,
        ),
        receipt=receipt,
    )


def execute_delta_candidate_capability_preflight(
    delta: TogetherCapabilityDeltaPlan,
    source_proof: TogetherCapabilityDeltaSourceProof,
    corrected_plan: TogetherCapabilityPlan,
    plan: TogetherDeltaCandidatePlan,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    transport: ProviderTransport,
    *,
    state_id: str,
    ledger_id: str,
    journal_id: str,
    clock: Callable[[], datetime],
    prior_attempts: Sequence[DeltaPriorAttempt] = (),
    prior_state: TogetherDeltaCandidateExecutionState | None = None,
    checkpoint: (
        Callable[[TogetherDeltaCandidateExecutionState], None] | None
    ) = None,
    validation_diagnostic_sink: (
        Callable[[ProviderStructuredOutputDiagnostic], None] | None
    ) = None,
) -> TogetherDeltaCandidateExecutionState:
    """Execute one candidate's exact reviewed delta and stop at first failure."""

    validate_capability_delta_execution_inputs(
        delta,
        source_proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    validate_delta_candidate_plan(
        plan,
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
    )
    started_at = clock()
    validate_delta_candidate_authorization_bundle(
        authorization,
        delta,
        source_proof,
        plan,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        prior_attempts=prior_attempts,
        now=started_at,
    )
    entries_by_id: dict[str, QualificationCallPlanEntry] = {
        item.coordinate.call_id: item
        for item in readiness.qualification_manifest.entries
    }
    for call in plan.calls:
        entry = entries_by_id.get(call.call_id)
        if entry is None or content_sha256(entry) != call.qualification_entry_sha256:
            raise ValueError("delta candidate execution entry differs")
    if prior_state is None:
        runtime = ProviderBudgetRuntime(
            profile,
            ledger_id=ledger_id,
            journal_id=journal_id,
        )
        outputs: list[TogetherCapabilityOutputRecord] = []
    else:
        validate_delta_candidate_execution_state(
            prior_state,
            delta,
            plan,
            authorization,
            suite,
            profile,
        )
        if prior_state.receipt is not None:
            return prior_state.model_copy(deep=True)
        if prior_state.provider_journal.finalizations:
            last_index = len(prior_state.provider_journal.finalizations) - 1
            if not _delta_call_passed(
                plan.calls[last_index],
                prior_state.provider_journal.finalizations[-1],
            ):
                raise ValueError("failed delta candidate attempt is terminal")
        runtime = ProviderBudgetRuntime.resume(
            profile,
            prior_state.provider_ledger,
            prior_state.provider_journal,
            *_delta_candidate_parts(suite),
        )
        outputs = [item.model_copy(deep=True) for item in prior_state.outputs]
    ledger = runtime.ledger_snapshot()
    if len(ledger.authorizations) != len(ledger.calls):
        raise ValueError("delta candidate has an outstanding call")
    completed_count = len(ledger.calls)

    def checkpoint_progress() -> None:
        progressive = _delta_execution_state(
            state_id=state_id,
            delta=delta,
            plan=plan,
            authorization=authorization,
            runtime=runtime,
            outputs=outputs,
            receipt=None,
        )
        validate_delta_candidate_execution_state(
            progressive,
            delta,
            plan,
            authorization,
            suite,
            profile,
        )
        if checkpoint is not None:
            checkpoint(progressive)

    for call in plan.calls[completed_count:]:
        spent = sum(
            item.billed_cost_microusd
            for item in runtime.ledger_snapshot().calls
        )
        if (
            spent + call.authorized_max_cost_microusd
            > plan.candidate_capability_max_spend_microusd
        ):
            raise ValueError("next delta call exceeds manual spend ceiling")
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entries_by_id[call.call_id],
            created_at=clock(),
        )
        try:
            result = runtime.execute(
                rebuilt.request,
                rebuilt.price_card,
                (
                    None
                    if rebuilt.request.response_validator is not None
                    else rebuilt.response_adapter
                ),
                transport,
                segment=BudgetSegment.QUALIFICATION,
            )
        except Exception:
            checkpoint_progress()
            raise
        if result.output is not None:
            payload = rebuilt.response_adapter.dump_python(
                result.output,
                mode="json",
            )
            outputs.append(
                TogetherCapabilityOutputRecord(
                    call_id=call.call_id,
                    candidate_id=call.candidate_id,
                    role=call.role,
                    output_sha256=content_sha256(payload),
                    output_payload=payload,
                )
            )
        checkpoint_progress()
        if result.validation_diagnostic is not None:
            if validation_diagnostic_sink is None:
                raise ValueError(
                    "invalid delta output requires a diagnostic sink"
                )
            validation_diagnostic_sink(result.validation_diagnostic)
        if result.finalization.outcome is not ProviderCallOutcome.SUCCESS:
            raise ValueError("delta candidate provider call did not succeed")
        if not _delta_call_passed(call, result.finalization):
            raise ValueError("delta candidate interviewer did not call a tool")
    receipt = _build_delta_candidate_receipt(
        delta,
        plan,
        suite,
        profile,
        runtime.ledger_snapshot(),
        runtime.journal_snapshot(),
        outputs,
        receipt_id=f"{state_id}_receipt",
        completed_at=clock(),
    )
    complete = _delta_execution_state(
        state_id=state_id,
        delta=delta,
        plan=plan,
        authorization=authorization,
        runtime=runtime,
        outputs=outputs,
        receipt=receipt,
    )
    validate_delta_candidate_execution_state(
        complete,
        delta,
        plan,
        authorization,
        suite,
        profile,
    )
    if checkpoint is not None:
        checkpoint(complete)
    return complete


def delta_candidate_state_summary(
    state: TogetherDeltaCandidateExecutionState,
) -> dict[str, JsonValue]:
    finalizations = state.provider_journal.finalizations
    return {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "state_sha256": content_sha256(state),
        "provider_call_count": len(state.provider_ledger.calls),
        "completed_call_count": len(finalizations),
        "successful_call_count": sum(
            item.outcome is ProviderCallOutcome.SUCCESS
            for item in finalizations
        ),
        "failed_call_count": sum(
            item.outcome is not ProviderCallOutcome.SUCCESS
            for item in finalizations
        ),
        "provider_spend_microusd": sum(
            item.billed_cost_microusd for item in state.provider_ledger.calls
        ),
        "manual_spend_ceiling_breached": (
            state.manual_spend_ceiling_breached
        ),
        "manual_spend_overrun_microusd": state.manual_spend_overrun_microusd,
        "provider_budget_limit_breached": (
            state.provider_budget_limit_breached
        ),
        "delta_subset_approved": state.receipt is not None,
    }


def capability_delta_summary(
    delta: TogetherCapabilityDeltaPlan,
) -> dict[str, JsonValue]:
    return {
        "schema_version": delta.schema_version,
        "plan_id": delta.plan_id,
        "plan_version": delta.plan_version,
        "plan_sha256": content_sha256(delta),
        "source_attempt_count": len(delta.source_attempts),
        "carried_forward_success_count": len(
            delta.carried_forward_successes
        ),
        "rerun_candidate_count": len(
            {item.candidate_id for item in delta.rerun_calls}
        ),
        "rerun_call_count": len(delta.rerun_calls),
        "prior_provider_spend_microusd": delta.prior_provider_spend_microusd,
        "additional_projected_cost_microusd": (
            delta.additional_projected_cost_microusd
        ),
        "additional_authorized_max_cost_microusd": (
            delta.additional_authorized_max_cost_microusd
        ),
        "cumulative_worst_case_spend_microusd": (
            delta.cumulative_worst_case_spend_microusd
        ),
        "provider_inference_calls_executed_by_plan_creation": 0,
        "provider_spend_microusd_by_plan_creation": 0,
    }


def load_capability_delta_plan(path: str | Path) -> TogetherCapabilityDeltaPlan:
    return TogetherCapabilityDeltaPlan.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_delta_source_proof(
    path: str | Path,
) -> TogetherCapabilityDeltaSourceProof:
    return TogetherCapabilityDeltaSourceProof.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
