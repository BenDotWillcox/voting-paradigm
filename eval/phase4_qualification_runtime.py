"""Paid runtime boundary for the reviewed two-deployment qualification.

This module deliberately does not extend the historical three-candidate live
authorization or qualification bundle.  It binds the reviewed scope amendment
to an exact 294-request authorization, keeps GLM and GPT-OSS provider audits in
separate progressive states, and treats any provider/transport failure as a
selection-blocking pause.

The content-bearing authorization and execution states belong only below
``eval/private_runs``.  Tracked artifacts may contain only the content-free
execution plan and aggregate result produced by the adjacent modules.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal, Self

import httpx
from pydantic import Field, SecretStr, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import CapabilityInterviewerTools, TogetherCapabilityPlan
from .phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderBudgetRuntime,
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderExecutionJournal,
    ProviderHTTPErrorDiagnostic,
    ProviderPriceCard,
    ProviderRequestBinding,
    ProviderStructuredOutputDiagnostic,
    ProviderTransport,
    price_provider_tokens,
    provider_request_content_sha256,
    provider_committed_totals,
    validate_provider_execution_journal,
)
from .phase4_qualification_execution import (
    CapabilitySourceState,
    QualificationCallDisposition,
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentCandidateQualificationPlan,
    TwoDeploymentQualificationCallPlan,
    TwoDeploymentQualificationExecutionPlan,
    validate_two_deployment_carry_bundle,
    validate_two_deployment_qualification_plan,
)
from .phase4_capability_aggregation import Phase4CapabilityAggregation
from .phase4_qualification_scope import (
    AMENDED_SCOPE_PAUSE_OUTCOMES,
    NEW_PROVIDER_CALL_COUNT,
    TwoDeploymentQualificationScopeAmendment,
    TwoDeploymentQualificationScopeEvidenceProof,
    validate_two_deployment_qualification_scope,
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
    DEFAULT_MAX_TOOL_ROUNDS,
    TogetherAmbiguousDeliveryError,
    TogetherCatalogPreflightBundle,
    TogetherInterviewerToolExecutor,
    TogetherTokenCounter,
    _build_together_invocation_core,
    validate_catalog_preflight_bundle,
)
from .prequential import PrequentialSessionScript


Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]

QUALIFICATION_APPROVAL_MAXIMUM_DURATION = timedelta(hours=8)
QUALIFICATION_CATALOG_MAXIMUM_AGE_AT_APPROVAL = timedelta(minutes=30)
QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD = 2_297_400
QUALIFICATION_PRIOR_SPEND_MICROUSD = 51_042
QUALIFICATION_SEGMENT_CAP_MICROUSD = 4_000_000
QUALIFICATION_CANDIDATE_CALL_COUNT = 147
QUALIFICATION_CARRIED_CALL_COUNT_PER_CANDIDATE = 5


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class QualificationExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    CANDIDATE_HARD_FAILURE = "candidate_hard_failure"
    PROVIDER_PAUSED = "provider_pause_pending_review"
    AMBIGUOUS_DELIVERY = "ambiguous_delivery_pending_reconciliation"
    HARNESS_PAUSED = "harness_pause_pending_review"


class QualificationHarnessFailureCode(str, Enum):
    """Content-free local failure classes that block selection."""

    SHARED_BUDGET_GATE = "shared_budget_gate"
    SOURCE_ENTRY_MISMATCH = "source_entry_mismatch"
    REQUEST_REBUILD_MISMATCH = "request_rebuild_mismatch"
    LOCAL_EXECUTION_EXCEPTION = "local_execution_exception"


class ExactQualificationRequestAuthorization(ContractModel):
    """One exact, content-addressed new request approved for paid execution."""

    record_version: Literal[
        "phase4_two_deployment_authorized_request.v1"
    ] = "phase4_two_deployment_authorized_request.v1"
    source_manifest_ordinal: PositiveCount
    qualification_entry_sha256: Sha256Digest
    call_id: StableId
    candidate_id: StableId
    role: LLMRole
    request_content_sha256: Sha256Digest
    authorized_max_cost_microusd: PositiveCount


class TwoDeploymentQualificationManualApproval(ContractModel):
    """Fresh private user approval for the exact two-deployment request set."""

    record_version: Literal[
        "phase4_two_deployment_qualification_manual_approval.v1"
    ] = "phase4_two_deployment_qualification_manual_approval.v1"
    approval_id: StableId
    approval_version: Literal[1] = 1
    scope_amendment_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    carry_bundle_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    exact_request_set_sha256: Sha256Digest
    approved_call_count: Literal[294] = NEW_PROVIDER_CALL_COUNT
    approved_max_spend_microusd: Literal[2_297_400] = (
        QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
    )
    public_development_inputs_only: Literal[True] = True
    participant_content_forbidden: Literal[True] = True
    automatic_retry_forbidden: Literal[True] = True
    fallback_and_replacement_forbidden: Literal[True] = True
    user_confirmed_paid_execution: Literal[True] = True
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "qualification approval time")
        return value

    @model_validator(mode="after")
    def require_short_forward_window(self) -> Self:
        duration = self.expires_at - self.approved_at
        if duration <= timedelta(0) or duration > (
            QUALIFICATION_APPROVAL_MAXIMUM_DURATION
        ):
            raise ValueError("qualification approval window is invalid")
        return self


class TwoDeploymentQualificationAuthorizationBundle(ContractModel):
    """Distinct exact-request authorization for the amended paid path."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_authorization.v1"
    ] = "preference_eval_phase4_two_deployment_authorization.v1"
    bundle_id: StableId
    bundle_version: Literal[1] = 1
    scope_amendment_sha256: Sha256Digest
    scope_evidence_proof_sha256: Sha256Digest
    execution_plan_sha256: Sha256Digest
    carry_bundle_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    readiness_sha256: Sha256Digest
    source_qualification_manifest_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    account_privacy_attestation_sha256: Sha256Digest
    catalog_preflight_receipt_sha256: Sha256Digest
    token_readiness_receipt_sha256: Sha256Digest
    headroom_policy_sha256: Sha256Digest
    manual_approval: TwoDeploymentQualificationManualApproval
    authorized_requests: list[ExactQualificationRequestAuthorization] = Field(
        min_length=NEW_PROVIDER_CALL_COUNT,
        max_length=NEW_PROVIDER_CALL_COUNT,
    )
    authorized_candidate_ids: list[StableId]
    authorized_roles: list[LLMRole]
    prior_qualification_spend_microusd: Literal[51_042] = (
        QUALIFICATION_PRIOR_SPEND_MICROUSD
    )
    new_authorized_max_spend_microusd: Literal[2_297_400] = (
        QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
    )
    qualification_segment_cap_microusd: Literal[4_000_000] = (
        QUALIFICATION_SEGMENT_CAP_MICROUSD
    )
    budget_segment: Literal[BudgetSegment.QUALIFICATION] = (
        BudgetSegment.QUALIFICATION
    )

    @model_validator(mode="after")
    def require_exact_scope(self) -> Self:
        request_ids = [item.call_id for item in self.authorized_requests]
        ordinals = [
            item.source_manifest_ordinal for item in self.authorized_requests
        ]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("qualification authorized call ids must be unique")
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("qualification authorized ordinals must be canonical")
        candidates = sorted(
            {item.candidate_id for item in self.authorized_requests}
        )
        roles = sorted(
            {item.role for item in self.authorized_requests},
            key=lambda item: item.value,
        )
        if self.authorized_candidate_ids != candidates or len(candidates) != 2:
            raise ValueError("qualification exact-request candidates differ")
        if self.authorized_roles != roles or set(roles) != set(LLMRole):
            raise ValueError("qualification exact-request roles differ")
        if sum(
            item.authorized_max_cost_microusd
            for item in self.authorized_requests
        ) != self.new_authorized_max_spend_microusd:
            raise ValueError("qualification exact-request spend differs")
        if self.prior_qualification_spend_microusd + (
            self.new_authorized_max_spend_microusd
        ) > self.qualification_segment_cap_microusd:
            raise ValueError("qualification authorization exceeds segment cap")
        expected_request_hash = content_sha256(
            [item.model_dump(mode="json") for item in self.authorized_requests]
        )
        if self.manual_approval.exact_request_set_sha256 != expected_request_hash:
            raise ValueError("qualification manual request-set hash differs")
        approval_bindings = (
            self.manual_approval.scope_amendment_sha256,
            self.manual_approval.execution_plan_sha256,
            self.manual_approval.carry_bundle_sha256,
            self.manual_approval.catalog_preflight_bundle_sha256,
        )
        bundle_bindings = (
            self.scope_amendment_sha256,
            self.execution_plan_sha256,
            self.carry_bundle_sha256,
            self.catalog_preflight_bundle_sha256,
        )
        if approval_bindings != bundle_bindings:
            raise ValueError("qualification manual approval bindings differ")
        return self


