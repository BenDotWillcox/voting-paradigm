"""No-spend tokenizer readiness and qualification planning for Phase 4E.

This module turns the frozen Together feasibility envelope into exact local
artifacts.  It deliberately has no HTTP client and no provider credential
surface.  The paid runner rebuilds each public-development
request from these same inputs and matches the predeclared payload hash before it
can ask the shared provider runtime to reserve budget.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    JsonValue,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_evidence import EvidenceProposalDraft
from .phase4_interviewer import InterviewerDecision
from .phase4_llm_readout import LLMReadoutResponseDraft
from .phase4_ontology import OntologyDimensionProposalDraft
from .phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderPriceCard,
    build_public_development_attestation,
    prepare_provider_request,
    price_provider_tokens,
    provider_request_content_sha256,
)
from .phase4_robustness import (
    LLMRole,
    NonNegativeCount,
    OpenWeightModelCandidate,
    OptionLabelVariant,
    OptionOrderVariant,
    Phase4ERobustnessProfile,
    PositiveCount,
    RobustnessPerturbationKind,
    RobustnessVariantBinding,
    build_option_label_variant,
    build_option_order_variant,
)
from .phase4_semantic import AuthoredSemanticMapBundle
from .phase4_together import (
    TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT,
    Phase4TogetherSuite,
    SharedRoleContract,
    build_together_chat_payload,
    response_schema_for_role,
    tool_definitions_for_role,
    validate_request_against_role_envelope,
)
from .phase4_together_live import (
    TogetherCandidateTokenProjection,
    TogetherHeadroomPolicy,
    TogetherPayloadTokenCount,
    TogetherTokenReadinessReceipt,
    validate_token_readiness_and_headroom,
)
from .prequential import PrequentialSessionScript


READINESS_CREATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
QUALIFICATION_VARIANT_IDS = (
    "canonical",
    "prompt_paraphrase_1",
    "prompt_paraphrase_2",
    "option_order_1",
    "option_label_1",
    "stochastic_repeat_1",
    "stochastic_repeat_2",
    "stochastic_repeat_3",
)
CONVERSATIONAL_ROLES = {
    LLMRole.INTERVIEWER,
    LLMRole.EVIDENCE_EXTRACTOR,
    LLMRole.ONTOLOGY_PROPOSER,
}
READOUT_ROLES = {LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT}


class ExactTokenCounter(Protocol):
    """Small injectable boundary around one revision-pinned tokenizer."""

    artifact: ExactTokenizerArtifact
    tokenizer_id: str
    tokenizer_version: int
    tokenizer_artifact_sha256: str

    def count(self, text: str) -> int: ...


class QualificationVariant(str, Enum):
    CANONICAL = "canonical"
    PROMPT_PARAPHRASE_1 = "prompt_paraphrase_1"
    PROMPT_PARAPHRASE_2 = "prompt_paraphrase_2"
    OPTION_ORDER_1 = "option_order_1"
    OPTION_LABEL_1 = "option_label_1"
    STOCHASTIC_REPEAT_1 = "stochastic_repeat_1"
    STOCHASTIC_REPEAT_2 = "stochastic_repeat_2"
    STOCHASTIC_REPEAT_3 = "stochastic_repeat_3"


class HeldOutCalibrationKind(str, Enum):
    INITIAL_WAVE = "initial_wave"
    RETEST = "retest"


class TokenizerFileDigest(ContractModel):
    relative_path: NonEmptyText
    byte_count: NonNegativeCount
    sha256: Sha256Digest


class ExactTokenizerArtifact(ContractModel):
    """Content identity of tokenizer files loaded without model weights."""

    record_version: Literal["phase4_exact_tokenizer_artifact.v1"] = (
        "phase4_exact_tokenizer_artifact.v1"
    )
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    upstream_model_id: NonEmptyText
    upstream_model_revision: NonEmptyText
    tokenizer_id: StableId
    tokenizer_version: PositiveVersion
    tokenizer_library: Literal["tokenizers"] = "tokenizers"
    tokenizer_library_version: NonEmptyText
    counting_method: Literal[
        "revision_pinned_tokenizer_on_canonical_http_json"
    ] = "revision_pinned_tokenizer_on_canonical_http_json"
    files: list[TokenizerFileDigest] = Field(min_length=1)
    model_weights_downloaded: Literal[False] = False
    provider_serving_tokenizer_attested: Literal[False] = False

    @model_validator(mode="after")
    def require_canonical_unique_files(self) -> Self:
        paths = [item.relative_path for item in self.files]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("tokenizer files must be unique and canonical")
        if "tokenizer.json" not in paths:
            raise ValueError("exact tokenizer artifact requires tokenizer.json")
        return self


class QualificationCallCoordinate(ContractModel):
    call_id: StableId
    ordinal: PositiveCount
    candidate_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    role: LLMRole
    variant_id: QualificationVariant
    request_seed: Annotated[int, Field(ge=0)]


class QualificationCallPlanEntry(ContractModel):
    """Content-free identity and token proof for one future paid call."""

    record_version: Literal["phase4_qualification_call_plan_entry.v1"] = (
        "phase4_qualification_call_plan_entry.v1"
    )
    coordinate: QualificationCallCoordinate
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    role_contract_sha256: Sha256Digest
    robustness_variant: RobustnessVariantBinding | None = None
    request_template_sha256: Sha256Digest
    rendered_payload_sha256: Sha256Digest
    provider_round_count: PositiveCount
    provider_round_payload_sha256: list[Sha256Digest] = Field(min_length=1)
    input_token_counts_by_round: list[NonNegativeCount] = Field(min_length=1)
    input_token_count: NonNegativeCount
    input_token_upper_bound: PositiveCount
    output_token_upper_bound: PositiveCount
    projected_cost_microusd: NonNegativeCount
    authorized_max_cost_microusd: NonNegativeCount

    @model_validator(mode="after")
    def require_variant_shape_and_envelope(self) -> Self:
        variant = self.coordinate.variant_id
        if variant is QualificationVariant.CANONICAL:
            if self.robustness_variant is not None:
                raise ValueError("canonical call cannot bind a robustness variant")
        elif self.robustness_variant is None:
            raise ValueError("shadow call requires a robustness variant")
        if self.provider_round_count != len(
            self.provider_round_payload_sha256
        ) or self.provider_round_count != len(self.input_token_counts_by_round):
            raise ValueError("qualification provider rounds do not reconcile")
        expected_rounds = (
            TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT
            if self.coordinate.role is LLMRole.INTERVIEWER
            else 1
        )
        if self.provider_round_count != expected_rounds:
            raise ValueError("qualification provider round count differs")
        if self.rendered_payload_sha256 != content_sha256(
            self.provider_round_payload_sha256
        ):
            raise ValueError("qualification provider-round hash differs")
        if self.input_token_count != sum(self.input_token_counts_by_round):
            raise ValueError("qualification round token counts do not reconcile")
        if self.input_token_count > self.input_token_upper_bound:
            raise ValueError("qualification call exceeds its input envelope")
        return self


class TogetherQualificationRequestManifest(ContractModel):
    schema_version: Literal["preference_eval_phase4_qualification_plan.v1"] = (
        "preference_eval_phase4_qualification_plan.v1"
    )
    plan_id: StableId
    plan_version: PositiveVersion
    created_at: datetime
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    public_development_semantic_map_sha256: Sha256Digest
    entries: list[QualificationCallPlanEntry] = Field(min_length=1)
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualification plan created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_canonical_complete_plan(self) -> Self:
        ordinals = [item.coordinate.ordinal for item in self.entries]
        if ordinals != list(range(1, len(self.entries) + 1)):
            raise ValueError("qualification plan ordinals must be contiguous")
        call_ids = [item.coordinate.call_id for item in self.entries]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("qualification plan call ids must be unique")
        if len(self.entries) != 456:
            raise ValueError("qualification plan must contain exactly 456 calls")
        counts = Counter(
            (item.coordinate.candidate_id, item.coordinate.role)
            for item in self.entries
        )
        candidate_ids = sorted(
            {item.coordinate.candidate_id for item in self.entries}
        )
        if len(candidate_ids) != 3:
            raise ValueError("qualification plan must cover three candidates")
        for candidate_id in candidate_ids:
            expected = {
                LLMRole.INTERVIEWER: 8,
                LLMRole.EVIDENCE_EXTRACTOR: 8,
                LLMRole.ONTOLOGY_PROPOSER: 8,
                LLMRole.DIRECT_READOUT: 64,
                LLMRole.HYBRID_READOUT: 64,
            }
            actual = {
                role: counts[(candidate_id, role)] for role in LLMRole
            }
            if actual != expected:
                raise ValueError("qualification plan role counts do not match")
        return self


class HeldOutWaveCalibration(ContractModel):
    """Aggregate exact counts over public synthetic wave-growth payloads."""

    record_version: Literal["phase4_held_out_wave_calibration.v1"] = (
        "phase4_held_out_wave_calibration.v1"
    )
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    price_card_sha256: Sha256Digest
    wave_index: Annotated[int, Field(ge=1, le=7)]
    presentation_kind: HeldOutCalibrationKind
    role: LLMRole
    request_count: PositiveCount
    ordered_payload_sha256: Sha256Digest
    input_token_counts: list[NonNegativeCount] = Field(min_length=1)
    input_token_count: NonNegativeCount
    input_token_upper_bound_per_request: PositiveCount
    maximum_input_tokens_per_request: NonNegativeCount
    output_token_upper_bound_per_request: PositiveCount
    output_token_upper_bound_count: NonNegativeCount
    projected_cost_microusd: NonNegativeCount

    @model_validator(mode="after")
    def require_reconciled_token_counts(self) -> Self:
        if self.presentation_kind is HeldOutCalibrationKind.RETEST:
            if self.wave_index != 7 or self.role not in READOUT_ROLES:
                raise ValueError("retest calibration row has invalid coordinates")
        elif self.wave_index == 7:
            raise ValueError("initial calibration row cannot use retest wave")
        if len(self.input_token_counts) != self.request_count:
            raise ValueError("held-out row token counts do not count requests")
        if sum(self.input_token_counts) != self.input_token_count:
            raise ValueError("held-out row input-token total does not reconcile")
        if max(self.input_token_counts) != self.maximum_input_tokens_per_request:
            raise ValueError("held-out row maximum token count does not reconcile")
        if self.maximum_input_tokens_per_request > (
            self.input_token_upper_bound_per_request
        ):
            raise ValueError("held-out row exceeds its input envelope")
        if self.output_token_upper_bound_count != (
            self.request_count * self.output_token_upper_bound_per_request
        ):
            raise ValueError("held-out row output-token total does not reconcile")
        return self


class TogetherHeldOutCalibrationManifest(ContractModel):
    schema_version: Literal["preference_eval_phase4_held_out_calibration.v1"] = (
        "preference_eval_phase4_held_out_calibration.v1"
    )
    calibration_id: StableId
    calibration_version: PositiveVersion
    created_at: datetime
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    method: Literal[
        "public_synthetic_unbounded_wave_growth_and_retest_tokenization"
    ] = (
        "public_synthetic_unbounded_wave_growth_and_retest_tokenization"
    )
    rows: list[HeldOutWaveCalibration] = Field(min_length=1)
    future_exact_count_required: Literal[True] = True
    over_envelope_action: Literal["pause_without_send"] = "pause_without_send"
    held_out_packet_content_used: Literal[False] = False
    participant_responses_used: Literal[False] = False
    full_accumulated_evidence_included: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("held-out calibration created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_complete_wave_matrix(self) -> Self:
        keys = [
            (
                item.candidate_id,
                item.wave_index,
                item.presentation_kind,
                item.role,
            )
            for item in self.rows
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("held-out calibration rows must be unique")
        candidate_ids = sorted({item.candidate_id for item in self.rows})
        expected_keys = {
            (
                candidate_id,
                wave,
                HeldOutCalibrationKind.INITIAL_WAVE,
                role,
            )
            for candidate_id in candidate_ids
            for wave in range(1, 7)
            for role in LLMRole
        }
        expected_keys.update(
            (
                candidate_id,
                7,
                HeldOutCalibrationKind.RETEST,
                role,
            )
            for candidate_id in candidate_ids
            for role in READOUT_ROLES
        )
        if len(candidate_ids) != 3 or set(keys) != expected_keys:
            raise ValueError("held-out calibration matrix is incomplete")
        for candidate_id in candidate_ids:
            request_count = sum(
                item.request_count
                for item in self.rows
                if item.candidate_id == candidate_id
            )
            if request_count != 1_104:
                raise ValueError("held-out calibration must count 1104 requests")
            for role in LLMRole:
                role_rows = [
                    item
                    for item in sorted(
                        self.rows,
                        key=lambda row: row.wave_index,
                    )
                    if item.candidate_id == candidate_id and item.role is role
                ]
                wave_totals = [item.input_token_count for item in role_rows]
                if any(
                    later <= earlier
                    for earlier, later in zip(wave_totals, wave_totals[1:])
                ):
                    raise ValueError(
                        "held-out wave input totals must strictly increase"
                    )
                if any(
                    later.maximum_input_tokens_per_request
                    <= earlier.maximum_input_tokens_per_request
                    for earlier, later in zip(role_rows, role_rows[1:])
                ):
                    raise ValueError(
                        "held-out per-request maxima must strictly increase"
                    )
        return self


class Phase4TogetherReadinessBundle(ContractModel):
    """Tracked aggregate gate required before any paid authorization."""

    schema_version: Literal["preference_eval_phase4_together_readiness.v1"] = (
        "preference_eval_phase4_together_readiness.v1"
    )
    readiness_id: StableId
    readiness_version: PositiveVersion
    created_at: datetime
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    public_development_fixture_sha256: Sha256Digest
    public_development_session_sha256: Sha256Digest
    public_development_semantic_map_sha256: Sha256Digest
    tokenizer_artifacts: list[ExactTokenizerArtifact]
    qualification_manifest: TogetherQualificationRequestManifest
    held_out_calibration_manifest: TogetherHeldOutCalibrationManifest
    token_readiness_receipt: TogetherTokenReadinessReceipt
    headroom_policy: TogetherHeadroomPolicy
    capability_preflight_call_ids: list[StableId] = Field(min_length=15, max_length=15)
    capability_preflight_call_count: Literal[15] = 15
    exact_qualification_request_count: Literal[456] = 456
    held_out_calibration_request_count: Literal[3312] = 3312
    provider_inference_calls_executed: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0
    together_api_key_required: Literal[False] = False
    provider_billing_token_equivalence_claimed: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("readiness created_at must be timezone-aware")
        return value


class QualificationResumeCursor(ContractModel):
    """Content-free deterministic cursor reconstructed from a journal prefix."""

    record_version: Literal["phase4_qualification_resume_cursor.v1"] = (
        "phase4_qualification_resume_cursor.v1"
    )
    qualification_manifest_sha256: Sha256Digest
    completed_call_ids: list[StableId]
    remaining_call_ids: list[StableId]
    next_call_id: StableId | None = None
    completed_call_count: NonNegativeCount
    remaining_call_count: NonNegativeCount
    provider_calls_executed_by_dry_run: Literal[0] = 0
    provider_spend_microusd_by_dry_run: Literal[0] = 0

    @model_validator(mode="after")
    def require_reconciled_cursor(self) -> Self:
        if self.completed_call_count != len(self.completed_call_ids):
            raise ValueError("qualification cursor completed count differs")
        if self.remaining_call_count != len(self.remaining_call_ids):
            raise ValueError("qualification cursor remaining count differs")
        expected_next = self.remaining_call_ids[0] if self.remaining_call_ids else None
        if self.next_call_id != expected_next:
            raise ValueError("qualification cursor next call differs")
        all_ids = [*self.completed_call_ids, *self.remaining_call_ids]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("qualification cursor call ids must be unique")
        return self


@dataclass(frozen=True)
class LoadedExactTokenizer:
    artifact: ExactTokenizerArtifact
    backend: object

    @property
    def tokenizer_id(self) -> str:
        return self.artifact.tokenizer_id

    @property
    def tokenizer_version(self) -> int:
        return self.artifact.tokenizer_version

    @property
    def tokenizer_artifact_sha256(self) -> str:
        return content_sha256(self.artifact)

    def count(self, text: str) -> int:
        encode = getattr(self.backend, "encode")
        return len(encode(text).ids)


class TogetherExactTokenCounterSet:
    """Adapter from readiness tokenizers to the paid transport boundary."""

    def __init__(self, counters: dict[str, LoadedExactTokenizer]) -> None:
        self._counters = dict(counters)

    def count_payload(
        self,
        candidate_id: str,
        payload: dict[str, JsonValue],
    ) -> TogetherPayloadTokenCount:
        counter = self._counters.get(candidate_id)
        if counter is None:
            raise ValueError("Together token counter candidate is unknown")
        return TogetherPayloadTokenCount(
            candidate_id=candidate_id,
            candidate_sha256=counter.artifact.candidate_sha256,
            tokenizer_id=counter.tokenizer_id,
            tokenizer_version=counter.tokenizer_version,
            tokenizer_artifact_sha256=counter.tokenizer_artifact_sha256,
            payload_sha256=content_sha256(payload),
            input_token_count=counter.count(_canonical_json(payload)),
        )


@dataclass(frozen=True)
class _RequestTemplate:
    candidate: OpenWeightModelCandidate
    price_card: ProviderPriceCard
    role_contract: SharedRoleContract
    measure_id: str
    measure_version: int
    role: LLMRole
    variant_id: QualificationVariant
    prompt_payload: JsonValue
    input_payload: JsonValue
    response_adapter: TypeAdapter[object]
    tool_definitions: list[dict[str, JsonValue]]
    request_seed: int
    output_token_upper_bound: int
    input_token_upper_bound: int
    robustness_variant: RobustnessVariantBinding | None


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _role_response_adapter(role: LLMRole) -> TypeAdapter[object]:
    adapters: dict[LLMRole, TypeAdapter[object]] = {
        LLMRole.INTERVIEWER: TypeAdapter(InterviewerDecision),
        LLMRole.EVIDENCE_EXTRACTOR: TypeAdapter(list[EvidenceProposalDraft]),
        LLMRole.ONTOLOGY_PROPOSER: TypeAdapter(
            list[OntologyDimensionProposalDraft]
        ),
        LLMRole.DIRECT_READOUT: TypeAdapter(LLMReadoutResponseDraft),
        LLMRole.HYBRID_READOUT: TypeAdapter(LLMReadoutResponseDraft),
    }
    return adapters[role]


def _role_usage(suite: Phase4TogetherSuite, role: LLMRole, *, held_out: bool):
    envelope = (
        suite.workload.held_out_selected_candidate
        if held_out
        else suite.workload.qualification_per_candidate
    )
    return {item.role: item for item in envelope.role_usage}[role]


def _history_prefix(
    session: PrequentialSessionScript,
    measure_index: int,
) -> list[dict[str, JsonValue]]:
    history: list[dict[str, JsonValue]] = [
        {
            "source": "public_synthetic_onboarding",
            "event": item.model_dump(mode="json"),
        }
        for item in session.onboarding_evidence
    ]
    history.extend(
        {
            "source": "public_synthetic_measure_response",
            "response": item.model_dump(mode="json"),
        }
        for item in session.responses[:measure_index]
    )
    return history


def _synthetic_posterior(
    semantic_map: AuthoredSemanticMapBundle,
    session: PrequentialSessionScript,
    measure_index: int,
) -> dict[str, JsonValue]:
    sums: defaultdict[str, float] = defaultdict(float)
    counts: Counter[str] = Counter()
    mapping_by_measure = {
        item.measure_id: item for item in semantic_map.mappings
    }
    for response in session.responses[:measure_index]:
        selected = response.selected_option_id
        if selected is None:
            continue
        mapping = mapping_by_measure[response.measure_id]
        stance = next(
            item for item in mapping.option_stances if item.option_id == selected
        )
        for dimension_id, weight in stance.dimension_weights.items():
            sums[dimension_id] += weight
            counts[dimension_id] += 1
    means = {
        dimension_id: sums[dimension_id] / counts[dimension_id]
        for dimension_id in sorted(sums)
    }
    return {
        "record_version": "phase4_public_synthetic_posterior.v1",
        "fixed_dimension_ids": list(semantic_map.ontology.item_ids),
        "observed_dimension_means": means,
        "unobserved_prior_mean": 0.0,
        "source": "public_development_session_only",
    }


def _prompt_paraphrase(role: LLMRole, variant: QualificationVariant) -> str:
    if role is LLMRole.DIRECT_READOUT:
        variants = {
            QualificationVariant.PROMPT_PARAPHRASE_1: (
                "Using only the neutral ballot packet and eligible evidence, "
                "estimate how the participant would vote. Exclude their actual "
                "answer. Return normalized option probabilities, a settledness "
                "estimate, eligible evidence identifiers, and any unsupported "
                "assumptions in the required structured form."
            ),
            QualificationVariant.PROMPT_PARAPHRASE_2: (
                "Return a structured prediction of the participant's ballot from "
                "the neutral packet and condition-eligible evidence alone. Never "
                "use the participant's response. Include normalized probabilities "
                "for every option, settled probability, supporting evidence ids, "
                "and unsupported assumptions."
            ),
        }
    else:
        variants = {
            QualificationVariant.PROMPT_PARAPHRASE_1: (
                "Use the neutral ballot packet, eligible evidence, and supplied "
                "explicit posterior to estimate the participant's vote. Do not "
                "use their actual answer. Return normalized option probabilities, "
                "settledness, eligible evidence identifiers, and unsupported "
                "assumptions in the required structured form."
            ),
            QualificationVariant.PROMPT_PARAPHRASE_2: (
                "Return a structured ballot prediction based solely on the neutral "
                "packet, condition-eligible evidence, and explicit posterior. "
                "Exclude the participant's response. Include probabilities for "
                "every option, settled probability, supporting evidence ids, and "
                "unsupported assumptions."
            ),
        }
    return variants[variant]


def _readout_variant_binding(
    variant: QualificationVariant,
    *,
    role: LLMRole,
    measure_id: str,
    option_ids: list[str],
) -> tuple[
    RobustnessVariantBinding | None,
    OptionOrderVariant | None,
    OptionLabelVariant | None,
]:
    if variant is QualificationVariant.CANONICAL:
        return None, None, None
    seed = _stable_seed(role.value, measure_id, variant.value)
    order: OptionOrderVariant | None = None
    labels: OptionLabelVariant | None = None
    if variant is QualificationVariant.PROMPT_PARAPHRASE_1:
        kind = RobustnessPerturbationKind.PROMPT_PARAPHRASE
        digest = content_sha256(_prompt_paraphrase(role, variant))
        repeat_index = None
        binding_seed = None
    elif variant is QualificationVariant.PROMPT_PARAPHRASE_2:
        kind = RobustnessPerturbationKind.PROMPT_PARAPHRASE
        digest = content_sha256(_prompt_paraphrase(role, variant))
        repeat_index = None
        binding_seed = None
    elif variant is QualificationVariant.OPTION_ORDER_1:
        kind = RobustnessPerturbationKind.OPTION_ORDER
        order = build_option_order_variant(option_ids, seed=seed)
        digest = content_sha256(order)
        repeat_index = None
        binding_seed = seed
    elif variant is QualificationVariant.OPTION_LABEL_1:
        kind = RobustnessPerturbationKind.OPTION_LABEL
        labels = build_option_label_variant(option_ids, seed=seed)
        digest = content_sha256(labels)
        repeat_index = None
        binding_seed = seed
    else:
        kind = RobustnessPerturbationKind.STOCHASTIC_REPEAT
        repeat_index = int(variant.value.rsplit("_", 1)[1])
        digest = content_sha256(
            {"repeat_index": repeat_index, "request_seed": seed}
        )
        binding_seed = seed
    binding = RobustnessVariantBinding(
        variant_id=f"{measure_id}_{role.value}_{variant.value}",
        variant_version=1,
        perturbation_kind=kind,
        variant_sha256=digest,
        seed=binding_seed,
        repeat_index=repeat_index,
    )
    return binding, order, labels


def _role_input_payload(
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    measure_index: int,
    role: LLMRole,
    variant: QualificationVariant,
    held_out_wave_index: int | None,
    held_out_calibration_kind: HeldOutCalibrationKind | None,
) -> JsonValue:
    if (held_out_wave_index is None) != (
        held_out_calibration_kind is None
    ):
        raise ValueError("held-out calibration coordinates must be paired")
    measure = fixture.measures[measure_index % len(fixture.measures)]
    history = _history_prefix(session, measure_index % len(fixture.measures))
    if held_out_wave_index is not None:
        completed_count = (held_out_wave_index - 1) * 8
        calibration_claim = max(
            (
                str(event.raw_response)
                for event in session.onboarding_evidence
            ),
            key=len,
        )
        history = [
            *history,
            *[
                {
                    "source": "public_synthetic_wave_growth",
                    "sequence": index + 1,
                    "claim": calibration_claim,
                    "confirmed": True,
                }
                for index in range(completed_count)
            ],
        ]
        if held_out_calibration_kind is HeldOutCalibrationKind.RETEST:
            history.append(
                {
                    "source": "public_synthetic_original_response_for_retest",
                    "sequence": completed_count + 1,
                    "claim": calibration_claim,
                    "confirmed": True,
                }
            )
    base: dict[str, JsonValue] = {
        "record_version": "phase4_public_development_role_input.v1",
        "session_id": session.session_id,
        "role": role.value,
        "evidence_history": history,
        "target_response_visible": False,
    }
    if held_out_wave_index is not None:
        base["calibration"] = {
            "method": (
                "public_synthetic_unbounded_wave_growth_and_retest_tokenization"
            ),
            "wave_index": held_out_wave_index,
            "presentation_kind": held_out_calibration_kind.value,
            "held_out_packet_content_used": False,
            "participant_response_used": False,
        }
    if role is LLMRole.INTERVIEWER:
        posterior = _synthetic_posterior(
            semantic_map,
            session,
            measure_index % len(fixture.measures),
        )
        base.update(
            {
                "target_packet_visible": False,
                "allowed_actions": [
                    "select_vetted_question",
                    "clarify_linked_evidence",
                    "pause",
                ],
                "posterior_summary": {
                    "record_version": "phase4_interviewer_posterior_summary.v1",
                    "fixed_ontology_sha256": content_sha256(
                        semantic_map.ontology.item_ids
                    ),
                    "observed_dimension_means": posterior[
                        "observed_dimension_means"
                    ],
                    "unobserved_prior_mean": 0.0,
                },
                "eligible_question_item_count": len(
                    semantic_map.ontology.item_ids
                ),
            }
        )
        return base
    if role is LLMRole.EVIDENCE_EXTRACTOR:
        base.update(
            {
                "target_packet_visible": False,
                "participant_messages": [
                    {
                        "message_id": f"public_message_{index + 1}",
                        "text": event.raw_response,
                    }
                    for index, event in enumerate(session.onboarding_evidence)
                ],
                "active_ontology_dimension_ids": list(
                    semantic_map.ontology.item_ids
                ),
                "proposals_receive_model_weight": False,
            }
        )
        return base
    if role is LLMRole.ONTOLOGY_PROPOSER:
        base.update(
            {
                "target_packet_visible": False,
                "confirmed_claims": [
                    claim
                    for event in session.onboarding_evidence
                    for claim in event.normalized_claims
                ],
                "active_ontology_dimension_ids": list(
                    semantic_map.ontology.item_ids
                ),
                "new_dimensions_receive_model_weight": False,
            }
        )
        return base

    target = measure.model_dump(mode="json")
    option_ids = [item.option_id for item in measure.options]
    binding, order, labels = _readout_variant_binding(
        variant,
        role=role,
        measure_id=measure.measure_id,
        option_ids=option_ids,
    )
    if order is not None:
        options_by_id = {item["option_id"]: item for item in target["options"]}
        target["options"] = [options_by_id[item] for item in order.variant_option_ids]
    if labels is not None:
        alias_by_id = {
            item.canonical_option_id: item.provider_alias for item in labels.aliases
        }
        target["provider_option_aliases"] = alias_by_id
        for option in target["options"]:
            option["provider_option_id"] = alias_by_id[option["option_id"]]
    base.update(
        {
            "target_packet_visible": True,
            "target_measure": target,
            "eligible_evidence_condition": "combined",
            "canonical_option_ids": option_ids,
        }
    )
    if binding is not None:
        base["robustness_variant"] = binding.model_dump(mode="json")
    if role is LLMRole.HYBRID_READOUT:
        base["explicit_posterior"] = _synthetic_posterior(
            semantic_map,
            session,
            measure_index % len(fixture.measures),
        )
        mapping = semantic_map.mappings[measure_index % len(semantic_map.mappings)]
        base["semantic_mapping"] = mapping.model_dump(mode="json")
    return base


def _request_template(
    suite: Phase4TogetherSuite,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    candidate: OpenWeightModelCandidate,
    price_card: ProviderPriceCard,
    role_contract: SharedRoleContract,
    measure_index: int,
    variant: QualificationVariant,
    held_out_wave_index: int | None,
    held_out_calibration_kind: HeldOutCalibrationKind | None,
) -> _RequestTemplate:
    role = role_contract.role
    measure = fixture.measures[measure_index % len(fixture.measures)]
    robustness_variant: RobustnessVariantBinding | None = None
    if role in READOUT_ROLES and variant is not QualificationVariant.CANONICAL:
        robustness_variant, _, _ = _readout_variant_binding(
            variant,
            role=role,
            measure_id=measure.measure_id,
            option_ids=[item.option_id for item in measure.options],
        )
    prompt_text = (
        _prompt_paraphrase(role, variant)
        if variant
        in {
            QualificationVariant.PROMPT_PARAPHRASE_1,
            QualificationVariant.PROMPT_PARAPHRASE_2,
        }
        else role_contract.prompt_text
    )
    prompt_payload: JsonValue = {
        "record_version": "phase4_together_qualification_prompt.v1",
        "role": role.value,
        "instructions": prompt_text,
        "canonical_prompt_id": role_contract.prompt_id,
        "canonical_prompt_sha256": role_contract.prompt_sha256,
        "variant_id": variant.value,
    }
    input_payload = _role_input_payload(
        fixture,
        session,
        semantic_map,
        measure_index=measure_index,
        role=role,
        variant=variant,
        held_out_wave_index=held_out_wave_index,
        held_out_calibration_kind=held_out_calibration_kind,
    )
    usage = _role_usage(suite, role, held_out=held_out_wave_index is not None)
    return _RequestTemplate(
        candidate=candidate,
        price_card=price_card,
        role_contract=role_contract,
        measure_id=measure.measure_id,
        measure_version=measure.version,
        role=role,
        variant_id=variant,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_adapter=_role_response_adapter(role),
        tool_definitions=tool_definitions_for_role(role),
        request_seed=_stable_seed(
            candidate.candidate_id,
            role.value,
            measure.measure_id,
            variant.value,
            held_out_wave_index or 0,
            held_out_calibration_kind.value
            if held_out_calibration_kind is not None
            else "qualification",
        ),
        output_token_upper_bound=usage.output_tokens_per_request,
        input_token_upper_bound=usage.input_tokens_per_request,
        robustness_variant=robustness_variant,
    )


def _planning_request(
    profile: Phase4ERobustnessProfile,
    template: _RequestTemplate,
    *,
    call_id: str,
) -> PrivateStructuredProviderRequest:
    schema = response_schema_for_role(template.role)
    attestation = build_public_development_attestation(
        attestation_id=f"{call_id}_public_development",
        prompt_payload=template.prompt_payload,
        input_payload=template.input_payload,
        response_json_schema=schema,
        tool_definitions=template.tool_definitions,
    )
    return prepare_provider_request(
        profile,
        template.candidate,
        template.price_card,
        call_id=call_id,
        role=template.role,
        prompt_id=template.role_contract.prompt_id,
        prompt_version=template.role_contract.prompt_version,
        prompt_payload=template.prompt_payload,
        input_payload=template.input_payload,
        response_schema_id=template.role_contract.response_schema_id,
        response_schema_version=template.role_contract.response_schema_version,
        response_adapter=template.response_adapter,
        privacy_attestation=attestation,
        request_seed=template.request_seed,
        provider_seed_parameter_sent=True,
        temperature=0.0,
        input_token_upper_bound=template.input_token_upper_bound,
        output_token_upper_bound=template.output_token_upper_bound,
        created_at=READINESS_CREATED_AT,
        tool_definitions=template.tool_definitions,
    )


def _projected_provider_payloads(
    suite: Phase4TogetherSuite,
    request: PrivateStructuredProviderRequest,
) -> list[dict[str, JsonValue]]:
    """Render one logical call, including the interviewer's one follow-up."""

    initial = build_together_chat_payload(suite, request)
    if not request.binding.tool_calling_enabled:
        return [initial]
    followup = deepcopy(initial)
    messages = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        followup["messages"]
    )
    messages.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "readiness_tool_call",
                        "type": "function",
                        "function": {
                            "name": "read_evidence_coverage",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "readiness_tool_call",
                "name": "read_evidence_coverage",
                "content": '{"evidence_count":3}',
            },
        ]
    )
    followup["messages"] = messages
    return [initial, followup]


