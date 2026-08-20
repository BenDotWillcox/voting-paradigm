"""Auditable three-candidate Phase 4E qualification artifacts."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from statistics import fmean
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    PositiveVersion,
    Probability,
    Sha256Digest,
    StableId,
    require_complete_enum_set,
)
from .fixture_io import content_sha256
from .phase4_provider import (
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderExecutionJournal,
    ProviderPriceCard,
    price_provider_tokens,
    validate_provider_execution_journal,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    OpenWeightModelCandidate,
    Phase4ERobustnessProfile,
    ProviderUsageLedger,
    QualificationCriterion,
    RobustnessAggregate,
    RobustnessPerturbationKind,
)

Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]
BoundedBrierScore = Annotated[
    float,
    Field(ge=0.0, le=2.0, allow_inf_nan=False),
]
PHASE4E_HELD_OUT_CAP_MICROUSD = 13_000_000
PROVIDER_FAILURE_OUTCOMES = frozenset(
    {
        ProviderCallOutcome.PROVIDER_ERROR,
        ProviderCallOutcome.TRANSPORT_ERROR,
        ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
        ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
        ProviderCallOutcome.CANCELLED,
    }
)


class QualificationStatus(str, Enum):
    SELECTED = "selected"
    NO_CANDIDATE_QUALIFIED = "no_candidate_qualified"


class QualificationSelectionPolicy(ContractModel):
    """Frozen practical-equivalence bands for ordered candidate selection."""

    record_version: Literal["phase4_qualification_selection_policy.v1"] = (
        "phase4_qualification_selection_policy.v1"
    )
    method: Literal["sequential_best_plus_tolerance"] = (
        "sequential_best_plus_tolerance"
    )
    prompt_and_stochastic_mean_jsd_tolerance: Literal[0.001] = 0.001
    development_mean_log_loss_tolerance: Literal[0.01] = 0.01
    projected_cost_tolerance_microusd: Literal[100_000] = 100_000
    p95_latency_tolerance_ms: Literal[100.0] = 100.0


PHASE4_QUALIFICATION_SELECTION_POLICY = QualificationSelectionPolicy()


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


class ProviderCallAssessment(ContractModel):
    """Content-free role compliance evidence for one finalized call."""

    record_version: Literal["phase4_provider_call_assessment.v1"] = (
        "phase4_provider_call_assessment.v1"
    )
    call_id: StableId
    role: LLMRole
    finalization_sha256: Sha256Digest
    exact_role_contract_valid: bool
    tool_result_replay_valid: bool | None = None

    @model_validator(mode="after")
    def require_interviewer_tool_assessment_only(self) -> Self:
        if self.role is LLMRole.INTERVIEWER:
            if self.tool_result_replay_valid is None:
                raise ValueError("interviewer assessment requires tool replay result")
        elif self.tool_result_replay_valid is not None:
            raise ValueError("only interviewer calls have tool replay assessment")
        return self


class DevelopmentPredictionMetrics(ContractModel):
    """Public-development prediction quality for one exact candidate."""

    record_version: Literal["phase4_development_prediction_metrics.v1"] = (
        "phase4_development_prediction_metrics.v1"
    )
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    sample_count: PositiveCount
    mean_log_loss: NonNegativeFiniteFloat
    multiclass_brier: BoundedBrierScore
    top_choice_accuracy: Probability
    high_confidence_coverage: Probability
    high_confidence_delegated_error: Probability | None = None

    @model_validator(mode="after")
    def require_risk_only_with_coverage(self) -> Self:
        if self.high_confidence_coverage == 0.0:
            if self.high_confidence_delegated_error is not None:
                raise ValueError("zero coverage cannot report delegated error")
        elif self.high_confidence_delegated_error is None:
            raise ValueError("positive coverage requires delegated error")
        return self


class ProjectedRoleUsage(ContractModel):
    role: LLMRole
    request_count: PositiveCount
    input_tokens_per_request: NonNegativeCount
    output_tokens_per_request: NonNegativeCount


class ProviderCostProjection(ContractModel):
    """Deterministic selected-study projection from one exact price card."""

    record_version: Literal["phase4_provider_cost_projection.v1"] = (
        "phase4_provider_cost_projection.v1"
    )
    model_candidate_id: StableId
    price_card_sha256: Sha256Digest
    workload_id: StableId
    workload_version: PositiveVersion
    workload_sha256: Sha256Digest
    token_counter_id: StableId
    token_counter_version: PositiveVersion
    token_counter_sha256: Sha256Digest
    role_usage: list[ProjectedRoleUsage]
    projected_request_count: PositiveCount
    projected_cost_microusd: Microusd

    @model_validator(mode="after")
    def require_complete_role_projection(self) -> Self:
        require_complete_enum_set(
            "projected provider roles",
            [item.role for item in self.role_usage],
            LLMRole,
            set_name="Phase 4E v1",
        )
        if self.projected_request_count != sum(
            item.request_count for item in self.role_usage
        ):
            raise ValueError("projected provider request count does not reconcile")
        return self


def build_provider_cost_projection(
    candidate: OpenWeightModelCandidate,
    price_card: ProviderPriceCard,
    role_usage: list[ProjectedRoleUsage],
    *,
    workload_id: str,
    workload_version: int,
    workload_sha256: str,
    token_counter_id: str,
    token_counter_version: int,
    token_counter_sha256: str,
) -> ProviderCostProjection:
    if price_card.model_candidate_id != candidate.candidate_id or (
        price_card.model_candidate_sha256 != content_sha256(candidate)
    ):
        raise ValueError("cost projection price card does not bind candidate")
    projected_cost = sum(
        item.request_count
        * price_provider_tokens(
            price_card,
            input_tokens=item.input_tokens_per_request,
            output_tokens=item.output_tokens_per_request,
        )
        for item in role_usage
    )
    return ProviderCostProjection(
        model_candidate_id=candidate.candidate_id,
        price_card_sha256=content_sha256(price_card),
        workload_id=workload_id,
        workload_version=workload_version,
        workload_sha256=workload_sha256,
        token_counter_id=token_counter_id,
        token_counter_version=token_counter_version,
        token_counter_sha256=token_counter_sha256,
        role_usage=role_usage,
        projected_request_count=sum(item.request_count for item in role_usage),
        projected_cost_microusd=projected_cost,
    )


class CandidateQualificationResult(ContractModel):
    """Aggregate, content-free evidence used in deterministic selection."""

    record_version: Literal["phase4_candidate_qualification_result.v1"] = (
        "phase4_candidate_qualification_result.v1"
    )
    model_candidate_id: StableId
    model_candidate_artifact_version: PositiveVersion
    model_candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    call_ids: list[StableId]
    call_assessment_sha256s: list[Sha256Digest]
    robustness_aggregate_sha256s: list[Sha256Digest]
    role_call_counts: dict[LLMRole, NonNegativeCount]
    provider_call_count: NonNegativeCount
    provider_call_failure_count: NonNegativeCount
    invalid_output_count: NonNegativeCount
    role_contract_failure_count: NonNegativeCount
    interviewer_tool_call_failure_count: NonNegativeCount
    interviewer_tool_replay_failure_count: NonNegativeCount
    interviewer_tool_call_count: NonNegativeCount
    robustness_invalid_output_count: NonNegativeCount
    strict_transform_invalid_output_count: NonNegativeCount
    strict_transform_top_choice_flip_count: NonNegativeCount
    prompt_and_stochastic_mean_jsd: Probability | None = None
    development_metrics: DevelopmentPredictionMetrics
    cost_projection: ProviderCostProjection
    qualification_cost_microusd: Microusd
    p95_latency_ms: NonNegativeFiniteFloat
    hard_failure_reasons: list[StableId]
    passed_hard_gates: bool

    @model_validator(mode="after")
    def require_reconciled_hard_gates(self) -> Self:
        if len(self.call_ids) != len(set(self.call_ids)):
            raise ValueError("qualification call ids must be unique")
        if self.provider_call_count != len(self.call_ids):
            raise ValueError("qualification provider call count does not reconcile")
        if len(self.call_assessment_sha256s) != self.provider_call_count:
            raise ValueError("qualification assessment hashes do not reconcile")
        if len(self.call_assessment_sha256s) != len(
            set(self.call_assessment_sha256s)
        ):
            raise ValueError("qualification assessment hashes must be unique")
        if len(self.robustness_aggregate_sha256s) != len(
            RobustnessPerturbationKind
        ) or len(self.robustness_aggregate_sha256s) != len(
            set(self.robustness_aggregate_sha256s)
        ):
            raise ValueError("qualification robustness hashes do not reconcile")
        if set(self.role_call_counts) != set(LLMRole):
            raise ValueError("qualification result must count every LLM role")
        if sum(self.role_call_counts.values()) != self.provider_call_count:
            raise ValueError("qualification role-call counts do not reconcile")
        expected_failures: list[str] = []
        if any(count == 0 for count in self.role_call_counts.values()):
            expected_failures.append("required_role_missing")
        if self.provider_call_failure_count:
            expected_failures.append("provider_call_failure")
        if self.invalid_output_count:
            expected_failures.append("invalid_structured_output")
        if self.role_contract_failure_count:
            expected_failures.append("role_contract_failure")
        if self.interviewer_tool_call_failure_count:
            expected_failures.append("interviewer_tool_call_failure")
        if self.interviewer_tool_replay_failure_count:
            expected_failures.append("interviewer_tool_replay_failure")
        if self.interviewer_tool_call_count == 0:
            expected_failures.append("interviewer_tool_not_exercised")
        if self.robustness_invalid_output_count:
            expected_failures.append("robustness_invalid_output")
        if self.strict_transform_top_choice_flip_count:
            expected_failures.append("strict_transform_top_choice_flip")
        if (
            self.cost_projection.projected_cost_microusd
            > PHASE4E_HELD_OUT_CAP_MICROUSD
        ):
            expected_failures.append("projected_study_cost_over_cap")
        if self.hard_failure_reasons != expected_failures:
            raise ValueError("qualification hard-failure reasons do not reconcile")
        if self.passed_hard_gates != (not expected_failures):
            raise ValueError("qualification hard-gate outcome does not reconcile")
        if self.passed_hard_gates and (
            self.prompt_and_stochastic_mean_jsd is None
        ):
            raise ValueError("qualified candidate requires sensitivity metrics")
        if (
            self.cost_projection.model_candidate_id != self.model_candidate_id
            or self.cost_projection.price_card_sha256 != self.price_card_sha256
        ):
            raise ValueError("qualification cost projection binding does not match")
        if (
            self.strict_transform_invalid_output_count
            > self.robustness_invalid_output_count
        ):
            raise ValueError("strict invalid outputs exceed all robustness failures")
        return self


class Phase4QualificationBundle(ContractModel):
    """Auditable three-candidate selection on public development data only."""

    schema_version: Literal["preference_eval_phase4_qualification.v1"] = (
        "preference_eval_phase4_qualification.v1"
    )
    qualification_id: StableId
    qualification_version: PositiveVersion
    created_at: datetime
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    public_development_fixture_id: StableId
    public_development_fixture_version: PositiveVersion
    public_development_fixture_sha256: Sha256Digest
    candidates: list[OpenWeightModelCandidate]
    price_cards: list[ProviderPriceCard]
    provider_usage_ledger_sha256: Sha256Digest
    provider_execution_journal_sha256: Sha256Digest
    call_assessments: list[ProviderCallAssessment]
    robustness_aggregates: list[RobustnessAggregate]
    results: list[CandidateQualificationResult]
    selection_criteria_in_priority_order: list[QualificationCriterion]
    selection_policy: QualificationSelectionPolicy
    status: QualificationStatus
    selected_model_candidate_id: StableId | None = None
    restricted_participant_responses_visible: Literal[False] = False
    held_out_study_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "qualification created_at")
        return value

    @model_validator(mode="after")
    def require_exact_candidate_matrix_and_selection(self) -> Self:
        if len(self.candidates) != 3 or len(self.results) != 3:
            raise ValueError("Phase 4E qualification requires exactly 3 candidates")
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("qualification candidate ids must be unique")
        if candidate_ids != sorted(candidate_ids):
            raise ValueError("qualification candidates must use canonical order")
        price_ids = [item.model_candidate_id for item in self.price_cards]
        if price_ids != candidate_ids or len(price_ids) != 3:
            raise ValueError("qualification requires one price card per candidate")
        if len({item.price_card_id for item in self.price_cards}) != 3:
            raise ValueError("qualification price-card ids must be unique")
        result_ids = [item.model_candidate_id for item in self.results]
        if result_ids != candidate_ids:
            raise ValueError("qualification results must cover exact candidates")
        assessment_hashes = [
            content_sha256(item) for item in self.call_assessments
        ]
        if len(assessment_hashes) != len(set(assessment_hashes)):
            raise ValueError("qualification call assessments must be unique")
        expected_assessment_hashes = [
            digest
            for result in self.results
            for digest in result.call_assessment_sha256s
        ]
        if sorted(assessment_hashes) != sorted(expected_assessment_hashes):
            raise ValueError("qualification assessment source hashes do not match")
        aggregate_hashes = [
            content_sha256(item) for item in self.robustness_aggregates
        ]
        if len(aggregate_hashes) != len(set(aggregate_hashes)):
            raise ValueError("qualification robustness aggregates must be unique")
        expected_aggregate_hashes = [
            digest
            for result in self.results
            for digest in result.robustness_aggregate_sha256s
        ]
        if sorted(aggregate_hashes) != sorted(expected_aggregate_hashes):
            raise ValueError("qualification robustness source hashes do not match")
        candidates_by_id = {item.candidate_id: item for item in self.candidates}
        workload_bindings = {
            (
                item.cost_projection.workload_id,
                item.cost_projection.workload_version,
                item.cost_projection.workload_sha256,
            )
            for item in self.results
        }
        if len(workload_bindings) != 1:
            raise ValueError("qualification projections must share one workload")
        for result in self.results:
            candidate = candidates_by_id[result.model_candidate_id]
            if (
                result.model_candidate_artifact_version,
                result.model_candidate_sha256,
            ) != (candidate.artifact_version, content_sha256(candidate)):
                raise ValueError("qualification result candidate hash does not match")
            price_card = next(
                item
                for item in self.price_cards
                if item.model_candidate_id == result.model_candidate_id
            )
            if result.price_card_sha256 != content_sha256(price_card):
                raise ValueError("qualification result price-card hash does not match")
            if (
                result.cost_projection.model_candidate_id
                != result.model_candidate_id
                or result.cost_projection.price_card_sha256
                != result.price_card_sha256
            ):
                raise ValueError("qualification cost projection does not match")
            expected_projected_cost = sum(
                item.request_count
                * price_provider_tokens(
                    price_card,
                    input_tokens=item.input_tokens_per_request,
                    output_tokens=item.output_tokens_per_request,
                )
                for item in result.cost_projection.role_usage
            )
            if (
                result.cost_projection.projected_cost_microusd
                != expected_projected_cost
            ):
                raise ValueError("qualification projected cost does not reconcile")
            if (
                result.development_metrics.fixture_id,
                result.development_metrics.fixture_version,
                result.development_metrics.fixture_sha256,
            ) != (
                self.public_development_fixture_id,
                self.public_development_fixture_version,
                self.public_development_fixture_sha256,
            ):
                raise ValueError("qualification metrics do not bind public fixture")
        if self.selection_criteria_in_priority_order != list(
            QualificationCriterion
        ):
            raise ValueError("qualification criteria order does not match profile")
        if self.selection_policy != PHASE4_QUALIFICATION_SELECTION_POLICY:
            raise ValueError("qualification selection policy does not match v1")
        eligible = [item for item in self.results if item.passed_hard_gates]
        if not eligible:
            if (
                self.status is not QualificationStatus.NO_CANDIDATE_QUALIFIED
                or self.selected_model_candidate_id is not None
            ):
                raise ValueError("failed qualification cannot select a candidate")
            return self
        selected = _select_qualified_candidate(
            eligible,
            self.selection_policy,
        )
        if (
            self.status is not QualificationStatus.SELECTED
            or self.selected_model_candidate_id != selected.model_candidate_id
        ):
            raise ValueError("selected candidate does not follow frozen criteria")
        return self


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _select_qualified_candidate(
    eligible: list[CandidateQualificationResult],
    policy: QualificationSelectionPolicy,
) -> CandidateQualificationResult:
    if not eligible:
        raise ValueError("candidate selection requires an eligible candidate")
    if any(
        item.prompt_and_stochastic_mean_jsd is None for item in eligible
    ):
        raise ValueError("qualified candidate is missing sensitivity metrics")

    def sensitivity_of(item: CandidateQualificationResult) -> float:
        value = item.prompt_and_stochastic_mean_jsd
        if value is None:
            raise ValueError("qualified candidate is missing sensitivity metrics")
        return value

    remaining = list(eligible)
    ordered_bands = (
        (
            sensitivity_of,
            policy.prompt_and_stochastic_mean_jsd_tolerance,
        ),
        (
            lambda item: item.development_metrics.mean_log_loss,
            policy.development_mean_log_loss_tolerance,
        ),
        (
            lambda item: float(
                item.cost_projection.projected_cost_microusd
            ),
            float(policy.projected_cost_tolerance_microusd),
        ),
        (
            lambda item: item.p95_latency_ms,
            policy.p95_latency_tolerance_ms,
        ),
    )
    for value_of, tolerance in ordered_bands:
        best = min(value_of(item) for item in remaining)
        remaining = [
            item for item in remaining if value_of(item) <= best + tolerance
        ]
    return min(remaining, key=lambda item: item.model_candidate_id)


def build_candidate_qualification_result(
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
    price_card: ProviderPriceCard,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    assessments: list[ProviderCallAssessment],
    robustness_aggregates: list[RobustnessAggregate],
    development_metrics: DevelopmentPredictionMetrics,
    cost_projection: ProviderCostProjection,
) -> CandidateQualificationResult:
    """Derive all hard gates and ranking values from exact source artifacts."""

    requests = [
        item
        for item in journal.request_bindings
        if item.model_candidate_id == candidate.candidate_id
    ]
    call_ids = [item.call_id for item in requests]
    finalizations_by_id = {
        item.call_id: item for item in journal.finalizations
    }
    assessments_by_id = {item.call_id: item for item in assessments}
    if len(assessments_by_id) != len(assessments):
        raise ValueError("provider call assessment ids must be unique")
    if set(call_ids) != set(assessments_by_id):
        raise ValueError("qualification assessments must cover candidate calls")
    if not set(call_ids) <= set(finalizations_by_id):
        raise ValueError("qualification candidate has unfinished provider calls")
    usages_by_id = {item.call_id: item for item in ledger.calls}
    if not set(call_ids) <= set(usages_by_id):
        raise ValueError("qualification candidate has unmatched provider usage")
    role_counts = Counter(item.role for item in requests)
    requests_by_id = {item.call_id: item for item in requests}
    for call_id, assessment in assessments_by_id.items():
        if assessment.role is not requests_by_id[call_id].role or (
            assessment.finalization_sha256
            != content_sha256(finalizations_by_id[call_id])
        ):
            raise ValueError("qualification assessment binding does not match")
    provider_failure_count = sum(
        finalizations_by_id[call_id].outcome in PROVIDER_FAILURE_OUTCOMES
        for call_id in call_ids
    )
    invalid_output_count = sum(
        finalizations_by_id[call_id].outcome
        is ProviderCallOutcome.INVALID_OUTPUT
        for call_id in call_ids
    )
    role_contract_failures = sum(
        not assessments_by_id[call_id].exact_role_contract_valid
        for call_id in call_ids
    )
    tool_replay_failures = sum(
        assessment.tool_result_replay_valid is False
        for assessment in assessments
        if assessment.role is LLMRole.INTERVIEWER
    )
    interviewer_tool_calls = sum(
        finalizations_by_id[call_id].tool_call_count
        for call_id in call_ids
        if requests_by_id[call_id].role is LLMRole.INTERVIEWER
    )
    tool_call_failures = sum(
        finalizations_by_id[call_id].tool_call_failure_count
        for call_id in call_ids
        if requests_by_id[call_id].role is LLMRole.INTERVIEWER
    )
    candidate_aggregates = [
        item
        for item in robustness_aggregates
        if item.evaluation_binding.model_candidate_id == candidate.candidate_id
    ]
    perturbation_order = {
        kind: index for index, kind in enumerate(RobustnessPerturbationKind)
    }
    candidate_aggregates.sort(
        key=lambda item: perturbation_order[item.perturbation_kind]
    )
    kinds = [item.perturbation_kind for item in candidate_aggregates]
    if set(kinds) != set(RobustnessPerturbationKind) or len(kinds) != len(
        RobustnessPerturbationKind
    ):
        raise ValueError("qualification requires one aggregate per perturbation")
    for aggregate in candidate_aggregates:
        binding = aggregate.evaluation_binding
        if (
            binding.robustness_profile_id,
            binding.robustness_profile_version,
            binding.robustness_profile_sha256,
            binding.model_candidate_id,
            binding.model_candidate_artifact_version,
            binding.model_candidate_sha256,
        ) != (
            profile.profile_id,
            profile.profile_version,
            content_sha256(profile),
            candidate.candidate_id,
            candidate.artifact_version,
            content_sha256(candidate),
        ):
            raise ValueError("qualification robustness binding does not match")
    strict = [
        item
        for item in candidate_aggregates
        if item.perturbation_kind
        in {
            RobustnessPerturbationKind.OPTION_ORDER,
            RobustnessPerturbationKind.OPTION_LABEL,
        }
    ]
    sensitivity = [
        item
        for item in candidate_aggregates
        if item.perturbation_kind
        in {
            RobustnessPerturbationKind.PROMPT_PARAPHRASE,
            RobustnessPerturbationKind.STOCHASTIC_REPEAT,
        }
    ]
    jsd_values = [
        item.mean_jensen_shannon_divergence
        for item in sensitivity
        if item.mean_jensen_shannon_divergence is not None
    ]
    qualification_cost = sum(
        usages_by_id[call_id].billed_cost_microusd for call_id in call_ids
    )
    reasons: list[str] = []
    normalized_counts = {role: role_counts[role] for role in LLMRole}
    if any(count == 0 for count in normalized_counts.values()):
        reasons.append("required_role_missing")
    if provider_failure_count:
        reasons.append("provider_call_failure")
    if invalid_output_count:
        reasons.append("invalid_structured_output")
    if role_contract_failures:
        reasons.append("role_contract_failure")
    if tool_call_failures:
        reasons.append("interviewer_tool_call_failure")
    if tool_replay_failures:
        reasons.append("interviewer_tool_replay_failure")
    if interviewer_tool_calls == 0:
        reasons.append("interviewer_tool_not_exercised")
    strict_invalid = sum(item.invalid_output_count for item in strict)
    strict_flips = sum(item.top_choice_flip_count for item in strict)
    robustness_invalid = sum(
        item.invalid_output_count for item in candidate_aggregates
    )
    if robustness_invalid:
        reasons.append("robustness_invalid_output")
    if strict_flips:
        reasons.append("strict_transform_top_choice_flip")
    if (
        cost_projection.projected_cost_microusd
        > profile.budget_policy.segment_caps_microusd[
            BudgetSegment.HELD_OUT_STUDY
        ]
    ):
        reasons.append("projected_study_cost_over_cap")
    return CandidateQualificationResult(
        model_candidate_id=candidate.candidate_id,
        model_candidate_artifact_version=candidate.artifact_version,
        model_candidate_sha256=content_sha256(candidate),
        price_card_sha256=content_sha256(price_card),
        call_ids=call_ids,
        call_assessment_sha256s=[
            content_sha256(assessments_by_id[call_id]) for call_id in call_ids
        ],
        robustness_aggregate_sha256s=[
            content_sha256(item) for item in candidate_aggregates
        ],
        role_call_counts=normalized_counts,
        provider_call_count=len(call_ids),
        provider_call_failure_count=provider_failure_count,
        invalid_output_count=invalid_output_count,
        role_contract_failure_count=role_contract_failures,
        interviewer_tool_call_failure_count=tool_call_failures,
        interviewer_tool_replay_failure_count=tool_replay_failures,
        interviewer_tool_call_count=interviewer_tool_calls,
        robustness_invalid_output_count=robustness_invalid,
        strict_transform_invalid_output_count=strict_invalid,
        strict_transform_top_choice_flip_count=strict_flips,
        prompt_and_stochastic_mean_jsd=(
            fmean(jsd_values)
            if len(jsd_values) == len(sensitivity)
            else None
        ),
        development_metrics=development_metrics,
        cost_projection=cost_projection,
        qualification_cost_microusd=qualification_cost,
        p95_latency_ms=_p95(
            [finalizations_by_id[call_id].latency_ms for call_id in call_ids]
        ),
        hard_failure_reasons=reasons,
        passed_hard_gates=not reasons,
    )


def build_phase4_qualification_bundle(
    profile: Phase4ERobustnessProfile,
    *,
    qualification_id: str,
    qualification_version: int,
    created_at: datetime,
    public_development_fixture_id: str,
    public_development_fixture_version: int,
    public_development_fixture_sha256: str,
    candidates: list[OpenWeightModelCandidate],
    price_cards: list[ProviderPriceCard],
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
    results: list[CandidateQualificationResult],
    call_assessments: list[ProviderCallAssessment],
    robustness_aggregates: list[RobustnessAggregate],
) -> Phase4QualificationBundle:
    """Select the banded-priority winner after every hard gate passes."""

    candidates = sorted(candidates, key=lambda item: item.candidate_id)
    price_by_candidate = {item.model_candidate_id: item for item in price_cards}
    result_by_candidate = {item.model_candidate_id: item for item in results}
    if len(price_by_candidate) != len(price_cards) or len(result_by_candidate) != len(
        results
    ):
        raise ValueError("qualification price cards and results must be unique")
    price_cards = [price_by_candidate[item.candidate_id] for item in candidates]
    results = [result_by_candidate[item.candidate_id] for item in candidates]
    eligible = [item for item in results if item.passed_hard_gates]
    selected = (
        _select_qualified_candidate(
            eligible,
            PHASE4_QUALIFICATION_SELECTION_POLICY,
        )
        if eligible
        else None
    )
    return Phase4QualificationBundle(
        qualification_id=qualification_id,
        qualification_version=qualification_version,
        created_at=created_at,
        robustness_profile_id=profile.profile_id,
        robustness_profile_version=profile.profile_version,
        robustness_profile_sha256=content_sha256(profile),
        public_development_fixture_id=public_development_fixture_id,
        public_development_fixture_version=public_development_fixture_version,
        public_development_fixture_sha256=public_development_fixture_sha256,
        candidates=candidates,
        price_cards=price_cards,
        provider_usage_ledger_sha256=content_sha256(ledger),
        provider_execution_journal_sha256=content_sha256(journal),
        call_assessments=call_assessments,
        robustness_aggregates=robustness_aggregates,
        results=results,
        selection_criteria_in_priority_order=(
            profile.qualification_policy.selection_criteria_in_priority_order
        ),
        selection_policy=PHASE4_QUALIFICATION_SELECTION_POLICY,
        status=(
            QualificationStatus.SELECTED
            if selected is not None
            else QualificationStatus.NO_CANDIDATE_QUALIFIED
        ),
        selected_model_candidate_id=(
            selected.model_candidate_id if selected is not None else None
        ),
    )


def validate_phase4_qualification_bundle(
    bundle: Phase4QualificationBundle,
    profile: Phase4ERobustnessProfile,
    ledger: ProviderUsageLedger,
    journal: ProviderExecutionJournal,
) -> None:
    profile_binding = (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    )
    if (
        bundle.robustness_profile_id,
        bundle.robustness_profile_version,
        bundle.robustness_profile_sha256,
    ) != profile_binding:
        raise ValueError("qualification bundle does not bind exact profile")
    if bundle.selection_criteria_in_priority_order != (
        profile.qualification_policy.selection_criteria_in_priority_order
    ):
        raise ValueError("qualification bundle criteria do not match profile")
    if bundle.provider_usage_ledger_sha256 != content_sha256(ledger) or (
        bundle.provider_execution_journal_sha256 != content_sha256(journal)
    ):
        raise ValueError("qualification bundle does not bind provider audit")
    if any(
        item.data_scope is not ProviderDataScope.PUBLIC_DEVELOPMENT
        for item in journal.request_bindings
    ):
        raise ValueError("qualification cannot use participant provider inputs")
    if any(
        item.segment is BudgetSegment.HELD_OUT_STUDY
        for item in ledger.authorizations
    ):
        raise ValueError("qualification cannot spend held-out study budget")
    validate_provider_execution_journal(
        journal,
        ledger,
        profile,
        bundle.candidates,
        bundle.price_cards,
        require_complete=True,
    )
    result_call_ids = [
        call_id for result in bundle.results for call_id in result.call_ids
    ]
    journal_call_ids = [item.call_id for item in journal.request_bindings]
    if len(result_call_ids) != len(set(result_call_ids)) or set(
        result_call_ids
    ) != set(journal_call_ids):
        raise ValueError("qualification results must partition provider calls")
    calls_by_id = {item.call_id: item for item in ledger.calls}
    request_by_id = {item.call_id: item for item in journal.request_bindings}
    finalization_by_id = {
        item.call_id: item for item in journal.finalizations
    }
    for result in bundle.results:
        if any(
            calls_by_id[call_id].model_candidate_id
            != result.model_candidate_id
            for call_id in result.call_ids
        ):
            raise ValueError("qualification result includes another candidate call")
        expected_cost = sum(
            calls_by_id[call_id].billed_cost_microusd
            for call_id in result.call_ids
        )
        if result.qualification_cost_microusd != expected_cost:
            raise ValueError("qualification result cost does not match provider audit")
        expected_provider_failures = sum(
            finalization_by_id[call_id].outcome in PROVIDER_FAILURE_OUTCOMES
            for call_id in result.call_ids
        )
        expected_invalid_outputs = sum(
            finalization_by_id[call_id].outcome
            is ProviderCallOutcome.INVALID_OUTPUT
            for call_id in result.call_ids
        )
        interviewer_ids = [
            call_id
            for call_id in result.call_ids
            if request_by_id[call_id].role is LLMRole.INTERVIEWER
        ]
        expected_tool_calls = sum(
            finalization_by_id[call_id].tool_call_count
            for call_id in interviewer_ids
        )
        expected_tool_call_failures = sum(
            finalization_by_id[call_id].tool_call_failure_count
            for call_id in interviewer_ids
        )
        expected_role_counts = Counter(
            request_by_id[call_id].role for call_id in result.call_ids
        )
        if (
            result.provider_call_failure_count != expected_provider_failures
            or result.invalid_output_count != expected_invalid_outputs
            or result.interviewer_tool_call_count != expected_tool_calls
            or result.interviewer_tool_call_failure_count
            != expected_tool_call_failures
            or result.role_call_counts
            != {role: expected_role_counts[role] for role in LLMRole}
        ):
            raise ValueError("qualification result provider counts do not match")
    candidate_by_id = {item.candidate_id: item for item in bundle.candidates}
    price_by_candidate = {
        item.model_candidate_id: item for item in bundle.price_cards
    }
    for result in bundle.results:
        candidate = candidate_by_id[result.model_candidate_id]
        result_call_ids = set(result.call_ids)
        rebuilt = build_candidate_qualification_result(
            profile,
            candidate,
            price_by_candidate[result.model_candidate_id],
            ledger,
            journal,
            [
                item
                for item in bundle.call_assessments
                if item.call_id in result_call_ids
            ],
            bundle.robustness_aggregates,
            result.development_metrics,
            result.cost_projection,
        )
        if rebuilt != result:
            raise ValueError("qualification result does not rebuild from sources")


def phase4_qualification_summary(
    bundle: Phase4QualificationBundle,
) -> dict[str, object]:
    return {
        "schema_version": bundle.schema_version,
        "qualification_id": bundle.qualification_id,
        "qualification_version": bundle.qualification_version,
        "qualification_sha256": content_sha256(bundle),
        "candidate_count": len(bundle.candidates),
        "qualified_candidate_count": sum(
            item.passed_hard_gates for item in bundle.results
        ),
        "status": bundle.status.value,
        "selected_model_candidate_id": bundle.selected_model_candidate_id,
        "provider_call_count": sum(
            item.provider_call_count for item in bundle.results
        ),
        "qualification_cost_microusd": sum(
            item.qualification_cost_microusd for item in bundle.results
        ),
        "held_out_study_spend_microusd": bundle.held_out_study_spend_microusd,
        "participant_content_omitted": True,
    }


def load_phase4_qualification_bundle(
    path: str | Path,
) -> Phase4QualificationBundle:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return Phase4QualificationBundle.model_validate(payload)
