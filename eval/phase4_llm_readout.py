"""Provider-neutral direct-LLM and hybrid Phase 4D prediction readouts.

The provider sees one exact neutral measure, the evidence view allowed by the
configured condition, and no target response. Hybrid arms additionally see a
recomputed option-level summary of an explicit preference posterior. The
expanding hybrid receives only active participant-admitted dimensions; retired
ontology history remains audit provenance.

This module ships a deterministic backend for boundary tests, not a benchmark
model or live provider adapter. Provider responses are content-addressed and
converted through the same deterministic rich-ballot policy as the classical
baselines.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

import numpy as np
from pydantic import Field, field_validator, model_validator

from preferences.model.common import flat_to_sigma
from preferences.types import Evidence, EvidenceSource, PreferenceState

from .contracts import (
    ContractModel,
    EvaluationFixture,
    MeasurePresentation,
    MeasureVersion,
    NonEmptyText,
    PositiveVersion,
    Probability,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_classical_readout import (
    ClassicalModelArtifact,
    Phase4BallotActionPolicy,
    ballot_prediction_from_probabilities,
    classical_model_artifact_reference,
    normalized_stance_matrix,
    top_option_id_from_probabilities,
    validate_preference_state,
)
from .phase4_evidence import (
    ConversationEvidenceMessage,
    FixedOntologyEvidenceLedger,
    conversation_messages_sha256,
    materialize_evidence,
    replay_preference_state,
)
from .phase4_interviewer import (
    preference_evidence_sha256,
    preference_state_sha256,
)
from .phase4_ontology import (
    ExpandingOntologyDimensionState,
    ExpandingOntologyLedger,
    active_dimension_states,
    evidence_ledger_identity_sha256,
    replay_expanding_ontology,
    validate_expanding_ontology_ledger,
)
from .phase4_prediction import (
    ComponentArtifactReference,
    Phase4ModelConfiguration,
    PredictionCheckpoint,
    PredictionInputBinding,
    PredictionSnapshotV2,
    PredictionUnsupportedAssumption,
    active_ontology_input_sha256,
    materialized_evidence_sha256,
    prediction_model_input_components_sha256,
    prediction_model_input_sha256,
    validate_prediction_v2_for_measure,
)
from .phase4_protocol import (
    EvidenceCondition,
    Phase4Protocol,
    PredictionReadout,
)
from .phase4_semantic import (
    AuthoredMeasureSemanticMapping,
    AuthoredSemanticMapBundle,
    semantic_map_artifact_reference,
    semantic_mapping_for_measure,
    validate_authored_semantic_map,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]


class LLMProviderModelArtifact(ContractModel):
    """Versioned identity of one provider adapter and hosted model."""

    record_version: Literal["phase4_llm_provider_model.v1"] = (
        "phase4_llm_provider_model.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    backend_id: StableId
    backend_version: PositiveVersion
    model_id: StableId
    model_version: NonEmptyText
    implementation_version: PositiveVersion
    structured_output_required: Literal[True] = True


class LLMReadoutPromptArtifact(ContractModel):
    """Exact provider-neutral instruction text used for one readout call."""

    record_version: Literal["phase4_llm_readout_prompt.v1"] = (
        "phase4_llm_readout_prompt.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    system_instruction: NonEmptyText
    participant_identity_cues_forbidden: Literal[True] = True
    target_response_must_be_hidden: Literal[True] = True
    full_option_probabilities_required: Literal[True] = True
    unsupported_assumptions_must_be_flagged: Literal[True] = True


class LLMReadoutPolicy(ContractModel):
    """Versioned LLM-output handling; final values freeze in Phase 4E."""

    record_version: Literal["phase4_llm_readout_policy.v1"] = (
        "phase4_llm_readout_policy.v1"
    )
    artifact_id: StableId
    artifact_version: PositiveVersion
    response_schema: Literal["full_probabilities_with_audit_flags_v1"] = (
        "full_probabilities_with_audit_flags_v1"
    )
    settledness_rule: Literal["provider_reported_probability"] = (
        "provider_reported_probability"
    )
    action_policy: Phase4BallotActionPolicy = Field(
        default_factory=Phase4BallotActionPolicy
    )


def _artifact_reference(
    artifact: LLMProviderModelArtifact
    | LLMReadoutPromptArtifact
    | LLMReadoutPolicy,
) -> ComponentArtifactReference:
    return ComponentArtifactReference(
        artifact_id=artifact.artifact_id,
        artifact_version=str(artifact.artifact_version),
        artifact_sha256=content_sha256(artifact),
    )


def llm_provider_artifact_reference(
    artifact: LLMProviderModelArtifact,
) -> ComponentArtifactReference:
    return _artifact_reference(artifact)


def llm_prompt_artifact_reference(
    artifact: LLMReadoutPromptArtifact,
) -> ComponentArtifactReference:
    return _artifact_reference(artifact)


def llm_readout_artifact_reference(
    artifact: LLMReadoutPolicy,
) -> ComponentArtifactReference:
    return _artifact_reference(artifact)


class LLMReadoutEvidence(ContractModel):
    """Decision-relevant view of one exact materialized evidence event."""

    record_version: Literal["phase4_llm_readout_evidence.v1"] = (
        "phase4_llm_readout_evidence.v1"
    )
    evidence_event_id: StableId
    evidence_sha256: Sha256Digest
    source: EvidenceSource
    item_a: StableId
    item_b: StableId
    value: Annotated[float, Field(ge=-10.0, le=10.0, allow_inf_nan=False)]
    confidence: Probability
    prompt_id: NonEmptyText | None = None
    extracted_claims: list[NonEmptyText] = Field(default_factory=list)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def evidence_pair_must_be_canonical(self) -> Self:
        if self.item_a >= self.item_b:
            raise ValueError("LLM evidence items must be canonical")
        return self


def _readout_evidence(evidence: Evidence) -> LLMReadoutEvidence:
    if evidence.event_id is None:
        raise ValueError("LLM evidence is missing a durable event id")
    if evidence.timestamp is None:
        raise ValueError("LLM evidence is missing its timestamp")
    occurred_at = datetime.fromisoformat(
        evidence.timestamp.replace("Z", "+00:00")
    )
    return LLMReadoutEvidence(
        evidence_event_id=evidence.event_id,
        evidence_sha256=preference_evidence_sha256(evidence),
        source=evidence.source,
        item_a=evidence.item_a,
        item_b=evidence.item_b,
        value=evidence.value,
        confidence=evidence.confidence,
        prompt_id=evidence.prompt_id,
        extracted_claims=list(evidence.extracted_claims),
        occurred_at=occurred_at,
    )


class PosteriorOptionSummary(ContractModel):
    record_version: Literal["phase4_posterior_option_summary.v1"] = (
        "phase4_posterior_option_summary.v1"
    )
    option_id: StableId
    mean_utility: FiniteFloat
    utility_standard_deviation: NonNegativeFiniteFloat


class PosteriorPairwiseSummary(ContractModel):
    """Decision-relevant marginal for one frozen-order option pair."""

    record_version: Literal["phase4_posterior_pairwise_summary.v1"] = (
        "phase4_posterior_pairwise_summary.v1"
    )
    first_option_id: StableId
    second_option_id: StableId
    mean_utility_difference: FiniteFloat
    difference_standard_deviation: NonNegativeFiniteFloat
    first_exceeds_second_probability: Probability

    @model_validator(mode="after")
    def options_must_be_distinct(self) -> Self:
        if self.first_option_id == self.second_option_id:
            raise ValueError("posterior pairwise options must be distinct")
        return self


class ExplicitPosteriorReadoutContext(ContractModel):
    """Compact exact projection of one explicit posterior into option space."""

    record_version: Literal["phase4_explicit_posterior_context.v1"] = (
        "phase4_explicit_posterior_context.v1"
    )
    preference_state_sha256: Sha256Digest
    model_version: NonEmptyText
    fixed_item_ids: list[StableId] = Field(min_length=2)
    semantic_mapping_sha256: Sha256Digest
    option_summaries: list[PosteriorOptionSummary] = Field(min_length=2)
    pairwise_summaries: list[PosteriorPairwiseSummary] = Field(min_length=1)
    active_ontology_sha256: Sha256Digest
    active_expanded_dimensions: list[ExpandingOntologyDimensionState] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if self.fixed_item_ids != sorted(self.fixed_item_ids):
            raise ValueError("posterior fixed item ids must use canonical order")
        if len(self.fixed_item_ids) != len(set(self.fixed_item_ids)):
            raise ValueError("posterior fixed item ids must be unique")
        option_ids = [item.option_id for item in self.option_summaries]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("posterior option summary ids must be unique")
        expected_pairs = [
            (option_ids[left], option_ids[right])
            for left in range(len(option_ids))
            for right in range(left + 1, len(option_ids))
        ]
        actual_pairs = [
            (item.first_option_id, item.second_option_id)
            for item in self.pairwise_summaries
        ]
        if actual_pairs != expected_pairs:
            raise ValueError(
                "posterior pairwise summaries must cover frozen option pairs"
            )
        expansion_ids = [
            item.dimension.dimension_id
            for item in self.active_expanded_dimensions
        ]
        if expansion_ids != sorted(expansion_ids):
            raise ValueError("expanded posterior dimensions must be canonical")
        expected_hash = active_ontology_input_sha256(
            self.fixed_item_ids,
            self.active_expanded_dimensions,
        )
        if self.active_ontology_sha256 != expected_hash:
            raise ValueError("posterior active ontology hash does not match")
        return self


class LLMReadoutRequest(ContractModel):
    """Complete private provider input, excluding the participant response."""

    record_version: Literal["phase4_llm_readout_request.v1"] = (
        "phase4_llm_readout_request.v1"
    )
    readout_kind: Literal["direct_llm", "llm_plus_explicit_posterior"]
    session_id: StableId
    target_measure: MeasureVersion
    target_packet_sha256: Sha256Digest
    evidence_condition: EvidenceCondition
    evidence_cutoff_sequence: Annotated[int, Field(ge=0)]
    eligible_evidence: list[LLMReadoutEvidence] = Field(default_factory=list)
    eligible_evidence_sha256: Sha256Digest
    conversation_messages: list[ConversationEvidenceMessage] = Field(
        default_factory=list
    )
    conversation_messages_sha256: Sha256Digest
    posterior: ExplicitPosteriorReadoutContext | None = None
    model_input_sha256: Sha256Digest
    preference_model: ComponentArtifactReference | None = None
    semantic_mapper: ComponentArtifactReference | None = None
    prediction_readout: ComponentArtifactReference
    provider_model: ComponentArtifactReference
    prompt: ComponentArtifactReference
    seed: Annotated[int, Field(ge=0)]
    target_packet_visible: Literal[True] = True
    target_response_visible: Literal[False] = False

    @model_validator(mode="after")
    def validate_exact_inputs(self) -> Self:
        if self.target_packet_sha256 != content_sha256(
            self.target_measure.packet
        ):
            raise ValueError("LLM request target packet hash does not match")
        evidence_ids = [
            item.evidence_event_id for item in self.eligible_evidence
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("LLM request evidence ids must be unique")
        if self.eligible_evidence_sha256 != content_sha256(
            [item.evidence_sha256 for item in self.eligible_evidence]
        ):
            raise ValueError("LLM request evidence hash does not match")
        message_ids = [
            item.message_id for item in self.conversation_messages
        ]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("LLM request message ids must be unique")
        expected_message_hash = (
            conversation_messages_sha256(self.conversation_messages)
            if self.conversation_messages
            else content_sha256([])
        )
        if self.conversation_messages_sha256 != expected_message_hash:
            raise ValueError("LLM request conversation hash does not match")
        if (
            self.evidence_condition is EvidenceCondition.STRUCTURED_ONLY
            and self.conversation_messages
        ):
            raise ValueError("structured-only LLM request cannot include messages")

        if self.readout_kind == "direct_llm":
            if any(
                value is not None
                for value in (
                    self.posterior,
                    self.preference_model,
                    self.semantic_mapper,
                )
            ):
                raise ValueError("direct LLM request cannot include posterior inputs")
        else:
            if (
                self.posterior is None
                or self.preference_model is None
                or self.semantic_mapper is None
            ):
                raise ValueError("hybrid LLM request requires posterior inputs")
            option_ids = [
                option.option_id for option in self.target_measure.options
            ]
            if [
                item.option_id for item in self.posterior.option_summaries
            ] != option_ids:
                raise ValueError(
                    "posterior summaries must follow target option order"
                )
        expected_model_input_hash = prediction_model_input_components_sha256(
            target_measure_id=self.target_measure.measure_id,
            target_measure_version=self.target_measure.version,
            target_packet_version=self.target_measure.packet.version,
            target_packet_sha256=self.target_packet_sha256,
            evidence_condition=self.evidence_condition,
            evidence_cutoff_sequence=self.evidence_cutoff_sequence,
            eligible_evidence_sha256=self.eligible_evidence_sha256,
            conversation_messages_sha256=self.conversation_messages_sha256,
            preference_state_sha256=(
                self.posterior.preference_state_sha256
                if self.posterior is not None
                else None
            ),
            active_ontology_sha256=(
                self.posterior.active_ontology_sha256
                if self.posterior is not None
                else None
            ),
            preference_model=self.preference_model,
            semantic_mapper=self.semantic_mapper,
            prediction_readout=self.prediction_readout,
            provider_model=self.provider_model,
            prompt=self.prompt,
            seed=self.seed,
        )
        if self.model_input_sha256 != expected_model_input_hash:
            raise ValueError("LLM request model input hash does not match")
        return self


class LLMReadoutResponseDraft(ContractModel):
    """Structured provider output before snapshot and ballot audit fields."""

    record_version: Literal["phase4_llm_readout_response.v1"] = (
        "phase4_llm_readout_response.v1"
    )
    option_probabilities: dict[StableId, Probability] = Field(min_length=2)
    settled_probability: Probability
    supporting_evidence_event_ids: list[StableId] = Field(default_factory=list)
    unsupported_assumptions: list[PredictionUnsupportedAssumption] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if not math.isclose(
            sum(self.option_probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("LLM option probabilities must sum to one")
        if len(self.supporting_evidence_event_ids) != len(
            set(self.supporting_evidence_event_ids)
        ):
            raise ValueError("LLM supporting evidence ids must be unique")
        assumption_ids = [
            item.assumption_id for item in self.unsupported_assumptions
        ]
        if len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("LLM unsupported assumption ids must be unique")
        return self


def _validate_response_for_request(
    response: LLMReadoutResponseDraft,
    request: LLMReadoutRequest,
) -> None:
    option_ids = {
        option.option_id for option in request.target_measure.options
    }
    if set(response.option_probabilities) != option_ids:
        raise ValueError("LLM response must cover every target option exactly")
    eligible_ids = {
        item.evidence_event_id for item in request.eligible_evidence
    }
    if not set(response.supporting_evidence_event_ids) <= eligible_ids:
        raise ValueError("LLM response cites ineligible evidence")
    if eligible_ids and not response.supporting_evidence_event_ids:
        raise ValueError("LLM response must cite eligible supporting evidence")
    for assumption in response.unsupported_assumptions:
        if not set(assumption.affected_option_ids) <= option_ids:
            raise ValueError("LLM response assumption names an unknown option")


class CachedLLMReadoutOutput(ContractModel):
    record_version: Literal["phase4_cached_llm_readout.v1"] = (
        "phase4_cached_llm_readout.v1"
    )
    request_sha256: Sha256Digest
    provider_model_sha256: Sha256Digest
    prompt_sha256: Sha256Digest
    response: LLMReadoutResponseDraft
    response_sha256: Sha256Digest

    @model_validator(mode="after")
    def response_hash_must_match(self) -> Self:
        if self.response_sha256 != content_sha256(self.response):
            raise ValueError("cached LLM response hash does not match")
        return self


class LLMReadoutBackend(Protocol):
    provider_model: LLMProviderModelArtifact
    prompt: LLMReadoutPromptArtifact

    def predict(self, request: LLMReadoutRequest) -> LLMReadoutResponseDraft: ...


class LLMReadoutCache(Protocol):
    def get(self, key: str) -> CachedLLMReadoutOutput | None: ...

    def put(self, key: str, output: CachedLLMReadoutOutput) -> None: ...


class InMemoryLLMReadoutCache:
    def __init__(self) -> None:
        self._outputs: dict[str, CachedLLMReadoutOutput] = {}

    def get(self, key: str) -> CachedLLMReadoutOutput | None:
        return self._outputs.get(key)

    def put(self, key: str, output: CachedLLMReadoutOutput) -> None:
        existing = self._outputs.get(key)
        if existing is not None and existing != output:
            raise ValueError("LLM readout cache key already binds another output")
        self._outputs[key] = output


class JsonDirectoryLLMReadoutCache:
    """Private content-addressed response cache without provider inputs."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(
            character not in "0123456789abcdef" for character in key
        ):
            raise ValueError("LLM readout cache key must be a SHA-256 digest")
        return self._directory / f"{key}.json"

    def get(self, key: str) -> CachedLLMReadoutOutput | None:
        path = self._path(key)
        if not path.exists():
            return None
        return CachedLLMReadoutOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def put(self, key: str, output: CachedLLMReadoutOutput) -> None:
        path = self._path(key)
        if path.exists():
            existing = CachedLLMReadoutOutput.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if existing != output:
                raise ValueError(
                    "LLM readout cache key already binds another output"
                )
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                output.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