class QualificationOutputRecord(ContractModel):
    """Private canonical parsed output for one successful new call."""

    record_version: Literal[
        "phase4_two_deployment_qualification_output.v1"
    ] = "phase4_two_deployment_qualification_output.v1"
    source_manifest_ordinal: PositiveCount
    qualification_entry_sha256: Sha256Digest
    call_id: StableId
    candidate_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    role: LLMRole
    variant_id: StableId
    output_sha256: Sha256Digest
    output_payload: JsonValue

    @model_validator(mode="after")
    def require_bound_payload(self) -> Self:
        if self.output_sha256 != content_sha256(self.output_payload):
            raise ValueError("qualification output hash does not match payload")
        return self


class QualificationToolReplayRecord(ContractModel):
    """Private local replay proof for one interviewer tool invocation."""

    record_version: Literal[
        "phase4_qualification_tool_replay.v1"
    ] = "phase4_qualification_tool_replay.v1"
    call_id: StableId
    tool_call_index: PositiveCount
    tool_name: StableId
    arguments_sha256: Sha256Digest
    result_sha256: Sha256Digest
    replay_result_sha256: Sha256Digest
    arguments_payload: JsonValue = Field(repr=False)
    result_payload: JsonValue = Field(repr=False)
    replay_result_payload: JsonValue = Field(repr=False)
    replay_matches: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_hashes(self) -> Self:
        if (
            self.arguments_sha256 != content_sha256(self.arguments_payload)
            or self.result_sha256 != content_sha256(self.result_payload)
            or self.replay_result_sha256
            != content_sha256(self.replay_result_payload)
            or self.result_sha256 != self.replay_result_sha256
        ):
            raise ValueError("qualification tool replay differs")
        return self


class QualificationCandidateReceipt(ContractModel):
    """Content-free terminal receipt for one runnable deployment."""

    record_version: Literal[
        "phase4_two_deployment_candidate_receipt.v1"
    ] = "phase4_two_deployment_candidate_receipt.v1"
    receipt_id: StableId
    receipt_version: Literal[1] = 1
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    candidate_id: StableId
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    output_records_sha256: Sha256Digest
    tool_replay_records_sha256: Sha256Digest
    status: QualificationExecutionStatus
    completed_new_call_count: NonNegativeCount
    successful_new_call_count: NonNegativeCount
    provider_spend_microusd: Microusd
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        _require_aware(value, "qualification candidate receipt time")
        return value

    @model_validator(mode="after")
    def require_terminal_status(self) -> Self:
        if self.status in {
            QualificationExecutionStatus.NOT_STARTED,
            QualificationExecutionStatus.RUNNING,
        }:
            raise ValueError("qualification candidate receipt must be terminal")
        if self.successful_new_call_count > self.completed_new_call_count:
            raise ValueError("qualification successful calls exceed completions")
        return self


