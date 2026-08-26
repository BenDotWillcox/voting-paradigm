"""Confirmed fixed-ontology conversational evidence for Phase 4C.

Raw conversation, LLM extraction proposals, participant decisions, and the
typed evidence consumed by preference models are separate records. Proposals
always have zero model weight. Only an explicit participant accept/edit
decision creates an eligible evidence event, and corrections append a new
event that supersedes (rather than mutates) the prior one.

This module intentionally implements only the fixed-ontology path. Expanding
ontology proposals require their own admission, duplicate, merge, shrinkage,
and prune rules and are deferred until this boundary is exercised.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from preferences.model.base import PreferenceModel
from preferences.types import Evidence, EvidenceSource, PreferenceState

from .contracts import (
    ContractModel,
    EventSequence,
    NonEmptyText,
    PositiveVersion,
    PrivateResponseText,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_interviewer import ConversationRole
from .phase4_protocol import EvidenceCondition

SliderValue = Annotated[float, Field(ge=-10.0, le=10.0, allow_inf_nan=False)]
PositiveConfidence = Annotated[float, Field(gt=0.0, le=1.0)]


class EvidenceDecisionKind(str, Enum):
    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class EvidenceOrigin(str, Enum):
    STRUCTURED = "structured"
    CONVERSATION = "conversation"


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _require_unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


def _deduplicate_in_order(values: list[str]) -> list[str]:
    """Remove repeated provider references without changing source chronology."""

    return list(dict.fromkeys(values))


class FixedOntologyReference(ContractModel):
    """Exact fixed item universe available to an extractor."""

    record_version: Literal["phase4_fixed_ontology_reference.v1"] = (
        "phase4_fixed_ontology_reference.v1"
    )
    ontology_id: StableId
    ontology_version: PositiveVersion
    item_ids: list[StableId]
    item_ids_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_items(self) -> Self:
        if not self.item_ids:
            raise ValueError("fixed ontology must contain at least one item")
        _require_unique(self.item_ids, "fixed ontology item ids")
        if self.item_ids != sorted(self.item_ids):
            raise ValueError("fixed ontology item ids must use canonical order")
        if self.item_ids_sha256 != content_sha256(self.item_ids):
            raise ValueError("item_ids_sha256 does not match fixed ontology items")
        return self


class FixedOntologyClaim(ContractModel):
    """One independently confirmable normalized pairwise preference claim."""

    record_version: Literal["phase4_fixed_ontology_claim.v1"] = (
        "phase4_fixed_ontology_claim.v1"
    )
    claim_text: NonEmptyText
    item_a: StableId
    item_b: StableId
    value: SliderValue

    @model_validator(mode="after")
    def canonicalize_pair(self) -> Self:
        if self.item_a == self.item_b:
            raise ValueError("claim items must be distinct")
        if self.item_a > self.item_b:
            original_item_a = self.item_a
            original_value = self.value
            object.__setattr__(self, "item_a", self.item_b)
            object.__setattr__(self, "item_b", original_item_a)
            object.__setattr__(
                self,
                "value",
                0.0 if original_value == 0.0 else -original_value,
            )
        return self


class UnsupportedAssumptionFlag(ContractModel):
    record_version: Literal["phase4_unsupported_assumption.v1"] = (
        "phase4_unsupported_assumption.v1"
    )
    flag_id: StableId
    description: NonEmptyText
    requires_participant_attention: Literal[True] = True


def canonical_unsupported_assumptions(
    assumptions: list[UnsupportedAssumptionFlag],
) -> list[UnsupportedAssumptionFlag]:
    """Sort audit flags by id and collapse only byte-equivalent repeats."""

    by_id: dict[str, UnsupportedAssumptionFlag] = {}
    for assumption in assumptions:
        previous = by_id.get(assumption.flag_id)
        if previous is not None and previous != assumption:
            raise ValueError("unsupported assumption flag ids must be unique")
        by_id[assumption.flag_id] = assumption
    return [by_id[flag_id] for flag_id in sorted(by_id)]


class EvidenceExtractorConfiguration(ContractModel):
    """Provider-neutral identity for one exact extraction implementation."""

    record_version: Literal["phase4_evidence_extractor_configuration.v1"] = (
        "phase4_evidence_extractor_configuration.v1"
    )
    configuration_id: StableId
    backend_id: StableId
    backend_version: PositiveVersion
    model_id: StableId
    model_version: NonEmptyText
    prompt_id: StableId
    prompt_version: PositiveVersion
    prompt_sha256: Sha256Digest
    implementation_version: PositiveVersion
    seed: int


class _SessionRecord(ContractModel):
    session_id: StableId
    sequence: EventSequence
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")


class ConversationEvidenceMessage(_SessionRecord):
    """Private raw conversation record, stored separately from proposals."""

    record_version: Literal["phase4_conversation_evidence_message.v1"] = (
        "phase4_conversation_evidence_message.v1"
    )
    message_id: StableId
    role: ConversationRole
    content: PrivateResponseText


class EvidenceExtractionRequest(_SessionRecord):
    """Hash-bound extractor input without duplicating raw message content."""

    record_version: Literal["phase4_evidence_extraction_request.v1"] = (
        "phase4_evidence_extraction_request.v1"
    )
    request_id: StableId
    ontology: FixedOntologyReference
    extractor_configuration_id: StableId
    extractor_configuration_sha256: Sha256Digest
    message_cutoff_sequence: EventSequence
    input_message_ids: list[StableId]
    input_messages_sha256: Sha256Digest
    target_packet_visible: Literal[False] = False

    @field_validator("input_message_ids")
    @classmethod
    def input_message_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("extraction request requires at least one message")
        return _require_unique(value, "input message ids")


class EvidenceProposalDraft(ContractModel):
    """Backend output before ledger identity and chronology are assigned."""

    record_version: Literal["phase4_evidence_proposal_draft.v1"] = (
        "phase4_evidence_proposal_draft.v1"
    )
    source_message_ids: list[StableId]
    claim: FixedOntologyClaim
    extractor_confidence: PositiveConfidence
    unsupported_assumptions: list[UnsupportedAssumptionFlag] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_draft(self) -> Self:
        source_message_ids = _deduplicate_in_order(self.source_message_ids)
        if not source_message_ids:
            raise ValueError("proposal requires participant source messages")
        object.__setattr__(self, "source_message_ids", source_message_ids)
        object.__setattr__(
            self,
            "unsupported_assumptions",
            canonical_unsupported_assumptions(self.unsupported_assumptions),
        )
        return self


_PROPOSAL_DRAFTS_ADAPTER = TypeAdapter(list[EvidenceProposalDraft])


class ConversationalEvidenceProposal(_SessionRecord):
    """One claim proposal; it cannot update a model while pending."""

    record_version: Literal["phase4_conversational_evidence_proposal.v1"] = (
        "phase4_conversational_evidence_proposal.v1"
    )
    proposal_id: StableId
    extraction_request_id: StableId
    source_message_ids: list[StableId]
    claim: FixedOntologyClaim
    extractor_confidence: PositiveConfidence
    unsupported_assumptions: list[UnsupportedAssumptionFlag] = Field(
        default_factory=list
    )
    provisional_model_weight: Literal[0.0] = 0.0

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        if not self.source_message_ids:
            raise ValueError("proposal requires participant source messages")
        _require_unique(self.source_message_ids, "proposal source message ids")
        _require_unique(
            [flag.flag_id for flag in self.unsupported_assumptions],
            "unsupported assumption flag ids",
        )
        return self


class ParticipantEvidenceDecision(_SessionRecord):
    """Explicit per-claim accept, edit, or reject decision."""

    record_version: Literal["phase4_participant_evidence_decision.v1"] = (
        "phase4_participant_evidence_decision.v1"
    )
    decision_id: StableId
    proposal_id: StableId
    decision: EvidenceDecisionKind
    evidence_event_id: StableId | None = None
    edited_claim: FixedOntologyClaim | None = None
    acknowledged_assumption_flag_ids: list[StableId] = Field(
        default_factory=list
    )
    confirmed_by_participant: Literal[True] = True

    @field_validator("acknowledged_assumption_flag_ids")
    @classmethod
    def assumption_acknowledgements_must_be_unique(
        cls, value: list[str]
    ) -> list[str]:
        return _require_unique(value, "acknowledged assumption flag ids")

    @model_validator(mode="after")
    def validate_decision_shape(self) -> Self:
        if self.decision is EvidenceDecisionKind.REJECT:
            if (
                self.evidence_event_id is not None
                or self.edited_claim is not None
                or self.acknowledged_assumption_flag_ids
            ):
                raise ValueError("rejected proposal cannot create evidence")
            return self
        if self.evidence_event_id is None:
            raise ValueError("accepted or edited proposal requires evidence_event_id")
        if self.decision is EvidenceDecisionKind.ACCEPT:
            if self.edited_claim is not None:
                raise ValueError("accepted proposal cannot carry an edited claim")
        elif self.edited_claim is None:
            raise ValueError("edited proposal requires edited_claim")
        return self


class StructuredPreferenceEvidenceEvent(_SessionRecord):
    """Direct participant input already normalized to the fixed ontology."""

    record_version: Literal["phase4_structured_preference_evidence.v1"] = (
        "phase4_structured_preference_evidence.v1"
    )
    evidence_event_id: StableId
    source: EvidenceSource
    claim: FixedOntologyClaim
    question_id: StableId
    response_id: StableId
    confirmed_by_participant: Literal[True] = True

    @field_validator("source")
    @classmethod
    def source_must_be_direct(cls, value: EvidenceSource) -> EvidenceSource:
        if value not in {EvidenceSource.PAIRWISE, EvidenceSource.SLIDER}:
            raise ValueError("structured evidence source must be pairwise or slider")
        return value


class EvidenceCorrectionEvent(_SessionRecord):
    """Append-only participant correction of one active evidence event."""

    record_version: Literal["phase4_evidence_correction.v1"] = (
        "phase4_evidence_correction.v1"
    )
    correction_id: StableId
    evidence_event_id: StableId
    supersedes_evidence_event_id: StableId
    corrected_claim: FixedOntologyClaim
    origin: EvidenceOrigin
    source_message_ids: list[StableId] = Field(default_factory=list)
    question_id: StableId | None = None
    response_id: StableId | None = None
    confirmed_by_participant: Literal[True] = True

    @field_validator("source_message_ids")
    @classmethod
    def correction_sources_must_be_unique(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "correction source message ids")

    @model_validator(mode="after")
    def require_new_event_id(self) -> Self:
        if self.evidence_event_id == self.supersedes_evidence_event_id:
            raise ValueError("correction must create a new evidence event id")
        if self.origin is EvidenceOrigin.CONVERSATION:
            if not self.source_message_ids:
                raise ValueError(
                    "conversation correction requires source message ids"
                )
            if self.question_id is not None or self.response_id is not None:
                raise ValueError(
                    "conversation correction cannot claim structured provenance"
                )
        else:
            if self.source_message_ids:
                raise ValueError(
                    "structured correction cannot use conversation messages"
                )
            if self.question_id is None or self.response_id is None:
                raise ValueError(
                    "structured correction requires question and response ids"
                )
        return self


class EvidenceExtractorBackend(Protocol):
    configuration: EvidenceExtractorConfiguration

    def extract(
        self,
        request: EvidenceExtractionRequest,
        messages: tuple[ConversationEvidenceMessage, ...],
    ) -> list[EvidenceProposalDraft]: ...


class DeterministicEvidenceExtractor:
    """Scripted test double for the provider-neutral extraction boundary."""

    def __init__(
        self,
        configuration: EvidenceExtractorConfiguration,
        drafts: list[EvidenceProposalDraft],
    ) -> None:
        self.configuration = configuration
        self._drafts = [draft.model_copy(deep=True) for draft in drafts]
        self.call_count = 0

    def extract(
        self,
        request: EvidenceExtractionRequest,
        messages: tuple[ConversationEvidenceMessage, ...],
    ) -> list[EvidenceProposalDraft]:
        self.call_count += 1
        return [draft.model_copy(deep=True) for draft in self._drafts]


def conversation_messages_sha256(
    messages: list[ConversationEvidenceMessage]
    | tuple[ConversationEvidenceMessage, ...],
) -> str:
    return content_sha256(
        [message.model_dump(mode="json") for message in messages]
    )


def build_extraction_request(
    *,
    request_id: str,
    session_id: str,
    sequence: int,
    created_at: datetime,
    ontology: FixedOntologyReference,
    configuration: EvidenceExtractorConfiguration,
    messages: list[ConversationEvidenceMessage],
    message_cutoff_sequence: int,
) -> EvidenceExtractionRequest:
    """Bind the exact conversation prefix and fixed ontology for extraction."""

    included = sorted(
        (
            message
            for message in messages
            if message.sequence <= message_cutoff_sequence
        ),
        key=lambda message: message.sequence,
    )
    if not included:
        raise ValueError("extraction request requires a non-empty message prefix")
    if any(message.session_id != session_id for message in included):
        raise ValueError("extraction messages must match request session")
    if included[-1].sequence != message_cutoff_sequence:
        raise ValueError("message cutoff must identify the last included message")
    if sequence <= message_cutoff_sequence:
        raise ValueError("extraction request must follow its message cutoff")
    _require_aware(created_at, "created_at")
    if created_at < included[-1].created_at:
        raise ValueError("extraction request cannot predate its message prefix")
    return EvidenceExtractionRequest(
        request_id=request_id,
        session_id=session_id,
        sequence=sequence,
        created_at=created_at,
        ontology=ontology,
        extractor_configuration_id=configuration.configuration_id,
        extractor_configuration_sha256=content_sha256(configuration),
        message_cutoff_sequence=message_cutoff_sequence,
        input_message_ids=[message.message_id for message in included],
        input_messages_sha256=conversation_messages_sha256(included),
    )


def run_evidence_extractor(
    *,
    request: EvidenceExtractionRequest,
    messages: list[ConversationEvidenceMessage],
    backend: EvidenceExtractorBackend,
    proposal_ids: list[str],
    proposal_sequences: list[int],
    created_at: datetime,
) -> list[ConversationalEvidenceProposal]:
    """Execute and validate one exact extractor request without a live provider."""

    configuration = backend.configuration
    if request.extractor_configuration_id != configuration.configuration_id:
        raise ValueError("extractor request configuration id does not match backend")
    if request.extractor_configuration_sha256 != content_sha256(configuration):
        raise ValueError("extractor request configuration hash does not match backend")
    by_id = {message.message_id: message for message in messages}
    try:
        included = [by_id[message_id] for message_id in request.input_message_ids]
    except KeyError as error:
        raise ValueError("extractor request references an unknown message") from error
    if conversation_messages_sha256(included) != request.input_messages_sha256:
        raise ValueError("extractor request message hash does not match input")
    if [message.message_id for message in included] != request.input_message_ids:
        raise ValueError("extractor input message order does not match request")
    if any(message.session_id != request.session_id for message in included):
        raise ValueError("extractor input messages must match request session")
    if any(
        message.sequence > request.message_cutoff_sequence for message in included
    ):
        raise ValueError("extractor input cannot include a message after its cutoff")
    if included[-1].sequence != request.message_cutoff_sequence:
        raise ValueError("extractor message cutoff must match its final input")

    drafts = _PROPOSAL_DRAFTS_ADAPTER.validate_python(
        backend.extract(request.model_copy(deep=True), tuple(included))
    )
    if len(drafts) != len(proposal_ids) or len(drafts) != len(proposal_sequences):
        raise ValueError("proposal identities must cover every extractor draft")
    _require_unique(proposal_ids, "proposal ids")
    if len(proposal_sequences) != len(set(proposal_sequences)):
        raise ValueError("proposal sequences must be unique")
    if any(sequence <= request.sequence for sequence in proposal_sequences):
        raise ValueError("every proposal must follow its extraction request")
    _require_aware(created_at, "created_at")
    if created_at < request.created_at:
        raise ValueError("proposal cannot predate its extraction request")

    participant_ids = {
        message.message_id
        for message in included
        if message.role is ConversationRole.PARTICIPANT
    }
    allowed_items = set(request.ontology.item_ids)
    proposals: list[ConversationalEvidenceProposal] = []
    for draft, proposal_id, sequence in zip(
        drafts, proposal_ids, proposal_sequences, strict=True
    ):
        if not set(draft.source_message_ids) <= participant_ids:
            raise ValueError("proposal sources must be participant messages in input")
        if {draft.claim.item_a, draft.claim.item_b} - allowed_items:
            raise ValueError("proposal claim uses an item outside the fixed ontology")
        proposals.append(
            ConversationalEvidenceProposal(
                proposal_id=proposal_id,
                session_id=request.session_id,
                sequence=sequence,
                created_at=created_at,
                extraction_request_id=request.request_id,
                source_message_ids=draft.source_message_ids,
                claim=draft.claim,
                extractor_confidence=draft.extractor_confidence,
                unsupported_assumptions=draft.unsupported_assumptions,
            )
        )
    return proposals


@dataclass(frozen=True)
class _EvidenceNode:
    evidence_event_id: str
    sequence: int
    origin: EvidenceOrigin
    evidence: Evidence
    supersedes_evidence_event_id: str | None = None


class FixedOntologyEvidenceLedger(ContractModel):
    """Append-only replay source for fixed-ontology Phase 4C evidence."""

    record_version: Literal["phase4_fixed_ontology_evidence_ledger.v1"] = (
        "phase4_fixed_ontology_evidence_ledger.v1"
    )
    ledger_id: StableId
    session_id: StableId
    ontology: FixedOntologyReference
    extractor_configurations: list[EvidenceExtractorConfiguration] = Field(
        default_factory=list
    )
    messages: list[ConversationEvidenceMessage] = Field(default_factory=list)
    extraction_requests: list[EvidenceExtractionRequest] = Field(
        default_factory=list
    )
    proposals: list[ConversationalEvidenceProposal] = Field(default_factory=list)
    decisions: list[ParticipantEvidenceDecision] = Field(default_factory=list)
    structured_evidence: list[StructuredPreferenceEvidenceEvent] = Field(
        default_factory=list
    )
    corrections: list[EvidenceCorrectionEvent] = Field(default_factory=list)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def ledger_time_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_append_only_graph(self) -> Self:
        self._validate_identity_and_time()
        configurations = {
            config.configuration_id: config
            for config in self.extractor_configurations
        }
        messages = {message.message_id: message for message in self.messages}
        requests = {
            request.request_id: request for request in self.extraction_requests
        }
        proposals = {proposal.proposal_id: proposal for proposal in self.proposals}

        allowed_items = set(self.ontology.item_ids)
        for request in self.extraction_requests:
            config = configurations.get(request.extractor_configuration_id)
            if config is None:
                raise ValueError("extraction request references unknown configuration")
            if request.extractor_configuration_sha256 != content_sha256(config):
                raise ValueError("extraction request configuration hash does not match")
            if request.ontology != self.ontology:
                raise ValueError("extraction request does not match ledger ontology")
            expected_messages = sorted(
                (
                    message
                    for message in self.messages
                    if message.sequence <= request.message_cutoff_sequence
                ),
                key=lambda message: message.sequence,
            )
            if request.input_message_ids != [
                message.message_id for message in expected_messages
            ]:
                raise ValueError(
                    "extraction request must bind the exact message prefix"
                )
            if request.input_messages_sha256 != conversation_messages_sha256(
                expected_messages
            ):
                raise ValueError("extraction request message hash does not match")
            if request.sequence <= request.message_cutoff_sequence:
                raise ValueError("extraction request must follow its message cutoff")

        for proposal in self.proposals:
            request = requests.get(proposal.extraction_request_id)
            if request is None:
                raise ValueError("proposal references unknown extraction request")
            if proposal.sequence <= request.sequence:
                raise ValueError("proposal must follow its extraction request")
            if not set(proposal.source_message_ids) <= set(request.input_message_ids):
                raise ValueError("proposal sources must belong to extractor input")
            for message_id in proposal.source_message_ids:
                message = messages[message_id]
                if message.role is not ConversationRole.PARTICIPANT:
                    raise ValueError("proposal sources must be participant messages")
            self._require_claim_items(proposal.claim, allowed_items)

        decision_by_proposal: dict[str, ParticipantEvidenceDecision] = {}
        for decision in self.decisions:
            proposal = proposals.get(decision.proposal_id)
            if proposal is None:
                raise ValueError("participant decision references unknown proposal")
            if decision.proposal_id in decision_by_proposal:
                raise ValueError("each proposal may have only one participant decision")
            decision_by_proposal[decision.proposal_id] = decision
            if decision.sequence <= proposal.sequence:
                raise ValueError("participant decision must follow its proposal")
            expected_flags = {
                flag.flag_id for flag in proposal.unsupported_assumptions
            }
            acknowledged_flags = set(
                decision.acknowledged_assumption_flag_ids
            )
            if (
                decision.decision is not EvidenceDecisionKind.REJECT
                and acknowledged_flags != expected_flags
            ):
                raise ValueError(
                    "accepted or edited proposal must acknowledge every "
                    "unsupported assumption flag"
                )
            if decision.edited_claim is not None:
                self._require_claim_items(decision.edited_claim, allowed_items)
                if decision.edited_claim == proposal.claim:
                    raise ValueError("edited decision must actually change the claim")

        for event in self.structured_evidence:
            self._require_claim_items(event.claim, allowed_items)
        self._validate_corrections(messages, proposals)
        return self

    def _validate_identity_and_time(self) -> None:
        id_groups = [
            (
                "extractor configuration ids",
                [c.configuration_id for c in self.extractor_configurations],
            ),
            ("message ids", [message.message_id for message in self.messages]),
            (
                "extraction request ids",
                [request.request_id for request in self.extraction_requests],
            ),
            ("proposal ids", [proposal.proposal_id for proposal in self.proposals]),
            ("decision ids", [decision.decision_id for decision in self.decisions]),
            (
                "correction ids",
                [correction.correction_id for correction in self.corrections],
            ),
        ]
        for label, values in id_groups:
            _require_unique(values, label)

        records: list[_SessionRecord] = [
            *self.messages,
            *self.extraction_requests,
            *self.proposals,
            *self.decisions,
            *self.structured_evidence,
            *self.corrections,
        ]
        if any(record.session_id != self.session_id for record in records):
            raise ValueError("every evidence ledger record must match its session")
        sequences = [record.sequence for record in records]
        if len(sequences) != len(set(sequences)):
            raise ValueError("evidence ledger sequences must be globally unique")
        ordered = sorted(records, key=lambda record: record.sequence)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.created_at < earlier.created_at:
                raise ValueError("evidence ledger sequence must agree with time")

        event_ids = [event.evidence_event_id for event in self.structured_evidence]
        event_ids.extend(
            decision.evidence_event_id
            for decision in self.decisions
            if decision.evidence_event_id is not None
        )
        event_ids.extend(
            correction.evidence_event_id for correction in self.corrections
        )
        _require_unique(event_ids, "evidence event ids")

    @staticmethod
    def _require_claim_items(
        claim: FixedOntologyClaim, allowed_items: set[str]
    ) -> None:
        if {claim.item_a, claim.item_b} - allowed_items:
            raise ValueError("evidence claim uses an item outside the fixed ontology")

    def _validate_corrections(
        self,
        messages: dict[str, ConversationEvidenceMessage],
        proposals: dict[str, ConversationalEvidenceProposal],
    ) -> None:
        active: set[str] = set()
        event_records: list[
            StructuredPreferenceEvidenceEvent
            | ParticipantEvidenceDecision
            | EvidenceCorrectionEvent
        ] = [*self.structured_evidence, *self.decisions, *self.corrections]
        allowed_items = set(self.ontology.item_ids)
        for record in sorted(event_records, key=lambda item: item.sequence):
            if isinstance(record, StructuredPreferenceEvidenceEvent):
                active.add(record.evidence_event_id)
                continue
            if isinstance(record, ParticipantEvidenceDecision):
                proposal = proposals[record.proposal_id]
                if record.sequence <= proposal.sequence:
                    raise ValueError("participant decision must follow its proposal")
                if record.evidence_event_id is not None:
                    active.add(record.evidence_event_id)
                continue

            self._require_claim_items(record.corrected_claim, allowed_items)
            if record.supersedes_evidence_event_id not in active:
                raise ValueError("correction must supersede an active evidence event")
            for message_id in record.source_message_ids:
                message = messages.get(message_id)
                if message is None:
                    raise ValueError("correction references unknown source message")
                if message.role is not ConversationRole.PARTICIPANT:
                    raise ValueError("correction sources must be participant messages")
                if message.sequence >= record.sequence:
                    raise ValueError(
                        "correction source message must precede correction"
                    )
            active.remove(record.supersedes_evidence_event_id)
            active.add(record.evidence_event_id)


def _claim_for_decision(
    decision: ParticipantEvidenceDecision,
    proposal: ConversationalEvidenceProposal,
) -> FixedOntologyClaim | None:
    if decision.decision is EvidenceDecisionKind.REJECT:
        return None
    if decision.decision is EvidenceDecisionKind.EDIT:
        if decision.edited_claim is None:  # defended by the contract
            raise ValueError("edited decision is missing its edited claim")
        return decision.edited_claim
    return proposal.claim


def _evidence_from_structured(
    event: StructuredPreferenceEvidenceEvent,
) -> Evidence:
    return Evidence(
        event_id=event.evidence_event_id,
        source=event.source,
        item_a=event.claim.item_a,
        item_b=event.claim.item_b,
        value=event.claim.value,
        confidence=1.0,
        prompt_id=event.question_id,
        raw_response=None,
        extracted_claims=[event.claim.claim_text],
        timestamp=event.created_at.isoformat(),
        metadata={
            "phase4_origin": EvidenceOrigin.STRUCTURED.value,
            "response_id": event.response_id,
        },
        confirmed_by_participant=True,
    )


def _evidence_from_decision(
    decision: ParticipantEvidenceDecision,
    proposal: ConversationalEvidenceProposal,
    request: EvidenceExtractionRequest,
    configuration: EvidenceExtractorConfiguration,
) -> Evidence | None:
    claim = _claim_for_decision(decision, proposal)
    if claim is None:
        return None
    return Evidence(
        event_id=decision.evidence_event_id,
        source=EvidenceSource.FREE_TEXT_EXTRACTION,
        item_a=claim.item_a,
        item_b=claim.item_b,
        value=claim.value,
        confidence=1.0,
        prompt_id=configuration.prompt_id,
        raw_response=None,
        extracted_claims=[claim.claim_text],
        timestamp=decision.created_at.isoformat(),
        metadata={
            "phase4_origin": EvidenceOrigin.CONVERSATION.value,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
            "decision": decision.decision.value,
            "acknowledged_assumption_flag_ids": list(
                decision.acknowledged_assumption_flag_ids
            ),
            "extraction_request_id": request.request_id,
            "source_message_ids": list(proposal.source_message_ids),
            "extractor_configuration_id": configuration.configuration_id,
            "extractor_confidence": proposal.extractor_confidence,
            "unsupported_assumptions": [
                flag.model_dump(mode="json")
                for flag in proposal.unsupported_assumptions
            ],
        },
        confirmed_by_participant=True,
    )


def materialize_evidence(
    ledger: FixedOntologyEvidenceLedger,
    *,
    condition: EvidenceCondition,
    cutoff_sequence: int,
) -> list[Evidence]:
    """Derive the active model-ready evidence at one shared event cutoff."""

    if cutoff_sequence < 0:
        raise ValueError("evidence cutoff sequence cannot be negative")
    proposals = {proposal.proposal_id: proposal for proposal in ledger.proposals}
    requests = {
        request.request_id: request for request in ledger.extraction_requests
    }
    configurations = {
        config.configuration_id: config
        for config in ledger.extractor_configurations
    }
    nodes: dict[str, _EvidenceNode] = {}
    active_event_ids: set[str] = set()
    records: list[
        StructuredPreferenceEvidenceEvent
        | ParticipantEvidenceDecision
        | EvidenceCorrectionEvent
    ] = [*ledger.structured_evidence, *ledger.decisions, *ledger.corrections]

    for record in sorted(records, key=lambda item: item.sequence):
        if record.sequence > cutoff_sequence:
            break
        if isinstance(record, StructuredPreferenceEvidenceEvent):
            evidence = _evidence_from_structured(record)
            nodes[record.evidence_event_id] = _EvidenceNode(
                evidence_event_id=record.evidence_event_id,
                sequence=record.sequence,
                origin=EvidenceOrigin.STRUCTURED,
                evidence=evidence,
            )
            active_event_ids.add(record.evidence_event_id)
            continue
        if isinstance(record, ParticipantEvidenceDecision):
            proposal = proposals[record.proposal_id]
            request = requests[proposal.extraction_request_id]
            configuration = configurations[request.extractor_configuration_id]
            evidence = _evidence_from_decision(
                record, proposal, request, configuration
            )
            if evidence is not None:
                if record.evidence_event_id is None:  # defended by contract
                    raise ValueError("confirmed evidence lacks an event id")
                nodes[record.evidence_event_id] = _EvidenceNode(
                    evidence_event_id=record.evidence_event_id,
                    sequence=record.sequence,
                    origin=EvidenceOrigin.CONVERSATION,
                    evidence=evidence,
                )
                active_event_ids.add(record.evidence_event_id)
            continue

        if record.supersedes_evidence_event_id not in active_event_ids:
            raise ValueError("correction must supersede active evidence")
        corrected = Evidence(
            event_id=record.evidence_event_id,
            source=EvidenceSource.CORRECTION,
            item_a=record.corrected_claim.item_a,
            item_b=record.corrected_claim.item_b,
            value=record.corrected_claim.value,
            confidence=1.0,
            prompt_id=record.question_id,
            raw_response=None,
            extracted_claims=[record.corrected_claim.claim_text],
            timestamp=record.created_at.isoformat(),
            metadata={
                "phase4_origin": record.origin.value,
                "correction_id": record.correction_id,
                "supersedes_evidence_event_id": (
                    record.supersedes_evidence_event_id
                ),
                "source_message_ids": list(record.source_message_ids),
                "response_id": record.response_id,
            },
            confirmed_by_participant=True,
        )
        nodes[record.evidence_event_id] = _EvidenceNode(
            evidence_event_id=record.evidence_event_id,
            sequence=record.sequence,
            origin=record.origin,
            evidence=corrected,
            supersedes_evidence_event_id=record.supersedes_evidence_event_id,
        )
        active_event_ids.remove(record.supersedes_evidence_event_id)
        active_event_ids.add(record.evidence_event_id)

    terminals = [nodes[event_id] for event_id in active_event_ids]
    if condition is EvidenceCondition.COMBINED:
        selected = terminals
    else:
        required_origin = (
            EvidenceOrigin.STRUCTURED
            if condition is EvidenceCondition.STRUCTURED_ONLY
            else EvidenceOrigin.CONVERSATION
        )
        selected = []
        for terminal in terminals:
            candidate: _EvidenceNode | None = terminal
            while candidate is not None and candidate.origin is not required_origin:
                predecessor_id = candidate.supersedes_evidence_event_id
                candidate = nodes.get(predecessor_id) if predecessor_id else None
            if candidate is not None:
                selected.append(candidate)

    return [
        item.evidence
        for item in sorted(selected, key=lambda value: value.sequence)
    ]


def materialize_all_evidence_conditions(
    ledger: FixedOntologyEvidenceLedger,
    *,
    cutoff_sequence: int,
) -> dict[EvidenceCondition, list[Evidence]]:
    """Materialize all predeclared evidence conditions at the same cutoff."""

    return {
        condition: materialize_evidence(
            ledger,
            condition=condition,
            cutoff_sequence=cutoff_sequence,
        )
        for condition in EvidenceCondition
    }


def replay_preference_state(
    *,
    model: PreferenceModel,
    ledger: FixedOntologyEvidenceLedger,
    condition: EvidenceCondition,
    cutoff_sequence: int,
    user_id: str,
) -> PreferenceState:
    """Rebuild a posterior from confirmed active evidence at one cutoff.

    Rebuilding rather than incrementally applying a correction is essential:
    superseded evidence must no longer contribute to either online or
    full-history model families.
    """

    state = model.initialize(
        user_id,
        ledger.session_id,
        list(ledger.ontology.item_ids),
    )
    for evidence in materialize_evidence(
        ledger,
        condition=condition,
        cutoff_sequence=cutoff_sequence,
    ):
        state = model.update(state, evidence)
    return state
