"""Auditable expanding-ontology lifecycle for Phase 4C.

The evidence extractor may propose a dimension, but a proposal has zero model
weight and cannot change the ontology. Only explicit participant decisions
and participant-confirmed maintenance events can admit, map, support, merge,
or prune dimensions. Replay is deterministic at any event cutoff.

This module layers over ``FixedOntologyEvidenceLedger`` rather than changing
its frozen fixed-ontology semantics. Policy parameters are versioned inputs;
the final experimental values remain a later freeze decision.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from .contracts import (
    ContractModel,
    EventSequence,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_evidence import (
    ConversationEvidenceMessage,
    EvidenceDecisionKind,
    EvidenceExtractorConfiguration,
    EvidenceOrigin,
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    UnsupportedAssumptionFlag,
    conversation_messages_sha256,
)
from .phase4_interviewer import ConversationRole
from .phase4_protocol import EvidenceCondition

NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
PositiveConfidence = Annotated[float, Field(gt=0.0, le=1.0)]
NonNegativeFinite = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
PositiveFinite = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class OntologyProposalDecisionKind(str, Enum):
    ADMIT_NEW = "admit_new"
    MAP_TO_EXISTING = "map_to_existing"
    REJECT = "reject"


class ExpandingDimensionStatus(str, Enum):
    ACTIVE = "active"
    MERGED = "merged"
    PRUNED = "pruned"


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _require_unique(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


def _float_equal(left: float | None, right: float) -> bool:
    return left is not None and math.isclose(
        left,
        right,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def _normalize_semantic_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


class OntologyDimensionDefinition(ContractModel):
    record_version: Literal["phase4_ontology_dimension_definition.v1"] = (
        "phase4_ontology_dimension_definition.v1"
    )
    dimension_id: StableId
    name: NonEmptyText
    definition: NonEmptyText
    interpretation: NonEmptyText


def dimension_semantic_sha256(dimension: OntologyDimensionDefinition) -> str:
    """Hash exact-normalized semantics without treating an id as meaning."""

    return content_sha256(
        {
            "name": _normalize_semantic_text(dimension.name),
            "definition": _normalize_semantic_text(dimension.definition),
            "interpretation": _normalize_semantic_text(
                dimension.interpretation
            ),
        }
    )


def evidence_ledger_identity_sha256(
    ledger: FixedOntologyEvidenceLedger,
) -> str:
    """Hash only immutable evidence-ledger identity available from creation."""

    return content_sha256(
        {
            "record_version": ledger.record_version,
            "ledger_id": ledger.ledger_id,
            "session_id": ledger.session_id,
            "ontology": ledger.ontology.model_dump(mode="json"),
            "created_at": ledger.model_dump(mode="json")["created_at"],
        }
    )


class OntologyExpansionPolicy(ContractModel):
    """Versioned deterministic maintenance rules, not final tuned values."""

    record_version: Literal["phase4_ontology_expansion_policy.v1"] = (
        "phase4_ontology_expansion_policy.v1"
    )
    policy_id: StableId
    policy_version: PositiveVersion
    duplicate_rule: Literal["nfkc_casefold_whitespace_exact_v1"] = (
        "nfkc_casefold_whitespace_exact_v1"
    )
    admission_confirmation_support_weight: PositiveFinite
    evidence_lineage_support_weight: PositiveFinite
    full_weight_support_score: PositiveFinite
    prune_max_support_score: NonNegativeFinite
    prune_min_idle_sequence_gap: PositiveCount
    participant_admission_required: Literal[True] = True
    participant_merge_confirmation_required: Literal[True] = True
    participant_prune_confirmation_required: Literal[True] = True
    seed_dimensions_are_not_merge_or_prune_targets: Literal[True] = True

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if (
            self.admission_confirmation_support_weight
            >= self.full_weight_support_score
        ):
            raise ValueError(
                "admission support weight must remain below full-weight support"
            )
        if (
            self.prune_max_support_score
            < self.admission_confirmation_support_weight
        ):
            raise ValueError(
                "prune support threshold must include admission-only dimensions"
            )
        if (
            self.prune_max_support_score
            >= self.full_weight_support_score
        ):
            raise ValueError(
                "prune support threshold must remain below full-weight support"
            )
        return self


class ExpandingOntologySeed(ContractModel):
    record_version: Literal["phase4_expanding_ontology_seed.v1"] = (
        "phase4_expanding_ontology_seed.v1"
    )
    ontology_id: StableId
    seed_version: PositiveVersion
    dimensions: list[OntologyDimensionDefinition]
    dimensions_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        if not self.dimensions:
            raise ValueError("expanding ontology seed cannot be empty")
        ids = [dimension.dimension_id for dimension in self.dimensions]
        _require_unique(ids, "seed dimension ids")
        if ids != sorted(ids):
            raise ValueError("seed dimensions must use canonical id order")
        semantic_hashes = [
            dimension_semantic_sha256(dimension)
            for dimension in self.dimensions
        ]
        _require_unique(semantic_hashes, "seed dimension semantics")
        expected = content_sha256(
            [dimension.model_dump(mode="json") for dimension in self.dimensions]
        )
        if self.dimensions_sha256 != expected:
            raise ValueError("dimensions_sha256 does not match seed dimensions")
        return self


class _OntologyRecord(ContractModel):
    session_id: StableId
    sequence: EventSequence
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")


class ConfirmedEvidenceReference(ContractModel):
    record_version: Literal["phase4_confirmed_evidence_reference.v1"] = (
        "phase4_confirmed_evidence_reference.v1"
    )
    evidence_event_id: StableId
    evidence_lineage_id: StableId
    sequence: EventSequence
    origin: EvidenceOrigin
    source_record_sha256: Sha256Digest
    confirmed_by_participant: Literal[True] = True


class OntologyEvidenceSupportCandidate(ContractModel):
    """Private confirmed claim made available to the ontology proposer."""

    record_version: Literal["phase4_ontology_evidence_support.v1"] = (
        "phase4_ontology_evidence_support.v1"
    )
    reference: ConfirmedEvidenceReference
    claim: FixedOntologyClaim


def confirmed_evidence_references(
    ledger: FixedOntologyEvidenceLedger,
) -> list[ConfirmedEvidenceReference]:
    """Derive confirmed event identities and correction-stable lineages."""

    references: list[ConfirmedEvidenceReference] = []
    lineage_by_event_id: dict[str, str] = {}
    for event in ledger.structured_evidence:
        lineage_by_event_id[event.evidence_event_id] = event.evidence_event_id
        references.append(
            ConfirmedEvidenceReference(
                evidence_event_id=event.evidence_event_id,
                evidence_lineage_id=event.evidence_event_id,
                sequence=event.sequence,
                origin=EvidenceOrigin.STRUCTURED,
                source_record_sha256=content_sha256(event),
            )
        )
    proposals = {proposal.proposal_id: proposal for proposal in ledger.proposals}
    for decision in ledger.decisions:
        if decision.decision is EvidenceDecisionKind.REJECT:
            continue
        if decision.evidence_event_id is None:
            raise ValueError("confirmed evidence decision lacks an event id")
        if decision.proposal_id not in proposals:
            raise ValueError("confirmed decision references unknown proposal")
        lineage_by_event_id[decision.evidence_event_id] = decision.evidence_event_id
        references.append(
            ConfirmedEvidenceReference(
                evidence_event_id=decision.evidence_event_id,
                evidence_lineage_id=decision.evidence_event_id,
                sequence=decision.sequence,
                origin=EvidenceOrigin.CONVERSATION,
                source_record_sha256=content_sha256(decision),
            )
        )
    for correction in sorted(ledger.corrections, key=lambda item: item.sequence):
        lineage_id = lineage_by_event_id.get(
            correction.supersedes_evidence_event_id
        )
        if lineage_id is None:
            raise ValueError("correction references unknown evidence lineage")
        lineage_by_event_id[correction.evidence_event_id] = lineage_id
        references.append(
            ConfirmedEvidenceReference(
                evidence_event_id=correction.evidence_event_id,
                evidence_lineage_id=lineage_id,
                sequence=correction.sequence,
                origin=correction.origin,
                source_record_sha256=content_sha256(correction),
            )
        )
    return sorted(references, key=lambda reference: reference.sequence)


def _reference_matches_condition(
    reference: ConfirmedEvidenceReference,
    condition: EvidenceCondition,
) -> bool:
    if condition is EvidenceCondition.STRUCTURED_ONLY:
        return reference.origin is EvidenceOrigin.STRUCTURED
    if condition is EvidenceCondition.CONVERSATION_ONLY:
        return reference.origin is EvidenceOrigin.CONVERSATION
    return True


def active_confirmed_evidence_references(
    ledger: FixedOntologyEvidenceLedger,
    *,
    cutoff_sequence: int,
    condition: EvidenceCondition = EvidenceCondition.COMBINED,
) -> list[ConfirmedEvidenceReference]:
    """Return the latest condition-eligible event per lineage at a cutoff."""

    if cutoff_sequence < 0:
        raise ValueError("evidence cutoff cannot be negative")
    return _active_references_at_cutoff(
        confirmed_evidence_references(ledger),
        cutoff_sequence=cutoff_sequence,
        condition=condition,
    )


def _active_references_at_cutoff(
    references: list[ConfirmedEvidenceReference],
    *,
    cutoff_sequence: int,
    condition: EvidenceCondition,
) -> list[ConfirmedEvidenceReference]:
    active_by_lineage: dict[str, ConfirmedEvidenceReference] = {}
    for reference in references:
        if reference.sequence > cutoff_sequence:
            break
        if not _reference_matches_condition(reference, condition):
            continue
        active_by_lineage[reference.evidence_lineage_id] = reference
    return sorted(active_by_lineage.values(), key=lambda item: item.sequence)


def confirmed_evidence_support_candidates(
    ledger: FixedOntologyEvidenceLedger,
    *,
    cutoff_sequence: int,
    condition: EvidenceCondition = EvidenceCondition.COMBINED,
) -> list[OntologyEvidenceSupportCandidate]:
    """Materialize exact active claims that may support an ontology proposal."""

    claims_by_event_id: dict[str, FixedOntologyClaim] = {
        event.evidence_event_id: event.claim
        for event in ledger.structured_evidence
    }
    proposals = {proposal.proposal_id: proposal for proposal in ledger.proposals}
    for decision in ledger.decisions:
        if decision.evidence_event_id is None:
            continue
        proposal = proposals[decision.proposal_id]
        if decision.decision is EvidenceDecisionKind.EDIT:
            if decision.edited_claim is None:
                raise ValueError("edited evidence decision lacks edited claim")
            claims_by_event_id[decision.evidence_event_id] = decision.edited_claim
        elif decision.decision is EvidenceDecisionKind.ACCEPT:
            claims_by_event_id[decision.evidence_event_id] = proposal.claim
    for correction in ledger.corrections:
        claims_by_event_id[correction.evidence_event_id] = (
            correction.corrected_claim
        )

    candidates = []
    for reference in active_confirmed_evidence_references(
        ledger,
        cutoff_sequence=cutoff_sequence,
        condition=condition,
    ):
        claim = claims_by_event_id.get(reference.evidence_event_id)
        if claim is None:
            raise ValueError("confirmed evidence reference lacks a claim")
        candidates.append(
            OntologyEvidenceSupportCandidate(
                reference=reference,
                claim=claim,
            )
        )
    return candidates


class OntologyProposalContext(_OntologyRecord):
    """Complete target-blind input to one ontology proposer call."""

    record_version: Literal["phase4_ontology_proposal_context.v1"] = (
        "phase4_ontology_proposal_context.v1"
    )
    context_id: StableId
    expansion_ledger_id: StableId
    evidence_condition: EvidenceCondition
    evidence_ledger_id: StableId
    evidence_ledger_identity_sha256: Sha256Digest
    seed_sha256: Sha256Digest
    policy_sha256: Sha256Digest
    parent_snapshot_sha256: Sha256Digest
    active_dimensions: list[OntologyDimensionDefinition]
    active_dimensions_sha256: Sha256Digest
    retired_dimensions: list[OntologyDimensionDefinition]
    retired_dimensions_sha256: Sha256Digest
    extractor_configuration_id: StableId
    extractor_configuration_sha256: Sha256Digest
    message_cutoff_sequence: EventSequence
    input_message_ids: list[StableId]
    input_messages_sha256: Sha256Digest
    evidence_cutoff_sequence: NonNegativeCount
    eligible_evidence: list[OntologyEvidenceSupportCandidate]
    eligible_evidence_event_ids: list[StableId]
    eligible_evidence_sha256: Sha256Digest
    target_packet_visible: Literal[False] = False

    @model_validator(mode="after")
    def validate_canonical_bindings(self) -> Self:
        if not self.input_message_ids:
            raise ValueError("ontology proposal context requires messages")
        _require_unique(self.input_message_ids, "ontology input message ids")
        _require_unique(
            self.eligible_evidence_event_ids,
            "ontology eligible evidence event ids",
        )
        if self.eligible_evidence_event_ids != [
            item.reference.evidence_event_id for item in self.eligible_evidence
        ]:
            raise ValueError("eligible evidence ids do not match evidence records")
        if self.eligible_evidence_sha256 != content_sha256(
            [item.model_dump(mode="json") for item in self.eligible_evidence]
        ):
            raise ValueError("eligible_evidence_sha256 does not match evidence")
        dimension_ids = [
            dimension.dimension_id for dimension in self.active_dimensions
        ]
        _require_unique(dimension_ids, "ontology context dimension ids")
        if dimension_ids != sorted(dimension_ids):
            raise ValueError("ontology context dimensions must use canonical order")
        expected_dimension_hash = content_sha256(
            [
                dimension.model_dump(mode="json")
                for dimension in self.active_dimensions
            ]
        )
        if self.active_dimensions_sha256 != expected_dimension_hash:
            raise ValueError("active_dimensions_sha256 does not match dimensions")
        retired_ids = [
            dimension.dimension_id for dimension in self.retired_dimensions
        ]
        _require_unique(retired_ids, "ontology context retired dimension ids")
        if retired_ids != sorted(retired_ids):
            raise ValueError(
                "ontology context retired dimensions must use canonical order"
            )
        if set(dimension_ids) & set(retired_ids):
            raise ValueError("active and retired ontology dimensions must be disjoint")
        expected_retired_hash = content_sha256(
            [
                dimension.model_dump(mode="json")
                for dimension in self.retired_dimensions
            ]
        )
        if self.retired_dimensions_sha256 != expected_retired_hash:
            raise ValueError("retired_dimensions_sha256 does not match dimensions")
        if self.sequence <= self.message_cutoff_sequence:
            raise ValueError("ontology context must follow its message cutoff")
        if self.sequence <= self.evidence_cutoff_sequence:
            raise ValueError("ontology context must follow its evidence cutoff")
        return self


class OntologyDimensionProposalDraft(ContractModel):
    record_version: Literal["phase4_ontology_dimension_proposal_draft.v1"] = (
        "phase4_ontology_dimension_proposal_draft.v1"
    )
    source_message_ids: list[StableId]
    proposed_dimension: OntologyDimensionDefinition
    supporting_evidence_event_ids: list[StableId]
    candidate_duplicate_dimension_ids: list[StableId] = Field(
        default_factory=list
    )
    extractor_confidence: PositiveConfidence
    unsupported_assumptions: list[UnsupportedAssumptionFlag] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_draft(self) -> Self:
        if not self.source_message_ids:
            raise ValueError("dimension proposal requires participant messages")
        _require_unique(self.source_message_ids, "dimension source message ids")
        _require_unique(
            self.supporting_evidence_event_ids,
            "dimension supporting evidence event ids",
        )
        _require_unique(
            self.candidate_duplicate_dimension_ids,
            "candidate duplicate dimension ids",
        )
        if self.candidate_duplicate_dimension_ids != sorted(
            self.candidate_duplicate_dimension_ids
        ):
            raise ValueError("candidate duplicate dimension ids must be canonical")
        flag_ids = [flag.flag_id for flag in self.unsupported_assumptions]
        _require_unique(
            flag_ids,
            "dimension unsupported assumption ids",
        )
        if flag_ids != sorted(flag_ids):
            raise ValueError("dimension unsupported assumptions must be canonical")
        return self


_ONTOLOGY_DRAFTS_ADAPTER = TypeAdapter(list[OntologyDimensionProposalDraft])


class OntologyDimensionProposal(_OntologyRecord):
    record_version: Literal["phase4_ontology_dimension_proposal.v1"] = (
        "phase4_ontology_dimension_proposal.v1"
    )
    proposal_id: StableId
    context_id: StableId
    context_sha256: Sha256Digest
    source_message_ids: list[StableId]
    proposed_dimension: OntologyDimensionDefinition
    supporting_evidence_event_ids: list[StableId]
    candidate_duplicate_dimension_ids: list[StableId] = Field(
        default_factory=list
    )
    extractor_confidence: PositiveConfidence
    unsupported_assumptions: list[UnsupportedAssumptionFlag] = Field(
        default_factory=list
    )
    provisional_dimension_weight: Literal[0.0] = 0.0

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        OntologyDimensionProposalDraft(
            source_message_ids=self.source_message_ids,
            proposed_dimension=self.proposed_dimension,
            supporting_evidence_event_ids=self.supporting_evidence_event_ids,
            candidate_duplicate_dimension_ids=(
                self.candidate_duplicate_dimension_ids
            ),
            extractor_confidence=self.extractor_confidence,
            unsupported_assumptions=self.unsupported_assumptions,
        )
        return self


class OntologyProposalDecision(_OntologyRecord):
    record_version: Literal["phase4_ontology_proposal_decision.v1"] = (
        "phase4_ontology_proposal_decision.v1"
    )
    decision_id: StableId
    proposal_id: StableId
    decision: OntologyProposalDecisionKind
    admitted_dimension: OntologyDimensionDefinition | None = None
    mapped_dimension_id: StableId | None = None
    acknowledged_candidate_dimension_ids: list[StableId] = Field(
        default_factory=list
    )
    acknowledged_assumption_flag_ids: list[StableId] = Field(
        default_factory=list
    )
    confirmed_by_participant: Literal[True] = True

    @model_validator(mode="after")
    def validate_decision_shape(self) -> Self:
        _require_unique(
            self.acknowledged_candidate_dimension_ids,
            "acknowledged candidate dimension ids",
        )
        _require_unique(
            self.acknowledged_assumption_flag_ids,
            "acknowledged dimension assumption ids",
        )
        if self.acknowledged_candidate_dimension_ids != sorted(
            self.acknowledged_candidate_dimension_ids
        ):
            raise ValueError("acknowledged duplicate candidates must be canonical")
        if self.acknowledged_assumption_flag_ids != sorted(
            self.acknowledged_assumption_flag_ids
        ):
            raise ValueError("acknowledged dimension assumptions must be canonical")
        if self.decision is OntologyProposalDecisionKind.REJECT:
            if (
                self.admitted_dimension is not None
                or self.mapped_dimension_id is not None
                or self.acknowledged_candidate_dimension_ids
                or self.acknowledged_assumption_flag_ids
            ):
                raise ValueError("rejected dimension proposal cannot alter ontology")
            return self
        if self.decision is OntologyProposalDecisionKind.MAP_TO_EXISTING:
            if self.mapped_dimension_id is None:
                raise ValueError("mapped proposal requires target dimension")
            if self.admitted_dimension is not None:
                raise ValueError("mapped proposal cannot admit a new dimension")
            return self
        if self.admitted_dimension is None:
            raise ValueError("admission requires exact participant-approved dimension")
        if self.mapped_dimension_id is not None:
            raise ValueError("admission cannot map to an existing dimension")
        return self


class OntologyDimensionSupportEvent(_OntologyRecord):
    record_version: Literal["phase4_ontology_dimension_support.v1"] = (
        "phase4_ontology_dimension_support.v1"
    )
    support_id: StableId
    dimension_id: StableId
    evidence_event_ids: list[StableId]
    support_rationale: NonEmptyText
    confirmed_by_participant: Literal[True] = True

    @field_validator("evidence_event_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("dimension support event cannot be empty")
        _require_unique(value, "dimension support evidence ids")
        if value != sorted(value):
            raise ValueError("dimension support evidence ids must be canonical")
        return value


class OntologyDimensionMergeEvent(_OntologyRecord):
    record_version: Literal["phase4_ontology_dimension_merge.v1"] = (
        "phase4_ontology_dimension_merge.v1"
    )
    merge_id: StableId
    source_dimension_ids: list[StableId]
    merged_dimension: OntologyDimensionDefinition
    additional_evidence_event_ids: list[StableId] = Field(default_factory=list)
    merge_rationale: NonEmptyText
    confirmed_by_participant: Literal[True] = True

    @model_validator(mode="after")
    def validate_merge_shape(self) -> Self:
        if len(self.source_dimension_ids) < 2:
            raise ValueError("merge requires at least two source dimensions")
        _require_unique(self.source_dimension_ids, "merge source dimension ids")
        if self.source_dimension_ids != sorted(self.source_dimension_ids):
            raise ValueError("merge source dimension ids must be canonical")
        _require_unique(
            self.additional_evidence_event_ids,
            "merge additional evidence ids",
        )
        if self.additional_evidence_event_ids != sorted(
            self.additional_evidence_event_ids
        ):
            raise ValueError("merge additional evidence ids must be canonical")
        if self.merged_dimension.dimension_id in self.source_dimension_ids:
            raise ValueError("merge must create a new dimension id")
        return self


class OntologyDimensionPruneEvent(_OntologyRecord):
    record_version: Literal["phase4_ontology_dimension_prune.v1"] = (
        "phase4_ontology_dimension_prune.v1"
    )
    prune_id: StableId
    dimension_id: StableId
    reason: NonEmptyText
    confirmed_by_participant: Literal[True] = True


class OntologyExpansionBackend(Protocol):
    configuration: EvidenceExtractorConfiguration

    def propose(
        self,
        context: OntologyProposalContext,
        messages: tuple[ConversationEvidenceMessage, ...],
    ) -> list[OntologyDimensionProposalDraft]: ...


class DeterministicOntologyExpansionBackend:
    """Scripted provider-neutral test double; not an experimental LLM arm."""

    def __init__(
        self,
        configuration: EvidenceExtractorConfiguration,
        drafts: list[OntologyDimensionProposalDraft],
    ) -> None:
        self.configuration = configuration
        self._drafts = [draft.model_copy(deep=True) for draft in drafts]
        self.call_count = 0

    def propose(
        self,
        context: OntologyProposalContext,
        messages: tuple[ConversationEvidenceMessage, ...],
    ) -> list[OntologyDimensionProposalDraft]:
        self.call_count += 1
        return [draft.model_copy(deep=True) for draft in self._drafts]


class ExpandingOntologyDimensionState(ContractModel):
    record_version: Literal["phase4_expanding_dimension_state.v1"] = (
        "phase4_expanding_dimension_state.v1"
    )
    dimension: OntologyDimensionDefinition
    status: ExpandingDimensionStatus
    is_seed: bool
    introduced_sequence: NonNegativeCount
    last_reinforced_sequence: NonNegativeCount
    supporting_evidence_event_ids: list[StableId]
    supporting_evidence_lineage_ids: list[StableId]
    admission_confirmation_count: Annotated[int, Field(ge=0, le=1)]
    independent_evidence_lineage_count: NonNegativeCount
    support_score: NonNegativeFinite
    shrinkage_weight: Annotated[float, Field(gt=0.0, le=1.0)] | None
    merged_into_dimension_id: StableId | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.is_seed and self.status is not ExpandingDimensionStatus.ACTIVE:
            raise ValueError("seed dimension state must remain active")
        if self.is_seed and self.shrinkage_weight != 1.0:
            raise ValueError("seed dimension state must retain full weight")
        if (
            self.status is not ExpandingDimensionStatus.ACTIVE
            and self.shrinkage_weight is not None
        ):
            raise ValueError("retired dimension cannot expose shrinkage weight")
        if (
            self.status is ExpandingDimensionStatus.ACTIVE
            and self.shrinkage_weight is None
        ):
            raise ValueError("active dimension requires shrinkage weight")
        expected_confirmation_count = 0 if self.is_seed else 1
        if self.admission_confirmation_count != expected_confirmation_count:
            raise ValueError("dimension admission confirmation count is invalid")
        if self.independent_evidence_lineage_count != len(
            self.supporting_evidence_lineage_ids
        ):
            raise ValueError("independent evidence count does not match lineages")
        if self.last_reinforced_sequence < self.introduced_sequence:
            raise ValueError("dimension reinforcement cannot predate introduction")
        if self.status is ExpandingDimensionStatus.MERGED:
            if self.merged_into_dimension_id is None:
                raise ValueError("merged dimension requires its destination")
        elif self.merged_into_dimension_id is not None:
            raise ValueError("only a merged dimension may name a destination")
        return self


class ExpandingOntologySnapshot(ContractModel):
    record_version: Literal["phase4_expanding_ontology_snapshot.v1"] = (
        "phase4_expanding_ontology_snapshot.v1"
    )
    ontology_id: StableId
    seed_version: PositiveVersion
    event_cutoff_sequence: NonNegativeCount
    policy: OntologyExpansionPolicy
    policy_sha256: Sha256Digest
    dimensions: list[ExpandingOntologyDimensionState]

    @model_validator(mode="after")
    def dimension_ids_must_be_unique(self) -> Self:
        if self.policy_sha256 != content_sha256(self.policy):
            raise ValueError("policy_sha256 does not match snapshot policy")
        _require_unique(
            [item.dimension.dimension_id for item in self.dimensions],
            "snapshot dimension ids",
        )
        for item in self.dimensions:
            _require_unique(
                item.supporting_evidence_event_ids,
                "snapshot supporting evidence event ids",
            )
            _require_unique(
                item.supporting_evidence_lineage_ids,
                "snapshot supporting evidence lineage ids",
            )
            expected_score = (
                item.admission_confirmation_count
                * self.policy.admission_confirmation_support_weight
                + item.independent_evidence_lineage_count
                * self.policy.evidence_lineage_support_weight
            )
            if not _float_equal(item.support_score, expected_score):
                raise ValueError("support score does not match provenance")
            if item.status is ExpandingDimensionStatus.ACTIVE:
                expected_weight = (
                    1.0
                    if item.is_seed
                    else _shrinkage_weight_from_score(
                        expected_score,
                        self.policy.full_weight_support_score,
                    )
                )
                if not _float_equal(item.shrinkage_weight, expected_weight):
                    raise ValueError("shrinkage weight does not match policy")
        return self


def active_dimension_states(
    snapshot: ExpandingOntologySnapshot,
) -> list[ExpandingOntologyDimensionState]:
    """Return the only dimension states eligible for model consumption."""

    return [
        item
        for item in snapshot.dimensions
        if item.status is ExpandingDimensionStatus.ACTIVE
    ]


def _retired_dimension_states(
    snapshot: ExpandingOntologySnapshot,
) -> list[ExpandingOntologyDimensionState]:
    return [
        item
        for item in snapshot.dimensions
        if item.status is not ExpandingDimensionStatus.ACTIVE
    ]


class ExpandingOntologyLedger(ContractModel):
    """Locally valid records; cross-ledger integrity requires the validator."""

    record_version: Literal["phase4_expanding_ontology_ledger.v1"] = (
        "phase4_expanding_ontology_ledger.v1"
    )
    ledger_id: StableId
    session_id: StableId
    evidence_condition: EvidenceCondition
    evidence_ledger_id: StableId
    evidence_ledger_identity_sha256: Sha256Digest
    seed: ExpandingOntologySeed
    policy: OntologyExpansionPolicy
    contexts: list[OntologyProposalContext] = Field(default_factory=list)
    proposals: list[OntologyDimensionProposal] = Field(default_factory=list)
    decisions: list[OntologyProposalDecision] = Field(default_factory=list)
    support_events: list[OntologyDimensionSupportEvent] = Field(
        default_factory=list
    )
    merge_events: list[OntologyDimensionMergeEvent] = Field(default_factory=list)
    prune_events: list[OntologyDimensionPruneEvent] = Field(default_factory=list)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")

    @model_validator(mode="after")
    def validate_local_identity(self) -> Self:
        groups = [
            ("context ids", [item.context_id for item in self.contexts]),
            ("proposal ids", [item.proposal_id for item in self.proposals]),
            ("decision ids", [item.decision_id for item in self.decisions]),
            ("support ids", [item.support_id for item in self.support_events]),
            ("merge ids", [item.merge_id for item in self.merge_events]),
            ("prune ids", [item.prune_id for item in self.prune_events]),
        ]
        for label, ids in groups:
            _require_unique(ids, label)
        collections: list[tuple[str, list[_OntologyRecord]]] = [
            ("contexts", list(self.contexts)),
            ("proposals", list(self.proposals)),
            ("decisions", list(self.decisions)),
            ("support events", list(self.support_events)),
            ("merge events", list(self.merge_events)),
            ("prune events", list(self.prune_events)),
        ]
        for label, collection in collections:
            if collection != sorted(collection, key=lambda item: item.sequence):
                raise ValueError(f"ontology {label} must use sequence order")
        records: list[_OntologyRecord] = [
            *self.contexts,
            *self.proposals,
            *self.decisions,
            *self.support_events,
            *self.merge_events,
            *self.prune_events,
        ]
        if any(record.session_id != self.session_id for record in records):
            raise ValueError("every ontology record must match ledger session")
        sequences = [record.sequence for record in records]
        if len(sequences) != len(set(sequences)):
            raise ValueError("ontology record sequences must be globally unique")
        ordered = sorted(records, key=lambda record: record.sequence)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.created_at < earlier.created_at:
                raise ValueError("ontology sequence must agree with time")
        if self.evidence_condition is EvidenceCondition.STRUCTURED_ONLY:
            if records:
                raise ValueError(
                    "structured-only ontology cannot contain expansion records"
                )
        return self


@dataclass
class _MutableDimension:
    definition: OntologyDimensionDefinition
    status: ExpandingDimensionStatus
    is_seed: bool
    introduced_sequence: int
    last_reinforced_sequence: int
    support_event_ids: set[str]
    support_lineage_ids: set[str]
    admission_confirmation_count: int
    merged_into_dimension_id: str | None = None


def _active_evidence_reference_map(
    confirmed_references: list[ConfirmedEvidenceReference],
    *,
    cutoff_sequence: int,
    condition: EvidenceCondition,
) -> dict[str, ConfirmedEvidenceReference]:
    return {
        reference.evidence_event_id: reference
        for reference in _active_references_at_cutoff(
            confirmed_references,
            cutoff_sequence=cutoff_sequence,
            condition=condition,
        )
    }


def _all_evidence_records(
    ledger: FixedOntologyEvidenceLedger,
) -> list[ContractModel]:
    return [
        *ledger.messages,
        *ledger.extraction_requests,
        *ledger.proposals,
        *ledger.decisions,
        *ledger.structured_evidence,
        *ledger.corrections,
    ]


def _validate_evidence_ledger_binding(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
) -> None:
    if ledger.session_id != evidence_ledger.session_id:
        raise ValueError("ontology and evidence ledgers use different sessions")
    if ledger.evidence_ledger_id != evidence_ledger.ledger_id:
        raise ValueError("ontology ledger references the wrong evidence ledger")
    if ledger.evidence_ledger_identity_sha256 != evidence_ledger_identity_sha256(
        evidence_ledger
    ):
        raise ValueError("ontology evidence-ledger identity hash does not match")
    if ledger.seed.ontology_id != evidence_ledger.ontology.ontology_id:
        raise ValueError("expanding seed references the wrong fixed ontology")
    if ledger.seed.seed_version != evidence_ledger.ontology.ontology_version:
        raise ValueError("expanding seed version does not match fixed ontology")
    seed_ids = [item.dimension_id for item in ledger.seed.dimensions]
    if seed_ids != evidence_ledger.ontology.item_ids:
        raise ValueError("expanding seed must define every fixed ontology item")
    evidence_sequences = {
        record.sequence for record in _all_evidence_records(evidence_ledger)
    }
    ontology_records: list[_OntologyRecord] = [
        *ledger.contexts,
        *ledger.proposals,
        *ledger.decisions,
        *ledger.support_events,
        *ledger.merge_events,
        *ledger.prune_events,
    ]
    if evidence_sequences & {record.sequence for record in ontology_records}:
        raise ValueError("ontology and evidence records cannot share a sequence")
    combined = [*_all_evidence_records(evidence_ledger), *ontology_records]
    ordered = sorted(combined, key=lambda record: record.sequence)
    for earlier, later in zip(ordered, ordered[1:]):
        if later.created_at < earlier.created_at:
            raise ValueError(
                "combined evidence and ontology sequence disagrees with time"
            )


def _require_active_prior_evidence(
    evidence_ids: list[str],
    *,
    before_sequence: int,
    confirmed_references: list[ConfirmedEvidenceReference],
    condition: EvidenceCondition,
) -> list[ConfirmedEvidenceReference]:
    references = _active_evidence_reference_map(
        confirmed_references,
        cutoff_sequence=before_sequence - 1,
        condition=condition,
    )
    resolved = []
    for evidence_id in evidence_ids:
        reference = references.get(evidence_id)
        if reference is None:
            raise ValueError(
                "ontology record must reference active prior confirmed evidence"
            )
        resolved.append(reference)
    return resolved


def _add_support(
    dimension: _MutableDimension,
    references: list[ConfirmedEvidenceReference],
    *,
    reinforced_sequence: int,
) -> None:
    dimension.support_event_ids.update(
        reference.evidence_event_id for reference in references
    )
    dimension.support_lineage_ids.update(
        reference.evidence_lineage_id for reference in references
    )
    dimension.last_reinforced_sequence = reinforced_sequence


def _support_score(
    *,
    admission_confirmation_count: int,
    evidence_lineage_count: int,
    policy: OntologyExpansionPolicy,
) -> float:
    return (
        admission_confirmation_count
        * policy.admission_confirmation_support_weight
        + evidence_lineage_count
        * policy.evidence_lineage_support_weight
    )


def _shrinkage_weight_from_score(
    support_score: float,
    full_weight_support_score: float,
) -> float:
    if support_score > full_weight_support_score or _float_equal(
        support_score,
        full_weight_support_score,
    ):
        return 1.0
    return support_score / full_weight_support_score


def _snapshot_from_dimensions(
    ledger: ExpandingOntologyLedger,
    dimensions: dict[str, _MutableDimension],
    cutoff_sequence: int,
) -> ExpandingOntologySnapshot:
    states = []
    for dimension_id in sorted(dimensions):
        item = dimensions[dimension_id]
        support_score = _support_score(
            admission_confirmation_count=item.admission_confirmation_count,
            evidence_lineage_count=len(item.support_lineage_ids),
            policy=ledger.policy,
        )
        shrinkage_weight = None
        if item.status is ExpandingDimensionStatus.ACTIVE:
            shrinkage_weight = (
                1.0
                if item.is_seed
                else _shrinkage_weight_from_score(
                    support_score,
                    ledger.policy.full_weight_support_score,
                )
            )
        states.append(
            ExpandingOntologyDimensionState(
                dimension=item.definition,
                status=item.status,
                is_seed=item.is_seed,
                introduced_sequence=item.introduced_sequence,
                last_reinforced_sequence=item.last_reinforced_sequence,
                supporting_evidence_event_ids=sorted(item.support_event_ids),
                supporting_evidence_lineage_ids=sorted(
                    item.support_lineage_ids
                ),
                admission_confirmation_count=(
                    item.admission_confirmation_count
                ),
                independent_evidence_lineage_count=len(
                    item.support_lineage_ids
                ),
                support_score=support_score,
                shrinkage_weight=shrinkage_weight,
                merged_into_dimension_id=item.merged_into_dimension_id,
            )
        )
    return ExpandingOntologySnapshot(
        ontology_id=ledger.seed.ontology_id,
        seed_version=ledger.seed.seed_version,
        event_cutoff_sequence=cutoff_sequence,
        policy=ledger.policy,
        policy_sha256=content_sha256(ledger.policy),
        dimensions=states,
    )


def _initial_dimensions(
    seed: ExpandingOntologySeed,
) -> dict[str, _MutableDimension]:
    return {
        definition.dimension_id: _MutableDimension(
            definition=definition,
            status=ExpandingDimensionStatus.ACTIVE,
            is_seed=True,
            introduced_sequence=0,
            last_reinforced_sequence=0,
            support_event_ids=set(),
            support_lineage_ids=set(),
            admission_confirmation_count=0,
        )
        for definition in seed.dimensions
    }


def _replay_confirmed_ontology_events(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
    *,
    cutoff_sequence: int,
    confirmed_references: list[ConfirmedEvidenceReference] | None = None,
) -> ExpandingOntologySnapshot:
    """Replay confirmed changes after input bindings have been validated."""

    if cutoff_sequence < 0:
        raise ValueError("ontology cutoff cannot be negative")
    contexts = {context.context_id: context for context in ledger.contexts}
    proposals = {proposal.proposal_id: proposal for proposal in ledger.proposals}
    decisions_by_proposal: dict[str, OntologyProposalDecision] = {}
    dimensions = _initial_dimensions(ledger.seed)
    if confirmed_references is None:
        confirmed_references = confirmed_evidence_references(evidence_ledger)

    events: list[
        OntologyProposalDecision
        | OntologyDimensionSupportEvent
        | OntologyDimensionMergeEvent
        | OntologyDimensionPruneEvent
    ] = [
        *ledger.decisions,
        *ledger.support_events,
        *ledger.merge_events,
        *ledger.prune_events,
    ]
    for event in sorted(events, key=lambda item: item.sequence):
        if event.sequence > cutoff_sequence:
            break
        if isinstance(event, OntologyProposalDecision):
            proposal = proposals.get(event.proposal_id)
            if proposal is None:
                raise ValueError("ontology decision references unknown proposal")
            if event.proposal_id in decisions_by_proposal:
                raise ValueError("each dimension proposal may have one decision")
            decisions_by_proposal[event.proposal_id] = event
            context = contexts.get(proposal.context_id)
            if context is None:
                raise ValueError("dimension proposal references unknown context")
            if proposal.context_sha256 != content_sha256(context):
                raise ValueError("dimension proposal context hash does not match")
            if proposal.sequence <= context.sequence:
                raise ValueError("dimension proposal must follow its context")
            if event.sequence <= proposal.sequence:
                raise ValueError("ontology decision must follow its proposal")
            support_references = _require_active_prior_evidence(
                proposal.supporting_evidence_event_ids,
                before_sequence=event.sequence,
                confirmed_references=confirmed_references,
                condition=ledger.evidence_condition,
            )
            expected_candidates = proposal.candidate_duplicate_dimension_ids
            if event.acknowledged_candidate_dimension_ids != expected_candidates:
                if event.decision is not OntologyProposalDecisionKind.REJECT:
                    raise ValueError(
                        "participant must acknowledge duplicate candidates"
                    )
            expected_flags = [
                flag.flag_id for flag in proposal.unsupported_assumptions
            ]
            if event.acknowledged_assumption_flag_ids != expected_flags:
                if event.decision is not OntologyProposalDecisionKind.REJECT:
                    raise ValueError(
                        "participant must acknowledge ontology assumptions"
                    )
            if event.decision is OntologyProposalDecisionKind.REJECT:
                continue
            active_ids = {
                dimension_id
                for dimension_id, item in dimensions.items()
                if item.status is ExpandingDimensionStatus.ACTIVE
            }
            unknown_candidates = set(expected_candidates) - active_ids
            if unknown_candidates:
                raise ValueError("duplicate candidates must be active dimensions")
            if event.decision is OntologyProposalDecisionKind.MAP_TO_EXISTING:
                target_id = event.mapped_dimension_id
                if target_id not in active_ids:
                    raise ValueError("mapped dimension must be active")
                if target_id not in set(expected_candidates):
                    raise ValueError("mapped target must be a reviewed duplicate")
                target = dimensions[target_id]
                _add_support(
                    target,
                    support_references,
                    reinforced_sequence=event.sequence,
                )
                continue

            admitted = event.admitted_dimension
            if admitted is None:
                raise ValueError("admission lacks participant-approved dimension")
            if admitted.dimension_id != proposal.proposed_dimension.dimension_id:
                raise ValueError("admitted dimension id must match proposal")
            if admitted.dimension_id in dimensions:
                raise ValueError("admission cannot reuse a dimension id")
            semantic_hash = dimension_semantic_sha256(admitted)
            if semantic_hash in {
                dimension_semantic_sha256(item.definition)
                for item in dimensions.values()
            }:
                raise ValueError("exact semantic duplicate cannot be admitted")
            supporting_lineages = {
                reference.evidence_lineage_id
                for reference in support_references
            }
            dimensions[admitted.dimension_id] = _MutableDimension(
                definition=admitted,
                status=ExpandingDimensionStatus.ACTIVE,
                is_seed=False,
                introduced_sequence=event.sequence,
                last_reinforced_sequence=event.sequence,
                support_event_ids={
                    reference.evidence_event_id
                    for reference in support_references
                },
                support_lineage_ids=supporting_lineages,
                admission_confirmation_count=1,
            )
            continue

        if isinstance(event, OntologyDimensionSupportEvent):
            dimension = dimensions.get(event.dimension_id)
            if (
                dimension is None
                or dimension.status is not ExpandingDimensionStatus.ACTIVE
            ):
                raise ValueError("support target must be an active dimension")
            support_references = _require_active_prior_evidence(
                event.evidence_event_ids,
                before_sequence=event.sequence,
                confirmed_references=confirmed_references,
                condition=ledger.evidence_condition,
            )
            _add_support(
                dimension,
                support_references,
                reinforced_sequence=event.sequence,
            )
            continue

        if isinstance(event, OntologyDimensionMergeEvent):
            sources = [
                dimensions.get(source_id)
                for source_id in event.source_dimension_ids
            ]
            if any(source is None for source in sources):
                raise ValueError("merge references unknown dimension")
            resolved_sources = [source for source in sources if source is not None]
            if any(
                source.status is not ExpandingDimensionStatus.ACTIVE
                for source in resolved_sources
            ):
                raise ValueError("merge sources must be active")
            if any(source.is_seed for source in resolved_sources):
                raise ValueError("seed dimensions cannot be merged")
            merged_id = event.merged_dimension.dimension_id
            if merged_id in dimensions:
                raise ValueError("merge cannot reuse a dimension id")
            semantic_hash = dimension_semantic_sha256(event.merged_dimension)
            outside_source_semantics = {
                dimension_semantic_sha256(item.definition)
                for dimension_id, item in dimensions.items()
                if dimension_id not in event.source_dimension_ids
            }
            if semantic_hash in outside_source_semantics:
                raise ValueError(
                    "merged dimension duplicates another ontology dimension"
                )
            additional_references = _require_active_prior_evidence(
                event.additional_evidence_event_ids,
                before_sequence=event.sequence,
                confirmed_references=confirmed_references,
                condition=ledger.evidence_condition,
            )
            support_event_ids = {
                reference.evidence_event_id
                for reference in additional_references
            }
            support_lineage_ids = {
                reference.evidence_lineage_id
                for reference in additional_references
            }
            for source in resolved_sources:
                support_event_ids.update(source.support_event_ids)
                support_lineage_ids.update(source.support_lineage_ids)
                source.status = ExpandingDimensionStatus.MERGED
                source.merged_into_dimension_id = merged_id
            dimensions[merged_id] = _MutableDimension(
                definition=event.merged_dimension,
                status=ExpandingDimensionStatus.ACTIVE,
                is_seed=False,
                introduced_sequence=event.sequence,
                last_reinforced_sequence=event.sequence,
                support_event_ids=support_event_ids,
                support_lineage_ids=support_lineage_ids,
                admission_confirmation_count=1,
            )
            continue

        dimension = dimensions.get(event.dimension_id)
        if dimension is None or dimension.status is not ExpandingDimensionStatus.ACTIVE:
            raise ValueError("prune target must be an active dimension")
        if dimension.is_seed:
            raise ValueError("seed dimensions cannot be pruned")
        support_score = _support_score(
            admission_confirmation_count=(
                dimension.admission_confirmation_count
            ),
            evidence_lineage_count=len(dimension.support_lineage_ids),
            policy=ledger.policy,
        )
        if support_score > ledger.policy.prune_max_support_score and not (
            _float_equal(
                support_score,
                ledger.policy.prune_max_support_score,
            )
        ):
            raise ValueError("dimension has too much support to prune")
        idle_gap = event.sequence - dimension.last_reinforced_sequence
        if idle_gap < ledger.policy.prune_min_idle_sequence_gap:
            raise ValueError("dimension is not idle long enough to prune")
        dimension.status = ExpandingDimensionStatus.PRUNED

    return _snapshot_from_dimensions(ledger, dimensions, cutoff_sequence)


def _validate_contexts_and_proposals(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
    confirmed_references: list[ConfirmedEvidenceReference],
) -> None:
    configurations = {
        item.configuration_id: item
        for item in evidence_ledger.extractor_configurations
    }
    messages = {item.message_id: item for item in evidence_ledger.messages}
    contexts = {item.context_id: item for item in ledger.contexts}
    parent_by_context_id: dict[str, ExpandingOntologySnapshot] = {}

    for context in sorted(ledger.contexts, key=lambda item: item.sequence):
        if context.expansion_ledger_id != ledger.ledger_id:
            raise ValueError("ontology context references the wrong expansion ledger")
        if context.evidence_condition is not ledger.evidence_condition:
            raise ValueError("ontology context uses the wrong evidence condition")
        if context.evidence_ledger_id != evidence_ledger.ledger_id:
            raise ValueError("ontology context references the wrong evidence ledger")
        if context.evidence_ledger_identity_sha256 != (
            evidence_ledger_identity_sha256(evidence_ledger)
        ):
            raise ValueError(
                "ontology context evidence-ledger identity hash does not match"
            )
        if context.seed_sha256 != content_sha256(ledger.seed):
            raise ValueError("ontology context seed hash does not match")
        if context.policy_sha256 != content_sha256(ledger.policy):
            raise ValueError("ontology context policy hash does not match")

        configuration = configurations.get(context.extractor_configuration_id)
        if configuration is None:
            raise ValueError("ontology context references unknown configuration")
        if context.extractor_configuration_sha256 != content_sha256(configuration):
            raise ValueError("ontology context configuration hash does not match")

        expected_messages = sorted(
            (
                message
                for message in evidence_ledger.messages
                if message.sequence <= context.message_cutoff_sequence
            ),
            key=lambda item: item.sequence,
        )
        if not expected_messages:
            raise ValueError("ontology context requires a nonempty message prefix")
        if expected_messages[-1].sequence != context.message_cutoff_sequence:
            raise ValueError("ontology message cutoff must identify a message")
        later_prior_messages = [
            message
            for message in evidence_ledger.messages
            if context.message_cutoff_sequence
            < message.sequence
            < context.sequence
        ]
        if later_prior_messages:
            raise ValueError("ontology context must use the latest message prefix")
        if context.input_message_ids != [
            message.message_id for message in expected_messages
        ]:
            raise ValueError("ontology context must bind the exact message prefix")
        if context.input_messages_sha256 != conversation_messages_sha256(
            expected_messages
        ):
            raise ValueError("ontology context message hash does not match")

        expected_evidence = confirmed_evidence_support_candidates(
            evidence_ledger,
            cutoff_sequence=context.evidence_cutoff_sequence,
            condition=ledger.evidence_condition,
        )
        if context.eligible_evidence_event_ids != [
            item.reference.evidence_event_id for item in expected_evidence
        ]:
            raise ValueError("ontology context must bind exact active evidence")
        if context.eligible_evidence != expected_evidence:
            raise ValueError("ontology context evidence records do not match")
        if context.eligible_evidence_sha256 != content_sha256(
            [item.model_dump(mode="json") for item in expected_evidence]
        ):
            raise ValueError("ontology context eligible-evidence hash does not match")
        later_prior_evidence = [
            reference
            for reference in confirmed_references
            if _reference_matches_condition(
                reference,
                ledger.evidence_condition,
            )
            if context.evidence_cutoff_sequence
            < reference.sequence
            < context.sequence
        ]
        if later_prior_evidence:
            raise ValueError("ontology context must use the latest evidence prefix")

        parent = _replay_confirmed_ontology_events(
            ledger,
            evidence_ledger,
            cutoff_sequence=context.sequence - 1,
            confirmed_references=confirmed_references,
        )
        parent_by_context_id[context.context_id] = parent
        if context.parent_snapshot_sha256 != content_sha256(parent):
            raise ValueError("ontology context parent snapshot hash does not match")
        expected_active = [
            item.dimension for item in active_dimension_states(parent)
        ]
        if context.active_dimensions != expected_active:
            raise ValueError("ontology context active dimensions do not match parent")
        expected_retired = [
            item.dimension for item in _retired_dimension_states(parent)
        ]
        if context.retired_dimensions != expected_retired:
            raise ValueError("ontology context retired dimensions do not match parent")

    for proposal in sorted(ledger.proposals, key=lambda item: item.sequence):
        context = contexts.get(proposal.context_id)
        if context is None:
            raise ValueError("dimension proposal references unknown context")
        if proposal.context_sha256 != content_sha256(context):
            raise ValueError("dimension proposal context hash does not match")
        if proposal.sequence <= context.sequence:
            raise ValueError("dimension proposal must follow its context")
        if not set(proposal.source_message_ids) <= set(context.input_message_ids):
            raise ValueError("dimension sources exceed the context message prefix")
        if any(
            messages[message_id].role is not ConversationRole.PARTICIPANT
            for message_id in proposal.source_message_ids
        ):
            raise ValueError("dimension sources must be participant messages")
        expected_source_order = [
            message_id
            for message_id in context.input_message_ids
            if message_id in set(proposal.source_message_ids)
        ]
        if proposal.source_message_ids != expected_source_order:
            raise ValueError("dimension source messages must use context order")
        if not set(proposal.supporting_evidence_event_ids) <= set(
            context.eligible_evidence_event_ids
        ):
            raise ValueError("dimension support exceeds confirmed evidence cutoff")
        expected_support_order = [
            evidence_id
            for evidence_id in context.eligible_evidence_event_ids
            if evidence_id in set(proposal.supporting_evidence_event_ids)
        ]
        if proposal.supporting_evidence_event_ids != expected_support_order:
            raise ValueError("dimension support must use context evidence order")
        if proposal.candidate_duplicate_dimension_ids != sorted(
            proposal.candidate_duplicate_dimension_ids
        ):
            raise ValueError("duplicate candidates must use canonical id order")
        parent = parent_by_context_id[context.context_id]
        parent_by_id = {
            item.dimension.dimension_id: item for item in parent.dimensions
        }
        if proposal.proposed_dimension.dimension_id in parent_by_id:
            raise ValueError("dimension proposal cannot reuse an ontology id")
        active_by_id = {
            item.dimension.dimension_id: item.dimension
            for item in active_dimension_states(parent)
        }
        if not set(proposal.candidate_duplicate_dimension_ids) <= set(active_by_id):
            raise ValueError("duplicate candidates must be active at proposal context")
        retired_by_id = {
            item.dimension.dimension_id: item.dimension
            for item in _retired_dimension_states(parent)
        }
        proposed_semantic_hash = dimension_semantic_sha256(
            proposal.proposed_dimension
        )
        if any(
            dimension_semantic_sha256(definition) == proposed_semantic_hash
            for definition in retired_by_id.values()
        ):
            raise ValueError("retired dimension semantics cannot be reproposed")
        exact_semantic_ids = {
            dimension_id
            for dimension_id, definition in active_by_id.items()
            if dimension_semantic_sha256(definition)
            == proposed_semantic_hash
        }
        if not exact_semantic_ids <= set(
            proposal.candidate_duplicate_dimension_ids
        ):
            raise ValueError("exact semantic duplicate must be identified")


def _max_ontology_sequence(ledger: ExpandingOntologyLedger) -> int:
    records: list[_OntologyRecord] = [
        *ledger.contexts,
        *ledger.proposals,
        *ledger.decisions,
        *ledger.support_events,
        *ledger.merge_events,
        *ledger.prune_events,
    ]
    return max((record.sequence for record in records), default=0)


def _validate_complete_expansion(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
) -> tuple[ExpandingOntologyLedger, FixedOntologyEvidenceLedger]:
    validated_ledger = ExpandingOntologyLedger.model_validate(
        ledger.model_dump(mode="json")
    )
    validated_evidence = FixedOntologyEvidenceLedger.model_validate(
        evidence_ledger.model_dump(mode="json")
    )
    confirmed_references = confirmed_evidence_references(validated_evidence)
    _validate_evidence_ledger_binding(validated_ledger, validated_evidence)
    _validate_contexts_and_proposals(
        validated_ledger,
        validated_evidence,
        confirmed_references,
    )
    _replay_confirmed_ontology_events(
        validated_ledger,
        validated_evidence,
        cutoff_sequence=_max_ontology_sequence(validated_ledger),
        confirmed_references=confirmed_references,
    )
    return validated_ledger, validated_evidence


def replay_expanding_ontology(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
    *,
    cutoff_sequence: int,
) -> ExpandingOntologySnapshot:
    """Replay the validated participant-confirmed ontology at one cutoff."""

    if cutoff_sequence < 0:
        raise ValueError("ontology cutoff cannot be negative")
    validated_ledger, validated_evidence = _validate_complete_expansion(
        ledger,
        evidence_ledger,
    )
    return _replay_confirmed_ontology_events(
        validated_ledger,
        validated_evidence,
        cutoff_sequence=cutoff_sequence,
    )


def validate_expanding_ontology_ledger(
    ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
) -> None:
    """Validate every record, including those after the current active cutoff."""

    _validate_complete_expansion(ledger, evidence_ledger)


def build_ontology_proposal_context(
    *,
    context_id: str,
    expansion_ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
    configuration: EvidenceExtractorConfiguration,
    sequence: int,
    created_at: datetime,
    message_cutoff_sequence: int,
    evidence_cutoff_sequence: int,
) -> OntologyProposalContext:
    """Bind exact conversation, evidence, policy, and parent ontology inputs."""

    if expansion_ledger.evidence_condition is EvidenceCondition.STRUCTURED_ONLY:
        raise ValueError(
            "structured-only ontology cannot use conversation proposals"
        )
    if expansion_ledger.evidence_ledger_identity_sha256 != (
        evidence_ledger_identity_sha256(evidence_ledger)
    ):
        raise ValueError("expansion ledger does not bind the evidence ledger")
    configurations = {
        item.configuration_id: item
        for item in evidence_ledger.extractor_configurations
    }
    if configurations.get(configuration.configuration_id) != configuration:
        raise ValueError("ontology context configuration is not evidence-bound")
    if sequence <= evidence_cutoff_sequence:
        raise ValueError("ontology context must follow its evidence cutoff")
    if any(
        message_cutoff_sequence < message.sequence < sequence
        for message in evidence_ledger.messages
    ):
        raise ValueError("ontology context must use the latest message prefix")
    if any(
        _reference_matches_condition(
            reference,
            expansion_ledger.evidence_condition,
        )
        and evidence_cutoff_sequence < reference.sequence < sequence
        for reference in confirmed_evidence_references(evidence_ledger)
    ):
        raise ValueError("ontology context must use the latest evidence prefix")
    messages = sorted(
        (
            message
            for message in evidence_ledger.messages
            if message.sequence <= message_cutoff_sequence
        ),
        key=lambda message: message.sequence,
    )
    if not messages or messages[-1].sequence != message_cutoff_sequence:
        raise ValueError("message cutoff must identify the final input message")
    eligible = confirmed_evidence_support_candidates(
        evidence_ledger,
        cutoff_sequence=evidence_cutoff_sequence,
        condition=expansion_ledger.evidence_condition,
    )
    parent = replay_expanding_ontology(
        expansion_ledger,
        evidence_ledger,
        cutoff_sequence=sequence - 1,
    )
    active_states = active_dimension_states(parent)
    retired_states = _retired_dimension_states(parent)
    active_dimensions = [item.dimension for item in active_states]
    retired_dimensions = [item.dimension for item in retired_states]
    return OntologyProposalContext(
        context_id=context_id,
        expansion_ledger_id=expansion_ledger.ledger_id,
        evidence_condition=expansion_ledger.evidence_condition,
        session_id=expansion_ledger.session_id,
        sequence=sequence,
        created_at=created_at,
        evidence_ledger_id=evidence_ledger.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            evidence_ledger
        ),
        seed_sha256=content_sha256(expansion_ledger.seed),
        policy_sha256=content_sha256(expansion_ledger.policy),
        parent_snapshot_sha256=content_sha256(parent),
        active_dimensions=active_dimensions,
        active_dimensions_sha256=content_sha256(
            [
                item.dimension.model_dump(mode="json")
                for item in active_states
            ]
        ),
        retired_dimensions=retired_dimensions,
        retired_dimensions_sha256=content_sha256(
            [
                item.dimension.model_dump(mode="json")
                for item in retired_states
            ]
        ),
        extractor_configuration_id=configuration.configuration_id,
        extractor_configuration_sha256=content_sha256(configuration),
        message_cutoff_sequence=message_cutoff_sequence,
        input_message_ids=[message.message_id for message in messages],
        input_messages_sha256=conversation_messages_sha256(messages),
        evidence_cutoff_sequence=evidence_cutoff_sequence,
        eligible_evidence=eligible,
        eligible_evidence_event_ids=[
            item.reference.evidence_event_id for item in eligible
        ],
        eligible_evidence_sha256=content_sha256(
            [reference.model_dump(mode="json") for reference in eligible]
        ),
    )


def run_ontology_expansion_backend(
    *,
    context: OntologyProposalContext,
    expansion_ledger: ExpandingOntologyLedger,
    evidence_ledger: FixedOntologyEvidenceLedger,
    backend: OntologyExpansionBackend,
    proposal_ids: list[str],
    proposal_sequences: list[int],
    created_at: datetime,
) -> list[OntologyDimensionProposal]:
    """Execute and revalidate a provider-neutral ontology proposal call."""

    context = OntologyProposalContext.model_validate(
        context.model_dump(mode="json")
    )
    evidence_ledger = FixedOntologyEvidenceLedger.model_validate(
        evidence_ledger.model_dump(mode="json")
    )
    expansion_ledger = ExpandingOntologyLedger.model_validate(
        expansion_ledger.model_dump(mode="json")
    )
    existing_contexts = {
        item.context_id: item for item in expansion_ledger.contexts
    }
    existing_context = existing_contexts.get(context.context_id)
    if existing_context is not None and existing_context != context:
        raise ValueError("ontology context id already binds different content")
    contextualized_ledger = expansion_ledger.model_copy(
        update={
            "contexts": (
                expansion_ledger.contexts
                if existing_context is not None
                else [*expansion_ledger.contexts, context]
            )
        }
    )
    _validate_complete_expansion(contextualized_ledger, evidence_ledger)
    backend_configuration = EvidenceExtractorConfiguration.model_validate(
        backend.configuration.model_dump(mode="json")
    )
    if context.evidence_condition is EvidenceCondition.STRUCTURED_ONLY:
        raise ValueError(
            "structured-only ontology cannot use conversation proposals"
        )
    if context.evidence_ledger_id != evidence_ledger.ledger_id:
        raise ValueError("ontology context references the wrong evidence ledger")
    if context.evidence_ledger_identity_sha256 != evidence_ledger_identity_sha256(
        evidence_ledger
    ):
        raise ValueError(
            "ontology context evidence-ledger identity hash does not match"
        )
    configurations = {
        item.configuration_id: item
        for item in evidence_ledger.extractor_configurations
    }
    if configurations.get(backend_configuration.configuration_id) != (
        backend_configuration
    ):
        raise ValueError("ontology backend configuration is not evidence-bound")
    if context.extractor_configuration_id != (
        backend_configuration.configuration_id
    ):
        raise ValueError("ontology context configuration id does not match backend")
    if context.extractor_configuration_sha256 != content_sha256(
        backend_configuration
    ):
        raise ValueError("ontology context configuration hash does not match backend")
    by_id = {message.message_id: message for message in evidence_ledger.messages}
    try:
        messages = [by_id[message_id] for message_id in context.input_message_ids]
    except KeyError as error:
        raise ValueError("ontology context references unknown message") from error
    if conversation_messages_sha256(messages) != context.input_messages_sha256:
        raise ValueError("ontology context message hash does not match")
    expected_evidence = confirmed_evidence_support_candidates(
        evidence_ledger,
        cutoff_sequence=context.evidence_cutoff_sequence,
        condition=context.evidence_condition,
    )
    if context.eligible_evidence_event_ids != [
        item.reference.evidence_event_id for item in expected_evidence
    ]:
        raise ValueError("ontology context eligible evidence does not match")
    if context.eligible_evidence != expected_evidence:
        raise ValueError("ontology context evidence records do not match")
    if context.eligible_evidence_sha256 != content_sha256(
        [item.model_dump(mode="json") for item in expected_evidence]
    ):
        raise ValueError("ontology context eligible-evidence hash does not match")
    raw_drafts = backend.propose(context.model_copy(deep=True), tuple(messages))
    drafts = _ONTOLOGY_DRAFTS_ADAPTER.validate_python(
        [
            draft.model_dump(mode="json")
            if isinstance(draft, OntologyDimensionProposalDraft)
            else draft
            for draft in raw_drafts
        ]
    )
    if len(drafts) != len(proposal_ids) or len(drafts) != len(proposal_sequences):
        raise ValueError("proposal identities must cover ontology drafts")
    _require_unique(proposal_ids, "ontology proposal ids")
    if len(proposal_sequences) != len(set(proposal_sequences)):
        raise ValueError("ontology proposal sequences must be unique")
    if proposal_sequences != sorted(proposal_sequences):
        raise ValueError("ontology proposal sequences must use canonical order")
    if any(sequence <= context.sequence for sequence in proposal_sequences):
        raise ValueError("ontology proposals must follow their context")
    _require_aware(created_at, "created_at")
    if created_at < context.created_at:
        raise ValueError("ontology proposal cannot predate context")

    participant_message_ids = {
        message.message_id
        for message in messages
        if message.role is ConversationRole.PARTICIPANT
    }
    eligible_evidence_ids = set(context.eligible_evidence_event_ids)
    active_dimensions = {
        dimension.dimension_id: dimension
        for dimension in context.active_dimensions
    }
    retired_dimensions = {
        dimension.dimension_id: dimension
        for dimension in context.retired_dimensions
    }
    proposals = []
    for draft, proposal_id, sequence in zip(
        drafts, proposal_ids, proposal_sequences, strict=True
    ):
        if not set(draft.source_message_ids) <= participant_message_ids:
            raise ValueError("dimension sources must be participant messages")
        if not set(draft.supporting_evidence_event_ids) <= eligible_evidence_ids:
            raise ValueError("dimension support exceeds confirmed evidence cutoff")
        if draft.source_message_ids != [
            message.message_id
            for message in messages
            if message.message_id in set(draft.source_message_ids)
        ]:
            raise ValueError("dimension source messages must use context order")
        if draft.supporting_evidence_event_ids != [
            evidence_id
            for evidence_id in context.eligible_evidence_event_ids
            if evidence_id in set(draft.supporting_evidence_event_ids)
        ]:
            raise ValueError("dimension support must use context evidence order")
        if draft.candidate_duplicate_dimension_ids != sorted(
            draft.candidate_duplicate_dimension_ids
        ):
            raise ValueError("duplicate candidates must use canonical id order")
        if not set(draft.candidate_duplicate_dimension_ids) <= set(
            active_dimensions
        ):
            raise ValueError("duplicate candidates must be active dimensions")
        if draft.proposed_dimension.dimension_id in {
            *active_dimensions,
            *retired_dimensions,
        }:
            raise ValueError("dimension proposal cannot reuse an ontology id")
        proposed_semantic_hash = dimension_semantic_sha256(
            draft.proposed_dimension
        )
        if any(
            dimension_semantic_sha256(definition) == proposed_semantic_hash
            for definition in retired_dimensions.values()
        ):
            raise ValueError("retired dimension semantics cannot be reproposed")
        exact_semantic_ids = {
            dimension_id
            for dimension_id, definition in active_dimensions.items()
            if dimension_semantic_sha256(definition)
            == proposed_semantic_hash
        }
        if not exact_semantic_ids <= set(
            draft.candidate_duplicate_dimension_ids
        ):
            raise ValueError("exact semantic duplicate must be identified")
        proposals.append(
            OntologyDimensionProposal(
                proposal_id=proposal_id,
                context_id=context.context_id,
                context_sha256=content_sha256(context),
                session_id=context.session_id,
                sequence=sequence,
                created_at=created_at,
                source_message_ids=draft.source_message_ids,
                proposed_dimension=draft.proposed_dimension,
                supporting_evidence_event_ids=(
                    draft.supporting_evidence_event_ids
                ),
                candidate_duplicate_dimension_ids=(
                    draft.candidate_duplicate_dimension_ids
                ),
                extractor_confidence=draft.extractor_confidence,
                unsupported_assumptions=draft.unsupported_assumptions,
            )
        )
    return proposals
