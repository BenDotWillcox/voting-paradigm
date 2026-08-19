"""Versioned Phase 4D prediction and run contracts.

The Phase 1-3 ``PredictionSnapshot`` and ``EvaluationRun`` contracts remain
frozen at v1.  This module adds a separate v2 boundary for the Phase 4 model
comparison: every arm binds the same held-out packet and evidence cutoff,
emits a normalized option distribution, and also emits one complete ballot-
type-specific prediction. Provider calls remain outside the contract in the
separate classical and LLM readout modules.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, field_validator, model_validator
from preferences.types import Evidence

from .bank_profile import ReviewActorType
from .contracts import (
    BallotType,
    ContractModel,
    EvaluationFixture,
    EvaluationRun,
    MeasurePresentation,
    MeasureVersion,
    NonEmptyText,
    ParticipantResponse,
    PositiveVersion,
    PredictionSnapshot,
    PresentationKind,
    Probability,
    RankingTier,
    RetestPacketVariant,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256, validate_run_against_fixture
from .phase4_evidence import (
    FixedOntologyEvidenceLedger,
    conversation_messages_sha256,
    materialize_evidence,
)
from .phase4_interviewer import preference_evidence_sha256
from .phase4_ontology import (
    ExpandingDimensionStatus,
    ExpandingOntologyDimensionState,
    ExpandingOntologyLedger,
    active_dimension_states,
    evidence_ledger_identity_sha256,
    replay_expanding_ontology,
    validate_expanding_ontology_ledger,
)
from .phase4_protocol import (
    EvidenceCondition,
    Phase4Protocol,
    PredictionReadout,
    PreferenceRepresentation,
)

NonNegativeSequence = Annotated[int, Field(ge=0)]
ScoreValue = Annotated[int, Field(ge=0, le=10)]
TOP_OPTION_ABS_TOLERANCE = 1e-12


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _require_unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


def _empty_payload_sha256() -> str:
    return content_sha256([])


def materialized_evidence_sha256(evidence: list[Evidence]) -> str:
    """Hash model-ready dataclass evidence with its canonical v4B encoding."""

    return content_sha256(
        [preference_evidence_sha256(item) for item in evidence]
    )


def _materialized_evidence_time(evidence: Evidence) -> datetime:
    if evidence.timestamp is None:
        raise ValueError("materialized evidence is missing its timestamp")
    return datetime.fromisoformat(evidence.timestamp.replace("Z", "+00:00"))


def active_ontology_input_sha256(
    fixed_item_ids: list[str],
    expanded_dimensions: list[ExpandingOntologyDimensionState] | None = None,
) -> str:
    """Hash only the active ontology surface consumed by a prediction model.

    An expanding arm with no active non-seed dimensions intentionally hashes
    identically to the fixed ontology. Once participant-admitted dimensions
    become active, their complete active states enter the hash; retired
    history remains audit provenance rather than model input.
    """

    active_expansions = expanded_dimensions or []
    if any(item.is_seed for item in active_expansions):
        raise ValueError("expanded ontology input cannot repeat seed dimensions")
    if any(
        item.status is not ExpandingDimensionStatus.ACTIVE
        for item in active_expansions
    ):
        raise ValueError("expanded ontology input must contain active dimensions")
    dimension_ids = [item.dimension.dimension_id for item in active_expansions]
    if len(dimension_ids) != len(set(dimension_ids)):
        raise ValueError("expanded ontology input dimension ids must be unique")
    if set(dimension_ids) & set(fixed_item_ids):
        raise ValueError("expanded ontology input cannot shadow a fixed dimension")
    if not active_expansions:
        return content_sha256(sorted(fixed_item_ids))
    return content_sha256(
        {
            "fixed_item_ids": sorted(fixed_item_ids),
            "expanded_dimensions": [
                item.model_dump(mode="json")
                for item in sorted(
                    active_expansions,
                    key=lambda value: value.dimension.dimension_id,
                )
            ],
        }
    )


def prediction_model_input_components_sha256(
    *,
    target_measure_id: str,
    target_measure_version: int,
    target_packet_version: int,
    target_packet_sha256: str,
    evidence_condition: EvidenceCondition | None,
    evidence_cutoff_sequence: int,
    eligible_evidence_sha256: str,
    conversation_messages_sha256: str,
    preference_state_sha256: str | None,
    active_ontology_sha256: str | None,
    preference_model: ComponentArtifactReference | None,
    semantic_mapper: ComponentArtifactReference | None,
    prediction_readout: ComponentArtifactReference,
    provider_model: ComponentArtifactReference | None,
    prompt: ComponentArtifactReference | None,
    seed: int,
) -> str:
    """Hash the provider-independent, model-consumable prediction surface."""

    def artifact_payload(
        artifact: ComponentArtifactReference | None,
    ) -> dict[str, str] | None:
        return artifact.model_dump(mode="json") if artifact is not None else None

    return content_sha256(
        {
            "target_measure_id": target_measure_id,
            "target_measure_version": target_measure_version,
            "target_packet_version": target_packet_version,
            "target_packet_sha256": target_packet_sha256,
            "evidence_condition": (
                evidence_condition.value
                if evidence_condition is not None
                else None
            ),
            "evidence_cutoff_sequence": evidence_cutoff_sequence,
            "eligible_evidence_sha256": eligible_evidence_sha256,
            "conversation_messages_sha256": conversation_messages_sha256,
            "preference_state_sha256": preference_state_sha256,
            "active_ontology_sha256": active_ontology_sha256,
            "preference_model": artifact_payload(preference_model),
            "semantic_mapper": artifact_payload(semantic_mapper),
            "prediction_readout": artifact_payload(prediction_readout),
            "provider_model": artifact_payload(provider_model),
            "prompt": artifact_payload(prompt),
            "seed": seed,
        }
    )


def prediction_model_input_sha256(
    binding: PredictionInputBinding,
    configuration: Phase4ModelConfiguration,
) -> str:
    """Hash the exact model-consumable input surface for one readout call.

    Full ontology history and configuration identity are audit provenance, not
    model inputs. The active feature universe and exact component stack are
    included instead, so fixed and expanding arms with genuinely identical
    active inputs produce the same reproducible input hash.
    """

    return prediction_model_input_components_sha256(
        target_measure_id=binding.target_measure_id,
        target_measure_version=binding.target_measure_version,
        target_packet_version=binding.target_packet_version,
        target_packet_sha256=binding.target_packet_sha256,
        evidence_condition=binding.evidence_condition,
        evidence_cutoff_sequence=binding.evidence_cutoff_sequence,
        eligible_evidence_sha256=binding.eligible_evidence_sha256,
        conversation_messages_sha256=binding.conversation_messages_sha256,
        preference_state_sha256=binding.preference_state_sha256,
        active_ontology_sha256=binding.active_ontology_sha256,
        preference_model=configuration.preference_model,
        semantic_mapper=configuration.semantic_mapper,
        prediction_readout=configuration.prediction_readout,
        provider_model=configuration.provider_model,
        prompt=configuration.prompt,
        seed=configuration.seed,
    )


class PredictionCheckpoint(str, Enum):
    ZERO_EVIDENCE = "zero_evidence"
    POST_ONBOARDING = "post_onboarding"
    POST_WAVE = "post_wave"
    IMMEDIATE_PRE_ANSWER = "immediate_pre_answer"


class ComponentArtifactReference(ContractModel):
    """Exact versioned implementation, prompt, model, or mapping artifact."""

    record_version: Literal["phase4_component_artifact.v1"] = (
        "phase4_component_artifact.v1"
    )
    artifact_id: StableId
    artifact_version: NonEmptyText
    artifact_sha256: Sha256Digest


class ReviewedSemanticMapperReference(ContractModel):
    """Aggregate-safe approval provenance for one exact semantic mapper."""

    record_version: Literal["phase4_reviewed_semantic_mapper.v1"] = (
        "phase4_reviewed_semantic_mapper.v1"
    )
    semantic_mapper: ComponentArtifactReference
    authoring_profile_id: StableId
    authoring_profile_version: PositiveVersion
    authoring_profile_sha256: Sha256Digest
    review_log_id: StableId
    review_log_version: PositiveVersion
    review_log_sha256: Sha256Digest
    review_summary_id: StableId
    review_summary_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: NonEmptyText
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    approved_measure_count: int = Field(ge=1)
    all_mappings_approved: Literal[True] = True

    @model_validator(mode="after")
    def ai_approval_requires_model_and_prompt(self) -> Self:
        if self.reviewer_type is ReviewActorType.AI and (
            self.reviewer_model_version is None
            or self.review_prompt_sha256 is None
        ):
            raise ValueError(
                "AI semantic-mapper approval requires model and prompt "
                "provenance"
            )
        return self


class Phase4ModelConfiguration(ContractModel):
    """One executable realization of a frozen Phase 4A model arm."""

    record_version: Literal["phase4_model_configuration.v1"] = (
        "phase4_model_configuration.v1"
    )
    configuration_id: StableId
    arm_id: StableId
    evidence_condition: EvidenceCondition | None
    preference_model: ComponentArtifactReference | None = None
    semantic_mapper: ComponentArtifactReference | None = None
    prediction_readout: ComponentArtifactReference
    provider_model: ComponentArtifactReference | None = None
    prompt: ComponentArtifactReference | None = None
    seed: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def provider_and_prompt_move_together(self) -> Self:
        if (self.provider_model is None) != (self.prompt is None):
            raise ValueError("provider_model and prompt must be supplied together")
        return self


class SingleChoicePrediction(ContractModel):
    record_version: Literal["phase4_single_choice_prediction.v1"] = (
        "phase4_single_choice_prediction.v1"
    )
    ballot_type: Literal[BallotType.SINGLE_CHOICE] = BallotType.SINGLE_CHOICE
    selected_option_id: StableId


class RankedPrediction(ContractModel):
    record_version: Literal["phase4_ranked_prediction.v1"] = (
        "phase4_ranked_prediction.v1"
    )
    ballot_type: Literal[BallotType.RANKED] = BallotType.RANKED
    ranking_tiers: list[RankingTier] = Field(min_length=1)

    @model_validator(mode="after")
    def ranking_option_ids_must_be_unique(self) -> Self:
        option_ids = [
            option_id
            for tier in self.ranking_tiers
            for option_id in tier.option_ids
        ]
        _require_unique(option_ids, "ranked prediction option ids")
        return self


class ApprovalPrediction(ContractModel):
    record_version: Literal["phase4_approval_prediction.v1"] = (
        "phase4_approval_prediction.v1"
    )
    ballot_type: Literal[BallotType.APPROVAL] = BallotType.APPROVAL
    approved_option_ids: list[StableId] = Field(min_length=1)

    @field_validator("approved_option_ids")
    @classmethod
    def approved_option_ids_must_be_unique(
        cls, value: list[str]
    ) -> list[str]:
        return _require_unique(value, "approved prediction option ids")


class ScorePrediction(ContractModel):
    record_version: Literal["phase4_score_prediction.v1"] = (
        "phase4_score_prediction.v1"
    )
    ballot_type: Literal[BallotType.SCORE] = BallotType.SCORE
    option_scores: dict[StableId, ScoreValue] = Field(min_length=2)


class QuadraticPrediction(ContractModel):
    record_version: Literal["phase4_quadratic_prediction.v1"] = (
        "phase4_quadratic_prediction.v1"
    )
    ballot_type: Literal[BallotType.QUADRATIC] = BallotType.QUADRATIC
    quadratic_allocations: dict[StableId, int] = Field(min_length=2)

    @model_validator(mode="after")
    def prediction_must_allocate_some_support(self) -> Self:
        if not any(self.quadratic_allocations.values()):
            raise ValueError("quadratic prediction cannot be an all-zero ballot")
        return self


BallotPrediction: TypeAlias = Annotated[
    SingleChoicePrediction
    | RankedPrediction
    | ApprovalPrediction
    | ScorePrediction
    | QuadraticPrediction,
    Field(discriminator="ballot_type"),
]


class PredictionUnsupportedAssumption(ContractModel):
    """Private audit diagnostic; never a participant-facing rationale."""

    record_version: Literal["phase4_prediction_unsupported_assumption.v1"] = (
        "phase4_prediction_unsupported_assumption.v1"
    )
    assumption_id: StableId
    description: NonEmptyText
    affected_option_ids: list[StableId] = Field(min_length=1)

    @field_validator("affected_option_ids")
    @classmethod
    def affected_option_ids_must_be_unique(
        cls, value: list[str]
    ) -> list[str]:
        return _require_unique(value, "assumption affected option ids")


class PredictionInputBinding(ContractModel):
    """Exact private inputs available before one target answer is revealed."""

    record_version: Literal["phase4_prediction_input_binding.v1"] = (
        "phase4_prediction_input_binding.v1"
    )
    target_presentation_id: StableId
    target_measure_id: StableId
    target_measure_version: PositiveVersion
    target_packet_version: PositiveVersion
    target_packet_sha256: Sha256Digest
    target_packet_visible: Literal[True] = True
    target_response_visible: Literal[False] = False
    evidence_ledger_id: StableId
    evidence_ledger_identity_sha256: Sha256Digest
    evidence_condition: EvidenceCondition | None
    evidence_cutoff_sequence: NonNegativeSequence
    eligible_evidence_event_ids: list[StableId] = Field(default_factory=list)
    eligible_evidence_sha256: Sha256Digest
    conversation_message_ids: list[StableId] = Field(default_factory=list)
    conversation_messages_sha256: Sha256Digest
    preference_state_sha256: Sha256Digest | None = None
    ontology_snapshot_sha256: Sha256Digest | None = None
    active_ontology_sha256: Sha256Digest | None = None
    model_input_sha256: Sha256Digest

    @model_validator(mode="after")
    def input_references_must_be_unique_and_coherent(self) -> Self:
        _require_unique(
            self.eligible_evidence_event_ids,
            "eligible evidence event ids",
        )
        _require_unique(
            self.conversation_message_ids,
            "conversation message ids",
        )
        if (self.ontology_snapshot_sha256 is None) != (
            self.active_ontology_sha256 is None
        ):
            raise ValueError(
                "ontology snapshot and active ontology hashes must move together"
            )
        return self


class PredictionSnapshotV2(ContractModel):
    """One frozen Phase 4 prediction before the target response is visible."""

    record_version: Literal["prediction_snapshot.v2"] = "prediction_snapshot.v2"
    snapshot_id: StableId
    session_id: StableId
    model_configuration_id: StableId
    model_configuration_sha256: Sha256Digest
    checkpoint: PredictionCheckpoint
    wave_index: Annotated[int, Field(ge=0)] | None = None
    input_binding: PredictionInputBinding
    option_probabilities: dict[StableId, Probability] = Field(min_length=2)
    top_option_id: StableId
    confidence: Probability
    settled_probability: Probability
    ballot_prediction: BallotPrediction
    provider_request_sha256: Sha256Digest | None = None
    supporting_evidence_event_ids: list[StableId] = Field(default_factory=list)
    unsupported_assumptions: list[PredictionUnsupportedAssumption] = Field(
        default_factory=list
    )
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_snapshot_shape(self) -> Self:
        _require_unique(
            self.supporting_evidence_event_ids,
            "snapshot supporting evidence event ids",
        )
        _require_unique(
            [item.assumption_id for item in self.unsupported_assumptions],
            "prediction unsupported assumption ids",
        )
        if not math.isclose(
            sum(self.option_probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("option probabilities must sum to 1")
        if self.top_option_id not in self.option_probabilities:
            raise ValueError("top_option_id must appear in option probabilities")
        top_probability = max(self.option_probabilities.values())
        if not math.isclose(
            self.option_probabilities[self.top_option_id],
            top_probability,
            rel_tol=0.0,
            abs_tol=TOP_OPTION_ABS_TOLERANCE,
        ):
            raise ValueError("top_option_id must identify a maximum probability")
        if not math.isclose(
            self.confidence,
            top_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("confidence must equal the top option probability")
        if self.checkpoint in {
            PredictionCheckpoint.ZERO_EVIDENCE,
            PredictionCheckpoint.POST_ONBOARDING,
        }:
            if self.wave_index is not None:
                raise ValueError(f"{self.checkpoint.value} cannot name a wave")
        elif self.wave_index is None:
            raise ValueError(f"{self.checkpoint.value} requires wave_index")
        if not set(self.supporting_evidence_event_ids) <= set(
            self.input_binding.eligible_evidence_event_ids
        ):
            raise ValueError(
                "supporting evidence must belong to the eligible evidence view"
            )
        return self


class Phase4EvaluationRun(ContractModel):
    """Private v2 run; compatible with v1 presentation/response execution."""

    record_version: Literal["evaluation_run.v2"] = "evaluation_run.v2"
    run_id: StableId
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    phase4_protocol_id: StableId
    phase4_protocol_version: PositiveVersion
    phase4_protocol_sha256: Sha256Digest
    session_id: StableId
    created_at: datetime
    evidence_ledger: FixedOntologyEvidenceLedger
    reviewed_semantic_mapper: ReviewedSemanticMapperReference | None = None
    expanding_ontology_ledgers: list[ExpandingOntologyLedger] = Field(
        default_factory=list
    )
    model_configurations: list[Phase4ModelConfiguration] = Field(
        default_factory=list
    )
    measure_presentations: list[MeasurePresentation] = Field(default_factory=list)
    prediction_snapshots: list[PredictionSnapshotV2] = Field(default_factory=list)
    participant_responses: list[ParticipantResponse] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_local_graph(self) -> Self:
        collections = {
            "model configuration ids": [
                item.configuration_id for item in self.model_configurations
            ],
            "presentation ids": [
                item.presentation_id for item in self.measure_presentations
            ],
            "snapshot ids": [
                item.snapshot_id for item in self.prediction_snapshots
            ],
            "response ids": [
                item.response_id for item in self.participant_responses
            ],
            "response presentation ids": [
                item.presentation_id for item in self.participant_responses
            ],
            "expanding ontology ledger ids": [
                item.ledger_id for item in self.expanding_ontology_ledgers
            ],
            "expanding ontology evidence conditions": [
                item.evidence_condition.value
                for item in self.expanding_ontology_ledgers
            ],
        }
        for label, values in collections.items():
            _require_unique(values, label)
        if self.evidence_ledger.session_id != self.session_id:
            raise ValueError("evidence ledger belongs to another session")
        if any(
            item.session_id != self.session_id
            for item in self.expanding_ontology_ledgers
        ):
            raise ValueError("expanding ontology ledger belongs to another session")

        configurations = {
            item.configuration_id: item for item in self.model_configurations
        }
        presentations = {
            item.presentation_id: item for item in self.measure_presentations
        }
        responses = {
            item.presentation_id: item for item in self.participant_responses
        }
        snapshot_keys: list[tuple[str, str, PredictionCheckpoint, int | None]] = []
        for snapshot in self.prediction_snapshots:
            if snapshot.session_id != self.session_id:
                raise ValueError(f"snapshot {snapshot.snapshot_id} belongs elsewhere")
            configuration = configurations.get(snapshot.model_configuration_id)
            if configuration is None:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} references unknown configuration"
                )
            if snapshot.model_configuration_sha256 != content_sha256(configuration):
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} configuration hash does not match"
                )
            if (
                snapshot.input_binding.evidence_condition
                is not configuration.evidence_condition
            ):
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} evidence condition does not match"
                )
            presentation = presentations.get(
                snapshot.input_binding.target_presentation_id
            )
            if presentation is None:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} references unknown presentation"
                )
            if snapshot.created_at < presentation.presented_at:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} predates target presentation"
                )
            response = responses.get(presentation.presentation_id)
            if response is not None and snapshot.created_at >= response.created_at:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} must precede target response"
                )
            snapshot_keys.append(
                (
                    snapshot.model_configuration_id,
                    presentation.presentation_id,
                    snapshot.checkpoint,
                    snapshot.wave_index,
                )
            )
        if len(snapshot_keys) != len(set(snapshot_keys)):
            raise ValueError(
                "run cannot contain duplicate model/presentation/checkpoint snapshots"
            )
        return self


def _validate_configuration_against_arm(
    configuration: Phase4ModelConfiguration,
    protocol: Phase4Protocol,
) -> None:
    arms = {item.arm_id: item for item in protocol.comparison.model_arms}
    arm = arms.get(configuration.arm_id)
    if arm is None:
        raise ValueError(
            f"configuration {configuration.configuration_id} uses unknown arm"
        )
    if arm.evidence_conditions:
        if configuration.evidence_condition not in arm.evidence_conditions:
            raise ValueError(
                f"configuration {configuration.configuration_id} uses an "
                "ineligible evidence condition"
            )
    elif configuration.evidence_condition is not None:
        raise ValueError("uniform-prior configuration cannot consume evidence")

    if arm.uses_explicit_posterior:
        if configuration.preference_model is None:
            raise ValueError("explicit-posterior arm requires preference_model")
    elif configuration.preference_model is not None:
        raise ValueError("non-posterior arm cannot name a preference_model")

    if arm.prediction_readout in {
        PredictionReadout.AUTHORED_SEMANTIC_MAPPING,
        PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR,
    }:
        if configuration.semantic_mapper is None:
            raise ValueError("mapped readout requires semantic_mapper")
    elif configuration.semantic_mapper is not None:
        raise ValueError("unmapped readout cannot name a semantic_mapper")

    uses_provider = arm.prediction_readout in {
        PredictionReadout.DIRECT_LLM,
        PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR,
    }
    if uses_provider and configuration.provider_model is None:
        raise ValueError("LLM readout requires provider_model and prompt")
    if not uses_provider and configuration.provider_model is not None:
        raise ValueError("non-LLM readout cannot name provider_model or prompt")


def _measure_lookup(
    fixture: EvaluationFixture,
    retest_variants: list[RetestPacketVariant],
) -> dict[tuple[str, int, int], MeasureVersion]:
    measures: dict[tuple[str, int, int], MeasureVersion] = {
        (measure.measure_id, measure.version, measure.packet.version): measure
        for measure in fixture.measures
    }
    canonical_by_key = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    for variant in retest_variants:
        canonical = canonical_by_key.get(
            (variant.source_measure_id, variant.source_measure_version)
        )
        if canonical is None:
            raise ValueError("retest variant references unknown canonical measure")
        key = (
            variant.source_measure_id,
            variant.source_measure_version,
            variant.packet.version,
        )
        if key in measures:
            raise ValueError("measure and packet references must be unique")
        measures[key] = MeasureVersion.model_validate(
            {
                **canonical.model_dump(mode="python"),
                "packet": variant.packet.model_dump(mode="python"),
            }
        )
    return measures


def expected_top_option_id(
    option_ids: list[str],
    probabilities: dict[str, float],
) -> str:
    """Return the first displayed option within the contract tie tolerance."""

    if not option_ids:
        raise ValueError("top-option selection requires at least one option")
    if set(option_ids) != set(probabilities):
        raise ValueError("top-option probabilities do not match the option ids")
    top_probability = max(probabilities.values())
    return next(
        option_id
        for option_id in option_ids
        if math.isclose(
            probabilities[option_id],
            top_probability,
            rel_tol=0.0,
            abs_tol=TOP_OPTION_ABS_TOLERANCE,
        )
    )


def validate_prediction_v2_for_measure(
    snapshot: PredictionSnapshotV2,
    measure: MeasureVersion,
) -> None:
    """Validate probabilities and the separate civic action against a measure."""

    binding = snapshot.input_binding
    if (
        binding.target_measure_id,
        binding.target_measure_version,
        binding.target_packet_version,
    ) != (measure.measure_id, measure.version, measure.packet.version):
        raise ValueError("prediction target does not match the measure")
    if binding.target_packet_sha256 != content_sha256(measure.packet):
        raise ValueError("prediction target packet hash does not match")

    option_ids = {option.option_id for option in measure.options}
    if set(snapshot.option_probabilities) != option_ids:
        raise ValueError("option probabilities must cover every option exactly")
    expected_top = expected_top_option_id(
        [option.option_id for option in measure.options],
        snapshot.option_probabilities,
    )
    if snapshot.top_option_id != expected_top:
        raise ValueError(
            "top_option_id must use measure display order for probability ties"
        )
    if snapshot.ballot_prediction.ballot_type is not measure.ballot_type:
        raise ValueError("ballot prediction type does not match measure ballot type")

    ballot = snapshot.ballot_prediction
    if isinstance(ballot, SingleChoicePrediction):
        if ballot.selected_option_id != snapshot.top_option_id:
            raise ValueError("single-choice action must select the top option")
    elif isinstance(ballot, RankedPrediction):
        ranked_ids = [
            option_id
            for tier in ballot.ranking_tiers
            for option_id in tier.option_ids
        ]
        if set(ranked_ids) != option_ids:
            raise ValueError("ranked prediction must cover every option exactly")
        if snapshot.top_option_id not in ballot.ranking_tiers[0].option_ids:
            raise ValueError("ranked prediction must place the top option first")
    elif isinstance(ballot, ApprovalPrediction):
        if not set(ballot.approved_option_ids) <= option_ids:
            raise ValueError("approval prediction contains an unknown option")
        if snapshot.top_option_id not in ballot.approved_option_ids:
            raise ValueError("approval prediction must approve the top option")
    elif isinstance(ballot, ScorePrediction):
        if set(ballot.option_scores) != option_ids:
            raise ValueError("score prediction must cover every option exactly")
        if ballot.option_scores[snapshot.top_option_id] != max(
            ballot.option_scores.values()
        ):
            raise ValueError("score prediction must maximize the top option")
    else:
        if set(ballot.quadratic_allocations) != option_ids:
            raise ValueError("quadratic prediction must cover every option exactly")
        if not measure.quadratic_allow_negative and any(
            value < 0 for value in ballot.quadratic_allocations.values()
        ):
            raise ValueError("quadratic prediction uses a forbidden negative value")
        budget = measure.quadratic_credit_budget
        if budget is None:
            raise ValueError("quadratic measure is missing its credit budget")
        cost = sum(value * value for value in ballot.quadratic_allocations.values())
        if cost > budget:
            raise ValueError("quadratic prediction exceeds the measure budget")
        if ballot.quadratic_allocations[snapshot.top_option_id] != max(
            ballot.quadratic_allocations.values()
        ):
            raise ValueError("quadratic prediction must maximize the top option")

    for assumption in snapshot.unsupported_assumptions:
        if not set(assumption.affected_option_ids) <= option_ids:
            raise ValueError("unsupported assumption contains an unknown option")


def as_v1_execution_run(run: Phase4EvaluationRun) -> EvaluationRun:
    """Project v2 onto the frozen v1 presentation/response execution surface."""

    return EvaluationRun(
        run_id=run.run_id,
        fixture_id=run.fixture_id,
        fixture_version=run.fixture_version,
        fixture_sha256=run.fixture_sha256,
        session_id=run.session_id,
        created_at=run.created_at,
        measure_presentations=run.measure_presentations,
        participant_responses=run.participant_responses,
    )


def _validate_snapshot_inputs(
    *,
    snapshot: PredictionSnapshotV2,
    configuration: Phase4ModelConfiguration,
    run: Phase4EvaluationRun,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    expansion_by_condition: dict[EvidenceCondition, ExpandingOntologyLedger],
) -> None:
    arm = next(
        item
        for item in protocol.comparison.model_arms
        if item.arm_id == configuration.arm_id
    )
    binding = snapshot.input_binding
    if binding.target_presentation_id != presentation.presentation_id:
        raise ValueError("snapshot target presentation binding does not match")
    if binding.evidence_ledger_id != run.evidence_ledger.ledger_id:
        raise ValueError("snapshot references another evidence ledger")
    if binding.evidence_ledger_identity_sha256 != evidence_ledger_identity_sha256(
        run.evidence_ledger
    ):
        raise ValueError("snapshot evidence ledger identity hash does not match")
    validate_prediction_v2_for_measure(snapshot, measure)

    if configuration.evidence_condition is None:
        if (
            binding.eligible_evidence_event_ids
            or binding.conversation_message_ids
            or binding.eligible_evidence_sha256 != _empty_payload_sha256()
            or binding.conversation_messages_sha256 != _empty_payload_sha256()
        ):
            raise ValueError("uniform-prior snapshot cannot bind participant evidence")
    else:
        evidence = materialize_evidence(
            run.evidence_ledger,
            condition=configuration.evidence_condition,
            cutoff_sequence=binding.evidence_cutoff_sequence,
        )
        expected_event_ids = [item.event_id for item in evidence]
        if any(event_id is None for event_id in expected_event_ids):
            raise ValueError("materialized evidence is missing an event id")
        if binding.eligible_evidence_event_ids != expected_event_ids:
            raise ValueError("snapshot must bind the exact eligible evidence view")
        if binding.eligible_evidence_sha256 != materialized_evidence_sha256(
            evidence
        ):
            raise ValueError("snapshot eligible evidence hash does not match")
        if any(
            _materialized_evidence_time(item) > presentation.presented_at
            for item in evidence
        ):
            raise ValueError("snapshot evidence includes a post-exposure event")

        if configuration.evidence_condition is EvidenceCondition.STRUCTURED_ONLY:
            expected_messages = []
        else:
            expected_messages = sorted(
                (
                    item
                    for item in run.evidence_ledger.messages
                    if item.sequence <= binding.evidence_cutoff_sequence
                ),
                key=lambda item: item.sequence,
            )
        if binding.conversation_message_ids != [
            item.message_id for item in expected_messages
        ]:
            raise ValueError("snapshot must bind the exact conversation prefix")
        if binding.conversation_messages_sha256 != (
            conversation_messages_sha256(expected_messages)
            if expected_messages
            else _empty_payload_sha256()
        ):
            raise ValueError("snapshot conversation prefix hash does not match")
        if any(
            item.created_at > presentation.presented_at
            for item in expected_messages
        ):
            raise ValueError("snapshot conversation includes a post-exposure message")

    if arm.uses_explicit_posterior:
        if binding.preference_state_sha256 is None:
            raise ValueError("explicit-posterior snapshot requires state hash")
        if binding.ontology_snapshot_sha256 is None:
            raise ValueError("explicit-posterior snapshot requires ontology hash")
        if arm.representation is PreferenceRepresentation.EXPLICIT_POSTERIOR_EXPANDING:
            condition = configuration.evidence_condition
            if condition is None:
                raise ValueError("expanding ontology requires an evidence condition")
            expansion = expansion_by_condition.get(condition)
            if expansion is None:
                raise ValueError("expanding arm is missing its ontology ledger")
            ontology = replay_expanding_ontology(
                expansion,
                run.evidence_ledger,
                cutoff_sequence=binding.evidence_cutoff_sequence,
            )
            expected_ontology_hash = content_sha256(ontology)
            expected_active_hash = active_ontology_input_sha256(
                run.evidence_ledger.ontology.item_ids,
                [
                    item
                    for item in active_dimension_states(ontology)
                    if not item.is_seed
                ],
            )
        else:
            expected_ontology_hash = content_sha256(run.evidence_ledger.ontology)
            expected_active_hash = active_ontology_input_sha256(
                run.evidence_ledger.ontology.item_ids
            )
        if binding.ontology_snapshot_sha256 != expected_ontology_hash:
            raise ValueError("snapshot ontology hash does not match")
        if binding.active_ontology_sha256 != expected_active_hash:
            raise ValueError("snapshot active ontology hash does not match")
    elif any(
        value is not None
        for value in (
            binding.preference_state_sha256,
            binding.ontology_snapshot_sha256,
            binding.active_ontology_sha256,
        )
    ):
        raise ValueError("non-posterior snapshot cannot bind posterior state")

    uses_llm = arm.prediction_readout in {
        PredictionReadout.DIRECT_LLM,
        PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR,
    }
    if uses_llm and snapshot.provider_request_sha256 is None:
        raise ValueError("LLM prediction must bind its exact provider request")
    if not uses_llm and snapshot.provider_request_sha256 is not None:
        raise ValueError("non-LLM prediction cannot bind a provider request")
    if snapshot.unsupported_assumptions and not uses_llm:
        raise ValueError("non-LLM prediction cannot emit LLM assumption flags")
    if (
        uses_llm
        and binding.eligible_evidence_event_ids
        and not snapshot.supporting_evidence_event_ids
    ):
        raise ValueError("LLM prediction must cite eligible supporting evidence")
    if binding.model_input_sha256 != prediction_model_input_sha256(
        binding,
        configuration,
    ):
        raise ValueError("snapshot model input hash does not match bound inputs")


def _validate_common_cutoffs(run: Phase4EvaluationRun) -> None:
    groups: dict[
        tuple[str, PredictionCheckpoint, int | None],
        list[PredictionSnapshotV2],
    ] = {}
    for snapshot in run.prediction_snapshots:
        key = (
            snapshot.input_binding.target_presentation_id,
            snapshot.checkpoint,
            snapshot.wave_index,
        )
        groups.setdefault(key, []).append(snapshot)
    for snapshots in groups.values():
        cutoffs = {
            item.input_binding.evidence_cutoff_sequence for item in snapshots
        }
        if len(cutoffs) != 1:
            raise ValueError("comparison snapshots must use one evidence cutoff")
        by_condition: dict[EvidenceCondition, list[PredictionSnapshotV2]] = {}
        for snapshot in snapshots:
            condition = snapshot.input_binding.evidence_condition
            if condition is not None:
                by_condition.setdefault(condition, []).append(snapshot)
        for condition_snapshots in by_condition.values():
            evidence_bindings = {
                (
                    tuple(item.input_binding.eligible_evidence_event_ids),
                    item.input_binding.eligible_evidence_sha256,
                    tuple(item.input_binding.conversation_message_ids),
                    item.input_binding.conversation_messages_sha256,
                )
                for item in condition_snapshots
            }
            if len(evidence_bindings) != 1:
                raise ValueError(
                    "same-condition comparisons must use one evidence view"
                )


def _configuration_stack(
    configuration: Phase4ModelConfiguration,
) -> tuple[
    ComponentArtifactReference | None,
    ComponentArtifactReference | None,
    ComponentArtifactReference,
    ComponentArtifactReference | None,
    ComponentArtifactReference | None,
    int,
]:
    return (
        configuration.preference_model,
        configuration.semantic_mapper,
        configuration.prediction_readout,
        configuration.provider_model,
        configuration.prompt,
        configuration.seed,
    )


def _probability_maps_close(
    left: dict[str, float],
    right: dict[str, float],
) -> bool:
    return set(left) == set(right) and all(
        math.isclose(
            left[option_id],
            right[option_id],
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for option_id in left
    )


def _validate_fixed_expanding_sanity(run: Phase4EvaluationRun) -> None:
    """Equal active feature/state inputs on one stack must yield equal outputs."""

    configurations = {
        item.configuration_id: item for item in run.model_configurations
    }
    groups: dict[
        tuple[
            str,
            PredictionCheckpoint,
            int | None,
            EvidenceCondition | None,
        ],
        list[PredictionSnapshotV2],
    ] = {}
    for snapshot in run.prediction_snapshots:
        groups.setdefault(
            (
                snapshot.input_binding.target_presentation_id,
                snapshot.checkpoint,
                snapshot.wave_index,
                snapshot.input_binding.evidence_condition,
            ),
            [],
        ).append(snapshot)

    for snapshots in groups.values():
        fixed = [
            item
            for item in snapshots
            if configurations[item.model_configuration_id].arm_id
            == "hybrid_fixed_ontology"
        ]
        expanding = [
            item
            for item in snapshots
            if configurations[item.model_configuration_id].arm_id
            == "hybrid_expanding_ontology"
        ]
        for fixed_snapshot in fixed:
            fixed_config = configurations[fixed_snapshot.model_configuration_id]
            for expanding_snapshot in expanding:
                expanding_config = configurations[
                    expanding_snapshot.model_configuration_id
                ]
                if _configuration_stack(fixed_config) != _configuration_stack(
                    expanding_config
                ):
                    continue
                fixed_input = fixed_snapshot.input_binding
                expanding_input = expanding_snapshot.input_binding
                comparable_inputs = (
                    fixed_input.eligible_evidence_sha256
                    == expanding_input.eligible_evidence_sha256
                    and fixed_input.preference_state_sha256
                    == expanding_input.preference_state_sha256
                    and fixed_input.active_ontology_sha256
                    == expanding_input.active_ontology_sha256
                    and fixed_input.model_input_sha256
                    == expanding_input.model_input_sha256
                )
                if not comparable_inputs:
                    continue
                categorical_outputs_equal = (
                    fixed_snapshot.top_option_id
                    == expanding_snapshot.top_option_id
                    and fixed_snapshot.ballot_prediction
                    == expanding_snapshot.ballot_prediction
                )
                continuous_outputs_equal = (
                    _probability_maps_close(
                        fixed_snapshot.option_probabilities,
                        expanding_snapshot.option_probabilities,
                    )
                    and math.isclose(
                        fixed_snapshot.confidence,
                        expanding_snapshot.confidence,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    and math.isclose(
                        fixed_snapshot.settled_probability,
                        expanding_snapshot.settled_probability,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                )
                if not (
                    categorical_outputs_equal and continuous_outputs_equal
                ):
                    raise ValueError(
                        "fixed and expanding arms diverge on identical active inputs"
                    )


def validate_phase4_evaluation_run(
    run: Phase4EvaluationRun,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    *,
    retest_variants: list[RetestPacketVariant] | None = None,
) -> None:
    """Validate v2 bindings without changing the frozen v1 execution contract."""

    variants = retest_variants or []
    if (
        run.fixture_id,
        run.fixture_version,
        run.fixture_sha256,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
    ):
        raise ValueError("Phase 4 run does not bind the exact fixture")
    if (
        run.phase4_protocol_id,
        run.phase4_protocol_version,
        run.phase4_protocol_sha256,
    ) != (
        protocol.protocol_id,
        protocol.protocol_version,
        content_sha256(protocol),
    ):
        raise ValueError("Phase 4 run does not bind the exact protocol")

    _validate_reviewed_semantic_mapper(run, fixture)

    projection = as_v1_execution_run(run)
    validate_run_against_fixture(
        projection,
        fixture,
        retest_variants=variants,
    )

    for configuration in run.model_configurations:
        _validate_configuration_against_arm(configuration, protocol)
    for expansion in run.expanding_ontology_ledgers:
        validate_expanding_ontology_ledger(expansion, run.evidence_ledger)

    measures = _measure_lookup(fixture, variants)
    presentations = {
        item.presentation_id: item for item in run.measure_presentations
    }
    configurations = {
        item.configuration_id: item for item in run.model_configurations
    }
    expansion_by_condition = {
        item.evidence_condition: item for item in run.expanding_ontology_ledgers
    }
    for snapshot in run.prediction_snapshots:
        presentation = presentations[snapshot.input_binding.target_presentation_id]
        key = (
            presentation.measure_id,
            presentation.measure_version,
            presentation.packet_version,
        )
        measure = measures.get(key)
        if measure is None:
            raise ValueError("snapshot references an unknown measure packet")
        if (
            snapshot.input_binding.target_measure_id,
            snapshot.input_binding.target_measure_version,
            snapshot.input_binding.target_packet_version,
        ) != key:
            raise ValueError("snapshot does not match its target presentation")
        _validate_snapshot_inputs(
            snapshot=snapshot,
            configuration=configurations[snapshot.model_configuration_id],
            run=run,
            protocol=protocol,
            measure=measure,
            presentation=presentation,
            expansion_by_condition=expansion_by_condition,
        )
    _validate_common_cutoffs(run)
    _validate_fixed_expanding_sanity(run)


def _validate_reviewed_semantic_mapper(
    run: Phase4EvaluationRun,
    fixture: EvaluationFixture,
) -> None:
    """Require exact approval provenance before a held-out mapper is used."""

    semantic_mappers = [
        configuration.semantic_mapper
        for configuration in run.model_configurations
        if configuration.semantic_mapper is not None
    ]
    approval = run.reviewed_semantic_mapper
    if not semantic_mappers:
        if approval is not None:
            raise ValueError(
                "run cannot approve a semantic mapper that no arm uses"
            )
        return
    if approval is None:
        if fixture.development_only:
            return
        raise ValueError(
            "held-out run requires an approved semantic mapper reference"
        )
    if any(
        semantic_mapper != approval.semantic_mapper
        for semantic_mapper in semantic_mappers
    ):
        raise ValueError(
            "semantic mapper approval does not match every mapped arm"
        )
    if approval.approved_measure_count != len(fixture.measures):
        raise ValueError(
            "semantic mapper approval count does not match the fixture"
        )


def assert_v1_record_versions_unchanged() -> None:
    """Pin the two legacy record discriminators beside the separate v2 types."""

    if PredictionSnapshot.model_fields["record_version"].default != (
        "prediction_snapshot.v1"
    ):
        raise ValueError("frozen PredictionSnapshot v1 contract changed")
    if EvaluationRun.model_fields["record_version"].default != "evaluation_run.v1":
        raise ValueError("frozen EvaluationRun v1 contract changed")
