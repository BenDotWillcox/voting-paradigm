"""Paid runtime for the reviewed second qualification attempt.

The completed v1 run and all of its contracts remain immutable.  This module
defines a separate v2 authorization and progressive candidate-state surface
for the 304-call, no-carry attempt.  Every paid request is rebuilt from the
tracked v6 manifest and is authorized by exact provider-visible content hash.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal, Self

import httpx
from pydantic import Field, SecretStr, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_provider import (
    PROVIDER_RESPONSE_JSON_DECODER_POLICY,
    PrivateStructuredProviderRequest,
    ProviderBudgetRuntime,
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderExecutionJournal,
    ProviderHTTPErrorDiagnostic,
    ProviderStructuredOutputDiagnostic,
    ProviderTransport,
    price_provider_tokens,
    provider_committed_totals,
    provider_request_content_sha256,
    provider_response_json_decoder_implementation_sha256,
    validate_provider_execution_journal,
)
from .phase4_qualification_attempt import (
    ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD,
    ATTEMPT_V2_PROVIDER_CALL_COUNT,
    QualificationAttemptStage,
    QualificationAttemptV2CallPlan,
    QualificationAttemptV2CandidatePlan,
    QualificationAttemptV2Plan,
    QualificationAttemptV2SourceProof,
    validate_qualification_attempt_v2_plan,
)
from .phase4_qualification_runtime import (
    AuditedQualificationInterviewerToolExecutor,
    QualificationOutputRecord,
    QualificationToolReplayRecord,
)
from .phase4_qualification_scope import (
    AMENDED_SCOPE_PAUSE_OUTCOMES,
    TwoDeploymentQualificationScopeAmendment,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    rebuild_qualification_call,
    validate_readiness_bundle,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    Phase4ERobustnessProfile,
    ProviderUsageLedger,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import (
    Phase4TogetherSuite,
    build_default_together_suite,
    validate_together_suite,
)
from .phase4_together_live import (
    DEFAULT_MAX_TOOL_ROUNDS,
    TogetherAmbiguousDeliveryError,
    TogetherCatalogPreflightBundle,
    TogetherTokenCounter,
    _build_together_invocation_core,
    together_json_decoder_integration_sha256,
    validate_catalog_preflight_bundle,
)
from .prequential import PrequentialSessionScript


Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]

ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD = 97_287
ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD = 2_384_400
ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD = 2_481_687
ATTEMPT_V2_QUALIFICATION_SEGMENT_CAP_MICROUSD = 4_000_000
ATTEMPT_V2_APPROVAL_MAXIMUM_DURATION = timedelta(hours=2)
ATTEMPT_V2_CATALOG_MAXIMUM_AGE_AT_APPROVAL = timedelta(minutes=30)


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


class QualificationAttemptV2ExecutionStatus(str, Enum):
    """Progress and terminal states for one candidate in paired execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    CANDIDATE_HARD_FAILURE = "candidate_hard_failure"
    GLOBAL_PROVIDER_PAUSE = "global_provider_pause_pending_review"
    GLOBAL_AMBIGUOUS_DELIVERY = (
        "global_ambiguous_delivery_pending_reconciliation"
    )
    GLOBAL_HARNESS_PAUSE = "global_harness_pause_pending_review"
    STOPPED_BY_GLOBAL_PAUSE = "stopped_by_global_pause"


GLOBAL_PAUSE_STATUSES = frozenset(
    {
        QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE,
        QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY,
        QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE,
    }
)


class QualificationAttemptV2HarnessFailureCode(str, Enum):
    SHARED_BUDGET_GATE = "shared_budget_gate"
    SOURCE_ENTRY_MISMATCH = "source_entry_mismatch"
    REQUEST_REBUILD_MISMATCH = "request_rebuild_mismatch"
    LOCAL_EXECUTION_EXCEPTION = "local_execution_exception"


class QualificationAttemptV2ExactRequestAuthorization(ContractModel):
    """One exact v6 request approved in the plan's paired order."""

    record_version: Literal[
        "phase4_qualification_attempt_authorized_request.v2"
    ] = "phase4_qualification_attempt_authorized_request.v2"
    execution_order_index: PositiveCount
    source_manifest_ordinal: PositiveCount
    source_entry_sha256: Sha256Digest
    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    request_content_sha256: Sha256Digest
    authorized_max_cost_microusd: PositiveCount


class QualificationAttemptV2ManualApproval(ContractModel):
    """Short-lived explicit user approval for one exact 304-request set."""

    record_version: Literal[
        "phase4_qualification_attempt_manual_approval.v2"
    ] = "phase4_qualification_attempt_manual_approval.v2"
    approval_id: StableId
    approval_version: Literal[2] = 2
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    prior_scope_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    exact_request_set_sha256: Sha256Digest
    approved_call_count: Literal[304] = ATTEMPT_V2_PROVIDER_CALL_COUNT
    prior_actual_spend_microusd: Literal[97_287] = (
        ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    )
    approved_max_spend_microusd: Literal[2_384_400] = (
        ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
    )
    cumulative_authorized_worst_case_microusd: Literal[2_481_687] = (
        ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
    )
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    paired_execution_order_required: Literal[True] = True
    candidate_local_hard_failure_only: Literal[True] = True
    global_pause_on_provider_transport_or_harness: Literal[True] = True
    automatic_retry_forbidden: Literal[True] = True
    fallback_and_replacement_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification attempt approval time")

    @model_validator(mode="after")
    def require_short_forward_window(self) -> Self:
        duration = self.expires_at - self.approved_at
        if duration <= timedelta(0) or duration > (
            ATTEMPT_V2_APPROVAL_MAXIMUM_DURATION
        ):
            raise ValueError("qualification attempt approval window is invalid")
        if self.prior_actual_spend_microusd + (
            self.approved_max_spend_microusd
        ) != self.cumulative_authorized_worst_case_microusd:
            raise ValueError("qualification attempt approval budget differs")
        return self