class DeterministicLLMReadoutBackend:
    """Stable test double for the provider boundary, not an evaluated arm."""

    def __init__(
        self,
        provider_model: LLMProviderModelArtifact,
        prompt: LLMReadoutPromptArtifact,
    ) -> None:
        self.provider_model = provider_model
        self.prompt = prompt
        self.call_count = 0
        self.requests: list[LLMReadoutRequest] = []

    @staticmethod
    def _unit_interval(payload: object) -> float:
        prefix = content_sha256(payload)[:16]
        return int(prefix, 16) / float(16**16 - 1)

    def predict(self, request: LLMReadoutRequest) -> LLMReadoutResponseDraft:
        self.call_count += 1
        self.requests.append(request.model_copy(deep=True))
        posterior_means = (
            {
                item.option_id: item.mean_utility
                for item in request.posterior.option_summaries
            }
            if request.posterior is not None
            else {}
        )
        expansions = (
            request.posterior.active_expanded_dimensions
            if request.posterior is not None
            else []
        )
        logits: dict[str, float] = {}
        for option in request.target_measure.options:
            base = self._unit_interval(
                {
                    "model_input_sha256": request.model_input_sha256,
                    "option_id": option.option_id,
                    "seed": request.seed,
                }
            ) - 0.5
            expansion_shift = sum(
                (
                    self._unit_interval(
                        {
                            "dimension": item.dimension.model_dump(mode="json"),
                            "option_id": option.option_id,
                            "seed": request.seed,
                        }
                    )
                    - 0.5
                )
                * (item.shrinkage_weight or 0.0)
                for item in expansions
            )
            logits[option.option_id] = (
                0.25 * base
                + posterior_means.get(option.option_id, 0.0)
                + 0.25 * expansion_shift
            )
        maximum = max(logits.values())
        exponentials = {
            option_id: math.exp(value - maximum)
            for option_id, value in logits.items()
        }
        denominator = sum(exponentials.values())
        probabilities = {
            option_id: value / denominator
            for option_id, value in exponentials.items()
        }
        return LLMReadoutResponseDraft(
            option_probabilities=probabilities,
            settled_probability=max(probabilities.values()),
            supporting_evidence_event_ids=[
                item.evidence_event_id for item in request.eligible_evidence
            ],
        )


