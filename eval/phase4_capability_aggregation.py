"""Content-free aggregation of the reviewed Phase 4E capability attempts.

The aggregate is deliberately not a capability-preflight receipt.  It binds
the exact three-candidate audit trail, merges previously proven carry-forward
successes with the selector-recovery attempts, and records infrastructure
failures without converting them into evidence about model capability.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import (
    TogetherCapabilityCallPlan,
    TogetherCapabilityPlan,
)
from .phase4_capability_recovery import (
    TogetherCapabilityDeltaPlan,
    TogetherCapabilityDeltaSourceProof,
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    delta_candidate_plan_for,
    validate_capability_delta_execution_inputs,
    validate_delta_candidate_authorization_bundle,
    validate_delta_candidate_execution_state,
)
from .phase4_provider import ProviderCallFinalization, ProviderCallOutcome
from .phase4_provider_semantics import ProviderResponseInvariantManifest
from .phase4_readiness import Phase4TogetherReadinessBundle
from .phase4_robustness import LLMRole, Phase4ERobustnessProfile
from .phase4_selector_recovery import (
    TogetherSelectorRecoveryDeltaPlan,
    TogetherSelectorRecoverySourceProof,
    validate_selector_recovery_public_artifacts,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import (
    TogetherCatalogPreflightBundle,
    validate_catalog_preflight_bundle,
)
from .prequential import PrequentialSessionScript


Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
CAPABILITY_CANDIDATE_COUNT = 3
CAPABILITY_ROLE_COUNT = len(LLMRole)
CAPABILITY_COORDINATE_COUNT = CAPABILITY_CANDIDATE_COUNT * CAPABILITY_ROLE_COUNT


class CapabilityRoleEvidenceStatus(str, Enum):
    """How one corrected-plan coordinate is supported by the audit trail."""

    CARRIED_SUCCESS = "carried_success"
    OBSERVED_SUCCESS = "observed_success"
    PROVIDER_DEPLOYMENT_INCONCLUSIVE = "provider_deployment_inconclusive"
    NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE = (
        "not_attempted_after_provider_failure"
    )


class CandidateCapabilityDisposition(str, Enum):
    """Scientific disposition of one exact candidate/deployment pairing."""

    CAPABILITY_PASSED = "capability_passed"
    PROVIDER_DEPLOYMENT_INCONCLUSIVE = "provider_deployment_inconclusive"


class CapabilityAggregationNextStep(str, Enum):
    """The only honest transition supported by a partial capability matrix."""

    REVIEWED_QUALIFICATION_SCOPE_REQUIRED = (
        "reviewed_qualification_scope_required"
    )


class CapabilityRoleEvidence(ContractModel):
    """Content-free evidence for one role in the corrected 3-by-5 matrix."""

    record_version: Literal[
        "phase4_capability_role_evidence.v1"
    ] = "phase4_capability_role_evidence.v1"
    ordinal: PositiveCount
    candidate_id: StableId
    role: LLMRole
    call_id: StableId
    call_plan_sha256: Sha256Digest
    status: CapabilityRoleEvidenceStatus
    source_authorization_sha256: Sha256Digest
    source_state_sha256: Sha256Digest
    provider_usage_sha256: Sha256Digest | None = None
    finalization_sha256: Sha256Digest | None = None
    output_sha256: Sha256Digest | None = None
    provider_outcome: ProviderCallOutcome | None = None
    failure_code: StableId | None = None

    @model_validator(mode="after")
    def require_status_shape(self) -> Self:
        if self.status is CapabilityRoleEvidenceStatus.CARRIED_SUCCESS:
            if (
                self.provider_usage_sha256 is not None
                or self.finalization_sha256 is None
                or self.output_sha256 is None
                or self.provider_outcome is not ProviderCallOutcome.SUCCESS
                or self.failure_code is not None
            ):
                raise ValueError("carried capability evidence has wrong shape")
        elif self.status is CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS:
            if (
                self.provider_usage_sha256 is None
                or self.finalization_sha256 is None
                or self.output_sha256 is None
                or self.provider_outcome is not ProviderCallOutcome.SUCCESS
                or self.failure_code is not None
            ):
                raise ValueError("observed capability success has wrong shape")
        elif self.status is (
            CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
        ):
            if (
                self.provider_usage_sha256 is None
                or self.finalization_sha256 is None
                or self.output_sha256 is not None
                or self.provider_outcome is not ProviderCallOutcome.PROVIDER_ERROR
                or self.failure_code is None
            ):
                raise ValueError("provider-inconclusive evidence has wrong shape")
        elif any(
            value is not None
            for value in (
                self.provider_usage_sha256,
                self.finalization_sha256,
                self.output_sha256,
                self.provider_outcome,
                self.failure_code,
            )
        ):
            raise ValueError("unattempted capability evidence has provider data")
        return self


class CandidateCapabilityOutcome(ContractModel):
    """Exact role coverage and disposition for one candidate/deployment."""

    record_version: Literal[
        "phase4_candidate_capability_outcome.v1"
    ] = "phase4_candidate_capability_outcome.v1"
    candidate_id: StableId
    candidate_artifact_sha256: Sha256Digest
    candidate_plan_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    state_sha256: Sha256Digest
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    receipt_sha256: Sha256Digest | None = None
    disposition: CandidateCapabilityDisposition
    role_evidence: list[CapabilityRoleEvidence] = Field(
        min_length=CAPABILITY_ROLE_COUNT,
        max_length=CAPABILITY_ROLE_COUNT,
    )
    carried_success_count: NonNegativeCount
    observed_success_count: NonNegativeCount
    provider_failure_count: NonNegativeCount
    unattempted_role_count: NonNegativeCount
    recovery_provider_call_count: NonNegativeCount
    recovery_provider_spend_microusd: Microusd
    terminal_at: datetime

    @field_validator("terminal_at")
    @classmethod
    def require_aware_terminal_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability outcome terminal_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_disposition(self) -> Self:
        if any(item.candidate_id != self.candidate_id for item in self.role_evidence):
            raise ValueError("capability outcome mixes candidates")
        if any(
            (
                item.source_authorization_sha256,
                item.source_state_sha256,
            )
            != (self.authorization_sha256, self.state_sha256)
            for item in self.role_evidence
            if item.status is not CapabilityRoleEvidenceStatus.CARRIED_SUCCESS
        ):
            raise ValueError("capability outcome source attempt differs")
        roles = [item.role for item in self.role_evidence]
        if set(roles) != set(LLMRole) or len(roles) != len(set(roles)):
            raise ValueError("capability outcome must cover every role")
        ordinals = [item.ordinal for item in self.role_evidence]
        if ordinals != sorted(ordinals) or len(ordinals) != len(set(ordinals)):
            raise ValueError("capability outcome role order differs")
        counts = {
            status: sum(item.status is status for item in self.role_evidence)
            for status in CapabilityRoleEvidenceStatus
        }
        actual_counts = (
            self.carried_success_count,
            self.observed_success_count,
            self.provider_failure_count,
            self.unattempted_role_count,
            self.recovery_provider_call_count,
        )
        expected_counts = (
            counts[CapabilityRoleEvidenceStatus.CARRIED_SUCCESS],
            counts[CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS],
            counts[
                CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            ],
            counts[
                CapabilityRoleEvidenceStatus.NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
            ],
            counts[CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS]
            + counts[
                CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            ],
        )
        if actual_counts != expected_counts:
            raise ValueError("capability outcome counts do not reconcile")
        if self.disposition is CandidateCapabilityDisposition.CAPABILITY_PASSED:
            if (
                self.receipt_sha256 is None
                or self.provider_failure_count
                or self.unattempted_role_count
                or self.carried_success_count + self.observed_success_count
                != CAPABILITY_ROLE_COUNT
            ):
                raise ValueError("capability-passed outcome lacks exact coverage")
        else:
            statuses = [item.status for item in self.role_evidence]
            if self.receipt_sha256 is not None or self.provider_failure_count != 1:
                raise ValueError(
                    "provider-inconclusive outcome has wrong terminal shape"
                )
            failure_index = statuses.index(
                CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            )
            if any(
                status
                is not CapabilityRoleEvidenceStatus.NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
                for status in statuses[failure_index + 1 :]
            ):
                raise ValueError("provider failure must leave an unattempted suffix")
            if any(
                status
                is CapabilityRoleEvidenceStatus.NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
                for status in statuses[:failure_index]
            ):
                raise ValueError("unattempted role cannot predate provider failure")
        return self


class Phase4CapabilityAggregation(ContractModel):
    """Tracked content-free result of all reviewed capability attempts."""

    schema_version: Literal[
        "preference_eval_phase4_capability_aggregation.v1"
    ] = "preference_eval_phase4_capability_aggregation.v1"
    aggregation_id: StableId
    aggregation_version: Literal[1] = 1
    created_at: datetime
    selector_recovery_delta_sha256: Sha256Digest
    selector_recovery_source_proof_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    corrected_together_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    candidate_outcomes: list[CandidateCapabilityOutcome] = Field(
        min_length=CAPABILITY_CANDIDATE_COUNT,
        max_length=CAPABILITY_CANDIDATE_COUNT,
    )
    capability_passed_candidate_count: PositiveCount
    provider_deployment_inconclusive_candidate_count: PositiveCount
    model_capability_rejected_candidate_count: Literal[0] = 0
    carried_success_count: NonNegativeCount
    observed_success_count: NonNegativeCount
    provider_failure_count: PositiveCount
    unattempted_role_count: NonNegativeCount
    role_coordinate_count: Literal[CAPABILITY_COORDINATE_COUNT] = (
        CAPABILITY_COORDINATE_COUNT
    )
    recovery_provider_call_count: PositiveCount
    prior_provider_spend_microusd: Microusd
    recovery_provider_spend_microusd: Microusd
    cumulative_provider_spend_microusd: Microusd
    original_capability_max_spend_microusd: Literal[150_000] = 150_000
    remaining_capability_ceiling_microusd: Microusd
    next_step: Literal[
        CapabilityAggregationNextStep.REVIEWED_QUALIFICATION_SCOPE_REQUIRED
    ] = CapabilityAggregationNextStep.REVIEWED_QUALIFICATION_SCOPE_REQUIRED
    capability_preflight_receipt_sha256: None = None
    qualification_authorization_sha256: None = None
    selected_model_candidate_id: None = None
    replacement_candidate_ids: list[StableId] = Field(default_factory=list)
    public_development_inputs_only: Literal[True] = True
    participant_content_present: Literal[False] = False
    model_selection_performed: Literal[False] = False
    provider_inference_calls_executed_by_aggregation: Literal[0] = 0
    provider_spend_microusd_by_aggregation: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability aggregation created_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_totals_and_transition(self) -> Self:
        candidate_ids = [item.candidate_id for item in self.candidate_outcomes]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("capability aggregation candidates must be unique")
        if self.replacement_candidate_ids:
            raise ValueError("capability aggregation cannot replace candidates")
        if self.created_at < max(
            item.terminal_at for item in self.candidate_outcomes
        ):
            raise ValueError("capability aggregation predates an attempt")
        all_evidence = [
            evidence
            for candidate in self.candidate_outcomes
            for evidence in candidate.role_evidence
        ]
        if [item.ordinal for item in all_evidence] != list(
            range(1, CAPABILITY_COORDINATE_COUNT + 1)
        ):
            raise ValueError("capability aggregation must retain plan order")
        if len({(item.candidate_id, item.role) for item in all_evidence}) != (
            CAPABILITY_COORDINATE_COUNT
        ):
            raise ValueError("capability aggregation role matrix differs")
        passed = sum(
            item.disposition is CandidateCapabilityDisposition.CAPABILITY_PASSED
            for item in self.candidate_outcomes
        )
        inconclusive = sum(
            item.disposition
            is CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            for item in self.candidate_outcomes
        )
        expected = (
            passed,
            inconclusive,
            sum(item.carried_success_count for item in self.candidate_outcomes),
            sum(item.observed_success_count for item in self.candidate_outcomes),
            sum(item.provider_failure_count for item in self.candidate_outcomes),
            sum(item.unattempted_role_count for item in self.candidate_outcomes),
            sum(
                item.recovery_provider_call_count
                for item in self.candidate_outcomes
            ),
            sum(
                item.recovery_provider_spend_microusd
                for item in self.candidate_outcomes
            ),
        )
        actual = (
            self.capability_passed_candidate_count,
            self.provider_deployment_inconclusive_candidate_count,
            self.carried_success_count,
            self.observed_success_count,
            self.provider_failure_count,
            self.unattempted_role_count,
            self.recovery_provider_call_count,
            self.recovery_provider_spend_microusd,
        )
        if actual != expected or passed + inconclusive != CAPABILITY_CANDIDATE_COUNT:
            raise ValueError("capability aggregation totals do not reconcile")
        if inconclusive == 0:
            raise ValueError("v1 aggregation requires a reviewed scope decision")
        if self.cumulative_provider_spend_microusd != (
            self.prior_provider_spend_microusd
            + self.recovery_provider_spend_microusd
        ):
            raise ValueError("capability aggregation spend does not reconcile")
        if self.remaining_capability_ceiling_microusd != (
            self.original_capability_max_spend_microusd
            - self.cumulative_provider_spend_microusd
        ):
            raise ValueError("capability aggregation remaining ceiling differs")
        return self


class Phase4CapabilityAggregationSourceProof(ContractModel):
    """Public-safe proof that private source audits rebuilt the aggregate."""

    record_version: Literal[
        "phase4_capability_aggregation_source_proof.v1"
    ] = "phase4_capability_aggregation_source_proof.v1"
    proof_id: StableId
    proof_version: Literal[1] = 1
    validated_at: datetime
    aggregation_sha256: Sha256Digest
    selector_recovery_delta_sha256: Sha256Digest
    selector_recovery_source_proof_sha256: Sha256Digest
    catalog_preflight_bundle_sha256: Sha256Digest
    candidate_outcomes_sha256: Sha256Digest
    private_authorization_state_bindings_sha256: Sha256Digest
    full_private_source_validation_passed: Literal[True] = True
    candidate_roster_preserved: Literal[True] = True
    values_messages_and_context_omitted: Literal[True] = True
    provider_inference_calls_executed_by_proof_creation: Literal[0] = 0
    provider_spend_microusd_by_proof_creation: Literal[0] = 0

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability aggregation proof needs timezone")
        return value


CapabilityAttempt = tuple[
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
]


def _records_sha256(records: Sequence[ContractModel]) -> str:
    return content_sha256([item.model_dump(mode="json") for item in records])


def _candidate_order(plan: TogetherCapabilityPlan) -> list[str]:
    return list(dict.fromkeys(item.candidate_id for item in plan.calls))


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


def _validate_private_attempts(
    delta: TogetherSelectorRecoveryDeltaPlan,
    proof: TogetherSelectorRecoverySourceProof,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    catalog: TogetherCatalogPreflightBundle,
    attempts: Sequence[CapabilityAttempt],
) -> None:
    validate_catalog_preflight_bundle(suite, catalog)
    candidate_order = _candidate_order(corrected_plan)
    if len(attempts) != CAPABILITY_CANDIDATE_COUNT:
        raise ValueError("capability aggregation needs exactly three attempts")
    prior_attempts: list[CapabilityAttempt] = []
    for position, (authorization, state) in enumerate(attempts):
        candidate_id = candidate_order[position]
        candidate_plan = delta_candidate_plan_for(
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
            proof,
            candidate_plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog,
            prior_attempts=prior_attempts,
            now=authorization.manual_approval.approved_at,
        )
        validate_delta_candidate_execution_state(
            state,
            delta,
            candidate_plan,
            authorization,
            suite,
            profile,
        )
        if state.manual_spend_ceiling_breached or state.provider_budget_limit_breached:
            raise ValueError("capability aggregation cannot accept a spend breach")
        authorization_ids = [
            item.call_id for item in state.provider_ledger.authorizations
        ]
        call_ids = [item.call_id for item in state.provider_ledger.calls]
        finalization_ids = [
            item.call_id for item in state.provider_journal.finalizations
        ]
        if (
            not call_ids
            or authorization_ids != call_ids
            or call_ids != finalization_ids
        ):
            raise ValueError("capability aggregation requires terminal attempts")
        if state.receipt is None:
            index = len(finalization_ids) - 1
            if _call_passed(
                candidate_plan.calls[index],
                state.provider_journal.finalizations[-1],
            ):
                raise ValueError("capability aggregation cannot accept a live prefix")
        prior_attempts.append((authorization, state))


def _role_evidence_for_candidate(
    delta: TogetherSelectorRecoveryDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    state: TogetherDeltaCandidateExecutionState,
    candidate_id: str,
) -> list[CapabilityRoleEvidence]:
    carried_by_coordinate = {
        (item.candidate_id, item.role): item
        for item in delta.carried_forward_successes
    }
    source_attempts = {
        item.attempt_sequence: item for item in delta.source_attempts
    }
    finalizations = {
        item.call_id: item for item in state.provider_journal.finalizations
    }
    usages = {item.call_id: item for item in state.provider_ledger.calls}
    outputs = {item.call_id: item for item in state.outputs}
    evidence: list[CapabilityRoleEvidence] = []
    provider_failure_seen = False
    for call in corrected_plan.calls:
        if call.candidate_id != candidate_id:
            continue
        carried = carried_by_coordinate.get((candidate_id, call.role))
        if carried is not None:
            source = source_attempts[carried.source_attempt_sequence]
            evidence.append(
                CapabilityRoleEvidence(
                    ordinal=call.ordinal,
                    candidate_id=candidate_id,
                    role=call.role,
                    call_id=call.call_id,
                    call_plan_sha256=content_sha256(call),
                    status=CapabilityRoleEvidenceStatus.CARRIED_SUCCESS,
                    source_authorization_sha256=source.authorization_sha256,
                    source_state_sha256=carried.source_state_sha256,
                    finalization_sha256=carried.finalization_sha256,
                    output_sha256=carried.corrected_revalidated_output_sha256,
                    provider_outcome=ProviderCallOutcome.SUCCESS,
                )
            )
            continue
        finalization = finalizations.get(call.call_id)
        if finalization is None:
            if not provider_failure_seen:
                raise ValueError("unattempted capability role lacks provider failure")
            evidence.append(
                CapabilityRoleEvidence(
                    ordinal=call.ordinal,
                    candidate_id=candidate_id,
                    role=call.role,
                    call_id=call.call_id,
                    call_plan_sha256=content_sha256(call),
                    status=(
                        CapabilityRoleEvidenceStatus
                        .NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
                    ),
                    source_authorization_sha256=content_sha256(authorization),
                    source_state_sha256=content_sha256(state),
                )
            )
            continue
        usage = usages[call.call_id]
        output = outputs.get(call.call_id)
        if _call_passed(call, finalization):
            if output is None:
                raise ValueError("successful capability role lacks output")
            status = CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS
        elif finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR:
            if provider_failure_seen or output is not None:
                raise ValueError("provider capability failure has wrong shape")
            if finalization.failure_code != "together_http_400":
                raise ValueError(
                    "provider capability failure differs from reviewed HTTP 400"
                )
            if any(
                (
                    usage.billed_cost_microusd,
                    usage.input_tokens,
                    usage.output_tokens,
                )
            ):
                raise ValueError("provider HTTP rejection must have zero usage")
            provider_failure_seen = True
            status = CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
        else:
            raise ValueError("capability result needs separate scientific review")
        evidence.append(
            CapabilityRoleEvidence(
                ordinal=call.ordinal,
                candidate_id=candidate_id,
                role=call.role,
                call_id=call.call_id,
                call_plan_sha256=content_sha256(call),
                status=status,
                source_authorization_sha256=content_sha256(authorization),
                source_state_sha256=content_sha256(state),
                provider_usage_sha256=content_sha256(usage),
                finalization_sha256=content_sha256(finalization),
                output_sha256=(output.output_sha256 if output else None),
                provider_outcome=finalization.outcome,
                failure_code=finalization.failure_code,
            )
        )
    return evidence


def _candidate_outcome(
    delta: TogetherSelectorRecoveryDeltaPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    readiness: Phase4TogetherReadinessBundle,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    state: TogetherDeltaCandidateExecutionState,
    candidate_id: str,
) -> CandidateCapabilityOutcome:
    candidate_plan = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        candidate_id,
    )
    evidence = _role_evidence_for_candidate(
        delta,
        corrected_plan,
        authorization,
        state,
        candidate_id,
    )
    status_counts = {
        status: sum(item.status is status for item in evidence)
        for status in CapabilityRoleEvidenceStatus
    }
    disposition = (
        CandidateCapabilityDisposition.CAPABILITY_PASSED
        if state.receipt is not None
        and not status_counts[
            CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
        ]
        else CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
    )
    candidate = next(
        item.candidate
        for item in suite.candidates
        if item.candidate.candidate_id == candidate_id
    )
    return CandidateCapabilityOutcome(
        candidate_id=candidate_id,
        candidate_artifact_sha256=content_sha256(candidate),
        candidate_plan_sha256=content_sha256(candidate_plan),
        authorization_sha256=content_sha256(authorization),
        state_sha256=content_sha256(state),
        provider_ledger_sha256=content_sha256(state.provider_ledger),
        provider_journal_sha256=content_sha256(state.provider_journal),
        receipt_sha256=(content_sha256(state.receipt) if state.receipt else None),
        disposition=disposition,
        role_evidence=evidence,
        carried_success_count=status_counts[
            CapabilityRoleEvidenceStatus.CARRIED_SUCCESS
        ],
        observed_success_count=status_counts[
            CapabilityRoleEvidenceStatus.OBSERVED_SUCCESS
        ],
        provider_failure_count=status_counts[
            CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
        ],
        unattempted_role_count=status_counts[
            CapabilityRoleEvidenceStatus.NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
        ],
        recovery_provider_call_count=len(state.provider_ledger.calls),
        recovery_provider_spend_microusd=sum(
            item.billed_cost_microusd for item in state.provider_ledger.calls
        ),
        terminal_at=state.provider_journal.finalizations[-1].created_at,
    )


def build_capability_aggregation(
    delta: TogetherSelectorRecoveryDeltaPlan,
    proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
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
    catalog: TogetherCatalogPreflightBundle,
    attempts: Sequence[CapabilityAttempt],
    *,
    aggregation_id: str,
    created_at: datetime,
) -> Phase4CapabilityAggregation:
    """Rebuild the result from exact public and private audit sources."""

    public_inputs = (
        delta,
        proof,
        parent_delta,
        parent_proof,
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
    validate_selector_recovery_public_artifacts(*public_inputs)
    validate_capability_delta_execution_inputs(
        delta,
        proof,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
    )
    _validate_private_attempts(
        delta,
        proof,
        corrected_plan,
        corrected_suite,
        profile,
        corrected_readiness,
        catalog,
        attempts,
    )
    candidate_order = _candidate_order(corrected_plan)
    outcomes = [
        _candidate_outcome(
            delta,
            corrected_plan,
            corrected_suite,
            profile,
            corrected_readiness,
            authorization,
            state,
            candidate_id,
        )
        for candidate_id, (authorization, state) in zip(
            candidate_order,
            attempts,
            strict=True,
        )
    ]
    recovery_spend = sum(
        item.recovery_provider_spend_microusd for item in outcomes
    )
    cumulative_spend = delta.prior_provider_spend_microusd + recovery_spend
    return Phase4CapabilityAggregation(
        aggregation_id=aggregation_id,
        created_at=created_at,
        selector_recovery_delta_sha256=content_sha256(delta),
        selector_recovery_source_proof_sha256=content_sha256(proof),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        corrected_together_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        robustness_profile_sha256=content_sha256(profile),
        provider_response_semantics_manifest_sha256=content_sha256(
            response_semantics_manifest
        ),
        catalog_preflight_bundle_sha256=content_sha256(catalog),
        candidate_outcomes=outcomes,
        capability_passed_candidate_count=sum(
            item.disposition is CandidateCapabilityDisposition.CAPABILITY_PASSED
            for item in outcomes
        ),
        provider_deployment_inconclusive_candidate_count=sum(
            item.disposition
            is CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
            for item in outcomes
        ),
        carried_success_count=sum(item.carried_success_count for item in outcomes),
        observed_success_count=sum(item.observed_success_count for item in outcomes),
        provider_failure_count=sum(item.provider_failure_count for item in outcomes),
        unattempted_role_count=sum(item.unattempted_role_count for item in outcomes),
        recovery_provider_call_count=sum(
            item.recovery_provider_call_count for item in outcomes
        ),
        prior_provider_spend_microusd=delta.prior_provider_spend_microusd,
        recovery_provider_spend_microusd=recovery_spend,
        cumulative_provider_spend_microusd=cumulative_spend,
        remaining_capability_ceiling_microusd=(
            delta.original_capability_max_spend_microusd - cumulative_spend
        ),
    )


def validate_capability_aggregation(
    aggregation: Phase4CapabilityAggregation,
    delta: TogetherSelectorRecoveryDeltaPlan,
    proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
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
    catalog: TogetherCatalogPreflightBundle,
    attempts: Sequence[CapabilityAttempt],
) -> None:
    """Rebuild an aggregate from every exact public and private input."""

    rebuilt = build_capability_aggregation(
        delta,
        proof,
        parent_delta,
        parent_proof,
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
        catalog,
        attempts,
        aggregation_id=aggregation.aggregation_id,
        created_at=aggregation.created_at,
    )
    if aggregation != rebuilt:
        raise ValueError("capability aggregation does not rebuild")


def validate_capability_aggregation_source_proof(
    proof: Phase4CapabilityAggregationSourceProof,
    aggregation: Phase4CapabilityAggregation,
) -> None:
    if proof.validated_at < aggregation.created_at:
        raise ValueError("capability aggregation proof predates result")
    expected = (
        content_sha256(aggregation),
        aggregation.selector_recovery_delta_sha256,
        aggregation.selector_recovery_source_proof_sha256,
        aggregation.catalog_preflight_bundle_sha256,
        _records_sha256(aggregation.candidate_outcomes),
        content_sha256(
            [
                {
                    "authorization_sha256": item.authorization_sha256,
                    "state_sha256": item.state_sha256,
                }
                for item in aggregation.candidate_outcomes
            ]
        ),
    )
    actual = (
        proof.aggregation_sha256,
        proof.selector_recovery_delta_sha256,
        proof.selector_recovery_source_proof_sha256,
        proof.catalog_preflight_bundle_sha256,
        proof.candidate_outcomes_sha256,
        proof.private_authorization_state_bindings_sha256,
    )
    if actual != expected:
        raise ValueError("capability aggregation proof bindings differ")


def build_capability_aggregation_source_proof(
    aggregation: Phase4CapabilityAggregation,
    delta: TogetherSelectorRecoveryDeltaPlan,
    proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
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
    catalog: TogetherCatalogPreflightBundle,
    attempts: Sequence[CapabilityAttempt],
    *,
    proof_id: str,
    validated_at: datetime,
) -> Phase4CapabilityAggregationSourceProof:
    validate_capability_aggregation(
        aggregation,
        delta,
        proof,
        parent_delta,
        parent_proof,
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
        catalog,
        attempts,
    )
    private_bindings = [
        {
            "authorization_sha256": content_sha256(authorization),
            "state_sha256": content_sha256(state),
        }
        for authorization, state in attempts
    ]
    expected_bindings = [
        {
            "authorization_sha256": item.authorization_sha256,
            "state_sha256": item.state_sha256,
        }
        for item in aggregation.candidate_outcomes
    ]
    if private_bindings != expected_bindings:
        raise ValueError("capability aggregation proof sources differ")
    proof = Phase4CapabilityAggregationSourceProof(
        proof_id=proof_id,
        validated_at=validated_at,
        aggregation_sha256=content_sha256(aggregation),
        selector_recovery_delta_sha256=(
            aggregation.selector_recovery_delta_sha256
        ),
        selector_recovery_source_proof_sha256=(
            aggregation.selector_recovery_source_proof_sha256
        ),
        catalog_preflight_bundle_sha256=(
            aggregation.catalog_preflight_bundle_sha256
        ),
        candidate_outcomes_sha256=_records_sha256(
            aggregation.candidate_outcomes
        ),
        private_authorization_state_bindings_sha256=content_sha256(
            private_bindings
        ),
    )
    validate_capability_aggregation_source_proof(proof, aggregation)
    return proof


def validate_capability_aggregation_public_artifacts(
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    delta: TogetherSelectorRecoveryDeltaPlan,
    proof: TogetherSelectorRecoverySourceProof,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
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
    public_inputs = (
        delta,
        proof,
        parent_delta,
        parent_proof,
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
    validate_selector_recovery_public_artifacts(*public_inputs)
    validate_capability_aggregation_source_proof(
        aggregation_proof,
        aggregation,
    )
    expected_bindings = (
        content_sha256(delta),
        content_sha256(proof),
        content_sha256(corrected_plan),
        content_sha256(corrected_suite),
        content_sha256(corrected_readiness),
        content_sha256(profile),
        content_sha256(response_semantics_manifest),
    )
    actual_bindings = (
        aggregation.selector_recovery_delta_sha256,
        aggregation.selector_recovery_source_proof_sha256,
        aggregation.corrected_capability_plan_sha256,
        aggregation.corrected_together_suite_sha256,
        aggregation.corrected_readiness_sha256,
        aggregation.robustness_profile_sha256,
        aggregation.provider_response_semantics_manifest_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("capability aggregation public bindings differ")
    if (
        aggregation.prior_provider_spend_microusd,
        aggregation.original_capability_max_spend_microusd,
        aggregation.carried_success_count,
    ) != (
        delta.prior_provider_spend_microusd,
        delta.original_capability_max_spend_microusd,
        len(delta.carried_forward_successes),
    ):
        raise ValueError("capability aggregation public totals differ")
    candidate_order = _candidate_order(corrected_plan)
    if [
        item.candidate_id for item in aggregation.candidate_outcomes
    ] != candidate_order:
        raise ValueError("capability aggregation candidate order differs")
    calls = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    carries = {
        (item.candidate_id, item.role): item
        for item in delta.carried_forward_successes
    }
    source_attempts = {
        item.attempt_sequence: item for item in delta.source_attempts
    }
    for outcome in aggregation.candidate_outcomes:
        candidate = next(
            item.candidate
            for item in corrected_suite.candidates
            if item.candidate.candidate_id == outcome.candidate_id
        )
        if outcome.candidate_artifact_sha256 != content_sha256(candidate):
            raise ValueError("capability aggregation candidate binding differs")
        candidate_plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            corrected_suite,
            profile,
            corrected_readiness,
            outcome.candidate_id,
        )
        if outcome.candidate_plan_sha256 != content_sha256(candidate_plan):
            raise ValueError("capability aggregation candidate plan differs")
        for evidence in outcome.role_evidence:
            call = calls[(evidence.candidate_id, evidence.role)]
            if (
                evidence.ordinal,
                evidence.call_id,
                evidence.call_plan_sha256,
            ) != (call.ordinal, call.call_id, content_sha256(call)):
                raise ValueError("capability aggregation role binding differs")
            carried = carries.get((evidence.candidate_id, evidence.role))
            if evidence.status is CapabilityRoleEvidenceStatus.CARRIED_SUCCESS:
                source = (
                    source_attempts.get(carried.source_attempt_sequence)
                    if carried is not None
                    else None
                )
                if carried is None or source is None or (
                    evidence.source_authorization_sha256,
                    evidence.source_state_sha256,
                    evidence.finalization_sha256,
                    evidence.output_sha256,
                ) != (
                    source.authorization_sha256,
                    carried.source_state_sha256,
                    carried.finalization_sha256,
                    carried.corrected_revalidated_output_sha256,
                ):
                    raise ValueError("capability aggregation carry differs")
            elif carried is not None:
                raise ValueError("capability aggregation discarded a carry")


def capability_aggregation_summary(
    aggregation: Phase4CapabilityAggregation,
) -> dict[str, JsonValue]:
    """Return aggregate-only public CLI output."""

    return {
        "schema_version": aggregation.schema_version,
        "aggregation_id": aggregation.aggregation_id,
        "aggregation_sha256": content_sha256(aggregation),
        "candidate_count": len(aggregation.candidate_outcomes),
        "capability_passed_candidate_count": (
            aggregation.capability_passed_candidate_count
        ),
        "provider_deployment_inconclusive_candidate_count": (
            aggregation.provider_deployment_inconclusive_candidate_count
        ),
        "model_capability_rejected_candidate_count": 0,
        "role_coordinate_count": aggregation.role_coordinate_count,
        "carried_success_count": aggregation.carried_success_count,
        "observed_success_count": aggregation.observed_success_count,
        "provider_failure_count": aggregation.provider_failure_count,
        "unattempted_role_count": aggregation.unattempted_role_count,
        "recovery_provider_call_count": (
            aggregation.recovery_provider_call_count
        ),
        "prior_provider_spend_microusd": (
            aggregation.prior_provider_spend_microusd
        ),
        "recovery_provider_spend_microusd": (
            aggregation.recovery_provider_spend_microusd
        ),
        "cumulative_provider_spend_microusd": (
            aggregation.cumulative_provider_spend_microusd
        ),
        "remaining_capability_ceiling_microusd": (
            aggregation.remaining_capability_ceiling_microusd
        ),
        "next_step": aggregation.next_step.value,
        "provider_inference_calls_executed_by_aggregation": 0,
        "provider_spend_microusd_by_aggregation": 0,
    }


def load_capability_aggregation(
    path: str | Path,
) -> Phase4CapabilityAggregation:
    return Phase4CapabilityAggregation.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_capability_aggregation_source_proof(
    path: str | Path,
) -> Phase4CapabilityAggregationSourceProof:
    return Phase4CapabilityAggregationSourceProof.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
