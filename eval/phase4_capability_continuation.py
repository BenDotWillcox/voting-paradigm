"""Candidate-isolated continuation for the Phase 4E capability gate.

The original v1 capability plan remains an immutable audit artifact.  This
module binds its terminal attempts, records capability-level rejections, and
derives one independent five-role plan for every candidate that remains
eligible for capability testing.  It does not weaken the three-candidate
qualification contract or authorize qualification from a partial matrix.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
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
    TogetherCapabilityAuthorizationBundle,
    TogetherCapabilityCallPlan,
    TogetherCapabilityExecutionState,
    TogetherCapabilityOutputRecord,
    TogetherCapabilityPlan,
    validate_capability_execution_state,
    validate_capability_plan,
)
from .phase4_provider import (
    ProviderBudgetRuntime,
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderExecutionJournal,
    ProviderPriceCard,
    ProviderTransport,
    validate_provider_execution_journal,
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


PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]
CANDIDATE_CAPABILITY_CALL_COUNT = len(LLMRole)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class CapabilityAttemptFailureKind(str, Enum):
    TRANSIENT_PROVIDER_FAILURE = "transient_provider_failure"
    HARNESS_INCONCLUSIVE = "harness_inconclusive"
    CANDIDATE_CAPABILITY_FAILURE = "candidate_capability_failure"


TRANSIENT_CAPABILITY_OUTCOMES = {
    ProviderCallOutcome.PROVIDER_ERROR,
    ProviderCallOutcome.TRANSPORT_ERROR,
    ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
    ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
    ProviderCallOutcome.CANCELLED,
}


class TogetherCapabilityAttemptRecord(ContractModel):
    """Content-free binding to one preserved private v1 attempt."""

    record_version: Literal["phase4_capability_attempt_record.v1"] = (
        "phase4_capability_attempt_record.v1"
    )
    attempt_number: PositiveCount
    authorization_bundle_sha256: Sha256Digest
    state_sha256: Sha256Digest
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    provider_call_count: PositiveCount
    provider_spend_microusd: Microusd
    terminal_candidate_id: StableId
    terminal_role: LLMRole
    terminal_outcome: ProviderCallOutcome
    terminal_failure_code: StableId | None
    terminal_finalization_sha256: Sha256Digest
    started_at: datetime
    terminal_at: datetime
    failure_kind: CapabilityAttemptFailureKind
    candidate_rejected: bool
    same_candidate_retry_permitted: bool

    @field_validator("started_at", "terminal_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "capability attempt time")
        return value

    @model_validator(mode="after")
    def require_failure_disposition(self) -> Self:
        capability_failure = (
            self.failure_kind
            is CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE
        )
        if self.candidate_rejected != capability_failure:
            raise ValueError("capability rejection does not match failure kind")
        if self.same_candidate_retry_permitted == capability_failure:
            raise ValueError("capability retry policy does not match failure kind")
        if self.terminal_at < self.started_at:
            raise ValueError("capability attempt cannot finish before it starts")
        if self.terminal_outcome in TRANSIENT_CAPABILITY_OUTCOMES:
            required_tool_failure = self.terminal_failure_code == (
                "together_required_tool_call_missing"
            )
            expected = (
                CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE
                if required_tool_failure
                else CapabilityAttemptFailureKind.TRANSIENT_PROVIDER_FAILURE
            )
            if self.failure_kind is not expected:
                raise ValueError(
                    "provider or transport failure disposition is invalid"
                )
        elif self.terminal_outcome in {
            ProviderCallOutcome.INVALID_OUTPUT,
            ProviderCallOutcome.SUCCESS,
        }:
            if self.failure_kind not in {
                CapabilityAttemptFailureKind.HARNESS_INCONCLUSIVE,
                CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE,
            }:
                raise ValueError("model-output failure disposition is invalid")
        else:
            raise ValueError("capability attempt outcome cannot be classified")
        return self


class TogetherCandidateCapabilityPlan(ContractModel):
    """One candidate's exact five-role slice of the frozen v1 plan."""

    schema_version: Literal[
        "preference_eval_phase4_candidate_capability_plan.v1"
    ] = "preference_eval_phase4_candidate_capability_plan.v1"
    plan_id: StableId
    plan_version: PositiveVersion
    created_at: datetime
    source_capability_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_bundle_sha256: Sha256Digest
    qualification_manifest_sha256: Sha256Digest
    candidate_id: StableId
    calls: list[TogetherCapabilityCallPlan] = Field(
        min_length=CANDIDATE_CAPABILITY_CALL_COUNT,
        max_length=CANDIDATE_CAPABILITY_CALL_COUNT,
    )
    projected_cost_microusd: Microusd
    all_calls_authorized_max_cost_microusd: Microusd
    candidate_capability_max_spend_microusd: Microusd
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )
    manual_paid_authorization_required: Literal[True] = True
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "candidate capability plan created_at")
        return value

    @model_validator(mode="after")
    def require_exact_candidate_matrix_and_costs(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.calls):
            raise ValueError("candidate capability plan mixes candidates")
        roles = [item.role for item in self.calls]
        if set(roles) != set(LLMRole) or len(roles) != len(set(roles)):
            raise ValueError("candidate capability plan must cover every role once")
        if [item.ordinal for item in self.calls] != sorted(
            item.ordinal for item in self.calls
        ):
            raise ValueError("candidate capability calls must retain source order")
        if self.projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.calls
        ):
            raise ValueError("candidate capability projected cost does not reconcile")
        authorized = sum(
            item.authorized_max_cost_microusd for item in self.calls
        )
        if self.all_calls_authorized_max_cost_microusd != authorized:
            raise ValueError(
                "candidate capability authorization total does not reconcile"
            )
        if self.candidate_capability_max_spend_microusd != authorized:
            raise ValueError(
                "candidate capability spend ceiling must equal exact reservations"
            )
        return self


