"""No-spend Together candidate freeze and chat-completion codec for Phase 4E.

This module is deliberately incapable of making a network request.  It freezes
the three approved serverless deployments, their public provenance, one shared
set of role contracts, and conservative qualification/study workload
envelopes.  ``build_together_chat_payload`` converts an already authorized
private provider request into Together's OpenAI-compatible wire shape; a live
HTTP client remains an explicitly injected, later step.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, TypeAdapter, field_validator, model_validator

from .contracts import (
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
    require_complete_enum_set,
)
from .fixture_io import content_sha256
from .phase4_evidence import EvidenceProposalDraft
from .phase4_interviewer import (
    InterviewerDecision,
    ReadCandidateQuestionScoresRequest,
    ReadEvidenceConflictsRequest,
    ReadEvidenceCoverageRequest,
    ReadPosteriorUncertaintyRequest,
)
from .phase4_llm_readout import LLMReadoutResponseDraft
from .phase4_ontology import OntologyDimensionProposalDraft
from .phase4_provider import PrivateStructuredProviderRequest, ProviderPriceCard
from .phase4_qualification import (
    ProjectedRoleUsage,
    ProviderCostProjection,
    build_provider_cost_projection,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    ModelCapability,
    OpenWeightModelCandidate,
    Phase4ERobustnessProfile,
)

NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]

TOGETHER_API_BASE_URL = "https://api.together.ai/v1"
TOGETHER_CHAT_COMPLETIONS_PATH = "/chat/completions"
TOGETHER_CATALOG_URL = "https://docs.together.ai/docs/serverless/models"
TOGETHER_PRIVACY_URL = "https://docs.together.ai/docs/privacy-and-security"
TOGETHER_PARAMETERS_URL = (
    "https://docs.together.ai/docs/inference/chat/parameters"
)
TOGETHER_STRUCTURED_OUTPUTS_URL = (
    "https://docs.together.ai/docs/inference/chat/structured-outputs"
)
TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT = 2
TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION = 3
CAPTURED_AT = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
SUITE_CREATED_AT = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


class TogetherQuantization(str, Enum):
    FP4 = "FP4"
    MXFP4 = "MXFP4"
    NVFP4 = "NVFP4"


class TogetherCatalogEntry(ContractModel):
    """One exact row transcribed from Together's serverless chat catalog."""

    record_version: Literal["phase4_together_catalog_entry.v1"] = (
        "phase4_together_catalog_entry.v1"
    )
    organization: NonEmptyText
    model_name: NonEmptyText
    api_model_string: NonEmptyText
    context_window_tokens: PositiveCount
    input_microusd_per_million_tokens: Microusd
    output_microusd_per_million_tokens: Microusd
    quantization: TogetherQuantization
    function_calling_supported: Literal[True] = True
    structured_outputs_supported: Literal[True] = True


class TogetherCatalogSnapshot(ContractModel):
    record_version: Literal["phase4_together_catalog_snapshot.v1"] = (
        "phase4_together_catalog_snapshot.v1"
    )
    snapshot_id: StableId
    snapshot_version: PositiveVersion
    source_url: Literal[TOGETHER_CATALOG_URL] = TOGETHER_CATALOG_URL
    captured_at: datetime
    entries: list[TogetherCatalogEntry]

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: datetime) -> datetime:
        _require_aware(value, "Together catalog captured_at")
        return value

    @model_validator(mode="after")
    def require_exact_candidate_catalog(self) -> Self:
        ids = [item.api_model_string for item in self.entries]
        if ids != sorted(ids):
            raise ValueError("Together catalog entries must be canonical")
        if len(ids) != 3 or len(ids) != len(set(ids)):
            raise ValueError("Together catalog must contain exactly three models")
        return self


class TogetherTermsSnapshot(ContractModel):
    """Auditable public provider claims that control this study's use."""

    record_version: Literal["phase4_together_terms_snapshot.v1"] = (
        "phase4_together_terms_snapshot.v1"
    )
    snapshot_id: StableId
    snapshot_version: PositiveVersion
    privacy_source_url: Literal[TOGETHER_PRIVACY_URL] = TOGETHER_PRIVACY_URL
    parameters_source_url: Literal[TOGETHER_PARAMETERS_URL] = (
        TOGETHER_PARAMETERS_URL
    )
    structured_outputs_source_url: Literal[TOGETHER_STRUCTURED_OUTPUTS_URL] = (
        TOGETHER_STRUCTURED_OUTPUTS_URL
    )
    captured_at: datetime
    zero_data_retention_default_claimed: Literal[True] = True
    provider_training_requires_opt_in: Literal[True] = True
    passthrough_inference_forbidden_for_study: Literal[True] = True
    per_token_serverless_billing_claimed: Literal[True] = True
    request_seed_documented: Literal[True] = True
    json_schema_response_format_documented: Literal[True] = True
    function_tools_documented: Literal[True] = True

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: datetime) -> datetime:
        _require_aware(value, "Together terms captured_at")
        return value


