"""Versioned contracts for the human preference-evaluation track.

The existing fixed-bank harness operates on synthetic latent utilities.  This
module defines the file-backed boundary for the standardized civic-measure
evaluation: versioned jurisdiction and measure inputs, auditable evidence,
pre-answer prediction snapshots, participant responses, ontology versions,
and replayable evaluation runs.

These are Pydantic contracts rather than database models.  Frozen evaluation
files and their manifests must remain reproducible even when the interactive
demo later persists equivalent records in PostgreSQL. Runtime model instances
are validated value containers, not deeply immutable objects.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

StableId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[a-z][a-z0-9_-]*$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PrivateResponseText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
]
PositiveVersion = Annotated[int, Field(ge=1)]
EventSequence = Annotated[int, Field(ge=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]

REQUIRED_JURISDICTION_FACT_KEYS = frozenset(
    {
        "population_context",
        "governance",
        "budget_and_taxes",
        "public_services",
        "housing",
        "transportation",
    }
)


class ContractModel(BaseModel):
    """Strict base model for every persisted evaluation contract."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class BallotType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    RANKED = "ranked"
    APPROVAL = "approval"
    SCORE = "score"
    QUADRATIC = "quadratic"


class ResponseField(str, Enum):
    TOP_CHOICE = "top_choice"
    RANKING = "ranking"
    APPROVAL = "approval"
    SCORES = "scores"
    QUADRATIC = "quadratic"


class MeasureDomain(str, Enum):
    FISCAL_ECONOMY_LABOR = "fiscal_economy_labor"
    HEALTH_SOCIAL_PROVISION = "health_social_provision"
    EDUCATION_FAMILY = "education_family"
    HOUSING_LAND_USE = "housing_land_use"
    TRANSPORTATION_INFRASTRUCTURE = "transportation_infrastructure"
    ENVIRONMENT_ENERGY = "environment_energy"
    JUSTICE_SAFETY_RIGHTS = "justice_safety_rights"
    GOVERNANCE_ELECTIONS_TECHNOLOGY = "governance_elections_technology"


class MeasureSourceKind(str, Enum):
    REAL_WORLD_ANCHORED = "real_world_anchored"
    CONSTRUCTED = "constructed"


class GeneralizationTier(str, Enum):
    FAMILIAR = "familiar"
    ADJACENT = "adjacent"
    NOVEL = "novel"


class ResponseState(str, Enum):
    CHOICE = "choice"
    UNSURE = "unsure"
    ABSTAIN = "abstain"


class ResponseStability(str, Enum):
    STABLE = "stable"
    TENTATIVE = "tentative"


class EvidenceModality(str, Enum):
    STRUCTURED_RESPONSE = "structured_response"
    FREE_TEXT_EXTRACTION = "free_text_extraction"
    CORRECTION = "correction"
    OVERRIDE = "override"
    NON_INTERVENTION = "non_intervention"


class PresentationKind(str, Enum):
    INITIAL = "initial"
    RETEST = "retest"


class DimensionStatus(str, Enum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class DelegationAction(str, Enum):
    VOTE = "vote"
    DEFER = "defer"
    ABSTAIN = "abstain"


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _assert_unique(values: list[str], label: str) -> None:
    duplicates = _duplicates(values)
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(f"{label} must be unique; duplicates: {joined}")


class JurisdictionFact(ContractModel):
    key: StableId
    label: NonEmptyText
    value: NonEmptyText


class JurisdictionVersion(ContractModel):
    record_version: Literal["jurisdiction.v1"] = "jurisdiction.v1"
    jurisdiction_id: StableId
    version: PositiveVersion
    name: NonEmptyText
    description: NonEmptyText
    reference_date: date
    facts: list[JurisdictionFact] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_facts(self) -> Self:
        keys = [fact.key for fact in self.facts]
        _assert_unique(keys, "jurisdiction fact keys")
        missing = REQUIRED_JURISDICTION_FACT_KEYS - set(keys)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"jurisdiction is missing required facts: {joined}")
        return self


class SourceRecord(ContractModel):
    record_version: Literal["source.v1"] = "source.v1"
    source_id: StableId
    title: NonEmptyText
    publisher: NonEmptyText | None = None
    url: HttpUrl | None = None
    published_date: date | None = None
    accessed_date: date | None = None
    adaptation_notes: NonEmptyText | None = None


class MeasureOption(ContractModel):
    record_version: Literal["measure_option.v1"] = "measure_option.v1"
    option_id: StableId
    label: NonEmptyText
    description: NonEmptyText
    display_order: Annotated[int, Field(ge=0)]