class QualificationAttemptV2AuthorizationBundle(ContractModel):
    """Private exact-request authorization for the v2 attempt only."""

    schema_version: Literal[
        "preference_eval_phase4_qualification_attempt_authorization.v2"
    ] = "preference_eval_phase4_qualification_attempt_authorization.v2"
    bundle_id: StableId
    bundle_version: Literal[2] = 2
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    prior_scope_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    development_fixture_sha256: Sha256Digest
    development_session_sha256: Sha256Digest
    development_semantic_map_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    account_privacy_attestation_sha256: Sha256Digest
    catalog_preflight_receipt_sha256: Sha256Digest
    token_readiness_receipt_sha256: Sha256Digest
    headroom_policy_sha256: Sha256Digest
    response_invariant_manifest_sha256: Sha256Digest
    response_behavior_spec_sha256: Sha256Digest
    readout_validator_implementation_sha256: Sha256Digest
    json_decoder_policy_sha256: Sha256Digest
    json_decoder_implementation_sha256: Sha256Digest
    together_json_decoder_integration_sha256: Sha256Digest
    execution_order_call_ids_sha256: Sha256Digest
    manual_approval: QualificationAttemptV2ManualApproval
    authorized_requests: list[
        QualificationAttemptV2ExactRequestAuthorization
    ] = Field(min_length=304, max_length=304)
    authorized_candidate_ids: list[StableId] = Field(min_length=2, max_length=2)
    authorized_roles: list[LLMRole] = Field(min_length=5, max_length=5)
    authorized_call_count: Literal[304] = ATTEMPT_V2_PROVIDER_CALL_COUNT
    prior_actual_spend_microusd: Literal[97_287] = (
        ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    )
    new_authorized_max_spend_microusd: Literal[2_384_400] = (
        ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
    )
    cumulative_authorized_worst_case_microusd: Literal[2_481_687] = (
        ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
    )
    qualification_segment_cap_microusd: Literal[4_000_000] = (
        ATTEMPT_V2_QUALIFICATION_SEGMENT_CAP_MICROUSD
    )
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )

    @model_validator(mode="after")
    def require_exact_scope(self) -> Self:
        if [item.execution_order_index for item in self.authorized_requests] != (
            list(range(1, self.authorized_call_count + 1))
        ):
            raise ValueError("qualification attempt authorization order differs")
        call_ids = [item.call_id for item in self.authorized_requests]
        ordinals = [
            item.source_manifest_ordinal for item in self.authorized_requests
        ]
        if len(call_ids) != len(set(call_ids)) or len(ordinals) != len(
            set(ordinals)
        ):
            raise ValueError("qualification attempt authorization is duplicated")
        candidates = sorted(
            {item.candidate_id for item in self.authorized_requests}
        )
        roles = sorted(
            {item.role for item in self.authorized_requests},
            key=lambda item: item.value,
        )
        if self.authorized_candidate_ids != candidates:
            raise ValueError("qualification attempt candidates differ")
        if self.authorized_roles != roles or set(roles) != set(LLMRole):
            raise ValueError("qualification attempt roles differ")
        if self.execution_order_call_ids_sha256 != content_sha256(call_ids):
            raise ValueError("qualification attempt execution order hash differs")
        if sum(
            item.authorized_max_cost_microusd
            for item in self.authorized_requests
        ) != self.new_authorized_max_spend_microusd:
            raise ValueError("qualification attempt authorized spend differs")
        if self.prior_actual_spend_microusd + (
            self.new_authorized_max_spend_microusd
        ) != self.cumulative_authorized_worst_case_microusd or (
            self.cumulative_authorized_worst_case_microusd
            > self.qualification_segment_cap_microusd
        ):
            raise ValueError("qualification attempt cumulative spend differs")
        request_set_sha256 = content_sha256(
            [item.model_dump(mode="json") for item in self.authorized_requests]
        )
        if self.manual_approval.exact_request_set_sha256 != request_set_sha256:
            raise ValueError("qualification attempt request-set hash differs")
        approval_bindings = (
            self.manual_approval.source_proof_sha256,
            self.manual_approval.execution_plan_sha256,
            self.manual_approval.prior_scope_sha256,
            self.manual_approval.together_suite_sha256,
            self.manual_approval.readiness_sha256,
            self.manual_approval.catalog_preflight_bundle_sha256,
            self.manual_approval.json_decoder_policy_sha256,
            self.manual_approval.json_decoder_implementation_sha256,
            self.manual_approval.together_json_decoder_integration_sha256,
        )
        bundle_bindings = (
            self.source_proof_sha256,
            self.execution_plan_sha256,
            self.prior_scope_sha256,
            self.together_suite_sha256,
            self.readiness_sha256,
            self.catalog_preflight_bundle_sha256,
            self.json_decoder_policy_sha256,
            self.json_decoder_implementation_sha256,
            self.together_json_decoder_integration_sha256,
        )
        if approval_bindings != bundle_bindings:
            raise ValueError("qualification attempt approval bindings differ")
        return self


class QualificationAttemptV2CandidateReceipt(ContractModel):
    """Content-free terminal receipt for one v2 candidate state."""

    record_version: Literal[
        "phase4_qualification_attempt_candidate_receipt.v2"
    ] = "phase4_qualification_attempt_candidate_receipt.v2"
    receipt_id: StableId
    receipt_version: Literal[2] = 2
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    candidate_id: StableId
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    output_records_sha256: Sha256Digest
    tool_replay_records_sha256: Sha256Digest
    status: QualificationAttemptV2ExecutionStatus
    completed_call_count: NonNegativeCount
    successful_call_count: NonNegativeCount
    provider_spend_microusd: Microusd
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        return _require_aware(value, "qualification attempt receipt time")

    @model_validator(mode="after")
    def require_terminal_status(self) -> Self:
        if self.status is QualificationAttemptV2ExecutionStatus.RUNNING:
            raise ValueError("qualification attempt receipt must be terminal")
        if self.successful_call_count > self.completed_call_count:
            raise ValueError("qualification attempt successes exceed calls")
        return self


class QualificationAttemptV2CandidateState(ContractModel):
    """Private progressive audit for one candidate under the paired v2 run."""

    schema_version: Literal[
        "preference_eval_phase4_qualification_attempt_candidate_state.v2"
    ] = "preference_eval_phase4_qualification_attempt_candidate_state.v2"
    state_id: StableId
    state_version: Literal[2] = 2
    source_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    candidate_id: StableId
    status: QualificationAttemptV2ExecutionStatus
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    outputs: list[QualificationOutputRecord]
    tool_replay_records: list[QualificationToolReplayRecord]
    validation_diagnostics: list[ProviderStructuredOutputDiagnostic]
    provider_error_diagnostics: list[ProviderHTTPErrorDiagnostic]
    harness_failure_code: QualificationAttemptV2HarnessFailureCode | None = None
    global_stop_call_id: StableId | None = None
    global_stop_candidate_id: StableId | None = None
    global_stop_status: QualificationAttemptV2ExecutionStatus | None = None
    receipt: QualificationAttemptV2CandidateReceipt | None = None

    @model_validator(mode="after")
    def require_coherent_private_records(self) -> Self:
        for values, label in (
            (self.outputs, "outputs"),
            (self.validation_diagnostics, "validation diagnostics"),
            (self.provider_error_diagnostics, "provider diagnostics"),
        ):
            call_ids = [item.call_id for item in values]
            if len(call_ids) != len(set(call_ids)):
                raise ValueError(f"qualification attempt {label} differ")
        replay_keys = [
            (item.call_id, item.tool_call_index)
            for item in self.tool_replay_records
        ]
        if len(replay_keys) != len(set(replay_keys)):
            raise ValueError("qualification attempt tool replays differ")
        global_parts = (
            self.global_stop_call_id,
            self.global_stop_candidate_id,
            self.global_stop_status,
        )
        globally_stopped = self.status in GLOBAL_PAUSE_STATUSES or (
            self.status
            is QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE
        )
        if globally_stopped != all(item is not None for item in global_parts):
            raise ValueError("qualification attempt global-stop binding differs")
        if not globally_stopped and any(item is not None for item in global_parts):
            raise ValueError("qualification attempt has unexpected global stop")
        if self.status in GLOBAL_PAUSE_STATUSES and (
            self.global_stop_status is not self.status
            or self.global_stop_candidate_id != self.candidate_id
        ):
            raise ValueError("qualification attempt pause owner differs")
        if (
            self.status
            is QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE
        ) and (
            self.global_stop_status not in GLOBAL_PAUSE_STATUSES
            or self.global_stop_candidate_id == self.candidate_id
        ):
            raise ValueError("qualification attempt sibling stop differs")
        harness_pause = (
            self.global_stop_status
            is QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
        )
        if harness_pause != (self.harness_failure_code is not None):
            raise ValueError("qualification attempt harness failure differs")
        terminal = self.status is not QualificationAttemptV2ExecutionStatus.RUNNING
        if terminal != (self.receipt is not None):
            raise ValueError("qualification attempt receipt presence differs")
        if self.receipt is not None and self.receipt.status is not self.status:
            raise ValueError("qualification attempt receipt status differs")
        return self