class OpenWeightManifest(ContractModel):
    """Revision-bound manifest identity without downloading model weights."""

    record_version: Literal["phase4_open_weight_manifest.v1"] = (
        "phase4_open_weight_manifest.v1"
    )
    manifest_id: StableId
    manifest_version: PositiveVersion
    upstream_model_id: NonEmptyText
    upstream_model_revision: NonEmptyText
    revision_tree_url: NonEmptyText
    checkpoint_format: Literal["safetensors"] = "safetensors"
    upstream_checkpoint_quantization: NonEmptyText
    provider_serving_quantization: TogetherQuantization
    remote_weight_bytes_downloaded: Literal[False] = False


class ModelLicenseProvenance(ContractModel):
    record_version: Literal["phase4_model_license_provenance.v1"] = (
        "phase4_model_license_provenance.v1"
    )
    provenance_id: StableId
    provenance_version: PositiveVersion
    upstream_model_id: NonEmptyText
    upstream_model_revision: NonEmptyText
    license_id: NonEmptyText
    license_source_url: NonEmptyText
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: datetime) -> datetime:
        _require_aware(value, "model license captured_at")
        return value


class TogetherCandidateArtifact(ContractModel):
    record_version: Literal["phase4_together_candidate_artifact.v1"] = (
        "phase4_together_candidate_artifact.v1"
    )
    weight_manifest: OpenWeightManifest
    license_provenance: ModelLicenseProvenance
    candidate: OpenWeightModelCandidate
    price_card: ProviderPriceCard

    @model_validator(mode="after")
    def bind_candidate_and_price(self) -> Self:
        catalog_identity = (
            self.weight_manifest.upstream_model_id,
            self.weight_manifest.upstream_model_revision,
        )
        candidate_identity = (
            self.candidate.upstream_model_id,
            self.candidate.upstream_model_revision,
        )
        license_identity = (
            self.license_provenance.upstream_model_id,
            self.license_provenance.upstream_model_revision,
        )
        if catalog_identity != candidate_identity or (
            license_identity != candidate_identity
        ):
            raise ValueError("candidate provenance identities do not match")
        if self.candidate.weights_manifest_sha256 != content_sha256(
            self.weight_manifest
        ):
            raise ValueError("candidate does not bind weight manifest")
        if (
            self.candidate.license_id != self.license_provenance.license_id
            or self.candidate.license_sha256
            != content_sha256(self.license_provenance)
        ):
            raise ValueError("candidate does not bind license provenance")
        if (
            self.price_card.model_candidate_id != self.candidate.candidate_id
            or self.price_card.model_candidate_artifact_version
            != self.candidate.artifact_version
            or self.price_card.model_candidate_sha256
            != content_sha256(self.candidate)
        ):
            raise ValueError("price card does not bind exact candidate")
        return self


class SharedRoleContract(ContractModel):
    """Provider-neutral prompt/schema identity used for every candidate."""

    record_version: Literal["phase4_shared_role_contract.v1"] = (
        "phase4_shared_role_contract.v1"
    )
    role: LLMRole
    prompt_id: StableId
    prompt_version: PositiveVersion
    prompt_text: NonEmptyText
    prompt_sha256: Sha256Digest
    response_schema_id: StableId
    response_schema_version: PositiveVersion
    response_schema_sha256: Sha256Digest
    tool_definitions_sha256: Sha256Digest
    interviewer_tools_enabled: bool

    @model_validator(mode="after")
    def bind_prompt_and_role(self) -> Self:
        if self.prompt_sha256 != content_sha256(self.prompt_text):
            raise ValueError("shared role prompt hash does not match")
        if self.interviewer_tools_enabled != (self.role is LLMRole.INTERVIEWER):
            raise ValueError("only the interviewer role may enable tools")
        if self.response_schema_sha256 != content_sha256(
            response_schema_for_role(self.role)
        ):
            raise ValueError("shared role response schema hash does not match")
        if self.tool_definitions_sha256 != content_sha256(
            tool_definitions_for_role(self.role)
        ):
            raise ValueError("shared role tool definitions hash does not match")
        return self


