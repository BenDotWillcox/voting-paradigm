"""Phase 3B authoring artifacts for the final evaluation bank.

Phase 3A freezes the bank profile and final-fixture acceptance boundary.
Phase 3B uses the contracts in this module to author six-measure domain
batches without weakening that boundary.  Each authored measure carries
source-content hashes and exact claim-to-source traces; the assembler accepts
only a complete set of eight profile-conforming batches and emits the
canonical 48-measure fixture in frozen slot order.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from .bank_profile import (
    EvaluationBankProfile,
    validate_final_fixture_against_profile,
    validate_final_measure_against_profile,
)
from .contracts import (
    ContractModel,
    EvaluationFixture,
    MeasureDomain,
    MeasureSourceKind,
    MeasureVersion,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256


class SourceContentHashScope(str, Enum):
    """The exact bytes or text normalization covered by a source hash."""

    RETRIEVED_DOCUMENT_BYTES = "retrieved_document_bytes"
    NORMALIZED_RELEVANT_TEXT_UTF8 = "normalized_relevant_text_utf8"


class SourceCaptureRole(str, Enum):
    """The role one captured source plays in the authored adaptation."""

    PRIMARY_OFFICIAL = "primary_official"
    OFFICIAL_CONTEXT = "official_context"
    INDEPENDENT_CONTEXT = "independent_context"


def source_content_sha256(
    content: bytes | str,
    scope: SourceContentHashScope,
) -> str:
    """Hash retrieved bytes or canonically normalized relevant source text."""

    if scope is SourceContentHashScope.RETRIEVED_DOCUMENT_BYTES:
        if not isinstance(content, bytes):
            raise TypeError(
                "retrieved_document_bytes hashing requires bytes"
            )
        payload = content
    else:
        if not isinstance(content, str):
            raise TypeError(
                "normalized_relevant_text_utf8 hashing requires text"
            )
        normalized = unicodedata.normalize(
            "NFC",
            content.replace("\r\n", "\n").replace("\r", "\n"),
        )
        payload = normalized.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SourceCaptureRecord(ContractModel):
    """Bind one packet source record to content observed during authoring."""

    record_version: Literal["source_capture.v1"] = "source_capture.v1"
    source_id: StableId
    source_record_sha256: Sha256Digest
    source_role: SourceCaptureRole
    captured_at: datetime
    retrieved_content_sha256: Sha256Digest
    content_hash_scope: SourceContentHashScope
    locator_notes: NonEmptyText

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return value


class ContentTraceRecord(ContractModel):
    """Trace one exact authored string to sources or jurisdiction facts."""

    record_version: Literal["content_trace.v1"] = "content_trace.v1"
    trace_id: StableId
    content_path: str = Field(min_length=2, pattern=r"^/")
    adapted_text: NonEmptyText
    source_ids: list[StableId] = Field(default_factory=list)
    jurisdiction_fact_keys: list[StableId] = Field(default_factory=list)
    adaptation_notes: NonEmptyText

    @model_validator(mode="after")
    def require_unique_evidence_and_a_ground(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("content-trace source ids must be unique")
        if len(self.jurisdiction_fact_keys) != len(
            set(self.jurisdiction_fact_keys)
        ):
            raise ValueError(
                "content-trace jurisdiction fact keys must be unique"
            )
        if not self.source_ids and not self.jurisdiction_fact_keys:
            raise ValueError(
                "content trace requires a packet source or jurisdiction fact"
            )
        return self


class MeasureSourceEvidence(ContractModel):
    """Durable source captures and exact adapted-text traces for one measure."""

    record_version: Literal["measure_source_evidence.v1"] = (
        "measure_source_evidence.v1"
    )
    measure_id: StableId
    measure_version: PositiveVersion
    measure_sha256: Sha256Digest
    source_captures: list[SourceCaptureRecord] = Field(min_length=1)
    content_traces: list[ContentTraceRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_bindings(self) -> Self:
        source_ids = [
            capture.source_id for capture in self.source_captures
        ]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source-capture ids must be unique")
        trace_ids = [trace.trace_id for trace in self.content_traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("content-trace ids must be unique")
        return self


def _json_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _participant_text_pointer(pointer: str) -> bool:
    tokens = [
        _json_pointer_token(token)
        for token in pointer.removeprefix("/").split("/")
    ]
    if tokens == ["title"]:
        return True
    if (
        len(tokens) == 3
        and tokens[0] == "options"
        and tokens[1].isdigit()
        and tokens[2] in {"label", "description"}
    ):
        return True
    if len(tokens) == 2 and tokens[0] == "packet":
        return tokens[1] in {
            "status_quo",
            "proposal",
            "who_is_affected",
            "fiscal_or_operational_effects",
        }
    if len(tokens) == 3 and tokens[:2] == [
        "packet",
        "arguments_by_option",
    ]:
        return True
    if (
        len(tokens) == 3
        and tokens[:2] == ["packet", "uncertainties"]
        and tokens[2].isdigit()
    ):
        return True
    if (
        len(tokens) == 3
        and tokens[:2] == ["packet", "definitions"]
    ):
        return True
    return False


def _resolve_json_pointer(document: JsonValue, pointer: str) -> JsonValue:
    current = document
    for raw_token in pointer.removeprefix("/").split("/"):
        token = _json_pointer_token(raw_token)
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(
                    f"content trace points to unknown key {token!r}"
                )
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
            except ValueError as error:
                raise ValueError(
                    f"content trace list index is not an integer: {token!r}"
                ) from error
            if index < 0 or index >= len(current):
                raise ValueError(
                    f"content trace list index is out of range: {index}"
                )
            current = current[index]
        else:
            raise ValueError(
                "content trace traverses through a non-container value"
            )
    return current


def validate_measure_source_evidence(
    evidence: MeasureSourceEvidence,
    measure: MeasureVersion,
    *,
    jurisdiction_fact_keys: set[str] | None = None,
) -> None:
    """Validate exact measure, source, and participant-facing text bindings."""

    if (
        evidence.measure_id,
        evidence.measure_version,
        evidence.measure_sha256,
    ) != (
        measure.measure_id,
        measure.version,
        content_sha256(measure),
    ):
        raise ValueError("source evidence does not match the exact measure")

    source_ids = [
        source.source_id for source in measure.packet.sources
    ]
    capture_ids = [
        capture.source_id for capture in evidence.source_captures
    ]
    source_by_id = {
        source.source_id: source for source in measure.packet.sources
    }
    capture_by_id = {
        capture.source_id: capture
        for capture in evidence.source_captures
    }
    if capture_ids != source_ids:
        raise ValueError(
            "source evidence must capture every packet source exactly once "
            "in packet order"
        )
    for source_id, capture in capture_by_id.items():
        source = source_by_id[source_id]
        if capture.source_record_sha256 != content_sha256(source):
            raise ValueError(
                f"source capture {source_id} does not match its source record"
            )
        if source.accessed_date is None:
            raise ValueError(
                f"packet source {source_id} lacks an accessed_date"
            )
        if capture.captured_at.date() != source.accessed_date:
            raise ValueError(
                f"source capture {source_id} date does not match "
                "source accessed_date"
            )

    measure_document = measure.model_dump(mode="json")
    traced_source_ids: set[str] = set()
    for trace in evidence.content_traces:
        if not _participant_text_pointer(trace.content_path):
            raise ValueError(
                f"content trace {trace.trace_id} must point to an exact "
                "participant-facing text field"
            )
        unknown_sources = set(trace.source_ids) - set(source_by_id)
        if unknown_sources:
            raise ValueError(
                f"content trace {trace.trace_id} references unknown packet "
                f"sources: {sorted(unknown_sources)}"
            )
        if jurisdiction_fact_keys is not None:
            unknown_fact_keys = (
                set(trace.jurisdiction_fact_keys)
                - jurisdiction_fact_keys
            )
            if unknown_fact_keys:
                raise ValueError(
                    f"content trace {trace.trace_id} references unknown "
                    f"jurisdiction facts: {sorted(unknown_fact_keys)}"
                )
        traced_value = _resolve_json_pointer(
            measure_document,
            trace.content_path,
        )
        if not isinstance(traced_value, str):
            raise ValueError(
                f"content trace {trace.trace_id} must resolve to text"
            )
        if traced_value != trace.adapted_text:
            raise ValueError(
                f"content trace {trace.trace_id} does not preserve the exact "
                "adapted text"
            )
        traced_source_ids.update(trace.source_ids)

    if traced_source_ids != set(source_by_id):
        missing = sorted(set(source_by_id) - traced_source_ids)
        raise ValueError(
            "every packet source must support at least one exact content "
            f"trace; missing={missing}"
        )


class DomainBankBatchItem(ContractModel):
    """One frozen profile slot, authored measure, and its source evidence."""

    record_version: Literal["preference_eval_domain_batch_item.v1"] = (
        "preference_eval_domain_batch_item.v1"
    )
    slot_id: StableId
    measure: MeasureVersion
    source_evidence: MeasureSourceEvidence

    @model_validator(mode="after")
    def validate_local_bindings(self) -> Self:
        validate_measure_source_evidence(
            self.source_evidence,
            self.measure,
        )
        return self


class DomainBankBatch(ContractModel):
    """Six exact measures authored for one frozen profile domain."""

    schema_version: Literal["preference_eval_domain_batch.v1"] = (
        "preference_eval_domain_batch.v1"
    )
    batch_id: StableId
    batch_version: PositiveVersion
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    domain: MeasureDomain
    authored_at: datetime
    items: list[DomainBankBatchItem] = Field(
        min_length=6,
        max_length=6,
    )

    @field_validator("authored_at")
    @classmethod
    def authored_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authored_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_domain_bindings(self) -> Self:
        slot_ids = [item.slot_id for item in self.items]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("domain-batch slot ids must be unique")
        measure_refs = [
            (item.measure.measure_id, item.measure.version)
            for item in self.items
        ]
        if len(measure_refs) != len(set(measure_refs)):
            raise ValueError(
                "domain-batch measure id/version pairs must be unique"
            )
        if any(
            item.measure.domain is not self.domain
            for item in self.items
        ):
            raise ValueError(
                "every domain-batch measure must match the declared domain"
            )
        return self


def load_domain_bank_batch(path: str | Path) -> DomainBankBatch:
    """Load and validate one six-measure Phase 3B domain batch."""

    batch_path = Path(path)
    raw = json.loads(batch_path.read_text(encoding="utf-8"))
    return DomainBankBatch.model_validate(raw)


def validate_domain_bank_batch(
    batch: DomainBankBatch,
    profile: EvaluationBankProfile,
) -> None:
    """Validate one authored batch against its exact six frozen slots."""

    if (
        batch.profile_id,
        batch.profile_version,
        batch.profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError("domain batch does not match the bank profile")

    expected_slots = {
        slot.slot_id: slot
        for slot in profile.slots
        if slot.domain is batch.domain
    }
    item_by_slot = {item.slot_id: item for item in batch.items}
    if list(item_by_slot) != list(expected_slots):
        raise ValueError(
            "domain batch must bind the six frozen domain slots in profile "
            "order"
        )

    jurisdiction_fact_keys = {
        fact.key for fact in profile.jurisdiction.facts
    }
    for slot_id, item in item_by_slot.items():
        slot = expected_slots[slot_id]
        measure = item.measure
        if (
            measure.domain,
            measure.source_kind,
            measure.intended_generalization_tier,
            measure.ballot_type,
        ) != (
            slot.domain,
            slot.source_kind,
            slot.intended_generalization_tier,
            slot.ballot_type,
        ):
            raise ValueError(
                f"domain-batch item {slot_id} does not match its frozen "
                "slot allocation"
            )
        validate_final_measure_against_profile(measure, profile)
        validate_measure_source_evidence(
            item.source_evidence,
            measure,
            jurisdiction_fact_keys=jurisdiction_fact_keys,
        )
        if (
            measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
            and sum(
                capture.source_role
                is SourceCaptureRole.PRIMARY_OFFICIAL
                for capture in item.source_evidence.source_captures
            )
            < profile.source_policy.real_world_min_primary_official_sources
        ):
            raise ValueError(
                f"domain-batch item {slot_id} lacks the required primary "
                "official source capture"
            )


def assemble_final_fixture(
    profile: EvaluationBankProfile,
    batches: list[DomainBankBatch],
    *,
    fixture_id: StableId,
    fixture_version: PositiveVersion,
    created_at: datetime,
) -> EvaluationFixture:
    """Assemble eight reviewed batches into the canonical final fixture."""

    batch_domains = [batch.domain for batch in batches]
    if len(batch_domains) != len(set(batch_domains)):
        raise ValueError("final-bank batches must have unique domains")
    if set(batch_domains) != set(MeasureDomain):
        missing = sorted(
            domain.value
            for domain in set(MeasureDomain) - set(batch_domains)
        )
        raise ValueError(
            "final-bank assembly requires exactly one batch per domain; "
            f"missing={missing}"
        )

    item_by_slot: dict[str, DomainBankBatchItem] = {}
    measure_refs: set[tuple[str, int]] = set()
    for batch in batches:
        validate_domain_bank_batch(batch, profile)
        for item in batch.items:
            if item.slot_id in item_by_slot:
                raise ValueError(
                    f"final-bank slot is duplicated: {item.slot_id}"
                )
            measure_ref = (
                item.measure.measure_id,
                item.measure.version,
            )
            if measure_ref in measure_refs:
                raise ValueError(
                    "final-bank measure id/version pairs must be unique"
                )
            item_by_slot[item.slot_id] = item
            measure_refs.add(measure_ref)

    fixture = EvaluationFixture(
        schema_version="preference_eval_fixture.v1",
        fixture_id=fixture_id,
        fixture_version=fixture_version,
        development_only=False,
        order_seed=profile.presentation_order_policy.order_seed,
        created_at=created_at,
        jurisdiction=profile.jurisdiction,
        measures=[
            item_by_slot[slot.slot_id].measure
            for slot in profile.slots
        ],
    )
    validate_final_fixture_against_profile(fixture, profile)
    return fixture
