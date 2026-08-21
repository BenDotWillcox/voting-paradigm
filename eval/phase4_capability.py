"""Exact, resumable Together capability preflight for Phase 4E.

The tracked plan is a zero-spend artifact.  Paid execution remains impossible
without a separate private manual-approval bundle and an injected authorized
transport.  Provider-visible requests and parsed outputs stay outside the
tracked plan; the durable execution state lives under ``eval/private_runs``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
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
from .phase4_interviewer import (
    ReadCandidateQuestionScoresRequest,
    ReadCandidateQuestionScoresResult,
    ReadEvidenceConflictsRequest,
    ReadEvidenceConflictsResult,
    ReadEvidenceCoverageRequest,
    ReadEvidenceCoverageResult,
    ReadPosteriorUncertaintyRequest,
    ReadPosteriorUncertaintyResult,
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
    validate_readiness_bundle,
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
    TogetherCapabilityPreflightReceipt,
    TogetherCapabilityProbeCheck,
    TogetherCatalogPreflightBundle,
    TogetherLiveAuthorization,
    TogetherPaidStage,
    validate_live_authorization,
)
from .prequential import PrequentialSessionScript


NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]
CAPABILITY_MAX_SPEND_MICROUSD = 150_000
CAPABILITY_CALL_COUNT = 15


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class CapabilityInterviewerTools:
    """Deterministic public-development tool surface for capability probes."""

    def __init__(self, item_ids: list[str]) -> None:
        if len(item_ids) < 2 or len(item_ids) != len(set(item_ids)):
            raise ValueError("capability tools require unique ontology items")
        self._item_ids = set(item_ids)

    def read_posterior_uncertainty(
        self,
        request: ReadPosteriorUncertaintyRequest,
    ) -> ReadPosteriorUncertaintyResult:
        if not {request.pair.item_a, request.pair.item_b} <= self._item_ids:
            raise ValueError("capability uncertainty pair is outside ontology")
        return ReadPosteriorUncertaintyResult(
            pair=request.pair,
            posterior_gap_std=1.0,
            model_version="capability_preflight_v1",
        )

    def read_candidate_question_scores(
        self,
        request: ReadCandidateQuestionScoresRequest,
    ) -> ReadCandidateQuestionScoresResult:
        del request
        return ReadCandidateQuestionScoresResult(
            candidates=[],
            model_version="capability_preflight_v1",
        )

    def read_evidence_coverage(
        self,
        request: ReadEvidenceCoverageRequest,
    ) -> ReadEvidenceCoverageResult:
        del request
        item_count = len(self._item_ids)
        return ReadEvidenceCoverageResult(
            evidence_count=0,
            item_count=item_count,
            observed_item_count=0,
            possible_pair_count=item_count * (item_count - 1) // 2,
            observed_pair_count=0,
            domains=[],
        )

    def read_evidence_conflicts(
        self,
        request: ReadEvidenceConflictsRequest,
    ) -> ReadEvidenceConflictsResult:
        del request
        return ReadEvidenceConflictsResult(conflicts=[])


class TogetherCapabilityCallPlan(ContractModel):
    record_version: Literal["phase4_together_capability_call_plan.v1"] = (
        "phase4_together_capability_call_plan.v1"
    )
    ordinal: PositiveCount
    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    qualification_entry_sha256: Sha256Digest
    request_template_sha256: Sha256Digest
    projected_cost_microusd: Microusd
    authorized_max_cost_microusd: Microusd
    actual_tool_call_required: bool

    @model_validator(mode="after")
    def require_interviewer_tool_probe_only(self) -> Self:
        if self.actual_tool_call_required != (self.role is LLMRole.INTERVIEWER):
            raise ValueError("only interviewer capability calls require a tool")
        return self


class TogetherCapabilityPlan(ContractModel):
    """Tracked zero-spend plan for the exact first 15 qualification calls."""

    schema_version: Literal["preference_eval_phase4_capability_plan.v1"] = (
        "preference_eval_phase4_capability_plan.v1"
    )
    plan_id: StableId
    plan_version: PositiveVersion
    created_at: datetime
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_bundle_sha256: Sha256Digest
    qualification_manifest_sha256: Sha256Digest
    calls: list[TogetherCapabilityCallPlan] = Field(
        min_length=CAPABILITY_CALL_COUNT,
        max_length=CAPABILITY_CALL_COUNT,
    )
    projected_cost_microusd: Microusd
    all_calls_authorized_max_cost_microusd: Microusd
    capability_max_spend_microusd: Literal[150_000] = (
        CAPABILITY_MAX_SPEND_MICROUSD
    )
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )
    manual_paid_authorization_required: Literal[True] = True
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "capability plan created_at")
        return value

    @model_validator(mode="after")
    def require_complete_matrix_and_costs(self) -> Self:
        ordinals = [item.ordinal for item in self.calls]
        if ordinals != list(range(1, CAPABILITY_CALL_COUNT + 1)):
            raise ValueError("capability plan ordinals must be contiguous")
        call_ids = [item.call_id for item in self.calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("capability plan call ids must be unique")
        matrix = {(item.candidate_id, item.role) for item in self.calls}
        candidate_ids = {item.candidate_id for item in self.calls}
        expected = {
            (candidate_id, role)
            for candidate_id in candidate_ids
            for role in LLMRole
        }
        if len(candidate_ids) != 3 or matrix != expected:
            raise ValueError("capability plan must cover three candidates and roles")
        if self.projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.calls
        ):
            raise ValueError("capability projected cost does not reconcile")
        if self.all_calls_authorized_max_cost_microusd != sum(
            item.authorized_max_cost_microusd for item in self.calls
        ):
            raise ValueError("capability authorization total does not reconcile")
        if (
            self.all_calls_authorized_max_cost_microusd
            > self.capability_max_spend_microusd
        ):
            raise ValueError("capability plan cannot fit its manual spend ceiling")
        return self


class TogetherCapabilityManualApproval(ContractModel):
    """Private explicit approval required before any capability provider call."""

    record_version: Literal["phase4_together_capability_approval.v1"] = (
        "phase4_together_capability_approval.v1"
    )
    approval_id: StableId
    approval_version: PositiveVersion
    capability_plan_sha256: Sha256Digest
    approved_call_count: Literal[15] = CAPABILITY_CALL_COUNT
    approved_max_spend_microusd: Literal[150_000] = (
        CAPABILITY_MAX_SPEND_MICROUSD
    )
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "capability approval time")
        return value

    @model_validator(mode="after")
    def require_active_interval(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("capability approval must expire later")
        return self


class TogetherCapabilityAuthorizationBundle(ContractModel):
    schema_version: Literal[
        "preference_eval_phase4_capability_authorization.v1"
    ] = "preference_eval_phase4_capability_authorization.v1"
    bundle_id: StableId
    bundle_version: PositiveVersion
    capability_plan_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    manual_approval: TogetherCapabilityManualApproval
    live_authorization: TogetherLiveAuthorization

    @model_validator(mode="after")
    def require_matching_approval_window(self) -> Self:
        if self.manual_approval.capability_plan_sha256 != (
            self.capability_plan_sha256
        ):
            raise ValueError("capability authorization plan hash differs")
        if (
            self.live_authorization.stage
            is not TogetherPaidStage.CAPABILITY_PREFLIGHT
            or self.live_authorization.budget_segment
            is not BudgetSegment.QUALIFICATION
        ):
            raise ValueError("capability authorization uses the wrong stage")
        if (
            self.live_authorization.approved_at
            != self.manual_approval.approved_at
            or self.live_authorization.expires_at
            != self.manual_approval.expires_at
        ):
            raise ValueError("capability authorization windows differ")
        return self


class TogetherCapabilityOutputRecord(ContractModel):
    """Private parsed output retained so capability calls can be reused."""

    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    output_sha256: Sha256Digest
    output_payload: JsonValue

    @model_validator(mode="after")
    def bind_output_payload(self) -> Self:
        if self.output_sha256 != content_sha256(self.output_payload):
            raise ValueError("capability output hash does not match payload")
        return self


class TogetherCapabilityExecutionState(ContractModel):
    """Private progressive state checkpointed after every provider attempt."""

    schema_version: Literal["preference_eval_phase4_capability_state.v1"] = (
        "preference_eval_phase4_capability_state.v1"
    )
    state_id: StableId
    state_version: PositiveVersion
    capability_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    outputs: list[TogetherCapabilityOutputRecord]
    receipt: TogetherCapabilityPreflightReceipt | None = None

    @model_validator(mode="after")
    def require_unique_outputs(self) -> Self:
        call_ids = [item.call_id for item in self.outputs]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("capability outputs must have unique call ids")
        return self


def _call_plan(
    entry: QualificationCallPlanEntry,
    ordinal: int,
) -> TogetherCapabilityCallPlan:
    return TogetherCapabilityCallPlan(
        ordinal=ordinal,
        call_id=entry.coordinate.call_id,
        candidate_id=entry.coordinate.candidate_id,
        role=entry.coordinate.role,
        qualification_entry_sha256=content_sha256(entry),
        request_template_sha256=entry.request_template_sha256,
        projected_cost_microusd=entry.projected_cost_microusd,
        authorized_max_cost_microusd=entry.authorized_max_cost_microusd,
        actual_tool_call_required=(
            entry.coordinate.role is LLMRole.INTERVIEWER
        ),
    )


def build_capability_plan(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    *,
    plan_id: str,
    plan_version: int,
    created_at: datetime,
) -> TogetherCapabilityPlan:
    entries = readiness.qualification_manifest.entries[:CAPABILITY_CALL_COUNT]
    if readiness.capability_preflight_call_ids != [
        item.coordinate.call_id for item in entries
    ]:
        raise ValueError("readiness capability prefix differs")
    calls = [
        _call_plan(entry, ordinal)
        for ordinal, entry in enumerate(entries, start=1)
    ]
    return TogetherCapabilityPlan(
        plan_id=plan_id,
        plan_version=plan_version,
        created_at=created_at,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        readiness_bundle_sha256=content_sha256(readiness),
        qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        calls=calls,
        projected_cost_microusd=sum(
            item.projected_cost_microusd for item in calls
        ),
        all_calls_authorized_max_cost_microusd=sum(
            item.authorized_max_cost_microusd for item in calls
        ),
    )


def validate_capability_plan(
    plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    validate_readiness_bundle(
        readiness,
        suite,
        profile,
        fixture,
        session,
        semantic_map,
    )
    rebuilt = build_capability_plan(
        suite,
        profile,
        readiness,
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        created_at=plan.created_at,
    )
    if plan != rebuilt:
        raise ValueError("capability plan does not rebuild from readiness")


def build_capability_authorization_bundle(
    plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TogetherCapabilityAuthorizationBundle:
    manual = TogetherCapabilityManualApproval(
        approval_id=approval_id,
        approval_version=1,
        capability_plan_sha256=content_sha256(plan),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    authorization = TogetherLiveAuthorization(
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
        authorized_candidate_ids=sorted(
            item.candidate.candidate_id for item in suite.candidates
        ),
        authorized_roles=sorted(LLMRole, key=lambda item: item.value),
        approved_max_spend_microusd=(
            profile.budget_policy.segment_caps_microusd[
                BudgetSegment.QUALIFICATION
            ]
        ),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    bundle = TogetherCapabilityAuthorizationBundle(
        bundle_id=bundle_id,
        bundle_version=1,
        capability_plan_sha256=content_sha256(plan),
        catalog_preflight_bundle_sha256=content_sha256(catalog_bundle),
        manual_approval=manual,
        live_authorization=authorization,
    )
    validate_capability_authorization_bundle(
        bundle,
        plan,
        suite,
        profile,
        readiness,
        catalog_bundle,
        now=approved_at,
    )
    return bundle


def validate_capability_authorization_bundle(
    bundle: TogetherCapabilityAuthorizationBundle,
    plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog_bundle: TogetherCatalogPreflightBundle,
    *,
    now: datetime,
) -> None:
    if (
        bundle.capability_plan_sha256 != content_sha256(plan)
        or bundle.catalog_preflight_bundle_sha256
        != content_sha256(catalog_bundle)
    ):
        raise ValueError("capability authorization bundle hashes differ")
    if not (
        bundle.manual_approval.approved_at
        <= now
        <= bundle.manual_approval.expires_at
    ):
        raise ValueError("capability manual approval is not active")
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


def _candidate_parts(
    suite: Phase4TogetherSuite,
) -> tuple[list[OpenWeightModelCandidate], list[ProviderPriceCard]]:
    candidates = [item.candidate for item in suite.candidates]
    price_cards = [item.price_card for item in suite.candidates]
    return candidates, price_cards


def _capability_call_passed(
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


def _validate_execution_authorization(
    authorization: TogetherCapabilityAuthorizationBundle,
    plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    *,
    now: datetime,
) -> None:
    """Recheck paid gates at the library boundary without making a call."""

    _require_aware(now, "capability execution time")
    if authorization.capability_plan_sha256 != content_sha256(plan):
        raise ValueError("capability execution authorization binds another plan")
    if not (
        authorization.manual_approval.approved_at
        <= now
        <= authorization.manual_approval.expires_at
    ):
        raise ValueError("capability execution approval is not active")
    live = authorization.live_authorization
    qualification_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.QUALIFICATION
    ]
    expected = (
        suite.suite_id,
        suite.suite_version,
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(readiness.token_readiness_receipt),
        content_sha256(readiness.headroom_policy),
        TogetherPaidStage.CAPABILITY_PREFLIGHT,
        BudgetSegment.QUALIFICATION,
        sorted(item.candidate.candidate_id for item in suite.candidates),
        sorted(LLMRole, key=lambda item: item.value),
        qualification_cap,
        None,
    )
    actual = (
        live.together_suite_id,
        live.together_suite_version,
        live.together_suite_sha256,
        live.robustness_profile_sha256,
        live.token_readiness_receipt_sha256,
        live.headroom_policy_sha256,
        live.stage,
        live.budget_segment,
        live.authorized_candidate_ids,
        live.authorized_roles,
        live.approved_max_spend_microusd,
        live.capability_preflight_receipt_sha256,
    )
    if actual != expected:
        raise ValueError("capability execution authorization bindings differ")


def _build_receipt(
    plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    outputs: list[TogetherCapabilityOutputRecord],
    *,
    receipt_id: str,
    completed_at: datetime,
) -> TogetherCapabilityPreflightReceipt:
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
    usages = {item.call_id: item for item in ledger.calls}
    outputs_by_id = {item.call_id: item for item in outputs}
    planned_ids = [item.call_id for item in plan.calls]
    if (
        set(bindings)
        != set(planned_ids)
        or set(finalizations) != set(planned_ids)
        or set(usages) != set(planned_ids)
        or set(outputs_by_id) != set(planned_ids)
    ):
        raise ValueError("capability audit must cover the exact plan")
    if completed_at < max(item.created_at for item in finalizations.values()):
        raise ValueError("capability receipt cannot predate provider completion")
    checks: list[TogetherCapabilityProbeCheck] = []
    for item in plan.calls:
        binding = bindings[item.call_id]
        finalization = finalizations[item.call_id]
        output = outputs_by_id[item.call_id]
        if (
            binding.model_candidate_id,
            binding.role,
            content_sha256(binding),
        ) != (
            item.candidate_id,
            item.role,
            finalization.request_binding_sha256,
        ) or (output.candidate_id, output.role) != (
            item.candidate_id,
            item.role,
        ):
            raise ValueError("capability finalization binding differs")
        if not _capability_call_passed(item, finalization) or (
            finalization.response_sha256 != output.output_sha256
        ):
            raise ValueError("capability probe did not succeed")
        tool_passed: bool | None = None
        if item.actual_tool_call_required:
            tool_passed = True
        checks.append(
            TogetherCapabilityProbeCheck(
                candidate_id=item.candidate_id,
                role=item.role,
                call_id=item.call_id,
                finalization_sha256=content_sha256(finalization),
                interviewer_tool_calling_passed=tool_passed,
            )
        )
    spend = sum(item.billed_cost_microusd for item in ledger.calls)
    if spend > plan.capability_max_spend_microusd:
        raise ValueError("capability provider spend exceeds manual ceiling")
    return TogetherCapabilityPreflightReceipt(
        receipt_id=receipt_id,
        receipt_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        provider_ledger_sha256=content_sha256(ledger),
        provider_journal_sha256=content_sha256(journal),
        completed_at=completed_at,
        checks=checks,
        provider_spend_microusd=spend,
    )


def validate_capability_execution_state(
    state: TogetherCapabilityExecutionState,
    plan: TogetherCapabilityPlan,
    authorization: TogetherCapabilityAuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    if (
        state.capability_plan_sha256 != content_sha256(plan)
        or state.authorization_bundle_sha256 != content_sha256(authorization)
    ):
        raise ValueError("capability state bindings differ")
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
        raise ValueError("capability state is not an exact plan prefix")
    finalization_ids = [
        item.call_id for item in state.provider_journal.finalizations
    ]
    if finalization_ids != authorization_ids[: len(finalization_ids)]:
        raise ValueError("capability finalizations are not an exact prefix")
    if len(authorization_ids) - len(finalization_ids) > 1:
        raise ValueError("capability state may retain one outstanding call")
    if any(
        not _capability_call_passed(plan.calls[index], finalization)
        for index, finalization in enumerate(
            state.provider_journal.finalizations[:-1]
        )
    ):
        raise ValueError("capability failure must terminate its attempt")
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
        (item.call_id, item.candidate_id, item.role)
        for item in state.outputs
    ]
    if actual_outputs != expected_outputs:
        raise ValueError("capability outputs must cover successful calls")
    finalizations_by_id = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    for output in state.outputs:
        if (
            finalizations_by_id[output.call_id].response_sha256
            != output.output_sha256
        ):
            raise ValueError("capability output differs from provider audit")
    if sum(
        item.billed_cost_microusd for item in state.provider_ledger.calls
    ) > plan.capability_max_spend_microusd:
        raise ValueError("capability state exceeds manual spend ceiling")
    if state.receipt is not None:
        rebuilt = _build_receipt(
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
            raise ValueError("capability receipt does not rebuild from audit")


def _execution_state(
    *,
    state_id: str,
    plan: TogetherCapabilityPlan,
    authorization: TogetherCapabilityAuthorizationBundle,
    runtime: ProviderBudgetRuntime,
    outputs: list[TogetherCapabilityOutputRecord],
    receipt: TogetherCapabilityPreflightReceipt | None,
) -> TogetherCapabilityExecutionState:
    return TogetherCapabilityExecutionState(
        state_id=state_id,
        state_version=1,
        capability_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        provider_ledger=runtime.ledger_snapshot(),
        provider_journal=runtime.journal_snapshot(),
        outputs=outputs,
        receipt=receipt,
    )


def execute_capability_preflight(
    plan: TogetherCapabilityPlan,
    authorization: TogetherCapabilityAuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    transport: ProviderTransport,
    *,
    state_id: str,
    ledger_id: str,
    journal_id: str,
    clock: Callable[[], datetime],
    prior_state: TogetherCapabilityExecutionState | None = None,
    checkpoint: Callable[[TogetherCapabilityExecutionState], None] | None = None,
) -> TogetherCapabilityExecutionState:
    """Execute the exact plan sequentially, checkpointing after every call."""

    validate_capability_plan(
        plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    started_at = clock()
    _validate_execution_authorization(
        authorization,
        plan,
        suite,
        profile,
        readiness,
        now=started_at,
    )

    if prior_state is None:
        runtime = ProviderBudgetRuntime(
            profile,
            ledger_id=ledger_id,
            journal_id=journal_id,
        )
        outputs: list[TogetherCapabilityOutputRecord] = []
    else:
        validate_capability_execution_state(
            prior_state,
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
            completed_index = len(
                prior_state.provider_journal.finalizations
            ) - 1
            if not _capability_call_passed(
                plan.calls[completed_index],
                prior_state.provider_journal.finalizations[-1],
            ):
                raise ValueError("failed capability attempt is terminal")
    ledger = runtime.ledger_snapshot()
    if len(ledger.authorizations) != len(ledger.calls):
        raise ValueError("capability state has an outstanding call to reconcile")
    completed_count = len(ledger.calls)
    for call_plan, entry in zip(
        plan.calls[completed_count:],
        readiness.qualification_manifest.entries[completed_count:],
    ):
        if content_sha256(entry) != call_plan.qualification_entry_sha256:
            raise ValueError("capability execution entry hash differs")
        spent = sum(
            item.billed_cost_microusd
            for item in runtime.ledger_snapshot().calls
        )
        if (
            spent + call_plan.authorized_max_cost_microusd
            > plan.capability_max_spend_microusd
        ):
            raise ValueError("next capability call exceeds manual spend ceiling")
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
            progressive = _execution_state(
                state_id=state_id,
                plan=plan,
                authorization=authorization,
                runtime=runtime,
                outputs=outputs,
                receipt=None,
            )
            validate_capability_execution_state(
                progressive,
                plan,
                authorization,
                suite,
                profile,
            )
            if checkpoint is not None:
                checkpoint(progressive)
            raise
        if result.output is not None:
            payload = rebuilt.response_adapter.dump_python(
                result.output,
                mode="json",
            )
            outputs.append(
                TogetherCapabilityOutputRecord(
                    call_id=call_plan.call_id,
                    candidate_id=call_plan.candidate_id,
                    role=call_plan.role,
                    output_sha256=content_sha256(payload),
                    output_payload=payload,
                )
            )
        progressive = _execution_state(
            state_id=state_id,
            plan=plan,
            authorization=authorization,
            runtime=runtime,
            outputs=outputs,
            receipt=None,
        )
        validate_capability_execution_state(
            progressive,
            plan,
            authorization,
            suite,
            profile,
        )
        if checkpoint is not None:
            checkpoint(progressive)
        if result.finalization.outcome is not ProviderCallOutcome.SUCCESS:
            raise ValueError("capability provider call did not succeed")
        if not _capability_call_passed(call_plan, result.finalization):
            raise ValueError("interviewer capability probe did not call a tool")
    completed_at = clock()
    receipt = _build_receipt(
        plan,
        suite,
        profile,
        runtime.ledger_snapshot(),
        runtime.journal_snapshot(),
        outputs,
        receipt_id=f"{state_id}_receipt",
        completed_at=completed_at,
    )
    complete = _execution_state(
        state_id=state_id,
        plan=plan,
        authorization=authorization,
        runtime=runtime,
        outputs=outputs,
        receipt=receipt,
    )
    validate_capability_execution_state(
        complete,
        plan,
        authorization,
        suite,
        profile,
    )
    if checkpoint is not None:
        checkpoint(complete)
    return complete


def capability_plan_summary(plan: TogetherCapabilityPlan) -> dict[str, JsonValue]:
    return {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "plan_version": plan.plan_version,
        "plan_sha256": content_sha256(plan),
        "candidate_count": len({item.candidate_id for item in plan.calls}),
        "role_count": len({item.role for item in plan.calls}),
        "call_count": len(plan.calls),
        "interviewer_tool_probe_count": sum(
            item.actual_tool_call_required for item in plan.calls
        ),
        "projected_cost_microusd": plan.projected_cost_microusd,
        "all_calls_authorized_max_cost_microusd": (
            plan.all_calls_authorized_max_cost_microusd
        ),
        "capability_max_spend_microusd": plan.capability_max_spend_microusd,
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
    }


def capability_state_summary(
    state: TogetherCapabilityExecutionState,
) -> dict[str, JsonValue]:
    spend = sum(
        item.billed_cost_microusd for item in state.provider_ledger.calls
    )
    return {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "state_version": state.state_version,
        "state_sha256": content_sha256(state),
        "authorized_call_count": len(state.provider_ledger.authorizations),
        "completed_call_count": len(state.provider_ledger.calls),
        "successful_output_count": len(state.outputs),
        "provider_spend_microusd": spend,
        "capability_approved": state.receipt is not None,
    }