class ConservativeTokenEnvelope(ContractModel):
    """Candidate-independent request planning bounds.

    Counts are budget envelopes rather than claims about provider billing.
    Actual billed tokens are recorded by the provider runtime.  Each live
    request must first be counted with its exact candidate tokenizer and fit
    its role envelope before it can be authorized.
    """

    record_version: Literal["phase4_conservative_token_envelope.v1"] = (
        "phase4_conservative_token_envelope.v1"
    )
    counter_id: StableId
    counter_version: PositiveVersion
    method: Literal["role_bound_requires_exact_candidate_tokenizer"] = (
        "role_bound_requires_exact_candidate_tokenizer"
    )
    role_usage: list[ProjectedRoleUsage]

    @model_validator(mode="after")
    def require_complete_roles(self) -> Self:
        require_complete_enum_set(
            "Together token-envelope roles",
            [item.role for item in self.role_usage],
            LLMRole,
            set_name="Phase 4E Together v1",
        )
        if [item.role.value for item in self.role_usage] != sorted(
            item.role.value for item in self.role_usage
        ):
            raise ValueError("Together token-envelope roles must be canonical")
        return self


class TogetherWorkloadPlan(ContractModel):
    record_version: Literal["phase4_together_workload_plan.v1"] = (
        "phase4_together_workload_plan.v1"
    )
    workload_id: StableId
    workload_version: PositiveVersion
    development_measure_count: Literal[8] = 8
    held_out_measure_count: Literal[48] = 48
    staged_prediction_calls_per_measure_and_role: Literal[8] = 8
    qualification_per_candidate: ConservativeTokenEnvelope
    held_out_selected_candidate: ConservativeTokenEnvelope

    @model_validator(mode="after")
    def require_declared_call_math(self) -> Self:
        if (
            self.workload_id,
            self.workload_version,
        ) == ("phase4_together_workload_v1", 1):
            held_out_readout_count = 384
        elif (
            self.workload_id,
            self.workload_version,
        ) == ("phase4_together_workload_v2", 2):
            held_out_readout_count = 480
        else:
            raise ValueError("Together workload version is unsupported")
        qualification = {
            item.role: item.request_count
            for item in self.qualification_per_candidate.role_usage
        }
        held_out = {
            item.role: item.request_count
            for item in self.held_out_selected_candidate.role_usage
        }
        if qualification != {
            LLMRole.INTERVIEWER: 8,
            LLMRole.EVIDENCE_EXTRACTOR: 8,
            LLMRole.ONTOLOGY_PROPOSER: 8,
            LLMRole.DIRECT_READOUT: 64,
            LLMRole.HYBRID_READOUT: 64,
        }:
            raise ValueError("qualification workload does not match v1 design")
        if held_out != {
            LLMRole.INTERVIEWER: 48,
            LLMRole.EVIDENCE_EXTRACTOR: 48,
            LLMRole.ONTOLOGY_PROPOSER: 48,
            LLMRole.DIRECT_READOUT: held_out_readout_count,
            LLMRole.HYBRID_READOUT: held_out_readout_count,
        }:
            raise ValueError("held-out workload does not match frozen design")
        return self


class Phase4TogetherSuite(ContractModel):
    schema_version: Literal["preference_eval_phase4_together.v1"] = (
        "preference_eval_phase4_together.v1"
    )
    suite_id: StableId
    suite_version: PositiveVersion
    created_at: datetime
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    provider_id: Literal["together_serverless"] = "together_serverless"
    api_base_url: Literal[TOGETHER_API_BASE_URL] = TOGETHER_API_BASE_URL
    chat_completions_path: Literal[TOGETHER_CHAT_COMPLETIONS_PATH] = (
        TOGETHER_CHAT_COMPLETIONS_PATH
    )
    catalog: TogetherCatalogSnapshot
    provider_terms: TogetherTermsSnapshot
    candidates: list[TogetherCandidateArtifact]
    shared_role_contracts: list[SharedRoleContract]
    workload: TogetherWorkloadPlan
    api_key_stored_in_artifact: Literal[False] = False
    network_calls_permitted_during_validation: Literal[False] = False
    candidate_specific_prompt_branches: Literal[False] = False
    serverless_weight_identity_limit_acknowledged: Literal[True] = True
    workload_is_non_authorizing_feasibility_plan: Literal[True] = True
    exact_candidate_tokenizer_projection_required_before_provider_call: (
        Literal[True]
    ) = True
    projected_headroom_gate_required_before_qualification: Literal[True] = True
    public_source_reverification_required_before_qualification: Literal[True] = (
        True
    )
    live_account_privacy_preflight_required: Literal[True] = True
    live_capability_probe_required_before_qualification: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together suite created_at")
        return value

    @model_validator(mode="after")
    def require_exact_suite(self) -> Self:
        candidate_ids = [item.candidate.candidate_id for item in self.candidates]
        if candidate_ids != sorted(candidate_ids):
            raise ValueError("Together candidates must be canonical")
        if len(candidate_ids) != 3 or len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Together suite requires exactly three candidates")
        role_values = [item.role for item in self.shared_role_contracts]
        require_complete_enum_set(
            "Together shared role contracts",
            role_values,
            LLMRole,
            set_name="Phase 4E Together v1",
        )
        if [item.role.value for item in self.shared_role_contracts] != sorted(
            item.role.value for item in self.shared_role_contracts
        ):
            raise ValueError("Together shared role contracts must be canonical")
        catalog_by_model = {
            item.api_model_string: item for item in self.catalog.entries
        }
        terms_hash = content_sha256(self.provider_terms)
        catalog_hash = content_sha256(self.catalog)
        expected_serving_revision = f"catalog_sha256:{catalog_hash}"
        for item in self.candidates:
            candidate = item.candidate
            catalog = catalog_by_model.get(candidate.serving_model_id)
            if catalog is None:
                raise ValueError("Together candidate is absent from catalog")
            if (
                candidate.serving_model_revision != expected_serving_revision
                or candidate.provider_terms_sha256 != terms_hash
                or item.price_card.provider_pricing_terms_sha256 != catalog_hash
            ):
                raise ValueError("Together candidate public bindings do not match")
            if (
                candidate.context_window_tokens != catalog.context_window_tokens
                or candidate.quantization != catalog.quantization.value
                or item.price_card.input_microusd_per_million_tokens
                != catalog.input_microusd_per_million_tokens
                or item.price_card.output_microusd_per_million_tokens
                != catalog.output_microusd_per_million_tokens
            ):
                raise ValueError("Together candidate catalog values do not match")
            require_complete_enum_set(
                "Together candidate capabilities",
                candidate.capabilities,
                ModelCapability,
                set_name="Phase 4E Together v1",
            )
        return self