def _candidate_parts(suite: Phase4TogetherSuite):
    return sorted(
        (
            (item.candidate, item.price_card)
            for item in suite.candidates
        ),
        key=lambda item: item[0].candidate_id,
    )


def _variants_for_role(role: LLMRole) -> tuple[QualificationVariant, ...]:
    if role in READOUT_ROLES:
        return tuple(QualificationVariant(item) for item in QUALIFICATION_VARIANT_IDS)
    return (QualificationVariant.CANONICAL,)


def build_qualification_request_manifest(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    counters: dict[str, ExactTokenCounter],
) -> TogetherQualificationRequestManifest:
    """Render and exactly count all 456 public-development requests."""

    if fixture.fixture_id != session.fixture_id or (
        session.fixture_sha256 != content_sha256(fixture)
    ):
        raise ValueError("qualification session does not bind development fixture")
    if semantic_map.fixture_sha256 != content_sha256(fixture):
        raise ValueError("qualification semantic map does not bind fixture")
    role_contracts = {item.role: item for item in suite.shared_role_contracts}
    entries: list[QualificationCallPlanEntry] = []
    specifications = []
    candidate_parts = _candidate_parts(suite)
    for candidate, price_card in candidate_parts:
        for role in sorted(LLMRole, key=lambda item: item.value):
            specifications.append(
                (
                    candidate,
                    price_card,
                    0,
                    role,
                    QualificationVariant.CANONICAL,
                )
            )
    for candidate, price_card in candidate_parts:
        for measure_index, _ in enumerate(fixture.measures):
            for role in sorted(LLMRole, key=lambda item: item.value):
                for variant in _variants_for_role(role):
                    if measure_index == 0 and variant is QualificationVariant.CANONICAL:
                        continue
                    specifications.append(
                        (candidate, price_card, measure_index, role, variant)
                    )
    for candidate, price_card, measure_index, role, variant in specifications:
        counter = counters[candidate.candidate_id]
        measure = fixture.measures[measure_index]
        template = _request_template(
            suite,
            fixture,
            session,
            semantic_map,
            candidate=candidate,
            price_card=price_card,
            role_contract=role_contracts[role],
            measure_index=measure_index,
            variant=variant,
            held_out_wave_index=None,
            held_out_calibration_kind=None,
        )
        call_id = (
            f"qual_{candidate.candidate_id}_{measure.measure_id}_"
            f"{role.value}_{variant.value}"
        )
        request = _planning_request(profile, template, call_id=call_id)
        validate_request_against_role_envelope(
            suite,
            request,
            held_out=False,
        )
        payloads = _projected_provider_payloads(suite, request)
        payload_hashes = [content_sha256(payload) for payload in payloads]
        token_counts = [
            counter.count(_canonical_json(payload)) for payload in payloads
        ]
        token_count = sum(token_counts)
        if token_count > template.input_token_upper_bound:
            raise ValueError(
                "qualification tokenizer count exceeds the frozen "
                f"envelope for {candidate.candidate_id}/{role.value}/"
                f"{variant.value}: {token_count} > "
                f"{template.input_token_upper_bound}"
            )
        projected_cost = price_provider_tokens(
            price_card,
            input_tokens=token_count,
            output_tokens=template.output_token_upper_bound,
        )
        max_cost = price_provider_tokens(
            price_card,
            input_tokens=template.input_token_upper_bound,
            output_tokens=template.output_token_upper_bound,
        )
        entries.append(
            QualificationCallPlanEntry(
                coordinate=QualificationCallCoordinate(
                    call_id=call_id,
                    ordinal=len(entries) + 1,
                    candidate_id=candidate.candidate_id,
                    measure_id=measure.measure_id,
                    measure_version=measure.version,
                    role=role,
                    variant_id=variant,
                    request_seed=template.request_seed,
                ),
                candidate_sha256=content_sha256(candidate),
                price_card_sha256=content_sha256(price_card),
                role_contract_sha256=content_sha256(role_contracts[role]),
                robustness_variant=template.robustness_variant,
                request_template_sha256=(
                    provider_request_content_sha256(request.binding)
                ),
                rendered_payload_sha256=content_sha256(payload_hashes),
                provider_round_count=len(payloads),
                provider_round_payload_sha256=payload_hashes,
                input_token_counts_by_round=token_counts,
                input_token_count=token_count,
                input_token_upper_bound=template.input_token_upper_bound,
                output_token_upper_bound=template.output_token_upper_bound,
                projected_cost_microusd=projected_cost,
                authorized_max_cost_microusd=max_cost,
            )
        )
    return TogetherQualificationRequestManifest(
        plan_id="phase4_together_qualification_plan_v2",
        plan_version=2,
        created_at=READINESS_CREATED_AT,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        public_development_fixture_sha256=content_sha256(fixture),
        public_development_session_sha256=content_sha256(session),
        public_development_semantic_map_sha256=content_sha256(semantic_map),
        entries=entries,
    )


