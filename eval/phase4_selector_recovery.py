"""Zero-spend chained recovery after the interviewer selector correction.

This module deliberately does not extend the v1 paid-execution contracts in
``phase4_capability_recovery``.  It authors a new, content-free v2 delta that
chains from the reviewed v1 delta and source proof, binds the later GLM
attempt, and partitions the corrected 15-call plan by exact wire equality plus
revalidation under the corrected response contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

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
    TogetherCapabilityOutputRecord,
    TogetherCapabilityPlan,
    validate_capability_plan,
)
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityExecutionState,
)
from .phase4_capability_recovery import (
    TogetherCapabilityDeltaPlan,
    TogetherCapabilityDeltaSourceProof,
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherDeltaCandidateExecutionState,
    delta_candidate_plan_for,
    validate_capability_delta_source_proof,
    validate_delta_candidate_execution_state,
)
from .phase4_provider import (
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderRequestBinding,
    ProviderStructuredOutputDiagnostic,
)
from .phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
    ProviderResponseInvariantManifest,
)
from .phase4_readiness import (
    Phase4TogetherReadinessBundle,
    rebuild_qualification_call,
)
from .phase4_robustness import LLMRole, Phase4ERobustnessProfile
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import Phase4TogetherSuite
from .prequential import PrequentialSessionScript


Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]

PARENT_SOURCE_ATTEMPT_COUNT = 3
TOTAL_SOURCE_ATTEMPT_COUNT = 4
EXPECTED_CARRY_COUNT = 5
EXPECTED_RERUN_COUNT = 10


class SelectorRecoverySourceAttempt(ContractModel):
    """Content-free binding to one historical paid attempt."""

    record_version: Literal[
        "phase4_selector_recovery_source_attempt.v2"
    ] = "phase4_selector_recovery_source_attempt.v2"
    attempt_sequence: PositiveCount
    lineage: Literal[
        "parent_delta_v1",
        "post_parent_delta_selector_attempt",
    ]
    candidate_id: StableId
    authorization_sha256: Sha256Digest
    state_sha256: Sha256Digest
    diagnostic_sha256: Sha256Digest | None = None
    provider_call_count: PositiveCount
    provider_spend_microusd: Microusd
    terminal_at: datetime
    terminal_role: LLMRole
    terminal_outcome: ProviderCallOutcome
    terminal_failure_code: StableId
    response_schema_sha256: Sha256Digest
    validation_error_count: NonNegativeCount
    values_messages_and_context_omitted: Literal[True] = True
    disposition: Literal["harness_inconclusive"] = "harness_inconclusive"

    @field_validator("terminal_at")
    @classmethod
    def require_aware_terminal_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("selector recovery terminal_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_diagnostic_count(self) -> Self:
        if (self.diagnostic_sha256 is None) != (
            self.validation_error_count == 0
        ):
            raise ValueError("selector recovery diagnostic count differs")
        return self


class SelectorRecoveryCarriedSuccess(ContractModel):
    """One exact wire-equivalent success revalidated under suite v5."""

    record_version: Literal[
        "phase4_selector_recovery_carried_success.v2"
    ] = "phase4_selector_recovery_carried_success.v2"
    candidate_id: StableId
    role: LLMRole
    source_attempt_sequence: PositiveCount
    source_state_sha256: Sha256Digest
    source_call_plan_sha256: Sha256Digest
    corrected_call_plan_sha256: Sha256Digest
    source_request_binding_sha256: Sha256Digest
    corrected_request_binding_sha256: Sha256Digest
    source_response_validator_sha256: Sha256Digest
    corrected_response_validator_sha256: Sha256Digest
    source_transmitted_payload_sha256: Sha256Digest
    corrected_transmitted_payload_sha256: Sha256Digest
    finalization_sha256: Sha256Digest
    source_output_sha256: Sha256Digest
    corrected_revalidated_output_sha256: Sha256Digest
    exact_transmitted_payload_unchanged: Literal[True] = True
    source_and_corrected_validators_both_bound: Literal[True] = True
    output_revalidated_under_corrected_contract: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_carry(self) -> Self:
        if (
            self.source_transmitted_payload_sha256
            != self.corrected_transmitted_payload_sha256
        ):
            raise ValueError("selector recovery carried wire payload changed")
        if (
            self.source_output_sha256
            != self.corrected_revalidated_output_sha256
        ):
            raise ValueError("selector recovery output changed on revalidation")
        return self


class TogetherSelectorRecoveryDeltaPlan(ContractModel):
    """Reviewed zero-spend partition after selector/hydration correction."""

    schema_version: Literal[
        "preference_eval_phase4_selector_recovery_delta.v2"
    ] = "preference_eval_phase4_selector_recovery_delta.v2"
    plan_id: StableId
    plan_version: Literal[2] = 2
    created_at: datetime
    parent_delta_plan_sha256: Sha256Digest
    parent_delta_source_proof_sha256: Sha256Digest
    parent_corrected_suite_sha256: Sha256Digest
    parent_corrected_readiness_sha256: Sha256Digest
    parent_corrected_capability_plan_sha256: Sha256Digest
    corrected_suite_sha256: Sha256Digest
    corrected_readiness_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    latest_selector_authorization_sha256: Sha256Digest
    latest_selector_state_sha256: Sha256Digest
    latest_selector_diagnostic_sha256: Sha256Digest
    source_attempts: list[SelectorRecoverySourceAttempt] = Field(
        min_length=TOTAL_SOURCE_ATTEMPT_COUNT,
        max_length=TOTAL_SOURCE_ATTEMPT_COUNT,
    )
    carried_forward_successes: list[SelectorRecoveryCarriedSuccess] = Field(
        min_length=EXPECTED_CARRY_COUNT,
        max_length=EXPECTED_CARRY_COUNT,
    )
    rerun_calls: list[TogetherCapabilityCallPlan] = Field(
        min_length=EXPECTED_RERUN_COUNT,
        max_length=EXPECTED_RERUN_COUNT,
    )
    parent_cumulative_provider_spend_microusd: Microusd
    latest_selector_provider_spend_microusd: Microusd
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
            raise ValueError("selector recovery created_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_exact_partition_and_totals(self) -> Self:
        sequences = [item.attempt_sequence for item in self.source_attempts]
        if sequences != list(range(1, TOTAL_SOURCE_ATTEMPT_COUNT + 1)):
            raise ValueError("selector recovery attempt sequence differs")
        if any(
            item.lineage != "parent_delta_v1"
            for item in self.source_attempts[:PARENT_SOURCE_ATTEMPT_COUNT]
        ) or self.source_attempts[-1].lineage != (
            "post_parent_delta_selector_attempt"
        ):
            raise ValueError("selector recovery attempt lineage differs")
        latest = self.source_attempts[-1]
        if (
            latest.authorization_sha256,
            latest.state_sha256,
            latest.diagnostic_sha256,
        ) != (
            self.latest_selector_authorization_sha256,
            self.latest_selector_state_sha256,
            self.latest_selector_diagnostic_sha256,
        ):
            raise ValueError("selector recovery latest attempt hashes differ")
        if self.created_at < max(
            item.terminal_at for item in self.source_attempts
        ):
            raise ValueError("selector recovery predates a source attempt")
        carry_coordinates = [
            (item.candidate_id, item.role)
            for item in self.carried_forward_successes
        ]
        canonical_carries = sorted(
            carry_coordinates,
            key=lambda item: (item[0], item[1].value),
        )
        if carry_coordinates != canonical_carries or len(
            set(carry_coordinates)
        ) != len(carry_coordinates):
            raise ValueError("selector recovery carries must be canonical")
        valid_sequences = set(sequences)
        if any(
            item.source_attempt_sequence not in valid_sequences
            for item in self.carried_forward_successes
        ):
            raise ValueError("selector recovery carry binds no source attempt")
        rerun_ordinals = [item.ordinal for item in self.rerun_calls]
        if rerun_ordinals != sorted(rerun_ordinals) or len(
            set(rerun_ordinals)
        ) != len(rerun_ordinals):
            raise ValueError("selector recovery reruns must retain plan order")
        rerun_coordinates = [
            (item.candidate_id, item.role) for item in self.rerun_calls
        ]
        if len(set(rerun_coordinates)) != len(rerun_coordinates):
            raise ValueError("selector recovery reruns must be unique")
        candidate_ids = {item.candidate_id for item in self.rerun_calls} | {
            item.candidate_id for item in self.carried_forward_successes
        }
        expected = {
            (candidate_id, role)
            for candidate_id in candidate_ids
            for role in LLMRole
        }
        if len(candidate_ids) != 3:
            raise ValueError("selector recovery must cover three candidates")
        if set(carry_coordinates) & set(rerun_coordinates):
            raise ValueError("selector recovery carry and rerun overlap")
        if set(carry_coordinates) | set(rerun_coordinates) != expected:
            raise ValueError("selector recovery does not cover exact matrix")
        if self.prior_provider_spend_microusd != (
            self.parent_cumulative_provider_spend_microusd
            + self.latest_selector_provider_spend_microusd
        ):
            raise ValueError("selector recovery prior spend does not reconcile")
        if self.additional_projected_cost_microusd != sum(
            item.projected_cost_microusd for item in self.rerun_calls
        ):
            raise ValueError("selector recovery projected cost differs")
        if self.additional_authorized_max_cost_microusd != sum(
            item.authorized_max_cost_microusd for item in self.rerun_calls
        ):
            raise ValueError("selector recovery authorization cost differs")
        if self.cumulative_worst_case_spend_microusd != (
            self.prior_provider_spend_microusd
            + self.additional_authorized_max_cost_microusd
        ):
            raise ValueError("selector recovery cumulative spend differs")
        if (
            self.cumulative_worst_case_spend_microusd
            > self.original_capability_max_spend_microusd
        ):
            raise ValueError("selector recovery exceeds original spend ceiling")
        return self


class TogetherSelectorRecoverySourceProof(ContractModel):
    """Content-free receipt for the exact chained private-source rebuild."""

    record_version: Literal[
        "phase4_selector_recovery_source_proof.v2"
    ] = "phase4_selector_recovery_source_proof.v2"
    proof_id: StableId
    proof_version: Literal[2] = 2
    validated_at: datetime
    selector_recovery_delta_sha256: Sha256Digest
    parent_delta_plan_sha256: Sha256Digest
    parent_delta_source_proof_sha256: Sha256Digest
    latest_selector_authorization_sha256: Sha256Digest
    latest_selector_state_sha256: Sha256Digest
    latest_selector_diagnostic_sha256: Sha256Digest
    source_attempts_sha256: Sha256Digest
    carried_forward_successes_sha256: Sha256Digest
    rerun_calls_sha256: Sha256Digest
    provider_response_semantics_manifest_sha256: Sha256Digest
    full_private_source_rebuild_passed: Literal[True] = True
    parent_audit_artifact_hashes_bound: Literal[True] = True
    values_messages_and_context_omitted: Literal[True] = True

    @field_validator("validated_at")
    @classmethod
    def require_aware_validated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("selector recovery proof needs timezone")
        return value


@dataclass(frozen=True)
class _SuccessfulSource:
    attempt_sequence: int
    state_sha256: str
    output: TogetherCapabilityOutputRecord
    binding: ProviderRequestBinding
    parent_request_binding_sha256: str
    finalization: ProviderCallFinalization


def _records_sha256(records: Sequence[ContractModel]) -> str:
    return content_sha256([item.model_dump(mode="json") for item in records])


def _provider_spend(
    state: TogetherCandidateCapabilityExecutionState
    | TogetherDeltaCandidateExecutionState,
) -> int:
    return sum(item.billed_cost_microusd for item in state.provider_ledger.calls)


def _terminal_parts(
    state: TogetherCandidateCapabilityExecutionState
    | TogetherDeltaCandidateExecutionState,
) -> tuple[ProviderCallFinalization, ProviderRequestBinding]:
    if state.receipt is not None or not state.provider_journal.finalizations:
        raise ValueError("selector recovery source must be terminal failure")
    finalization = state.provider_journal.finalizations[-1]
    bindings = {
        item.call_id: item for item in state.provider_journal.request_bindings
    }
    return finalization, bindings[finalization.call_id]


def _parent_attempt_records(
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_states: Sequence[TogetherCandidateCapabilityExecutionState],
) -> tuple[
    list[SelectorRecoverySourceAttempt],
    dict[str, TogetherCandidateCapabilityExecutionState],
]:
    states_by_hash = {content_sha256(state): state for state in parent_states}
    if len(parent_states) != PARENT_SOURCE_ATTEMPT_COUNT or len(
        states_by_hash
    ) != PARENT_SOURCE_ATTEMPT_COUNT:
        raise ValueError("selector recovery needs exact parent source states")
    if set(states_by_hash) != {
        item.state_sha256 for item in parent_delta.source_attempts
    }:
        raise ValueError("selector recovery parent source states differ")
    attempts = [
        SelectorRecoverySourceAttempt(
            attempt_sequence=index,
            lineage="parent_delta_v1",
            candidate_id=item.candidate_id,
            authorization_sha256=item.authorization_sha256,
            state_sha256=item.state_sha256,
            diagnostic_sha256=item.diagnostic_sha256,
            provider_call_count=item.provider_call_count,
            provider_spend_microusd=item.provider_spend_microusd,
            terminal_at=item.terminal_at,
            terminal_role=item.terminal_role,
            terminal_outcome=item.terminal_outcome,
            terminal_failure_code=item.terminal_failure_code,
            response_schema_sha256=item.response_schema_sha256,
            validation_error_count=item.validation_error_count,
        )
        for index, item in enumerate(parent_delta.source_attempts, start=1)
    ]
    return attempts, states_by_hash


def _latest_attempt_record(
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
    parent_plan: TogetherCapabilityPlan,
    parent_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    parent_readiness: Phase4TogetherReadinessBundle,
    authorization: TogetherDeltaCandidateAuthorizationBundle,
    state: TogetherDeltaCandidateExecutionState,
    diagnostic: ProviderStructuredOutputDiagnostic,
) -> SelectorRecoverySourceAttempt:
    candidate_id = authorization.manual_approval.candidate_id
    candidate_plan = delta_candidate_plan_for(
        parent_delta,
        parent_plan,
        parent_suite,
        profile,
        parent_readiness,
        candidate_id,
    )
    validate_delta_candidate_execution_state(
        state,
        parent_delta,
        candidate_plan,
        authorization,
        parent_suite,
        profile,
    )
    if (
        authorization.delta_plan_sha256,
        authorization.source_proof_sha256,
    ) != (content_sha256(parent_delta), content_sha256(parent_proof)):
        raise ValueError("selector recovery latest authorization chain differs")
    finalization, binding = _terminal_parts(state)
    if (
        finalization.outcome is not ProviderCallOutcome.INVALID_OUTPUT
        or finalization.failure_code != "structured_output_invalid"
    ):
        raise ValueError("selector recovery latest source is not invalid output")
    if (
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
        raise ValueError("selector recovery latest diagnostic bindings differ")
    return SelectorRecoverySourceAttempt(
        attempt_sequence=TOTAL_SOURCE_ATTEMPT_COUNT,
        lineage="post_parent_delta_selector_attempt",
        candidate_id=candidate_id,
        authorization_sha256=content_sha256(authorization),
        state_sha256=content_sha256(state),
        diagnostic_sha256=content_sha256(diagnostic),
        provider_call_count=len(state.provider_ledger.calls),
        provider_spend_microusd=_provider_spend(state),
        terminal_at=finalization.created_at,
        terminal_role=binding.role,
        terminal_outcome=finalization.outcome,
        terminal_failure_code=finalization.failure_code,
        response_schema_sha256=binding.response_schema_sha256,
        validation_error_count=len(diagnostic.issues),
    )


def _successful_sources(
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_states_by_hash: dict[
        str,
        TogetherCandidateCapabilityExecutionState,
    ],
    latest_state: TogetherDeltaCandidateExecutionState,
) -> list[_SuccessfulSource]:
    sources: list[_SuccessfulSource] = []
    for carry in parent_delta.carried_forward_successes:
        state = parent_states_by_hash[carry.source_state_sha256]
        outputs = [
            item
            for item in state.outputs
            if (item.candidate_id, item.role) == (
                carry.candidate_id,
                carry.role,
            )
        ]
        if len(outputs) != 1:
            raise ValueError("selector recovery parent output differs")
        output = outputs[0]
        bindings = {
            item.call_id: item for item in state.provider_journal.request_bindings
        }
        finalizations = {
            item.call_id: item for item in state.provider_journal.finalizations
        }
        binding = bindings[output.call_id]
        finalization = finalizations[output.call_id]
        if (
            content_sha256(binding),
            content_sha256(finalization),
            output.output_sha256,
        ) != (
            carry.source_request_binding_sha256,
            carry.finalization_sha256,
            carry.source_output_sha256,
        ):
            raise ValueError("selector recovery parent carry audit differs")
        attempt_sequence = next(
            index
            for index, item in enumerate(parent_delta.source_attempts, start=1)
            if item.state_sha256 == carry.source_state_sha256
        )
        sources.append(
            _SuccessfulSource(
                attempt_sequence=attempt_sequence,
                state_sha256=carry.source_state_sha256,
                output=output,
                binding=binding,
                parent_request_binding_sha256=(
                    carry.corrected_request_binding_sha256
                ),
                finalization=finalization,
            )
        )
    latest_bindings = {
        item.call_id: item for item in latest_state.provider_journal.request_bindings
    }
    latest_finalizations = {
        item.call_id: item for item in latest_state.provider_journal.finalizations
    }
    for output in latest_state.outputs:
        finalization = latest_finalizations[output.call_id]
        if finalization.outcome is not ProviderCallOutcome.SUCCESS:
            raise ValueError("selector recovery stored output is not successful")
        sources.append(
            _SuccessfulSource(
                attempt_sequence=TOTAL_SOURCE_ATTEMPT_COUNT,
                state_sha256=content_sha256(latest_state),
                output=output,
                binding=latest_bindings[output.call_id],
                parent_request_binding_sha256=content_sha256(
                    latest_bindings[output.call_id]
                ),
                finalization=finalization,
            )
        )
    coordinates = [
        (item.output.candidate_id, item.output.role) for item in sources
    ]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("selector recovery successful coordinates overlap")
    return sources


def _carried_successes(
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_plan: TogetherCapabilityPlan,
    parent_suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    parent_readiness: Phase4TogetherReadinessBundle,
    corrected_plan: TogetherCapabilityPlan,
    corrected_suite: Phase4TogetherSuite,
    corrected_readiness: Phase4TogetherReadinessBundle,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    parent_states_by_hash: dict[
        str,
        TogetherCandidateCapabilityExecutionState,
    ],
    latest_state: TogetherDeltaCandidateExecutionState,
) -> list[SelectorRecoveryCarriedSuccess]:
    parent_calls = {
        (item.candidate_id, item.role): item for item in parent_plan.calls
    }
    corrected_calls = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    parent_entries = {
        item.coordinate.call_id: item
        for item in parent_readiness.qualification_manifest.entries
    }
    corrected_entries = {
        item.coordinate.call_id: item
        for item in corrected_readiness.qualification_manifest.entries
    }
    carried: list[SelectorRecoveryCarriedSuccess] = []
    for source in _successful_sources(
        parent_delta,
        parent_states_by_hash,
        latest_state,
    ):
        coordinate = (source.output.candidate_id, source.output.role)
        parent_call = parent_calls.get(coordinate)
        corrected_call = corrected_calls.get(coordinate)
        if parent_call is None or corrected_call is None:
            continue
        parent_entry = parent_entries.get(parent_call.call_id)
        corrected_entry = corrected_entries.get(corrected_call.call_id)
        if parent_entry is None or corrected_entry is None:
            continue
        parent_rebuilt = rebuild_qualification_call(
            parent_suite,
            profile,
            fixture,
            session,
            semantic_map,
            parent_entry,
            created_at=source.binding.created_at,
        )
        corrected_rebuilt = rebuild_qualification_call(
            corrected_suite,
            profile,
            fixture,
            session,
            semantic_map,
            corrected_entry,
            created_at=source.binding.created_at,
        )
        if content_sha256(parent_rebuilt.request.binding) != (
            source.parent_request_binding_sha256
        ):
            continue
        parent_transmitted = (
            parent_rebuilt.request.privacy_attestation.transmitted_payload_sha256
        )
        corrected_transmitted = (
            corrected_rebuilt.request.privacy_attestation
            .transmitted_payload_sha256
        )
        source_validator = (
            parent_rebuilt.request.binding.response_validator_sha256
        )
        corrected_validator = (
            corrected_rebuilt.request.binding.response_validator_sha256
        )
        if (
            parent_transmitted != corrected_transmitted
            or source_validator is None
            or corrected_validator is None
            or source.finalization.outcome is not ProviderCallOutcome.SUCCESS
            or source.finalization.response_sha256
            != source.output.output_sha256
        ):
            continue
        try:
            validated = corrected_rebuilt.response_adapter.validate_python(
                source.output.output_payload
            )
            canonical = corrected_rebuilt.response_adapter.dump_python(
                validated,
                mode="json",
            )
        except (ValidationError, TypeError, ValueError):
            continue
        corrected_output_sha256 = content_sha256(canonical)
        if corrected_output_sha256 != source.output.output_sha256:
            continue
        carried.append(
            SelectorRecoveryCarriedSuccess(
                candidate_id=source.output.candidate_id,
                role=source.output.role,
                source_attempt_sequence=source.attempt_sequence,
                source_state_sha256=source.state_sha256,
                source_call_plan_sha256=content_sha256(parent_call),
                corrected_call_plan_sha256=content_sha256(corrected_call),
                source_request_binding_sha256=content_sha256(
                    parent_rebuilt.request.binding
                ),
                corrected_request_binding_sha256=content_sha256(
                    corrected_rebuilt.request.binding
                ),
                source_response_validator_sha256=source_validator,
                corrected_response_validator_sha256=corrected_validator,
                source_transmitted_payload_sha256=parent_transmitted,
                corrected_transmitted_payload_sha256=corrected_transmitted,
                finalization_sha256=content_sha256(source.finalization),
                source_output_sha256=source.output.output_sha256,
                corrected_revalidated_output_sha256=corrected_output_sha256,
            )
        )
    return sorted(carried, key=lambda item: (item.candidate_id, item.role.value))


def build_selector_recovery_delta_plan(
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
    parent_source_states: Sequence[TogetherCandidateCapabilityExecutionState],
    latest_authorization: TogetherDeltaCandidateAuthorizationBundle,
    latest_state: TogetherDeltaCandidateExecutionState,
    latest_diagnostic: ProviderStructuredOutputDiagnostic,
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
    *,
    plan_id: str,
    created_at: datetime,
) -> TogetherSelectorRecoveryDeltaPlan:
    """Rebuild the exact four-attempt chain without network or credentials."""

    validate_capability_delta_source_proof(parent_proof, parent_delta)
    parent_bindings = (
        content_sha256(parent_suite),
        content_sha256(parent_readiness),
        content_sha256(parent_plan),
    )
    if parent_bindings != (
        parent_delta.corrected_suite_sha256,
        parent_delta.corrected_readiness_sha256,
        parent_delta.corrected_capability_plan_sha256,
    ):
        raise ValueError("selector recovery parent corrected artifacts differ")
    validate_capability_plan(
        parent_plan,
        parent_suite,
        profile,
        parent_readiness,
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
    if parent_suite.suite_version >= corrected_suite.suite_version:
        raise ValueError("selector recovery corrected suite is not newer")
    if (
        parent_suite.robustness_profile_sha256,
        parent_suite.catalog,
        parent_suite.provider_terms,
        parent_suite.candidates,
        parent_suite.workload,
    ) != (
        corrected_suite.robustness_profile_sha256,
        corrected_suite.catalog,
        corrected_suite.provider_terms,
        corrected_suite.candidates,
        corrected_suite.workload,
    ):
        raise ValueError("selector recovery changed non-contract suite inputs")
    if response_semantics_manifest != PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2:
        raise ValueError("selector recovery semantics manifest differs")
    attempts, parent_states_by_hash = _parent_attempt_records(
        parent_delta,
        parent_source_states,
    )
    latest_attempt = _latest_attempt_record(
        parent_delta,
        parent_proof,
        parent_plan,
        parent_suite,
        profile,
        parent_readiness,
        latest_authorization,
        latest_state,
        latest_diagnostic,
    )
    attempts.append(latest_attempt)
    carried = _carried_successes(
        parent_delta,
        parent_plan,
        parent_suite,
        profile,
        parent_readiness,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        fixture,
        session,
        semantic_map,
        parent_states_by_hash,
        latest_state,
    )
    if len(carried) != EXPECTED_CARRY_COUNT:
        raise ValueError("selector recovery did not prove five exact carries")
    carry_coordinates = {(item.candidate_id, item.role) for item in carried}
    rerun_calls = [
        item.model_copy(deep=True)
        for item in corrected_plan.calls
        if (item.candidate_id, item.role) not in carry_coordinates
    ]
    if len(rerun_calls) != EXPECTED_RERUN_COUNT:
        raise ValueError("selector recovery did not derive ten reruns")
    parent_spend = parent_delta.prior_provider_spend_microusd
    latest_spend = latest_attempt.provider_spend_microusd
    additional_projected = sum(
        item.projected_cost_microusd for item in rerun_calls
    )
    additional_authorized = sum(
        item.authorized_max_cost_microusd for item in rerun_calls
    )
    return TogetherSelectorRecoveryDeltaPlan(
        plan_id=plan_id,
        created_at=created_at,
        parent_delta_plan_sha256=content_sha256(parent_delta),
        parent_delta_source_proof_sha256=content_sha256(parent_proof),
        parent_corrected_suite_sha256=content_sha256(parent_suite),
        parent_corrected_readiness_sha256=content_sha256(parent_readiness),
        parent_corrected_capability_plan_sha256=content_sha256(parent_plan),
        corrected_suite_sha256=content_sha256(corrected_suite),
        corrected_readiness_sha256=content_sha256(corrected_readiness),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        provider_response_semantics_manifest_sha256=content_sha256(
            response_semantics_manifest
        ),
        latest_selector_authorization_sha256=content_sha256(
            latest_authorization
        ),
        latest_selector_state_sha256=content_sha256(latest_state),
        latest_selector_diagnostic_sha256=content_sha256(latest_diagnostic),
        source_attempts=attempts,
        carried_forward_successes=carried,
        rerun_calls=rerun_calls,
        parent_cumulative_provider_spend_microusd=parent_spend,
        latest_selector_provider_spend_microusd=latest_spend,
        prior_provider_spend_microusd=parent_spend + latest_spend,
        additional_projected_cost_microusd=additional_projected,
        additional_authorized_max_cost_microusd=additional_authorized,
        cumulative_worst_case_spend_microusd=(
            parent_spend + latest_spend + additional_authorized
        ),
    )


def validate_selector_recovery_delta_plan(
    delta: TogetherSelectorRecoveryDeltaPlan,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
    parent_source_states: Sequence[TogetherCandidateCapabilityExecutionState],
    latest_authorization: TogetherDeltaCandidateAuthorizationBundle,
    latest_state: TogetherDeltaCandidateExecutionState,
    latest_diagnostic: ProviderStructuredOutputDiagnostic,
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
    rebuilt = build_selector_recovery_delta_plan(
        parent_delta,
        parent_proof,
        parent_source_states,
        latest_authorization,
        latest_state,
        latest_diagnostic,
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
        plan_id=delta.plan_id,
        created_at=delta.created_at,
    )
    if delta != rebuilt:
        raise ValueError("selector recovery delta does not rebuild")


def validate_selector_recovery_source_proof(
    proof: TogetherSelectorRecoverySourceProof,
    delta: TogetherSelectorRecoveryDeltaPlan,
) -> None:
    if proof.validated_at < delta.created_at:
        raise ValueError("selector recovery proof predates delta")
    actual = (
        proof.selector_recovery_delta_sha256,
        proof.parent_delta_plan_sha256,
        proof.parent_delta_source_proof_sha256,
        proof.latest_selector_authorization_sha256,
        proof.latest_selector_state_sha256,
        proof.latest_selector_diagnostic_sha256,
        proof.source_attempts_sha256,
        proof.carried_forward_successes_sha256,
        proof.rerun_calls_sha256,
        proof.provider_response_semantics_manifest_sha256,
    )
    expected = (
        content_sha256(delta),
        delta.parent_delta_plan_sha256,
        delta.parent_delta_source_proof_sha256,
        delta.latest_selector_authorization_sha256,
        delta.latest_selector_state_sha256,
        delta.latest_selector_diagnostic_sha256,
        _records_sha256(delta.source_attempts),
        _records_sha256(delta.carried_forward_successes),
        _records_sha256(delta.rerun_calls),
        delta.provider_response_semantics_manifest_sha256,
    )
    if actual != expected:
        raise ValueError("selector recovery source proof bindings differ")


def build_selector_recovery_source_proof(
    delta: TogetherSelectorRecoveryDeltaPlan,
    parent_delta: TogetherCapabilityDeltaPlan,
    parent_proof: TogetherCapabilityDeltaSourceProof,
    parent_source_states: Sequence[TogetherCandidateCapabilityExecutionState],
    latest_authorization: TogetherDeltaCandidateAuthorizationBundle,
    latest_state: TogetherDeltaCandidateExecutionState,
    latest_diagnostic: ProviderStructuredOutputDiagnostic,
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
    *,
    proof_id: str,
    validated_at: datetime,
) -> TogetherSelectorRecoverySourceProof:
    validate_selector_recovery_delta_plan(
        delta,
        parent_delta,
        parent_proof,
        parent_source_states,
        latest_authorization,
        latest_state,
        latest_diagnostic,
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
    proof = TogetherSelectorRecoverySourceProof(
        proof_id=proof_id,
        validated_at=validated_at,
        selector_recovery_delta_sha256=content_sha256(delta),
        parent_delta_plan_sha256=delta.parent_delta_plan_sha256,
        parent_delta_source_proof_sha256=(
            delta.parent_delta_source_proof_sha256
        ),
        latest_selector_authorization_sha256=(
            delta.latest_selector_authorization_sha256
        ),
        latest_selector_state_sha256=delta.latest_selector_state_sha256,
        latest_selector_diagnostic_sha256=(
            delta.latest_selector_diagnostic_sha256
        ),
        source_attempts_sha256=_records_sha256(delta.source_attempts),
        carried_forward_successes_sha256=_records_sha256(
            delta.carried_forward_successes
        ),
        rerun_calls_sha256=_records_sha256(delta.rerun_calls),
        provider_response_semantics_manifest_sha256=(
            delta.provider_response_semantics_manifest_sha256
        ),
    )
    validate_selector_recovery_source_proof(proof, delta)
    return proof


def validate_selector_recovery_public_artifacts(
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
    """Recheck the complete tracked chain without loading private sources."""

    validate_capability_delta_source_proof(parent_proof, parent_delta)
    validate_selector_recovery_source_proof(proof, delta)
    expected_bindings = (
        content_sha256(parent_delta),
        content_sha256(parent_proof),
        content_sha256(parent_plan),
        content_sha256(parent_suite),
        content_sha256(parent_readiness),
        content_sha256(corrected_plan),
        content_sha256(corrected_suite),
        content_sha256(corrected_readiness),
        content_sha256(response_semantics_manifest),
    )
    actual_bindings = (
        delta.parent_delta_plan_sha256,
        delta.parent_delta_source_proof_sha256,
        delta.parent_corrected_capability_plan_sha256,
        delta.parent_corrected_suite_sha256,
        delta.parent_corrected_readiness_sha256,
        delta.corrected_capability_plan_sha256,
        delta.corrected_suite_sha256,
        delta.corrected_readiness_sha256,
        delta.provider_response_semantics_manifest_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("selector recovery public artifact bindings differ")
    if response_semantics_manifest != PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2:
        raise ValueError("selector recovery public semantics manifest differs")
    validate_capability_plan(
        parent_plan,
        parent_suite,
        profile,
        parent_readiness,
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
    corrected_by_coordinate = {
        (item.candidate_id, item.role): item for item in corrected_plan.calls
    }
    parent_by_coordinate = {
        (item.candidate_id, item.role): item for item in parent_plan.calls
    }
    carried_coordinates = {
        (item.candidate_id, item.role)
        for item in delta.carried_forward_successes
    }
    for carried in delta.carried_forward_successes:
        parent_call = parent_by_coordinate.get(
            (carried.candidate_id, carried.role)
        )
        corrected_call = corrected_by_coordinate.get(
            (carried.candidate_id, carried.role)
        )
        if (
            parent_call is None
            or corrected_call is None
            or content_sha256(parent_call)
            != carried.source_call_plan_sha256
            or content_sha256(corrected_call)
            != carried.corrected_call_plan_sha256
        ):
            raise ValueError("selector recovery carried plan binding differs")
    expected_reruns = [
        item
        for item in corrected_plan.calls
        if (item.candidate_id, item.role) not in carried_coordinates
    ]
    if delta.rerun_calls != expected_reruns:
        raise ValueError("selector recovery public rerun partition differs")


def selector_recovery_summary(
    delta: TogetherSelectorRecoveryDeltaPlan,
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


def load_selector_recovery_delta(
    path: str | Path,
) -> TogetherSelectorRecoveryDeltaPlan:
    return TogetherSelectorRecoveryDeltaPlan.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_selector_recovery_source_proof(
    path: str | Path,
) -> TogetherSelectorRecoverySourceProof:
    return TogetherSelectorRecoverySourceProof.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