def _candidate_plans_by_id(
    plan: QualificationAttemptV2Plan,
) -> dict[str, QualificationAttemptV2CandidatePlan]:
    return {item.candidate_id: item for item in plan.candidate_plans}


def _planned_calls_by_id(
    plan: QualificationAttemptV2Plan,
) -> dict[str, QualificationAttemptV2CallPlan]:
    return {
        item.call_id: item
        for candidate in plan.candidate_plans
        for item in candidate.calls
    }


def _ordered_candidate_calls(
    plan: QualificationAttemptV2Plan,
    candidate_id: str,
) -> list[QualificationAttemptV2CallPlan]:
    calls = _planned_calls_by_id(plan)
    return [
        calls[call_id]
        for call_id in plan.execution_order_call_ids
        if calls[call_id].candidate_id == candidate_id
    ]


def _build_exact_authorized_requests(
    plan: QualificationAttemptV2Plan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    approved_at: datetime,
) -> list[QualificationAttemptV2ExactRequestAuthorization]:
    entries_by_id = {
        item.coordinate.call_id: item
        for item in readiness.qualification_manifest.entries
    }
    calls_by_id = _planned_calls_by_id(plan)
    exact: list[QualificationAttemptV2ExactRequestAuthorization] = []
    for index, call_id in enumerate(plan.execution_order_call_ids, start=1):
        call = calls_by_id[call_id]
        entry = entries_by_id.get(call_id)
        if entry is None or entry != call.source_entry:
            raise ValueError("qualification attempt source entry differs")
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=approved_at + timedelta(microseconds=index),
        )
        request_sha256 = provider_request_content_sha256(
            rebuilt.request.binding
        )
        if request_sha256 != entry.request_template_sha256:
            raise ValueError("qualification attempt request template differs")
        exact.append(
            QualificationAttemptV2ExactRequestAuthorization(
                execution_order_index=index,
                source_manifest_ordinal=entry.coordinate.ordinal,
                source_entry_sha256=content_sha256(entry),
                call_id=call_id,
                candidate_id=entry.coordinate.candidate_id,
                role=entry.coordinate.role,
                request_content_sha256=request_sha256,
                authorized_max_cost_microusd=(
                    entry.authorized_max_cost_microusd
                ),
            )
        )
    return exact