class LLMReadoutExecutor:
    """Validate, cache, and execute one exact provider request."""

    def __init__(
        self,
        *,
        backend: LLMReadoutBackend,
        cache: LLMReadoutCache,
    ) -> None:
        self._backend = backend
        self._cache = cache

    def run(
        self,
        request: LLMReadoutRequest,
        *,
        require_cache_hit: bool = False,
    ) -> LLMReadoutResponseDraft:
        request = LLMReadoutRequest.model_validate(
            request.model_dump(mode="json")
        )
        provider_reference = llm_provider_artifact_reference(
            self._backend.provider_model
        )
        prompt_reference = llm_prompt_artifact_reference(self._backend.prompt)
        if request.provider_model != provider_reference:
            raise ValueError("LLM request does not match backend provider model")
        if request.prompt != prompt_reference:
            raise ValueError("LLM request does not match backend prompt")

        request_hash = content_sha256(request)
        cached = self._cache.get(request_hash)
        if cached is None:
            if require_cache_hit:
                raise ValueError(
                    "LLM validation requires an existing cached response"
                )
            backend_response = self._backend.predict(
                request.model_copy(deep=True)
            )
            response = LLMReadoutResponseDraft.model_validate(
                backend_response.model_dump(mode="json")
            )
            _validate_response_for_request(response, request)
            cached = CachedLLMReadoutOutput(
                request_sha256=request_hash,
                provider_model_sha256=provider_reference.artifact_sha256,
                prompt_sha256=prompt_reference.artifact_sha256,
                response=response,
                response_sha256=content_sha256(response),
            )
            self._cache.put(request_hash, cached)
        else:
            cached = CachedLLMReadoutOutput.model_validate(
                cached.model_dump(mode="json")
            )
            if cached.request_sha256 != request_hash:
                raise ValueError("cached LLM request hash does not match key")
            if cached.provider_model_sha256 != provider_reference.artifact_sha256:
                raise ValueError("cached LLM provider hash does not match")
            if cached.prompt_sha256 != prompt_reference.artifact_sha256:
                raise ValueError("cached LLM prompt hash does not match")
            _validate_response_for_request(cached.response, request)
        return cached.response.model_copy(deep=True)