def build_held_out_calibration_manifest(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    counters: dict[str, ExactTokenCounter],
) -> TogetherHeldOutCalibrationManifest:
    """Count six initial waves plus twelve post-wave-six retests."""

    role_contracts = {item.role: item for item in suite.shared_role_contracts}
    rows: list[HeldOutWaveCalibration] = []
    specifications = [
        (
            wave_index,
            HeldOutCalibrationKind.INITIAL_WAVE,
            tuple(sorted(LLMRole, key=lambda item: item.value)),
            len(fixture.measures),
        )
        for wave_index in range(1, 7)
    ]
    specifications.append(
        (
            7,
            HeldOutCalibrationKind.RETEST,
            tuple(sorted(READOUT_ROLES, key=lambda item: item.value)),
            12,
        )
    )
    for candidate, price_card in _candidate_parts(suite):
        counter = counters[candidate.candidate_id]
        for wave_index, presentation_kind, roles, measure_count in specifications:
            for role in roles:
                hashes: list[str] = []
                token_counts: list[int] = []
                projected_cost = 0
                output_total = 0
                for measure_index in range(measure_count):
                    for variant in _variants_for_role(role):
                        template = _request_template(
                            suite,
                            fixture,
                            session,
                            semantic_map,
                            candidate=candidate,
                            price_card=price_card,
                            role_contract=role_contracts[role],
                            measure_index=measure_index,
                            variant=variant,
                            held_out_wave_index=wave_index,
                            held_out_calibration_kind=presentation_kind,
                        )
                        calibration_id = (
                            f"cal_{candidate.candidate_id}_"
                            f"{presentation_kind.value}_w{wave_index}_"
                            f"m{measure_index + 1}_{role.value}_{variant.value}"
                        )
                        request = _planning_request(
                            profile,
                            template=template,
                            call_id=calibration_id,
                        )
                        validate_request_against_role_envelope(
                            suite,
                            request,
                            held_out=True,
                        )
                        payloads = _projected_provider_payloads(suite, request)
                        payload_hashes = [
                            content_sha256(payload) for payload in payloads
                        ]
                        token_count = sum(
                            counter.count(_canonical_json(payload))
                            for payload in payloads
                        )
                        if token_count > template.input_token_upper_bound:
                            raise ValueError(
                                "held-out calibration exceeds its role envelope"
                            )
                        hashes.append(content_sha256(payload_hashes))
                        token_counts.append(token_count)
                        output_total += template.output_token_upper_bound
                        projected_cost += price_provider_tokens(
                            price_card,
                            input_tokens=token_count,
                            output_tokens=template.output_token_upper_bound,
                        )
                rows.append(
                    HeldOutWaveCalibration(
                        candidate_id=candidate.candidate_id,
                        candidate_sha256=content_sha256(candidate),
                        price_card_sha256=content_sha256(price_card),
                        wave_index=wave_index,
                        presentation_kind=presentation_kind,
                        role=role,
                        request_count=len(hashes),
                        ordered_payload_sha256=content_sha256(hashes),
                        input_token_counts=token_counts,
                        input_token_count=sum(token_counts),
                        input_token_upper_bound_per_request=(
                            template.input_token_upper_bound
                        ),
                        maximum_input_tokens_per_request=max(token_counts),
                        output_token_upper_bound_per_request=(
                            template.output_token_upper_bound
                        ),
                        output_token_upper_bound_count=output_total,
                        projected_cost_microusd=projected_cost,
                    )
                )
    return TogetherHeldOutCalibrationManifest(
        calibration_id="phase4_together_held_out_calibration_v2",
        calibration_version=2,
        created_at=READINESS_CREATED_AT,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        public_development_fixture_sha256=content_sha256(fixture),
        rows=rows,
    )


