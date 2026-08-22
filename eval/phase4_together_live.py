"""Authorized Together network boundary for Phase 4E.

The tracked no-spend suite deliberately contains no credential or HTTP client.
This module adds two explicit live boundaries:

* a zero-provider-spend catalog preflight that requires a manual account
  privacy attestation; and
* a paid chat transport that cannot be constructed without exact workload,
  headroom, and user-authorization artifacts.

Secrets remain runtime-only.  Persisted receipts contain hashes, public model
metadata, aggregate counts, and approval bindings, never API-key material or
provider request text.
"""

from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from .contracts import (
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
    require_complete_enum_set,
)
from .fixture_io import content_sha256
from .phase4_interviewer import (
    InterviewerToolProvider,
    ReadCandidateQuestionScoresRequest,
    ReadEvidenceConflictsRequest,
    ReadEvidenceCoverageRequest,
    ReadPosteriorUncertaintyRequest,
)
from .phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderSeedStatus,
    ProviderTransportResult,
    price_provider_tokens,
)
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    Phase4ERobustnessProfile,
)
from .phase4_together import (
    TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT,
    TOGETHER_CATALOG_URL,
    TOGETHER_PRIVACY_URL,
    TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION,
    Phase4TogetherSuite,
    build_together_chat_payload,
    build_together_interviewer_final_payload,
)

NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
Microusd = Annotated[int, Field(ge=0)]
PositiveFiniteFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]

TOGETHER_API_KEY_ENV = "TOGETHER_API_KEY"
DEFAULT_HTTP_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_TOOL_ROUNDS = TOGETHER_INTERVIEWER_PROVIDER_ROUND_LIMIT - 1


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


def _canonical_ids(values: list[str], label: str) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique and canonical")


class TogetherAccountPrivacyAttestation(ContractModel):
    """Manual, content-free check of the exact account used for the study."""

    record_version: Literal["phase4_together_account_privacy.v1"] = (
        "phase4_together_account_privacy.v1"
    )
    attestation_id: StableId
    attestation_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    provider_terms_sha256: Sha256Digest
    checked_at: datetime
    privacy_settings_url: Literal[TOGETHER_PRIVACY_URL] = TOGETHER_PRIVACY_URL
    project_scoped_api_key_created: Literal[True] = True
    data_sharing_for_training_disabled: Literal[True] = True
    default_input_output_nonstorage_acknowledged: Literal[True] = True
    temporary_caching_terms_acknowledged: Literal[True] = True
    api_key_stored_outside_repository_history: Literal[True] = True
    api_key_value_or_hash_recorded: Literal[False] = False
    account_identifier_recorded: Literal[False] = False
    public_development_preflight_approved: Literal[True] = True

    @field_validator("checked_at")
    @classmethod
    def require_aware_checked_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together account checked_at")
        return value


class TogetherPublicSourceCheck(ContractModel):
    source_url: NonEmptyText
    response_sha256: Sha256Digest


class TogetherPublicSourceReverification(ContractModel):
    """Content hashes from re-fetching every public source bound by the suite."""

    record_version: Literal["phase4_together_source_reverification.v1"] = (
        "phase4_together_source_reverification.v1"
    )
    receipt_id: StableId
    receipt_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    checked_at: datetime
    source_checks: list[TogetherPublicSourceCheck]

    @field_validator("checked_at")
    @classmethod
    def require_aware_checked_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together public sources checked_at")
        return value

    @model_validator(mode="after")
    def require_canonical_sources(self) -> Self:
        urls = [item.source_url for item in self.source_checks]
        _canonical_ids(urls, "Together public source URLs")
        return self