class TwoDeploymentCandidateExecutionState(ContractModel):
    """Private candidate-isolated audit containing new provider calls only."""

    schema_version: Literal[
        "preference_eval_phase4_two_deployment_candidate_state.v1"
    ] = "preference_eval_phase4_two_deployment_candidate_state.v1"
    state_id: StableId
    state_version: Literal[1] = 1
    execution_plan_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    carry_record_sha256s: list[Sha256Digest] = Field(
        min_length=QUALIFICATION_CARRIED_CALL_COUNT_PER_CANDIDATE,
        max_length=QUALIFICATION_CARRIED_CALL_COUNT_PER_CANDIDATE,
    )
    candidate_id: StableId
    status: QualificationExecutionStatus
    provider_ledger: ProviderUsageLedger
    provider_journal: ProviderExecutionJournal
    outputs: list[QualificationOutputRecord]
    tool_replay_records: list[QualificationToolReplayRecord]
    validation_diagnostics: list[ProviderStructuredOutputDiagnostic]
    provider_error_diagnostics: list[ProviderHTTPErrorDiagnostic]
    harness_failure_code: QualificationHarnessFailureCode | None = None
    receipt: QualificationCandidateReceipt | None = None

    @model_validator(mode="after")
    def require_unique_private_records(self) -> Self:
        if len(self.carry_record_sha256s) != len(
            set(self.carry_record_sha256s)
        ):
            raise ValueError("qualification carry hashes must be unique")
        for values, label in (
            (self.outputs, "outputs"),
            (self.validation_diagnostics, "validation diagnostics"),
            (self.provider_error_diagnostics, "provider diagnostics"),
        ):
            call_ids = [item.call_id for item in values]
            if len(call_ids) != len(set(call_ids)):
                raise ValueError(f"qualification {label} must be unique")
        replay_keys = [
            (item.call_id, item.tool_call_index)
            for item in self.tool_replay_records
        ]
        if len(replay_keys) != len(set(replay_keys)):
            raise ValueError("qualification tool replays must be unique")
        if self.receipt is None and self.status in {
            QualificationExecutionStatus.COMPLETED,
            QualificationExecutionStatus.CANDIDATE_HARD_FAILURE,
            QualificationExecutionStatus.PROVIDER_PAUSED,
            QualificationExecutionStatus.AMBIGUOUS_DELIVERY,
            QualificationExecutionStatus.HARNESS_PAUSED,
        }:
            raise ValueError("terminal qualification state requires receipt")
        if self.receipt is not None and self.receipt.status is not self.status:
            raise ValueError("qualification receipt status differs")
        if (self.status is QualificationExecutionStatus.HARNESS_PAUSED) != (
            self.harness_failure_code is not None
        ):
            raise ValueError("qualification harness failure code differs")
        return self


class AuditedQualificationInterviewerToolExecutor:
    """Replay each deterministic local tool call and retain private proof."""

    def __init__(self, tools: CapabilityInterviewerTools) -> None:
        self._delegate = TogetherInterviewerToolExecutor(tools)
        self._current_call_id: str | None = None
        self._records: list[QualificationToolReplayRecord] = []

    def begin_call(self, call_id: str) -> None:
        if self._current_call_id is not None:
            raise ValueError("qualification tool audit already has an active call")
        self._current_call_id = call_id

    def end_call(self) -> list[QualificationToolReplayRecord]:
        if self._current_call_id is None:
            raise ValueError("qualification tool audit has no active call")
        call_id = self._current_call_id
        self._current_call_id = None
        return [
            item.model_copy(deep=True)
            for item in self._records
            if item.call_id == call_id
        ]

    def execute(self, name: str, arguments: JsonValue) -> JsonValue:
        call_id = self._current_call_id
        if call_id is None:
            raise ValueError("qualification tool call lacks an active provider call")
        result = self._delegate.execute(name, arguments)
        replay = self._delegate.execute(name, arguments)
        if content_sha256(result) != content_sha256(replay):
            raise ValueError("qualification interviewer tool replay differs")
        record = QualificationToolReplayRecord(
            call_id=call_id,
            tool_call_index=(
                1 + sum(item.call_id == call_id for item in self._records)
            ),
            tool_name=name,
            arguments_sha256=content_sha256(arguments),
            result_sha256=content_sha256(result),
            replay_result_sha256=content_sha256(replay),
            arguments_payload=arguments,
            result_payload=result,
            replay_result_payload=replay,
        )
        self._records.append(record)
        return result