def _validate_target(
    *,
    fixture: EvaluationFixture,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    created_at: datetime,
) -> None:
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
        raise ValueError("LLM target is not the exact fixture measure")
    if (
        presentation.session_id != evidence_ledger.session_id
        or presentation.measure_id != measure.measure_id
        or presentation.measure_version != measure.version
        or presentation.packet_version != measure.packet.version
    ):
        raise ValueError("LLM target presentation does not match")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("LLM prediction time must include a timezone")
    if created_at < presentation.presented_at:
        raise ValueError("LLM prediction cannot predate target presentation")


def _validate_configuration(
    *,
    configuration: Phase4ModelConfiguration,
    protocol: Phase4Protocol,
    readout_policy: LLMReadoutPolicy,
    provider_model: LLMProviderModelArtifact,
    prompt: LLMReadoutPromptArtifact,
    model_artifact: ClassicalModelArtifact | None,
    semantic_map: AuthoredSemanticMapBundle | None,
    expansion_ledger: ExpandingOntologyLedger | None,
) -> Literal["direct_llm", "llm_plus_explicit_posterior"]:
    arm = next(
        (
            item
            for item in protocol.comparison.model_arms
            if item.arm_id == configuration.arm_id
        ),
        None,
    )
    if arm is None:
        raise ValueError("LLM configuration uses an unknown arm")
    if configuration.evidence_condition not in arm.evidence_conditions:
        raise ValueError("LLM configuration uses an ineligible evidence condition")
    if configuration.prediction_readout != llm_readout_artifact_reference(
        readout_policy
    ):
        raise ValueError("LLM configuration does not bind the exact readout")
    if configuration.provider_model != llm_provider_artifact_reference(
        provider_model
    ):
        raise ValueError("LLM configuration does not bind the exact provider")
    if configuration.prompt != llm_prompt_artifact_reference(prompt):
        raise ValueError("LLM configuration does not bind the exact prompt")

    if arm.prediction_readout is PredictionReadout.DIRECT_LLM:
        if configuration.arm_id != "direct_llm_control":
            raise ValueError("direct LLM readout must use the control arm")
        if any(
            value is not None
            for value in (
                configuration.preference_model,
                configuration.semantic_mapper,
                model_artifact,
                semantic_map,
                expansion_ledger,
            )
        ):
            raise ValueError("direct LLM control cannot consume posterior inputs")
        return "direct_llm"

    if arm.prediction_readout is not PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR:
        raise ValueError("configuration is not an LLM prediction arm")
    if model_artifact is None or semantic_map is None:
        raise ValueError("hybrid readout requires model and semantic artifacts")
    if configuration.preference_model != classical_model_artifact_reference(
        model_artifact
    ):
        raise ValueError("hybrid configuration does not bind the exact model")
    if configuration.semantic_mapper != semantic_map_artifact_reference(
        semantic_map
    ):
        raise ValueError("hybrid configuration does not bind the exact mapper")
    if configuration.arm_id == "hybrid_fixed_ontology":
        if expansion_ledger is not None:
            raise ValueError("fixed hybrid cannot consume an expansion ledger")
    elif configuration.arm_id == "hybrid_expanding_ontology":
        if expansion_ledger is None:
            raise ValueError("expanding hybrid requires its ontology ledger")
        if expansion_ledger.evidence_condition is not configuration.evidence_condition:
            raise ValueError("expanding ontology evidence condition does not match")
    else:
        raise ValueError("hybrid readout must use a frozen hybrid arm")
    return "llm_plus_explicit_posterior"