def _validate_attempt_v2_sources(
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    scope: TwoDeploymentQualificationScopeAmendment,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    validate_qualification_attempt_v2_plan(plan, proof, suite, readiness)
    runnable_candidate_ids = scope.runnable_candidate_ids
    if (
        content_sha256(scope) != proof.prior_scope_sha256
        or content_sha256(scope) != plan.prior_scope_sha256
        or runnable_candidate_ids
        != [item.candidate_id for item in plan.candidate_plans]
        or runnable_candidate_ids
        != sorted(proof.prior_candidate_state_sha256s)
    ):
        raise ValueError("qualification attempt scope or runnable roster differs")
    if suite != build_default_together_suite(profile) or suite.suite_version != 6:
        raise ValueError("qualification attempt requires the exact v6 suite")
    validate_together_suite(suite, profile)
    validate_readiness_bundle(
        readiness,
        suite,
        profile,
        fixture,
        session,
        semantic_map,
    )
    bindings = (
        readiness.together_suite_sha256,
        readiness.robustness_profile_sha256,
        readiness.public_development_fixture_sha256,
        readiness.public_development_session_sha256,
        readiness.public_development_semantic_map_sha256,
    )
    expected = (
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(fixture),
        content_sha256(session),
        content_sha256(semantic_map),
    )
    if bindings != expected or readiness.readiness_version != 6:
        raise ValueError("qualification attempt readiness bindings differ")
    planned_calls = _planned_calls_by_id(plan)
    ordered_stages = [
        planned_calls[call_id].execution_stage
        for call_id in plan.execution_order_call_ids
    ]
    if ordered_stages[:4] != [
        QualificationAttemptStage.READOUT_CONFORMANCE
    ] * 4 or any(
        stage is not QualificationAttemptStage.FULL_QUALIFICATION
        for stage in ordered_stages[4:]
    ):
        raise ValueError("qualification attempt conformance order differs")
    if (
        plan.prior_actual_spend_microusd
        != ATTEMPT_V1_CUMULATIVE_SPEND_MICROUSD
        or plan.prior_actual_spend_microusd
        != ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    ):
        raise ValueError("qualification attempt prior spend differs")
    decoder = (
        content_sha256(PROVIDER_RESPONSE_JSON_DECODER_POLICY),
        provider_response_json_decoder_implementation_sha256(),
        together_json_decoder_integration_sha256(),
    )
    if (
        plan.json_decoder_policy_sha256,
        plan.json_decoder_implementation_sha256,
        plan.together_json_decoder_integration_sha256,
    ) != decoder or (
        proof.json_decoder_policy_sha256,
        proof.json_decoder_implementation_sha256,
        proof.together_json_decoder_integration_sha256,
    ) != decoder:
        raise ValueError("qualification attempt JSON decoder differs")


def build_qualification_attempt_v2_authorization(
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    scope: TwoDeploymentQualificationScopeAmendment,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    catalog: TogetherCatalogPreflightBundle,
    *,
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> QualificationAttemptV2AuthorizationBundle:
    """Create the zero-spend authorization for all 304 exact v2 requests."""

    _validate_attempt_v2_sources(
        plan,
        proof,
        scope,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    validate_catalog_preflight_bundle(suite, catalog)
    _require_aware(approved_at, "qualification attempt approval time")
    if catalog.receipt.checked_at > approved_at or approved_at - (
        catalog.receipt.checked_at
    ) > ATTEMPT_V2_CATALOG_MAXIMUM_AGE_AT_APPROVAL or (
        catalog.receipt.checked_at <= plan.created_at
    ):
        raise ValueError("qualification attempt catalog preflight is not fresh")
    exact = _build_exact_authorized_requests(
        plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        approved_at=approved_at,
    )
    request_set_sha256 = content_sha256(
        [item.model_dump(mode="json") for item in exact]
    )
    manual = QualificationAttemptV2ManualApproval(
        approval_id=approval_id,
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        prior_scope_sha256=content_sha256(scope),
        together_suite_sha256=content_sha256(suite),
        readiness_sha256=content_sha256(readiness),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        json_decoder_policy_sha256=plan.json_decoder_policy_sha256,
        json_decoder_implementation_sha256=(
            plan.json_decoder_implementation_sha256
        ),
        together_json_decoder_integration_sha256=(
            plan.together_json_decoder_integration_sha256
        ),
        exact_request_set_sha256=request_set_sha256,
        approved_at=approved_at,
        expires_at=expires_at,
    )
    bundle = QualificationAttemptV2AuthorizationBundle(
        bundle_id=bundle_id,
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        prior_scope_sha256=content_sha256(scope),
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        development_fixture_sha256=content_sha256(fixture),
        development_session_sha256=content_sha256(session),
        development_semantic_map_sha256=content_sha256(semantic_map),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        account_privacy_attestation_sha256=content_sha256(
            catalog.account_privacy_attestation
        ),
        catalog_preflight_receipt_sha256=content_sha256(catalog.receipt),
        token_readiness_receipt_sha256=content_sha256(
            readiness.token_readiness_receipt
        ),
        headroom_policy_sha256=content_sha256(readiness.headroom_policy),
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
        execution_order_call_ids_sha256=content_sha256(
            plan.execution_order_call_ids
        ),
        manual_approval=manual,
        authorized_requests=exact,
        authorized_candidate_ids=[
            item.candidate_id for item in plan.candidate_plans
        ],
        authorized_roles=sorted(LLMRole, key=lambda item: item.value),
    )
    validate_qualification_attempt_v2_authorization(
        bundle,
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
        now=approved_at,
    )
    return bundle


def validate_qualification_attempt_v2_authorization(
    bundle: QualificationAttemptV2AuthorizationBundle,
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    scope: TwoDeploymentQualificationScopeAmendment,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    catalog: TogetherCatalogPreflightBundle,
    *,
    now: datetime,
) -> None:
    """Rebuild the complete v2 authorization without trusting its claims."""

    _require_aware(now, "qualification attempt authorization validation time")
    _validate_attempt_v2_sources(
        plan,
        proof,
        scope,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    validate_catalog_preflight_bundle(suite, catalog)
    expected_bindings = (
        content_sha256(proof),
        content_sha256(plan),
        content_sha256(scope),
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(readiness),
        content_sha256(readiness.qualification_manifest),
        content_sha256(fixture),
        content_sha256(session),
        content_sha256(semantic_map),
        content_sha256(catalog),
        content_sha256(catalog.account_privacy_attestation),
        content_sha256(catalog.receipt),
        content_sha256(readiness.token_readiness_receipt),
        content_sha256(readiness.headroom_policy),
        plan.response_invariant_manifest_sha256,
        plan.response_behavior_spec_sha256,
        plan.readout_validator_implementation_sha256,
        plan.json_decoder_policy_sha256,
        plan.json_decoder_implementation_sha256,
        plan.together_json_decoder_integration_sha256,
        content_sha256(plan.execution_order_call_ids),
    )
    actual_bindings = (
        bundle.source_proof_sha256,
        bundle.execution_plan_sha256,
        bundle.prior_scope_sha256,
        bundle.together_suite_sha256,
        bundle.robustness_profile_sha256,
        bundle.readiness_sha256,
        bundle.source_qualification_manifest_sha256,
        bundle.development_fixture_sha256,
        bundle.development_session_sha256,
        bundle.development_semantic_map_sha256,
        bundle.catalog_preflight_bundle_sha256,
        bundle.account_privacy_attestation_sha256,
        bundle.catalog_preflight_receipt_sha256,
        bundle.token_readiness_receipt_sha256,
        bundle.headroom_policy_sha256,
        bundle.response_invariant_manifest_sha256,
        bundle.response_behavior_spec_sha256,
        bundle.readout_validator_implementation_sha256,
        bundle.json_decoder_policy_sha256,
        bundle.json_decoder_implementation_sha256,
        bundle.together_json_decoder_integration_sha256,
        bundle.execution_order_call_ids_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("qualification attempt authorization bindings differ")
    approval = bundle.manual_approval
    if not approval.approved_at <= now <= approval.expires_at:
        raise ValueError("qualification attempt manual approval is not active")
    if catalog.receipt.checked_at > approval.approved_at or (
        approval.approved_at - catalog.receipt.checked_at
        > ATTEMPT_V2_CATALOG_MAXIMUM_AGE_AT_APPROVAL
    ) or catalog.receipt.checked_at <= plan.created_at:
        raise ValueError("qualification attempt catalog preflight is not fresh")
    expected_requests = _build_exact_authorized_requests(
        plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        approved_at=approval.approved_at,
    )
    if expected_requests != bundle.authorized_requests:
        raise ValueError("qualification attempt exact requests do not rebuild")


def qualification_attempt_v2_authorization_summary(
    bundle: QualificationAttemptV2AuthorizationBundle,
) -> dict[str, JsonValue]:
    return {
        "schema_version": bundle.schema_version,
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": content_sha256(bundle),
        "candidate_count": len(bundle.authorized_candidate_ids),
        "authorized_call_count": bundle.authorized_call_count,
        "authorized_max_spend_microusd": (
            bundle.new_authorized_max_spend_microusd
        ),
        "prior_actual_spend_microusd": bundle.prior_actual_spend_microusd,
        "cumulative_authorized_worst_case_microusd": (
            bundle.cumulative_authorized_worst_case_microusd
        ),
        "participant_content_present": False,
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
    }


class QualificationAttemptV2TogetherTransport:
    """Together transport reachable only through the exact v2 authorization."""

    def __init__(
        self,
        authorization: QualificationAttemptV2AuthorizationBundle,
        plan: QualificationAttemptV2Plan,
        proof: QualificationAttemptV2SourceProof,
        scope: TwoDeploymentQualificationScopeAmendment,
        suite: Phase4TogetherSuite,
        profile: Phase4ERobustnessProfile,
        readiness: Phase4TogetherReadinessBundle,
        fixture: EvaluationFixture,
        session: PrequentialSessionScript,
        semantic_map: AuthoredSemanticMapBundle,
        catalog: TogetherCatalogPreflightBundle,
        api_key: SecretStr,
        *,
        client: httpx.Client,
        token_counter: TogetherTokenCounter,
        tool_executor: AuditedQualificationInterviewerToolExecutor,
        now: datetime,
        clock: Callable[[], datetime],
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    ) -> None:
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
            now=now,
        )
        if not api_key.get_secret_value():
            raise ValueError("Together API key is empty")
        if max_tool_rounds != DEFAULT_MAX_TOOL_ROUNDS:
            raise ValueError("Together max tool rounds differ from readiness")
        self._authorization = authorization.model_copy(deep=True)
        self._profile_sha256 = content_sha256(profile)
        self._price_cards = {
            item.candidate.candidate_id: item.price_card
            for item in suite.candidates
            if item.candidate.candidate_id
            in authorization.authorized_candidate_ids
        }
        self._exact = {
            item.call_id: item for item in authorization.authorized_requests
        }
        self._clock = clock
        self._core = _build_together_invocation_core(
            suite=suite,
            projection=readiness.token_readiness_receipt,
            api_key=api_key,
            client=client,
            token_counter=token_counter,
            tool_executor=tool_executor,
            clock=clock,
            max_tool_rounds=max_tool_rounds,
        )

    def validate_execution(
        self,
        request: PrivateStructuredProviderRequest,
        *,
        segment: BudgetSegment,
    ) -> None:
        now = _require_aware(self._clock(), "Together attempt execution time")
        approval = self._authorization.manual_approval
        if not approval.approved_at <= now <= approval.expires_at:
            raise ValueError("qualification attempt approval is not active")
        if segment is not BudgetSegment.QUALIFICATION:
            raise ValueError("qualification attempt uses another budget segment")
        binding = request.binding
        if binding.data_scope is not ProviderDataScope.PUBLIC_DEVELOPMENT:
            raise ValueError("qualification attempt is not public development")
        if binding.robustness_profile_sha256 != self._profile_sha256:
            raise ValueError("qualification attempt uses another profile")
        exact = self._exact.get(binding.call_id)
        if exact is None:
            raise ValueError("qualification attempt request is unauthorized")
        actual = (
            binding.model_candidate_id,
            binding.role,
            provider_request_content_sha256(binding),
        )
        expected = (
            exact.candidate_id,
            exact.role,
            exact.request_content_sha256,
        )
        if actual != expected:
            raise ValueError("qualification attempt request binding differs")
        price_card = self._price_cards.get(binding.model_candidate_id)
        if price_card is None:
            raise ValueError("qualification attempt candidate is unauthorized")
        maximum = price_provider_tokens(
            price_card,
            input_tokens=binding.input_token_upper_bound,
            output_tokens=binding.output_token_upper_bound,
        )
        if maximum != exact.authorized_max_cost_microusd:
            raise ValueError("qualification attempt request cost differs")
        if self._core.count_initial_payload(request).input_token_count > (
            binding.input_token_upper_bound
        ):
            raise ValueError("Together input count exceeds attempt bound")

    def invoke(self, request: PrivateStructuredProviderRequest):
        return self._core.invoke(request)


def _terminal_status_for(
    outcome: ProviderCallOutcome,
) -> QualificationAttemptV2ExecutionStatus:
    if outcome in set(AMENDED_SCOPE_PAUSE_OUTCOMES):
        return QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
    if outcome is not ProviderCallOutcome.SUCCESS:
        return QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
    raise ValueError("successful qualification attempt call is not terminal")


def _candidate_receipt(
    *,
    state_id: str,
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    candidate_plan: QualificationAttemptV2CandidatePlan,
    authorization: QualificationAttemptV2AuthorizationBundle,
    candidate_id: str,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    outputs: list[QualificationOutputRecord],
    tool_replays: list[QualificationToolReplayRecord],
    status: QualificationAttemptV2ExecutionStatus,
    completed_at: datetime,
) -> QualificationAttemptV2CandidateReceipt:
    return QualificationAttemptV2CandidateReceipt(
        receipt_id=f"{state_id}_receipt",
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        authorization_bundle_sha256=content_sha256(authorization),
        candidate_plan_sha256=content_sha256(candidate_plan),
        candidate_id=candidate_id,
        provider_ledger_sha256=content_sha256(ledger),
        provider_journal_sha256=content_sha256(journal),
        output_records_sha256=content_sha256(
            [item.model_dump(mode="json") for item in outputs]
        ),
        tool_replay_records_sha256=content_sha256(
            [item.model_dump(mode="json") for item in tool_replays]
        ),
        status=status,
        completed_call_count=len(ledger.calls),
        successful_call_count=sum(
            item.outcome is ProviderCallOutcome.SUCCESS
            for item in journal.finalizations
        ),
        provider_spend_microusd=sum(
            item.billed_cost_microusd for item in ledger.calls
        ),
        completed_at=completed_at,
    )


def _candidate_state(
    *,
    state_id: str,
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    candidate_plan: QualificationAttemptV2CandidatePlan,
    authorization: QualificationAttemptV2AuthorizationBundle,
    candidate_id: str,
    runtime: ProviderBudgetRuntime,
    outputs: list[QualificationOutputRecord],
    tool_replays: list[QualificationToolReplayRecord],
    validation_diagnostics: list[ProviderStructuredOutputDiagnostic],
    provider_diagnostics: list[ProviderHTTPErrorDiagnostic],
    status: QualificationAttemptV2ExecutionStatus,
    completed_at: datetime | None = None,
    harness_failure_code: QualificationAttemptV2HarnessFailureCode | None = None,
    global_stop_call_id: str | None = None,
    global_stop_candidate_id: str | None = None,
    global_stop_status: QualificationAttemptV2ExecutionStatus | None = None,
) -> QualificationAttemptV2CandidateState:
    ledger = runtime.ledger_snapshot()
    journal = runtime.journal_snapshot()
    terminal = status is not QualificationAttemptV2ExecutionStatus.RUNNING
    if terminal and completed_at is None:
        raise ValueError("terminal qualification attempt needs completion time")
    receipt = (
        _candidate_receipt(
            state_id=state_id,
            proof=proof,
            plan=plan,
            candidate_plan=candidate_plan,
            authorization=authorization,
            candidate_id=candidate_id,
            ledger=ledger,
            journal=journal,
            outputs=outputs,
            tool_replays=tool_replays,
            status=status,
            completed_at=completed_at,
        )
        if terminal
        else None
    )
    return QualificationAttemptV2CandidateState(
        state_id=state_id,
        source_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        candidate_plan_sha256=content_sha256(candidate_plan),
        authorization_bundle_sha256=content_sha256(authorization),
        candidate_id=candidate_id,
        status=status,
        provider_ledger=ledger,
        provider_journal=journal,
        outputs=outputs,
        tool_replay_records=tool_replays,
        validation_diagnostics=validation_diagnostics,
        provider_error_diagnostics=provider_diagnostics,
        harness_failure_code=harness_failure_code,
        global_stop_call_id=global_stop_call_id,
        global_stop_candidate_id=global_stop_candidate_id,
        global_stop_status=global_stop_status,
        receipt=receipt,
    )


def _rebuild_receipt(
    state: QualificationAttemptV2CandidateState,
    proof: QualificationAttemptV2SourceProof,
    plan: QualificationAttemptV2Plan,
    candidate_plan: QualificationAttemptV2CandidatePlan,
    authorization: QualificationAttemptV2AuthorizationBundle,
) -> QualificationAttemptV2CandidateReceipt:
    if state.receipt is None:
        raise ValueError("qualification attempt terminal state lacks receipt")
    return _candidate_receipt(
        state_id=state.state_id,
        proof=proof,
        plan=plan,
        candidate_plan=candidate_plan,
        authorization=authorization,
        candidate_id=state.candidate_id,
        ledger=state.provider_ledger,
        journal=state.provider_journal,
        outputs=state.outputs,
        tool_replays=state.tool_replay_records,
        status=state.status,
        completed_at=state.receipt.completed_at,
    )


def validate_qualification_attempt_v2_candidate_state(
    state: QualificationAttemptV2CandidateState,
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    authorization: QualificationAttemptV2AuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    *,
    require_terminal: bool = False,
) -> None:
    """Validate one progressive state against the exact paired v2 plan."""

    candidate_plan = _candidate_plans_by_id(plan).get(state.candidate_id)
    suite_candidate = next(
        (
            item
            for item in suite.candidates
            if item.candidate.candidate_id == state.candidate_id
        ),
        None,
    )
    if candidate_plan is None or suite_candidate is None:
        raise ValueError("qualification attempt state candidate is unknown")
    expected_bindings = (
        content_sha256(proof),
        content_sha256(plan),
        content_sha256(candidate_plan),
        content_sha256(authorization),
    )
    actual_bindings = (
        state.source_proof_sha256,
        state.execution_plan_sha256,
        state.candidate_plan_sha256,
        state.authorization_bundle_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("qualification attempt state bindings differ")
    manual_approval = authorization.manual_approval
    if any(
        not (
            manual_approval.approved_at
            <= binding.created_at
            <= manual_approval.expires_at
        )
        for binding in state.provider_journal.request_bindings
    ):
        raise ValueError(
            "qualification attempt request was created outside approval"
        )
    validate_provider_execution_journal(
        state.provider_journal,
        state.provider_ledger,
        profile,
        [suite_candidate.candidate],
        [suite_candidate.price_card],
        require_complete=False,
    )
    calls = _ordered_candidate_calls(plan, state.candidate_id)
    planned_ids = [item.call_id for item in calls]
    exact = [
        item
        for item in authorization.authorized_requests
        if item.candidate_id == state.candidate_id
    ]
    if [item.call_id for item in exact] != planned_ids:
        raise ValueError("qualification attempt candidate authorization differs")
    authorization_ids = [
        item.call_id for item in state.provider_ledger.authorizations
    ]
    usage_ids = [item.call_id for item in state.provider_ledger.calls]
    binding_ids = [
        item.call_id for item in state.provider_journal.request_bindings
    ]
    finalization_ids = [
        item.call_id for item in state.provider_journal.finalizations
    ]
    if authorization_ids != planned_ids[: len(authorization_ids)]:
        raise ValueError("qualification attempt authorizations are not a prefix")
    if binding_ids != authorization_ids or usage_ids != authorization_ids[
        : len(usage_ids)
    ] or finalization_ids != usage_ids:
        raise ValueError("qualification attempt provider records differ")
    if len(authorization_ids) - len(usage_ids) > 1:
        raise ValueError("qualification attempt has multiple outstanding calls")
    for index, binding in enumerate(state.provider_journal.request_bindings):
        call = calls[index]
        approved = exact[index]
        provider_authorization = state.provider_ledger.authorizations[index]
        expected = (
            call.source_manifest_ordinal,
            call.source_entry_sha256,
            call.call_id,
            call.candidate_id,
            call.role,
            call.source_entry.request_template_sha256,
            call.authorized_max_cost_microusd,
        )
        actual = (
            approved.source_manifest_ordinal,
            approved.source_entry_sha256,
            approved.call_id,
            approved.candidate_id,
            approved.role,
            approved.request_content_sha256,
            approved.authorized_max_cost_microusd,
        )
        if actual != expected:
            raise ValueError("qualification attempt exact request differs")
        if (
            binding.call_id,
            binding.model_candidate_id,
            binding.role,
            provider_request_content_sha256(binding),
        ) != (
            approved.call_id,
            approved.candidate_id,
            approved.role,
            approved.request_content_sha256,
        ):
            raise ValueError("qualification attempt request audit differs")
        if (
            provider_authorization.call_id,
            provider_authorization.segment,
            provider_authorization.model_candidate_id,
            provider_authorization.request_sha256,
            provider_authorization.retry_of_call_id,
            provider_authorization.authorized_max_cost_microusd,
        ) != (
            approved.call_id,
            BudgetSegment.QUALIFICATION,
            approved.candidate_id,
            approved.request_content_sha256,
            None,
            approved.authorized_max_cost_microusd,
        ):
            raise ValueError("qualification attempt provider authorization differs")
    finalizations = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    successful_ids = [
        call_id
        for call_id in planned_ids
        if call_id in finalizations
        and finalizations[call_id].outcome is ProviderCallOutcome.SUCCESS
    ]
    if [item.call_id for item in state.outputs] != successful_ids:
        raise ValueError("qualification attempt outputs differ from successes")
    for output in state.outputs:
        call = calls[planned_ids.index(output.call_id)]
        if (
            output.source_manifest_ordinal,
            output.qualification_entry_sha256,
            output.call_id,
            output.candidate_id,
            output.measure_id,
            output.measure_version,
            output.role,
            output.variant_id,
        ) != (
            call.source_manifest_ordinal,
            call.source_entry_sha256,
            call.call_id,
            call.candidate_id,
            call.measure_id,
            call.measure_version,
            call.role,
            call.variant_id.value,
        ) or finalizations[output.call_id].response_sha256 != output.output_sha256:
            raise ValueError("qualification attempt output audit differs")
    validation_diagnostics = {
        item.call_id: item for item in state.validation_diagnostics
    }
    provider_diagnostics = {
        item.call_id: item for item in state.provider_error_diagnostics
    }
    if set(validation_diagnostics) != {
        call_id
        for call_id, finalization in finalizations.items()
        if finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
    }:
        raise ValueError("qualification attempt validation diagnostics differ")
    if set(provider_diagnostics) != {
        call_id
        for call_id, finalization in finalizations.items()
        if finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR
    }:
        raise ValueError("qualification attempt provider diagnostics differ")
    replay_counts = Counter(item.call_id for item in state.tool_replay_records)
    request_roles = {
        item.call_id: item.role
        for item in state.provider_journal.request_bindings
    }
    if not set(replay_counts) <= set(finalizations):
        raise ValueError("qualification attempt tool replay lacks finalization")
    for call_id, finalization in finalizations.items():
        if request_roles[call_id] is LLMRole.INTERVIEWER:
            if replay_counts[call_id] != finalization.tool_call_count or (
                finalization.outcome is ProviderCallOutcome.SUCCESS
                and replay_counts[call_id] == 0
            ):
                raise ValueError("qualification attempt interviewer replay differs")
        elif replay_counts[call_id]:
            raise ValueError("qualification attempt non-interviewer used tools")
    last_outcome = (
        state.provider_journal.finalizations[-1].outcome
        if state.provider_journal.finalizations
        else None
    )
    outstanding = len(authorization_ids) != len(usage_ids)
    if state.status is QualificationAttemptV2ExecutionStatus.RUNNING:
        if outstanding or any(
            item.outcome is not ProviderCallOutcome.SUCCESS
            for item in state.provider_journal.finalizations
        ) or len(finalization_ids) >= len(planned_ids):
            raise ValueError("qualification attempt running state differs")
    elif state.status is QualificationAttemptV2ExecutionStatus.COMPLETED:
        if outstanding or len(finalization_ids) != len(planned_ids) or any(
            item.outcome is not ProviderCallOutcome.SUCCESS
            for item in state.provider_journal.finalizations
        ):
            raise ValueError("qualification attempt completion differs")
    elif (
        state.status
        is QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
    ):
        if outstanding or last_outcome is None or last_outcome in (
            set(AMENDED_SCOPE_PAUSE_OUTCOMES) | {ProviderCallOutcome.SUCCESS}
        ):
            raise ValueError("qualification attempt hard failure differs")
    elif (
        state.status
        is QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
    ):
        if outstanding or last_outcome not in set(AMENDED_SCOPE_PAUSE_OUTCOMES):
            raise ValueError("qualification attempt provider pause differs")
    elif (
        state.status
        is QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
    ):
        if not outstanding:
            raise ValueError("qualification attempt ambiguous delivery differs")
    elif (
        state.status
        is QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
    ):
        if outstanding:
            raise ValueError("qualification attempt harness pause is ambiguous")
    elif (
        state.status
        is QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE
    ) and (outstanding or any(
        item.outcome is not ProviderCallOutcome.SUCCESS
        for item in state.provider_journal.finalizations
    )):
        raise ValueError("qualification attempt sibling stop differs")
    if require_terminal and (
        state.status is QualificationAttemptV2ExecutionStatus.RUNNING
    ):
        raise ValueError("qualification attempt state is not terminal")
    if state.receipt is not None and _rebuild_receipt(
        state,
        proof,
        plan,
        candidate_plan,
        authorization,
    ) != state.receipt:
        raise ValueError("qualification attempt receipt does not rebuild")


def validate_qualification_attempt_v2_execution_states(
    states: Mapping[str, QualificationAttemptV2CandidateState],
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    authorization: QualificationAttemptV2AuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    """Reconcile both private states against the frozen global interleave."""

    candidate_ids = {item.candidate_id for item in plan.candidate_plans}
    if set(states) != candidate_ids:
        raise ValueError("qualification attempt execution states differ")
    for state in states.values():
        validate_qualification_attempt_v2_candidate_state(
            state,
            plan,
            proof,
            authorization,
            suite,
            profile,
            require_terminal=True,
        )
    bindings = {
        binding.call_id: binding
        for state in states.values()
        for binding in state.provider_journal.request_bindings
    }
    binding_count = sum(
        len(state.provider_journal.request_bindings)
        for state in states.values()
    )
    if len(bindings) != binding_count:
        raise ValueError("qualification attempt merged bindings are duplicated")
    binding_times = [binding.created_at for binding in bindings.values()]
    if len(binding_times) != len(set(binding_times)):
        raise ValueError("qualification attempt merged timestamps differ")
    observed_ids = [
        binding.call_id
        for binding in sorted(bindings.values(), key=lambda item: item.created_at)
    ]
    finalizations = {
        item.call_id: item
        for state in states.values()
        for item in state.provider_journal.finalizations
    }
    usages = {
        item.call_id: item
        for state in states.values()
        for item in state.provider_ledger.calls
    }
    provider_authorizations = {
        item.call_id: item
        for state in states.values()
        for item in state.provider_ledger.authorizations
    }
    global_stops = {
        (
            state.global_stop_call_id,
            state.global_stop_candidate_id,
            state.global_stop_status,
        )
        for state in states.values()
        if state.global_stop_call_id is not None
    }
    if len(global_stops) > 1:
        raise ValueError("qualification attempt global-stop records differ")
    global_stop = next(iter(global_stops), None)
    if global_stop is not None:
        stop_call_id, stop_candidate_id, stop_status = global_stop
        if (
            stop_call_id is None
            or stop_candidate_id is None
            or stop_candidate_id not in states
            or stop_status not in GLOBAL_PAUSE_STATUSES
            or states[stop_candidate_id].status is not stop_status
        ):
            raise ValueError("qualification attempt global-stop owner differs")
    expected_observed: list[str] = []
    hard_failed: set[str] = set()
    committed = ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    previous_completed_at: datetime | None = None
    calls = _planned_calls_by_id(plan)
    for call_id in plan.execution_order_call_ids:
        call = calls[call_id]
        if call.candidate_id in hard_failed:
            continue
        is_global_stop_call = global_stop is not None and (
            call_id == global_stop[0]
        )
        binding = bindings.get(call_id)
        if binding is None:
            if is_global_stop_call and global_stop[2] is (
                QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
            ):
                break
            raise ValueError("qualification attempt skipped a live coordinate")
        expected_observed.append(call_id)
        provider_authorization = provider_authorizations[call_id]
        if committed + provider_authorization.authorized_max_cost_microusd > (
            authorization.qualification_segment_cap_microusd
        ):
            raise ValueError("qualification attempt shared budget proof differs")
        if previous_completed_at is not None and binding.created_at <= (
            previous_completed_at
        ):
            raise ValueError("qualification attempt global chronology differs")
        finalization = finalizations.get(call_id)
        if finalization is None:
            if not is_global_stop_call or global_stop[2] is not (
                QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
            ):
                raise ValueError("qualification attempt completion is missing")
            break
        if finalization.created_at < binding.created_at:
            raise ValueError("qualification attempt completion predates request")
        previous_completed_at = finalization.created_at
        committed += usages[call_id].billed_cost_microusd
        if finalization.outcome is ProviderCallOutcome.SUCCESS:
            if is_global_stop_call:
                if global_stop[2] is not (
                    QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
                ):
                    raise ValueError("qualification attempt stop outcome differs")
                break
            continue
        if finalization.outcome in set(AMENDED_SCOPE_PAUSE_OUTCOMES):
            if not is_global_stop_call or global_stop[2] is not (
                QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE
            ):
                raise ValueError("qualification attempt provider pause differs")
            break
        hard_failed.add(call.candidate_id)
    if observed_ids != expected_observed:
        raise ValueError("qualification attempt global execution order differs")
    if global_stop is None:
        if any(state.status in GLOBAL_PAUSE_STATUSES for state in states.values()):
            raise ValueError("qualification attempt global pause lacks linkage")
        if any(
            state.status
            not in {
                QualificationAttemptV2ExecutionStatus.COMPLETED,
                QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE,
            }
            for state in states.values()
        ):
            raise ValueError("qualification attempt terminal statuses differ")


def _shared_committed_microusd(
    runtimes: Mapping[str, ProviderBudgetRuntime],
) -> int:
    return ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD + sum(
        provider_committed_totals(runtime.ledger_snapshot())[
            BudgetSegment.QUALIFICATION
        ]
        for runtime in runtimes.values()
    )


def execute_qualification_attempt_v2(
    plan: QualificationAttemptV2Plan,
    proof: QualificationAttemptV2SourceProof,
    scope: TwoDeploymentQualificationScopeAmendment,
    authorization: QualificationAttemptV2AuthorizationBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    transport: ProviderTransport,
    tool_auditor: AuditedQualificationInterviewerToolExecutor,
    *,
    clock: Callable[[], datetime],
    checkpoint: Callable[[str, QualificationAttemptV2CandidateState], None],
) -> dict[str, QualificationAttemptV2CandidateState]:
    """Execute the exact paired order once with frozen local/global stops."""

    _validate_attempt_v2_sources(
        plan,
        proof,
        scope,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    candidates = _candidate_plans_by_id(plan)
    calls = _planned_calls_by_id(plan)
    entries = {
        item.coordinate.call_id: item
        for item in readiness.qualification_manifest.entries
    }
    exact = {item.call_id: item for item in authorization.authorized_requests}
    runtimes = {
        candidate_id: ProviderBudgetRuntime(
            profile,
            ledger_id=f"{plan.plan_id}_{candidate_id}_attempt_v2_ledger",
            journal_id=f"{plan.plan_id}_{candidate_id}_attempt_v2_journal",
        )
        for candidate_id in candidates
    }
    outputs: dict[str, list[QualificationOutputRecord]] = {
        candidate_id: [] for candidate_id in candidates
    }
    replays: dict[str, list[QualificationToolReplayRecord]] = {
        candidate_id: [] for candidate_id in candidates
    }
    validation_diagnostics: dict[
        str, list[ProviderStructuredOutputDiagnostic]
    ] = {candidate_id: [] for candidate_id in candidates}
    provider_diagnostics: dict[str, list[ProviderHTTPErrorDiagnostic]] = {
        candidate_id: [] for candidate_id in candidates
    }
    states: dict[str, QualificationAttemptV2CandidateState] = {}
    hard_failed: set[str] = set()
    global_stop: tuple[
        str,
        str,
        QualificationAttemptV2ExecutionStatus,
        QualificationAttemptV2HarnessFailureCode | None,
    ] | None = None

    def build_state(
        candidate_id: str,
        status: QualificationAttemptV2ExecutionStatus,
        *,
        terminal: bool,
        harness_code: QualificationAttemptV2HarnessFailureCode | None = None,
        stop_call_id: str | None = None,
        stop_candidate_id: str | None = None,
        stop_status: QualificationAttemptV2ExecutionStatus | None = None,
    ) -> QualificationAttemptV2CandidateState:
        state = _candidate_state(
            state_id=f"{plan.plan_id}_{candidate_id}_state_v2",
            proof=proof,
            plan=plan,
            candidate_plan=candidates[candidate_id],
            authorization=authorization,
            candidate_id=candidate_id,
            runtime=runtimes[candidate_id],
            outputs=outputs[candidate_id],
            tool_replays=replays[candidate_id],
            validation_diagnostics=validation_diagnostics[candidate_id],
            provider_diagnostics=provider_diagnostics[candidate_id],
            status=status,
            completed_at=clock() if terminal else None,
            harness_failure_code=harness_code,
            global_stop_call_id=stop_call_id,
            global_stop_candidate_id=stop_candidate_id,
            global_stop_status=stop_status,
        )
        if terminal:
            validate_qualification_attempt_v2_candidate_state(
                state,
                plan,
                proof,
                authorization,
                suite,
                profile,
                require_terminal=True,
            )
        checkpoint(candidate_id, state)
        states[candidate_id] = state
        return state

    for call_id in plan.execution_order_call_ids:
        call = calls[call_id]
        candidate_id = call.candidate_id
        if candidate_id in hard_failed:
            continue
        approved = exact[call_id]
        if _shared_committed_microusd(runtimes) + (
            approved.authorized_max_cost_microusd
        ) > authorization.qualification_segment_cap_microusd:
            status = QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
            code = QualificationAttemptV2HarnessFailureCode.SHARED_BUDGET_GATE
            build_state(
                candidate_id,
                status,
                terminal=True,
                harness_code=code,
                stop_call_id=call_id,
                stop_candidate_id=candidate_id,
                stop_status=status,
            )
            global_stop = (call_id, candidate_id, status, code)
            break
        entry = entries.get(call_id)
        if entry is None or entry != call.source_entry or (
            content_sha256(entry) != call.source_entry_sha256
        ):
            status = QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
            code = QualificationAttemptV2HarnessFailureCode.SOURCE_ENTRY_MISMATCH
            build_state(
                candidate_id,
                status,
                terminal=True,
                harness_code=code,
                stop_call_id=call_id,
                stop_candidate_id=candidate_id,
                stop_status=status,
            )
            global_stop = (call_id, candidate_id, status, code)
            break
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=clock(),
        )
        if provider_request_content_sha256(rebuilt.request.binding) != (
            approved.request_content_sha256
        ):
            status = QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
            code = QualificationAttemptV2HarnessFailureCode.REQUEST_REBUILD_MISMATCH
            build_state(
                candidate_id,
                status,
                terminal=True,
                harness_code=code,
                stop_call_id=call_id,
                stop_candidate_id=candidate_id,
                stop_status=status,
            )
            global_stop = (call_id, candidate_id, status, code)
            break
        interviewer = entry.coordinate.role is LLMRole.INTERVIEWER
        if interviewer:
            tool_auditor.begin_call(call_id)
        try:
            result = runtimes[candidate_id].execute(
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
            if interviewer:
                replays[candidate_id].extend(tool_auditor.end_call())
            if result.output is not None:
                payload = rebuilt.response_adapter.dump_python(
                    result.output,
                    mode="json",
                )
                outputs[candidate_id].append(
                    QualificationOutputRecord(
                        source_manifest_ordinal=entry.coordinate.ordinal,
                        qualification_entry_sha256=content_sha256(entry),
                        call_id=call_id,
                        candidate_id=candidate_id,
                        measure_id=entry.coordinate.measure_id,
                        measure_version=entry.coordinate.measure_version,
                        role=entry.coordinate.role,
                        variant_id=entry.coordinate.variant_id.value,
                        output_sha256=content_sha256(payload),
                        output_payload=payload,
                    )
                )
            if result.validation_diagnostic is not None:
                validation_diagnostics[candidate_id].append(
                    result.validation_diagnostic
                )
            if result.provider_error_diagnostic is not None:
                provider_diagnostics[candidate_id].append(
                    result.provider_error_diagnostic
                )
        except Exception as error:
            if interviewer:
                try:
                    replays[candidate_id].extend(tool_auditor.end_call())
                except ValueError:
                    pass
            ledger = runtimes[candidate_id].ledger_snapshot()
            ambiguous = isinstance(error, TogetherAmbiguousDeliveryError) or (
                len(ledger.authorizations) != len(ledger.calls)
            )
            status = (
                QualificationAttemptV2ExecutionStatus.GLOBAL_AMBIGUOUS_DELIVERY
                if ambiguous
                else QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
            )
            code = (
                None
                if ambiguous
                else QualificationAttemptV2HarnessFailureCode.LOCAL_EXECUTION_EXCEPTION
            )
            build_state(
                candidate_id,
                status,
                terminal=True,
                harness_code=code,
                stop_call_id=call_id,
                stop_candidate_id=candidate_id,
                stop_status=status,
            )
            global_stop = (call_id, candidate_id, status, code)
            break
        outcome = result.finalization.outcome
        terminal = outcome is not ProviderCallOutcome.SUCCESS
        if terminal:
            status = _terminal_status_for(outcome)
        else:
            completed_count = len(
                runtimes[candidate_id].journal_snapshot().finalizations
            )
            status = (
                QualificationAttemptV2ExecutionStatus.COMPLETED
                if completed_count == len(
                    _ordered_candidate_calls(plan, candidate_id)
                )
                else QualificationAttemptV2ExecutionStatus.RUNNING
            )
            terminal = status is QualificationAttemptV2ExecutionStatus.COMPLETED
        if status is QualificationAttemptV2ExecutionStatus.GLOBAL_PROVIDER_PAUSE:
            build_state(
                candidate_id,
                status,
                terminal=True,
                stop_call_id=call_id,
                stop_candidate_id=candidate_id,
                stop_status=status,
            )
            global_stop = (call_id, candidate_id, status, None)
            break
        build_state(candidate_id, status, terminal=terminal)
        if status is (
            QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE
        ):
            hard_failed.add(candidate_id)

    if global_stop is not None:
        stop_call_id, owner_id, stop_status, harness_code = global_stop
        for candidate_id in candidates:
            existing = states.get(candidate_id)
            if candidate_id == owner_id or (
                existing is not None
                and existing.status
                in {
                    QualificationAttemptV2ExecutionStatus.COMPLETED,
                    QualificationAttemptV2ExecutionStatus.CANDIDATE_HARD_FAILURE,
                }
            ):
                continue
            build_state(
                candidate_id,
                QualificationAttemptV2ExecutionStatus.STOPPED_BY_GLOBAL_PAUSE,
                terminal=True,
                harness_code=(
                    harness_code
                    if stop_status
                    is QualificationAttemptV2ExecutionStatus.GLOBAL_HARNESS_PAUSE
                    else None
                ),
                stop_call_id=stop_call_id,
                stop_candidate_id=owner_id,
                stop_status=stop_status,
            )
    for candidate_id in candidates:
        state = states.get(candidate_id)
        if state is None or state.status is (
            QualificationAttemptV2ExecutionStatus.RUNNING
        ):
            raise ValueError("qualification attempt left a candidate unterminated")
    validate_qualification_attempt_v2_execution_states(
        states,
        plan,
        proof,
        authorization,
        suite,
        profile,
    )
    return states


def qualification_attempt_v2_candidate_state_summary(
    state: QualificationAttemptV2CandidateState,
) -> dict[str, JsonValue]:
    return {
        "schema_version": state.schema_version,
        "state_sha256": content_sha256(state),
        "status": state.status.value,
        "authorized_call_count": len(state.provider_ledger.authorizations),
        "completed_call_count": len(state.provider_ledger.calls),
        "successful_output_count": len(state.outputs),
        "provider_spend_microusd": sum(
            item.billed_cost_microusd for item in state.provider_ledger.calls
        ),
        "participant_content_present": False,
    }