class MeasurePacket(ContractModel):
    record_version: Literal["measure_packet.v1"] = "measure_packet.v1"
    packet_id: StableId
    version: PositiveVersion
    status_quo: NonEmptyText
    proposal: NonEmptyText
    who_is_affected: NonEmptyText
    fiscal_or_operational_effects: NonEmptyText
    arguments_by_option: dict[StableId, NonEmptyText] = Field(min_length=2)
    uncertainties: list[NonEmptyText] = Field(min_length=1)
    definitions: dict[NonEmptyText, NonEmptyText] = Field(default_factory=dict)
    sources: list[SourceRecord] = Field(default_factory=list)
    authored_at: datetime

    @field_validator("authored_at")
    @classmethod
    def authored_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authored_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_source_ids(self) -> Self:
        _assert_unique(
            [source.source_id for source in self.sources],
            "packet source ids",
        )
        return self


class MeasureVersion(ContractModel):
    record_version: Literal["measure.v1"] = "measure.v1"
    measure_id: StableId
    version: PositiveVersion
    title: NonEmptyText
    domain: MeasureDomain
    ballot_type: BallotType
    response_fields: list[ResponseField] = Field(min_length=1)
    source_kind: MeasureSourceKind
    intended_generalization_tier: GeneralizationTier
    options: list[MeasureOption] = Field(min_length=2)
    packet: MeasurePacket
    quadratic_credit_budget: Annotated[int, Field(gt=0)] | None = None
    quadratic_allow_negative: bool | None = None

    @model_validator(mode="after")
    def validate_measure(self) -> Self:
        option_ids = [option.option_id for option in self.options]
        _assert_unique(option_ids, "measure option ids")
        _assert_unique(
            [option.label.casefold() for option in self.options],
            "measure option labels",
        )
        _assert_unique(
            [field.value for field in self.response_fields],
            "response fields",
        )

        expected_orders = list(range(len(self.options)))
        actual_orders = [option.display_order for option in self.options]
        if actual_orders != expected_orders:
            raise ValueError(
                "measure options must be stored in contiguous display_order "
                f"order {expected_orders}; received {actual_orders}"
            )

        argument_ids = set(self.packet.arguments_by_option)
        if argument_ids != set(option_ids):
            missing = sorted(set(option_ids) - argument_ids)
            extra = sorted(argument_ids - set(option_ids))
            raise ValueError(
                "arguments_by_option must match measure options exactly; "
                f"missing={missing}, extra={extra}"
            )

        if (
            self.source_kind is MeasureSourceKind.REAL_WORLD_ANCHORED
            and not any(source.url is not None for source in self.packet.sources)
        ):
            raise ValueError(
                "real_world_anchored measures require at least one URL-backed "
                "source record"
            )

        if self.ballot_type is BallotType.QUADRATIC:
            if ResponseField.QUADRATIC not in self.response_fields:
                raise ValueError(
                    "quadratic measures must require a quadratic response"
                )
            if self.quadratic_credit_budget is None:
                raise ValueError(
                    "quadratic measures require quadratic_credit_budget"
                )
            if self.quadratic_allow_negative is None:
                raise ValueError(
                    "quadratic measures require an explicit "
                    "quadratic_allow_negative policy"
                )
        elif (
            self.quadratic_credit_budget is not None
            or self.quadratic_allow_negative is not None
        ):
            raise ValueError(
                "quadratic settings are only valid for quadratic measures"
            )

        return self


class EvaluationFixture(ContractModel):
    schema_version: Literal["preference_eval_fixture.v1"]
    fixture_id: StableId
    fixture_version: PositiveVersion
    development_only: bool
    order_seed: Annotated[int, Field(ge=0)]
    created_at: datetime
    jurisdiction: JurisdictionVersion
    measures: list[MeasureVersion] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_measure_ids(self) -> Self:
        _assert_unique(
            [f"{measure.measure_id}@{measure.version}" for measure in self.measures],
            "measure id/version pairs",
        )
        _assert_unique(
            [
                f"{measure.packet.packet_id}@{measure.packet.version}"
                for measure in self.measures
            ],
            "packet id/version pairs",
        )
        return self


class RankingTier(ContractModel):
    option_ids: list[StableId] = Field(min_length=1)

    @field_validator("option_ids")
    @classmethod
    def option_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        _assert_unique(value, "option ids within a ranking tier")
        return value


