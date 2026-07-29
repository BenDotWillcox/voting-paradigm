"""Primary metrics for prequential human-measure predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from .contracts import (
    ContractModel,
    DelegationAction,
    MeasurePresentation,
    ParticipantResponse,
    PredictionSnapshot,
    PresentationKind,
    Probability,
    ResponseStability,
    ResponseState,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .prequential import (
    DEFAULT_DELEGATION_THRESHOLDS,
    PrequentialReplay,
    SnapshotCheckpoint,
)

DEFAULT_LOG_LOSS_EPSILON = 1e-15


class ChoiceMetricSummary(ContractModel):
    count: int = Field(ge=0)
    mean_log_loss: float | None = Field(default=None, ge=0.0)
    top_choice_accuracy: Probability | None = Field(
        default=None,
        description=(
            "Mean top-choice credit, split equally across exact probability "
            "ties so null baselines are invariant to option display order."
        ),
    )
    mean_brier_score: float | None = Field(default=None, ge=0.0)


class SettlednessMetricSummary(ContractModel):
    count: int = Field(ge=0)
    mean_brier_score: Probability | None = None


class RiskCoveragePoint(ContractModel):
    threshold: Probability
    eligible_choice_count: int = Field(ge=0)
    nonchoice_count: int = Field(ge=0)
    automatic_choice_vote_count: int = Field(ge=0)
    coverage: Probability
    wrong_vote_count: int = Field(ge=0)
    risk: Probability | None = None
    unsupported_vote_count: int = Field(ge=0)
    unsupported_vote_rate: Probability | None = None


class CheckpointMetricSlice(ContractModel):
    checkpoint: SnapshotCheckpoint
    wave_index: int | None = Field(default=None, ge=0)
    prediction_count: int = Field(gt=0)
    evidence_event_count_min: int = Field(ge=0)
    evidence_event_count_max: int = Field(ge=0)
    choice: ChoiceMetricSummary
    settledness: SettlednessMetricSummary

    @model_validator(mode="after")
    def evidence_range_is_ordered(self) -> "CheckpointMetricSlice":
        if self.evidence_event_count_min > self.evidence_event_count_max:
            raise ValueError(
                "minimum evidence-event count cannot exceed maximum"
            )
        return self


class ModelEvaluationMetrics(ContractModel):
    configuration_id: StableId
    choice: ChoiceMetricSummary
    stable_choice: ChoiceMetricSummary
    tentative_choice: ChoiceMetricSummary
    settledness: SettlednessMetricSummary
    candidate_thresholds: list[RiskCoveragePoint]
    risk_coverage_curve: list[RiskCoveragePoint]
    wrong_vote_confidences: list[Probability]
    checkpoint_slices: list[CheckpointMetricSlice]


class HumanMeasureMetrics(ContractModel):
    schema_version: Literal["human_measure_metrics.v1"] = (
        "human_measure_metrics.v1"
    )
    run_sha256: Sha256Digest
    log_loss_epsilon: float = Field(gt=0.0, lt=1.0)
    models: list[ModelEvaluationMetrics]


@dataclass(frozen=True)
class _PredictionOutcome:
    presentation: MeasurePresentation
    response: ParticipantResponse
    snapshot: PredictionSnapshot


def _choice_summary(
    outcomes: list[_PredictionOutcome],
    *,
    epsilon: float,
) -> ChoiceMetricSummary:
    choices = [
        outcome
        for outcome in outcomes
        if outcome.response.response_state is ResponseState.CHOICE
    ]
    if not choices:
        return ChoiceMetricSummary(count=0)

    log_losses: list[float] = []
    brier_scores: list[float] = []
    top_choice_credit = 0.0
    for outcome in choices:
        selected_option_id = outcome.response.selected_option_id
        if selected_option_id is None:
            raise ValueError(
                f"choice response {outcome.response.response_id} has no option"
            )
        selected_probability = outcome.snapshot.option_probabilities[
            selected_option_id
        ]
        log_losses.append(-math.log(max(selected_probability, epsilon)))
        brier_scores.append(
            sum(
                (
                    probability
                    - (1.0 if option_id == selected_option_id else 0.0)
                )
                ** 2
                for option_id, probability in (
                    outcome.snapshot.option_probabilities.items()
                )
            )
        )
        top_probability = max(
            outcome.snapshot.option_probabilities.values()
        )
        tied_top_options = [
            option_id
            for option_id, probability in (
                outcome.snapshot.option_probabilities.items()
            )
            if math.isclose(
                probability,
                top_probability,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ]
        if selected_option_id in tied_top_options:
            top_choice_credit += 1.0 / len(tied_top_options)
    return ChoiceMetricSummary(
        count=len(choices),
        mean_log_loss=sum(log_losses) / len(log_losses),
        top_choice_accuracy=top_choice_credit / len(choices),
        mean_brier_score=sum(brier_scores) / len(brier_scores),
    )


def _settledness_summary(
    outcomes: list[_PredictionOutcome],
) -> SettlednessMetricSummary:
    if not outcomes:
        return SettlednessMetricSummary(count=0)
    errors = []
    for outcome in outcomes:
        # A deliberate, stable abstention is a settled civic preference. UNSURE
        # instead means the participant has not reached a settled position.
        is_settled = (
            outcome.response.stability is ResponseStability.STABLE
            and outcome.response.response_state is not ResponseState.UNSURE
        )
        target = 1.0 if is_settled else 0.0
        errors.append((outcome.snapshot.settled_probability - target) ** 2)
    return SettlednessMetricSummary(
        count=len(outcomes),
        mean_brier_score=sum(errors) / len(errors),
    )


def _stored_action(
    snapshot: PredictionSnapshot,
    threshold: float,
) -> DelegationAction:
    for decision in snapshot.delegation_decisions:
        if math.isclose(
            decision.threshold,
            threshold,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            return decision.action
    raise ValueError(
        f"snapshot {snapshot.snapshot_id} has no decision at threshold "
        f"{threshold}"
    )


def _risk_coverage_point(
    outcomes: list[_PredictionOutcome],
    *,
    threshold: float,
    require_stored_decision: bool,
) -> RiskCoveragePoint:
    choices = [
        outcome
        for outcome in outcomes
        if outcome.response.response_state is ResponseState.CHOICE
    ]
    nonchoices = [
        outcome
        for outcome in outcomes
        if outcome.response.response_state is not ResponseState.CHOICE
    ]

    def votes(outcome: _PredictionOutcome) -> bool:
        if require_stored_decision:
            return (
                _stored_action(outcome.snapshot, threshold)
                is DelegationAction.VOTE
            )
        return outcome.snapshot.confidence >= threshold

    covered_choices = [outcome for outcome in choices if votes(outcome)]
    wrong_votes = [
        outcome
        for outcome in covered_choices
        if outcome.snapshot.top_option_id
        != outcome.response.selected_option_id
    ]
    unsupported_votes = [
        outcome for outcome in nonchoices if votes(outcome)
    ]
    return RiskCoveragePoint(
        threshold=threshold,
        eligible_choice_count=len(choices),
        nonchoice_count=len(nonchoices),
        automatic_choice_vote_count=len(covered_choices),
        coverage=(
            len(covered_choices) / len(choices) if choices else 0.0
        ),
        wrong_vote_count=len(wrong_votes),
        risk=(
            len(wrong_votes) / len(covered_choices)
            if covered_choices
            else None
        ),
        unsupported_vote_count=len(unsupported_votes),
        unsupported_vote_rate=(
            len(unsupported_votes) / len(nonchoices)
            if nonchoices
            else None
        ),
    )


CheckpointSliceKey = tuple[SnapshotCheckpoint, int | None]


def _checkpoint_sort_key(
    key: CheckpointSliceKey,
) -> tuple[int, int]:
    checkpoint, wave_index = key
    if checkpoint is SnapshotCheckpoint.ZERO_EVIDENCE:
        return (0, -1)
    if checkpoint is SnapshotCheckpoint.POST_ONBOARDING:
        return (1, -1)
    if wave_index is None:
        raise ValueError(f"{checkpoint.value} checkpoint requires a wave index")
    if checkpoint is SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER:
        return (2 + 2 * wave_index, wave_index)
    return (3 + 2 * wave_index, wave_index)


def _checkpoint_outcomes_by_configuration(
    replay: PrequentialReplay,
) -> dict[str, dict[CheckpointSliceKey, list[_PredictionOutcome]]]:
    run = replay.run
    trace_by_snapshot_id = {
        trace.snapshot_id: trace for trace in replay.snapshot_traces
    }
    presentation_by_id = {
        presentation.presentation_id: presentation
        for presentation in run.measure_presentations
        if presentation.kind is PresentationKind.INITIAL
    }
    response_by_presentation_id = {
        response.presentation_id: response
        for response in run.participant_responses
    }
    outcomes_by_configuration: dict[
        str,
        dict[CheckpointSliceKey, list[_PredictionOutcome]],
    ] = {
        configuration.configuration_id: {}
        for configuration in run.model_configurations
    }
    seen_snapshots: set[
        tuple[str, str, SnapshotCheckpoint, int | None]
    ] = set()

    for snapshot in run.prediction_snapshots:
        trace = trace_by_snapshot_id[snapshot.snapshot_id]
        presentation = presentation_by_id.get(
            snapshot.target_presentation_id
        )
        response = response_by_presentation_id.get(
            snapshot.target_presentation_id
        )
        if presentation is None or response is None:
            continue
        uniqueness_key = (
            snapshot.model_configuration_id,
            snapshot.target_presentation_id,
            trace.checkpoint,
            trace.wave_index,
        )
        if uniqueness_key in seen_snapshots:
            raise ValueError(
                "duplicate checkpoint snapshot for model and presentation; "
                f"configuration={snapshot.model_configuration_id}, "
                f"presentation={snapshot.target_presentation_id}, "
                f"checkpoint={trace.checkpoint.value}, "
                f"wave={trace.wave_index}"
            )
        seen_snapshots.add(uniqueness_key)
        slice_key = (trace.checkpoint, trace.wave_index)
        outcomes_by_configuration[
            snapshot.model_configuration_id
        ].setdefault(slice_key, []).append(
            _PredictionOutcome(
                presentation=presentation,
                response=response,
                snapshot=snapshot,
            )
        )

    answered_initial_presentations = {
        presentation_id
        for presentation_id in presentation_by_id
        if presentation_id in response_by_presentation_id
    }
    for configuration_id, slices in outcomes_by_configuration.items():
        immediate_presentations = [
            outcome.presentation.presentation_id
            for key, outcomes in slices.items()
            if key[0] is SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER
            for outcome in outcomes
        ]
        if (
            len(immediate_presentations)
            != len(set(immediate_presentations))
            or set(immediate_presentations)
            != answered_initial_presentations
        ):
            missing = sorted(
                answered_initial_presentations - set(immediate_presentations)
            )
            extra = sorted(
                set(immediate_presentations) - answered_initial_presentations
            )
            duplicates = sorted(
                {
                    presentation_id
                    for presentation_id in immediate_presentations
                    if immediate_presentations.count(presentation_id) > 1
                }
            )
            raise ValueError(
                "each answered initial presentation requires exactly one "
                "immediate pre-answer snapshot per model; "
                f"configuration={configuration_id}, missing={missing}, "
                f"extra={extra}, duplicates={duplicates}"
            )
    return outcomes_by_configuration


def _checkpoint_metric_slice(
    *,
    key: CheckpointSliceKey,
    outcomes: list[_PredictionOutcome],
    epsilon: float,
) -> CheckpointMetricSlice:
    evidence_counts = [
        len(outcome.snapshot.evidence_event_ids)
        for outcome in outcomes
    ]
    if not evidence_counts:
        raise ValueError(
            "checkpoint metric slices require at least one prediction"
        )
    checkpoint, wave_index = key
    return CheckpointMetricSlice(
        checkpoint=checkpoint,
        wave_index=wave_index,
        prediction_count=len(outcomes),
        evidence_event_count_min=min(evidence_counts),
        evidence_event_count_max=max(evidence_counts),
        choice=_choice_summary(outcomes, epsilon=epsilon),
        settledness=_settledness_summary(outcomes),
    )


def compute_human_measure_metrics(
    replay: PrequentialReplay,
    *,
    candidate_thresholds: tuple[float, ...] = (
        DEFAULT_DELEGATION_THRESHOLDS
    ),
    log_loss_epsilon: float = DEFAULT_LOG_LOSS_EPSILON,
) -> HumanMeasureMetrics:
    """Score initial CHOICE responses, including tentative choices.

    UNSURE, ABSTAIN, and RETEST responses do not define option labels. Voting
    on an UNSURE or ABSTAIN response is instead counted as unsupported
    delegation.
    """

    if not 0.0 < log_loss_epsilon < 1.0:
        raise ValueError("log_loss_epsilon must fall strictly between 0 and 1")
    if len(candidate_thresholds) != len(set(candidate_thresholds)):
        raise ValueError("candidate thresholds must be unique")
    if any(
        threshold < 0.0 or threshold > 1.0
        for threshold in candidate_thresholds
    ):
        raise ValueError("candidate thresholds must fall between 0 and 1")
    thresholds = tuple(sorted(candidate_thresholds))

    checkpoint_outcomes = _checkpoint_outcomes_by_configuration(replay)
    model_metrics: list[ModelEvaluationMetrics] = []
    for configuration_id in sorted(checkpoint_outcomes):
        checkpoint_groups = checkpoint_outcomes[configuration_id]
        outcomes = [
            outcome
            for key, slice_outcomes in checkpoint_groups.items()
            if key[0] is SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER
            for outcome in slice_outcomes
        ]
        stable_outcomes = [
            outcome
            for outcome in outcomes
            if outcome.response.stability is ResponseStability.STABLE
        ]
        tentative_outcomes = [
            outcome
            for outcome in outcomes
            if outcome.response.stability is ResponseStability.TENTATIVE
        ]
        curve_thresholds = sorted(
            {1.0}.union(
                outcome.snapshot.confidence for outcome in outcomes
            ),
            reverse=True,
        )
        wrong_confidences = sorted(
            [
                outcome.snapshot.confidence
                for outcome in outcomes
                if (
                    outcome.response.response_state is ResponseState.CHOICE
                    and outcome.snapshot.top_option_id
                    != outcome.response.selected_option_id
                )
            ],
            reverse=True,
        )
        model_metrics.append(
            ModelEvaluationMetrics(
                configuration_id=configuration_id,
                choice=_choice_summary(outcomes, epsilon=log_loss_epsilon),
                stable_choice=_choice_summary(
                    stable_outcomes,
                    epsilon=log_loss_epsilon,
                ),
                tentative_choice=_choice_summary(
                    tentative_outcomes,
                    epsilon=log_loss_epsilon,
                ),
                settledness=_settledness_summary(outcomes),
                candidate_thresholds=[
                    _risk_coverage_point(
                        outcomes,
                        threshold=threshold,
                        require_stored_decision=True,
                    )
                    for threshold in thresholds
                ],
                risk_coverage_curve=[
                    _risk_coverage_point(
                        outcomes,
                        threshold=threshold,
                        require_stored_decision=False,
                    )
                    for threshold in curve_thresholds
                ],
                wrong_vote_confidences=wrong_confidences,
                checkpoint_slices=[
                    _checkpoint_metric_slice(
                        key=key,
                        outcomes=checkpoint_groups[key],
                        epsilon=log_loss_epsilon,
                    )
                    for key in sorted(
                        checkpoint_groups,
                        key=_checkpoint_sort_key,
                    )
                ],
            )
        )
    return HumanMeasureMetrics(
        run_sha256=content_sha256(replay.run),
        log_loss_epsilon=log_loss_epsilon,
        models=model_metrics,
    )