def _posterior_summaries(
    state: PreferenceState,
    mapping: AuthoredMeasureSemanticMapping,
) -> tuple[list[PosteriorOptionSummary], list[PosteriorPairwiseSummary]]:
    stance_matrix = normalized_stance_matrix(mapping, list(state.item_ids))
    means = stance_matrix @ np.asarray(state.mu, dtype=float)
    covariance = flat_to_sigma(state.sigma_flat, len(state.item_ids))
    option_covariance = stance_matrix @ covariance @ stance_matrix.T
    option_summaries = [
        PosteriorOptionSummary(
            option_id=stance.option_id,
            mean_utility=float(means[index]),
            utility_standard_deviation=math.sqrt(
                max(float(option_covariance[index, index]), 0.0)
            ),
        )
        for index, stance in enumerate(mapping.option_stances)
    ]
    pairwise_summaries: list[PosteriorPairwiseSummary] = []
    for left in range(len(mapping.option_stances)):
        for right in range(left + 1, len(mapping.option_stances)):
            mean_difference = float(means[left] - means[right])
            difference_variance = float(
                option_covariance[left, left]
                + option_covariance[right, right]
                - 2.0 * option_covariance[left, right]
            )
            standard_deviation = math.sqrt(max(difference_variance, 0.0))
            if standard_deviation == 0.0:
                if mean_difference > 0.0:
                    probability = 1.0
                elif mean_difference < 0.0:
                    probability = 0.0
                else:
                    probability = 0.5
            else:
                probability = 0.5 * (
                    1.0
                    + math.erf(
                        mean_difference
                        / (standard_deviation * math.sqrt(2.0))
                    )
                )
            pairwise_summaries.append(
                PosteriorPairwiseSummary(
                    first_option_id=(
                        mapping.option_stances[left].option_id
                    ),
                    second_option_id=(
                        mapping.option_stances[right].option_id
                    ),
                    mean_utility_difference=mean_difference,
                    difference_standard_deviation=standard_deviation,
                    first_exceeds_second_probability=probability,
                )
            )
    return option_summaries, pairwise_summaries


