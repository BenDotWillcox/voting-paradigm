"""Executable authored-map readouts for the two Phase 4 classical baselines.

Gaussian linear and Bradley-Terry differ only in how confirmed evidence moves
their posterior.  Both then use the same reviewed option stance map, posterior-
predictive pairwise coupling, settledness calculation, and deterministic rich-
ballot action policy. Keeping that vote layer common makes the model-family
comparison interpretable.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, TypeAlias

import numpy as np
from pydantic import Field
from scipy.stats import norm

from preferences.model.bradley_terry import BradleyTerryLaplaceModel
from preferences.model.common import flat_to_sigma
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.types import PreferenceState

from .contracts import (
    BallotType,
    ContractModel,
    EvaluationFixture,
    MeasurePresentation,
    MeasureVersion,
    PositiveVersion,
    RankingTier,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_evidence import (
    FixedOntologyEvidenceLedger,
    materialize_evidence,
    replay_preference_state,
)
from .phase4_interviewer import preference_state_sha256
from .phase4_ontology import evidence_ledger_identity_sha256
from .phase4_prediction import (
    ApprovalPrediction,
    BallotPrediction,
    ComponentArtifactReference,
    Phase4ModelConfiguration,
    PredictionCheckpoint,
    PredictionInputBinding,
    PredictionSnapshotV2,
    QuadraticPrediction,
    RankedPrediction,
    ScorePrediction,
    SingleChoicePrediction,
    TOP_OPTION_ABS_TOLERANCE,
    materialized_evidence_sha256,
    prediction_model_input_sha256,
    validate_prediction_v2_for_measure,
)
from .phase4_protocol import EvidenceCondition, Phase4Protocol
from .phase4_semantic import (
    AuthoredMeasureSemanticMapping,
    AuthoredSemanticMapBundle,
    semantic_map_artifact_reference,
    semantic_mapping_for_measure,
    validate_authored_semantic_map,
)

PositiveFiniteFloat = Annotated[
    float,
    Field(gt=0.0, allow_inf_nan=False),
]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]


class ClassicalModelFamily(str, Enum):
    GAUSSIAN_LINEAR = "gaussian_linear"
    BRADLEY_TERRY = "bradley_terry"


class GaussianLinearModelArtifact(ContractModel):
    record_version: Literal["phase4_gaussian_model_artifact.v1"] = (
        "phase4_gaussian_model_artifact.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    family: Literal[ClassicalModelFamily.GAUSSIAN_LINEAR] = (
        ClassicalModelFamily.GAUSSIAN_LINEAR
    )
    model_version: Literal["gaussian_linear_v1"] = "gaussian_linear_v1"
    prior_variance: PositiveFiniteFloat = 1.0
    base_noise_variance: PositiveFiniteFloat = 0.25
    min_strength_weight: Annotated[
        float,
        Field(gt=0.0, le=1.0, allow_inf_nan=False),
    ] = 0.05

    def instantiate(self) -> GaussianLinearUtilityModel:
        return GaussianLinearUtilityModel(
            prior_variance=self.prior_variance,
            base_noise_variance=self.base_noise_variance,
            min_strength_weight=self.min_strength_weight,
        )


class BradleyTerryModelArtifact(ContractModel):
    record_version: Literal["phase4_bradley_terry_model_artifact.v1"] = (
        "phase4_bradley_terry_model_artifact.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    family: Literal[ClassicalModelFamily.BRADLEY_TERRY] = (
        ClassicalModelFamily.BRADLEY_TERRY
    )
    model_version: Literal["bradley_terry_laplace_v1"] = (
        "bradley_terry_laplace_v1"
    )
    prior_variance: PositiveFiniteFloat = 1.0
    min_strength_weight: Annotated[
        float,
        Field(gt=0.0, le=1.0, allow_inf_nan=False),
    ] = 0.05
    max_newton_iters: Annotated[int, Field(gt=0)] = 50
    newton_tol: PositiveFiniteFloat = 1e-8

    def instantiate(self) -> BradleyTerryLaplaceModel:
        return BradleyTerryLaplaceModel(
            prior_variance=self.prior_variance,
            min_strength_weight=self.min_strength_weight,
            max_newton_iters=self.max_newton_iters,
            newton_tol=self.newton_tol,
        )


ClassicalModelArtifact: TypeAlias = (
    GaussianLinearModelArtifact | BradleyTerryModelArtifact
)


class Phase4BallotActionPolicy(ContractModel):
    """Common probability-to-ballot conversion reused by every model arm."""

    record_version: Literal["phase4_ballot_action_policy.v1"] = (
        "phase4_ballot_action_policy.v1"
    )
    approval_rule: Literal["at_or_above_uniform_probability"] = (
        "at_or_above_uniform_probability"
    )
    score_rule: Literal["uniform_centered_piecewise_linear_0_10"] = (
        "uniform_centered_piecewise_linear_0_10"
    )
    quadratic_rule: Literal["probability_proportional_integer_scaling"] = (
        "probability_proportional_integer_scaling"
    )
    comparison_tolerance: Annotated[
        float,
        Field(
            ge=TOP_OPTION_ABS_TOLERANCE,
            le=1e-6,
            allow_inf_nan=False,
        ),
    ] = 1e-12


class ClassicalReadoutPolicy(ContractModel):
    """Versioned classical readout; final values freeze in Phase 4E."""

    record_version: Literal["phase4_classical_readout_policy.v1"] = (
        "phase4_classical_readout_policy.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    probability_rule: Literal["pairwise_logistic_normal_coupling"] = (
        "pairwise_logistic_normal_coupling"
    )
    stance_scale_rule: Literal["maximum_pairwise_l2_distance"] = (
        "maximum_pairwise_l2_distance"
    )
    probability_temperature: PositiveFiniteFloat = 1.0
    settledness_rule: Literal["minimum_pairwise_margin_probability"] = (
        "minimum_pairwise_margin_probability"
    )
    settled_utility_margin: NonNegativeFiniteFloat = 0.0
    action_policy: Phase4BallotActionPolicy = Field(
        default_factory=Phase4BallotActionPolicy
    )


def _artifact_reference(
    artifact: ClassicalModelArtifact | ClassicalReadoutPolicy,
) -> ComponentArtifactReference:
    return ComponentArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_version=str(artifact.artifact_version),
        artifact_sha256=content_sha256(artifact),
    )


def classical_model_artifact_reference(
    artifact: ClassicalModelArtifact,
) -> ComponentArtifactReference:
    return _artifact_reference(artifact)


def classical_readout_artifact_reference(
    policy: ClassicalReadoutPolicy,
) -> ComponentArtifactReference:
    return _artifact_reference(policy)


def _expected_arm_id(artifact: ClassicalModelArtifact) -> str:
    if artifact.family is ClassicalModelFamily.GAUSSIAN_LINEAR:
        return "gaussian_linear_fixed"
    return "bradley_terry_fixed"


def validate_classical_configuration(
    configuration: Phase4ModelConfiguration,
    model_artifact: ClassicalModelArtifact,
    semantic_map: AuthoredSemanticMapBundle,
    readout_policy: ClassicalReadoutPolicy,
    protocol: Phase4Protocol,
) -> None:
    """Fail closed unless configuration references the exact supplied code/data."""

    arm_ids = {arm.arm_id for arm in protocol.comparison.model_arms}
    expected_arm_id = _expected_arm_id(model_artifact)
    if expected_arm_id not in arm_ids:
        raise ValueError("classical model arm is absent from the Phase 4 protocol")
    if configuration.arm_id != expected_arm_id:
        raise ValueError("classical model artifact does not match configured arm")
    if configuration.evidence_condition is not EvidenceCondition.STRUCTURED_ONLY:
        raise ValueError("classical baseline requires structured-only evidence")
    if configuration.preference_model != classical_model_artifact_reference(
        model_artifact
    ):
        raise ValueError("configuration does not bind the exact model artifact")
    if configuration.semantic_mapper != semantic_map_artifact_reference(
        semantic_map
    ):
        raise ValueError("configuration does not bind the exact semantic map")
    if configuration.prediction_readout != classical_readout_artifact_reference(
        readout_policy
    ):
        raise ValueError("configuration does not bind the exact readout policy")
    if configuration.provider_model is not None or configuration.prompt is not None:
        raise ValueError("classical baseline cannot bind an LLM provider or prompt")


def _normalized_stance_matrix(
    mapping: AuthoredMeasureSemanticMapping,
    dimension_ids: list[str],
) -> np.ndarray:
    matrix = np.asarray(
        [
            [
                stance.dimension_weights.get(dimension_id, 0.0)
                for dimension_id in dimension_ids
            ]
            for stance in mapping.option_stances
        ],
        dtype=float,
    )
    scale = max(
        float(np.linalg.norm(matrix[left] - matrix[right]))
        for left in range(len(matrix))
        for right in range(left + 1, len(matrix))
    )
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("authored mapping has no finite option contrast")
    return matrix / scale


def _validate_preference_state(
    state: PreferenceState,
    expected_item_ids: list[str],
    expected_model_version: str,
) -> None:
    if state.item_ids != expected_item_ids:
        raise ValueError("preference state does not match the mapped ontology")
    if state.model_version != expected_model_version:
        raise ValueError("preference state model version does not match artifact")
    item_count = len(expected_item_ids)
    if len(state.mu) != item_count:
        raise ValueError("preference state mean has the wrong dimension")
    if len(state.sigma_flat) != item_count * (item_count + 1) // 2:
        raise ValueError("preference state covariance has the wrong dimension")
    if not all(math.isfinite(value) for value in state.mu + state.sigma_flat):
        raise ValueError("preference state contains a non-finite value")


def _readout_values(
    state: PreferenceState,
    mapping: AuthoredMeasureSemanticMapping,
    policy: ClassicalReadoutPolicy,
) -> tuple[dict[str, float], str, float]:
    dimension_ids = list(state.item_ids)
    stance_matrix = _normalized_stance_matrix(mapping, dimension_ids)
    posterior_mean = np.asarray(state.mu, dtype=float)
    posterior_covariance = flat_to_sigma(state.sigma_flat, len(dimension_ids))
    option_means = stance_matrix @ posterior_mean
    option_covariance = stance_matrix @ posterior_covariance @ stance_matrix.T

    option_count = len(mapping.option_stances)
    coupled_logits = np.zeros(option_count, dtype=float)
    for left in range(option_count):
        for right in range(option_count):
            if left == right:
                continue
            mean_difference = float(option_means[left] - option_means[right])
            variance_difference = float(
                option_covariance[left, left]
                + option_covariance[right, right]
                - 2.0 * option_covariance[left, right]
            )
            logistic_normal_scale = math.sqrt(
                policy.probability_temperature**2
                + math.pi * max(variance_difference, 0.0) / 8.0
            )
            coupled_logits[left] += mean_difference / logistic_normal_scale
    coupled_logits /= option_count
    coupled_logits -= float(np.max(coupled_logits))
    exponentials = np.exp(coupled_logits)
    probability_values = exponentials / float(np.sum(exponentials))
    option_ids = [item.option_id for item in mapping.option_stances]
    probabilities = {
        option_id: float(probability_values[index])
        for index, option_id in enumerate(option_ids)
    }
    top_probability = float(np.max(probability_values))
    top_index = next(
        index
        for index in range(len(option_ids))
        if math.isclose(
            float(probability_values[index]),
            top_probability,
            rel_tol=0.0,
            abs_tol=TOP_OPTION_ABS_TOLERANCE,
        )
    )
    top_option_id = option_ids[top_index]

    pairwise_settled: list[float] = []
    for other_index in range(len(option_ids)):
        if other_index == top_index:
            continue
        mean_difference = float(option_means[top_index] - option_means[other_index])
        variance_difference = float(
            option_covariance[top_index, top_index]
            + option_covariance[other_index, other_index]
            - 2.0 * option_covariance[top_index, other_index]
        )
        standard_deviation = math.sqrt(max(variance_difference, 0.0))
        adjusted_difference = mean_difference - policy.settled_utility_margin
        if standard_deviation == 0.0:
            if adjusted_difference > 0.0:
                settled = 1.0
            elif adjusted_difference < 0.0:
                settled = 0.0
            else:
                settled = 0.5
        else:
            settled = float(norm.cdf(adjusted_difference / standard_deviation))
        pairwise_settled.append(settled)
    return probabilities, top_option_id, min(pairwise_settled)


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def _score_from_probability(probability: float, uniform: float) -> int:
    if probability >= uniform:
        scaled = 5.0 + 5.0 * (probability - uniform) / (1.0 - uniform)
    else:
        scaled = 5.0 * probability / uniform
    return min(10, max(0, _round_half_up(scaled)))


def _signed_round(value: float) -> int:
    return _round_half_up(value) if value >= 0.0 else -_round_half_up(-value)


def _quadratic_allocations(
    measure: MeasureVersion,
    probabilities: dict[str, float],
    top_option_id: str,
) -> dict[str, int]:
    budget = measure.quadratic_credit_budget
    if budget is None:
        raise ValueError("quadratic measure is missing its credit budget")
    option_ids = [option.option_id for option in measure.options]
    if measure.quadratic_allow_negative:
        uniform = 1.0 / len(option_ids)
        raw_targets = {
            option_id: probabilities[option_id] - uniform
            for option_id in option_ids
        }
        denominator = max(abs(value) for value in raw_targets.values())
    else:
        raw_targets = dict(probabilities)
        denominator = max(raw_targets.values())
    normalized = {
        option_id: (
            raw_targets[option_id] / denominator if denominator > 0.0 else 0.0
        )
        for option_id in option_ids
    }

    best = {option_id: 0 for option_id in option_ids}
    for scale in range(1, math.isqrt(budget) + 1):
        candidate = {
            option_id: _signed_round(scale * normalized[option_id])
            for option_id in option_ids
        }
        cost = sum(value * value for value in candidate.values())
        if cost <= budget:
            best = candidate
    if not any(best.values()):
        best[top_option_id] = 1
    return best


def ballot_prediction_from_probabilities(
    measure: MeasureVersion,
    probabilities: dict[str, float],
    policy: Phase4BallotActionPolicy,
) -> BallotPrediction:
    """Convert one distribution to the common deterministic civic action."""

    option_ids = [option.option_id for option in measure.options]
    if set(probabilities) != set(option_ids):
        raise ValueError("action probabilities must cover every option exactly")
    if any(
        not math.isfinite(value) or value < 0.0
        for value in probabilities.values()
    ) or not math.isclose(
        sum(probabilities.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("action probabilities must be a normalized distribution")
    top_probability = max(probabilities.values())
    top_option_id = next(
        option_id
        for option_id in option_ids
        if math.isclose(
            probabilities[option_id],
            top_probability,
            rel_tol=0.0,
            abs_tol=TOP_OPTION_ABS_TOLERANCE,
        )
    )

    if measure.ballot_type is BallotType.SINGLE_CHOICE:
        return SingleChoicePrediction(selected_option_id=top_option_id)
    if measure.ballot_type is BallotType.RANKED:
        ordered = sorted(
            option_ids,
            key=lambda option_id: (
                -probabilities[option_id],
                option_ids.index(option_id),
            ),
        )
        tiers: list[RankingTier] = []
        for option_id in ordered:
            if tiers and math.isclose(
                probabilities[option_id],
                probabilities[tiers[-1].option_ids[0]],
                rel_tol=0.0,
                abs_tol=policy.comparison_tolerance,
            ):
                tiers[-1].option_ids.append(option_id)
            else:
                tiers.append(RankingTier(option_ids=[option_id]))
        return RankedPrediction(ranking_tiers=tiers)
    if measure.ballot_type is BallotType.APPROVAL:
        uniform = 1.0 / len(option_ids)
        return ApprovalPrediction(
            approved_option_ids=[
                option_id
                for option_id in option_ids
                if probabilities[option_id]
                >= uniform - policy.comparison_tolerance
            ]
        )
    if measure.ballot_type is BallotType.SCORE:
        uniform = 1.0 / len(option_ids)
        return ScorePrediction(
            option_scores={
                option_id: _score_from_probability(
                    probabilities[option_id],
                    uniform,
                )
                for option_id in option_ids
            }
        )
    return QuadraticPrediction(
        quadratic_allocations=_quadratic_allocations(
            measure,
            probabilities,
            top_option_id,
        )
    )


def build_classical_prediction_snapshot(
    *,
    snapshot_id: str,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: Phase4ModelConfiguration,
    model_artifact: ClassicalModelArtifact,
    semantic_map: AuthoredSemanticMapBundle,
    readout_policy: ClassicalReadoutPolicy,
    evidence_cutoff_sequence: int,
    checkpoint: PredictionCheckpoint,
    wave_index: int | None,
    created_at: datetime,
) -> PredictionSnapshotV2:
    """Replay one classical posterior and emit its exact v2 snapshot."""

    validate_authored_semantic_map(
        semantic_map,
        fixture,
        evidence_ledger.ontology,
    )
    validate_classical_configuration(
        configuration,
        model_artifact,
        semantic_map,
        readout_policy,
        protocol,
    )
    fixture_measure = next(
        (
            item
            for item in fixture.measures
            if (item.measure_id, item.version)
            == (measure.measure_id, measure.version)
        ),
        None,
    )
    if fixture_measure != measure:
        raise ValueError("classical target is not the exact fixture measure")
    if (
        presentation.session_id != evidence_ledger.session_id
        or presentation.measure_id != measure.measure_id
        or presentation.measure_version != measure.version
        or presentation.packet_version != measure.packet.version
    ):
        raise ValueError("classical target presentation does not match")
    if created_at < presentation.presented_at:
        raise ValueError("classical prediction cannot predate target presentation")

    mapping = semantic_mapping_for_measure(
        semantic_map,
        measure.measure_id,
        measure.version,
    )
    model = model_artifact.instantiate()
    state = replay_preference_state(
        model=model,
        ledger=evidence_ledger,
        condition=EvidenceCondition.STRUCTURED_ONLY,
        cutoff_sequence=evidence_cutoff_sequence,
        user_id=evidence_ledger.session_id,
    )
    _validate_preference_state(
        state,
        evidence_ledger.ontology.item_ids,
        model_artifact.model_version,
    )
    eligible_evidence = materialize_evidence(
        evidence_ledger,
        condition=EvidenceCondition.STRUCTURED_ONLY,
        cutoff_sequence=evidence_cutoff_sequence,
    )
    event_ids = [item.event_id for item in eligible_evidence]
    if any(event_id is None for event_id in event_ids):
        raise ValueError("classical evidence is missing a durable event id")

    probabilities, top_option_id, settled_probability = _readout_values(
        state,
        mapping,
        readout_policy,
    )
    binding = PredictionInputBinding(
        target_presentation_id=presentation.presentation_id,
        target_measure_id=measure.measure_id,
        target_measure_version=measure.version,
        target_packet_version=measure.packet.version,
        target_packet_sha256=content_sha256(measure.packet),
        evidence_ledger_id=evidence_ledger.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            evidence_ledger
        ),
        evidence_condition=EvidenceCondition.STRUCTURED_ONLY,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        eligible_evidence_event_ids=[
            event_id for event_id in event_ids if event_id is not None
        ],
        eligible_evidence_sha256=materialized_evidence_sha256(
            eligible_evidence
        ),
        conversation_message_ids=[],
        conversation_messages_sha256=content_sha256([]),
        preference_state_sha256=preference_state_sha256(state),
        ontology_snapshot_sha256=content_sha256(evidence_ledger.ontology),
        active_ontology_sha256=content_sha256(
            sorted(evidence_ledger.ontology.item_ids)
        ),
        model_input_sha256="0" * 64,
    )
    binding = binding.model_copy(
        update={
            "model_input_sha256": prediction_model_input_sha256(
                binding,
                configuration,
            )
        }
    )
    snapshot = PredictionSnapshotV2(
        snapshot_id=snapshot_id,
        session_id=evidence_ledger.session_id,
        model_configuration_id=configuration.configuration_id,
        model_configuration_sha256=content_sha256(configuration),
        checkpoint=checkpoint,
        wave_index=wave_index,
        input_binding=binding,
        option_probabilities=probabilities,
        top_option_id=top_option_id,
        confidence=probabilities[top_option_id],
        settled_probability=settled_probability,
        ballot_prediction=ballot_prediction_from_probabilities(
            measure,
            probabilities,
            readout_policy.action_policy,
        ),
        created_at=created_at,
    )
    validate_prediction_v2_for_measure(snapshot, measure)
    return snapshot


def validate_classical_prediction_snapshot(
    snapshot: PredictionSnapshotV2,
    *,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: Phase4ModelConfiguration,
    model_artifact: ClassicalModelArtifact,
    semantic_map: AuthoredSemanticMapBundle,
    readout_policy: ClassicalReadoutPolicy,
) -> None:
    """Rebuild a snapshot so caller-asserted state cannot pass.

    Equality is intentionally exact: persisted float and hash reproducibility
    therefore depends on the frozen Python, NumPy, SciPy, and BLAS environment
    recorded for the evaluation run.
    """

    expected = build_classical_prediction_snapshot(
        snapshot_id=snapshot.snapshot_id,
        fixture=fixture,
        protocol=protocol,
        measure=measure,
        presentation=presentation,
        evidence_ledger=evidence_ledger,
        configuration=configuration,
        model_artifact=model_artifact,
        semantic_map=semantic_map,
        readout_policy=readout_policy,
        evidence_cutoff_sequence=(
            snapshot.input_binding.evidence_cutoff_sequence
        ),
        checkpoint=snapshot.checkpoint,
        wave_index=snapshot.wave_index,
        created_at=snapshot.created_at,
    )
    if snapshot != expected:
        raise ValueError(
            "classical snapshot does not match the reproducible model readout"
        )