class ScopedQualificationTogetherTransport:
    """Together transport reachable only through the distinct scoped auth."""

    def __init__(
        self,
        authorization: TwoDeploymentQualificationAuthorizationBundle,
        scope: TwoDeploymentQualificationScopeAmendment,
        proof: TwoDeploymentQualificationScopeEvidenceProof,
        plan: TwoDeploymentQualificationExecutionPlan,
        carry: TwoDeploymentQualificationCarryBundle,
        aggregation: Phase4CapabilityAggregation,
        corrected_capability_plan: TogetherCapabilityPlan,
        suite: Phase4TogetherSuite,
        profile: Phase4ERobustnessProfile,
        readiness: Phase4TogetherReadinessBundle,
        fixture: EvaluationFixture,
        session: PrequentialSessionScript,
        semantic_map: AuthoredSemanticMapBundle,
        source_states: Sequence[CapabilitySourceState],
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
        validate_two_deployment_qualification_authorization(
            authorization,
            scope,
            proof,
            plan,
            carry,
            aggregation,
            corrected_capability_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            source_states,
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
        now = self._clock()
        _require_aware(now, "Together scoped execution time")
        approval = self._authorization.manual_approval
        if not approval.approved_at <= now <= approval.expires_at:
            raise ValueError("qualification manual approval is not active")
        if segment is not BudgetSegment.QUALIFICATION:
            raise ValueError("qualification request uses another budget segment")
        binding = request.binding
        if binding.data_scope is not ProviderDataScope.PUBLIC_DEVELOPMENT:
            raise ValueError("qualification request is not public development")
        if binding.robustness_profile_sha256 != self._profile_sha256:
            raise ValueError("qualification request uses another profile")
        exact = self._exact.get(binding.call_id)
        if exact is None:
            raise ValueError("qualification request is not exactly authorized")
        identity = (
            binding.model_candidate_id,
            binding.role,
            provider_request_content_sha256(binding),
        )
        expected = (
            exact.candidate_id,
            exact.role,
            exact.request_content_sha256,
        )
        if identity != expected:
            raise ValueError("qualification exact request binding differs")
        price_card = self._price_cards.get(binding.model_candidate_id)
        if price_card is None:
            raise ValueError("qualification request candidate is unauthorized")
        maximum = price_provider_tokens(
            price_card,
            input_tokens=binding.input_token_upper_bound,
            output_tokens=binding.output_token_upper_bound,
        )
        if maximum != exact.authorized_max_cost_microusd:
            raise ValueError("qualification exact request cost differs")
        count = self._core.count_initial_payload(request)
        if count.input_token_count > binding.input_token_upper_bound:
            raise ValueError("Together exact input count exceeds request bound")

    def invoke(self, request: PrivateStructuredProviderRequest):
        return self._core.invoke(request)


def _new_entries(
    plan: TwoDeploymentQualificationExecutionPlan,
    readiness: Phase4TogetherReadinessBundle,
) -> list[QualificationCallPlanEntry]:
    entries_by_ordinal = {
        item.coordinate.ordinal: item
        for item in readiness.qualification_manifest.entries
    }
    calls = [
        call
        for candidate in plan.candidate_plans
        for call in candidate.calls
        if call.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    ]
    return [entries_by_ordinal[item.source_manifest_ordinal] for item in calls]


def _build_exact_authorized_requests(
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    approved_at: datetime,
) -> list[ExactQualificationRequestAuthorization]:
    entries = _new_entries(plan, readiness)
    carried_ids = {item.call_id for item in carry.records}
    exact: list[ExactQualificationRequestAuthorization] = []
    for index, entry in enumerate(entries):
        if entry.coordinate.call_id in carried_ids:
            raise ValueError("carried qualification call cannot be authorized")
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=approved_at + timedelta(microseconds=index + 1),
        )
        exact.append(
            ExactQualificationRequestAuthorization(
                source_manifest_ordinal=entry.coordinate.ordinal,
                qualification_entry_sha256=content_sha256(entry),
                call_id=entry.coordinate.call_id,
                candidate_id=entry.coordinate.candidate_id,
                role=entry.coordinate.role,
                request_content_sha256=provider_request_content_sha256(
                    rebuilt.request.binding
                ),
                authorized_max_cost_microusd=(
                    entry.authorized_max_cost_microusd
                ),
            )
        )
    return exact


def build_two_deployment_qualification_authorization(
    scope: TwoDeploymentQualificationScopeAmendment,
    proof: TwoDeploymentQualificationScopeEvidenceProof,
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    aggregation: Phase4CapabilityAggregation,
    corrected_capability_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_states: Sequence[CapabilitySourceState],
    catalog: TogetherCatalogPreflightBundle,
    *,
    bundle_id: str,
    approval_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TwoDeploymentQualificationAuthorizationBundle:
    """Rebuild and authorize only the exact 294 non-carried requests."""

    validate_two_deployment_qualification_plan(
        plan,
        scope,
        proof,
        readiness,
    )
    validate_two_deployment_carry_bundle(
        carry,
        plan,
        scope,
        proof,
        aggregation,
        corrected_capability_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        source_states,
    )
    validate_catalog_preflight_bundle(suite, catalog)
    _require_aware(approved_at, "qualification approval time")
    if catalog.receipt.checked_at > approved_at or approved_at - (
        catalog.receipt.checked_at
    ) > QUALIFICATION_CATALOG_MAXIMUM_AGE_AT_APPROVAL:
        raise ValueError("qualification catalog preflight is not fresh")
    if catalog.receipt.checked_at <= scope.created_at:
        raise ValueError("qualification catalog preflight predates scope")
    exact = _build_exact_authorized_requests(
        plan,
        carry,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        approved_at=approved_at,
    )
    manual = TwoDeploymentQualificationManualApproval(
        approval_id=approval_id,
        scope_amendment_sha256=content_sha256(scope),
        execution_plan_sha256=content_sha256(plan),
        carry_bundle_sha256=content_sha256(carry),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        exact_request_set_sha256=content_sha256(
            [item.model_dump(mode="json") for item in exact]
        ),
        approved_at=approved_at,
        expires_at=expires_at,
    )
    bundle = TwoDeploymentQualificationAuthorizationBundle(
        bundle_id=bundle_id,
        scope_amendment_sha256=content_sha256(scope),
        scope_evidence_proof_sha256=content_sha256(proof),
        execution_plan_sha256=content_sha256(plan),
        carry_bundle_sha256=content_sha256(carry),
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        readiness_sha256=content_sha256(readiness),
        source_qualification_manifest_sha256=content_sha256(
            readiness.qualification_manifest
        ),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        account_privacy_attestation_sha256=content_sha256(
            catalog.account_privacy_attestation
        ),
        catalog_preflight_receipt_sha256=content_sha256(catalog.receipt),
        token_readiness_receipt_sha256=content_sha256(
            readiness.token_readiness_receipt
        ),
        headroom_policy_sha256=content_sha256(readiness.headroom_policy),
        manual_approval=manual,
        authorized_requests=exact,
        authorized_candidate_ids=list(scope.runnable_candidate_ids),
        authorized_roles=sorted(LLMRole, key=lambda item: item.value),
    )
    validate_two_deployment_qualification_authorization(
        bundle,
        scope,
        proof,
        plan,
        carry,
        aggregation,
        corrected_capability_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        source_states,
        catalog,
        now=approved_at,
    )
    return bundle


def validate_two_deployment_qualification_authorization(
    bundle: TwoDeploymentQualificationAuthorizationBundle,
    scope: TwoDeploymentQualificationScopeAmendment,
    proof: TwoDeploymentQualificationScopeEvidenceProof,
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    aggregation: Phase4CapabilityAggregation,
    corrected_capability_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    source_states: Sequence[CapabilitySourceState],
    catalog: TogetherCatalogPreflightBundle,
    *,
    now: datetime,
) -> None:
    """Rebuild every exact request and all paid boundary bindings."""

    _require_aware(now, "qualification authorization validation time")
    validate_two_deployment_qualification_plan(
        plan,
        scope,
        proof,
        readiness,
    )
    validate_two_deployment_carry_bundle(
        carry,
        plan,
        scope,
        proof,
        aggregation,
        corrected_capability_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        source_states,
    )
    validate_catalog_preflight_bundle(suite, catalog)
    expected_bindings = (
        content_sha256(scope),
        content_sha256(proof),
        content_sha256(plan),
        content_sha256(carry),
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(readiness),
        content_sha256(readiness.qualification_manifest),
        content_sha256(catalog),
        content_sha256(catalog.account_privacy_attestation),
        content_sha256(catalog.receipt),
        content_sha256(readiness.token_readiness_receipt),
        content_sha256(readiness.headroom_policy),
    )
    actual_bindings = (
        bundle.scope_amendment_sha256,
        bundle.scope_evidence_proof_sha256,
        bundle.execution_plan_sha256,
        bundle.carry_bundle_sha256,
        bundle.together_suite_sha256,
        bundle.robustness_profile_sha256,
        bundle.readiness_sha256,
        bundle.source_qualification_manifest_sha256,
        bundle.catalog_preflight_bundle_sha256,
        bundle.account_privacy_attestation_sha256,
        bundle.catalog_preflight_receipt_sha256,
        bundle.token_readiness_receipt_sha256,
        bundle.headroom_policy_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("qualification authorization artifact hashes differ")
    if not bundle.manual_approval.approved_at <= now <= (
        bundle.manual_approval.expires_at
    ):
        raise ValueError("qualification manual approval is not active")
    if (
        catalog.receipt.checked_at > bundle.manual_approval.approved_at
        or bundle.manual_approval.approved_at - catalog.receipt.checked_at
        > QUALIFICATION_CATALOG_MAXIMUM_AGE_AT_APPROVAL
        or catalog.receipt.checked_at <= scope.created_at
    ):
        raise ValueError("qualification catalog preflight is not fresh")
    expected_requests = _build_exact_authorized_requests(
        plan,
        carry,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        approved_at=bundle.manual_approval.approved_at,
    )
    if expected_requests != bundle.authorized_requests:
        raise ValueError("qualification exact requests do not rebuild")


def qualification_authorization_summary(
    bundle: TwoDeploymentQualificationAuthorizationBundle,
) -> dict[str, JsonValue]:
    return {
        "schema_version": bundle.schema_version,
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": content_sha256(bundle),
        "candidate_count": len(bundle.authorized_candidate_ids),
        "authorized_call_count": len(bundle.authorized_requests),
        "authorized_max_spend_microusd": (
            bundle.new_authorized_max_spend_microusd
        ),
        "prior_qualification_spend_microusd": (
            bundle.prior_qualification_spend_microusd
        ),
        "participant_content_present": False,
    }


def _candidate_plan_for(
    plan: TwoDeploymentQualificationExecutionPlan,
    candidate_id: str,
) -> TwoDeploymentCandidateQualificationPlan:
    matches = [
        item for item in plan.candidate_plans if item.candidate_id == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("qualification candidate plan is missing or duplicated")
    return matches[0]


def _candidate_new_calls(
    candidate_plan: TwoDeploymentCandidateQualificationPlan,
) -> list[TwoDeploymentQualificationCallPlan]:
    return [
        item
        for item in candidate_plan.calls
        if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    ]


def _candidate_carry_hashes(
    carry: TwoDeploymentQualificationCarryBundle,
    candidate_id: str,
) -> list[str]:
    records = [
        item for item in carry.records if item.candidate_id == candidate_id
    ]
    if len(records) != QUALIFICATION_CARRIED_CALL_COUNT_PER_CANDIDATE:
        raise ValueError("qualification candidate carry count differs")
    return [content_sha256(item) for item in records]


def _terminal_status_for(
    finalization_outcome: ProviderCallOutcome,
) -> QualificationExecutionStatus:
    if finalization_outcome in set(AMENDED_SCOPE_PAUSE_OUTCOMES):
        return QualificationExecutionStatus.PROVIDER_PAUSED
    if finalization_outcome is not ProviderCallOutcome.SUCCESS:
        return QualificationExecutionStatus.CANDIDATE_HARD_FAILURE
    raise ValueError("successful call is not terminal by itself")


def _candidate_receipt(
    *,
    state_id: str,
    plan: TwoDeploymentQualificationExecutionPlan,
    candidate_plan: TwoDeploymentCandidateQualificationPlan,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    candidate_id: str,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    outputs: list[QualificationOutputRecord],
    tool_replays: list[QualificationToolReplayRecord],
    status: QualificationExecutionStatus,
    completed_at: datetime,
) -> QualificationCandidateReceipt:
    return QualificationCandidateReceipt(
        receipt_id=f"{state_id}_receipt",
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
        completed_new_call_count=len(ledger.calls),
        successful_new_call_count=sum(
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
    plan: TwoDeploymentQualificationExecutionPlan,
    candidate_plan: TwoDeploymentCandidateQualificationPlan,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    carry: TwoDeploymentQualificationCarryBundle,
    candidate_id: str,
    runtime: ProviderBudgetRuntime,
    outputs: list[QualificationOutputRecord],
    tool_replays: list[QualificationToolReplayRecord],
    validation_diagnostics: list[ProviderStructuredOutputDiagnostic],
    provider_diagnostics: list[ProviderHTTPErrorDiagnostic],
    status: QualificationExecutionStatus,
    harness_failure_code: QualificationHarnessFailureCode | None = None,
    completed_at: datetime | None = None,
) -> TwoDeploymentCandidateExecutionState:
    ledger = runtime.ledger_snapshot()
    journal = runtime.journal_snapshot()
    terminal = status not in {
        QualificationExecutionStatus.NOT_STARTED,
        QualificationExecutionStatus.RUNNING,
    }
    if terminal and completed_at is None:
        raise ValueError("terminal qualification state needs a completion time")
    receipt = (
        _candidate_receipt(
            state_id=state_id,
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
    return TwoDeploymentCandidateExecutionState(
        state_id=state_id,
        execution_plan_sha256=content_sha256(plan),
        candidate_plan_sha256=content_sha256(candidate_plan),
        authorization_bundle_sha256=content_sha256(authorization),
        carry_record_sha256s=_candidate_carry_hashes(carry, candidate_id),
        candidate_id=candidate_id,
        status=status,
        provider_ledger=ledger,
        provider_journal=journal,
        outputs=outputs,
        tool_replay_records=tool_replays,
        validation_diagnostics=validation_diagnostics,
        provider_error_diagnostics=provider_diagnostics,
        harness_failure_code=harness_failure_code,
        receipt=receipt,
    )


def validate_two_deployment_candidate_state(
    state: TwoDeploymentCandidateExecutionState,
    plan: TwoDeploymentQualificationExecutionPlan,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    carry: TwoDeploymentQualificationCarryBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    """Full audit used at terminal boundaries, never on each hot-path call."""

    candidate_plan = _candidate_plan_for(plan, state.candidate_id)
    if (
        state.execution_plan_sha256,
        state.candidate_plan_sha256,
        state.authorization_bundle_sha256,
        state.carry_record_sha256s,
    ) != (
        content_sha256(plan),
        content_sha256(candidate_plan),
        content_sha256(authorization),
        _candidate_carry_hashes(carry, state.candidate_id),
    ):
        raise ValueError("qualification candidate state bindings differ")
    suite_candidate = next(
        (
            item
            for item in suite.candidates
            if item.candidate.candidate_id == state.candidate_id
        ),
        None,
    )
    if suite_candidate is None:
        raise ValueError("qualification state candidate is outside suite")
    request_bindings_by_id = {
        item.call_id: item for item in state.provider_journal.request_bindings
    }
    provider_authorizations_by_id = {
        item.call_id: item for item in state.provider_ledger.authorizations
    }
    if (
        len(request_bindings_by_id)
        != len(state.provider_journal.request_bindings)
        or len(provider_authorizations_by_id)
        != len(state.provider_ledger.authorizations)
        or set(request_bindings_by_id) != set(provider_authorizations_by_id)
    ):
        raise ValueError(
            "qualification request and authorization chronology differs"
        )
    approval = authorization.manual_approval
    for call_id, binding in request_bindings_by_id.items():
        provider_authorization = provider_authorizations_by_id[call_id]
        if binding.created_at != provider_authorization.created_at:
            raise ValueError(
                "qualification request and authorization times differ"
            )
        if not approval.approved_at <= binding.created_at <= approval.expires_at:
            raise ValueError(
                "qualification request falls outside the manual approval window"
            )
    require_complete = len(state.provider_ledger.authorizations) == len(
        state.provider_ledger.calls
    )
    validate_provider_execution_journal(
        state.provider_journal,
        state.provider_ledger,
        profile,
        [suite_candidate.candidate],
        [suite_candidate.price_card],
        require_complete=require_complete,
    )
    calls = _candidate_new_calls(candidate_plan)
    planned_ids = [item.call_id for item in calls]
    carried_ids = {
        item.call_id
        for item in carry.records
        if item.candidate_id == state.candidate_id
    }
    authorization_ids = [
        item.call_id for item in state.provider_ledger.authorizations
    ]
    usage_ids = [item.call_id for item in state.provider_ledger.calls]
    binding_ids = [item.call_id for item in state.provider_journal.request_bindings]
    finalization_ids = [
        item.call_id for item in state.provider_journal.finalizations
    ]
    exact_requests = [
        item
        for item in authorization.authorized_requests
        if item.candidate_id == state.candidate_id
    ]
    if [item.call_id for item in exact_requests] != planned_ids:
        raise ValueError("qualification exact authorization differs from plan")
    if authorization_ids != planned_ids[: len(authorization_ids)]:
        raise ValueError("qualification authorizations are not an exact prefix")
    if binding_ids != authorization_ids:
        raise ValueError("qualification request bindings differ from authorization")
    if usage_ids != authorization_ids[: len(usage_ids)] or (
        finalization_ids != usage_ids
    ):
        raise ValueError("qualification completions are not an exact prefix")
    if carried_ids & set(authorization_ids):
        raise ValueError("qualification state replays a carried call")
    if len(authorization_ids) - len(usage_ids) > 1:
        raise ValueError("qualification state has multiple outstanding calls")
    if any(
        item.model_candidate_id != state.candidate_id
        for item in state.provider_journal.request_bindings
    ):
        raise ValueError("qualification state mixes candidates")
    for index, binding in enumerate(state.provider_journal.request_bindings):
        call = calls[index]
        exact = exact_requests[index]
        provider_authorization = state.provider_ledger.authorizations[index]
        if (
            exact.source_manifest_ordinal,
            exact.qualification_entry_sha256,
            exact.call_id,
            exact.candidate_id,
            exact.role,
            exact.request_content_sha256,
            exact.authorized_max_cost_microusd,
        ) != (
            call.source_manifest_ordinal,
            call.source_entry_sha256,
            call.call_id,
            call.candidate_id,
            call.role,
            call.source_entry.request_template_sha256,
            call.authorized_max_cost_microusd,
        ):
            raise ValueError("qualification exact authorization differs from plan")
        if (
            binding.call_id,
            binding.model_candidate_id,
            binding.role,
            provider_request_content_sha256(binding),
        ) != (
            exact.call_id,
            exact.candidate_id,
            exact.role,
            exact.request_content_sha256,
        ):
            raise ValueError(
                "qualification recorded request differs from exact authorization"
            )
        if (
            provider_authorization.call_id,
            provider_authorization.segment,
            provider_authorization.model_candidate_id,
            provider_authorization.request_sha256,
            provider_authorization.retry_of_call_id,
            provider_authorization.authorized_max_cost_microusd,
        ) != (
            exact.call_id,
            BudgetSegment.QUALIFICATION,
            exact.candidate_id,
            exact.request_content_sha256,
            None,
            exact.authorized_max_cost_microusd,
        ):
            raise ValueError(
                "qualification provider authorization differs from exact request"
            )
    non_success = [
        index
        for index, item in enumerate(state.provider_journal.finalizations)
        if item.outcome is not ProviderCallOutcome.SUCCESS
    ]
    if non_success and non_success != [len(finalization_ids) - 1]:
        raise ValueError("qualification failure must terminate candidate attempt")
    successful = {
        item.call_id
        for item in state.provider_journal.finalizations
        if item.outcome is ProviderCallOutcome.SUCCESS
    }
    if [item.call_id for item in state.outputs] != [
        call_id for call_id in planned_ids if call_id in successful
    ]:
        raise ValueError("qualification outputs do not cover successful calls")
    finalizations = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    for output in state.outputs:
        call = calls[planned_ids.index(output.call_id)]
        if (
            output.candidate_id != state.candidate_id
            or (
                output.source_manifest_ordinal,
                output.qualification_entry_sha256,
                output.call_id,
                output.measure_id,
                output.measure_version,
                output.role,
                output.variant_id,
            )
            != (
                call.source_manifest_ordinal,
                call.source_entry_sha256,
                call.call_id,
                call.measure_id,
                call.measure_version,
                call.role,
                call.variant_id.value,
            )
            or finalizations[output.call_id].response_sha256
            != output.output_sha256
        ):
            raise ValueError("qualification output differs from provider audit")
    diagnostics = {
        item.call_id: item for item in state.validation_diagnostics
    }
    provider_diagnostics = {
        item.call_id: item for item in state.provider_error_diagnostics
    }
    expected_validation_diagnostics = {
        call_id
        for call_id, finalization in finalizations.items()
        if finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
    }
    if set(diagnostics) != expected_validation_diagnostics:
        raise ValueError("qualification validation diagnostic differs")
    expected_provider_diagnostics = {
        call_id
        for call_id, finalization in finalizations.items()
        if finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR
    }
    if set(provider_diagnostics) != expected_provider_diagnostics:
        raise ValueError("qualification provider diagnostic differs")
    replay_counts = Counter(
        item.call_id for item in state.tool_replay_records
    )
    if not set(replay_counts) <= set(finalizations):
        raise ValueError("qualification tool replay lacks a finalization")
    request_roles = {
        item.call_id: item.role for item in state.provider_journal.request_bindings
    }
    for call_id, finalization in finalizations.items():
        if request_roles[call_id] is LLMRole.INTERVIEWER:
            if replay_counts[call_id] != finalization.tool_call_count or (
                finalization.outcome is ProviderCallOutcome.SUCCESS
                and replay_counts[call_id] == 0
            ):
                raise ValueError("qualification interviewer replay count differs")
        elif replay_counts[call_id]:
            raise ValueError("non-interviewer call has tool replay evidence")
    expected_status = QualificationExecutionStatus.RUNNING
    if len(authorization_ids) != len(usage_ids):
        expected_status = QualificationExecutionStatus.AMBIGUOUS_DELIVERY
    elif finalization_ids and non_success:
        expected_status = _terminal_status_for(
            state.provider_journal.finalizations[-1].outcome
        )
    elif len(finalization_ids) == len(planned_ids):
        expected_status = QualificationExecutionStatus.COMPLETED
    elif not finalization_ids:
        expected_status = QualificationExecutionStatus.NOT_STARTED
    if state.status is QualificationExecutionStatus.HARNESS_PAUSED:
        if len(authorization_ids) != len(usage_ids):
            raise ValueError("harness pause cannot hide outstanding delivery")
    elif state.status is not expected_status:
        raise ValueError("qualification candidate status does not reconcile")
    if state.receipt is not None:
        rebuilt_receipt = _candidate_receipt(
            state_id=state.state_id,
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
        if rebuilt_receipt != state.receipt:
            raise ValueError("qualification candidate receipt does not rebuild")


def _shared_committed_microusd(
    states: Mapping[str, TwoDeploymentCandidateExecutionState],
) -> int:
    return QUALIFICATION_PRIOR_SPEND_MICROUSD + sum(
        provider_committed_totals(state.provider_ledger)[
            BudgetSegment.QUALIFICATION
        ]
        for state in states.values()
    )


def execute_two_deployment_qualification(
    plan: TwoDeploymentQualificationExecutionPlan,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    carry: TwoDeploymentQualificationCarryBundle,
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
    checkpoint: Callable[[str, TwoDeploymentCandidateExecutionState], None],
) -> dict[str, TwoDeploymentCandidateExecutionState]:
    """Execute both isolated candidates once; never resume or retry a claim."""

    entries = {
        item.coordinate.ordinal: item
        for item in readiness.qualification_manifest.entries
    }
    suite_by_id = {
        item.candidate.candidate_id: item for item in suite.candidates
    }
    states: dict[str, TwoDeploymentCandidateExecutionState] = {}
    for candidate_plan in plan.candidate_plans:
        candidate_id = candidate_plan.candidate_id
        suite_candidate = suite_by_id[candidate_id]
        state_id = f"{plan.plan_id}_{candidate_id}_state"
        runtime = ProviderBudgetRuntime(
            profile,
            ledger_id=f"{state_id}_ledger",
            journal_id=f"{state_id}_journal",
        )
        outputs: list[QualificationOutputRecord] = []
        tool_replays: list[QualificationToolReplayRecord] = []
        validation_diagnostics: list[ProviderStructuredOutputDiagnostic] = []
        provider_diagnostics: list[ProviderHTTPErrorDiagnostic] = []
        new_calls = _candidate_new_calls(candidate_plan)
        status = QualificationExecutionStatus.RUNNING
        harness_failure_code: QualificationHarnessFailureCode | None = None
        for call_plan in new_calls:
            exact = next(
                item
                for item in authorization.authorized_requests
                if item.call_id == call_plan.call_id
            )
            if _shared_committed_microusd(states) + (
                runtime.committed_totals[BudgetSegment.QUALIFICATION]
            ) + exact.authorized_max_cost_microusd > (
                authorization.qualification_segment_cap_microusd
            ):
                status = QualificationExecutionStatus.HARNESS_PAUSED
                harness_failure_code = (
                    QualificationHarnessFailureCode.SHARED_BUDGET_GATE
                )
                break
            entry = entries[call_plan.source_manifest_ordinal]
            if content_sha256(entry) != call_plan.source_entry_sha256:
                status = QualificationExecutionStatus.HARNESS_PAUSED
                harness_failure_code = (
                    QualificationHarnessFailureCode.SOURCE_ENTRY_MISMATCH
                )
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
            if provider_request_content_sha256(
                rebuilt.request.binding
            ) != exact.request_content_sha256:
                status = QualificationExecutionStatus.HARNESS_PAUSED
                harness_failure_code = (
                    QualificationHarnessFailureCode.REQUEST_REBUILD_MISMATCH
                )
                break
            interviewer = entry.coordinate.role is LLMRole.INTERVIEWER
            if interviewer:
                tool_auditor.begin_call(entry.coordinate.call_id)
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
                if interviewer:
                    tool_replays.extend(tool_auditor.end_call())
            except Exception as error:
                if interviewer:
                    try:
                        tool_replays.extend(tool_auditor.end_call())
                    except ValueError:
                        pass
                ledger = runtime.ledger_snapshot()
                ambiguous = isinstance(error, TogetherAmbiguousDeliveryError) or (
                    len(ledger.authorizations) != len(ledger.calls)
                )
                status = (
                    QualificationExecutionStatus.AMBIGUOUS_DELIVERY
                    if ambiguous
                    else QualificationExecutionStatus.HARNESS_PAUSED
                )
                harness_failure_code = (
                    None
                    if ambiguous
                    else QualificationHarnessFailureCode.LOCAL_EXECUTION_EXCEPTION
                )
                state = _candidate_state(
                    state_id=state_id,
                    plan=plan,
                    candidate_plan=candidate_plan,
                    authorization=authorization,
                    carry=carry,
                    candidate_id=candidate_id,
                    runtime=runtime,
                    outputs=outputs,
                    tool_replays=tool_replays,
                    validation_diagnostics=validation_diagnostics,
                    provider_diagnostics=provider_diagnostics,
                    status=status,
                    harness_failure_code=harness_failure_code,
                    completed_at=clock(),
                )
                checkpoint(candidate_id, state)
                states[candidate_id] = state
                break
            if result.output is not None:
                payload = rebuilt.response_adapter.dump_python(
                    result.output,
                    mode="json",
                )
                outputs.append(
                    QualificationOutputRecord(
                        source_manifest_ordinal=entry.coordinate.ordinal,
                        qualification_entry_sha256=content_sha256(entry),
                        call_id=entry.coordinate.call_id,
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
                validation_diagnostics.append(result.validation_diagnostic)
            if result.provider_error_diagnostic is not None:
                provider_diagnostics.append(result.provider_error_diagnostic)
            terminal = result.finalization.outcome is not ProviderCallOutcome.SUCCESS
            status = (
                _terminal_status_for(result.finalization.outcome)
                if terminal
                else QualificationExecutionStatus.RUNNING
            )
            if not terminal and len(runtime.ledger_snapshot().calls) == len(
                new_calls
            ):
                status = QualificationExecutionStatus.COMPLETED
                terminal = True
            state = _candidate_state(
                state_id=state_id,
                plan=plan,
                candidate_plan=candidate_plan,
                authorization=authorization,
                carry=carry,
                candidate_id=candidate_id,
                runtime=runtime,
                outputs=outputs,
                tool_replays=tool_replays,
                validation_diagnostics=validation_diagnostics,
                provider_diagnostics=provider_diagnostics,
                status=status,
                completed_at=clock() if terminal else None,
            )
            checkpoint(candidate_id, state)
            if terminal:
                states[candidate_id] = state
                break
        else:  # pragma: no cover - completion is handled on the last call
            raise ValueError("qualification candidate loop ended without receipt")
        if candidate_id not in states:
            state = _candidate_state(
                state_id=state_id,
                plan=plan,
                candidate_plan=candidate_plan,
                authorization=authorization,
                carry=carry,
                candidate_id=candidate_id,
                runtime=runtime,
                outputs=outputs,
                tool_replays=tool_replays,
                validation_diagnostics=validation_diagnostics,
                provider_diagnostics=provider_diagnostics,
                status=status,
                harness_failure_code=harness_failure_code,
                completed_at=clock(),
            )
            checkpoint(candidate_id, state)
            states[candidate_id] = state
        validate_two_deployment_candidate_state(
            states[candidate_id],
            plan,
            authorization,
            carry,
            suite,
            profile,
        )
    if set(states) != set(authorization.authorized_candidate_ids):
        raise ValueError("qualification did not attempt both runnable candidates")
    return states


def qualification_candidate_state_summary(
    state: TwoDeploymentCandidateExecutionState,
) -> dict[str, JsonValue]:
    return {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "state_sha256": content_sha256(state),
        "candidate_id": state.candidate_id,
        "status": state.status.value,
        "authorized_call_count": len(state.provider_ledger.authorizations),
        "completed_call_count": len(state.provider_ledger.calls),
        "successful_output_count": len(state.outputs),
        "provider_spend_microusd": sum(
            item.billed_cost_microusd for item in state.provider_ledger.calls
        ),
        "participant_content_present": False,
    }
