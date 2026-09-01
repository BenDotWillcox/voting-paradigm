"""Assemble the private two-deployment qualification result from audits.

This module is deliberately provider-free.  It validates the frozen public
chain, the exact paid authorization, the historical carry sources, and both
candidate-isolated terminal states before converting them into the generic
observation surface consumed by :mod:`eval.phase4_two_deployment_result`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from .fixture_io import content_sha256
from .phase4_capability import TogetherCapabilityOutputRecord
from .phase4_capability_aggregation import (
    Phase4CapabilityAggregation,
    Phase4CapabilityAggregationSourceProof,
)
from .phase4_capability_retry import (
    TogetherCapabilityDiagnosticRetryPlan,
    TogetherCapabilityDiagnosticRetrySourceProof,
)
from .phase4_provider import ProviderCallOutcome
from .phase4_qualification_execution import (
    CapabilitySourceState,
    QualificationCallDisposition,
    TwoDeploymentQualificationCarryBundle,
    TwoDeploymentQualificationExecutionPlan,
)
from .phase4_qualification_runtime import (
    QualificationExecutionStatus,
    QualificationOutputRecord,
    TwoDeploymentCandidateExecutionState,
    TwoDeploymentQualificationAuthorizationBundle,
    validate_two_deployment_candidate_state,
    validate_two_deployment_qualification_authorization,
)
from .phase4_qualification_scope import (
    QualificationScopePublicInputs,
    TwoDeploymentQualificationScopeAmendment,
    TwoDeploymentQualificationScopeEvidenceProof,
    validate_two_deployment_qualification_scope,
)
from .phase4_readiness import Phase4TogetherReadinessBundle
from .phase4_robustness import LLMRole, Phase4ERobustnessProfile
from .phase4_together import Phase4TogetherSuite
from .phase4_together_live import TogetherCatalogPreflightBundle
from .phase4_two_deployment_result import (
    InterviewerToolReplayStatus,
    QualificationCallObservation,
    QualificationCandidateAttemptStatus,
    QualificationObservationSource,
    QualificationResultSourceBindings,
    TwoDeploymentQualificationAggregateReceipt,
    TwoDeploymentQualificationResult,
    build_two_deployment_qualification_aggregate_receipt,
    build_two_deployment_qualification_result,
    validate_two_deployment_qualification_aggregate_receipt,
    validate_two_deployment_qualification_result,
)


_TERMINAL_STATUS_MAP = {
    QualificationExecutionStatus.COMPLETED: (
        QualificationCandidateAttemptStatus.COMPLETED
    ),
    QualificationExecutionStatus.CANDIDATE_HARD_FAILURE: (
        QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE
    ),
    QualificationExecutionStatus.PROVIDER_PAUSED: (
        QualificationCandidateAttemptStatus.PROVIDER_PAUSED
    ),
    QualificationExecutionStatus.AMBIGUOUS_DELIVERY: (
        QualificationCandidateAttemptStatus.AMBIGUOUS_DELIVERY
    ),
    QualificationExecutionStatus.HARNESS_PAUSED: (
        QualificationCandidateAttemptStatus.HARNESS_PAUSED
    ),
}


def _plan_calls_by_id(
    plan: TwoDeploymentQualificationExecutionPlan,
):
    calls = {
        call.call_id: call
        for candidate in plan.candidate_plans
        for call in candidate.calls
    }
    if len(calls) != sum(
        len(candidate.calls) for candidate in plan.candidate_plans
    ):
        raise ValueError("qualification result plan call ids are not unique")
    return calls


def _source_states_by_sha256(
    source_states: Sequence[CapabilitySourceState],
) -> dict[str, CapabilitySourceState]:
    result = {content_sha256(item): item for item in source_states}
    if len(result) != len(source_states):
        raise ValueError("qualification carry source states are duplicated")
    return result


def _carried_observations(
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    source_states: Sequence[CapabilitySourceState],
) -> list[QualificationCallObservation]:
    calls = _plan_calls_by_id(plan)
    states = _source_states_by_sha256(source_states)
    if set(states) != set(carry.source_state_sha256s):
        raise ValueError("qualification carry source-state inventory differs")
    observations: list[QualificationCallObservation] = []
    for record in carry.records:
        call = calls.get(record.call_id)
        state = states.get(record.source_state_sha256)
        if call is None or state is None:
            raise ValueError("qualification carry result source is missing")
        if call.disposition is not QualificationCallDisposition.CARRIED_SUCCESS:
            raise ValueError("qualification carry result replays a provider call")
        if (
            content_sha256(state.provider_ledger)
            != record.source_provider_ledger_sha256
            or content_sha256(state.provider_journal)
            != record.source_provider_journal_sha256
            or state.authorization_bundle_sha256
            != record.source_authorization_sha256
        ):
            raise ValueError("qualification carry source-state lineage differs")
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
            binding = bindings[record.call_id]
            authorization = authorizations[record.call_id]
            usage = usages[record.call_id]
            finalization = finalizations[record.call_id]
            output: TogetherCapabilityOutputRecord = outputs[record.call_id]
        except KeyError as error:
            raise ValueError(
                "qualification carry result source chain is incomplete"
            ) from error
        hashes = (
            content_sha256(binding),
            content_sha256(authorization),
            content_sha256(usage),
            content_sha256(finalization),
            output.output_sha256,
        )
        expected = (
            record.request_binding_sha256,
            record.provider_authorization_sha256,
            record.provider_usage_sha256,
            record.finalization_sha256,
            record.source_output_sha256,
        )
        if hashes != expected or output.output_payload != record.output_payload:
            raise ValueError("qualification carry result evidence differs")
        if (
            output.call_id,
            output.candidate_id,
            output.role,
            state.schema_version,
        ) != (
            record.call_id,
            record.candidate_id,
            record.role,
            record.source_state_schema_version,
        ):
            raise ValueError("qualification carry output identity differs")
        observations.append(
            QualificationCallObservation(
                source_manifest_ordinal=record.source_manifest_ordinal,
                source_entry_sha256=record.source_entry_sha256,
                call_id=record.call_id,
                candidate_id=record.candidate_id,
                measure_id=call.source_entry.coordinate.measure_id,
                measure_version=call.source_entry.coordinate.measure_version,
                role=record.role,
                variant_id=call.source_entry.coordinate.variant_id,
                source=(
                    QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS
                ),
                request_binding=binding,
                request_binding_sha256=content_sha256(binding),
                request_content_sha256=usage.request_sha256,
                usage=usage,
                usage_sha256=content_sha256(usage),
                finalization=finalization,
                finalization_sha256=content_sha256(finalization),
                output_sha256=output.output_sha256,
                parsed_output=output.output_payload,
                exact_role_contract_valid=True,
                interviewer_tool_replay_status=(
                    InterviewerToolReplayStatus.HISTORICAL_UNVERIFIABLE
                    if record.role is LLMRole.INTERVIEWER
                    else InterviewerToolReplayStatus.NOT_APPLICABLE
                ),
            )
        )
    return observations


def build_new_qualification_observations(
    plan: TwoDeploymentQualificationExecutionPlan,
    candidate_states: Sequence[TwoDeploymentCandidateExecutionState],
) -> list[QualificationCallObservation]:
    """Rebuild new-call observations from exact candidate audit states."""

    calls = _plan_calls_by_id(plan)
    observations: list[QualificationCallObservation] = []
    for state in candidate_states:
        bindings = {
            item.call_id: item for item in state.provider_journal.request_bindings
        }
        usages = {item.call_id: item for item in state.provider_ledger.calls}
        authorizations = {
            item.call_id: item for item in state.provider_ledger.authorizations
        }
        outputs: dict[str, QualificationOutputRecord] = {
            item.call_id: item for item in state.outputs
        }
        replay_counts = Counter(
            item.call_id for item in state.tool_replay_records
        )
        for finalization in state.provider_journal.finalizations:
            call = calls.get(finalization.call_id)
            if call is None or call.disposition is not (
                QualificationCallDisposition.EXECUTE_PROVIDER
            ):
                raise ValueError("qualification result includes an unplanned call")
            if call.candidate_id != state.candidate_id:
                raise ValueError("qualification result state mixes candidates")
            try:
                binding = bindings[call.call_id]
                authorization = authorizations[call.call_id]
                usage = usages[call.call_id]
            except KeyError as error:
                raise ValueError(
                    "qualification result provider chain is incomplete"
                ) from error
            if (
                finalization.authorization_sha256
                != content_sha256(authorization)
                or usage.authorization_sha256 != content_sha256(authorization)
            ):
                raise ValueError("qualification result authorization differs")
            successful = finalization.outcome in {
                ProviderCallOutcome.SUCCESS,
                ProviderCallOutcome.CACHE_HIT,
            }
            output = outputs.get(call.call_id)
            if successful != (output is not None):
                raise ValueError("qualification result output coverage differs")
            if output is not None and (
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
                call.source_entry.coordinate.measure_id,
                call.source_entry.coordinate.measure_version,
                call.role,
                call.source_entry.coordinate.variant_id.value,
            ):
                raise ValueError("qualification result output identity differs")
            if call.role is LLMRole.INTERVIEWER:
                replay_status = (
                    InterviewerToolReplayStatus.VERIFIED
                    if (
                        finalization.tool_call_count > 0
                        and finalization.tool_call_failure_count == 0
                        and replay_counts[call.call_id]
                        == finalization.tool_call_count
                    )
                    else InterviewerToolReplayStatus.FAILED
                )
            else:
                replay_status = InterviewerToolReplayStatus.NOT_APPLICABLE
            observations.append(
                QualificationCallObservation(
                    source_manifest_ordinal=call.source_manifest_ordinal,
                    source_entry_sha256=call.source_entry_sha256,
                    call_id=call.call_id,
                    candidate_id=call.candidate_id,
                    measure_id=call.source_entry.coordinate.measure_id,
                    measure_version=call.source_entry.coordinate.measure_version,
                    role=call.role,
                    variant_id=call.source_entry.coordinate.variant_id,
                    source=QualificationObservationSource.NEW_QUALIFICATION_CALL,
                    request_binding=binding,
                    request_binding_sha256=content_sha256(binding),
                    request_content_sha256=usage.request_sha256,
                    usage=usage,
                    usage_sha256=content_sha256(usage),
                    finalization=finalization,
                    finalization_sha256=content_sha256(finalization),
                    output_sha256=(output.output_sha256 if output else None),
                    parsed_output=(output.output_payload if output else None),
                    exact_role_contract_valid=(
                        True
                        if successful
                        else (
                            False
                            if finalization.outcome
                            is ProviderCallOutcome.INVALID_OUTPUT
                            else None
                        )
                    ),
                    interviewer_tool_replay_status=replay_status,
                )
            )
    return observations


def build_result_sources_and_observations(
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    source_states: Sequence[CapabilitySourceState],
    candidate_states: Sequence[TwoDeploymentCandidateExecutionState],
) -> tuple[QualificationResultSourceBindings, list[QualificationCallObservation]]:
    """Convert exact private audits into the result contract's input surface."""

    states_by_candidate = {item.candidate_id: item for item in candidate_states}
    expected_candidates = [item.candidate_id for item in plan.candidate_plans]
    if set(states_by_candidate) != set(expected_candidates) or len(
        states_by_candidate
    ) != len(candidate_states):
        raise ValueError("qualification result requires both candidate states")
    statuses: dict[str, QualificationCandidateAttemptStatus] = {}
    for candidate_id in expected_candidates:
        state = states_by_candidate[candidate_id]
        status = _TERMINAL_STATUS_MAP.get(state.status)
        if status is None:
            raise ValueError("qualification result requires terminal candidate states")
        statuses[candidate_id] = status
    bindings = QualificationResultSourceBindings(
        execution_plan_sha256=content_sha256(plan),
        carry_bundle_sha256=content_sha256(carry),
        authorization_bundle_sha256=content_sha256(authorization),
        candidate_state_sha256s={
            candidate_id: content_sha256(states_by_candidate[candidate_id])
            for candidate_id in expected_candidates
        },
        candidate_attempt_statuses=statuses,
    )
    observations = [
        *_carried_observations(plan, carry, source_states),
        *build_new_qualification_observations(plan, candidate_states),
    ]
    observations.sort(key=lambda item: item.source_manifest_ordinal)
    if len({item.call_id for item in observations}) != len(observations):
        raise ValueError("qualification result observations are duplicated")
    return bindings, observations