class TogetherCapabilityContinuationPlan(ContractModel):
    """Tracked, zero-spend decision after terminal v1 attempts."""

    schema_version: Literal[
        "preference_eval_phase4_capability_continuation.v1"
    ] = "preference_eval_phase4_capability_continuation.v1"
    continuation_id: StableId
    continuation_version: PositiveVersion
    created_at: datetime
    historical_capability_plan_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    attempts: list[TogetherCapabilityAttemptRecord] = Field(min_length=1)
    inconclusive_candidate_ids: list[StableId] = Field(min_length=1)
    rejected_candidate_ids: list[StableId] = Field(default_factory=list)
    candidate_plans: list[TogetherCandidateCapabilityPlan] = Field(min_length=1)
    prior_provider_spend_microusd: Microusd
    additional_projected_cost_microusd: Microusd
    additional_authorized_max_cost_microusd: Microusd
    original_capability_max_spend_microusd: Microusd
    cumulative_worst_case_spend_microusd: Microusd
    qualification_authorization_permitted: Literal[False] = False
    three_candidate_qualification_contract_unchanged: Literal[True] = True
    capability_failures_are_not_retried: Literal[True] = True
    independent_candidate_authorization_required: Literal[True] = True
    corrected_plan_must_differ_from_historical: Literal[True] = True
    all_candidate_round2_schema_failure_disposition: Literal[
        "shared_provider_schema_incompatibility_requires_versioned_schema_revision"
    ] = "shared_provider_schema_incompatibility_requires_versioned_schema_revision"
    provider_inference_calls_executed_by_plan_creation: Literal[0] = 0
    provider_spend_microusd_by_plan_creation: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "capability continuation created_at")
        return value

    @model_validator(mode="after")
    def require_partition_and_totals(self) -> Self:
        if (
            self.historical_capability_plan_sha256
            == self.corrected_capability_plan_sha256
        ):
            raise ValueError(
                "corrected capability plan must differ from historical plan"
            )
        attempt_numbers = [item.attempt_number for item in self.attempts]
        if attempt_numbers != list(range(1, len(self.attempts) + 1)):
            raise ValueError("capability attempt numbers must be contiguous")
        if len({item.state_sha256 for item in self.attempts}) != len(
            self.attempts
        ):
            raise ValueError("capability attempts must bind unique states")
        if any(
            later.started_at <= earlier.terminal_at
            for earlier, later in zip(self.attempts, self.attempts[1:])
        ):
            raise ValueError("capability attempts must retain chronological order")
        if self.created_at < self.attempts[-1].terminal_at:
            raise ValueError("continuation cannot predate its terminal attempts")
        rejected = sorted(
            {
                item.terminal_candidate_id
                for item in self.attempts
                if item.candidate_rejected
            }
        )
        if self.rejected_candidate_ids != rejected:
            raise ValueError("rejected candidates do not match attempt outcomes")
        inconclusive = sorted(
            {
                item.terminal_candidate_id
                for item in self.attempts
                if item.failure_kind
                is CapabilityAttemptFailureKind.HARNESS_INCONCLUSIVE
            }
        )
        if self.inconclusive_candidate_ids != inconclusive:
            raise ValueError("inconclusive candidates do not match attempts")
        plan_ids = [item.candidate_id for item in self.candidate_plans]
        if plan_ids != sorted(plan_ids) or len(plan_ids) != len(set(plan_ids)):
            raise ValueError("continuation candidate plans must be canonical")
        if set(plan_ids) & set(rejected):
            raise ValueError("rejected candidate cannot receive a continuation plan")
        if any(
            item.source_capability_plan_sha256
            != self.corrected_capability_plan_sha256
            for item in self.candidate_plans
        ):
            raise ValueError("candidate plans bind another corrected plan")
        if self.prior_provider_spend_microusd != sum(
            item.provider_spend_microusd for item in self.attempts
        ):
            raise ValueError("prior capability spend does not reconcile")
        if self.additional_projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.candidate_plans
        ):
            raise ValueError("continuation projected cost does not reconcile")
        if self.additional_authorized_max_cost_microusd != sum(
            item.all_calls_authorized_max_cost_microusd
            for item in self.candidate_plans
        ):
            raise ValueError("continuation authorization total does not reconcile")
        cumulative = (
            self.prior_provider_spend_microusd
            + self.additional_authorized_max_cost_microusd
        )
        if self.cumulative_worst_case_spend_microusd != cumulative:
            raise ValueError("continuation cumulative spend does not reconcile")
        if cumulative > self.original_capability_max_spend_microusd:
            raise ValueError("continuation exceeds original capability ceiling")
        return self