class TogetherNoSpendReport(ContractModel):
    record_version: Literal["phase4_together_no_spend_report.v2"] = (
        "phase4_together_no_spend_report.v2"
    )
    suite_sha256: Sha256Digest
    candidate_count: Literal[3] = 3
    shared_role_count: Literal[5] = 5
    qualification_request_count: PositiveCount
    qualification_projected_cost_microusd: Microusd
    qualification_cap_microusd: Literal[4_000_000] = 4_000_000
    qualification_projected_headroom_microusd: int
    held_out_request_count: PositiveCount
    held_out_projected_cost_microusd_by_candidate: dict[StableId, Microusd]
    held_out_projected_headroom_microusd_by_candidate: dict[StableId, int]
    held_out_cap_microusd: Literal[13_000_000] = 13_000_000
    all_candidates_fit_qualification_cap: bool
    all_candidates_fit_held_out_cap: bool
    all_calls_at_envelope_totals_are_non_authorizing: Literal[True] = True
    sequential_reservation_gate_required_for_authorization: Literal[True] = True
    exact_candidate_tokenizer_projection_complete: Literal[False] = False
    projected_headroom_gate_frozen: Literal[False] = False
    live_authorization_ready: Literal[False] = False
    network_call_count: Literal[0] = 0
    spend_microusd: Literal[0] = 0


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def response_schema_for_role(role: LLMRole) -> dict[str, JsonValue]:
    """Return the exact provider response schema for one frozen role."""

    adapters: dict[LLMRole, TypeAdapter] = {
        LLMRole.INTERVIEWER: TypeAdapter(InterviewerDecision),
        LLMRole.EVIDENCE_EXTRACTOR: TypeAdapter(list[EvidenceProposalDraft]),
        LLMRole.ONTOLOGY_PROPOSER: TypeAdapter(
            list[OntologyDimensionProposalDraft]
        ),
        LLMRole.DIRECT_READOUT: TypeAdapter(LLMReadoutResponseDraft),
        LLMRole.HYBRID_READOUT: TypeAdapter(LLMReadoutResponseDraft),
    }
    return adapters[role].json_schema(mode="validation")


def tool_definitions_for_role(
    role: LLMRole,
) -> list[dict[str, JsonValue]]:
    """Return the exact read-only interviewer tool surface, or an empty list."""

    if role is not LLMRole.INTERVIEWER:
        return []
    definitions = (
        (
            "read_posterior_uncertainty",
            "Read posterior uncertainty for one canonical item pair.",
            ReadPosteriorUncertaintyRequest,
        ),
        (
            "read_candidate_question_scores",
            "Read scored vetted question candidates.",
            ReadCandidateQuestionScoresRequest,
        ),
        (
            "read_evidence_coverage",
            "Read aggregate confirmed-evidence coverage.",
            ReadEvidenceCoverageRequest,
        ),
        (
            "read_evidence_conflicts",
            "Read confirmed evidence conflicts.",
            ReadEvidenceConflictsRequest,
        ),
    )
    return [
        {
            "name": name,
            "description": description,
            "input_schema": TypeAdapter(request_type).json_schema(
                mode="validation"
            ),
        }
        for name, description, request_type in definitions
    ]


