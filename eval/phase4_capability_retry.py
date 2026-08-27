"""Exact one-call diagnostic retry for an inconclusive capability probe.

The tracked plan binds one historical provider failure and one byte-equivalent
retry.  Paid execution remains behind a separate short-lived authorization,
uses the retry-reserve segment, resumes the historical provider audit, and
always stops after the single planned call.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum
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
)
from .phase4_capability_aggregation import (
    CapabilityRoleEvidence,
    CapabilityRoleEvidenceStatus,
    CandidateCapabilityDisposition,
    CandidateCapabilityOutcome,
    Phase4CapabilityAggregation,
    Phase4CapabilityAggregationSourceProof,
    validate_capability_aggregation_public_artifacts,
)
from .phase4_capability_recovery import (
    TogetherCapabilityDeltaPlan,
    TogetherCapabilityDeltaSourceProof,
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    delta_candidate_plan_for,
    validate_delta_candidate_execution_state,
)
from .phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderBudgetRuntime,
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderExecutionJournal,
    ProviderExecutionResult,
    ProviderHTTPErrorDiagnostic,
    ProviderPriceCard,
    ProviderRequestBinding,
    ProviderStructuredOutputDiagnostic,
    ProviderTransport,
    provider_request_content_sha256,
    validate_provider_execution_journal,
    validate_terminal_provider_budget_breach_journal,
)
from .phase4_provider_semantics import ProviderResponseInvariantManifest
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
    ProviderCallAuthorization,
    ProviderCallUsage,
    ProviderUsageLedger,
    provider_budget_limits_exceeded,
)
from .phase4_selector_recovery import (
    TogetherSelectorRecoveryDeltaPlan,
    TogetherSelectorRecoverySourceProof,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import (
    TogetherAuthorizedProviderRequest,
    TogetherCatalogPreflightBundle,
    TogetherLiveAuthorization,
    TogetherPaidStage,
    validate_live_authorization,
)
from .prequential import PrequentialSessionScript


NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]

DIAGNOSTIC_RETRY_CALL_COUNT = 1
DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD = 7_200


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class CapabilityDiagnosticRetryDisposition(str, Enum):
    """Content-free interpretation of the single diagnostic attempt."""

    RETRY_SUCCEEDED = "retry_succeeded"
    REPEATED_HTTP_400 = "repeated_http_400"
    PROVIDER_OR_TRANSPORT_INCONCLUSIVE = "provider_or_transport_inconclusive"
    INVALID_OUTPUT_REQUIRES_ADJUDICATION = (
        "invalid_output_requires_adjudication"
    )
    OTHER_FAILURE_REQUIRES_REVIEW = "other_failure_requires_review"


class TogetherCapabilityDiagnosticRetryPlan(ContractModel):
    """Tracked zero-spend plan for one exact provider diagnostic retry."""

    schema_version: Literal[
        "preference_eval_phase4_capability_diagnostic_retry_plan.v1"
    ] = "preference_eval_phase4_capability_diagnostic_retry_plan.v1"
    plan_id: StableId
    plan_version: Literal[1] = 1
    created_at: datetime
    capability_aggregation_sha256: Sha256Digest
    capability_aggregation_source_proof_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    corrected_together_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    source_catalog_preflight_bundle_sha256: Sha256Digest
    candidate_id: StableId
    role: LLMRole
    source_authorization_sha256: Sha256Digest
    source_state_sha256: Sha256Digest
    source_provider_ledger_sha256: Sha256Digest
    source_provider_journal_sha256: Sha256Digest
    source_call_id: StableId
    source_call_plan_sha256: Sha256Digest
    source_qualification_entry_sha256: Sha256Digest
    source_request_binding_sha256: Sha256Digest
    source_request_content_sha256: Sha256Digest
    source_provider_usage_sha256: Sha256Digest
    source_finalization_sha256: Sha256Digest
    source_failed_at: datetime
    source_outcome: Literal[ProviderCallOutcome.PROVIDER_ERROR] = (
        ProviderCallOutcome.PROVIDER_ERROR
    )
    source_failure_code: Literal["together_http_400"] = "together_http_400"
    source_billed_cost_microusd: Literal[0] = 0
    source_input_tokens: Literal[0] = 0
    source_output_tokens: Literal[0] = 0
    retry_call_id: StableId
    retry_of_call_id: StableId
    retry_request_content_sha256: Sha256Digest
    retry_projected_cost_microusd: Microusd
    retry_authorized_max_cost_microusd: Literal[7_200] = (
        DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
    )
    retry_budget_segment: Literal[BudgetSegment.RETRY_RESERVE] = (
        BudgetSegment.RETRY_RESERVE
    )
    retry_call_count: Literal[1] = DIAGNOSTIC_RETRY_CALL_COUNT
    prior_capability_spend_microusd: Microusd
    cumulative_worst_case_spend_microusd: Microusd
    original_capability_max_spend_microusd: Literal[150_000] = 150_000
    remaining_capability_ceiling_microusd: Microusd
    exact_request_replay_required: Literal[True] = True
    no_fallback_or_continuation: Literal[True] = True
    candidate_roster_preserved: Literal[True] = True
    model_selection_forbidden: Literal[True] = True
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    fresh_manual_paid_authorization_required: Literal[True] = True
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at", "source_failed_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "capability diagnostic retry time")
        return value

    @model_validator(mode="after")
    def require_one_exact_retry(self) -> Self:
        if self.created_at < self.source_failed_at:
            raise ValueError("diagnostic retry plan predates its source failure")
        if (
            self.retry_of_call_id != self.source_call_id
            or self.retry_call_id == self.source_call_id
        ):
            raise ValueError("diagnostic retry lineage differs from source call")
        if self.retry_request_content_sha256 != self.source_request_content_sha256:
            raise ValueError("diagnostic retry request content differs")
        if self.cumulative_worst_case_spend_microusd != (
            self.prior_capability_spend_microusd
            + self.retry_authorized_max_cost_microusd
        ):
            raise ValueError("diagnostic retry cumulative spend does not reconcile")
        if self.cumulative_worst_case_spend_microusd > (
            self.original_capability_max_spend_microusd
        ):
            raise ValueError("diagnostic retry exceeds the original capability ceiling")
        if self.remaining_capability_ceiling_microusd != (
            self.original_capability_max_spend_microusd
            - self.cumulative_worst_case_spend_microusd
        ):
            raise ValueError("diagnostic retry remaining ceiling does not reconcile")
        return self


class TogetherCapabilityDiagnosticRetrySourceProof(ContractModel):
    """Public-safe proof that exact private failure sources built the plan."""

    record_version: Literal[
        "phase4_capability_diagnostic_retry_source_proof.v1"
    ] = "phase4_capability_diagnostic_retry_source_proof.v1"
    proof_id: StableId
    proof_version: Literal[1] = 1
    validated_at: datetime
    retry_plan_sha256: Sha256Digest
    capability_aggregation_sha256: Sha256Digest
    capability_aggregation_source_proof_sha256: Sha256Digest
    source_authorization_sha256: Sha256Digest
    source_state_sha256: Sha256Digest
    source_request_binding_sha256: Sha256Digest
    source_request_content_sha256: Sha256Digest
    source_provider_event_sha256: Sha256Digest
    full_private_source_validation_passed: Literal[True] = True
    exact_private_request_rebuild_passed: Literal[True] = True
    source_artifacts_unchanged: Literal[True] = True
    values_messages_and_context_omitted: Literal[True] = True
    provider_inference_calls_executed_by_proof_creation: Literal[0] = 0
    provider_spend_microusd_by_proof_creation: Literal[0] = 0

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        _require_aware(value, "capability diagnostic retry proof time")
        return value


class TogetherCapabilityDiagnosticRetryManualApproval(ContractModel):
    """Private approval for only the exact one-call diagnostic retry."""

    record_version: Literal[
        "phase4_capability_diagnostic_retry_approval.v1"
    ] = "phase4_capability_diagnostic_retry_approval.v1"
    approval_id: StableId
    approval_version: PositiveVersion
    retry_plan_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    candidate_id: StableId
    role: LLMRole
    retry_call_id: StableId
    retry_of_call_id: StableId
    retry_request_content_sha256: Sha256Digest
    approved_call_count: Literal[1] = DIAGNOSTIC_RETRY_CALL_COUNT
    approved_max_spend_microusd: Literal[7_200] = (
        DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
    )
    cumulative_worst_case_spend_microusd: Microusd
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "capability diagnostic retry approval time")
        return value

    @model_validator(mode="after")
    def require_active_window(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("diagnostic retry approval must expire later")
        if self.expires_at - self.approved_at > timedelta(minutes=30):
            raise ValueError("diagnostic retry approval window exceeds 30 minutes")
        return self


class TogetherCapabilityDiagnosticRetryAuthorizationBundle(ContractModel):
    """Private exact-request authorization for the one diagnostic send."""

    schema_version: Literal[
        "preference_eval_phase4_capability_diagnostic_retry_authorization.v1"
    ] = "preference_eval_phase4_capability_diagnostic_retry_authorization.v1"
    bundle_id: StableId
    bundle_version: PositiveVersion
    retry_plan_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    fresh_catalog_preflight_bundle_sha256: Sha256Digest
    source_state_sha256: Sha256Digest
    manual_approval: TogetherCapabilityDiagnosticRetryManualApproval
    live_authorization: TogetherLiveAuthorization
    exact_request_transport_boundary_required: Literal[True] = True

    @model_validator(mode="after")
    def require_matching_approval(self) -> Self:
        if (
            self.manual_approval.retry_plan_sha256,
            self.manual_approval.source_proof_sha256,
        ) != (self.retry_plan_sha256, self.source_proof_sha256):
            raise ValueError("diagnostic retry approval hashes differ")
        if (
            self.live_authorization.approved_at,
            self.live_authorization.expires_at,
        ) != (
            self.manual_approval.approved_at,
            self.manual_approval.expires_at,
        ):
            raise ValueError("diagnostic retry authorization windows differ")
        return self


class TogetherCapabilityDiagnosticRetryExecutionState(ContractModel):
    """Private progressive audit containing the source call and its one retry."""

    schema_version: Literal[
        "preference_eval_phase4_capability_diagnostic_retry_state.v1"
    ] = "preference_eval_phase4_capability_diagnostic_retry_state.v1"
    state_id: StableId
    state_version: Literal[1] = 1
    retry_plan_sha256: Sha256Digest
    source_proof_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    source_state_sha256: Sha256Digest
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    retry_output: TogetherCapabilityOutputRecord | None = None
    provider_error_diagnostic: ProviderHTTPErrorDiagnostic | None = None
    structured_output_diagnostic: ProviderStructuredOutputDiagnostic | None = None
    disposition: CapabilityDiagnosticRetryDisposition | None = None
    retry_provider_spend_microusd: Microusd
    cumulative_capability_spend_microusd: Microusd
    remaining_capability_ceiling_microusd: Microusd
    manual_spend_ceiling_breached: bool
    provider_budget_limit_breached: bool
    completed_at: datetime | None = None
    retry_call_count: Literal[1] = DIAGNOSTIC_RETRY_CALL_COUNT
    candidate_roster_changed: Literal[False] = False
    model_capability_rejection_recorded: Literal[False] = False
    model_selection_performed: Literal[False] = False

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            _require_aware(value, "capability diagnostic retry completion time")
        return value

    @model_validator(mode="after")
    def require_one_diagnostic_kind(self) -> Self:
        if (
            self.provider_error_diagnostic is not None
            and self.structured_output_diagnostic is not None
        ):
            raise ValueError("diagnostic retry state mixes diagnostic kinds")
        return self


def _source_provider_event_sha256(
    plan: TogetherCapabilityDiagnosticRetryPlan,
) -> str:
    return content_sha256(
        {
            "source_call_id": plan.source_call_id,
            "source_request_binding_sha256": plan.source_request_binding_sha256,
            "source_request_content_sha256": plan.source_request_content_sha256,
            "source_provider_usage_sha256": plan.source_provider_usage_sha256,
            "source_finalization_sha256": plan.source_finalization_sha256,
            "source_outcome": plan.source_outcome.value,
            "source_failure_code": plan.source_failure_code,
        }
    )


def _inconclusive_source(
    aggregation: Phase4CapabilityAggregation,
) -> tuple[CandidateCapabilityOutcome, CapabilityRoleEvidence]:
    outcomes = [
        item
        for item in aggregation.candidate_outcomes
        if item.disposition
        is CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
    ]
    if len(outcomes) != 1:
        raise ValueError("diagnostic retry requires one inconclusive candidate")
    evidence = [
        item
        for item in outcomes[0].role_evidence
        if item.status
        is CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
    ]
    if len(evidence) != 1:
        raise ValueError("diagnostic retry requires one provider failure")
    return outcomes[0], evidence[0]


def _qualification_entry(
    readiness: Phase4TogetherReadinessBundle,
    call_id: str,
) -> QualificationCallPlanEntry:
    matches = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.call_id == call_id
    ]
    if len(matches) != 1:
        raise ValueError("diagnostic retry source qualification entry differs")
    return matches[0]


def _candidate_parts(
    suite: Phase4TogetherSuite,
) -> tuple[list[OpenWeightModelCandidate], list[ProviderPriceCard]]:
    return (
        [item.candidate for item in suite.candidates],
        [item.price_card for item in suite.candidates],
    )


def _source_audit_parts(
    state: TogetherDeltaCandidateExecutionState,
    call_id: str,
) -> tuple[
    ProviderRequestBinding,
    ProviderCallAuthorization,
    ProviderCallUsage,
    ProviderCallFinalization,
]:
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
    try:
        return (
            bindings[call_id],
            authorizations[call_id],
            usages[call_id],
            finalizations[call_id],
        )
    except KeyError as error:
        raise ValueError("diagnostic retry source audit is incomplete") from error


def _validate_private_source(
    aggregation: Phase4CapabilityAggregation,
    delta: TogetherSelectorRecoveryDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_authorization: TogetherDeltaCandidateAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
) -> tuple[
    CandidateCapabilityOutcome,
    CapabilityRoleEvidence,
    TogetherCapabilityCallPlan,
    QualificationCallPlanEntry,
    ProviderRequestBinding,
    ProviderCallUsage,
    ProviderCallFinalization,
]:
    outcome, evidence = _inconclusive_source(aggregation)
    if (
        content_sha256(source_authorization),
        content_sha256(source_state),
    ) != (outcome.authorization_sha256, outcome.state_sha256):
        raise ValueError("diagnostic retry private source hashes differ")
    candidate_plan = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        outcome.candidate_id,
    )
    validate_delta_candidate_execution_state(
        source_state,
        delta,
        candidate_plan,
        source_authorization,
        suite,
        profile,
    )
    if source_state.receipt is not None:
        raise ValueError("diagnostic retry source cannot have a receipt")
    source_call = next(
        (
            item
            for item in corrected_plan.calls
            if item.candidate_id == outcome.candidate_id
            and item.role is evidence.role
        ),
        None,
    )
    if source_call is None or (
        source_call.call_id,
        content_sha256(source_call),
    ) != (evidence.call_id, evidence.call_plan_sha256):
        raise ValueError("diagnostic retry source call differs")
    binding, provider_authorization, usage, finalization = _source_audit_parts(
        source_state,
        source_call.call_id,
    )
    if (
        content_sha256(source_state.provider_ledger),
        content_sha256(source_state.provider_journal),
        content_sha256(usage),
        content_sha256(finalization),
    ) != (
        outcome.provider_ledger_sha256,
        outcome.provider_journal_sha256,
        evidence.provider_usage_sha256,
        evidence.finalization_sha256,
    ):
        raise ValueError("diagnostic retry source event hashes differ")
    if (
        binding.model_candidate_id,
        binding.role,
        finalization.outcome,
        finalization.failure_code,
        usage.billed_cost_microusd,
        usage.input_tokens,
        usage.output_tokens,
        provider_authorization.authorized_max_cost_microusd,
    ) != (
        outcome.candidate_id,
        evidence.role,
        ProviderCallOutcome.PROVIDER_ERROR,
        "together_http_400",
        0,
        0,
        0,
        DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD,
    ):
        raise ValueError("diagnostic retry source failure shape differs")
    if finalization.response_sha256 is not None:
        raise ValueError("diagnostic retry source unexpectedly has model output")
    entry = _qualification_entry(readiness, source_call.call_id)
    rebuilt = rebuild_qualification_call(
        suite,
        profile,
        fixture,
        session,
        semantic_map,
        entry,
        created_at=binding.created_at,
    )
    if rebuilt.request.binding != binding:
        raise ValueError("diagnostic retry source request does not rebuild")
    request_content_sha256 = provider_request_content_sha256(binding)
    if (
        request_content_sha256,
        usage.request_sha256,
        source_call.request_template_sha256,
    ) != (request_content_sha256,) * 3:
        raise ValueError("diagnostic retry source request hashes differ")
    if (
        source_call.authorized_max_cost_microusd
        != DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
    ):
        raise ValueError("diagnostic retry source call cap differs")
    return (
        outcome,
        evidence,
        source_call,
        entry,
        binding,
        usage,
        finalization,
    )


def validate_capability_diagnostic_retry_plan_public(
    plan: TogetherCapabilityDiagnosticRetryPlan,
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    delta: TogetherSelectorRecoveryDeltaPlan,
    delta_proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_delta_proof: TogetherCapabilityDeltaSourceProof,
    parent_plan: TogetherCapabilityPlan,
    parent_suite: Phase4TogetherSuite,
    parent_readiness: Phase4TogetherReadinessBundle,
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    response_semantics_manifest: ProviderResponseInvariantManifest,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    validate_capability_aggregation_public_artifacts(
        aggregation,
        aggregation_proof,
        delta,
        delta_proof,
        parent_delta,
        parent_delta_proof,
        parent_plan,
        parent_suite,
        parent_readiness,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        profile,
        response_semantics_manifest,
        fixture,
        session,
        semantic_map,
    )
    outcome, evidence = _inconclusive_source(aggregation)
    source_call = next(
        (
            item
            for item in corrected_plan.calls
            if item.candidate_id == outcome.candidate_id
            and item.role is evidence.role
        ),
        None,
    )
    if source_call is None:
        raise ValueError("capability diagnostic retry public source call differs")
    entry = _qualification_entry(corrected_readiness, source_call.call_id)
    expected = (
        content_sha256(aggregation),
        content_sha256(aggregation_proof),
        content_sha256(corrected_plan),
        content_sha256(corrected_suite),
        content_sha256(corrected_readiness),
        content_sha256(profile),
        content_sha256(response_semantics_manifest),
        aggregation.catalog_preflight_bundle_sha256,
        outcome.candidate_id,
        evidence.role,
        outcome.authorization_sha256,
        outcome.state_sha256,
        outcome.provider_ledger_sha256,
        outcome.provider_journal_sha256,
        evidence.call_id,
        evidence.call_plan_sha256,
        content_sha256(entry),
        source_call.request_template_sha256,
        evidence.provider_usage_sha256,
        evidence.finalization_sha256,
        outcome.terminal_at,
        evidence.provider_outcome,
        evidence.failure_code,
        source_call.request_template_sha256,
        source_call.projected_cost_microusd,
        source_call.authorized_max_cost_microusd,
        aggregation.cumulative_provider_spend_microusd,
        aggregation.cumulative_provider_spend_microusd
        + DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD,
        aggregation.original_capability_max_spend_microusd,
        aggregation.remaining_capability_ceiling_microusd
        - DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD,
    )
    actual = (
        plan.capability_aggregation_sha256,
        plan.capability_aggregation_source_proof_sha256,
        plan.corrected_capability_plan_sha256,
        plan.corrected_together_suite_sha256,
        plan.corrected_readiness_sha256,
        plan.robustness_profile_sha256,
        plan.provider_response_semantics_manifest_sha256,
        plan.source_catalog_preflight_bundle_sha256,
        plan.candidate_id,
        plan.role,
        plan.source_authorization_sha256,
        plan.source_state_sha256,
        plan.source_provider_ledger_sha256,
        plan.source_provider_journal_sha256,
        plan.source_call_id,
        plan.source_call_plan_sha256,
        plan.source_qualification_entry_sha256,
        plan.source_request_content_sha256,
        plan.source_provider_usage_sha256,
        plan.source_finalization_sha256,
        plan.source_failed_at,
        plan.source_outcome,
        plan.source_failure_code,
        plan.retry_request_content_sha256,
        plan.retry_projected_cost_microusd,
        plan.retry_authorized_max_cost_microusd,
        plan.prior_capability_spend_microusd,
        plan.cumulative_worst_case_spend_microusd,
        plan.original_capability_max_spend_microusd,
        plan.remaining_capability_ceiling_microusd,
    )
    if actual != expected:
        raise ValueError("capability diagnostic retry public bindings differ")


def build_capability_diagnostic_retry_plan(
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    delta: TogetherSelectorRecoveryDeltaPlan,
    delta_proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_delta_proof: TogetherCapabilityDeltaSourceProof,
    parent_plan: TogetherCapabilityPlan,
    parent_suite: Phase4TogetherSuite,
    parent_readiness: Phase4TogetherReadinessBundle,
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    response_semantics_manifest: ProviderResponseInvariantManifest,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_catalog: TogetherCatalogPreflightBundle,
    source_authorization: TogetherDeltaCandidateAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
    *,
    plan_id: str,
    retry_call_id: str,
    created_at: datetime,
) -> TogetherCapabilityDiagnosticRetryPlan:
    validate_capability_aggregation_public_artifacts(
        aggregation,
        aggregation_proof,
        delta,
        delta_proof,
        parent_delta,
        parent_delta_proof,
        parent_plan,
        parent_suite,
        parent_readiness,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        profile,
        response_semantics_manifest,
        fixture,
        session,
        semantic_map,
    )
    if content_sha256(source_catalog) != (
        aggregation.catalog_preflight_bundle_sha256
    ):
        raise ValueError("diagnostic retry source catalog differs from aggregation")
    (
        outcome,
        evidence,
        source_call,
        entry,
        binding,
        usage,
        finalization,
    ) = _validate_private_source(
        aggregation,
        delta,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
        source_authorization,
        source_state,
    )
    plan = TogetherCapabilityDiagnosticRetryPlan(
        plan_id=plan_id,
        created_at=created_at,
        capability_aggregation_sha256=content_sha256(aggregation),
        capability_aggregation_source_proof_sha256=content_sha256(
            aggregation_proof
        ),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        corrected_together_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        robustness_profile_sha256=content_sha256(profile),
        provider_response_semantics_manifest_sha256=content_sha256(
            response_semantics_manifest
        ),
        source_catalog_preflight_bundle_sha256=content_sha256(source_catalog),
        candidate_id=outcome.candidate_id,
        role=evidence.role,
        source_authorization_sha256=content_sha256(source_authorization),
        source_state_sha256=content_sha256(source_state),
        source_provider_ledger_sha256=content_sha256(
            source_state.provider_ledger
        ),
        source_provider_journal_sha256=content_sha256(
            source_state.provider_journal
        ),
        source_call_id=source_call.call_id,
        source_call_plan_sha256=content_sha256(source_call),
        source_qualification_entry_sha256=content_sha256(entry),
        source_request_binding_sha256=content_sha256(binding),
        source_request_content_sha256=provider_request_content_sha256(binding),
        source_provider_usage_sha256=content_sha256(usage),
        source_finalization_sha256=content_sha256(finalization),
        source_failed_at=finalization.created_at,
        retry_call_id=retry_call_id,
        retry_of_call_id=source_call.call_id,
        retry_request_content_sha256=provider_request_content_sha256(binding),
        retry_projected_cost_microusd=source_call.projected_cost_microusd,
        prior_capability_spend_microusd=(
            aggregation.cumulative_provider_spend_microusd
        ),
        cumulative_worst_case_spend_microusd=(
            aggregation.cumulative_provider_spend_microusd
            + DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
        ),
        remaining_capability_ceiling_microusd=(
            aggregation.remaining_capability_ceiling_microusd
            - DIAGNOSTIC_RETRY_MAX_SPEND_MICROUSD
        ),
    )
    validate_capability_diagnostic_retry_plan_public(
        plan,
        aggregation,
        aggregation_proof,
        delta,
        delta_proof,
        parent_delta,
        parent_delta_proof,
        parent_plan,
        parent_suite,
        parent_readiness,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        profile,
        response_semantics_manifest,
        fixture,
        session,
        semantic_map,
    )
    return plan


def validate_capability_diagnostic_retry_source_proof(
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    plan: TogetherCapabilityDiagnosticRetryPlan,
) -> None:
    if proof.validated_at < plan.created_at:
        raise ValueError("capability diagnostic retry proof predates plan")
    expected = (
        content_sha256(plan),
        plan.capability_aggregation_sha256,
        plan.capability_aggregation_source_proof_sha256,
        plan.source_authorization_sha256,
        plan.source_state_sha256,
        plan.source_request_binding_sha256,
        plan.source_request_content_sha256,
        _source_provider_event_sha256(plan),
    )
    actual = (
        proof.retry_plan_sha256,
        proof.capability_aggregation_sha256,
        proof.capability_aggregation_source_proof_sha256,
        proof.source_authorization_sha256,
        proof.source_state_sha256,
        proof.source_request_binding_sha256,
        proof.source_request_content_sha256,
        proof.source_provider_event_sha256,
    )
    if actual != expected:
        raise ValueError("capability diagnostic retry proof bindings differ")


def _validate_plan_source_input_hashes(
    plan: TogetherCapabilityDiagnosticRetryPlan,
    aggregation: Phase4CapabilityAggregation,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    source_catalog: TogetherCatalogPreflightBundle,
) -> None:
    if plan.source_catalog_preflight_bundle_sha256 != (
        aggregation.catalog_preflight_bundle_sha256
    ):
        raise ValueError("capability diagnostic retry source catalog differs")
    if (
        plan.capability_aggregation_sha256,
        plan.corrected_capability_plan_sha256,
        plan.corrected_together_suite_sha256,
        plan.corrected_readiness_sha256,
        plan.robustness_profile_sha256,
        plan.source_catalog_preflight_bundle_sha256,
    ) != (
        content_sha256(aggregation),
        content_sha256(corrected_plan),
        content_sha256(suite),
        content_sha256(readiness),
        content_sha256(profile),
        content_sha256(source_catalog),
    ):
        raise ValueError("capability diagnostic retry source inputs differ")


def build_capability_diagnostic_retry_source_proof(
    plan: TogetherCapabilityDiagnosticRetryPlan,
    aggregation: Phase4CapabilityAggregation,
    delta: TogetherSelectorRecoveryDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_catalog: TogetherCatalogPreflightBundle,
    source_authorization: TogetherDeltaCandidateAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
    *,
    proof_id: str,
    validated_at: datetime,
) -> TogetherCapabilityDiagnosticRetrySourceProof:
    _validate_plan_source_input_hashes(
        plan,
        aggregation,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        source_catalog,
    )
    (
        _outcome,
        _evidence,
        _source_call,
        _entry,
        binding,
        usage,
        finalization,
    ) = _validate_private_source(
        aggregation,
        delta,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
        source_authorization,
        source_state,
    )
    if (
        content_sha256(source_authorization),
        content_sha256(source_state),
        content_sha256(source_state.provider_ledger),
        content_sha256(source_state.provider_journal),
    ) != (
        plan.source_authorization_sha256,
        plan.source_state_sha256,
        plan.source_provider_ledger_sha256,
        plan.source_provider_journal_sha256,
    ):
        raise ValueError("capability diagnostic retry proof sources differ")
    if (
        content_sha256(binding),
        provider_request_content_sha256(binding),
        content_sha256(usage),
        content_sha256(finalization),
    ) != (
        plan.source_request_binding_sha256,
        plan.source_request_content_sha256,
        plan.source_provider_usage_sha256,
        plan.source_finalization_sha256,
    ):
        raise ValueError("capability diagnostic retry proof event differs")
    proof = TogetherCapabilityDiagnosticRetrySourceProof(
        proof_id=proof_id,
        validated_at=validated_at,
        retry_plan_sha256=content_sha256(plan),
        capability_aggregation_sha256=plan.capability_aggregation_sha256,
        capability_aggregation_source_proof_sha256=(
            plan.capability_aggregation_source_proof_sha256
        ),
        source_authorization_sha256=plan.source_authorization_sha256,
        source_state_sha256=plan.source_state_sha256,
        source_request_binding_sha256=plan.source_request_binding_sha256,
        source_request_content_sha256=plan.source_request_content_sha256,
        source_provider_event_sha256=_source_provider_event_sha256(plan),
    )
    validate_capability_diagnostic_retry_source_proof(proof, plan)
    return proof


def validate_capability_diagnostic_retry_authorization_bundle(
    bundle: TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    plan: TogetherCapabilityDiagnosticRetryPlan,
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fresh_catalog: TogetherCatalogPreflightBundle,
    *,
    now: datetime,
) -> None:
    validate_capability_diagnostic_retry_source_proof(proof, plan)
    if (
        plan.corrected_together_suite_sha256,
        plan.corrected_readiness_sha256,
        plan.robustness_profile_sha256,
    ) != (
        content_sha256(suite),
        content_sha256(readiness),
        content_sha256(profile),
    ):
        raise ValueError("capability diagnostic retry live inputs differ")
    if (
        bundle.retry_plan_sha256,
        bundle.source_proof_sha256,
        bundle.fresh_catalog_preflight_bundle_sha256,
        bundle.source_state_sha256,
    ) != (
        content_sha256(plan),
        content_sha256(proof),
        content_sha256(fresh_catalog),
        plan.source_state_sha256,
    ):
        raise ValueError("capability diagnostic retry authorization hashes differ")
    approval = bundle.manual_approval
    if approval.approved_at < proof.validated_at:
        raise ValueError("diagnostic retry approval predates reviewed proof")
    if content_sha256(fresh_catalog) == (
        plan.source_catalog_preflight_bundle_sha256
    ):
        raise ValueError("diagnostic retry requires a new catalog preflight")
    if fresh_catalog.receipt.checked_at < proof.validated_at:
        raise ValueError("diagnostic retry catalog predates reviewed proof")
    if not (
        fresh_catalog.receipt.checked_at
        <= approval.approved_at
        <= fresh_catalog.receipt.checked_at + timedelta(minutes=30)
    ):
        raise ValueError("diagnostic retry requires a fresh catalog preflight")
    expected_approval = (
        plan.candidate_id,
        plan.role,
        plan.retry_call_id,
        plan.retry_of_call_id,
        plan.retry_request_content_sha256,
        plan.cumulative_worst_case_spend_microusd,
    )
    actual_approval = (
        approval.candidate_id,
        approval.role,
        approval.retry_call_id,
        approval.retry_of_call_id,
        approval.retry_request_content_sha256,
        approval.cumulative_worst_case_spend_microusd,
    )
    if actual_approval != expected_approval:
        raise ValueError("capability diagnostic retry approval differs from plan")
    if not approval.approved_at <= now <= approval.expires_at:
        raise ValueError("capability diagnostic retry approval is not active")
    live = bundle.live_authorization
    validate_live_authorization(
        suite,
        profile,
        fresh_catalog,
        readiness.token_readiness_receipt,
        readiness.headroom_policy,
        live,
        capability_receipt=None,
        now=now,
    )
    exact_request = TogetherAuthorizedProviderRequest(
        call_id=plan.retry_call_id,
        model_candidate_id=plan.candidate_id,
        role=plan.role,
        request_content_sha256=plan.retry_request_content_sha256,
        authorized_max_cost_microusd=plan.retry_authorized_max_cost_microusd,
    )
    if (
        live.record_version,
        live.stage,
        live.budget_segment,
        live.authorized_candidate_ids,
        live.authorized_roles,
        live.approved_max_spend_microusd,
        live.authorized_requests,
    ) != (
        "phase4_together_live_authorization.v2",
        TogetherPaidStage.CAPABILITY_PREFLIGHT,
        BudgetSegment.RETRY_RESERVE,
        [plan.candidate_id],
        [plan.role],
        plan.retry_authorized_max_cost_microusd,
        [exact_request],
    ):
        raise ValueError("capability diagnostic retry live scope differs")


def build_capability_diagnostic_retry_authorization_bundle(
    plan: TogetherCapabilityDiagnosticRetryPlan,
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fresh_catalog: TogetherCatalogPreflightBundle,
    *,
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TogetherCapabilityDiagnosticRetryAuthorizationBundle:
    validate_capability_diagnostic_retry_source_proof(proof, plan)
    exact_request = TogetherAuthorizedProviderRequest(
        call_id=plan.retry_call_id,
        model_candidate_id=plan.candidate_id,
        role=plan.role,
        request_content_sha256=plan.retry_request_content_sha256,
        authorized_max_cost_microusd=plan.retry_authorized_max_cost_microusd,
    )
    approval = TogetherCapabilityDiagnosticRetryManualApproval(
        approval_id=approval_id,
        approval_version=1,
        retry_plan_sha256=content_sha256(plan),
        source_proof_sha256=content_sha256(proof),
        candidate_id=plan.candidate_id,
        role=plan.role,
        retry_call_id=plan.retry_call_id,
        retry_of_call_id=plan.retry_of_call_id,
        retry_request_content_sha256=plan.retry_request_content_sha256,
        cumulative_worst_case_spend_microusd=(
            plan.cumulative_worst_case_spend_microusd
        ),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    live = TogetherLiveAuthorization(
        record_version="phase4_together_live_authorization.v2",
        authorization_id=f"{approval_id}_live",
        authorization_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        account_privacy_attestation_sha256=content_sha256(
            fresh_catalog.account_privacy_attestation
        ),
        catalog_preflight_receipt_sha256=content_sha256(fresh_catalog.receipt),
        token_readiness_receipt_sha256=content_sha256(
            readiness.token_readiness_receipt
        ),
        headroom_policy_sha256=content_sha256(readiness.headroom_policy),
        stage=TogetherPaidStage.CAPABILITY_PREFLIGHT,
        budget_segment=BudgetSegment.RETRY_RESERVE,
        authorized_candidate_ids=[plan.candidate_id],
        authorized_roles=[plan.role],
        approved_max_spend_microusd=plan.retry_authorized_max_cost_microusd,
        authorized_requests=[exact_request],
        approved_at=approved_at,
        expires_at=expires_at,
    )
    bundle = TogetherCapabilityDiagnosticRetryAuthorizationBundle(
        bundle_id=bundle_id,
        bundle_version=1,
        retry_plan_sha256=content_sha256(plan),
        source_proof_sha256=content_sha256(proof),
        fresh_catalog_preflight_bundle_sha256=content_sha256(fresh_catalog),
        source_state_sha256=plan.source_state_sha256,
        manual_approval=approval,
        live_authorization=live,
    )
    validate_capability_diagnostic_retry_authorization_bundle(
        bundle,
        plan,
        proof,
        suite,
        profile,
        readiness,
        fresh_catalog,
        now=approved_at,
    )
    return bundle


def _retry_request(
    original: PrivateStructuredProviderRequest,
    plan: TogetherCapabilityDiagnosticRetryPlan,
    *,
    created_at: datetime,
) -> PrivateStructuredProviderRequest:
    payload = original.model_dump(mode="python")
    binding = payload.get("binding")
    if not isinstance(binding, dict):
        raise ValueError("diagnostic retry request binding is malformed")
    binding["call_id"] = plan.retry_call_id
    binding["created_at"] = created_at
    request = PrivateStructuredProviderRequest.model_validate(payload)
    if provider_request_content_sha256(request.binding) != (
        plan.retry_request_content_sha256
    ):
        raise ValueError("diagnostic retry rebuilt request differs")
    return request


def _retry_disposition(
    outcome: ProviderCallOutcome,
    failure_code: str | None,
) -> CapabilityDiagnosticRetryDisposition:
    if outcome is ProviderCallOutcome.SUCCESS:
        return CapabilityDiagnosticRetryDisposition.RETRY_SUCCEEDED
    if (
        outcome is ProviderCallOutcome.PROVIDER_ERROR
        and failure_code == "together_http_400"
    ):
        return CapabilityDiagnosticRetryDisposition.REPEATED_HTTP_400
    if outcome in {
        ProviderCallOutcome.PROVIDER_ERROR,
        ProviderCallOutcome.TRANSPORT_ERROR,
        ProviderCallOutcome.CANCELLED,
    }:
        return (
            CapabilityDiagnosticRetryDisposition.PROVIDER_OR_TRANSPORT_INCONCLUSIVE
        )
    if outcome is ProviderCallOutcome.INVALID_OUTPUT:
        return (
            CapabilityDiagnosticRetryDisposition.INVALID_OUTPUT_REQUIRES_ADJUDICATION
        )
    return CapabilityDiagnosticRetryDisposition.OTHER_FAILURE_REQUIRES_REVIEW


def validate_capability_diagnostic_retry_execution_state(
    state: TogetherCapabilityDiagnosticRetryExecutionState,
    plan: TogetherCapabilityDiagnosticRetryPlan,
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    authorization: TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    if (
        state.retry_plan_sha256,
        state.source_proof_sha256,
        state.authorization_bundle_sha256,
        state.source_state_sha256,
    ) != (
        content_sha256(plan),
        content_sha256(proof),
        content_sha256(authorization),
        content_sha256(source_state),
    ):
        raise ValueError("capability diagnostic retry state hashes differ")
    source_ledger = source_state.provider_ledger
    source_journal = source_state.provider_journal
    if (
        state.provider_ledger.authorizations[: len(source_ledger.authorizations)]
        != source_ledger.authorizations
        or state.provider_ledger.calls[: len(source_ledger.calls)]
        != source_ledger.calls
        or state.provider_journal.request_bindings[
            : len(source_journal.request_bindings)
        ]
        != source_journal.request_bindings
        or state.provider_journal.finalizations[: len(source_journal.finalizations)]
        != source_journal.finalizations
        or state.provider_journal.no_charge_attestations[
            : len(source_journal.no_charge_attestations)
        ]
        != source_journal.no_charge_attestations
    ):
        raise ValueError("capability diagnostic retry changed its source prefix")
    if (
        len(state.provider_ledger.authorizations)
        != len(source_ledger.authorizations) + 1
        or len(state.provider_journal.request_bindings)
        != len(source_journal.request_bindings) + 1
        or len(state.provider_journal.no_charge_attestations)
        != len(source_journal.no_charge_attestations)
    ):
        raise ValueError("capability diagnostic retry must authorize one call")
    closed_count = len(state.provider_ledger.calls) - len(source_ledger.calls)
    if closed_count not in {0, 1} or (
        len(state.provider_journal.finalizations)
        != len(source_journal.finalizations) + closed_count
    ):
        raise ValueError("capability diagnostic retry completion shape differs")
    candidates, price_cards = _candidate_parts(suite)
    provider_limit_breached = provider_budget_limits_exceeded(
        state.provider_ledger,
        profile,
    )
    if provider_limit_breached:
        if closed_count != 1:
            raise ValueError("outstanding retry cannot exceed provider budget")
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
            require_complete=closed_count == 1,
        )
    binding = state.provider_journal.request_bindings[-1]
    provider_authorization = state.provider_ledger.authorizations[-1]
    if (
        binding.call_id,
        binding.model_candidate_id,
        binding.role,
        provider_request_content_sha256(binding),
        provider_authorization.segment,
        provider_authorization.retry_of_call_id,
        provider_authorization.authorized_max_cost_microusd,
        provider_authorization.request_sha256,
    ) != (
        plan.retry_call_id,
        plan.candidate_id,
        plan.role,
        plan.retry_request_content_sha256,
        BudgetSegment.RETRY_RESERVE,
        plan.source_call_id,
        plan.retry_authorized_max_cost_microusd,
        plan.retry_request_content_sha256,
    ):
        raise ValueError("capability diagnostic retry lineage differs")
    if closed_count == 0:
        cumulative = plan.prior_capability_spend_microusd
        if (
            state.retry_output,
            state.provider_error_diagnostic,
            state.structured_output_diagnostic,
            state.disposition,
            state.retry_provider_spend_microusd,
            state.cumulative_capability_spend_microusd,
            state.remaining_capability_ceiling_microusd,
            state.manual_spend_ceiling_breached,
            state.provider_budget_limit_breached,
            state.completed_at,
        ) != (
            None,
            None,
            None,
            None,
            0,
            cumulative,
            plan.original_capability_max_spend_microusd - cumulative,
            False,
            provider_limit_breached,
            None,
        ):
            raise ValueError("outstanding diagnostic retry state differs")
        return
    usage = state.provider_ledger.calls[-1]
    finalization = state.provider_journal.finalizations[-1]
    if (
        usage.retry_of_call_id,
        usage.request_sha256,
        finalization.call_id,
    ) != (
        plan.source_call_id,
        plan.retry_request_content_sha256,
        plan.retry_call_id,
    ):
        raise ValueError("capability diagnostic retry completion lineage differs")
    output = state.retry_output
    if finalization.outcome is ProviderCallOutcome.SUCCESS:
        if output is None or (
            output.call_id,
            output.candidate_id,
            output.role,
            output.output_sha256,
        ) != (
            plan.retry_call_id,
            plan.candidate_id,
            plan.role,
            finalization.response_sha256,
        ):
            raise ValueError("successful diagnostic retry lacks exact output")
    elif output is not None:
        raise ValueError("failed diagnostic retry cannot retain output")
    http_diagnostic = state.provider_error_diagnostic
    if http_diagnostic is not None and (
        http_diagnostic.call_id,
        http_diagnostic.model_candidate_id,
        http_diagnostic.role,
        http_diagnostic.request_binding_sha256,
        http_diagnostic.request_content_sha256,
        http_diagnostic.finalization_sha256,
        http_diagnostic.provider_request_id_sha256,
        http_diagnostic.failure_code,
    ) != (
        plan.retry_call_id,
        plan.candidate_id,
        plan.role,
        content_sha256(binding),
        plan.retry_request_content_sha256,
        content_sha256(finalization),
        finalization.provider_request_id_sha256,
        finalization.failure_code,
    ):
        raise ValueError("capability diagnostic HTTP-error binding differs")
    if finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR:
        if http_diagnostic is None:
            raise ValueError("provider-error retry requires sanitized diagnostic")
        if (
            finalization.failure_code == "together_http_400"
            and http_diagnostic.http_status_code != 400
        ):
            raise ValueError("repeated HTTP 400 diagnostic status differs")
    elif http_diagnostic is not None:
        raise ValueError("non-provider-error retry cannot carry HTTP diagnostic")
    structured_diagnostic = state.structured_output_diagnostic
    if structured_diagnostic is not None and (
        structured_diagnostic.call_id,
        structured_diagnostic.role,
        structured_diagnostic.response_schema_sha256,
        structured_diagnostic.finalization_sha256,
    ) != (
        plan.retry_call_id,
        plan.role,
        binding.response_schema_sha256,
        content_sha256(finalization),
    ):
        raise ValueError("capability diagnostic structured-output binding differs")
    if finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT:
        if structured_diagnostic is None:
            raise ValueError("invalid diagnostic retry requires validation diagnostic")
    elif structured_diagnostic is not None:
        raise ValueError("non-invalid retry cannot carry validation diagnostic")
    expected_disposition = _retry_disposition(
        finalization.outcome,
        finalization.failure_code,
    )
    retry_spend = usage.billed_cost_microusd
    cumulative = plan.prior_capability_spend_microusd + retry_spend
    if (
        state.disposition,
        state.retry_provider_spend_microusd,
        state.cumulative_capability_spend_microusd,
        state.remaining_capability_ceiling_microusd,
        state.manual_spend_ceiling_breached,
        state.provider_budget_limit_breached,
    ) != (
        expected_disposition,
        retry_spend,
        cumulative,
        max(0, plan.original_capability_max_spend_microusd - cumulative),
        retry_spend > plan.retry_authorized_max_cost_microusd,
        provider_limit_breached,
    ):
        raise ValueError("capability diagnostic retry totals differ")
    if state.completed_at is None:
        raise ValueError("closed diagnostic retry lacks completion time")
    if state.completed_at < finalization.created_at:
        raise ValueError("capability diagnostic retry completion predates provider")


def _build_capability_diagnostic_retry_execution_state(
    *,
    state_id: str,
    plan: TogetherCapabilityDiagnosticRetryPlan,
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    authorization: TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
    runtime: ProviderBudgetRuntime,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    output: TogetherCapabilityOutputRecord | None,
    result: ProviderExecutionResult | None,
    completed_at: datetime | None,
) -> TogetherCapabilityDiagnosticRetryExecutionState:
    ledger = runtime.ledger_snapshot()
    journal = runtime.journal_snapshot()
    closed = len(ledger.calls) == len(source_state.provider_ledger.calls) + 1
    if closed:
        if result is None or completed_at is None:
            raise ValueError("closed diagnostic retry lacks execution result")
        finalization = journal.finalizations[-1]
        retry_spend = ledger.calls[-1].billed_cost_microusd
        disposition = _retry_disposition(
            finalization.outcome,
            finalization.failure_code,
        )
        provider_error_diagnostic = result.provider_error_diagnostic
        structured_output_diagnostic = result.validation_diagnostic
    else:
        if result is not None or completed_at is not None or output is not None:
            raise ValueError("outstanding diagnostic retry has terminal data")
        retry_spend = 0
        disposition = None
        provider_error_diagnostic = None
        structured_output_diagnostic = None
    cumulative = plan.prior_capability_spend_microusd + retry_spend
    state = TogetherCapabilityDiagnosticRetryExecutionState(
        state_id=state_id,
        retry_plan_sha256=content_sha256(plan),
        source_proof_sha256=content_sha256(proof),
        authorization_bundle_sha256=content_sha256(authorization),
        source_state_sha256=content_sha256(source_state),
        provider_ledger=ledger,
        provider_journal=journal,
        retry_output=output,
        provider_error_diagnostic=provider_error_diagnostic,
        structured_output_diagnostic=structured_output_diagnostic,
        disposition=disposition,
        retry_provider_spend_microusd=retry_spend,
        cumulative_capability_spend_microusd=cumulative,
        remaining_capability_ceiling_microusd=max(
            0,
            plan.original_capability_max_spend_microusd - cumulative,
        ),
        manual_spend_ceiling_breached=(
            retry_spend > plan.retry_authorized_max_cost_microusd
            or cumulative > plan.original_capability_max_spend_microusd
        ),
        provider_budget_limit_breached=provider_budget_limits_exceeded(
            ledger,
            profile,
        ),
        completed_at=completed_at,
    )
    validate_capability_diagnostic_retry_execution_state(
        state,
        plan,
        proof,
        authorization,
        source_state,
        suite,
        profile,
    )
    return state


def execute_capability_diagnostic_retry(
    plan: TogetherCapabilityDiagnosticRetryPlan,
    proof: TogetherCapabilityDiagnosticRetrySourceProof,
    authorization: TogetherCapabilityDiagnosticRetryAuthorizationBundle,
    aggregation: Phase4CapabilityAggregation,
    delta: TogetherSelectorRecoveryDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_catalog: TogetherCatalogPreflightBundle,
    fresh_catalog: TogetherCatalogPreflightBundle,
    source_authorization: TogetherDeltaCandidateAuthorizationBundle,
    source_state: TogetherDeltaCandidateExecutionState,
    transport: ProviderTransport,
    *,
    state_id: str,
    clock: Callable[[], datetime],
    checkpoint: (
        Callable[[TogetherCapabilityDiagnosticRetryExecutionState], None] | None
    ) = None,
    prior_state: TogetherCapabilityDiagnosticRetryExecutionState | None = None,
) -> TogetherCapabilityDiagnosticRetryExecutionState:
    """Execute the exact retry once; every terminal outcome stops the slice."""

    validate_capability_diagnostic_retry_source_proof(proof, plan)
    _validate_plan_source_input_hashes(
        plan,
        aggregation,
        corrected_plan,
        suite,
        profile,
        readiness,
        source_catalog,
    )
    started_at = clock()
    validate_capability_diagnostic_retry_authorization_bundle(
        authorization,
        plan,
        proof,
        suite,
        profile,
        readiness,
        fresh_catalog,
        now=started_at,
    )
    _validate_private_source(
        aggregation,
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        source_authorization,
        source_state,
    )
    if prior_state is not None:
        validate_capability_diagnostic_retry_execution_state(
            prior_state,
            plan,
            proof,
            authorization,
            source_state,
            suite,
            profile,
        )
        return prior_state.model_copy(deep=True)
    source_binding = next(
        item
        for item in source_state.provider_journal.request_bindings
        if item.call_id == plan.source_call_id
    )
    entry = _qualification_entry(readiness, plan.source_call_id)
    rebuilt = rebuild_qualification_call(
        suite,
        profile,
        fixture,
        session,
        semantic_map,
        entry,
        created_at=source_binding.created_at,
    )
    request = _retry_request(rebuilt.request, plan, created_at=started_at)
    runtime = ProviderBudgetRuntime.resume(
        profile,
        source_state.provider_ledger,
        source_state.provider_journal,
        *_candidate_parts(suite),
    )
    try:
        result = runtime.execute(
            request,
            rebuilt.price_card,
            (
                None
                if request.response_validator is not None
                else rebuilt.response_adapter
            ),
            transport,
            segment=BudgetSegment.RETRY_RESERVE,
            retry_of_call_id=plan.source_call_id,
        )
    except Exception:
        if len(runtime.ledger_snapshot().authorizations) == (
            len(source_state.provider_ledger.authorizations) + 1
        ) and len(runtime.ledger_snapshot().calls) == len(
            source_state.provider_ledger.calls
        ):
            progressive = _build_capability_diagnostic_retry_execution_state(
                state_id=state_id,
                plan=plan,
                proof=proof,
                authorization=authorization,
                source_state=source_state,
                runtime=runtime,
                suite=suite,
                profile=profile,
                output=None,
                result=None,
                completed_at=None,
            )
            if checkpoint is not None:
                checkpoint(progressive)
        raise
    output = None
    if result.output is not None:
        payload: JsonValue = rebuilt.response_adapter.dump_python(
            result.output,
            mode="json",
        )
        output = TogetherCapabilityOutputRecord(
            call_id=plan.retry_call_id,
            candidate_id=plan.candidate_id,
            role=plan.role,
            output_sha256=content_sha256(payload),
            output_payload=payload,
        )
    state = _build_capability_diagnostic_retry_execution_state(
        state_id=state_id,
        plan=plan,
        proof=proof,
        authorization=authorization,
        source_state=source_state,
        runtime=runtime,
        suite=suite,
        profile=profile,
        output=output,
        result=result,
        completed_at=clock(),
    )
    if checkpoint is not None:
        checkpoint(state)
    return state


def capability_diagnostic_retry_summary(
    state: TogetherCapabilityDiagnosticRetryExecutionState,
) -> dict[str, JsonValue]:
    retry_finalized = (
        len(state.provider_ledger.authorizations)
        == len(state.provider_ledger.calls)
    )
    finalization = (
        state.provider_journal.finalizations[-1] if retry_finalized else None
    )
    diagnostic = state.provider_error_diagnostic
    return {
        "schema_version": state.schema_version,
        "state_sha256": content_sha256(state),
        "retry_call_count": state.retry_call_count,
        "retry_finalized": retry_finalized,
        "outstanding_authorization_preserved": not retry_finalized,
        "reconciliation_required_before_any_further_send": (
            not retry_finalized
        ),
        "provider_outcome": (
            finalization.outcome.value if finalization is not None else None
        ),
        "failure_code": (
            finalization.failure_code if finalization is not None else None
        ),
        "disposition": (
            state.disposition.value if state.disposition is not None else None
        ),
        "retry_provider_spend_microusd": state.retry_provider_spend_microusd,
        "cumulative_capability_spend_microusd": (
            state.cumulative_capability_spend_microusd
        ),
        "remaining_capability_ceiling_microusd": (
            state.remaining_capability_ceiling_microusd
        ),
        "provider_error_diagnostic_present": diagnostic is not None,
        "http_status_code": (
            diagnostic.http_status_code if diagnostic is not None else None
        ),
        "error_envelope_state": (
            diagnostic.envelope_state.value if diagnostic is not None else None
        ),
        "error_type": (
            diagnostic.error_type.value if diagnostic is not None else None
        ),
        "error_code": (
            diagnostic.error_code.value if diagnostic is not None else None
        ),
        "rejected_request_field": (
            diagnostic.rejected_request_field.value
            if diagnostic is not None
            else None
        ),
        "structured_output_diagnostic_present": (
            state.structured_output_diagnostic is not None
        ),
        "candidate_roster_changed": False,
        "model_capability_rejection_recorded": False,
        "model_selection_performed": False,
    }


def load_capability_diagnostic_retry_plan(
    path: str | Path,
) -> TogetherCapabilityDiagnosticRetryPlan:
    return TogetherCapabilityDiagnosticRetryPlan.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_diagnostic_retry_source_proof(
    path: str | Path,
) -> TogetherCapabilityDiagnosticRetrySourceProof:
    return TogetherCapabilityDiagnosticRetrySourceProof.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_diagnostic_retry_authorization_bundle(
    path: str | Path,
) -> TogetherCapabilityDiagnosticRetryAuthorizationBundle:
    return TogetherCapabilityDiagnosticRetryAuthorizationBundle.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_diagnostic_retry_execution_state(
    path: str | Path,
) -> TogetherCapabilityDiagnosticRetryExecutionState:
    return TogetherCapabilityDiagnosticRetryExecutionState.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