class TogetherCandidateCapabilityManualApproval(ContractModel):
    """Private approval for exactly one candidate plan."""

    record_version: Literal[
        "phase4_candidate_capability_approval.v1"
    ] = "phase4_candidate_capability_approval.v1"
    approval_id: StableId
    approval_version: PositiveVersion
    continuation_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    candidate_id: StableId
    approved_call_count: Literal[CANDIDATE_CAPABILITY_CALL_COUNT] = (
        CANDIDATE_CAPABILITY_CALL_COUNT
    )
    approved_max_spend_microusd: Microusd
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "candidate capability approval time")
        return value

    @model_validator(mode="after")
    def require_active_interval(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("candidate capability approval must expire later")
        return self


class TogetherCandidateCapabilityAuthorizationBundle(ContractModel):
    schema_version: Literal[
        "preference_eval_phase4_candidate_capability_authorization.v1"
    ] = "preference_eval_phase4_candidate_capability_authorization.v1"
    bundle_id: StableId
    bundle_version: PositiveVersion
    continuation_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    manual_approval: TogetherCandidateCapabilityManualApproval
    live_authorization: TogetherLiveAuthorization

    @model_validator(mode="after")
    def require_matching_approval(self) -> Self:
        if (
            self.manual_approval.continuation_plan_sha256,
            self.manual_approval.candidate_plan_sha256,
        ) != (self.continuation_plan_sha256, self.candidate_plan_sha256):
            raise ValueError("candidate capability approval hashes differ")
        if (
            self.live_authorization.stage
            is not TogetherPaidStage.CAPABILITY_PREFLIGHT
            or self.live_authorization.budget_segment
            is not BudgetSegment.QUALIFICATION
        ):
            raise ValueError("candidate capability authorization uses wrong stage")
        if (
            self.live_authorization.approved_at
            != self.manual_approval.approved_at
            or self.live_authorization.expires_at
            != self.manual_approval.expires_at
        ):
            raise ValueError("candidate capability authorization windows differ")
        return self


class TogetherCandidateCapabilityReceipt(ContractModel):
    """Content-free approval of one candidate's complete role matrix."""

    record_version: Literal[
        "phase4_candidate_capability_receipt.v1"
    ] = "phase4_candidate_capability_receipt.v1"
    receipt_id: StableId
    receipt_version: PositiveVersion
    continuation_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    candidate_id: StableId
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    completed_at: datetime
    checks: list[TogetherCapabilityProbeCheck] = Field(
        min_length=CANDIDATE_CAPABILITY_CALL_COUNT,
        max_length=CANDIDATE_CAPABILITY_CALL_COUNT,
    )
    provider_spend_microusd: Microusd

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        _require_aware(value, "candidate capability receipt completed_at")
        return value

    @model_validator(mode="after")
    def require_exact_role_matrix(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.checks):
            raise ValueError("candidate capability receipt mixes candidates")
        roles = [item.role for item in self.checks]
        if set(roles) != set(LLMRole) or len(roles) != len(set(roles)):
            raise ValueError("candidate capability receipt must cover every role")
        return self


class TogetherCandidateCapabilityExecutionState(ContractModel):
    """Private progressive state for one candidate-isolated attempt."""

    schema_version: Literal[
        "preference_eval_phase4_candidate_capability_state.v1"
    ] = "preference_eval_phase4_candidate_capability_state.v1"
    state_id: StableId
    state_version: PositiveVersion
    continuation_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    outputs: list[TogetherCapabilityOutputRecord]
    receipt: TogetherCandidateCapabilityReceipt | None = None

    @model_validator(mode="after")
    def require_unique_outputs(self) -> Self:
        call_ids = [item.call_id for item in self.outputs]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("candidate capability outputs must be unique")
        return self


def _candidate_parts(
    suite: Phase4TogetherSuite,
) -> tuple[list[OpenWeightModelCandidate], list[ProviderPriceCard]]:
    return (
        [item.candidate for item in suite.candidates],
        [item.price_card for item in suite.candidates],
    )


def _call_passed(
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


def _attempt_record(
    attempt_number: int,
    source_plan: TogetherCapabilityPlan,
    authorization: TogetherCapabilityAuthorizationBundle,
    state: TogetherCapabilityExecutionState,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> TogetherCapabilityAttemptRecord:
    validate_capability_execution_state(
        state,
        source_plan,
        authorization,
        suite,
        profile,
    )
    if state.receipt is not None or not state.provider_journal.finalizations:
        raise ValueError("continuation attempt must end in a capability failure")
    finalization = state.provider_journal.finalizations[-1]
    started_at = state.provider_journal.request_bindings[0].created_at
    if not (
        authorization.manual_approval.approved_at
        <= started_at
        <= authorization.manual_approval.expires_at
    ):
        raise ValueError("capability attempt started outside its approval window")
    bindings = {
        item.call_id: item for item in state.provider_journal.request_bindings
    }
    binding = bindings[finalization.call_id]
    calls = {item.call_id: item for item in source_plan.calls}
    call = calls[finalization.call_id]
    if _call_passed(call, finalization):
        raise ValueError("continuation attempt does not end in a failed gate")
    if (
        suite.suite_version >= 3
        and binding.role is LLMRole.INTERVIEWER
        and finalization.failure_code
        == "together_required_tool_call_missing"
    ):
        failure_kind = CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE
    elif finalization.outcome in TRANSIENT_CAPABILITY_OUTCOMES:
        failure_kind = CapabilityAttemptFailureKind.TRANSIENT_PROVIDER_FAILURE
    elif finalization.outcome in {
        ProviderCallOutcome.INVALID_OUTPUT,
        ProviderCallOutcome.SUCCESS,
    }:
        failure_kind = (
            CapabilityAttemptFailureKind.HARNESS_INCONCLUSIVE
            if suite.suite_version < 3 and binding.role is LLMRole.INTERVIEWER
            else CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE
        )
    else:
        raise ValueError("terminal capability outcome cannot be classified")
    rejected = (
        failure_kind is CapabilityAttemptFailureKind.CANDIDATE_CAPABILITY_FAILURE
    )
    return TogetherCapabilityAttemptRecord(
        attempt_number=attempt_number,
        authorization_bundle_sha256=content_sha256(authorization),
        state_sha256=content_sha256(state),
        provider_ledger_sha256=content_sha256(state.provider_ledger),
        provider_journal_sha256=content_sha256(state.provider_journal),
        provider_call_count=len(state.provider_ledger.calls),
        provider_spend_microusd=sum(
            item.billed_cost_microusd for item in state.provider_ledger.calls
        ),
        terminal_candidate_id=binding.model_candidate_id,
        terminal_role=binding.role,
        terminal_outcome=finalization.outcome,
        terminal_failure_code=finalization.failure_code,
        terminal_finalization_sha256=content_sha256(finalization),
        started_at=started_at,
        terminal_at=finalization.created_at,
        failure_kind=failure_kind,
        candidate_rejected=rejected,
        same_candidate_retry_permitted=not rejected,
    )


def _candidate_plan(
    source_plan: TogetherCapabilityPlan,
    candidate_id: str,
    *,
    created_at: datetime,
    continuation_version: int,
) -> TogetherCandidateCapabilityPlan:
    calls = [
        item.model_copy(deep=True)
        for item in source_plan.calls
        if item.candidate_id == candidate_id
    ]
    if len(calls) != CANDIDATE_CAPABILITY_CALL_COUNT:
        raise ValueError("source plan lacks a complete candidate role matrix")
    return TogetherCandidateCapabilityPlan(
        plan_id=f"phase4_candidate_capability_{candidate_id}_v{continuation_version}",
        plan_version=continuation_version,
        created_at=created_at,
        source_capability_plan_sha256=content_sha256(source_plan),
        together_suite_sha256=source_plan.together_suite_sha256,
        robustness_profile_sha256=source_plan.robustness_profile_sha256,
        readiness_bundle_sha256=source_plan.readiness_bundle_sha256,
        qualification_manifest_sha256=(
            source_plan.qualification_manifest_sha256
        ),
        candidate_id=candidate_id,
        calls=calls,
        projected_cost_microusd=sum(
            item.projected_cost_microusd for item in calls
        ),
        all_calls_authorized_max_cost_microusd=sum(
            item.authorized_max_cost_microusd for item in calls
        ),
        candidate_capability_max_spend_microusd=sum(
            item.authorized_max_cost_microusd for item in calls
        ),
    )


def build_capability_continuation_plan(
    historical_plan: TogetherCapabilityPlan,
    corrected_plan: TogetherCapabilityPlan,
    source_attempts: Sequence[
        tuple[TogetherCapabilityAuthorizationBundle, TogetherCapabilityExecutionState]
    ],
    historical_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    *,
    continuation_id: str,
    continuation_version: int,
    created_at: datetime,
) -> TogetherCapabilityContinuationPlan:
    records = [
        _attempt_record(
            number,
            historical_plan,
            authorization,
            state,
            historical_suite,
            profile,
        )
        for number, (authorization, state) in enumerate(source_attempts, start=1)
    ]
    rejected = sorted(
        {
            item.terminal_candidate_id
            for item in records
            if item.candidate_rejected
        }
    )
    for candidate_id in rejected:
        rejection_index = next(
            index
            for index, item in enumerate(records)
            if item.terminal_candidate_id == candidate_id
            and item.candidate_rejected
        )
        if any(
            later.terminal_candidate_id == candidate_id
            for later in records[rejection_index + 1 :]
        ):
            raise ValueError("capability failure cannot be followed by another retry")
    source_candidate_ids = sorted(
        {item.candidate_id for item in corrected_plan.calls}
    )
    remaining = [
        candidate_id
        for candidate_id in source_candidate_ids
        if candidate_id not in rejected
    ]
    candidate_plans = [
        _candidate_plan(
            corrected_plan,
            candidate_id,
            created_at=created_at,
            continuation_version=continuation_version,
        )
        for candidate_id in remaining
    ]
    return TogetherCapabilityContinuationPlan(
        continuation_id=continuation_id,
        continuation_version=continuation_version,
        created_at=created_at,
        historical_capability_plan_sha256=content_sha256(historical_plan),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        attempts=records,
        inconclusive_candidate_ids=sorted(
            {
                item.terminal_candidate_id
                for item in records
                if item.failure_kind
                is CapabilityAttemptFailureKind.HARNESS_INCONCLUSIVE
            }
        ),
        rejected_candidate_ids=rejected,
        candidate_plans=candidate_plans,
        prior_provider_spend_microusd=sum(
            item.provider_spend_microusd for item in records
        ),
        additional_projected_cost_microusd=sum(
            item.projected_cost_microusd for item in candidate_plans
        ),
        additional_authorized_max_cost_microusd=sum(
            item.all_calls_authorized_max_cost_microusd
            for item in candidate_plans
        ),
        original_capability_max_spend_microusd=(
            corrected_plan.capability_max_spend_microusd
        ),
        cumulative_worst_case_spend_microusd=(
            sum(item.provider_spend_microusd for item in records)
            + sum(
                item.all_calls_authorized_max_cost_microusd
                for item in candidate_plans
            )
        ),
    )


def validate_capability_continuation_plan(
    continuation: TogetherCapabilityContinuationPlan,
    historical_plan: TogetherCapabilityPlan,
    corrected_plan: TogetherCapabilityPlan,
    source_attempts: Sequence[
        tuple[TogetherCapabilityAuthorizationBundle, TogetherCapabilityExecutionState]
    ],
    historical_suite: Phase4TogetherSuite,
    corrected_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    historical_readiness: Phase4TogetherReadinessBundle,
    corrected_readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    validate_capability_plan(
        historical_plan,
        historical_suite,
        profile,
        historical_readiness,
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
    rebuilt = build_capability_continuation_plan(
        historical_plan,
        corrected_plan,
        source_attempts,
        historical_suite,
        profile,
        continuation_id=continuation.continuation_id,
        continuation_version=continuation.continuation_version,
        created_at=continuation.created_at,
    )
    if continuation != rebuilt:
        raise ValueError("capability continuation does not rebuild from attempts")
    source_candidates = {item.candidate_id for item in corrected_plan.calls}
    partition = set(continuation.rejected_candidate_ids) | {
        item.candidate_id for item in continuation.candidate_plans
    }
    if partition != source_candidates:
        raise ValueError("capability continuation does not partition candidates")


def candidate_plan_for(
    continuation: TogetherCapabilityContinuationPlan,
    candidate_id: str,
) -> TogetherCandidateCapabilityPlan:
    matches = [
        item for item in continuation.candidate_plans
        if item.candidate_id == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate is not eligible for capability continuation")
    return matches[0].model_copy(deep=True)


def build_candidate_capability_authorization_bundle(
    continuation: TogetherCapabilityContinuationPlan,
    candidate_plan: TogetherCandidateCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TogetherCandidateCapabilityAuthorizationBundle:
    if candidate_plan != candidate_plan_for(
        continuation, candidate_plan.candidate_id
    ):
        raise ValueError("candidate plan differs from continuation")
    manual = TogetherCandidateCapabilityManualApproval(
        approval_id=approval_id,
        approval_version=1,
        continuation_plan_sha256=content_sha256(continuation),
        candidate_plan_sha256=content_sha256(candidate_plan),
        candidate_id=candidate_plan.candidate_id,
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
    bundle = TogetherCandidateCapabilityAuthorizationBundle(
        bundle_id=bundle_id,
        bundle_version=1,
        continuation_plan_sha256=content_sha256(continuation),
        candidate_plan_sha256=content_sha256(candidate_plan),
        catalog_preflight_bundle_sha256=content_sha256(catalog_bundle),
        manual_approval=manual,
        live_authorization=live,
    )
    validate_candidate_capability_authorization_bundle(
        bundle,
        continuation,
        candidate_plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        now=approved_at,
    )
    return bundle


def validate_candidate_capability_authorization_bundle(
    bundle: TogetherCandidateCapabilityAuthorizationBundle,
    continuation: TogetherCapabilityContinuationPlan,
    candidate_plan: TogetherCandidateCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    now: datetime,
) -> None:
    if (
        bundle.continuation_plan_sha256,
        bundle.candidate_plan_sha256,
        bundle.catalog_preflight_bundle_sha256,
    ) != (
        content_sha256(continuation),
        content_sha256(candidate_plan),
        content_sha256(catalog_bundle),
    ):
        raise ValueError("candidate capability authorization hashes differ")
    if candidate_plan != candidate_plan_for(
        continuation, candidate_plan.candidate_id
    ):
        raise ValueError("candidate capability plan is not continuation-eligible")
    if (
        bundle.manual_approval.candidate_id != candidate_plan.candidate_id
        or bundle.manual_approval.approved_max_spend_microusd
        != candidate_plan.candidate_capability_max_spend_microusd
    ):
        raise ValueError("candidate capability manual approval differs from plan")
    if not (
        bundle.manual_approval.approved_at
        <= now
        <= bundle.manual_approval.expires_at
    ):
        raise ValueError("candidate capability manual approval is not active")
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
        raise ValueError("candidate capability live authorization is not isolated")


def _build_candidate_receipt(
    continuation: TogetherCapabilityContinuationPlan,
    plan: TogetherCandidateCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    outputs: list[TogetherCapabilityOutputRecord],
    *,
    receipt_id: str,
    completed_at: datetime,
) -> TogetherCandidateCapabilityReceipt:
    candidates, price_cards = _candidate_parts(suite)
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
        raise ValueError("candidate capability audit must cover exact plan")
    if completed_at < max(item.created_at for item in finalizations.values()):
        raise ValueError("candidate receipt cannot predate provider completion")
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
            raise ValueError("candidate capability finalization binding differs")
        if not _call_passed(call, finalization) or (
            finalization.response_sha256 != output.output_sha256
        ):
            raise ValueError("candidate capability probe did not succeed")
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
        raise ValueError("candidate capability spend exceeds manual ceiling")
    return TogetherCandidateCapabilityReceipt(
        receipt_id=receipt_id,
        receipt_version=1,
        continuation_plan_sha256=content_sha256(continuation),
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


def validate_candidate_capability_execution_state(
    state: TogetherCandidateCapabilityExecutionState,
    continuation: TogetherCapabilityContinuationPlan,
    plan: TogetherCandidateCapabilityPlan,
    authorization: TogetherCandidateCapabilityAuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    if (
        state.continuation_plan_sha256,
        state.candidate_plan_sha256,
        state.authorization_bundle_sha256,
    ) != (
        content_sha256(continuation),
        content_sha256(plan),
        content_sha256(authorization),
    ):
        raise ValueError("candidate capability state bindings differ")
    candidates, price_cards = _candidate_parts(suite)
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
        raise ValueError("candidate capability state is not an exact plan prefix")
    finalization_ids = [
        item.call_id for item in state.provider_journal.finalizations
    ]
    if finalization_ids != authorization_ids[: len(finalization_ids)]:
        raise ValueError("candidate capability finalizations are not a prefix")
    if len(authorization_ids) - len(finalization_ids) > 1:
        raise ValueError("candidate capability may retain one outstanding call")
    if any(
        not _call_passed(plan.calls[index], finalization)
        for index, finalization in enumerate(
            state.provider_journal.finalizations[:-1]
        )
    ):
        raise ValueError("candidate capability failure must terminate its attempt")
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
        raise ValueError("candidate capability outputs must cover successful calls")
    finalizations = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    for output in state.outputs:
        if finalizations[output.call_id].response_sha256 != output.output_sha256:
            raise ValueError("candidate capability output differs from audit")
    if sum(
        item.billed_cost_microusd for item in state.provider_ledger.calls
    ) > plan.candidate_capability_max_spend_microusd:
        raise ValueError("candidate capability state exceeds manual ceiling")
    if state.receipt is not None:
        rebuilt = _build_candidate_receipt(
            continuation,
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
            raise ValueError("candidate capability receipt does not rebuild")


def _execution_state(
    *,
    state_id: str,
    continuation: TogetherCapabilityContinuationPlan,
    plan: TogetherCandidateCapabilityPlan,
    authorization: TogetherCandidateCapabilityAuthorizationBundle,
    runtime: ProviderBudgetRuntime,
    outputs: list[TogetherCapabilityOutputRecord],
    receipt: TogetherCandidateCapabilityReceipt | None,
) -> TogetherCandidateCapabilityExecutionState:
    return TogetherCandidateCapabilityExecutionState(
        state_id=state_id,
        state_version=1,
        continuation_plan_sha256=content_sha256(continuation),
        candidate_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        provider_ledger=runtime.ledger_snapshot(),
        provider_journal=runtime.journal_snapshot(),
        outputs=outputs,
        receipt=receipt,
    )


def execute_candidate_capability_preflight(
    continuation: TogetherCapabilityContinuationPlan,
    historical_plan: TogetherCapabilityPlan,
    corrected_plan: TogetherCapabilityPlan,
    source_attempts: Sequence[
        tuple[TogetherCapabilityAuthorizationBundle, TogetherCapabilityExecutionState]
    ],
    historical_suite: Phase4TogetherSuite,
    historical_readiness: Phase4TogetherReadinessBundle,
    plan: TogetherCandidateCapabilityPlan,
    authorization: TogetherCandidateCapabilityAuthorizationBundle,
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
    prior_state: TogetherCandidateCapabilityExecutionState | None = None,
    checkpoint: (
        Callable[[TogetherCandidateCapabilityExecutionState], None] | None
    ) = None,
) -> TogetherCandidateCapabilityExecutionState:
    """Execute one exact five-role plan and stop at that candidate's failure."""

    started_at = clock()
    validate_capability_continuation_plan(
        continuation,
        historical_plan,
        corrected_plan,
        source_attempts,
        historical_suite,
        suite,
        profile,
        historical_readiness,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    validate_candidate_capability_authorization_bundle(
        authorization,
        continuation,
        plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        now=started_at,
    )
    entries_by_id: dict[str, QualificationCallPlanEntry] = {
        item.coordinate.call_id: item
        for item in readiness.qualification_manifest.entries
    }
    for call in plan.calls:
        entry = entries_by_id.get(call.call_id)
        if entry is None or content_sha256(entry) != call.qualification_entry_sha256:
            raise ValueError("candidate capability execution entry differs")
    if prior_state is None:
        runtime = ProviderBudgetRuntime(
            profile,
            ledger_id=ledger_id,
            journal_id=journal_id,
        )
        outputs: list[TogetherCapabilityOutputRecord] = []
    else:
        validate_candidate_capability_execution_state(
            prior_state,
            continuation,
            plan,
            authorization,
            suite,
            profile,
        )
        if prior_state.receipt is not None:
            return prior_state.model_copy(deep=True)
        runtime = ProviderBudgetRuntime.resume(
            profile,
            prior_state.provider_ledger,
            prior_state.provider_journal,
            *_candidate_parts(suite),
        )
        outputs = [item.model_copy(deep=True) for item in prior_state.outputs]
        if prior_state.provider_journal.finalizations:
            last_index = len(prior_state.provider_journal.finalizations) - 1
            if not _call_passed(
                plan.calls[last_index],
                prior_state.provider_journal.finalizations[-1],
            ):
                raise ValueError("failed candidate capability attempt is terminal")
    ledger = runtime.ledger_snapshot()
    if len(ledger.authorizations) != len(ledger.calls):
        raise ValueError("candidate capability has an outstanding call")
    completed_count = len(ledger.calls)

    def checkpoint_progress() -> None:
        progressive = _execution_state(
            state_id=state_id,
            continuation=continuation,
            plan=plan,
            authorization=authorization,
            runtime=runtime,
            outputs=outputs,
            receipt=None,
        )
        validate_candidate_capability_execution_state(
            progressive,
            continuation,
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
            raise ValueError("next candidate call exceeds manual spend ceiling")
        entry = entries_by_id[call.call_id]
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=clock(),
        )
        try:
            result = runtime.execute(
                rebuilt.request,
                rebuilt.price_card,
                rebuilt.response_adapter,
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
        if result.finalization.outcome is not ProviderCallOutcome.SUCCESS:
            raise ValueError("candidate capability provider call did not succeed")
        if not _call_passed(call, result.finalization):
            raise ValueError("candidate interviewer probe did not call a tool")
    receipt = _build_candidate_receipt(
        continuation,
        plan,
        suite,
        profile,
        runtime.ledger_snapshot(),
        runtime.journal_snapshot(),
        outputs,
        receipt_id=f"{state_id}_receipt",
        completed_at=clock(),
    )
    complete = _execution_state(
        state_id=state_id,
        continuation=continuation,
        plan=plan,
        authorization=authorization,
        runtime=runtime,
        outputs=outputs,
        receipt=receipt,
    )
    validate_candidate_capability_execution_state(
        complete,
        continuation,
        plan,
        authorization,
        suite,
        profile,
    )
    if checkpoint is not None:
        checkpoint(complete)
    return complete


def capability_continuation_summary(
    continuation: TogetherCapabilityContinuationPlan,
) -> dict[str, JsonValue]:
    return {
        "schema_version": continuation.schema_version,
        "continuation_id": continuation.continuation_id,
        "continuation_version": continuation.continuation_version,
        "continuation_sha256": content_sha256(continuation),
        "attempt_count": len(continuation.attempts),
        "inconclusive_candidate_count": len(
            continuation.inconclusive_candidate_ids
        ),
        "rejected_candidate_count": len(continuation.rejected_candidate_ids),
        "remaining_candidate_count": len(continuation.candidate_plans),
        "remaining_call_count": sum(
            len(item.calls) for item in continuation.candidate_plans
        ),
        "prior_provider_spend_microusd": (
            continuation.prior_provider_spend_microusd
        ),
        "additional_projected_cost_microusd": (
            continuation.additional_projected_cost_microusd
        ),
        "additional_authorized_max_cost_microusd": (
            continuation.additional_authorized_max_cost_microusd
        ),
        "cumulative_worst_case_spend_microusd": (
            continuation.cumulative_worst_case_spend_microusd
        ),
        "qualification_authorization_permitted": (
            continuation.qualification_authorization_permitted
        ),
        "provider_inference_calls_executed_by_plan_creation": 0,
        "provider_spend_microusd_by_plan_creation": 0,
    }


def candidate_capability_state_summary(
    state: TogetherCandidateCapabilityExecutionState,
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
        "candidate_approved": state.receipt is not None,
    }


def load_capability_source_attempts(
    paths: Sequence[tuple[Path, Path]],
) -> list[
    tuple[TogetherCapabilityAuthorizationBundle, TogetherCapabilityExecutionState]
]:
    return [
        (
            TogetherCapabilityAuthorizationBundle.model_validate_json(
                authorization.read_text(encoding="utf-8")
            ),
            TogetherCapabilityExecutionState.model_validate_json(
                state.read_text(encoding="utf-8")
            ),
        )
        for authorization, state in paths
    ]