def _eligible_inputs(
    *,
    ledger: FixedOntologyEvidenceLedger,
    condition: EvidenceCondition,
    cutoff_sequence: int,
    presentation: MeasurePresentation,
) -> tuple[
    list[Evidence],
    list[LLMReadoutEvidence],
    list[ConversationEvidenceMessage],
]:
    evidence = materialize_evidence(
        ledger,
        condition=condition,
        cutoff_sequence=cutoff_sequence,
    )
    readout_evidence = [_readout_evidence(item) for item in evidence]
    messages = (
        []
        if condition is EvidenceCondition.STRUCTURED_ONLY
        else sorted(
            (
                item
                for item in ledger.messages
                if item.sequence <= cutoff_sequence
            ),
            key=lambda item: item.sequence,
        )
    )
    if any(
        item.occurred_at > presentation.presented_at
        for item in readout_evidence
    ):
        raise ValueError("LLM evidence includes a post-exposure event")
    if any(item.created_at > presentation.presented_at for item in messages):
        raise ValueError("LLM conversation includes a post-exposure message")
    return evidence, readout_evidence, messages


def _build_llm_prediction_snapshot(
    *,
    snapshot_id: str,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: Phase4ModelConfiguration,
    readout_policy: LLMReadoutPolicy,
    provider_model: LLMProviderModelArtifact,
    prompt: LLMReadoutPromptArtifact,
    executor: LLMReadoutExecutor,
    evidence_cutoff_sequence: int,
    checkpoint: PredictionCheckpoint,
    wave_index: int | None,
    created_at: datetime,
    model_artifact: ClassicalModelArtifact | None = None,
    semantic_map: AuthoredSemanticMapBundle | None = None,
    expansion_ledger: ExpandingOntologyLedger | None = None,
    require_cached_response: bool = False,
) -> PredictionSnapshotV2:
    _validate_target(
        fixture=fixture,
        measure=measure,
        presentation=presentation,
        evidence_ledger=evidence_ledger,
        created_at=created_at,
    )
    readout_kind = _validate_configuration(
        configuration=configuration,
        protocol=protocol,
        readout_policy=readout_policy,
        provider_model=provider_model,
        prompt=prompt,
        model_artifact=model_artifact,
        semantic_map=semantic_map,
        expansion_ledger=expansion_ledger,
    )
    condition = configuration.evidence_condition
    if condition is None:
        raise ValueError("LLM readout requires an evidence condition")
    evidence, readout_evidence, messages = _eligible_inputs(
        ledger=evidence_ledger,
        condition=condition,
        cutoff_sequence=evidence_cutoff_sequence,
        presentation=presentation,
    )

    posterior: ExplicitPosteriorReadoutContext | None = None
    preference_state_hash: str | None = None
    ontology_snapshot_hash: str | None = None
    active_ontology_hash: str | None = None
    if readout_kind == "llm_plus_explicit_posterior":
        if model_artifact is None or semantic_map is None:
            raise ValueError("hybrid readout artifacts are missing")
        validate_authored_semantic_map(
            semantic_map,
            fixture,
            evidence_ledger.ontology,
        )
        mapping = semantic_mapping_for_measure(
            semantic_map,
            measure.measure_id,
            measure.version,
        )
        state = replay_preference_state(
            model=model_artifact.instantiate(),
            ledger=evidence_ledger,
            condition=condition,
            cutoff_sequence=evidence_cutoff_sequence,
            user_id=evidence_ledger.session_id,
        )
        validate_preference_state(
            state,
            evidence_ledger.ontology.item_ids,
            model_artifact.model_version,
        )
        preference_state_hash = preference_state_sha256(state)
        active_expansions: list[ExpandingOntologyDimensionState] = []
        if expansion_ledger is None:
            ontology_snapshot_hash = content_sha256(evidence_ledger.ontology)
        else:
            validate_expanding_ontology_ledger(
                expansion_ledger,
                evidence_ledger,
            )
            seed_ids = [
                item.dimension_id for item in expansion_ledger.seed.dimensions
            ]
            if seed_ids != evidence_ledger.ontology.item_ids:
                raise ValueError("expanding ontology seed does not match fixed items")
            ontology_snapshot = replay_expanding_ontology(
                expansion_ledger,
                evidence_ledger,
                cutoff_sequence=evidence_cutoff_sequence,
            )
            ontology_snapshot_hash = content_sha256(ontology_snapshot)
            active_expansions = sorted(
                (
                    item
                    for item in active_dimension_states(ontology_snapshot)
                    if not item.is_seed
                ),
                key=lambda item: item.dimension.dimension_id,
            )
        active_ontology_hash = active_ontology_input_sha256(
            evidence_ledger.ontology.item_ids,
            active_expansions,
        )
        option_summaries, pairwise_summaries = _posterior_summaries(
            state,
            mapping,
        )
        posterior = ExplicitPosteriorReadoutContext(
            preference_state_sha256=preference_state_hash,
            model_version=state.model_version,
            fixed_item_ids=list(state.item_ids),
            semantic_mapping_sha256=content_sha256(mapping),
            option_summaries=option_summaries,
            pairwise_summaries=pairwise_summaries,
            active_ontology_sha256=active_ontology_hash,
            active_expanded_dimensions=active_expansions,
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
        evidence_condition=condition,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        eligible_evidence_event_ids=[
            item.evidence_event_id for item in readout_evidence
        ],
        eligible_evidence_sha256=materialized_evidence_sha256(evidence),
        conversation_message_ids=[item.message_id for item in messages],
        conversation_messages_sha256=(
            conversation_messages_sha256(messages)
            if messages
            else content_sha256([])
        ),
        preference_state_sha256=preference_state_hash,
        ontology_snapshot_sha256=ontology_snapshot_hash,
        active_ontology_sha256=active_ontology_hash,
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
    request = LLMReadoutRequest(
        readout_kind=readout_kind,
        session_id=evidence_ledger.session_id,
        target_measure=measure,
        target_packet_sha256=binding.target_packet_sha256,
        evidence_condition=condition,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        eligible_evidence=readout_evidence,
        eligible_evidence_sha256=binding.eligible_evidence_sha256,
        conversation_messages=messages,
        conversation_messages_sha256=binding.conversation_messages_sha256,
        posterior=posterior,
        model_input_sha256=binding.model_input_sha256,
        preference_model=configuration.preference_model,
        semantic_mapper=configuration.semantic_mapper,
        prediction_readout=configuration.prediction_readout,
        provider_model=configuration.provider_model,
        prompt=configuration.prompt,
        seed=configuration.seed,
    )
    response = executor.run(
        request,
        require_cache_hit=require_cached_response,
    )
    provider_request_sha256 = content_sha256(request)
    top_option_id = top_option_id_from_probabilities(
        measure,
        response.option_probabilities,
    )
    snapshot = PredictionSnapshotV2(
        snapshot_id=snapshot_id,
        session_id=evidence_ledger.session_id,
        model_configuration_id=configuration.configuration_id,
        model_configuration_sha256=content_sha256(configuration),
        checkpoint=checkpoint,
        wave_index=wave_index,
        input_binding=binding,
        option_probabilities=response.option_probabilities,
        top_option_id=top_option_id,
        confidence=response.option_probabilities[top_option_id],
        settled_probability=response.settled_probability,
        ballot_prediction=ballot_prediction_from_probabilities(
            measure,
            response.option_probabilities,
            readout_policy.action_policy,
        ),
        provider_request_sha256=provider_request_sha256,
        supporting_evidence_event_ids=(
            response.supporting_evidence_event_ids
        ),
        unsupported_assumptions=response.unsupported_assumptions,
        created_at=created_at,
    )
    validate_prediction_v2_for_measure(snapshot, measure)
    return snapshot


def build_direct_llm_prediction_snapshot(
    *,
    snapshot_id: str,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: Phase4ModelConfiguration,
    readout_policy: LLMReadoutPolicy,
    provider_model: LLMProviderModelArtifact,
    prompt: LLMReadoutPromptArtifact,
    executor: LLMReadoutExecutor,
    evidence_cutoff_sequence: int,
    checkpoint: PredictionCheckpoint,
    wave_index: int | None,
    created_at: datetime,
) -> PredictionSnapshotV2:
    """Build one exact direct-LLM control snapshot."""

    return _build_llm_prediction_snapshot(
        snapshot_id=snapshot_id,
        fixture=fixture,
        protocol=protocol,
        measure=measure,
        presentation=presentation,
        evidence_ledger=evidence_ledger,
        configuration=configuration,
        readout_policy=readout_policy,
        provider_model=provider_model,
        prompt=prompt,
        executor=executor,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        checkpoint=checkpoint,
        wave_index=wave_index,
        created_at=created_at,
    )


def build_hybrid_prediction_snapshot(
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
    readout_policy: LLMReadoutPolicy,
    provider_model: LLMProviderModelArtifact,
    prompt: LLMReadoutPromptArtifact,
    executor: LLMReadoutExecutor,
    evidence_cutoff_sequence: int,
    checkpoint: PredictionCheckpoint,
    wave_index: int | None,
    created_at: datetime,
    expansion_ledger: ExpandingOntologyLedger | None = None,
) -> PredictionSnapshotV2:
    """Build one fixed- or expanding-ontology hybrid snapshot."""

    return _build_llm_prediction_snapshot(
        snapshot_id=snapshot_id,
        fixture=fixture,
        protocol=protocol,
        measure=measure,
        presentation=presentation,
        evidence_ledger=evidence_ledger,
        configuration=configuration,
        readout_policy=readout_policy,
        provider_model=provider_model,
        prompt=prompt,
        executor=executor,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        checkpoint=checkpoint,
        wave_index=wave_index,
        created_at=created_at,
        model_artifact=model_artifact,
        semantic_map=semantic_map,
        expansion_ledger=expansion_ledger,
    )


def validate_llm_prediction_snapshot(
    snapshot: PredictionSnapshotV2,
    *,
    fixture: EvaluationFixture,
    protocol: Phase4Protocol,
    measure: MeasureVersion,
    presentation: MeasurePresentation,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: Phase4ModelConfiguration,
    readout_policy: LLMReadoutPolicy,
    provider_model: LLMProviderModelArtifact,
    prompt: LLMReadoutPromptArtifact,
    executor: LLMReadoutExecutor,
    model_artifact: ClassicalModelArtifact | None = None,
    semantic_map: AuthoredSemanticMapBundle | None = None,
    expansion_ledger: ExpandingOntologyLedger | None = None,
) -> None:
    """Rebuild from the exact cached provider output and compare byte-for-byte."""

    expected = _build_llm_prediction_snapshot(
        snapshot_id=snapshot.snapshot_id,
        fixture=fixture,
        protocol=protocol,
        measure=measure,
        presentation=presentation,
        evidence_ledger=evidence_ledger,
        configuration=configuration,
        readout_policy=readout_policy,
        provider_model=provider_model,
        prompt=prompt,
        executor=executor,
        evidence_cutoff_sequence=(
            snapshot.input_binding.evidence_cutoff_sequence
        ),
        checkpoint=snapshot.checkpoint,
        wave_index=snapshot.wave_index,
        created_at=snapshot.created_at,
        model_artifact=model_artifact,
        semantic_map=semantic_map,
        expansion_ledger=expansion_ledger,
        require_cached_response=True,
    )
    if snapshot != expected:
        raise ValueError("LLM prediction snapshot does not reproduce exactly")