class TogetherCatalogPreflightAuthorization(ContractModel):
    """User authorization for one authenticated, zero-inference model-list call."""

    record_version: Literal["phase4_together_catalog_authorization.v1"] = (
        "phase4_together_catalog_authorization.v1"
    )
    authorization_id: StableId
    authorization_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    account_privacy_attestation_sha256: Sha256Digest
    public_source_reverification_sha256: Sha256Digest
    exact_endpoint_path: Literal["/models"] = "/models"
    authorized_request_count: Literal[1] = 1
    authorized_provider_spend_microusd: Literal[0] = 0
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "Together catalog authorization time")
        return value

    @model_validator(mode="after")
    def require_forward_window(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("Together catalog authorization must expire later")
        return self


class TogetherCatalogCandidateCheck(ContractModel):
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    serving_model_id: NonEmptyText
    advertised_context_window_tokens: PositiveCount
    live_context_window_tokens: PositiveCount
    required_context_window_tokens: PositiveCount
    live_context_satisfies_workload: Literal[True] = True
    input_microusd_per_million_tokens: Microusd
    output_microusd_per_million_tokens: Microusd

    @model_validator(mode="after")
    def require_live_workload_capacity(self) -> Self:
        if self.live_context_window_tokens < self.required_context_window_tokens:
            raise ValueError(
                "Together live candidate context cannot fit the study workload"
            )
        return self


class TogetherCatalogPreflightReceipt(ContractModel):
    """Public-metadata-only receipt from the authenticated model-list endpoint."""

    record_version: Literal["phase4_together_catalog_receipt.v1"] = (
        "phase4_together_catalog_receipt.v1"
    )
    receipt_id: StableId
    receipt_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    live_model_list_sha256: Sha256Digest
    checked_at: datetime
    source_url: Literal[TOGETHER_CATALOG_URL] = TOGETHER_CATALOG_URL
    candidate_checks: list[TogetherCatalogCandidateCheck]
    candidate_identity_and_prices_match_suite: Literal[True] = True
    authenticated_network_request_count: Literal[1] = 1
    inference_request_count: Literal[0] = 0
    provider_spend_microusd: Literal[0] = 0

    @field_validator("checked_at")
    @classmethod
    def require_aware_checked_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together catalog receipt checked_at")
        return value

    @model_validator(mode="after")
    def require_canonical_candidates(self) -> Self:
        _canonical_ids(
            [item.candidate_id for item in self.candidate_checks],
            "Together catalog candidate checks",
        )
        return self


class TogetherCatalogPreflightBundle(ContractModel):
    """Private local bundle required before any paid Together authorization."""

    record_version: Literal["phase4_together_catalog_bundle.v1"] = (
        "phase4_together_catalog_bundle.v1"
    )
    bundle_id: StableId
    bundle_version: PositiveVersion
    account_privacy_attestation: TogetherAccountPrivacyAttestation
    public_source_reverification: TogetherPublicSourceReverification
    authorization: TogetherCatalogPreflightAuthorization
    receipt: TogetherCatalogPreflightReceipt

    @model_validator(mode="after")
    def require_exact_hash_chain(self) -> Self:
        if self.authorization.account_privacy_attestation_sha256 != (
            content_sha256(self.account_privacy_attestation)
        ):
            raise ValueError("Together catalog bundle account hash differs")
        if self.authorization.public_source_reverification_sha256 != (
            content_sha256(self.public_source_reverification)
        ):
            raise ValueError("Together catalog bundle source hash differs")
        if self.receipt.authorization_sha256 != content_sha256(
            self.authorization
        ):
            raise ValueError("Together catalog bundle authorization hash differs")
        return self


class TogetherCandidateTokenProjection(ContractModel):
    """Exact development counts plus held-out calibration for one candidate."""

    candidate_id: StableId
    candidate_sha256: Sha256Digest
    tokenizer_id: StableId
    tokenizer_version: PositiveVersion
    tokenizer_artifact_sha256: Sha256Digest
    qualification_request_manifest_sha256: Sha256Digest
    qualification_request_count: PositiveCount
    qualification_input_token_count: NonNegativeCount
    qualification_output_token_upper_bound_count: NonNegativeCount
    qualification_projected_cost_microusd: Microusd
    qualification_max_single_call_authorization_microusd: Microusd
    qualification_all_calls_at_envelope_cost_microusd: Microusd
    held_out_calibration_manifest_sha256: Sha256Digest
    held_out_calibration_request_count: PositiveCount
    held_out_input_token_count: NonNegativeCount
    held_out_output_token_upper_bound_count: NonNegativeCount
    held_out_projected_cost_microusd: Microusd
    held_out_max_single_call_authorization_microusd: Microusd
    held_out_all_calls_at_envelope_cost_microusd: Microusd


class TogetherTokenReadinessReceipt(ContractModel):
    """Tokenizer readiness required before a paid chat transport can exist."""

    record_version: Literal["phase4_together_token_readiness.v1"] = (
        "phase4_together_token_readiness.v1"
    )
    receipt_id: StableId
    receipt_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    workload_sha256: Sha256Digest
    created_at: datetime
    candidate_projections: list[TogetherCandidateTokenProjection]
    exact_candidate_tokenizers_used: Literal[True] = True
    qualification_requests_rendered_and_counted: Literal[True] = True
    held_out_calibration_is_wave_aware: Literal[True] = True
    future_held_out_request_exact_count_required: Literal[True] = True
    over_envelope_action: Literal["pause_without_send"] = "pause_without_send"
    prompt_and_response_format_schema_copies_counted: Literal[2] = 2
    interviewer_provider_round_limit: Literal[2] = 2
    tool_loop_followup_allowance_counted: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together token projection created_at")
        return value

    @model_validator(mode="after")
    def require_canonical_candidates(self) -> Self:
        _canonical_ids(
            [item.candidate_id for item in self.candidate_projections],
            "Together token projections",
        )
        return self


class TogetherHeadroomPolicy(ContractModel):
    """Predeclared margin tokenizer projections retain under hard caps."""

    record_version: Literal["phase4_together_headroom_policy.v1"] = (
        "phase4_together_headroom_policy.v1"
    )
    policy_id: StableId
    policy_version: PositiveVersion
    created_at: datetime
    qualification_minimum_headroom_microusd: PositiveCount
    held_out_minimum_headroom_microusd: PositiveCount
    qualification_cap_microusd: Literal[4_000_000] = 4_000_000
    held_out_cap_microusd: Literal[13_000_000] = 13_000_000
    accounting_method: Literal[
        "projected_spend_plus_largest_single_call_reservation"
    ] = "projected_spend_plus_largest_single_call_reservation"
    frozen_before_capability_calls: Literal[True] = True
    applies_to_token_readiness_receipt: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together headroom policy created_at")
        return value


class TogetherCapabilityProbeCheck(ContractModel):
    candidate_id: StableId
    role: LLMRole
    call_id: StableId
    finalization_sha256: Sha256Digest
    strict_structured_output_passed: Literal[True] = True
    seed_request_accepted: Literal[True] = True
    interviewer_tool_calling_passed: bool | None = None

    @model_validator(mode="after")
    def require_interviewer_tool_result_only(self) -> Self:
        if self.role is LLMRole.INTERVIEWER:
            if self.interviewer_tool_calling_passed is not True:
                raise ValueError("interviewer capability probe must pass tools")
        elif self.interviewer_tool_calling_passed is not None:
            raise ValueError("only interviewer capability probes test tools")
        return self


class TogetherCapabilityPreflightReceipt(ContractModel):
    """Content-free matrix produced by paid public-development probes."""

    record_version: Literal["phase4_together_capability_receipt.v1"] = (
        "phase4_together_capability_receipt.v1"
    )
    receipt_id: StableId
    receipt_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    provider_ledger_sha256: Sha256Digest
    provider_journal_sha256: Sha256Digest
    completed_at: datetime
    checks: list[TogetherCapabilityProbeCheck]
    provider_spend_microusd: Microusd

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        _require_aware(value, "Together capability receipt completed_at")
        return value

    @model_validator(mode="after")
    def require_unique_check_matrix(self) -> Self:
        identities = [(item.candidate_id, item.role) for item in self.checks]
        if len(identities) != len(set(identities)):
            raise ValueError("Together capability checks cannot duplicate roles")
        return self


class TogetherPaidStage(str, Enum):
    CAPABILITY_PREFLIGHT = "capability_preflight"
    QUALIFICATION = "qualification"


class TogetherLiveAuthorization(ContractModel):
    """Required user authorization object for the paid Together transport."""

    record_version: Literal["phase4_together_live_authorization.v1"] = (
        "phase4_together_live_authorization.v1"
    )
    authorization_id: StableId
    authorization_version: PositiveVersion
    together_suite_id: StableId
    together_suite_version: PositiveVersion
    together_suite_sha256: Sha256Digest
    robustness_profile_sha256: Sha256Digest
    account_privacy_attestation_sha256: Sha256Digest
    catalog_preflight_receipt_sha256: Sha256Digest
    token_readiness_receipt_sha256: Sha256Digest
    headroom_policy_sha256: Sha256Digest
    capability_preflight_receipt_sha256: Sha256Digest | None = None
    stage: TogetherPaidStage
    budget_segment: Literal[
        BudgetSegment.QUALIFICATION,
        BudgetSegment.RETRY_RESERVE,
    ] = BudgetSegment.QUALIFICATION
    authorized_candidate_ids: list[StableId]
    authorized_roles: list[LLMRole]
    approved_max_spend_microusd: Microusd
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        _require_aware(value, "Together live authorization time")
        return value

    @model_validator(mode="after")
    def require_stage_shape(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("Together live authorization must expire later")
        _canonical_ids(
            self.authorized_candidate_ids,
            "Together authorized candidate ids",
        )
        require_complete_enum_set(
            "Together authorized roles",
            self.authorized_roles,
            LLMRole,
            set_name="Phase 4E Together live v1",
        )
        if [item.value for item in self.authorized_roles] != sorted(
            item.value for item in self.authorized_roles
        ):
            raise ValueError("Together authorized roles must be canonical")
        if self.stage is TogetherPaidStage.CAPABILITY_PREFLIGHT:
            if self.capability_preflight_receipt_sha256 is not None:
                raise ValueError("capability authorization cannot bind its result")
        elif self.capability_preflight_receipt_sha256 is None:
            raise ValueError("qualification authorization requires capability receipt")
        return self


class TogetherAmbiguousDeliveryError(RuntimeError):
    """A request may have reached Together but no auditable usage was returned."""

    def __init__(self, call_id: str, failure_code: str) -> None:
        super().__init__(
            "Together delivery is ambiguous; preserve the outstanding "
            f"authorization for {call_id} ({failure_code})"
        )
        self.call_id = call_id
        self.failure_code = failure_code


class _TogetherPricing(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: int | float | str
    output: int | float | str


class _TogetherModelRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    context_length: int
    pricing: _TogetherPricing


class _TogetherUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: NonNegativeCount
    completion_tokens: NonNegativeCount
    total_tokens: NonNegativeCount

    @model_validator(mode="after")
    def require_reconciled_total(self) -> Self:
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Together usage token total does not reconcile")
        return self


class _TogetherToolFunction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    arguments: str


class _TogetherToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["function"]
    function: _TogetherToolFunction


class _TogetherMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[_TogetherToolCall] = Field(default_factory=list)


class _TogetherChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int
    seed: int | None = None
    finish_reason: str | None = None
    message: _TogetherMessage


class _TogetherChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    choices: list[_TogetherChoice]
    usage: _TogetherUsage

    @model_validator(mode="after")
    def require_one_choice(self) -> Self:
        if len(self.choices) != 1 or self.choices[0].index != 0:
            raise ValueError("Together response must contain choice zero only")
        return self


class TogetherToolExecutor(Protocol):
    def execute(self, name: str, arguments: JsonValue) -> JsonValue: ...


class TogetherPayloadTokenCount(ContractModel):
    """Exact local tokenizer result for one provider payload."""

    record_version: Literal["phase4_together_payload_token_count.v1"] = (
        "phase4_together_payload_token_count.v1"
    )
    candidate_id: StableId
    candidate_sha256: Sha256Digest
    tokenizer_id: StableId
    tokenizer_version: PositiveVersion
    tokenizer_artifact_sha256: Sha256Digest
    payload_sha256: Sha256Digest
    input_token_count: NonNegativeCount


class TogetherTokenCounter(Protocol):
    def count_payload(
        self,
        candidate_id: str,
        payload: dict[str, JsonValue],
    ) -> TogetherPayloadTokenCount: ...


class TogetherInterviewerToolExecutor:
    """Typed bridge from Together function calls to the frozen read-only tools."""

    def __init__(self, tools: InterviewerToolProvider) -> None:
        self._tools = tools

    def execute(self, name: str, arguments: JsonValue) -> JsonValue:
        if not isinstance(arguments, dict):
            raise ValueError("Together tool arguments must be an object")
        routes = {
            "read_posterior_uncertainty": (
                ReadPosteriorUncertaintyRequest,
                self._tools.read_posterior_uncertainty,
            ),
            "read_candidate_question_scores": (
                ReadCandidateQuestionScoresRequest,
                self._tools.read_candidate_question_scores,
            ),
            "read_evidence_coverage": (
                ReadEvidenceCoverageRequest,
                self._tools.read_evidence_coverage,
            ),
            "read_evidence_conflicts": (
                ReadEvidenceConflictsRequest,
                self._tools.read_evidence_conflicts,
            ),
        }
        route = routes.get(name)
        if route is None:
            raise ValueError("Together requested an unknown interviewer tool")
        request_type, handler = route
        request = request_type.model_validate(arguments)
        return handler(request).model_dump(mode="json")


def load_together_api_key(
    *,
    environment: Mapping[str, str] | None = None,
    local_env_file: str | Path | None = None,
) -> SecretStr:
    """Load one local secret without accepting it as a command-line value."""

    source = os.environ if environment is None else environment
    environment_value = source.get(TOGETHER_API_KEY_ENV)
    if environment_value and local_env_file is not None:
        raise ValueError("Together API key must have one local source")
    value = environment_value
    if local_env_file is not None:
        lines = Path(local_env_file).read_text(encoding="utf-8").splitlines()
        matches = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, candidate = stripped.split("=", 1)
            if name.strip() == TOGETHER_API_KEY_ENV:
                matches.append(candidate.strip())
        if len(matches) != 1:
            raise ValueError("local secret file must define TOGETHER_API_KEY once")
        value = matches[0]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
    if value is None or len(value.strip()) < 16:
        raise ValueError("Together API key is missing or malformed")
    return SecretStr(value.strip())


def _usd_per_million_to_microusd(value: int | float | str) -> int:
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Together model price is not numeric") from error
    microusd = decimal_value * Decimal(1_000_000)
    if microusd < 0 or microusd != microusd.to_integral_value():
        raise ValueError("Together model price is not exact to one microusd")
    return int(microusd)


def build_catalog_preflight_authorization(
    suite: Phase4TogetherSuite,
    account_attestation: TogetherAccountPrivacyAttestation,
    public_sources: TogetherPublicSourceReverification,
    *,
    authorization_id: str,
    approved_at: datetime,
    expires_at: datetime,
) -> TogetherCatalogPreflightAuthorization:
    expected_suite = (
        suite.suite_id,
        suite.suite_version,
        content_sha256(suite),
    )
    if (
        account_attestation.together_suite_id,
        account_attestation.together_suite_version,
        account_attestation.together_suite_sha256,
    ) != expected_suite:
        raise ValueError("Together account attestation binds another suite")
    if account_attestation.provider_terms_sha256 != content_sha256(
        suite.provider_terms
    ):
        raise ValueError("Together account attestation binds other terms")
    validate_public_source_reverification(suite, public_sources)
    return TogetherCatalogPreflightAuthorization(
        authorization_id=authorization_id,
        authorization_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        account_privacy_attestation_sha256=content_sha256(account_attestation),
        public_source_reverification_sha256=content_sha256(public_sources),
        approved_at=approved_at,
        expires_at=expires_at,
    )


def _validate_catalog_authorization(
    suite: Phase4TogetherSuite,
    account_attestation: TogetherAccountPrivacyAttestation,
    public_sources: TogetherPublicSourceReverification,
    authorization: TogetherCatalogPreflightAuthorization,
    *,
    now: datetime,
) -> None:
    _require_aware(now, "Together catalog preflight now")
    if not authorization.approved_at <= now <= authorization.expires_at:
        raise ValueError("Together catalog preflight authorization is not active")
    if (
        authorization.together_suite_id,
        authorization.together_suite_version,
        authorization.together_suite_sha256,
    ) != (suite.suite_id, suite.suite_version, content_sha256(suite)):
        raise ValueError("Together catalog authorization binds another suite")
    if authorization.account_privacy_attestation_sha256 != content_sha256(
        account_attestation
    ):
        raise ValueError("Together catalog authorization binds another account check")
    validate_public_source_reverification(suite, public_sources)
    if authorization.public_source_reverification_sha256 != content_sha256(
        public_sources
    ):
        raise ValueError("Together catalog authorization binds other source checks")


def validate_public_source_reverification(
    suite: Phase4TogetherSuite,
    receipt: TogetherPublicSourceReverification,
) -> None:
    if (
        receipt.together_suite_id,
        receipt.together_suite_version,
        receipt.together_suite_sha256,
    ) != (suite.suite_id, suite.suite_version, content_sha256(suite)):
        raise ValueError("Together source checks bind another suite")
    expected_urls = _public_source_urls(suite)
    actual_urls = {item.source_url for item in receipt.source_checks}
    if actual_urls != expected_urls or len(actual_urls) != len(
        receipt.source_checks
    ):
        raise ValueError("Together source checks must cover every public source")


def _public_source_urls(suite: Phase4TogetherSuite) -> set[str]:
    return {
        suite.catalog.source_url,
        suite.provider_terms.privacy_source_url,
        suite.provider_terms.parameters_source_url,
        suite.provider_terms.structured_outputs_source_url,
        *(
            artifact.weight_manifest.revision_tree_url
            for artifact in suite.candidates
        ),
        *(
            artifact.license_provenance.license_source_url
            for artifact in suite.candidates
        ),
    }


def fetch_public_source_reverification(
    suite: Phase4TogetherSuite,
    *,
    client: httpx.Client,
    receipt_id: str,
    checked_at: datetime,
) -> TogetherPublicSourceReverification:
    """Re-fetch every suite URL without attaching provider credentials."""

    _require_aware(checked_at, "Together public-source checked_at")
    checks: list[TogetherPublicSourceCheck] = []
    for url in sorted(_public_source_urls(suite)):
        response = client.get(
            url,
            headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(
                "Together public-source revalidation failed with HTTP "
                f"{response.status_code}"
            )
        checks.append(
            TogetherPublicSourceCheck(
                source_url=url,
                response_sha256=sha256(response.content).hexdigest(),
            )
        )
    receipt = TogetherPublicSourceReverification(
        receipt_id=receipt_id,
        receipt_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        checked_at=checked_at,
        source_checks=checks,
    )
    validate_public_source_reverification(suite, receipt)
    return receipt


def _required_context_window_tokens(suite: Phase4TogetherSuite) -> int:
    return max(
        item.input_tokens_per_request + item.output_tokens_per_request
        for envelope in (
            suite.workload.qualification_per_candidate,
            suite.workload.held_out_selected_candidate,
        )
        for item in envelope.role_usage
    )


def build_catalog_preflight_receipt(
    suite: Phase4TogetherSuite,
    authorization: TogetherCatalogPreflightAuthorization,
    live_model_payload: JsonValue,
    *,
    receipt_id: str,
    checked_at: datetime,
) -> TogetherCatalogPreflightReceipt:
    rows_payload: JsonValue = live_model_payload
    if isinstance(live_model_payload, dict) and "data" in live_model_payload:
        rows_payload = live_model_payload["data"]
    raw_rows = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        rows_payload
    )
    expected_model_ids = {
        artifact.candidate.serving_model_id for artifact in suite.candidates
    }
    candidate_rows = [
        row for row in raw_rows if row.get("id") in expected_model_ids
    ]
    rows = TypeAdapter(list[_TogetherModelRow]).validate_python(candidate_rows)
    rows_by_id = {item.id: item for item in rows}
    if len(rows_by_id) != len(rows):
        raise ValueError("Together live model list contains duplicate ids")
    required_context_window_tokens = _required_context_window_tokens(suite)
    checks: list[TogetherCatalogCandidateCheck] = []
    for artifact in suite.candidates:
        candidate = artifact.candidate
        live = rows_by_id.get(candidate.serving_model_id)
        if live is None:
            raise ValueError("Together live model list is missing a candidate")
        input_price = _usd_per_million_to_microusd(live.pricing.input)
        output_price = _usd_per_million_to_microusd(live.pricing.output)
        if (
            input_price != artifact.price_card.input_microusd_per_million_tokens
            or output_price
            != artifact.price_card.output_microusd_per_million_tokens
        ):
            raise ValueError("Together live candidate metadata differs from suite")
        if live.context_length < required_context_window_tokens:
            raise ValueError(
                "Together live candidate context cannot fit the study workload"
            )
        checks.append(
            TogetherCatalogCandidateCheck(
                candidate_id=candidate.candidate_id,
                candidate_sha256=content_sha256(candidate),
                serving_model_id=candidate.serving_model_id,
                advertised_context_window_tokens=(
                    candidate.context_window_tokens
                ),
                live_context_window_tokens=live.context_length,
                required_context_window_tokens=required_context_window_tokens,
                input_microusd_per_million_tokens=input_price,
                output_microusd_per_million_tokens=output_price,
            )
        )
    checks.sort(key=lambda item: item.candidate_id)
    return TogetherCatalogPreflightReceipt(
        receipt_id=receipt_id,
        receipt_version=1,
        together_suite_id=suite.suite_id,
        together_suite_version=suite.suite_version,
        together_suite_sha256=content_sha256(suite),
        authorization_sha256=content_sha256(authorization),
        live_model_list_sha256=content_sha256(live_model_payload),
        checked_at=checked_at,
        candidate_checks=checks,
    )


def validate_catalog_preflight_bundle(
    suite: Phase4TogetherSuite,
    bundle: TogetherCatalogPreflightBundle,
) -> None:
    _validate_catalog_authorization(
        suite,
        bundle.account_privacy_attestation,
        bundle.public_source_reverification,
        bundle.authorization,
        now=bundle.receipt.checked_at,
    )
    if bundle.receipt.authorization_sha256 != content_sha256(
        bundle.authorization
    ):
        raise ValueError("Together catalog receipt authorization differs")
    if (
        bundle.receipt.together_suite_id,
        bundle.receipt.together_suite_version,
        bundle.receipt.together_suite_sha256,
    ) != (suite.suite_id, suite.suite_version, content_sha256(suite)):
        raise ValueError("Together catalog receipt binds another suite")
    expected_checks = {
        artifact.candidate.candidate_id: (
            content_sha256(artifact.candidate),
            artifact.candidate.serving_model_id,
            artifact.candidate.context_window_tokens,
            _required_context_window_tokens(suite),
            artifact.price_card.input_microusd_per_million_tokens,
            artifact.price_card.output_microusd_per_million_tokens,
        )
        for artifact in suite.candidates
    }
    actual_checks = {
        item.candidate_id: (
            item.candidate_sha256,
            item.serving_model_id,
            item.advertised_context_window_tokens,
            item.required_context_window_tokens,
            item.input_microusd_per_million_tokens,
            item.output_microusd_per_million_tokens,
        )
        for item in bundle.receipt.candidate_checks
    }
    if actual_checks != expected_checks:
        raise ValueError("Together catalog receipt candidate checks differ")


class TogetherCatalogPreflightClient:
    """One-shot authenticated GET client; it cannot invoke inference."""

    def __init__(
        self,
        suite: Phase4TogetherSuite,
        account_attestation: TogetherAccountPrivacyAttestation,
        public_sources: TogetherPublicSourceReverification,
        authorization: TogetherCatalogPreflightAuthorization,
        api_key: SecretStr,
        *,
        client: httpx.Client,
        now: datetime,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        _validate_catalog_authorization(
            suite,
            account_attestation,
            public_sources,
            authorization,
            now=now,
        )
        if not api_key.get_secret_value():
            raise ValueError("Together API key is empty")
        self._suite = suite.model_copy(deep=True)
        self._authorization = authorization.model_copy(deep=True)
        self._api_key = api_key
        self._client = client
        self._used = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        receipt_id: str,
    ) -> TogetherCatalogPreflightReceipt:
        if self._used:
            raise ValueError("Together catalog preflight authorization is spent")
        checked_at = self._clock()
        if not (
            self._authorization.approved_at
            <= checked_at
            <= self._authorization.expires_at
        ):
            raise ValueError("Together catalog preflight authorization is not active")
        self._used = True
        response = self._client.get(
            f"{self._suite.api_base_url}/models",
            headers={
                "Authorization": (
                    f"Bearer {self._api_key.get_secret_value()}"
                ),
                "Accept": "application/json",
            },
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise ValueError(
                "Together catalog preflight failed with HTTP "
                f"{response.status_code}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            raise ValueError("Together catalog response was not JSON") from error
        return build_catalog_preflight_receipt(
            self._suite,
            self._authorization,
            payload,
            receipt_id=receipt_id,
            checked_at=checked_at,
        )


def validate_token_readiness_and_headroom(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    projection: TogetherTokenReadinessReceipt,
    headroom: TogetherHeadroomPolicy,
) -> None:
    if (
        projection.together_suite_id,
        projection.together_suite_version,
        projection.together_suite_sha256,
        projection.workload_sha256,
    ) != (
        suite.suite_id,
        suite.suite_version,
        content_sha256(suite),
        content_sha256(suite.workload),
    ):
        raise ValueError("Together token readiness binds another suite")
    artifacts = {item.candidate.candidate_id: item for item in suite.candidates}
    projections = {
        item.candidate_id: item for item in projection.candidate_projections
    }
    if set(projections) != set(artifacts):
        raise ValueError("Together token readiness must cover every candidate")
    qualification_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.QUALIFICATION
    ]
    qualification_request_count = sum(
        item.request_count
        for item in suite.workload.qualification_per_candidate.role_usage
    )
    held_out_request_count = sum(
        item.request_count
        for item in suite.workload.held_out_selected_candidate.role_usage
    )
    qualification_cost = 0
    qualification_max_reservation = 0
    held_out_cap = profile.budget_policy.segment_caps_microusd[
        BudgetSegment.HELD_OUT_STUDY
    ]
    if (
        headroom.qualification_cap_microusd != qualification_cap
        or headroom.held_out_cap_microusd != held_out_cap
    ):
        raise ValueError("Together headroom policy caps differ from profile")
    for candidate_id, item in projections.items():
        candidate = artifacts[candidate_id].candidate
        if item.candidate_sha256 != content_sha256(candidate):
            raise ValueError("Together token-readiness candidate hash differs")
        if (
            item.qualification_request_count != qualification_request_count
            or item.held_out_calibration_request_count != held_out_request_count
        ):
            raise ValueError("Together token-readiness request counts differ")
        price_card = artifacts[candidate_id].price_card
        qualification_single_call = max(
            price_provider_tokens(
                price_card,
                input_tokens=usage.input_tokens_per_request,
                output_tokens=usage.output_tokens_per_request,
            )
            for usage in suite.workload.qualification_per_candidate.role_usage
        )
        held_out_single_call = max(
            price_provider_tokens(
                price_card,
                input_tokens=usage.input_tokens_per_request,
                output_tokens=usage.output_tokens_per_request,
            )
            for usage in suite.workload.held_out_selected_candidate.role_usage
        )
        if (
            item.qualification_max_single_call_authorization_microusd
            != qualification_single_call
            or item.held_out_max_single_call_authorization_microusd
            != held_out_single_call
        ):
            raise ValueError("Together maximum reservation does not reconcile")
        qualification_bounds = _projection_cost_bounds(
            price_card.input_microusd_per_million_tokens,
            price_card.output_microusd_per_million_tokens,
            price_card.fixed_request_cost_microusd,
            request_count=item.qualification_request_count,
            input_tokens=item.qualification_input_token_count,
            output_tokens=item.qualification_output_token_upper_bound_count,
        )
        held_out_bounds = _projection_cost_bounds(
            price_card.input_microusd_per_million_tokens,
            price_card.output_microusd_per_million_tokens,
            price_card.fixed_request_cost_microusd,
            request_count=item.held_out_calibration_request_count,
            input_tokens=item.held_out_input_token_count,
            output_tokens=item.held_out_output_token_upper_bound_count,
        )
        if not (
            qualification_bounds[0]
            <= item.qualification_projected_cost_microusd
            <= qualification_bounds[1]
        ) or not (
            held_out_bounds[0]
            <= item.held_out_projected_cost_microusd
            <= held_out_bounds[1]
        ):
            raise ValueError("Together token-readiness cost does not reconcile")
        qualification_cost += item.qualification_projected_cost_microusd
        qualification_max_reservation = max(
            qualification_max_reservation,
            qualification_single_call,
        )
        if (
            held_out_cap
            - item.held_out_projected_cost_microusd
            - held_out_single_call
            < headroom.held_out_minimum_headroom_microusd
        ):
            raise ValueError("Together held-out sequential plan lacks headroom")
    if (
        qualification_cap - qualification_cost - qualification_max_reservation
        < headroom.qualification_minimum_headroom_microusd
    ):
        raise ValueError("Together qualification sequential plan lacks headroom")


def _projection_cost_bounds(
    input_rate: int,
    output_rate: int,
    fixed_request_cost: int,
    *,
    request_count: int,
    input_tokens: int,
    output_tokens: int,
) -> tuple[int, int]:
    """Bound the sum of per-request ceil pricing from exact token totals."""

    def rounded_component(tokens: int, rate: int) -> int:
        return (tokens * rate + 999_999) // 1_000_000

    minimum = (
        request_count * fixed_request_cost
        + rounded_component(input_tokens, input_rate)
        + rounded_component(output_tokens, output_rate)
    )
    maximum = minimum + 2 * max(0, request_count - 1)
    return minimum, maximum


def validate_live_authorization(
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    catalog_bundle: TogetherCatalogPreflightBundle,
    projection: TogetherTokenReadinessReceipt,
    headroom: TogetherHeadroomPolicy,
    authorization: TogetherLiveAuthorization,
    *,
    capability_receipt: TogetherCapabilityPreflightReceipt | None,
    now: datetime,
) -> None:
    _require_aware(now, "Together live authorization now")
    if not authorization.approved_at <= now <= authorization.expires_at:
        raise ValueError("Together live authorization is not active")
    suite_binding = (suite.suite_id, suite.suite_version, content_sha256(suite))
    if (
        authorization.together_suite_id,
        authorization.together_suite_version,
        authorization.together_suite_sha256,
    ) != suite_binding:
        raise ValueError("Together live authorization binds another suite")
    if authorization.robustness_profile_sha256 != content_sha256(profile):
        raise ValueError("Together live authorization binds another profile")
    expected_segment_cap = profile.budget_policy.segment_caps_microusd[
        authorization.budget_segment
    ]
    if authorization.approved_max_spend_microusd != expected_segment_cap:
        raise ValueError("Together live authorization segment cap differs")
    validate_catalog_preflight_bundle(suite, catalog_bundle)
    expected_hashes = (
        content_sha256(catalog_bundle.account_privacy_attestation),
        content_sha256(catalog_bundle.receipt),
        content_sha256(projection),
        content_sha256(headroom),
    )
    actual_hashes = (
        authorization.account_privacy_attestation_sha256,
        authorization.catalog_preflight_receipt_sha256,
        authorization.token_readiness_receipt_sha256,
        authorization.headroom_policy_sha256,
    )
    if actual_hashes != expected_hashes:
        raise ValueError("Together live authorization artifact hashes differ")
    candidate_ids = sorted(
        item.candidate.candidate_id for item in suite.candidates
    )
    if authorization.stage is TogetherPaidStage.QUALIFICATION:
        if authorization.authorized_candidate_ids != candidate_ids:
            raise ValueError(
                "Together qualification authorization must cover exact candidates"
            )
        if capability_receipt is None or (
            authorization.capability_preflight_receipt_sha256
            != content_sha256(capability_receipt)
        ):
            raise ValueError("Together qualification lacks capability receipt")
        expected_checks = {
            (candidate_id, role)
            for candidate_id in candidate_ids
            for role in LLMRole
        }
        actual_checks = {
            (item.candidate_id, item.role) for item in capability_receipt.checks
        }
        if actual_checks != expected_checks:
            raise ValueError("Together capability receipt matrix is incomplete")
        if (
            capability_receipt.together_suite_id,
            capability_receipt.together_suite_version,
            capability_receipt.together_suite_sha256,
            capability_receipt.robustness_profile_sha256,
        ) != (
            suite.suite_id,
            suite.suite_version,
            content_sha256(suite),
            content_sha256(profile),
        ):
            raise ValueError("Together capability receipt bindings differ")
    else:
        if not authorization.authorized_candidate_ids or not set(
            authorization.authorized_candidate_ids
        ) <= set(candidate_ids):
            raise ValueError(
                "Together capability authorization candidates must be a "
                "nonempty suite subset"
            )
        if capability_receipt is not None:
            raise ValueError(
                "Together capability authorization cannot consume receipt"
            )
    validate_token_readiness_and_headroom(suite, profile, projection, headroom)


def _seed_status(
    request: PrivateStructuredProviderRequest,
    choices: list[_TogetherChoice],
) -> ProviderSeedStatus:
    if not request.binding.provider_seed_parameter_sent:
        return ProviderSeedStatus.NOT_SENT
    if choices and all(
        item.seed == request.binding.request_seed for item in choices
    ):
        return ProviderSeedStatus.PROVIDER_CONFIRMED
    return ProviderSeedStatus.SENT_UNCONFIRMED


class TogetherHTTPTransport:
    """Authorized synchronous Together chat transport with a bounded tool loop."""

    def __init__(
        self,
        suite: Phase4TogetherSuite,
        profile: Phase4ERobustnessProfile,
        catalog_bundle: TogetherCatalogPreflightBundle,
        projection: TogetherTokenReadinessReceipt,
        headroom: TogetherHeadroomPolicy,
        authorization: TogetherLiveAuthorization,
        api_key: SecretStr,
        *,
        client: httpx.Client,
        token_counter: TogetherTokenCounter,
        capability_receipt: TogetherCapabilityPreflightReceipt | None = None,
        tool_executor: TogetherToolExecutor | None = None,
        now: datetime,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        validate_live_authorization(
            suite,
            profile,
            catalog_bundle,
            projection,
            headroom,
            authorization,
            capability_receipt=capability_receipt,
            now=now,
        )
        if not api_key.get_secret_value():
            raise ValueError("Together API key is empty")
        if max_tool_rounds != DEFAULT_MAX_TOOL_ROUNDS:
            raise ValueError("Together max tool rounds differ from readiness")
        self._suite = suite.model_copy(deep=True)
        self._authorization = authorization.model_copy(deep=True)
        self._api_key = api_key
        self._client = client
        self._token_counter = token_counter
        self._projection_by_candidate = {
            item.candidate_id: item for item in projection.candidate_projections
        }
        self._tool_executor = tool_executor
        self._max_tool_rounds = max_tool_rounds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def validate_execution(
        self,
        request: PrivateStructuredProviderRequest,
        *,
        segment: BudgetSegment,
    ) -> None:
        binding = request.binding
        observed_at = self._clock()
        _require_aware(observed_at, "Together transport execution time")
        if not (
            self._authorization.approved_at
            <= observed_at
            <= self._authorization.expires_at
        ):
            raise ValueError("Together live authorization is not active")
        if segment is not self._authorization.budget_segment:
            raise ValueError("Together request uses an unauthorized budget segment")
        if binding.data_scope is not ProviderDataScope.PUBLIC_DEVELOPMENT:
            raise ValueError("Together qualification transport is public-only")
        if binding.model_candidate_id not in (
            self._authorization.authorized_candidate_ids
        ):
            raise ValueError("Together request uses an unauthorized candidate")
        if binding.role not in self._authorization.authorized_roles:
            raise ValueError("Together request uses an unauthorized role")
        if binding.robustness_profile_sha256 != (
            self._authorization.robustness_profile_sha256
        ):
            raise ValueError("Together request uses an unauthorized profile")
        initial_payload = build_together_chat_payload(self._suite, request)
        count = self._count_payload(request, initial_payload)
        if count.input_token_count > binding.input_token_upper_bound:
            raise ValueError("Together exact input count exceeds request bound")

    def _count_payload(
        self,
        request: PrivateStructuredProviderRequest,
        payload: dict[str, JsonValue],
    ) -> TogetherPayloadTokenCount:
        candidate_id = request.binding.model_candidate_id
        count = self._token_counter.count_payload(candidate_id, payload)
        projection = self._projection_by_candidate[candidate_id]
        expected = (
            candidate_id,
            request.binding.model_candidate_sha256,
            projection.tokenizer_id,
            projection.tokenizer_version,
            projection.tokenizer_artifact_sha256,
            content_sha256(payload),
        )
        actual = (
            count.candidate_id,
            count.candidate_sha256,
            count.tokenizer_id,
            count.tokenizer_version,
            count.tokenizer_artifact_sha256,
            count.payload_sha256,
        )
        if actual != expected:
            raise ValueError("Together exact token count binding differs")
        return count

    def _post(self, payload: dict[str, JsonValue]) -> httpx.Response:
        try:
            return self._client.post(
                (
                    f"{self._suite.api_base_url}"
                    f"{self._suite.chat_completions_path}"
                ),
                headers={
                    "Authorization": (
                        f"Bearer {self._api_key.get_secret_value()}"
                    ),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise ConnectionError("Together connection failed before send") from error

    def invoke(
        self,
        request: PrivateStructuredProviderRequest,
    ) -> ProviderTransportResult:
        started = time.perf_counter()
        payload = build_together_chat_payload(self._suite, request)
        total_input = 0
        total_output = 0
        request_ids: list[str] = []
        choices_seen: list[_TogetherChoice] = []
        tool_call_count = 0
        tool_call_failure_count = 0
        cumulative_local_input_tokens = 0
        allowed_tool_names = {
            str(item["name"]) for item in request.tool_definitions
        }
        for tool_round in range(self._max_tool_rounds + 1):
            local_count = self._count_payload(request, payload)
            cumulative_local_input_tokens += local_count.input_token_count
            if (
                cumulative_local_input_tokens
                > request.binding.input_token_upper_bound
            ):
                if not request_ids:
                    raise ValueError(
                        "Together exact input count exceeds request bound"
                    )
                return ProviderTransportResult(
                    outcome=ProviderCallOutcome.TRANSPORT_ERROR,
                    output_payload=None,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    provider_request_id="|".join(request_ids),
                    provider_request_sent=True,
                    provider_seed_status=_seed_status(request, choices_seen),
                    tool_call_count=tool_call_count,
                    tool_call_failure_count=tool_call_failure_count,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_code="together_followup_input_bound_exceeded",
                    completed_at=self._clock(),
                )
            try:
                response = self._post(payload)
            except ConnectionError:
                if request_ids:
                    raise TogetherAmbiguousDeliveryError(
                        request.binding.call_id,
                        "together_followup_connect_error",
                    )
                completed = self._clock()
                return ProviderTransportResult(
                    outcome=ProviderCallOutcome.TRANSPORT_ERROR,
                    output_payload=None,
                    input_tokens=0,
                    output_tokens=0,
                    provider_request_id=None,
                    provider_request_sent=False,
                    provider_seed_status=ProviderSeedStatus.NOT_SENT,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_code="together_connect_error",
                    completed_at=completed,
                )
            except (httpx.ReadTimeout, httpx.RemoteProtocolError) as error:
                raise TogetherAmbiguousDeliveryError(
                    request.binding.call_id,
                    "together_response_ambiguous",
                ) from error
            if response.status_code < 200 or response.status_code >= 300:
                return ProviderTransportResult(
                    outcome=ProviderCallOutcome.PROVIDER_ERROR,
                    output_payload=None,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    provider_request_id="|".join(request_ids) or None,
                    provider_request_sent=True,
                    provider_seed_status=_seed_status(request, choices_seen),
                    tool_call_count=tool_call_count,
                    tool_call_failure_count=tool_call_failure_count,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_code=f"together_http_{response.status_code}",
                    completed_at=self._clock(),
                )
            try:
                raw_payload = response.json()
                parsed = _TogetherChatResponse.model_validate(raw_payload)
            except (json.JSONDecodeError, ValidationError, ValueError) as error:
                raise TogetherAmbiguousDeliveryError(
                    request.binding.call_id,
                    "together_response_unverifiable",
                ) from error
            total_input += parsed.usage.prompt_tokens
            total_output += parsed.usage.completion_tokens
            request_ids.append(parsed.id)
            choice = parsed.choices[0]
            choices_seen.append(choice)
            if not choice.message.tool_calls:
                if (
                    request.binding.tool_calling_enabled
                    and self._suite.suite_version
                    >= TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION
                    and tool_round == 0
                ):
                    return ProviderTransportResult(
                        outcome=ProviderCallOutcome.TRANSPORT_ERROR,
                        output_payload=None,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        provider_request_id="|".join(request_ids),
                        provider_request_sent=True,
                        provider_seed_status=_seed_status(
                            request,
                            choices_seen,
                        ),
                        tool_call_count=0,
                        tool_call_failure_count=0,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        failure_code="together_required_tool_call_missing",
                        completed_at=self._clock(),
                    )
                output: JsonValue = choice.message.content or ""
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    pass
                return ProviderTransportResult(
                    outcome=ProviderCallOutcome.SUCCESS,
                    output_payload=output,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    provider_request_id="|".join(request_ids),
                    provider_request_sent=True,
                    provider_seed_status=_seed_status(request, choices_seen),
                    tool_call_count=tool_call_count,
                    tool_call_failure_count=tool_call_failure_count,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    completed_at=self._clock(),
                )
            if tool_round >= self._max_tool_rounds:
                return ProviderTransportResult(
                    outcome=ProviderCallOutcome.TRANSPORT_ERROR,
                    output_payload=None,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    provider_request_id="|".join(request_ids),
                    provider_request_sent=True,
                    provider_seed_status=_seed_status(request, choices_seen),
                    tool_call_count=tool_call_count,
                    tool_call_failure_count=tool_call_failure_count,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    failure_code="together_tool_round_limit",
                    completed_at=self._clock(),
                )
            messages = payload.get("messages")
            if not isinstance(messages, list):
                raise ValueError("Together payload messages are malformed")
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        item.model_dump(mode="json")
                        for item in choice.message.tool_calls
                    ],
                }
            )
            for tool_call in choice.message.tool_calls:
                tool_call_count += 1
                try:
                    if (
                        self._tool_executor is None
                        or tool_call.function.name not in allowed_tool_names
                    ):
                        raise ValueError("Together tool call is not authorized")
                    arguments = json.loads(tool_call.function.arguments)
                    result = self._tool_executor.execute(
                        tool_call.function.name,
                        arguments,
                    )
                except (json.JSONDecodeError, ValidationError, ValueError):
                    tool_call_failure_count += 1
                    return ProviderTransportResult(
                        outcome=ProviderCallOutcome.TRANSPORT_ERROR,
                        output_payload=None,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        provider_request_id="|".join(request_ids),
                        provider_request_sent=True,
                        provider_seed_status=_seed_status(
                            request,
                            choices_seen,
                        ),
                        tool_call_count=tool_call_count,
                        tool_call_failure_count=tool_call_failure_count,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        failure_code="together_tool_execution_error",
                        completed_at=self._clock(),
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    }
                )
            if (
                request.binding.tool_calling_enabled
                and self._suite.suite_version
                >= TOGETHER_TWO_PHASE_INTERVIEWER_SUITE_VERSION
            ):
                payload = build_together_interviewer_final_payload(
                    self._suite,
                    request,
                    payload,
                )
        raise AssertionError("Together tool loop did not terminate")
