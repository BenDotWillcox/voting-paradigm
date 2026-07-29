"""Deterministic prequential replay for standardized human measures.

Adapters receive the frozen jurisdiction, one target measure, and only the
evidence available at a declared cutoff. Participant responses remain outside
the adapter boundary until after the immediate pre-answer prediction is
captured.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import (
    ContractModel,
    DelegationAction,
    DelegationDecision,
    EvaluationFixture,
    EvaluationRun,
    EvidenceEvent,
    EvidenceModality,
    JurisdictionVersion,
    MeasurePresentation,
    MeasureVersion,
    ModelConfiguration,
    ParticipantResponse,
    PositiveVersion,
    PredictionSnapshot,
    PresentationKind,
    Probability,
    RankingTier,
    ResponseStability,
    ResponseState,
    Sha256Digest,
    StableId,
    validate_prediction_for_measure,
    validate_response_for_measure,
)
from .fixture_io import content_sha256, validate_run_against_fixture

DEFAULT_DELEGATION_THRESHOLDS = (0.65, 0.75, 0.85, 0.95)


class SnapshotCheckpoint(str, Enum):
    ZERO_EVIDENCE = "zero_evidence"
    POST_ONBOARDING = "post_onboarding"
    POST_WAVE = "post_wave"
    IMMEDIATE_PRE_ANSWER = "immediate_pre_answer"


class AdapterPrediction(ContractModel):
    """One adapter response before it is bound to a persisted snapshot."""

    option_probabilities: dict[StableId, Probability] = Field(min_length=2)
    settled_probability: Probability
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def probabilities_must_sum_to_one(self) -> "AdapterPrediction":
        if not math.isclose(
            sum(self.option_probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("adapter option probabilities must sum to 1")
        return self


@dataclass(frozen=True)
class PredictionRequest:
    """Leakage-safe input supplied to every prediction adapter."""

    jurisdiction: JurisdictionVersion
    target_measure: MeasureVersion
    target_presentation: MeasurePresentation
    evidence_events: tuple[EvidenceEvent, ...]
    checkpoint: SnapshotCheckpoint
    wave_index: int | None


@runtime_checkable
class PredictionModelAdapter(Protocol):
    @property
    def configuration(self) -> ModelConfiguration:
        """Return the frozen configuration recorded with every snapshot."""

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        """Predict from the target packet and evidence available at the cutoff."""


class UniformPredictionAdapter:
    """Legitimate zero-information baseline with equal option probability."""

    def __init__(
        self,
        *,
        configuration_id: str = "uniform_prior_v1",
        seed: int = 0,
        settled_probability: float = 0.5,
    ) -> None:
        self._configuration = ModelConfiguration(
            configuration_id=configuration_id,
            model_name="Uniform prior",
            model_version="v1",
            seed=seed,
            parameters={"role": "zero_information_baseline"},
        )
        self._settled_probability = settled_probability

    @property
    def configuration(self) -> ModelConfiguration:
        return self._configuration.model_copy(deep=True)

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        probability = 1.0 / len(request.target_measure.options)
        return AdapterPrediction(
            option_probabilities={
                option.option_id: probability
                for option in request.target_measure.options
            },
            settled_probability=self._settled_probability,
            metadata={"evidence_count": len(request.evidence_events)},
        )


class ScriptedPredictionAdapter:
    """Deterministic test double for replay, chronology, and metric tests."""

    def __init__(
        self,
        *,
        configuration: ModelConfiguration,
        probabilities_by_measure: dict[str, dict[str, float]],
        settled_probability_by_measure: dict[str, float],
        prediction_metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        self._configuration = configuration.model_copy(deep=True)
        self._probabilities_by_measure = {
            measure_id: dict(probabilities)
            for measure_id, probabilities in probabilities_by_measure.items()
        }
        self._settled_probability_by_measure = dict(
            settled_probability_by_measure
        )
        self._prediction_metadata = dict(prediction_metadata or {})

    @property
    def configuration(self) -> ModelConfiguration:
        return self._configuration.model_copy(deep=True)

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        measure_id = request.target_measure.measure_id
        try:
            probabilities = self._probabilities_by_measure[measure_id]
            settled_probability = self._settled_probability_by_measure[
                measure_id
            ]
        except KeyError as error:
            raise ValueError(
                f"scripted adapter has no prediction for {measure_id}"
            ) from error
        return AdapterPrediction(
            option_probabilities=probabilities,
            settled_probability=settled_probability,
            metadata={
                **self._prediction_metadata,
                "evidence_count": len(request.evidence_events),
            },
        )


class SessionResponse(ContractModel):
    """Future response template kept outside the model adapter boundary."""

    measure_id: StableId
    measure_version: PositiveVersion
    response_state: ResponseState
    selected_option_id: StableId | None = None
    confidence: Probability
    preference_strength: int = Field(ge=0, le=10)
    stability: ResponseStability
    ranking_tiers: list[RankingTier] | None = None
    approved_option_ids: list[StableId] | None = None
    option_scores: dict[StableId, int] | None = None
    quadratic_allocations: dict[StableId, int] | None = None
    evidence_reliability_weight: Probability

    @model_validator(mode="after")
    def nonchoices_cannot_include_ballot_fields(self) -> "SessionResponse":
        if self.response_state not in {
            ResponseState.UNSURE,
            ResponseState.ABSTAIN,
        }:
            return self
        supplied = [
            name
            for name, value in {
                "selected_option_id": self.selected_option_id,
                "ranking_tiers": self.ranking_tiers,
                "approved_option_ids": self.approved_option_ids,
                "option_scores": self.option_scores,
                "quadratic_allocations": self.quadratic_allocations,
            }.items()
            if value is not None
        ]
        if supplied:
            raise ValueError(
                f"{self.response_state.value} responses cannot include ballot "
                f"selections: {', '.join(supplied)}"
            )
        return self


class PrequentialSessionScript(ContractModel):
    """Versioned synthetic or private input used to replay one session."""

    schema_version: Literal["prequential_session_script.v1"] = (
        "prequential_session_script.v1"
    )
    script_id: StableId
    script_version: PositiveVersion
    run_id: StableId
    session_id: StableId
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    started_at: datetime
    order_seed: int = Field(ge=0)
    wave_size: int = Field(gt=0)
    onboarding_evidence: list[EvidenceEvent] = Field(default_factory=list)
    responses: list[SessionResponse] = Field(min_length=1)

    @field_validator("started_at")
    @classmethod
    def started_at_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_script_records(self) -> "PrequentialSessionScript":
        measure_keys = [
            (response.measure_id, response.measure_version)
            for response in self.responses
        ]
        if len(measure_keys) != len(set(measure_keys)):
            raise ValueError("session script responses must target unique measures")

        ordered_events = sorted(
            self.onboarding_evidence,
            key=lambda event: event.sequence,
        )
        expected_sequences = list(range(1, len(ordered_events) + 1))
        if [event.sequence for event in ordered_events] != expected_sequences:
            raise ValueError(
                "onboarding evidence sequences must be contiguous from 1"
            )
        previous_time = self.started_at
        for event in ordered_events:
            if event.session_id != self.session_id:
                raise ValueError(
                    f"onboarding event {event.event_id} belongs to another session"
                )
            if event.occurred_at < previous_time:
                raise ValueError(
                    "onboarding evidence sequence must agree with time"
                )
            if event.presentation_id is not None or event.response_id is not None:
                raise ValueError(
                    "onboarding evidence cannot reference a target presentation "
                    "or response"
                )
            previous_time = event.occurred_at
        return self


class SnapshotTrace(ContractModel):
    """Private checkpoint metadata associated with a persisted snapshot."""

    record_version: Literal["snapshot_trace.v1"] = "snapshot_trace.v1"
    snapshot_id: StableId
    checkpoint: SnapshotCheckpoint
    wave_index: int | None = Field(default=None, ge=0)
    response_order: int | None = Field(default=None, ge=0)
    adapter_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class PrequentialReplay(ContractModel):
    """Private replay record. Never serialize this as a public artifact."""

    schema_version: Literal["prequential_replay.v1"] = "prequential_replay.v1"
    session_script_id: StableId
    session_script_version: PositiveVersion
    session_script_sha256: Sha256Digest
    completed_at: datetime
    run: EvaluationRun
    snapshot_traces: list[SnapshotTrace]

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def traces_must_cover_snapshots(self) -> "PrequentialReplay":
        trace_ids = [trace.snapshot_id for trace in self.snapshot_traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("snapshot trace ids must be unique")
        snapshot_ids = {
            snapshot.snapshot_id for snapshot in self.run.prediction_snapshots
        }
        if set(trace_ids) != snapshot_ids:
            missing = sorted(snapshot_ids - set(trace_ids))
            extra = sorted(set(trace_ids) - snapshot_ids)
            raise ValueError(
                "snapshot traces must cover every snapshot exactly; "
                f"missing={missing}, extra={extra}"
            )
        return self


def load_session_script(path: str | Path) -> PrequentialSessionScript:
    """Load one strict session script from JSON."""

    with open(path, encoding="utf-8") as source:
        return PrequentialSessionScript.model_validate(json.load(source))


def validate_session_script_against_fixture(
    script: PrequentialSessionScript,
    fixture: EvaluationFixture,
    *,
    require_complete: bool = True,
) -> None:
    """Validate future response templates without exposing them to adapters."""

    if script.fixture_id != fixture.fixture_id:
        raise ValueError(
            f"script fixture_id {script.fixture_id!r} does not match "
            f"{fixture.fixture_id!r}"
        )
    if script.fixture_version != fixture.fixture_version:
        raise ValueError(
            f"script fixture_version {script.fixture_version} does not match "
            f"{fixture.fixture_version}"
        )
    expected_hash = content_sha256(fixture)
    if script.fixture_sha256 != expected_hash:
        raise ValueError(
            f"script fixture_sha256 {script.fixture_sha256} does not match "
            f"{expected_hash}"
        )

    measure_by_key = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    response_keys = {
        (response.measure_id, response.measure_version)
        for response in script.responses
    }
    if require_complete and response_keys != set(measure_by_key):
        missing = sorted(set(measure_by_key) - response_keys)
        extra = sorted(response_keys - set(measure_by_key))
        raise ValueError(
            "complete session script must answer every fixture measure once; "
            f"missing={missing}, extra={extra}"
        )

    for index, response_template in enumerate(script.responses, start=1):
        key = (
            response_template.measure_id,
            response_template.measure_version,
        )
        measure = measure_by_key.get(key)
        if measure is None:
            raise ValueError(
                "session response references unknown measure "
                f"{response_template.measure_id}@"
                f"{response_template.measure_version}"
            )
        response = _build_response(
            template=response_template,
            measure=measure,
            session_id=script.session_id,
            presentation_id=f"validation_presentation_{index}",
            response_id=f"validation_response_{index}",
            sequence=index,
            created_at=script.started_at + timedelta(seconds=index),
        )
        validate_response_for_measure(response, measure)


def _seeded_response_order(
    responses: list[SessionResponse],
    seed: int,
) -> list[SessionResponse]:
    """Use a cross-version stable hash order instead of RNG shuffle details."""

    def order_key(response: SessionResponse) -> tuple[str, str]:
        digest = hashlib.sha256(
            f"{seed}:{response.measure_id}:{response.measure_version}".encode(
                "utf-8"
            )
        ).hexdigest()
        return digest, response.measure_id

    return sorted(responses, key=order_key)


def _validate_thresholds(
    thresholds: tuple[float, ...],
) -> tuple[float, ...]:
    if not thresholds:
        raise ValueError("at least one delegation threshold is required")
    if len(thresholds) != len(set(thresholds)):
        raise ValueError("delegation thresholds must be unique")
    if any(threshold < 0.0 or threshold > 1.0 for threshold in thresholds):
        raise ValueError("delegation thresholds must fall between 0 and 1")
    return tuple(sorted(thresholds))


def _build_response(
    *,
    template: SessionResponse,
    measure: MeasureVersion,
    session_id: str,
    presentation_id: str,
    response_id: str,
    sequence: int,
    created_at: datetime,
) -> ParticipantResponse:
    return ParticipantResponse(
        response_id=response_id,
        session_id=session_id,
        presentation_id=presentation_id,
        measure_id=measure.measure_id,
        measure_version=measure.version,
        packet_version=measure.packet.version,
        sequence=sequence,
        response_state=template.response_state,
        selected_option_id=template.selected_option_id,
        confidence=template.confidence,
        preference_strength=template.preference_strength,
        stability=template.stability,
        ranking_tiers=template.ranking_tiers,
        approved_option_ids=template.approved_option_ids,
        option_scores=template.option_scores,
        quadratic_allocations=template.quadratic_allocations,
        created_at=created_at,
    )


def _response_evidence(
    *,
    response: ParticipantResponse,
    template: SessionResponse,
    event_id: str,
    sequence: int,
    occurred_at: datetime,
) -> EvidenceEvent:
    if response.response_state is ResponseState.CHOICE:
        claim = f"Selected option {response.selected_option_id}."
    elif response.response_state is ResponseState.ABSTAIN:
        claim = "Chose to abstain."
    else:
        claim = "Reported being unsure."
    return EvidenceEvent(
        event_id=event_id,
        session_id=response.session_id,
        sequence=sequence,
        modality=EvidenceModality.STRUCTURED_RESPONSE,
        measure_id=response.measure_id,
        measure_version=response.measure_version,
        packet_version=response.packet_version,
        presentation_id=response.presentation_id,
        response_id=response.response_id,
        raw_response=f"Synthetic development response: {claim}",
        normalized_claims=[claim],
        confirmed_by_participant=True,
        stability=response.stability,
        reliability_weight=template.evidence_reliability_weight,
        occurred_at=occurred_at,
        metadata={
            "synthetic": True,
            "response_state": response.response_state.value,
        },
    )


def run_prequential_session(
    *,
    fixture: EvaluationFixture,
    script: PrequentialSessionScript,
    adapters: list[PredictionModelAdapter],
    delegation_thresholds: tuple[float, ...] = DEFAULT_DELEGATION_THRESHOLDS,
) -> PrequentialReplay:
    """Replay one session while freezing every prediction before its answer."""

    validate_session_script_against_fixture(script, fixture)
    thresholds = _validate_thresholds(delegation_thresholds)
    if not adapters:
        raise ValueError("at least one prediction adapter is required")

    configurations = [adapter.configuration for adapter in adapters]
    configuration_ids = [
        configuration.configuration_id for configuration in configurations
    ]
    if len(configuration_ids) != len(set(configuration_ids)):
        raise ValueError("prediction adapter configuration ids must be unique")

    measure_by_key = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    ordered_responses = _seeded_response_order(
        script.responses,
        script.order_seed,
    )
    presentations: list[MeasurePresentation] = []
    presentation_by_key: dict[tuple[str, int], MeasurePresentation] = {}
    response_order_by_key: dict[tuple[str, int], int] = {}
    for response_order, template in enumerate(ordered_responses):
        measure = measure_by_key[(template.measure_id, template.measure_version)]
        presentation = MeasurePresentation(
            presentation_id=(
                f"presentation_{response_order + 1}_{measure.measure_id}"
            ),
            session_id=script.session_id,
            measure_id=measure.measure_id,
            measure_version=measure.version,
            packet_version=measure.packet.version,
            kind=PresentationKind.INITIAL,
            order_seed=script.order_seed,
            presented_at=script.started_at,
        )
        presentations.append(presentation)
        key = (measure.measure_id, measure.version)
        presentation_by_key[key] = presentation
        response_order_by_key[key] = response_order

    evidence_events: list[EvidenceEvent] = []
    participant_responses: list[ParticipantResponse] = []
    snapshots: list[PredictionSnapshot] = []
    traces: list[SnapshotTrace] = []
    snapshot_number = 0
    last_sequence = 0
    clock = script.started_at

    def capture(
        *,
        checkpoint: SnapshotCheckpoint,
        response_templates: list[SessionResponse],
        created_at: datetime,
        wave_index: int | None,
    ) -> None:
        nonlocal snapshot_number
        for template in response_templates:
            key = (template.measure_id, template.measure_version)
            measure = measure_by_key[key]
            presentation = presentation_by_key[key]
            for adapter, configuration in zip(adapters, configurations):
                request = PredictionRequest(
                    jurisdiction=fixture.jurisdiction.model_copy(deep=True),
                    target_measure=measure.model_copy(deep=True),
                    target_presentation=presentation.model_copy(deep=True),
                    evidence_events=tuple(
                        event.model_copy(deep=True)
                        for event in evidence_events
                    ),
                    checkpoint=checkpoint,
                    wave_index=wave_index,
                )
                prediction = adapter.predict(request)
                expected_option_ids = {
                    option.option_id for option in measure.options
                }
                if set(prediction.option_probabilities) != expected_option_ids:
                    missing = sorted(
                        expected_option_ids
                        - set(prediction.option_probabilities)
                    )
                    extra = sorted(
                        set(prediction.option_probabilities)
                        - expected_option_ids
                    )
                    raise ValueError(
                        f"adapter {configuration.configuration_id} returned "
                        f"wrong options for {measure.measure_id}; "
                        f"missing={missing}, extra={extra}"
                    )

                top_probability = max(
                    prediction.option_probabilities.values()
                )
                top_option_id = next(
                    option.option_id
                    for option in measure.options
                    if math.isclose(
                        prediction.option_probabilities[option.option_id],
                        top_probability,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                )
                decisions = [
                    DelegationDecision(
                        threshold=threshold,
                        action=(
                            DelegationAction.VOTE
                            if top_probability >= threshold
                            else DelegationAction.DEFER
                        ),
                        option_id=(
                            top_option_id
                            if top_probability >= threshold
                            else None
                        ),
                    )
                    for threshold in thresholds
                ]
                snapshot_number += 1
                snapshot = PredictionSnapshot(
                    snapshot_id=(
                        f"snapshot_{snapshot_number:04d}_"
                        f"{configuration.configuration_id}_"
                        f"{measure.measure_id}"
                    ),
                    session_id=script.session_id,
                    target_presentation_id=presentation.presentation_id,
                    target_measure_id=measure.measure_id,
                    target_measure_version=measure.version,
                    target_packet_version=measure.packet.version,
                    evidence_cutoff_sequence=last_sequence,
                    evidence_event_ids=[
                        event.event_id for event in evidence_events
                    ],
                    option_probabilities=prediction.option_probabilities,
                    top_option_id=top_option_id,
                    confidence=top_probability,
                    settled_probability=prediction.settled_probability,
                    delegation_decisions=decisions,
                    model_configuration_id=configuration.configuration_id,
                    created_at=created_at,
                )
                validate_prediction_for_measure(snapshot, measure)
                snapshots.append(snapshot)
                traces.append(
                    SnapshotTrace(
                        snapshot_id=snapshot.snapshot_id,
                        checkpoint=checkpoint,
                        wave_index=wave_index,
                        response_order=(
                            response_order_by_key[key]
                            if checkpoint
                            is SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER
                            else None
                        ),
                        adapter_metadata=prediction.metadata,
                    )
                )

    capture(
        checkpoint=SnapshotCheckpoint.ZERO_EVIDENCE,
        response_templates=ordered_responses,
        created_at=clock,
        wave_index=None,
    )

    for event in sorted(
        script.onboarding_evidence,
        key=lambda candidate: candidate.sequence,
    ):
        evidence_events.append(event.model_copy(deep=True))
        last_sequence = event.sequence
        clock = max(clock, event.occurred_at)

    clock += timedelta(seconds=1)
    capture(
        checkpoint=SnapshotCheckpoint.POST_ONBOARDING,
        response_templates=ordered_responses,
        created_at=clock,
        wave_index=None,
    )

    for response_order, template in enumerate(ordered_responses):
        wave_index = response_order // script.wave_size
        clock += timedelta(seconds=1)
        capture(
            checkpoint=SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER,
            response_templates=[template],
            created_at=clock,
            wave_index=wave_index,
        )

        key = (template.measure_id, template.measure_version)
        measure = measure_by_key[key]
        presentation = presentation_by_key[key]
        last_sequence += 1
        clock += timedelta(seconds=1)
        response = _build_response(
            template=template,
            measure=measure,
            session_id=script.session_id,
            presentation_id=presentation.presentation_id,
            response_id=f"response_{response_order + 1}_{measure.measure_id}",
            sequence=last_sequence,
            created_at=clock,
        )
        validate_response_for_measure(response, measure)
        participant_responses.append(response)

        last_sequence += 1
        clock += timedelta(seconds=1)
        evidence_events.append(
            _response_evidence(
                response=response,
                template=template,
                event_id=f"evidence_{response_order + 1}_{measure.measure_id}",
                sequence=last_sequence,
                occurred_at=clock,
            )
        )

        completed_wave = (response_order + 1) % script.wave_size == 0
        remaining = ordered_responses[response_order + 1 :]
        if completed_wave and remaining:
            clock += timedelta(seconds=1)
            capture(
                checkpoint=SnapshotCheckpoint.POST_WAVE,
                response_templates=remaining,
                created_at=clock,
                wave_index=wave_index,
            )

    run = EvaluationRun(
        run_id=script.run_id,
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        session_id=script.session_id,
        created_at=script.started_at,
        model_configurations=configurations,
        measure_presentations=presentations,
        evidence_events=evidence_events,
        prediction_snapshots=snapshots,
        participant_responses=participant_responses,
    )
    validate_run_against_fixture(run, fixture)
    return PrequentialReplay(
        session_script_id=script.script_id,
        session_script_version=script.script_version,
        session_script_sha256=content_sha256(script),
        completed_at=clock,
        run=run,
        snapshot_traces=traces,
    )