def build_together_chat_payload(
    suite: Phase4TogetherSuite,
    request: PrivateStructuredProviderRequest,
) -> dict[str, JsonValue]:
    """Render an authorized envelope without credentials or network access."""

    candidates = {
        item.candidate.candidate_id: item.candidate for item in suite.candidates
    }
    candidate = candidates.get(request.binding.model_candidate_id)
    if candidate is None:
        raise ValueError("Together request references unknown candidate")
    if request.binding.model_candidate_sha256 != content_sha256(candidate):
        raise ValueError("Together request candidate hash does not match")
    if (
        request.binding.input_token_upper_bound
        + request.binding.output_token_upper_bound
        > candidate.context_window_tokens
    ):
        raise ValueError("Together request exceeds candidate context window")
    max_tokens = request.binding.output_token_upper_bound
    if request.binding.tool_calling_enabled:
        if max_tokens % TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT:
            raise ValueError(
                "Together interviewer output bound must divide by rounds"
            )
        max_tokens //= TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT
    prompt_text = _canonical_json(request.prompt_payload)
    schema_text = _canonical_json(request.response_json_schema)
    two_phase_interviewer = (
        request.binding.tool_calling_enabled
        and suite.suite_version >= TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION
    )
    if two_phase_interviewer:
        system_content = (
            f"{prompt_text}\nCall at least one provided read-only tool before "
            "making the final decision. Do not emit the final decision in "
            "this tool-selection round."
        )
    else:
        system_content = (
            f"{prompt_text}\nRespond only with JSON matching this schema: "
            f"{schema_text}"
        )
    payload: dict[str, JsonValue] = {
        "model": candidate.serving_model_id,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": _canonical_json(request.input_payload)},
        ],
        "temperature": request.binding.temperature,
        "max_tokens": max_tokens,
        "n": 1,
        "stream": False,
    }
    if not two_phase_interviewer:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.binding.response_schema_id,
                "schema": request.response_json_schema,
            },
        }
    if request.binding.provider_seed_parameter_sent:
        payload["seed"] = request.binding.request_seed
    if request.tool_definitions:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in request.tool_definitions
        ]
        payload["tool_choice"] = (
            "required" if two_phase_interviewer else "auto"
        )
    return payload