class MeasurePresentation(ContractModel):
    """One participant exposure to a frozen measure packet."""

    record_version: Literal["measure_presentation.v1"] = "measure_presentation.v1"
    presentation_id: StableId
    session_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    packet_version: PositiveVersion
    kind: PresentationKind
    retest_of_presentation_id: StableId | None = None
    order_seed: Annotated[int, Field(ge=0)]
    presented_at: datetime

    @field_validator("presented_at")
    @classmethod
    def presentation_time_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("presented_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_retest_link(self) -> Self:
        if (
            self.kind is PresentationKind.INITIAL
            and self.retest_of_presentation_id is not None
        ):
            raise ValueError(
                "initial presentations cannot reference a prior presentation"
            )
        if (
            self.kind is PresentationKind.RETEST
            and self.retest_of_presentation_id is None
        ):
            raise ValueError(
                "retest presentations require retest_of_presentation_id"
            )
        return self


class ParticipantResponse(ContractModel):
    record_version: Literal["participant_response.v1"] = "participant_response.v1"
    response_id: StableId
    session_id: StableId
    presentation_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    packet_version: PositiveVersion
    sequence: EventSequence
    response_state: ResponseState
    selected_option_id: StableId | None = None
    confidence: Probability
    preference_strength: Annotated[int, Field(ge=0, le=10)]
    stability: ResponseStability
    ranking_tiers: list[RankingTier] | None = None
    approved_option_ids: list[StableId] | None = None
    option_scores: dict[StableId, Annotated[int, Field(ge=0, le=10)]] | None = None
    quadratic_allocations: dict[StableId, int] | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def response_time_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_response_state(self) -> Self:
        if self.ranking_tiers is not None:
            ranked = [
                option_id
                for tier in self.ranking_tiers
                for option_id in tier.option_ids
            ]
            _assert_unique(ranked, "option ids across ranking tiers")

        if self.approved_option_ids is not None:
            _assert_unique(self.approved_option_ids, "approved option ids")

        if self.response_state in {ResponseState.UNSURE, ResponseState.ABSTAIN}:
            ballot_payloads = {
                "selected_option_id": self.selected_option_id,
                "ranking_tiers": self.ranking_tiers,
                "approved_option_ids": self.approved_option_ids,
                "option_scores": self.option_scores,
                "quadratic_allocations": self.quadratic_allocations,
            }
            supplied = [name for name, value in ballot_payloads.items() if value is not None]
            if supplied:
                raise ValueError(
                    f"{self.response_state.value} responses cannot include "
                    f"ballot selections: {', '.join(supplied)}"
                )
        return self


def validate_response_for_measure(
    response: ParticipantResponse,
    measure: MeasureVersion,
) -> None:
    """Validate one response against the exact frozen measure contract."""

    if response.measure_id != measure.measure_id:
        raise ValueError(
            f"response measure_id {response.measure_id!r} does not match "
            f"{measure.measure_id!r}"
        )
    if response.measure_version != measure.version:
        raise ValueError(
            f"response measure_version {response.measure_version} does not "
            f"match {measure.version}"
        )
    if response.packet_version != measure.packet.version:
        raise ValueError(
            f"response packet_version {response.packet_version} does not "
            f"match {measure.packet.version}"
        )

    if response.response_state is not ResponseState.CHOICE:
        return

    option_ids = {option.option_id for option in measure.options}
    supplied_fields = {
        ResponseField.TOP_CHOICE: response.selected_option_id is not None,
        ResponseField.RANKING: response.ranking_tiers is not None,
        ResponseField.APPROVAL: response.approved_option_ids is not None,
        ResponseField.SCORES: response.option_scores is not None,
        ResponseField.QUADRATIC: response.quadratic_allocations is not None,
    }
    unexpected_fields = sorted(
        field.value
        for field, supplied in supplied_fields.items()
        if supplied and field not in measure.response_fields
    )
    if unexpected_fields:
        raise ValueError(
            "response includes fields not declared by the measure: "
            f"{', '.join(unexpected_fields)}"
        )

    def require_known(option_id: str, field_name: str) -> None:
        if option_id not in option_ids:
            raise ValueError(
                f"{field_name} contains unknown option {option_id!r}"
            )

    if ResponseField.TOP_CHOICE in measure.response_fields:
        if response.selected_option_id is None:
            raise ValueError("measure requires selected_option_id")
        require_known(response.selected_option_id, "selected_option_id")

    if ResponseField.RANKING in measure.response_fields:
        if response.ranking_tiers is None:
            raise ValueError("measure requires ranking_tiers")
        for tier in response.ranking_tiers:
            for option_id in tier.option_ids:
                require_known(option_id, "ranking_tiers")

    if ResponseField.APPROVAL in measure.response_fields:
        if response.approved_option_ids is None:
            raise ValueError("measure requires approved_option_ids")
        for option_id in response.approved_option_ids:
            require_known(option_id, "approved_option_ids")

    if ResponseField.SCORES in measure.response_fields:
        if response.option_scores is None:
            raise ValueError("measure requires option_scores")
        score_ids = set(response.option_scores)
        if score_ids != option_ids:
            missing = sorted(option_ids - score_ids)
            extra = sorted(score_ids - option_ids)
            raise ValueError(
                "option_scores must cover every option exactly; "
                f"missing={missing}, extra={extra}"
            )

    if ResponseField.QUADRATIC in measure.response_fields:
        if response.quadratic_allocations is None:
            raise ValueError("measure requires quadratic_allocations")
        for option_id in response.quadratic_allocations:
            require_known(option_id, "quadratic_allocations")
        if not measure.quadratic_allow_negative:
            negative_ids = sorted(
                option_id
                for option_id, votes in response.quadratic_allocations.items()
                if votes < 0
            )
            if negative_ids:
                raise ValueError(
                    "quadratic measure does not allow negative allocations; "
                    f"negative options={negative_ids}"
                )
        budget = measure.quadratic_credit_budget
        if budget is None:
            raise ValueError("quadratic response requires a measure budget")
        credit_cost = sum(
            votes * votes for votes in response.quadratic_allocations.values()
        )
        if credit_cost > budget:
            raise ValueError(
                f"quadratic allocation cost {credit_cost} exceeds credit "
                f"budget {budget}"
            )


class EvidenceEvent(ContractModel):
    record_version: Literal["evidence_event.v1"] = "evidence_event.v1"
    event_id: StableId
    session_id: StableId
    sequence: EventSequence
    modality: EvidenceModality
    measure_id: StableId | None = None
    measure_version: PositiveVersion | None = None
    packet_version: PositiveVersion | None = None
    presentation_id: StableId | None = None
    question_id: StableId | None = None
    question_version: PositiveVersion | None = None
    response_id: StableId | None = None
    raw_response: PrivateResponseText | None = None
    normalized_claims: list[NonEmptyText] = Field(default_factory=list)
    confirmed_by_participant: bool
    stability: ResponseStability
    reliability_weight: Probability
    occurred_at: datetime
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def event_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        measure_fields = (
            self.measure_id,
            self.measure_version,
            self.packet_version,
        )
        if any(value is not None for value in measure_fields) and not all(
            value is not None for value in measure_fields
        ):
            raise ValueError(
                "measure_id, measure_version, and packet_version must be "
                "supplied together"
            )
        if (self.question_id is None) != (self.question_version is None):
            raise ValueError(
                "question_id and question_version must be supplied together"
            )
        if self.presentation_id is not None and self.measure_id is None:
            raise ValueError(
                "presentation-linked evidence requires measure provenance"
            )
        if self.response_id is not None and self.presentation_id is None:
            raise ValueError(
                "response-linked evidence requires presentation_id"
            )
        if (
            self.modality is EvidenceModality.NON_INTERVENTION
            and self.reliability_weight != 0.0
        ):
            raise ValueError(
                "non_intervention evidence must have reliability_weight 0"
            )
        return self


class ModelConfiguration(ContractModel):
    record_version: Literal["model_configuration.v1"] = "model_configuration.v1"
    configuration_id: StableId
    model_name: NonEmptyText
    model_version: NonEmptyText
    prompt_version: NonEmptyText | None = None
    seed: Annotated[int, Field(ge=0)]
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class DelegationDecision(ContractModel):
    threshold: Probability
    action: DelegationAction
    option_id: StableId | None = None

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.action is DelegationAction.VOTE and self.option_id is None:
            raise ValueError("vote decisions require option_id")
        if self.action is not DelegationAction.VOTE and self.option_id is not None:
            raise ValueError(
                f"{self.action.value} decisions cannot include option_id"
            )
        return self


class PredictionSnapshot(ContractModel):
    record_version: Literal["prediction_snapshot.v1"] = "prediction_snapshot.v1"
    snapshot_id: StableId
    session_id: StableId
    target_presentation_id: StableId
    target_measure_id: StableId
    target_measure_version: PositiveVersion
    target_packet_version: PositiveVersion
    evidence_cutoff_sequence: Annotated[int, Field(ge=0)]
    evidence_event_ids: list[StableId] = Field(default_factory=list)
    option_probabilities: dict[StableId, Probability] = Field(min_length=2)
    top_option_id: StableId
    confidence: Probability
    settled_probability: Probability
    delegation_decisions: list[DelegationDecision] = Field(default_factory=list)
    model_configuration_id: StableId
    ontology_version_id: StableId | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def snapshot_time_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_probabilities(self) -> Self:
        _assert_unique(self.evidence_event_ids, "snapshot evidence event ids")
        if not math.isclose(
            sum(self.option_probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("option probabilities must sum to 1")
        if self.top_option_id not in self.option_probabilities:
            raise ValueError("top_option_id must appear in option_probabilities")
        top_probability = max(self.option_probabilities.values())
        if not math.isclose(
            self.option_probabilities[self.top_option_id],
            top_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("top_option_id must identify a maximum probability")
        if not math.isclose(
            self.confidence,
            top_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "confidence must equal the top option probability in v1"
            )
        thresholds = [decision.threshold for decision in self.delegation_decisions]
        if len(thresholds) != len(set(thresholds)):
            raise ValueError("delegation decision thresholds must be unique")
        return self


def validate_prediction_for_measure(
    snapshot: PredictionSnapshot,
    measure: MeasureVersion,
) -> None:
    """Validate one prediction against the exact frozen measure contract."""

    if snapshot.target_measure_id != measure.measure_id:
        raise ValueError(
            f"prediction target_measure_id {snapshot.target_measure_id!r} "
            f"does not match {measure.measure_id!r}"
        )
    if snapshot.target_measure_version != measure.version:
        raise ValueError(
            f"prediction target_measure_version "
            f"{snapshot.target_measure_version} does not match {measure.version}"
        )
    if snapshot.target_packet_version != measure.packet.version:
        raise ValueError(
            f"prediction target_packet_version {snapshot.target_packet_version} "
            f"does not match {measure.packet.version}"
        )

    option_ids = {option.option_id for option in measure.options}
    probability_ids = set(snapshot.option_probabilities)
    if probability_ids != option_ids:
        missing = sorted(option_ids - probability_ids)
        extra = sorted(probability_ids - option_ids)
        raise ValueError(
            "option_probabilities must cover every measure option exactly; "
            f"missing={missing}, extra={extra}"
        )
    top_probability = max(snapshot.option_probabilities.values())
    expected_top_option_id = next(
        option.option_id
        for option in measure.options
        if math.isclose(
            snapshot.option_probabilities[option.option_id],
            top_probability,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )
    if snapshot.top_option_id != expected_top_option_id:
        raise ValueError(
            "top_option_id must use measure display order to break exact "
            f"probability ties; expected {expected_top_option_id!r}"
        )
    for decision in snapshot.delegation_decisions:
        if decision.option_id is not None and decision.option_id not in option_ids:
            raise ValueError(
                f"delegation decision contains unknown option "
                f"{decision.option_id!r}"
            )


class PreferenceDimension(ContractModel):
    record_version: Literal["preference_dimension.v1"] = "preference_dimension.v1"
    dimension_id: StableId
    name: NonEmptyText
    definition: NonEmptyText
    interpretation: NonEmptyText
    status: DimensionStatus
    supporting_evidence_event_ids: list[StableId] = Field(default_factory=list)
    created_by_configuration_id: StableId

    @field_validator("supporting_evidence_event_ids")
    @classmethod
    def supporting_evidence_must_be_unique(
        cls, value: list[str]
    ) -> list[str]:
        _assert_unique(value, "dimension supporting evidence event ids")
        return value


class OntologyVersion(ContractModel):
    record_version: Literal["ontology.v1"] = "ontology.v1"
    ontology_version_id: StableId
    version: PositiveVersion
    parent_ontology_version_id: StableId | None = None
    evidence_cutoff_sequence: Annotated[int, Field(ge=0)]
    dimensions: list[PreferenceDimension] = Field(default_factory=list)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def ontology_time_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def dimension_ids_must_be_unique(self) -> Self:
        _assert_unique(
            [dimension.dimension_id for dimension in self.dimensions],
            "ontology dimension ids",
        )
        return self


class EvaluationRun(ContractModel):
    record_version: Literal["evaluation_run.v1"] = "evaluation_run.v1"
    run_id: StableId
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    session_id: StableId
    created_at: datetime
    model_configurations: list[ModelConfiguration] = Field(default_factory=list)
    ontology_versions: list[OntologyVersion] = Field(default_factory=list)
    measure_presentations: list[MeasurePresentation] = Field(default_factory=list)
    evidence_events: list[EvidenceEvent] = Field(default_factory=list)
    prediction_snapshots: list[PredictionSnapshot] = Field(default_factory=list)
    participant_responses: list[ParticipantResponse] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def run_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_references_and_cutoffs(self) -> Self:
        self._validate_unique_ids()

        presentation_by_id = {
            presentation.presentation_id: presentation
            for presentation in self.measure_presentations
        }
        response_by_id = {
            response.response_id: response
            for response in self.participant_responses
        }
        response_by_presentation_id = {
            response.presentation_id: response
            for response in self.participant_responses
        }
        event_by_id = {
            event.event_id: event for event in self.evidence_events
        }
        config_ids = {
            config.configuration_id for config in self.model_configurations
        }
        ontology_by_id = {
            ontology.ontology_version_id: ontology
            for ontology in self.ontology_versions
        }

        event_stream = self._ordered_event_stream()
        self._validate_event_sequences(event_stream)
        self._validate_session_ownership()
        self._validate_presentations(presentation_by_id)
        self._validate_responses(presentation_by_id)
        self._validate_evidence_references(
            presentation_by_id,
            response_by_id,
        )
        self._validate_ontologies(event_by_id, config_ids, event_stream)
        self._validate_snapshots(
            presentation_by_id=presentation_by_id,
            response_by_presentation_id=response_by_presentation_id,
            event_by_id=event_by_id,
            config_ids=config_ids,
            ontology_by_id=ontology_by_id,
            event_stream=event_stream,
        )
        return self

    def _validate_unique_ids(self) -> None:
        collections = {
            "model configuration ids": [
                config.configuration_id for config in self.model_configurations
            ],
            "ontology version ids": [
                ontology.ontology_version_id for ontology in self.ontology_versions
            ],
            "measure presentation ids": [
                presentation.presentation_id
                for presentation in self.measure_presentations
            ],
            "evidence event ids": [event.event_id for event in self.evidence_events],
            "prediction snapshot ids": [
                snapshot.snapshot_id for snapshot in self.prediction_snapshots
            ],
            "participant response ids": [
                response.response_id for response in self.participant_responses
            ],
        }
        for label, values in collections.items():
            _assert_unique(values, label)
        _assert_unique(
            [
                response.presentation_id
                for response in self.participant_responses
            ],
            "response presentation ids",
        )
        _assert_unique(
            [
                f"{presentation.measure_id}@{presentation.measure_version}"
                for presentation in self.measure_presentations
                if presentation.kind is PresentationKind.INITIAL
            ],
            "initial presentation measure id/version pairs",
        )

    def _ordered_event_stream(self) -> list[tuple[int, datetime, str]]:
        records = [
            (
                event.sequence,
                event.occurred_at,
                f"evidence event {event.event_id}",
            )
            for event in self.evidence_events
        ]
        records.extend(
            (
                response.sequence,
                response.created_at,
                f"response {response.response_id}",
            )
            for response in self.participant_responses
        )
        return sorted(records, key=lambda record: record[0])

    def _validate_event_sequences(
        self,
        event_stream: list[tuple[int, datetime, str]],
    ) -> None:
        all_sequences = [sequence for sequence, _, _ in event_stream]
        if len(all_sequences) != len(set(all_sequences)):
            raise ValueError(
                "evidence and response records must share one unique event sequence"
            )
        for previous, current in zip(event_stream, event_stream[1:]):
            previous_sequence, previous_time, previous_label = previous
            current_sequence, current_time, current_label = current
            if current_time < previous_time:
                raise ValueError(
                    "evidence and response sequence must agree with time: "
                    f"{current_label} at sequence {current_sequence} predates "
                    f"{previous_label} at sequence {previous_sequence}"
                )

    @staticmethod
    def _validate_cutoff_chronology(
        *,
        owner_label: str,
        cutoff_sequence: int,
        created_at: datetime,
        event_stream: list[tuple[int, datetime, str]],
    ) -> None:
        for sequence, recorded_at, record_label in event_stream:
            if sequence > cutoff_sequence:
                break
            if recorded_at > created_at:
                raise ValueError(
                    f"{owner_label} cutoff includes future {record_label} at "
                    f"sequence {sequence}"
                )

    def _validate_session_ownership(self) -> None:
        for presentation in self.measure_presentations:
            if presentation.session_id != self.session_id:
                raise ValueError(
                    f"presentation {presentation.presentation_id} belongs to "
                    "another session"
                )
        for event in self.evidence_events:
            if event.session_id != self.session_id:
                raise ValueError(
                    f"evidence event {event.event_id} belongs to another session"
                )
        for response in self.participant_responses:
            if response.session_id != self.session_id:
                raise ValueError(
                    f"response {response.response_id} belongs to another session"
                )
        for snapshot in self.prediction_snapshots:
            if snapshot.session_id != self.session_id:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} belongs to another session"
                )

    def _validate_presentations(
        self,
        presentation_by_id: dict[str, MeasurePresentation],
    ) -> None:
        for presentation in self.measure_presentations:
            if presentation.kind is not PresentationKind.RETEST:
                continue
            original_id = presentation.retest_of_presentation_id
            original = presentation_by_id.get(original_id or "")
            if original is None:
                raise ValueError(
                    f"retest presentation {presentation.presentation_id} "
                    f"references unknown presentation {original_id}"
                )
            if original.kind is not PresentationKind.INITIAL:
                raise ValueError(
                    f"retest presentation {presentation.presentation_id} must "
                    "reference an initial presentation"
                )
            if (
                presentation.measure_id,
                presentation.measure_version,
            ) != (
                original.measure_id,
                original.measure_version,
            ):
                raise ValueError(
                    f"retest presentation {presentation.presentation_id} must "
                    "use the original measure id and version"
                )
            if presentation.presented_at <= original.presented_at:
                raise ValueError(
                    f"retest presentation {presentation.presentation_id} must "
                    "occur after its original presentation"
                )

    def _validate_responses(
        self,
        presentation_by_id: dict[str, MeasurePresentation],
    ) -> None:
        for response in self.participant_responses:
            presentation = presentation_by_id.get(response.presentation_id)
            if presentation is None:
                raise ValueError(
                    f"response {response.response_id} references unknown "
                    f"presentation {response.presentation_id}"
                )
            if (
                response.measure_id,
                response.measure_version,
                response.packet_version,
            ) != (
                presentation.measure_id,
                presentation.measure_version,
                presentation.packet_version,
            ):
                raise ValueError(
                    f"response {response.response_id} does not match "
                    f"presentation {presentation.presentation_id}"
                )
            if response.created_at < presentation.presented_at:
                raise ValueError(
                    f"response {response.response_id} predates presentation "
                    f"{presentation.presentation_id}"
                )

    def _validate_evidence_references(
        self,
        presentation_by_id: dict[str, MeasurePresentation],
        response_by_id: dict[str, ParticipantResponse],
    ) -> None:
        for event in self.evidence_events:
            presentation = None
            if event.presentation_id is not None:
                presentation = presentation_by_id.get(event.presentation_id)
                if presentation is None:
                    raise ValueError(
                        f"evidence event {event.event_id} references unknown "
                        f"presentation {event.presentation_id}"
                    )
                if (
                    event.measure_id,
                    event.measure_version,
                    event.packet_version,
                ) != (
                    presentation.measure_id,
                    presentation.measure_version,
                    presentation.packet_version,
                ):
                    raise ValueError(
                        f"evidence event {event.event_id} does not match "
                        f"presentation {presentation.presentation_id}"
                    )

            if event.response_id is None:
                continue
            response = response_by_id.get(event.response_id)
            if response is None:
                raise ValueError(
                    f"evidence event {event.event_id} references unknown "
                    f"response {event.response_id}"
                )
            if event.presentation_id != response.presentation_id:
                raise ValueError(
                    f"evidence event {event.event_id} and response "
                    f"{response.response_id} use different presentations"
                )
            if event.measure_id != response.measure_id:
                raise ValueError(
                    f"evidence event {event.event_id} and response "
                    f"{response.response_id} use different measures"
                )
            if event.sequence <= response.sequence:
                raise ValueError(
                    f"evidence event {event.event_id} must follow response "
                    f"{response.response_id} in the event sequence"
                )
            if event.occurred_at < response.created_at:
                raise ValueError(
                    f"evidence event {event.event_id} predates response "
                    f"{response.response_id}"
                )

    def _validate_ontologies(
        self,
        event_by_id: dict[str, EvidenceEvent],
        config_ids: set[str],
        event_stream: list[tuple[int, datetime, str]],
    ) -> None:
        for ontology in self.ontology_versions:
            self._validate_cutoff_chronology(
                owner_label=f"ontology {ontology.ontology_version_id}",
                cutoff_sequence=ontology.evidence_cutoff_sequence,
                created_at=ontology.created_at,
                event_stream=event_stream,
            )
            for dimension in ontology.dimensions:
                if dimension.created_by_configuration_id not in config_ids:
                    raise ValueError(
                        f"dimension {dimension.dimension_id} references unknown "
                        f"model configuration "
                        f"{dimension.created_by_configuration_id}"
                    )
                for event_id in dimension.supporting_evidence_event_ids:
                    event = event_by_id.get(event_id)
                    if event is None:
                        raise ValueError(
                            f"dimension {dimension.dimension_id} references "
                            f"unknown evidence event {event_id}"
                        )
                    if event.sequence > ontology.evidence_cutoff_sequence:
                        raise ValueError(
                            f"ontology {ontology.ontology_version_id} uses future "
                            f"evidence event {event_id} at sequence "
                            f"{event.sequence} after cutoff "
                            f"{ontology.evidence_cutoff_sequence}"
                        )

    def _validate_snapshots(
        self,
        *,
        presentation_by_id: dict[str, MeasurePresentation],
        response_by_presentation_id: dict[str, ParticipantResponse],
        event_by_id: dict[str, EvidenceEvent],
        config_ids: set[str],
        ontology_by_id: dict[str, OntologyVersion],
        event_stream: list[tuple[int, datetime, str]],
    ) -> None:
        for snapshot in self.prediction_snapshots:
            presentation = presentation_by_id.get(
                snapshot.target_presentation_id
            )
            if presentation is None:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} references unknown "
                    f"presentation {snapshot.target_presentation_id}"
                )
            if (
                snapshot.target_measure_id,
                snapshot.target_measure_version,
                snapshot.target_packet_version,
            ) != (
                presentation.measure_id,
                presentation.measure_version,
                presentation.packet_version,
            ):
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} does not match "
                    f"presentation {presentation.presentation_id}"
                )
            if snapshot.created_at < presentation.presented_at:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} predates presentation "
                    f"{presentation.presentation_id}"
                )
            if snapshot.model_configuration_id not in config_ids:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} references unknown model "
                    f"configuration {snapshot.model_configuration_id}"
                )
            if (
                snapshot.ontology_version_id is not None
                and snapshot.ontology_version_id not in ontology_by_id
            ):
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} references unknown ontology "
                    f"{snapshot.ontology_version_id}"
                )
            if snapshot.ontology_version_id is not None:
                ontology = ontology_by_id[snapshot.ontology_version_id]
                if (
                    ontology.evidence_cutoff_sequence
                    > snapshot.evidence_cutoff_sequence
                ):
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} references ontology "
                        f"{ontology.ontology_version_id} built after the "
                        f"snapshot evidence cutoff"
                    )

            for event_id in snapshot.evidence_event_ids:
                event = event_by_id.get(event_id)
                if event is None:
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} references unknown "
                        f"evidence event {event_id}"
                    )
                if event.sequence > snapshot.evidence_cutoff_sequence:
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} references future "
                        f"evidence event {event_id} at sequence {event.sequence} "
                        f"after cutoff {snapshot.evidence_cutoff_sequence}"
                    )

            presentation_leaks = [
                event.event_id
                for event in self.evidence_events
                if event.presentation_id == snapshot.target_presentation_id
                and event.sequence <= snapshot.evidence_cutoff_sequence
            ]
            if presentation_leaks:
                raise ValueError(
                    f"snapshot {snapshot.snapshot_id} target presentation is "
                    f"already in evidence: {', '.join(presentation_leaks)}"
                )

            if presentation.kind is PresentationKind.INITIAL:
                prior_target_events = [
                    event.event_id
                    for event in self.evidence_events
                    if event.measure_id == snapshot.target_measure_id
                    and event.sequence <= snapshot.evidence_cutoff_sequence
                ]
                if prior_target_events:
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} initial target answer "
                        f"is already in evidence: {', '.join(prior_target_events)}"
                    )

            response = response_by_presentation_id.get(
                snapshot.target_presentation_id
            )
            if response is not None:
                if response.sequence <= snapshot.evidence_cutoff_sequence:
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} was created after target "
                        f"response {response.response_id} entered the event stream"
                    )
                if snapshot.created_at >= response.created_at:
                    raise ValueError(
                        f"snapshot {snapshot.snapshot_id} must precede target "
                        f"response {response.response_id}"
                    )

            self._validate_cutoff_chronology(
                owner_label=f"snapshot {snapshot.snapshot_id}",
                cutoff_sequence=snapshot.evidence_cutoff_sequence,
                created_at=snapshot.created_at,
                event_stream=event_stream,
            )