def qualification_remaining_entries(
    manifest: TogetherQualificationRequestManifest,
    completed_call_ids: list[str],
) -> list[QualificationCallPlanEntry]:
    """Return the deterministic suffix after an exact completed prefix."""

    planned = [item.coordinate.call_id for item in manifest.entries]
    if completed_call_ids != planned[: len(completed_call_ids)]:
        raise ValueError("qualification resume must be an exact plan prefix")
    return manifest.entries[len(completed_call_ids) :]


def build_qualification_resume_cursor(
    manifest: TogetherQualificationRequestManifest,
    *,
    completed_call_ids: list[str] | None = None,
) -> QualificationResumeCursor:
    completed = completed_call_ids or []
    remaining = qualification_remaining_entries(manifest, completed)
    remaining_ids = [item.coordinate.call_id for item in remaining]
    return QualificationResumeCursor(
        qualification_manifest_sha256=content_sha256(manifest),
        completed_call_ids=completed,
        remaining_call_ids=remaining_ids,
        next_call_id=remaining_ids[0] if remaining_ids else None,
        completed_call_count=len(completed),
        remaining_call_count=len(remaining_ids),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_exact_tokenizer_from_snapshot(
    candidate: OpenWeightModelCandidate,
    snapshot_path: Path,
    *,
    tokenizer_library_version: str,
) -> LoadedExactTokenizer:
    """Load only tokenizer files already downloaded at the candidate revision."""

    tokenizer_json = snapshot_path / "tokenizer.json"
    if not tokenizer_json.is_file():
        raise ValueError("tokenizer snapshot does not contain tokenizer.json")
    files = [
        path
        for path in snapshot_path.rglob("*")
        if path.is_file()
        and ".cache" not in path.relative_to(snapshot_path).parts
    ]
    file_records = [
        TokenizerFileDigest(
            relative_path=path.relative_to(snapshot_path).as_posix(),
            byte_count=path.stat().st_size,
            sha256=_file_sha256(path),
        )
        for path in sorted(files)
    ]
    artifact = ExactTokenizerArtifact(
        candidate_id=candidate.candidate_id,
        candidate_sha256=content_sha256(candidate),
        upstream_model_id=candidate.upstream_model_id,
        upstream_model_revision=candidate.upstream_model_revision,
        tokenizer_id=f"{candidate.candidate_id}_upstream_tokenizer",
        tokenizer_version=1,
        tokenizer_library_version=tokenizer_library_version,
        files=file_records,
    )
    try:
        from tokenizers import Tokenizer
    except ImportError as error:  # pragma: no cover - exercised by CLI setup
        raise RuntimeError("tokenizers is required for exact readiness") from error
    return LoadedExactTokenizer(
        artifact=artifact,
        backend=Tokenizer.from_file(str(tokenizer_json)),
    )


def build_readiness_bundle(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
    *,
    tokenizer_artifacts: list[ExactTokenizerArtifact],
    qualification_manifest: TogetherQualificationRequestManifest,
    held_out_calibration_manifest: TogetherHeldOutCalibrationManifest,
    qualification_minimum_headroom_microusd: int,
    held_out_minimum_headroom_microusd: int,
) -> Phase4TogetherReadinessBundle:
    artifact_by_candidate = {
        item.candidate_id: item for item in tokenizer_artifacts
    }
    projections: list[TogetherCandidateTokenProjection] = []
    for candidate, price_card in _candidate_parts(suite):
        qualification_entries = [
            item
            for item in qualification_manifest.entries
            if item.coordinate.candidate_id == candidate.candidate_id
        ]
        held_out_rows = [
            item
            for item in held_out_calibration_manifest.rows
            if item.candidate_id == candidate.candidate_id
        ]
        artifact = artifact_by_candidate[candidate.candidate_id]
        projections.append(
            TogetherCandidateTokenProjection(
                candidate_id=candidate.candidate_id,
                candidate_sha256=content_sha256(candidate),
                tokenizer_id=artifact.tokenizer_id,
                tokenizer_version=artifact.tokenizer_version,
                tokenizer_artifact_sha256=content_sha256(artifact),
                qualification_request_manifest_sha256=content_sha256(
                    qualification_manifest
                ),
                qualification_request_count=len(qualification_entries),
                qualification_input_token_count=sum(
                    item.input_token_count for item in qualification_entries
                ),
                qualification_output_token_upper_bound_count=sum(
                    item.output_token_upper_bound for item in qualification_entries
                ),
                qualification_projected_cost_microusd=sum(
                    item.projected_cost_microusd
                    for item in qualification_entries
                ),
                qualification_max_single_call_authorization_microusd=max(
                    item.authorized_max_cost_microusd
                    for item in qualification_entries
                ),
                qualification_all_calls_at_envelope_cost_microusd=sum(
                    item.authorized_max_cost_microusd
                    for item in qualification_entries
                ),
                held_out_calibration_manifest_sha256=content_sha256(
                    held_out_calibration_manifest
                ),
                held_out_calibration_request_count=sum(
                    item.request_count for item in held_out_rows
                ),
                held_out_input_token_count=sum(
                    item.input_token_count for item in held_out_rows
                ),
                held_out_output_token_upper_bound_count=sum(
                    item.output_token_upper_bound_count for item in held_out_rows
                ),
                held_out_projected_cost_microusd=sum(
                    item.projected_cost_microusd for item in held_out_rows
                ),
                held_out_max_single_call_authorization_microusd=max(
                    price_provider_tokens(
                        price_card,
                        input_tokens=row.input_token_upper_bound_per_request,
                        output_tokens=(
                            row.output_token_upper_bound_per_request
                        ),
                    )
                    for row in held_out_rows
                ),
                held_out_all_calls_at_envelope_cost_microusd=sum(
                    row.request_count
                    * price_provider_tokens(
                        price_card,
                        input_tokens=row.input_token_upper_bound_per_request,
                        output_tokens=(
                            row.output_token_upper_bound_per_request
                        ),
                    )
                    for row in held_out_rows
                ),
            )
        )
    receipt = TogetherTokenReadinessReceipt(
        receipt_id="phase4_together_token_readiness_v2",
        receipt_version=2,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        workload_sha256=content_sha256(suite.workload),
        created_at=READINESS_CREATED_AT,
        candidate_projections=projections,
    )
    headroom = TogetherHeadroomPolicy(
        policy_id="phase4_together_headroom_v2",
        policy_version=2,
        created_at=READINESS_CREATED_AT,
        qualification_minimum_headroom_microusd=(
            qualification_minimum_headroom_microusd
        ),
        held_out_minimum_headroom_microusd=(
            held_out_minimum_headroom_microusd
        ),
    )
    bundle = Phase4TogetherReadinessBundle(
        readiness_id="phase4_together_readiness_v2",
        readiness_version=2,
        created_at=READINESS_CREATED_AT,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        robustness_profile_sha256=content_sha256(profile),
        public_development_fixture_sha256=content_sha256(fixture),
        public_development_session_sha256=content_sha256(session),
        public_development_semantic_map_sha256=content_sha256(semantic_map),
        tokenizer_artifacts=tokenizer_artifacts,
        qualification_manifest=qualification_manifest,
        held_out_calibration_manifest=held_out_calibration_manifest,
        token_readiness_receipt=receipt,
        headroom_policy=headroom,
        capability_preflight_call_ids=[
            item.coordinate.call_id
            for item in qualification_manifest.entries[:15]
        ],
    )
    validate_readiness_bundle(
        bundle,
        suite,
        profile,
        fixture,
        session,
        semantic_map,
    )
    return bundle


def validate_readiness_bundle(
    bundle: Phase4TogetherReadinessBundle,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    fixture: EvaluationFixture,
    session: PrequentialSessionScript,
    semantic_map: AuthoredSemanticMapBundle,
) -> None:
    """Reconcile every aggregate without loading a tokenizer or using network."""

    expected_bindings = (
        suite.suite_id,
        suite.suite_version,
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(fixture),
        content_sha256(session),
        content_sha256(semantic_map),
    )
    actual_bindings = (
        bundle.together_suite_id,
        bundle.together_suite_version,
        bundle.together_suite_sha256,
        bundle.robustness_profile_sha256,
        bundle.public_development_fixture_sha256,
        bundle.public_development_session_sha256,
        bundle.public_development_semantic_map_sha256,
    )
    if actual_bindings != expected_bindings:
        raise ValueError("Together readiness binds different public inputs")
    manifest = bundle.qualification_manifest
    calibration = bundle.held_out_calibration_manifest
    expected_manifest_bindings = (
        content_sha256(suite),
        content_sha256(profile),
        content_sha256(fixture),
    )
    if (
        manifest.together_suite_sha256,
        manifest.robustness_profile_sha256,
        manifest.public_development_fixture_sha256,
    ) != expected_manifest_bindings:
        raise ValueError("qualification manifest bindings differ")
    if (
        manifest.public_development_session_sha256,
        manifest.public_development_semantic_map_sha256,
    ) != (content_sha256(session), content_sha256(semantic_map)):
        raise ValueError("qualification manifest development inputs differ")
    if (
        calibration.together_suite_sha256,
        calibration.robustness_profile_sha256,
        calibration.public_development_fixture_sha256,
    ) != expected_manifest_bindings:
        raise ValueError("held-out calibration bindings differ")

    candidate_by_id = {
        item.candidate.candidate_id: item for item in suite.candidates
    }
    role_contracts = {item.role: item for item in suite.shared_role_contracts}
    artifacts = {item.candidate_id: item for item in bundle.tokenizer_artifacts}
    if set(artifacts) != set(candidate_by_id):
        raise ValueError("readiness tokenizer artifacts must cover candidates")
    projections = {
        item.candidate_id: item
        for item in bundle.token_readiness_receipt.candidate_projections
    }
    if set(projections) != set(candidate_by_id):
        raise ValueError("readiness token projections must cover candidates")
    capability_entries = manifest.entries[:15]
    capability_keys = {
        (item.coordinate.candidate_id, item.coordinate.role)
        for item in capability_entries
    }
    expected_capability_keys = {
        (candidate_id, role)
        for candidate_id in candidate_by_id
        for role in LLMRole
    }
    if (
        bundle.capability_preflight_call_ids
        != [item.coordinate.call_id for item in capability_entries]
        or capability_keys != expected_capability_keys
        or any(
            item.coordinate.variant_id is not QualificationVariant.CANONICAL
            for item in capability_entries
        )
    ):
        raise ValueError("capability preflight must be the exact 15-call prefix")

    for candidate_id, container in candidate_by_id.items():
        candidate = container.candidate
        price_card = container.price_card
        artifact = artifacts[candidate_id]
        if (
            artifact.candidate_sha256,
            artifact.upstream_model_id,
            artifact.upstream_model_revision,
        ) != (
            content_sha256(candidate),
            candidate.upstream_model_id,
            candidate.upstream_model_revision,
        ):
            raise ValueError("tokenizer artifact binds another candidate")
        entries = [
            item
            for item in manifest.entries
            if item.coordinate.candidate_id == candidate_id
        ]
        for entry in entries:
            if (
                entry.candidate_sha256,
                entry.price_card_sha256,
                entry.role_contract_sha256,
            ) != (
                content_sha256(candidate),
                content_sha256(price_card),
                content_sha256(role_contracts[entry.coordinate.role]),
            ):
                raise ValueError("qualification plan public binding differs")
            expected_projected_cost = price_provider_tokens(
                price_card,
                input_tokens=entry.input_token_count,
                output_tokens=entry.output_token_upper_bound,
            )
            expected_authorized_cost = price_provider_tokens(
                price_card,
                input_tokens=entry.input_token_upper_bound,
                output_tokens=entry.output_token_upper_bound,
            )
            if (
                entry.projected_cost_microusd != expected_projected_cost
                or entry.authorized_max_cost_microusd
                != expected_authorized_cost
            ):
                raise ValueError("qualification plan cost does not reconcile")
        rows = [
            item for item in calibration.rows if item.candidate_id == candidate_id
        ]
        if any(
            (item.candidate_sha256, item.price_card_sha256)
            != (content_sha256(candidate), content_sha256(price_card))
            for item in rows
        ):
            raise ValueError("held-out calibration public binding differs")
        for row in rows:
            expected_cost = sum(
                price_provider_tokens(
                    price_card,
                    input_tokens=input_tokens,
                    output_tokens=row.output_token_upper_bound_per_request,
                )
                for input_tokens in row.input_token_counts
            )
            if row.projected_cost_microusd != expected_cost:
                raise ValueError("held-out calibration cost does not reconcile")
        projection = projections[candidate_id]
        expected_projection = (
            artifact.tokenizer_id,
            artifact.tokenizer_version,
            content_sha256(artifact),
            content_sha256(manifest),
            len(entries),
            sum(item.input_token_count for item in entries),
            sum(item.output_token_upper_bound for item in entries),
            sum(item.projected_cost_microusd for item in entries),
            max(item.authorized_max_cost_microusd for item in entries),
            sum(item.authorized_max_cost_microusd for item in entries),
            content_sha256(calibration),
            sum(item.request_count for item in rows),
            sum(item.input_token_count for item in rows),
            sum(item.output_token_upper_bound_count for item in rows),
            sum(item.projected_cost_microusd for item in rows),
            max(
                price_provider_tokens(
                    price_card,
                    input_tokens=item.input_token_upper_bound_per_request,
                    output_tokens=item.output_token_upper_bound_per_request,
                )
                for item in rows
            ),
            sum(
                item.request_count
                * price_provider_tokens(
                    price_card,
                    input_tokens=item.input_token_upper_bound_per_request,
                    output_tokens=item.output_token_upper_bound_per_request,
                )
                for item in rows
            ),
        )
        actual_projection = (
            projection.tokenizer_id,
            projection.tokenizer_version,
            projection.tokenizer_artifact_sha256,
            projection.qualification_request_manifest_sha256,
            projection.qualification_request_count,
            projection.qualification_input_token_count,
            projection.qualification_output_token_upper_bound_count,
            projection.qualification_projected_cost_microusd,
            projection.qualification_max_single_call_authorization_microusd,
            projection.qualification_all_calls_at_envelope_cost_microusd,
            projection.held_out_calibration_manifest_sha256,
            projection.held_out_calibration_request_count,
            projection.held_out_input_token_count,
            projection.held_out_output_token_upper_bound_count,
            projection.held_out_projected_cost_microusd,
            projection.held_out_max_single_call_authorization_microusd,
            projection.held_out_all_calls_at_envelope_cost_microusd,
        )
        if actual_projection != expected_projection:
            raise ValueError("Together token projection does not reconcile")
    validate_token_readiness_and_headroom(
        suite,
        profile,
        bundle.token_readiness_receipt,
        bundle.headroom_policy,
    )


def readiness_summary(
    bundle: Phase4TogetherReadinessBundle,
) -> dict[str, JsonValue]:
    projections = bundle.token_readiness_receipt.candidate_projections
    qualification_costs = {
        item.candidate_id: item.qualification_projected_cost_microusd
        for item in projections
    }
    held_out_costs = {
        item.candidate_id: item.held_out_projected_cost_microusd
        for item in projections
    }
    qualification_envelope_costs = {
        item.candidate_id: (
            item.qualification_all_calls_at_envelope_cost_microusd
        )
        for item in projections
    }
    held_out_envelope_costs = {
        item.candidate_id: item.held_out_all_calls_at_envelope_cost_microusd
        for item in projections
    }
    qualification_max_reservation = max(
        item.qualification_max_single_call_authorization_microusd
        for item in projections
    )
    held_out_sequential_headroom = {
        item.candidate_id: (
            bundle.headroom_policy.held_out_cap_microusd
            - item.held_out_projected_cost_microusd
            - item.held_out_max_single_call_authorization_microusd
        )
        for item in projections
    }
    qualification_utilization = {
        candidate_id: max(
            (
                item.input_token_count * 1_000_000
                + item.input_token_upper_bound
                - 1
            )
            // item.input_token_upper_bound
            for item in bundle.qualification_manifest.entries
            if item.coordinate.candidate_id == candidate_id
        )
        for candidate_id in qualification_costs
    }
    held_out_utilization = {
        candidate_id: max(
            (
                item.maximum_input_tokens_per_request * 1_000_000
                + item.input_token_upper_bound_per_request
                - 1
            )
            // item.input_token_upper_bound_per_request
            for item in bundle.held_out_calibration_manifest.rows
            if item.candidate_id == candidate_id
        )
        for candidate_id in held_out_costs
    }
    return {
        "schema_version": bundle.schema_version,
        "readiness_id": bundle.readiness_id,
        "readiness_version": bundle.readiness_version,
        "readiness_sha256": content_sha256(bundle),
        "candidate_count": len(bundle.tokenizer_artifacts),
        "qualification_request_count": len(
            bundle.qualification_manifest.entries
        ),
        "capability_preflight_call_count": (
            bundle.capability_preflight_call_count
        ),
        "held_out_calibration_request_count": sum(
            item.request_count
            for item in bundle.held_out_calibration_manifest.rows
        ),
        "qualification_projected_cost_microusd_by_candidate": (
            qualification_costs
        ),
        "held_out_projected_cost_microusd_by_candidate": held_out_costs,
        "qualification_all_calls_at_envelope_cost_microusd_by_candidate": (
            qualification_envelope_costs
        ),
        "held_out_all_calls_at_envelope_cost_microusd_by_candidate": (
            held_out_envelope_costs
        ),
        "qualification_sequential_reservation_headroom_microusd": (
            bundle.headroom_policy.qualification_cap_microusd
            - sum(qualification_costs.values())
            - qualification_max_reservation
        ),
        "held_out_sequential_reservation_headroom_microusd_by_candidate": (
            held_out_sequential_headroom
        ),
        "maximum_qualification_input_envelope_utilization_ppm_by_candidate": (
            qualification_utilization
        ),
        "maximum_held_out_input_envelope_utilization_ppm_by_candidate": (
            held_out_utilization
        ),
        "qualification_minimum_headroom_microusd": (
            bundle.headroom_policy.qualification_minimum_headroom_microusd
        ),
        "held_out_minimum_headroom_microusd": (
            bundle.headroom_policy.held_out_minimum_headroom_microusd
        ),
        "provider_inference_calls_executed": 0,
        "provider_spend_microusd": 0,
        "provider_billing_token_equivalence_claimed": False,
        "participant_content_omitted": True,
    }


def load_readiness_bundle(path: Path) -> Phase4TogetherReadinessBundle:
    return Phase4TogetherReadinessBundle.model_validate_json(
        path.read_text(encoding="utf-8")
    )