def assemble_two_deployment_qualification_result(
    scope: TwoDeploymentQualificationScopeAmendment,
    scope_proof: TwoDeploymentQualificationScopeEvidenceProof,
    aggregation: Phase4CapabilityAggregation,
    aggregation_proof: Phase4CapabilityAggregationSourceProof,
    retry_plan: TogetherCapabilityDiagnosticRetryPlan,
    retry_proof: TogetherCapabilityDiagnosticRetrySourceProof,
    public_inputs: QualificationScopePublicInputs,
    plan: TwoDeploymentQualificationExecutionPlan,
    carry: TwoDeploymentQualificationCarryBundle,
    authorization: TwoDeploymentQualificationAuthorizationBundle,
    catalog: TogetherCatalogPreflightBundle,
    source_states: Sequence[CapabilitySourceState],
    candidate_states: Sequence[TwoDeploymentCandidateExecutionState],
    *,
    qualification_id: str,
    receipt_id: str,
    created_at: datetime,
) -> tuple[
    TwoDeploymentQualificationResult,
    TwoDeploymentQualificationAggregateReceipt,
]:
    """Validate all source artifacts, then build private and safe results."""

    suite: Phase4TogetherSuite = public_inputs.corrected_suite
    readiness: Phase4TogetherReadinessBundle = public_inputs.corrected_readiness
    profile: Phase4ERobustnessProfile = public_inputs.robustness_profile
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("qualification result time must include a timezone")
    receipts = [item.receipt for item in candidate_states]
    if any(item is None for item in receipts):
        raise ValueError("qualification result requires terminal receipts")
    if any(
        item is not None and item.completed_at > created_at for item in receipts
    ):
        raise ValueError("qualification result predates a candidate receipt")
    validate_two_deployment_qualification_scope(
        scope,
        scope_proof,
        aggregation,
        aggregation_proof,
        retry_plan,
        retry_proof,
        suite,
        readiness,
        profile,
        public_inputs,
    )
    validate_two_deployment_qualification_authorization(
        authorization,
        scope,
        scope_proof,
        plan,
        carry,
        aggregation,
        public_inputs.corrected_capability_plan,
        suite,
        profile,
        readiness,
        public_inputs.development_fixture,
        public_inputs.development_session,
        public_inputs.development_semantic_map,
        source_states,
        catalog,
        now=authorization.manual_approval.approved_at,
    )
    for state in candidate_states:
        validate_two_deployment_candidate_state(
            state,
            plan,
            authorization,
            carry,
            suite,
            profile,
        )
    source_bindings, observations = build_result_sources_and_observations(
        plan,
        carry,
        authorization,
        source_states,
        candidate_states,
    )
    result = build_two_deployment_qualification_result(
        scope,
        readiness,
        profile,
        suite,
        public_inputs.development_fixture,
        public_inputs.development_session,
        plan,
        source_bindings,
        observations,
        qualification_id=qualification_id,
        qualification_version=1,
        created_at=created_at,
    )
    validate_two_deployment_qualification_result(
        result,
        scope,
        readiness,
        profile,
        suite,
        public_inputs.development_fixture,
        public_inputs.development_session,
        plan,
    )
    receipt = build_two_deployment_qualification_aggregate_receipt(
        result,
        receipt_id=receipt_id,
    )
    validate_two_deployment_qualification_aggregate_receipt(receipt, result)
    return result, receipt
