"""Budgeted provider execution for Phase 4E.

The Phase 4A-D role contracts deliberately stop at provider-neutral backend
protocols.  This module supplies the shared live boundary beneath those
roles: exact request bindings, privacy attestations, price-card accounting,
incremental hard-cap reservations, and explicit authorization finalization.
It contains no provider credentials, selected model, restricted packet
content, or network client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, Self

from pydantic import (
    Field,
    JsonValue,
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
)
from .fixture_io import content_sha256
from .phase4_robustness import (
    BudgetSegment,
    LLMRole,
    OpenWeightModelCandidate,
    Phase4ERobustnessProfile,
    ProviderCallAuthorization,
    ProviderCallUsage,
    ProviderUsageLedger,
    provider_committed_totals,
    validate_provider_usage_ledger,
)

Microusd = Annotated[int, Field(ge=0)]
NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]


class ProviderDataScope(str, Enum):
    PUBLIC_DEVELOPMENT = "public_development"
    PSEUDONYMOUS_PARTICIPANT = "pseudonymous_participant"


class ProviderCallOutcome(str, Enum):
    SUCCESS = "success"
    CACHE_HIT = "cache_hit"
    INVALID_OUTPUT = "invalid_output"
    PROVIDER_ERROR = "provider_error"
    TRANSPORT_ERROR = "transport_error"
    TRANSPORT_CONTRACT_ERROR = "transport_contract_error"
    TOKEN_BOUND_EXCEEDED = "token_bound_exceeded"
    CANCELLED = "cancelled"


class ProviderSeedStatus(str, Enum):
    NOT_SENT = "not_sent"
    SENT_UNCONFIRMED = "sent_unconfirmed"
    PROVIDER_CONFIRMED = "provider_confirmed"


class ProviderNoChargeBasis(str, Enum):
    NOT_SENT = "not_sent"
    PROVIDER_VOID_CONFIRMED = "provider_void_confirmed"


class ProviderPriceCard(ContractModel):
    """Exact token pricing used for both reservation and final accounting."""

    record_version: Literal["phase4_provider_price_card.v1"] = (
        "phase4_provider_price_card.v1"
    )
    price_card_id: StableId
    price_card_version: PositiveVersion
    model_candidate_id: StableId
    model_candidate_artifact_version: PositiveVersion
    model_candidate_sha256: Sha256Digest
    currency: Literal["USD"] = "USD"
    input_microusd_per_million_tokens: Microusd
    output_microusd_per_million_tokens: Microusd
    fixed_request_cost_microusd: Microusd = 0
    provider_pricing_terms_sha256: Sha256Digest
    effective_at: datetime

    @field_validator("effective_at")
    @classmethod
    def require_aware_effective_at(cls, value: datetime) -> datetime:
        _require_aware(value, "price-card effective_at")
        return value


class ProviderPrivacyAttestation(ContractModel):
    """Content-free local preflight for one exact transmitted payload."""

    record_version: Literal["phase4_provider_privacy_attestation.v1"] = (
        "phase4_provider_privacy_attestation.v1"
    )
    attestation_id: StableId
    data_scope: ProviderDataScope
    transmitted_payload_sha256: Sha256Digest
    participant_content_present: bool
    opaque_participant_id: StableId | None = None
    scanner_id: StableId | None = None
    scanner_version: PositiveVersion | None = None
    scanner_result_sha256: Sha256Digest | None = None
    direct_identifier_finding_count: NonNegativeCount = 0
    redacted_finding_count: NonNegativeCount = 0
    participant_confirmed_false_positive_count: NonNegativeCount = 0
    unresolved_finding_count: NonNegativeCount = 0
    contact_and_consent_stored_separately: Literal[True] = True
    political_identity_excluded: Literal[True] = True
    demographic_proxies_excluded: Literal[True] = True
    approved_for_transmission: Literal[True] = True

    @model_validator(mode="after")
    def require_scope_appropriate_preflight(self) -> Self:
        scanner_fields = (
            self.scanner_id,
            self.scanner_version,
            self.scanner_result_sha256,
        )
        if self.data_scope is ProviderDataScope.PUBLIC_DEVELOPMENT:
            if self.participant_content_present or self.opaque_participant_id:
                raise ValueError(
                    "public-development requests cannot carry participant identity"
                )
            if any(value is not None for value in scanner_fields) or any(
                (
                    self.direct_identifier_finding_count,
                    self.redacted_finding_count,
                    self.participant_confirmed_false_positive_count,
                    self.unresolved_finding_count,
                )
            ):
                raise ValueError(
                    "public-development attestation cannot claim participant scan"
                )
            return self
        if not self.participant_content_present:
            raise ValueError(
                "pseudonymous scope must explicitly declare participant content"
            )
        if self.opaque_participant_id is None or any(
            value is None for value in scanner_fields
        ):
            raise ValueError(
                "pseudonymous provider input requires opaque id and local scan"
            )
        if self.unresolved_finding_count != 0:
            raise ValueError(
                "provider input cannot retain unresolved identifier findings"
            )
        if (
            self.redacted_finding_count
            + self.participant_confirmed_false_positive_count
            != self.direct_identifier_finding_count
        ):
            raise ValueError(
                "identifier findings must be redacted or participant-confirmed"
            )
        return self


class ProviderNoChargeAttestation(ContractModel):
    """Auditable basis for closing one authorization at zero provider cost."""

    record_version: Literal["phase4_provider_no_charge_attestation.v1"] = (
        "phase4_provider_no_charge_attestation.v1"
    )
    attestation_id: StableId
    call_id: StableId
    basis: ProviderNoChargeBasis
    provider_confirmation_sha256: Sha256Digest | None = None
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def require_aware_confirmed_at(cls, value: datetime) -> datetime:
        _require_aware(value, "provider no-charge confirmed_at")
        return value

    @model_validator(mode="after")
    def require_evidence_for_confirmation_basis(self) -> Self:
        if self.basis is ProviderNoChargeBasis.NOT_SENT:
            if self.provider_confirmation_sha256 is not None:
                raise ValueError(
                    "not-sent no-charge attestation cannot bind provider proof"
                )
        elif self.provider_confirmation_sha256 is None:
            raise ValueError(
                "provider-void no-charge attestation requires confirmation"
            )
        return self


class ProviderRequestBinding(ContractModel):
    """Content-free exact identity of one logical provider invocation."""

    record_version: Literal["phase4_provider_request_binding.v1"] = (
        "phase4_provider_request_binding.v1"
    )
    call_id: StableId
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    model_candidate_id: StableId
    model_candidate_artifact_version: PositiveVersion
    model_candidate_sha256: Sha256Digest
    price_card_id: StableId
    price_card_version: PositiveVersion
    price_card_sha256: Sha256Digest
    role: LLMRole
    data_scope: ProviderDataScope
    privacy_attestation_sha256: Sha256Digest
    prompt_id: StableId
    prompt_version: PositiveVersion
    prompt_payload_sha256: Sha256Digest
    input_payload_sha256: Sha256Digest
    response_schema_id: StableId
    response_schema_version: PositiveVersion
    response_schema_sha256: Sha256Digest
    tool_definitions_sha256: Sha256Digest
    tool_calling_enabled: bool
    request_seed: Annotated[int, Field(ge=0)]
    provider_seed_parameter_sent: bool
    temperature: Annotated[
        float,
        Field(ge=0.0, le=2.0, allow_inf_nan=False),
    ]
    input_token_upper_bound: NonNegativeCount
    output_token_upper_bound: PositiveCount
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "provider request created_at")
        return value

    @model_validator(mode="after")
    def require_tools_only_for_interviewer(self) -> Self:
        empty_tools_sha = content_sha256([])
        if self.tool_calling_enabled:
            if self.role is not LLMRole.INTERVIEWER:
                raise ValueError(
                    "only the interviewer role may enable provider tool calling"
                )
            if self.tool_definitions_sha256 == empty_tools_sha:
                raise ValueError("tool-enabled request requires tool definitions")
        elif self.tool_definitions_sha256 != empty_tools_sha:
            raise ValueError("tool-disabled request must bind an empty tool list")
        return self


class PrivateStructuredProviderRequest(ContractModel):
    """Private transport input; never a tracked or participant-safe artifact."""

    record_version: Literal["phase4_private_provider_request.v1"] = (
        "phase4_private_provider_request.v1"
    )
    binding: ProviderRequestBinding
    privacy_attestation: ProviderPrivacyAttestation
    prompt_payload: JsonValue
    input_payload: JsonValue
    response_json_schema: dict[str, JsonValue]
    tool_definitions: list[dict[str, JsonValue]] = Field(default_factory=list)

    @model_validator(mode="after")
    def bind_every_private_component(self) -> Self:
        transmitted_hash = content_sha256(
            {
                "prompt_payload": self.prompt_payload,
                "input_payload": self.input_payload,
                "response_json_schema": self.response_json_schema,
                "tool_definitions": self.tool_definitions,
            }
        )
        if (
            self.privacy_attestation.transmitted_payload_sha256
            != transmitted_hash
        ):
            raise ValueError("privacy attestation does not bind transmitted payload")
        if self.binding.privacy_attestation_sha256 != content_sha256(
            self.privacy_attestation
        ):
            raise ValueError("provider request does not bind privacy attestation")
        expected = (
            content_sha256(self.prompt_payload),
            content_sha256(self.input_payload),
            content_sha256(self.response_json_schema),
            content_sha256(self.tool_definitions),
        )
        actual = (
            self.binding.prompt_payload_sha256,
            self.binding.input_payload_sha256,
            self.binding.response_schema_sha256,
            self.binding.tool_definitions_sha256,
        )
        if actual != expected:
            raise ValueError("provider request private hashes do not match")
        if self.binding.data_scope is not self.privacy_attestation.data_scope:
            raise ValueError("provider request and privacy scope do not match")
        return self


class ProviderTransportResult(ContractModel):
    """Provider-neutral result returned by a concrete network transport."""

    record_version: Literal["phase4_provider_transport_result.v1"] = (
        "phase4_provider_transport_result.v1"
    )
    outcome: Literal[
        ProviderCallOutcome.SUCCESS,
        ProviderCallOutcome.PROVIDER_ERROR,
        ProviderCallOutcome.TRANSPORT_ERROR,
    ]
    output_payload: JsonValue | None = None
    input_tokens: NonNegativeCount
    output_tokens: NonNegativeCount
    provider_request_id: NonEmptyText | None = None
    provider_request_sent: bool
    provider_seed_status: ProviderSeedStatus
    tool_call_count: NonNegativeCount = 0
    tool_call_failure_count: NonNegativeCount = 0
    latency_ms: NonNegativeFiniteFloat
    failure_code: StableId | None = None
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def require_aware_completed_at(cls, value: datetime) -> datetime:
        _require_aware(value, "provider transport completed_at")
        return value

    @model_validator(mode="after")
    def require_outcome_shape(self) -> Self:
        if self.tool_call_failure_count > self.tool_call_count:
            raise ValueError("tool-call failures cannot exceed tool calls")
        if self.outcome is ProviderCallOutcome.SUCCESS:
            if self.output_payload is None or self.failure_code is not None:
                raise ValueError("successful transport result is incomplete")
        elif self.output_payload is not None or self.failure_code is None:
            raise ValueError("failed transport result must be content-free")
        if not self.provider_request_sent:
            if self.outcome is not ProviderCallOutcome.TRANSPORT_ERROR:
                raise ValueError("unsent provider request must be a transport error")
            if self.provider_request_id is not None or any(
                (
                    self.input_tokens,
                    self.output_tokens,
                    self.tool_call_count,
                    self.tool_call_failure_count,
                )
            ):
                raise ValueError("unsent provider request cannot report usage")
            if self.provider_seed_status is not ProviderSeedStatus.NOT_SENT:
                raise ValueError("unsent provider request cannot report seed handling")
        return self


class ProviderTransport(Protocol):
    """Provider-specific network behavior behind the shared Phase 4 boundary."""

    def validate_execution(
        self,
        request: PrivateStructuredProviderRequest,
        *,
        segment: BudgetSegment,
    ) -> None:
        """Fail closed before the shared runtime creates a reservation."""

    def invoke(
        self,
        request: PrivateStructuredProviderRequest,
    ) -> ProviderTransportResult: ...


class ScriptedProviderTransport:
    """Deterministic no-network transport used by adapter tests."""

    def __init__(self, results: list[ProviderTransportResult]) -> None:
        self._results = [result.model_copy(deep=True) for result in results]
        self.requests: list[PrivateStructuredProviderRequest] = []

    def validate_execution(
        self,
        request: PrivateStructuredProviderRequest,
        *,
        segment: BudgetSegment,
    ) -> None:
        del request, segment

    def invoke(
        self,
        request: PrivateStructuredProviderRequest,
    ) -> ProviderTransportResult:
        self.requests.append(request.model_copy(deep=True))
        if not self._results:
            raise ValueError("scripted provider transport has no result")
        return self._results.pop(0).model_copy(deep=True)


class ProviderCallFinalization(ContractModel):
    """Explicit terminal outcome for one authorization, including zero cost."""

    record_version: Literal["phase4_provider_call_finalization.v1"] = (
        "phase4_provider_call_finalization.v1"
    )
    call_id: StableId
    request_binding_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    usage_sha256: Sha256Digest
    outcome: ProviderCallOutcome
    response_sha256: Sha256Digest | None = None
    provider_request_id_sha256: Sha256Digest | None = None
    no_charge_attestation_sha256: Sha256Digest | None = None
    provider_seed_status: ProviderSeedStatus
    tool_call_count: NonNegativeCount = 0
    tool_call_failure_count: NonNegativeCount = 0
    latency_ms: NonNegativeFiniteFloat
    failure_code: StableId | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        _require_aware(value, "provider finalization created_at")
        return value

    @model_validator(mode="after")
    def require_terminal_shape(self) -> Self:
        if self.tool_call_failure_count > self.tool_call_count:
            raise ValueError("tool-call failures cannot exceed tool calls")
        successful = {
            ProviderCallOutcome.SUCCESS,
            ProviderCallOutcome.CACHE_HIT,
        }
        if self.outcome in successful:
            if self.response_sha256 is None or self.failure_code is not None:
                raise ValueError("successful finalization is incomplete")
        elif self.response_sha256 is not None or self.failure_code is None:
            raise ValueError("failed finalization must bind a failure code only")
        if (
            self.outcome is ProviderCallOutcome.CANCELLED
            and self.provider_seed_status is not ProviderSeedStatus.NOT_SENT
        ):
            raise ValueError("cancelled call cannot claim provider seed handling")
        if self.outcome is ProviderCallOutcome.CANCELLED:
            if self.no_charge_attestation_sha256 is None:
                raise ValueError("cancelled call requires no-charge attestation")
            if self.provider_request_id_sha256 is not None:
                raise ValueError("cancelled call cannot bind a provider request id")
        elif self.no_charge_attestation_sha256 is not None:
            raise ValueError("only cancelled calls bind no-charge attestation")
        return self


class ProviderExecutionJournal(ContractModel):
    """Content-free provider request and terminal-outcome lineage."""

    schema_version: Literal["phase4_provider_execution_journal.v1"] = (
        "phase4_provider_execution_journal.v1"
    )
    journal_id: StableId
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    request_bindings: list[ProviderRequestBinding] = Field(default_factory=list)
    finalizations: list[ProviderCallFinalization] = Field(default_factory=list)
    no_charge_attestations: list[ProviderNoChargeAttestation] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def require_unique_lineage(self) -> Self:
        request_ids = [item.call_id for item in self.request_bindings]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("provider journal request call ids must be unique")
        final_ids = [item.call_id for item in self.finalizations]
        if len(final_ids) != len(set(final_ids)):
            raise ValueError("provider finalization call ids must be unique")
        if not set(final_ids) <= set(request_ids):
            raise ValueError("provider finalization requires a request binding")
        attestation_ids = [
            item.attestation_id for item in self.no_charge_attestations
        ]
        if len(attestation_ids) != len(set(attestation_ids)):
            raise ValueError("provider no-charge attestation ids must be unique")
        attestation_call_ids = [
            item.call_id for item in self.no_charge_attestations
        ]
        if len(attestation_call_ids) != len(set(attestation_call_ids)):
            raise ValueError("provider calls may have one no-charge attestation")
        if not set(attestation_call_ids) <= set(request_ids):
            raise ValueError("provider no-charge attestation requires a request")
        return self


@dataclass(frozen=True)
class ProviderExecutionResult:
    """Runtime return value; parsed output stays outside the public journal."""

    output: object | None
    finalization: ProviderCallFinalization


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


def price_provider_tokens(
    price_card: ProviderPriceCard,
    *,
    input_tokens: int,
    output_tokens: int,
) -> int:
    """Conservatively round each token component up to one microusd."""

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("provider token counts cannot be negative")
    input_numerator = (
        input_tokens * price_card.input_microusd_per_million_tokens
    )
    output_numerator = (
        output_tokens * price_card.output_microusd_per_million_tokens
    )
    input_cost = (input_numerator + 999_999) // 1_000_000
    output_cost = (output_numerator + 999_999) // 1_000_000
    return price_card.fixed_request_cost_microusd + input_cost + output_cost


def provider_request_content_sha256(binding: ProviderRequestBinding) -> str:
    """Hash provider-visible semantics without local call identity or time.

    A retry receives a new ``call_id`` and issuance time but must preserve this
    digest exactly.  The request seed remains inside the digest because it is
    part of the Phase 4D cache and sampling identity even when a provider does
    not advertise seed support.
    """

    return content_sha256(
        binding.model_dump(
            mode="json",
            exclude={"call_id", "created_at"},
        )
    )


def build_public_development_attestation(
    *,
    attestation_id: str,
    prompt_payload: JsonValue,
    input_payload: JsonValue,
    response_json_schema: dict[str, JsonValue],
    tool_definitions: list[dict[str, JsonValue]] | None = None,
) -> ProviderPrivacyAttestation:
    tools = tool_definitions or []
    return ProviderPrivacyAttestation(
        attestation_id=attestation_id,
        data_scope=ProviderDataScope.PUBLIC_DEVELOPMENT,
        transmitted_payload_sha256=content_sha256(
            {
                "prompt_payload": prompt_payload,
                "input_payload": input_payload,
                "response_json_schema": response_json_schema,
                "tool_definitions": tools,
            }
        ),
        participant_content_present=False,
    )


def prepare_provider_request(
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
    price_card: ProviderPriceCard,
    *,
    call_id: str,
    role: LLMRole,
    prompt_id: str,
    prompt_version: int,
    prompt_payload: JsonValue,
    input_payload: JsonValue,
    response_schema_id: str,
    response_schema_version: int,
    response_adapter: TypeAdapter[object],
    privacy_attestation: ProviderPrivacyAttestation,
    request_seed: int,
    provider_seed_parameter_sent: bool,
    temperature: float,
    input_token_upper_bound: int,
    output_token_upper_bound: int,
    created_at: datetime,
    tool_definitions: list[dict[str, JsonValue]] | None = None,
) -> PrivateStructuredProviderRequest:
    """Build the exact private request and its content-free audit binding."""

    if price_card.model_candidate_id != candidate.candidate_id or (
        price_card.model_candidate_artifact_version != candidate.artifact_version
    ) or price_card.model_candidate_sha256 != content_sha256(candidate):
        raise ValueError("provider price card does not bind exact candidate")
    schema = response_adapter.json_schema(mode="validation")
    tools = tool_definitions or []
    binding = ProviderRequestBinding(
        call_id=call_id,
        robustness_profile_id=profile.profile_id,
        robustness_profile_version=profile.profile_version,
        robustness_profile_sha256=content_sha256(profile),
        model_candidate_id=candidate.candidate_id,
        model_candidate_artifact_version=candidate.artifact_version,
        model_candidate_sha256=content_sha256(candidate),
        price_card_id=price_card.price_card_id,
        price_card_version=price_card.price_card_version,
        price_card_sha256=content_sha256(price_card),
        role=role,
        data_scope=privacy_attestation.data_scope,
        privacy_attestation_sha256=content_sha256(privacy_attestation),
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_payload_sha256=content_sha256(prompt_payload),
        input_payload_sha256=content_sha256(input_payload),
        response_schema_id=response_schema_id,
        response_schema_version=response_schema_version,
        response_schema_sha256=content_sha256(schema),
        tool_definitions_sha256=content_sha256(tools),
        tool_calling_enabled=bool(tools),
        request_seed=request_seed,
        provider_seed_parameter_sent=provider_seed_parameter_sent,
        temperature=temperature,
        input_token_upper_bound=input_token_upper_bound,
        output_token_upper_bound=output_token_upper_bound,
        created_at=created_at,
    )
    return PrivateStructuredProviderRequest(
        binding=binding,
        privacy_attestation=privacy_attestation,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_json_schema=schema,
        tool_definitions=tools,
    )


def validate_provider_execution_journal(
    journal: ProviderExecutionJournal,
    ledger: ProviderUsageLedger,
    profile: Phase4ERobustnessProfile,
    candidates: list[OpenWeightModelCandidate],
    price_cards: list[ProviderPriceCard],
    *,
    require_complete: bool,
) -> None:
    """Recompute every public binding and authorization terminal outcome."""

    validate_provider_usage_ledger(ledger, profile)
    profile_binding = (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    )
    if (
        journal.robustness_profile_id,
        journal.robustness_profile_version,
        journal.robustness_profile_sha256,
    ) != profile_binding:
        raise ValueError("provider journal does not bind exact profile")
    if (
        ledger.robustness_profile_id,
        ledger.robustness_profile_version,
        ledger.robustness_profile_sha256,
    ) != profile_binding:
        raise ValueError("provider ledger does not bind exact profile")

    candidate_by_id = {item.candidate_id: item for item in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ValueError("provider candidate ids must be unique")
    price_by_id = {item.price_card_id: item for item in price_cards}
    if len(price_by_id) != len(price_cards):
        raise ValueError("provider price-card ids must be unique")
    requests = {item.call_id: item for item in journal.request_bindings}
    authorizations = {item.call_id: item for item in ledger.authorizations}
    calls = {item.call_id: item for item in ledger.calls}
    finalizations = {item.call_id: item for item in journal.finalizations}
    no_charge_attestations = {
        item.call_id: item for item in journal.no_charge_attestations
    }
    if set(requests) != set(authorizations):
        raise ValueError("provider journal must bind every authorization exactly")
    if require_complete and (
        set(calls) != set(authorizations)
        or set(finalizations) != set(authorizations)
    ):
        raise ValueError("provider execution journal has outstanding calls")
    if set(calls) != set(finalizations):
        raise ValueError("provider usage and finalizations must close together")
    cancelled_ids = {
        item.call_id
        for item in journal.finalizations
        if item.outcome is ProviderCallOutcome.CANCELLED
    }
    if set(no_charge_attestations) != cancelled_ids:
        raise ValueError(
            "provider cancellations require exact no-charge attestations"
        )

    for call_id, binding in requests.items():
        candidate = candidate_by_id.get(binding.model_candidate_id)
        price_card = price_by_id.get(binding.price_card_id)
        if candidate is None or price_card is None:
            raise ValueError("provider request references unknown artifact")
        if (
            binding.model_candidate_artifact_version,
            binding.model_candidate_sha256,
        ) != (candidate.artifact_version, content_sha256(candidate)):
            raise ValueError("provider request candidate binding does not match")
        if (
            binding.price_card_version,
            binding.price_card_sha256,
            price_card.model_candidate_id,
        ) != (
            price_card.price_card_version,
            content_sha256(price_card),
            candidate.candidate_id,
        ):
            raise ValueError("provider request price-card binding does not match")
        authorization = authorizations[call_id]
        if (
            authorization.model_candidate_id,
            authorization.request_sha256,
        ) != (candidate.candidate_id, provider_request_content_sha256(binding)):
            raise ValueError("provider authorization does not bind exact request")
        call = calls.get(call_id)
        finalization = finalizations.get(call_id)
        if call is None or finalization is None:
            continue
        no_charge_attestation = no_charge_attestations.get(call_id)
        if (
            finalization.request_binding_sha256,
            finalization.authorization_sha256,
            finalization.usage_sha256,
        ) != (
            content_sha256(binding),
            content_sha256(authorization),
            content_sha256(call),
        ):
            raise ValueError("provider finalization hashes do not match lineage")
        expected_cost = price_provider_tokens(
            price_card,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
        )
        if finalization.outcome in {
            ProviderCallOutcome.CACHE_HIT,
            ProviderCallOutcome.CANCELLED,
        }:
            expected_cost = 0
        if call.billed_cost_microusd != expected_cost:
            raise ValueError("provider usage cost does not match price card")
        if call.created_at != finalization.created_at:
            raise ValueError("provider usage and finalization times do not match")
        if no_charge_attestation is not None:
            if (
                finalization.no_charge_attestation_sha256
                != content_sha256(no_charge_attestation)
                or no_charge_attestation.confirmed_at
                > finalization.created_at
                or no_charge_attestation.confirmed_at < authorization.created_at
            ):
                raise ValueError(
                    "provider no-charge attestation does not match cancellation"
                )
        if call.cache_hit != (
            finalization.outcome is ProviderCallOutcome.CACHE_HIT
        ):
            raise ValueError("provider cache outcome does not match usage")
        transport_contract_invalid = (
            binding.role is not LLMRole.INTERVIEWER
            and finalization.tool_call_count
        ) or (
            not binding.provider_seed_parameter_sent
            and finalization.provider_seed_status
            is not ProviderSeedStatus.NOT_SENT
        )
        if transport_contract_invalid and finalization.outcome not in {
            ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
            ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
        }:
            raise ValueError("provider transport-contract outcome does not match")
        if (
            not transport_contract_invalid
            and finalization.outcome
            is ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR
        ):
            raise ValueError("provider transport-contract outcome does not match")
        token_bound_exceeded = (
            call.input_tokens > binding.input_token_upper_bound
            or call.output_tokens > binding.output_token_upper_bound
        )
        if token_bound_exceeded != (
            finalization.outcome is ProviderCallOutcome.TOKEN_BOUND_EXCEEDED
        ):
            raise ValueError("provider token-bound outcome does not match usage")
        if (
            binding.provider_seed_parameter_sent
            and finalization.outcome
            in {ProviderCallOutcome.SUCCESS, ProviderCallOutcome.INVALID_OUTPUT}
            and finalization.provider_seed_status is ProviderSeedStatus.NOT_SENT
        ):
            raise ValueError("completed provider request omitted seed provenance")


class ProviderBudgetRuntime:
    """O(1) live reservations with a full-ledger audit at natural boundaries."""

    def __init__(
        self,
        profile: Phase4ERobustnessProfile,
        *,
        ledger_id: str,
        journal_id: str,
    ) -> None:
        self.profile = profile.model_copy(deep=True)
        profile_hash = content_sha256(profile)
        self._ledger = ProviderUsageLedger(
            ledger_id=ledger_id,
            robustness_profile_id=profile.profile_id,
            robustness_profile_version=profile.profile_version,
            robustness_profile_sha256=profile_hash,
        )
        self._journal = ProviderExecutionJournal(
            journal_id=journal_id,
            robustness_profile_id=profile.profile_id,
            robustness_profile_version=profile.profile_version,
            robustness_profile_sha256=profile_hash,
        )
        self._committed = {segment: 0 for segment in BudgetSegment}
        self._authorizations: dict[str, ProviderCallAuthorization] = {}
        self._calls: dict[str, ProviderCallUsage] = {}
        self._latest_event_at: datetime | None = None

    @classmethod
    def resume(
        cls,
        profile: Phase4ERobustnessProfile,
        ledger: ProviderUsageLedger,
        journal: ProviderExecutionJournal,
        candidates: list[OpenWeightModelCandidate],
        price_cards: list[ProviderPriceCard],
    ) -> ProviderBudgetRuntime:
        """Rebuild incremental state once from durable progressive artifacts."""

        validate_provider_execution_journal(
            journal,
            ledger,
            profile,
            candidates,
            price_cards,
            require_complete=False,
        )
        runtime = cls(
            profile,
            ledger_id=ledger.ledger_id,
            journal_id=journal.journal_id,
        )
        runtime._ledger = ledger.model_copy(deep=True)
        runtime._journal = journal.model_copy(deep=True)
        runtime._committed = provider_committed_totals(ledger)
        runtime._authorizations = {
            item.call_id: item for item in runtime._ledger.authorizations
        }
        runtime._calls = {item.call_id: item for item in runtime._ledger.calls}
        event_times = [
            *(item.created_at for item in runtime._ledger.authorizations),
            *(item.created_at for item in runtime._ledger.calls),
        ]
        runtime._latest_event_at = max(event_times, default=None)
        return runtime

    @property
    def committed_totals(self) -> dict[BudgetSegment, int]:
        return dict(self._committed)

    def ledger_snapshot(self) -> ProviderUsageLedger:
        return self._ledger.model_copy(deep=True)

    def journal_snapshot(self) -> ProviderExecutionJournal:
        return self._journal.model_copy(deep=True)

    def _authorize(
        self,
        request: PrivateStructuredProviderRequest,
        price_card: ProviderPriceCard,
        *,
        segment: BudgetSegment,
        retry_of_call_id: str | None,
    ) -> ProviderCallAuthorization:
        binding = request.binding
        call_id = binding.call_id
        if (
            binding.robustness_profile_id,
            binding.robustness_profile_version,
            binding.robustness_profile_sha256,
        ) != (
            self.profile.profile_id,
            self.profile.profile_version,
            content_sha256(self.profile),
        ):
            raise ValueError("provider request does not bind runtime profile")
        if (
            binding.model_candidate_id,
            binding.model_candidate_artifact_version,
            binding.model_candidate_sha256,
        ) != (
            price_card.model_candidate_id,
            price_card.model_candidate_artifact_version,
            price_card.model_candidate_sha256,
        ):
            raise ValueError("provider request and price card candidate differ")
        if call_id in self._authorizations or call_id in self._calls:
            raise ValueError("provider call id already exists")
        if (
            self._latest_event_at is not None
            and binding.created_at <= self._latest_event_at
        ):
            raise ValueError(
                "provider authorization must follow the latest runtime event"
            )
        if self._ledger.authorizations and binding.created_at <= (
            self._ledger.authorizations[-1].created_at
        ):
            raise ValueError(
                "provider authorization must follow earlier issuance time"
            )
        if retry_of_call_id is not None:
            original = self._calls.get(retry_of_call_id)
            if original is None:
                raise ValueError("provider retry must reference a closed call")
            if (
                original.model_candidate_id,
                original.request_sha256,
            ) != (
                binding.model_candidate_id,
                provider_request_content_sha256(binding),
            ):
                raise ValueError("provider retry must preserve model and request")
        maximum = price_provider_tokens(
            price_card,
            input_tokens=binding.input_token_upper_bound,
            output_tokens=binding.output_token_upper_bound,
        )
        segment_cap = self.profile.budget_policy.segment_caps_microusd[segment]
        segment_remaining = segment_cap - self._committed[segment]
        total_remaining = (
            self.profile.budget_policy.hard_total_microusd
            - sum(self._committed.values())
        )
        if maximum > segment_remaining:
            raise ValueError("provider request exceeds remaining segment budget")
        if maximum > total_remaining:
            raise ValueError("provider request exceeds remaining total budget")
        authorization = ProviderCallAuthorization(
            call_id=call_id,
            segment=segment,
            model_candidate_id=binding.model_candidate_id,
            request_sha256=provider_request_content_sha256(binding),
            retry_of_call_id=retry_of_call_id,
            authorized_max_cost_microusd=maximum,
            segment_remaining_before_microusd=segment_remaining,
            total_remaining_before_microusd=total_remaining,
            created_at=binding.created_at,
        )
        self._ledger.authorizations.append(authorization)
        self._journal.request_bindings.append(binding.model_copy(deep=True))
        self._authorizations[call_id] = authorization
        self._committed[segment] += maximum
        self._latest_event_at = binding.created_at
        return authorization

    def _finalize(
        self,
        binding: ProviderRequestBinding,
        price_card: ProviderPriceCard,
        authorization: ProviderCallAuthorization,
        *,
        outcome: ProviderCallOutcome,
        response_sha256: str | None,
        provider_request_id: str | None,
        provider_seed_status: ProviderSeedStatus,
        input_tokens: int,
        output_tokens: int,
        tool_call_count: int,
        tool_call_failure_count: int,
        latency_ms: float,
        failure_code: str | None,
        completed_at: datetime,
        no_charge_attestation: ProviderNoChargeAttestation | None = None,
    ) -> ProviderCallFinalization:
        if binding.call_id in self._calls:
            raise ValueError("provider call is already finalized")
        if completed_at < authorization.created_at:
            raise ValueError("provider finalization cannot predate authorization")
        if (
            self._latest_event_at is not None
            and completed_at < self._latest_event_at
        ):
            raise ValueError(
                "provider finalization cannot predate the latest runtime event"
            )
        token_bound_exceeded = (
            input_tokens > binding.input_token_upper_bound
            or output_tokens > binding.output_token_upper_bound
        )
        if token_bound_exceeded != (
            outcome is ProviderCallOutcome.TOKEN_BOUND_EXCEEDED
        ):
            raise ValueError("provider token-bound outcome does not match usage")
        transport_contract_invalid = bool(
            (
                binding.role is not LLMRole.INTERVIEWER
                and tool_call_count
            )
            or (
                not binding.provider_seed_parameter_sent
                and provider_seed_status is not ProviderSeedStatus.NOT_SENT
            )
        )
        if transport_contract_invalid and outcome not in {
            ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
            ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
        }:
            raise ValueError("provider transport-contract outcome does not match")
        if (
            not transport_contract_invalid
            and outcome is ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR
        ):
            raise ValueError("provider transport-contract outcome does not match")
        billed = price_provider_tokens(
            price_card,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        cache_hit = outcome is ProviderCallOutcome.CACHE_HIT
        if cache_hit or outcome is ProviderCallOutcome.CANCELLED:
            billed = 0
            input_tokens = 0
            output_tokens = 0
        if outcome is ProviderCallOutcome.CANCELLED:
            if (
                no_charge_attestation is None
                or no_charge_attestation.call_id != binding.call_id
                or no_charge_attestation.confirmed_at > completed_at
                or no_charge_attestation.confirmed_at
                < authorization.created_at
            ):
                raise ValueError(
                    "provider cancellation requires matching no-charge proof"
                )
        elif no_charge_attestation is not None:
            raise ValueError("only provider cancellations accept no-charge proof")
        usage = ProviderCallUsage(
            call_id=binding.call_id,
            segment=authorization.segment,
            model_candidate_id=binding.model_candidate_id,
            request_sha256=provider_request_content_sha256(binding),
            authorization_sha256=content_sha256(authorization),
            billed_cost_microusd=billed,
            authorization_overrun_microusd=max(
                0,
                billed - authorization.authorized_max_cost_microusd,
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cache_hit,
            retry_of_call_id=authorization.retry_of_call_id,
            created_at=completed_at,
        )
        finalization = ProviderCallFinalization(
            call_id=binding.call_id,
            request_binding_sha256=content_sha256(binding),
            authorization_sha256=content_sha256(authorization),
            usage_sha256=content_sha256(usage),
            outcome=outcome,
            response_sha256=response_sha256,
            provider_request_id_sha256=(
                content_sha256(provider_request_id)
                if provider_request_id is not None
                else None
            ),
            no_charge_attestation_sha256=(
                content_sha256(no_charge_attestation)
                if no_charge_attestation is not None
                else None
            ),
            provider_seed_status=provider_seed_status,
            tool_call_count=tool_call_count,
            tool_call_failure_count=tool_call_failure_count,
            latency_ms=latency_ms,
            failure_code=failure_code,
            created_at=completed_at,
        )
        self._ledger.calls.append(usage)
        self._journal.finalizations.append(finalization)
        if no_charge_attestation is not None:
            self._journal.no_charge_attestations.append(
                no_charge_attestation.model_copy(deep=True)
            )
        self._calls[binding.call_id] = usage
        self._committed[authorization.segment] += (
            billed - authorization.authorized_max_cost_microusd
        )
        self._latest_event_at = completed_at
        return finalization

    def execute(
        self,
        request: PrivateStructuredProviderRequest,
        price_card: ProviderPriceCard,
        response_adapter: TypeAdapter[object],
        transport: ProviderTransport,
        *,
        segment: BudgetSegment,
        retry_of_call_id: str | None = None,
    ) -> ProviderExecutionResult:
        """Reserve, invoke, validate, and close one logical model call."""

        if request.binding.price_card_sha256 != content_sha256(price_card):
            raise ValueError("provider request does not bind supplied price card")
        transport.validate_execution(request, segment=segment)
        authorization = self._authorize(
            request,
            price_card,
            segment=segment,
            retry_of_call_id=retry_of_call_id,
        )
        transport_result = transport.invoke(request)
        binding = request.binding
        if not transport_result.provider_request_sent:
            no_charge_attestation = ProviderNoChargeAttestation(
                attestation_id=f"{binding.call_id}_transport_not_sent",
                call_id=binding.call_id,
                basis=ProviderNoChargeBasis.NOT_SENT,
                confirmed_at=transport_result.completed_at,
            )
            finalization = self._finalize(
                binding,
                price_card,
                authorization,
                outcome=ProviderCallOutcome.CANCELLED,
                response_sha256=None,
                provider_request_id=None,
                provider_seed_status=ProviderSeedStatus.NOT_SENT,
                input_tokens=0,
                output_tokens=0,
                tool_call_count=0,
                tool_call_failure_count=0,
                latency_ms=transport_result.latency_ms,
                failure_code=transport_result.failure_code,
                completed_at=transport_result.completed_at,
                no_charge_attestation=no_charge_attestation,
            )
            return ProviderExecutionResult(None, finalization)
        if (
            transport_result.input_tokens > binding.input_token_upper_bound
            or transport_result.output_tokens > binding.output_token_upper_bound
        ):
            finalization = self._finalize(
                binding,
                price_card,
                authorization,
                outcome=ProviderCallOutcome.TOKEN_BOUND_EXCEEDED,
                response_sha256=None,
                provider_request_id=transport_result.provider_request_id,
                provider_seed_status=transport_result.provider_seed_status,
                input_tokens=transport_result.input_tokens,
                output_tokens=transport_result.output_tokens,
                tool_call_count=transport_result.tool_call_count,
                tool_call_failure_count=(
                    transport_result.tool_call_failure_count
                ),
                latency_ms=transport_result.latency_ms,
                failure_code="provider_token_bound_exceeded",
                completed_at=transport_result.completed_at,
            )
            return ProviderExecutionResult(None, finalization)
        transport_contract_failure_code: str | None = None
        if (
            not binding.provider_seed_parameter_sent
            and transport_result.provider_seed_status
            is not ProviderSeedStatus.NOT_SENT
        ):
            transport_contract_failure_code = "transport_seed_claim_invalid"
        elif (
            binding.role is not LLMRole.INTERVIEWER
            and transport_result.tool_call_count
        ):
            transport_contract_failure_code = "transport_tool_claim_invalid"
        if transport_contract_failure_code is not None:
            finalization = self._finalize(
                binding,
                price_card,
                authorization,
                outcome=ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR,
                response_sha256=None,
                provider_request_id=transport_result.provider_request_id,
                provider_seed_status=transport_result.provider_seed_status,
                input_tokens=transport_result.input_tokens,
                output_tokens=transport_result.output_tokens,
                tool_call_count=transport_result.tool_call_count,
                tool_call_failure_count=(
                    transport_result.tool_call_failure_count
                ),
                latency_ms=transport_result.latency_ms,
                failure_code=transport_contract_failure_code,
                completed_at=transport_result.completed_at,
            )
            return ProviderExecutionResult(None, finalization)
        if transport_result.outcome is not ProviderCallOutcome.SUCCESS:
            finalization = self._finalize(
                binding,
                price_card,
                authorization,
                outcome=transport_result.outcome,
                response_sha256=None,
                provider_request_id=transport_result.provider_request_id,
                provider_seed_status=transport_result.provider_seed_status,
                input_tokens=transport_result.input_tokens,
                output_tokens=transport_result.output_tokens,
                tool_call_count=transport_result.tool_call_count,
                tool_call_failure_count=(
                    transport_result.tool_call_failure_count
                ),
                latency_ms=transport_result.latency_ms,
                failure_code=transport_result.failure_code,
                completed_at=transport_result.completed_at,
            )
            return ProviderExecutionResult(None, finalization)
        try:
            parsed = response_adapter.validate_python(
                transport_result.output_payload
            )
            response_hash = content_sha256(parsed)
        except (ValidationError, TypeError, ValueError):
            finalization = self._finalize(
                binding,
                price_card,
                authorization,
                outcome=ProviderCallOutcome.INVALID_OUTPUT,
                response_sha256=None,
                provider_request_id=transport_result.provider_request_id,
                provider_seed_status=transport_result.provider_seed_status,
                input_tokens=transport_result.input_tokens,
                output_tokens=transport_result.output_tokens,
                tool_call_count=transport_result.tool_call_count,
                tool_call_failure_count=(
                    transport_result.tool_call_failure_count
                ),
                latency_ms=transport_result.latency_ms,
                failure_code="structured_output_invalid",
                completed_at=transport_result.completed_at,
            )
            return ProviderExecutionResult(None, finalization)
        finalization = self._finalize(
            binding,
            price_card,
            authorization,
            outcome=ProviderCallOutcome.SUCCESS,
            response_sha256=response_hash,
            provider_request_id=transport_result.provider_request_id,
            provider_seed_status=transport_result.provider_seed_status,
            input_tokens=transport_result.input_tokens,
            output_tokens=transport_result.output_tokens,
            tool_call_count=transport_result.tool_call_count,
            tool_call_failure_count=transport_result.tool_call_failure_count,
            latency_ms=transport_result.latency_ms,
            failure_code=None,
            completed_at=transport_result.completed_at,
        )
        return ProviderExecutionResult(parsed, finalization)

    def cancel(
        self,
        request: PrivateStructuredProviderRequest,
        price_card: ProviderPriceCard,
        *,
        segment: BudgetSegment,
        completed_at: datetime,
        failure_code: str = "cancelled_before_provider_send",
    ) -> ProviderCallFinalization:
        """Close an abandoned authorization without stranding its reservation."""

        authorization = self._authorize(
            request,
            price_card,
            segment=segment,
            retry_of_call_id=None,
        )
        no_charge_attestation = ProviderNoChargeAttestation(
            attestation_id=f"{request.binding.call_id}_cancelled_not_sent",
            call_id=request.binding.call_id,
            basis=ProviderNoChargeBasis.NOT_SENT,
            confirmed_at=completed_at,
        )
        return self._finalize(
            request.binding,
            price_card,
            authorization,
            outcome=ProviderCallOutcome.CANCELLED,
            response_sha256=None,
            provider_request_id=None,
            provider_seed_status=ProviderSeedStatus.NOT_SENT,
            input_tokens=0,
            output_tokens=0,
            tool_call_count=0,
            tool_call_failure_count=0,
            latency_ms=0.0,
            failure_code=failure_code,
            completed_at=completed_at,
            no_charge_attestation=no_charge_attestation,
        )

    def cancel_outstanding(
        self,
        call_id: str,
        price_card: ProviderPriceCard,
        *,
        completed_at: datetime,
        no_charge_attestation: ProviderNoChargeAttestation,
        failure_code: str = "cancelled_after_transport_abort",
    ) -> ProviderCallFinalization:
        """Close a previously issued reservation after a transport abort.

        The supplied attestation must establish that no provider charge was
        incurred. A transport that received a provider response must instead
        return a structured failure result with its observed token usage.
        """

        authorization = self._authorizations.get(call_id)
        if authorization is None or call_id in self._calls:
            raise ValueError("provider call is not an outstanding authorization")
        if no_charge_attestation.call_id != call_id:
            raise ValueError("no-charge attestation does not bind outstanding call")
        binding = next(
            item for item in self._journal.request_bindings if item.call_id == call_id
        )
        return self._finalize(
            binding,
            price_card,
            authorization,
            outcome=ProviderCallOutcome.CANCELLED,
            response_sha256=None,
            provider_request_id=None,
            provider_seed_status=ProviderSeedStatus.NOT_SENT,
            input_tokens=0,
            output_tokens=0,
            tool_call_count=0,
            tool_call_failure_count=0,
            latency_ms=0.0,
            failure_code=failure_code,
            completed_at=completed_at,
            no_charge_attestation=no_charge_attestation,
        )

    def audit(
        self,
        candidates: list[OpenWeightModelCandidate],
        price_cards: list[ProviderPriceCard],
        *,
        require_complete: bool = True,
    ) -> None:
        validate_provider_execution_journal(
            self._journal,
            self._ledger,
            self.profile,
            candidates,
            price_cards,
            require_complete=require_complete,
        )