def build_together_interviewer_final_payload(
    suite: Phase4TogetherSuite,
    request: PrivateStructuredProviderRequest,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Switch a v3 interviewer call from required tool use to typed output."""

    if (
        suite.suite_version < TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION
        or not request.binding.tool_calling_enabled
    ):
        raise ValueError("Together final interviewer phase requires v3 tools")
    messages = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        payload.get("messages")
    )
    if len(messages) < 4 or messages[-1].get("role") != "tool":
        raise ValueError("Together final interviewer phase requires tool output")
    final = dict(payload)
    final["messages"] = [dict(item) for item in messages]
    prompt_text = _canonical_json(request.prompt_payload)
    schema_text = _canonical_json(request.response_json_schema)
    final["messages"][0] = {
        "role": "system",
        "content": (
            f"{prompt_text}\nUse the completed tool result and respond only "
            f"with JSON matching this schema: {schema_text}"
        ),
    }
    final.pop("tools", None)
    final.pop("tool_choice", None)
    final["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": request.binding.response_schema_id,
            "schema": request.response_json_schema,
        },
    }
    return final


def validate_request_against_role_envelope(
    suite: Phase4TogetherSuite,
    request: PrivateStructuredProviderRequest,
    *,
    held_out: bool,
) -> None:
    envelope = (
        suite.workload.held_out_selected_candidate
        if held_out
        else suite.workload.qualification_per_candidate
    )
    usage = {item.role: item for item in envelope.role_usage}[
        request.binding.role
    ]
    if request.binding.input_token_upper_bound > usage.input_tokens_per_request:
        raise ValueError("Together request exceeds role input-token envelope")
    if request.binding.output_token_upper_bound > usage.output_tokens_per_request:
        raise ValueError("Together request exceeds role output-token envelope")
    if request.binding.tool_calling_enabled and (
        request.binding.output_token_upper_bound
        % TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT
    ):
        raise ValueError("Together interviewer output bound must divide by rounds")


def build_no_spend_report(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> TogetherNoSpendReport:
    validate_together_suite(suite, profile)
    workload_hash = content_sha256(suite.workload)
    qualification_projections: list[ProviderCostProjection] = []
    held_out_costs: dict[str, int] = {}
    for item in suite.candidates:
        qualification_projections.append(
            build_provider_cost_projection(
                item.candidate,
                item.price_card,
                workload_id=suite.workload.workload_id,
                workload_version=suite.workload.workload_version,
                workload_sha256=workload_hash,
                token_counter_id=(
                    suite.workload.qualification_per_candidate.counter_id
                ),
                token_counter_version=(
                    suite.workload.qualification_per_candidate.counter_version
                ),
                token_counter_sha256=content_sha256(
                    suite.workload.qualification_per_candidate
                ),
                role_usage=suite.workload.qualification_per_candidate.role_usage,
            )
        )
        held_out = build_provider_cost_projection(
            item.candidate,
            item.price_card,
            workload_id=suite.workload.workload_id,
            workload_version=suite.workload.workload_version,
            workload_sha256=workload_hash,
            token_counter_id=suite.workload.held_out_selected_candidate.counter_id,
            token_counter_version=(
                suite.workload.held_out_selected_candidate.counter_version
            ),
            token_counter_sha256=content_sha256(
                suite.workload.held_out_selected_candidate
            ),
            role_usage=suite.workload.held_out_selected_candidate.role_usage,
        )
        candidate_id = item.candidate.candidate_id
        held_out_costs[candidate_id] = held_out.projected_cost_microusd
    qualification_cost = sum(
        item.projected_cost_microusd for item in qualification_projections
    )
    qualification_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.QUALIFICATION
    ]
    held_out_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.HELD_OUT_STUDY
    ]
    return TogetherNoSpendReport(
        suite_sha256=content_sha256(suite),
        qualification_request_count=sum(
            item.projected_request_count for item in qualification_projections
        ),
        qualification_projected_cost_microusd=qualification_cost,
        qualification_projected_headroom_microusd=(
            qualification_cap - qualification_cost
        ),
        held_out_request_count=sum(
            item.request_count
            for item in suite.workload.held_out_selected_candidate.role_usage
        ),
        held_out_projected_cost_microusd_by_candidate=held_out_costs,
        held_out_projected_headroom_microusd_by_candidate={
            candidate_id: held_out_cap - cost
            for candidate_id, cost in held_out_costs.items()
        },
        all_candidates_fit_qualification_cap=(
            qualification_cost <= qualification_cap
        ),
        all_candidates_fit_held_out_cap=all(
            cost <= held_out_cap for cost in held_out_costs.values()
        ),
    )


def validate_together_suite(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
) -> None:
    expected_profile = (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    )
    if (
        suite.robustness_profile_id,
        suite.robustness_profile_version,
        suite.robustness_profile_sha256,
    ) != expected_profile:
        raise ValueError("Together suite does not bind exact robustness profile")
    if len(suite.candidates) != profile.model_policy.development_candidate_count:
        raise ValueError("Together suite candidate count does not match profile")
    for item in suite.candidates:
        require_complete_enum_set(
            "Together suite candidate capabilities",
            item.candidate.capabilities,
            ModelCapability,
            set_name="Phase 4E Together v1",
        )


def load_together_suite(path: str | Path) -> Phase4TogetherSuite:
    return Phase4TogetherSuite.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _catalog_snapshot() -> TogetherCatalogSnapshot:
    return TogetherCatalogSnapshot(
        snapshot_id="together_serverless_catalog_2026_08_20",
        snapshot_version=1,
        captured_at=CAPTURED_AT,
        entries=[
            TogetherCatalogEntry(
                organization="NVIDIA",
                model_name="Nemotron 3 Ultra 550B A55B",
                api_model_string="nvidia/nemotron-3-ultra-550b-a55b",
                context_window_tokens=512_300,
                input_microusd_per_million_tokens=600_000,
                output_microusd_per_million_tokens=3_600_000,
                quantization=TogetherQuantization.NVFP4,
            ),
            TogetherCatalogEntry(
                organization="OpenAI",
                model_name="GPT-OSS 120B",
                api_model_string="openai/gpt-oss-120b",
                context_window_tokens=128_000,
                input_microusd_per_million_tokens=150_000,
                output_microusd_per_million_tokens=600_000,
                quantization=TogetherQuantization.MXFP4,
            ),
            TogetherCatalogEntry(
                organization="Z.ai",
                model_name="GLM-5.2",
                api_model_string="zai-org/GLM-5.2",
                context_window_tokens=512_000,
                input_microusd_per_million_tokens=1_400_000,
                output_microusd_per_million_tokens=4_400_000,
                quantization=TogetherQuantization.FP4,
            ),
        ],
    )


def _terms_snapshot() -> TogetherTermsSnapshot:
    return TogetherTermsSnapshot(
        snapshot_id="together_public_terms_2026_08_20",
        snapshot_version=1,
        captured_at=CAPTURED_AT,
    )


def _candidate_artifact(
    *,
    candidate_id: str,
    upstream_model_id: str,
    upstream_revision: str,
    serving_model_id: str,
    upstream_quantization: str,
    serving_quantization: TogetherQuantization,
    license_id: str,
    license_source_url: str,
    catalog: TogetherCatalogSnapshot,
    terms: TogetherTermsSnapshot,
) -> TogetherCandidateArtifact:
    manifest = OpenWeightManifest(
        manifest_id=f"{candidate_id}_weights",
        manifest_version=1,
        upstream_model_id=upstream_model_id,
        upstream_model_revision=upstream_revision,
        revision_tree_url=(
            f"https://huggingface.co/{upstream_model_id}/tree/{upstream_revision}"
        ),
        upstream_checkpoint_quantization=upstream_quantization,
        provider_serving_quantization=serving_quantization,
    )
    license_provenance = ModelLicenseProvenance(
        provenance_id=f"{candidate_id}_license",
        provenance_version=1,
        upstream_model_id=upstream_model_id,
        upstream_model_revision=upstream_revision,
        license_id=license_id,
        license_source_url=license_source_url,
        captured_at=CAPTURED_AT,
    )
    catalog_entry = {
        item.api_model_string: item for item in catalog.entries
    }[serving_model_id]
    candidate = OpenWeightModelCandidate(
        candidate_id=candidate_id,
        artifact_id=f"{candidate_id}_artifact",
        artifact_version=1,
        upstream_model_id=upstream_model_id,
        upstream_model_revision=upstream_revision,
        weights_manifest_sha256=content_sha256(manifest),
        license_id=license_id,
        license_sha256=content_sha256(license_provenance),
        deployment_mode="hosted_api",
        backend_id="together_chat_completions",
        backend_version=1,
        serving_model_id=serving_model_id,
        serving_model_revision=f"catalog_sha256:{content_sha256(catalog)}",
        provider_terms_sha256=content_sha256(terms),
        quantization=serving_quantization.value,
        context_window_tokens=catalog_entry.context_window_tokens,
        capabilities=list(ModelCapability),
    )
    price_card = ProviderPriceCard(
        price_card_id=f"{candidate_id}_price_2026_08_20",
        price_card_version=1,
        model_candidate_id=candidate_id,
        model_candidate_artifact_version=candidate.artifact_version,
        model_candidate_sha256=content_sha256(candidate),
        input_microusd_per_million_tokens=(
            catalog_entry.input_microusd_per_million_tokens
        ),
        output_microusd_per_million_tokens=(
            catalog_entry.output_microusd_per_million_tokens
        ),
        provider_pricing_terms_sha256=content_sha256(catalog),
        effective_at=CAPTURED_AT,
    )
    return TogetherCandidateArtifact(
        weight_manifest=manifest,
        license_provenance=license_provenance,
        candidate=candidate,
        price_card=price_card,
    )


def _role_contracts() -> list[SharedRoleContract]:
    definitions: dict[LLMRole, tuple[str, str]] = {
        LLMRole.INTERVIEWER: (
            "Choose only an allowed preference-interview action. First use "
            "at least one provided read-only tool, never invent a question, "
            "never update preference state, and never inspect a target packet. "
            "After observing the tool result, return only the required "
            "structured decision.",
            "phase4_interviewer_decision_and_tool_contracts_v1",
        ),
        LLMRole.EVIDENCE_EXTRACTOR: (
            "Extract only preference claims explicitly supported by the supplied "
            "participant messages. Preserve source-message lineage, flag every "
            "unsupported assumption, and return only structured zero-weight "
            "proposals for participant confirmation.",
            "phase4_evidence_proposal_drafts_v1",
        ),
        LLMRole.ONTOLOGY_PROPOSER: (
            "Propose a new value dimension only when confirmed participant "
            "evidence cannot be represented by the active ontology. Identify "
            "possible duplicates, preserve exact evidence lineage, assign no "
            "model weight, and return only structured proposals.",
            "phase4_ontology_dimension_proposal_drafts_v1",
        ),
        LLMRole.DIRECT_READOUT: (
            "Predict the participant's ballot choice from only the neutral target "
            "packet and condition-eligible evidence. Do not use the participant's "
            "answer. Return normalized option probabilities, settled probability, "
            "eligible supporting-evidence ids, and unsupported assumptions.",
            "phase4_llm_readout_response_v1",
        ),
        LLMRole.HYBRID_READOUT: (
            "Predict the participant's ballot choice from only the neutral target "
            "packet, condition-eligible evidence, and supplied explicit posterior. "
            "Do not use the participant's answer. Return normalized option "
            "probabilities, settled probability, eligible supporting-evidence ids, "
            "and unsupported assumptions.",
            "phase4_llm_readout_response_v1",
        ),
    }
    contracts: list[SharedRoleContract] = []
    for role in sorted(LLMRole, key=lambda item: item.value):
        prompt, response_contract_id = definitions[role]
        contracts.append(
            SharedRoleContract(
                role=role,
                prompt_id=(
                    "phase4_interviewer_together_v2"
                    if role is LLMRole.INTERVIEWER
                    else f"phase4_{role.value}_together_v1"
                ),
                prompt_version=(2 if role is LLMRole.INTERVIEWER else 1),
                prompt_text=prompt,
                prompt_sha256=content_sha256(prompt),
                response_schema_id=response_contract_id,
                response_schema_version=1,
                response_schema_sha256=content_sha256(
                    response_schema_for_role(role)
                ),
                tool_definitions_sha256=content_sha256(
                    tool_definitions_for_role(role)
                ),
                interviewer_tools_enabled=(role is LLMRole.INTERVIEWER),
            )
        )
    return contracts


def _role_usage(
    *,
    conversational_count: int,
    readout_count: int,
    held_out: bool,
) -> list[ProjectedRoleUsage]:
    token_bounds = {
        LLMRole.DIRECT_READOUT: (7_000 if held_out else 6_000, 1_000),
        LLMRole.EVIDENCE_EXTRACTOR: (6_000, 1_000),
        LLMRole.HYBRID_READOUT: (8_000 if held_out else 7_000, 1_000),
        LLMRole.INTERVIEWER: (15_000, 1_000),
        LLMRole.ONTOLOGY_PROPOSER: (6_000, 1_000),
    }
    return [
        ProjectedRoleUsage(
            role=role,
            request_count=(
                readout_count
                if role in {LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT}
                else conversational_count
            ),
            input_tokens_per_request=token_bounds[role][0],
            output_tokens_per_request=token_bounds[role][1],
        )
        for role in sorted(LLMRole, key=lambda item: item.value)
    ]


def _workload_plan() -> TogetherWorkloadPlan:
    return TogetherWorkloadPlan(
        workload_id="phase4_together_workload_v2",
        workload_version=2,
        qualification_per_candidate=ConservativeTokenEnvelope(
            counter_id="phase4_together_qualification_envelope_v2",
            counter_version=2,
            role_usage=_role_usage(
                conversational_count=8,
                readout_count=64,
                held_out=False,
            ),
        ),
        held_out_selected_candidate=ConservativeTokenEnvelope(
            counter_id="phase4_together_held_out_envelope_v2",
            counter_version=2,
            role_usage=_role_usage(
                conversational_count=48,
                readout_count=480,
                held_out=True,
            ),
        ),
    )


def build_default_together_suite(
    profile: Phase4ERobustnessProfile,
) -> Phase4TogetherSuite:
    """Build the exact tracked v3 suite without reading credentials or network."""

    catalog = _catalog_snapshot()
    terms = _terms_snapshot()
    candidates = [
        _candidate_artifact(
            candidate_id="together_glm_5_2",
            upstream_model_id="zai-org/GLM-5.2",
            upstream_revision="48cf76872d0f20ab526a663f7e540817afc9b9ef",
            serving_model_id="zai-org/GLM-5.2",
            upstream_quantization="BF16 source checkpoint",
            serving_quantization=TogetherQuantization.FP4,
            license_id="MIT",
            license_source_url=(
                "https://huggingface.co/zai-org/GLM-5.2/blob/"
                "48cf76872d0f20ab526a663f7e540817afc9b9ef/LICENSE"
            ),
            catalog=catalog,
            terms=terms,
        ),
        _candidate_artifact(
            candidate_id="together_gpt_oss_120b",
            upstream_model_id="openai/gpt-oss-120b",
            upstream_revision="b5c939de8f754692c1647ca79fbf85e8c1e70f8a",
            serving_model_id="openai/gpt-oss-120b",
            upstream_quantization="MXFP4",
            serving_quantization=TogetherQuantization.MXFP4,
            license_id="Apache-2.0",
            license_source_url=(
                "https://huggingface.co/openai/gpt-oss-120b/blob/"
                "b5c939de8f754692c1647ca79fbf85e8c1e70f8a/LICENSE"
            ),
            catalog=catalog,
            terms=terms,
        ),
        _candidate_artifact(
            candidate_id="together_nemotron_3_ultra_550b_a55b",
            upstream_model_id=(
                "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4"
            ),
            upstream_revision="183968f87ae4cedce3039313cac1fd43d112c578",
            serving_model_id="nvidia/nemotron-3-ultra-550b-a55b",
            upstream_quantization="NVFP4",
            serving_quantization=TogetherQuantization.NVFP4,
            license_id="OpenMDW-1.1",
            license_source_url=(
                "https://huggingface.co/nvidia/"
                "NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4/blob/"
                "183968f87ae4cedce3039313cac1fd43d112c578/README.md"
            ),
            catalog=catalog,
            terms=terms,
        ),
    ]
    suite = Phase4TogetherSuite(
        suite_id="preference_eval_phase4_together_v3",
        suite_version=3,
        created_at=SUITE_CREATED_AT,
        robustness_profile_id=profile.profile_id,
        robustness_profile_version=profile.profile_version,
        robustness_profile_sha256=content_sha256(profile),
        catalog=catalog,
        provider_terms=terms,
        candidates=candidates,
        shared_role_contracts=_role_contracts(),
        workload=_workload_plan(),
    )
    validate_together_suite(suite, profile)
    return suite
