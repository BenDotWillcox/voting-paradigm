"""Provider-neutral, auditable Phase 4B interviewer boundary.

The interviewer may choose among vetted questions, request clarification of
already-recorded evidence, or pause. It cannot create evidence, update the
posterior, or inspect a held-out target packet. Provider adapters sit behind
``InterviewerBackend``; this module intentionally ships no live adapter.

Every backend input is content-addressed, every tool request and result is
recorded in full, and backend outputs can be cached without persisting private
conversation text. The deterministic backend is a test double for exercising
the boundary, not an experimental LLM arm.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self, TypeAlias

from pydantic import Field, TypeAdapter, field_validator, model_validator

from preferences.model.base import PreferenceModel
from preferences.questions.bank import QuestionBank
from preferences.serialization import state_to_dict
from preferences.types import Evidence, ItemId, PreferenceState

from .contracts import (
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    PrivateResponseText,
    Probability,
    Sha256Digest,
    StableId,
    require_complete_enum_set,
)
from .fixture_io import content_sha256
from .phase4_protocol import InterviewerAction, InterviewerTool

NonNegativeCount = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
SliderValue = Annotated[float, Field(ge=-10.0, le=10.0)]
INTERVIEWER_TOOL_SURFACE_VERSION = 1
INTERVIEWER_TOOL_IMPLEMENTATION_VERSION = 1


class ConversationRole(str, Enum):
    PARTICIPANT = "participant"
    INTERVIEWER = "interviewer"


class ClarificationKind(str, Enum):
    RESOLVE_CONFLICT = "resolve_conflict"
    CONFIRM_STRENGTH = "confirm_strength"
    CONFIRM_SCOPE = "confirm_scope"


class InterviewerBackendConfiguration(ContractModel):
    """Exact version and seed identity for one provider-neutral backend."""

    record_version: Literal["phase4_interviewer_backend.v1"] = (
        "phase4_interviewer_backend.v1"
    )
    backend_id: StableId
    backend_version: PositiveVersion
    model_id: StableId
    model_version: NonEmptyText
    prompt_id: StableId
    prompt_version: PositiveVersion
    prompt_sha256: Sha256Digest
    seed: int


class InterviewerMessage(ContractModel):
    record_version: Literal["phase4_interviewer_message.v1"] = (
        "phase4_interviewer_message.v1"
    )
    message_id: StableId
    sequence: PositiveCount
    role: ConversationRole
    content: PrivateResponseText


class EvidenceAuditReference(ContractModel):
    """Stable audit identity for evidence already present in a state.

    Phase 4C materialized evidence carries the event id directly. Legacy and
    synthetic states may still omit it, so this record continues to bind a
    caller-supplied id to one exact index and value in the current posterior
    state.
    """

    record_version: Literal["phase4_evidence_audit_reference.v1"] = (
        "phase4_evidence_audit_reference.v1"
    )
    evidence_event_id: StableId
    state_evidence_index: NonNegativeCount
    evidence_sha256: Sha256Digest
    item_a: StableId
    item_b: StableId
    value: SliderValue
    confidence: Probability

    @model_validator(mode="after")
    def require_distinct_items(self) -> Self:
        if self.item_a == self.item_b:
            raise ValueError("evidence reference items must be distinct")
        if self.confidence <= 0.0:
            raise ValueError("evidence reference confidence must be positive")
        return self


class InterviewerTurnRequest(ContractModel):
    """Complete private model input for one interviewer decision."""

    record_version: Literal["phase4_interviewer_turn_request.v1"] = (
        "phase4_interviewer_turn_request.v1"
    )
    session_id: StableId
    turn_index: PositiveCount
    question_bank_id: StableId
    question_bank_version: PositiveVersion
    question_bank_sha256: Sha256Digest
    preference_state_sha256: Sha256Digest
    evidence_cutoff_count: NonNegativeCount
    evidence_references: list[EvidenceAuditReference]
    conversation_history: list[InterviewerMessage]
    conversation_history_sha256: Sha256Digest
    backend: InterviewerBackendConfiguration
    allowed_actions: list[InterviewerAction]
    allowed_tools: list[InterviewerTool]
    tool_surface_version: Literal[1] = INTERVIEWER_TOOL_SURFACE_VERSION
    tool_implementation_version: Literal[1] = (
        INTERVIEWER_TOOL_IMPLEMENTATION_VERSION
    )
    target_packet_visible: Literal[False] = False

    @model_validator(mode="after")
    def validate_complete_input(self) -> Self:
        require_complete_enum_set(
            "allowed_actions",
            self.allowed_actions,
            InterviewerAction,
        )
        require_complete_enum_set(
            "allowed_tools",
            self.allowed_tools,
            InterviewerTool,
        )

        event_ids = [ref.evidence_event_id for ref in self.evidence_references]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("evidence reference ids must be unique")
        indices = [ref.state_evidence_index for ref in self.evidence_references]
        if indices != list(range(self.evidence_cutoff_count)):
            raise ValueError(
                "evidence references must cover the exact ordered evidence cutoff"
            )

        message_ids = [message.message_id for message in self.conversation_history]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("conversation message ids must be unique")
        sequences = [message.sequence for message in self.conversation_history]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("conversation messages must use contiguous sequence")
        expected_history_hash = content_sha256(
            [message.model_dump(mode="json") for message in self.conversation_history]
        )
        if self.conversation_history_sha256 != expected_history_hash:
            raise ValueError("conversation_history_sha256 does not match messages")
        return self


class PairReference(ContractModel):
    item_a: StableId
    item_b: StableId

    @model_validator(mode="after")
    def require_canonical_pair(self) -> Self:
        if self.item_a >= self.item_b:
            raise ValueError("pair reference items must be distinct and canonical")
        return self


class VettedQuestionOption(ContractModel):
    item_id: StableId
    text: NonEmptyText
    description: str = ""


class VettedQuestionCandidate(ContractModel):
    record_version: Literal["phase4_vetted_question_candidate.v1"] = (
        "phase4_vetted_question_candidate.v1"
    )
    question_id: StableId
    question_version: PositiveVersion
    question_sha256: Sha256Digest
    item_a: StableId
    item_b: StableId
    prompt: NonEmptyText
    options: list[VettedQuestionOption]
    domain: NonEmptyText | None = None
    score: Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
    score_kind: Literal["posterior_gap_std"] = "posterior_gap_std"

    @model_validator(mode="after")
    def validate_pair_and_options(self) -> Self:
        if self.item_a >= self.item_b:
            raise ValueError("candidate item pair must be canonical")
        if [option.item_id for option in self.options] != [
            self.item_a,
            self.item_b,
        ]:
            raise ValueError("candidate options must match the ordered item pair")
        if self.question_sha256 != vetted_question_sha256(self):
            raise ValueError("candidate question hash does not match content")
        return self


class ReadPosteriorUncertaintyRequest(ContractModel):
    record_version: Literal["read_posterior_uncertainty_request.v1"] = (
        "read_posterior_uncertainty_request.v1"
    )
    pair: PairReference


class ReadPosteriorUncertaintyResult(ContractModel):
    record_version: Literal["read_posterior_uncertainty_result.v1"] = (
        "read_posterior_uncertainty_result.v1"
    )
    pair: PairReference
    posterior_gap_std: Annotated[float, Field(ge=0.0)]
    model_version: NonEmptyText


class ReadCandidateQuestionScoresRequest(ContractModel):
    record_version: Literal["read_candidate_question_scores_request.v1"] = (
        "read_candidate_question_scores_request.v1"
    )
    limit: Annotated[int, Field(ge=1, le=100)] = 10
    excluded_question_ids: list[StableId] = Field(default_factory=list)

    @field_validator("excluded_question_ids")
    @classmethod
    def require_unique_exclusions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("excluded question ids must be unique")
        return value


class ReadCandidateQuestionScoresResult(ContractModel):
    record_version: Literal["read_candidate_question_scores_result.v1"] = (
        "read_candidate_question_scores_result.v1"
    )
    candidates: list[VettedQuestionCandidate]
    model_version: NonEmptyText


class ReadEvidenceCoverageRequest(ContractModel):
    record_version: Literal["read_evidence_coverage_request.v1"] = (
        "read_evidence_coverage_request.v1"
    )


class DomainEvidenceCoverage(ContractModel):
    """Coverage touching one domain, not a partition of all evidence.

    One cross-domain observation contributes to both domains, so the sum of
    ``touching_evidence_count`` can exceed the top-level ``evidence_count``.
    """

    domain: NonEmptyText
    item_count: NonNegativeCount
    observed_item_count: NonNegativeCount
    touching_evidence_count: NonNegativeCount


class ReadEvidenceCoverageResult(ContractModel):
    record_version: Literal["read_evidence_coverage_result.v1"] = (
        "read_evidence_coverage_result.v1"
    )
    evidence_count: NonNegativeCount
    item_count: PositiveCount
    observed_item_count: NonNegativeCount
    possible_pair_count: PositiveCount
    observed_pair_count: NonNegativeCount
    domains: list[DomainEvidenceCoverage]


class ReadEvidenceConflictsRequest(ContractModel):
    record_version: Literal["read_evidence_conflicts_request.v1"] = (
        "read_evidence_conflicts_request.v1"
    )


class EvidenceConflict(ContractModel):
    pair: PairReference
    positive_evidence_event_ids: list[StableId]
    negative_evidence_event_ids: list[StableId]


class ReadEvidenceConflictsResult(ContractModel):
    record_version: Literal["read_evidence_conflicts_result.v1"] = (
        "read_evidence_conflicts_result.v1"
    )
    conflicts: list[EvidenceConflict]


ToolRequest: TypeAlias = (
    ReadPosteriorUncertaintyRequest
    | ReadCandidateQuestionScoresRequest
    | ReadEvidenceCoverageRequest
    | ReadEvidenceConflictsRequest
)
ToolResult: TypeAlias = (
    ReadPosteriorUncertaintyResult
    | ReadCandidateQuestionScoresResult
    | ReadEvidenceCoverageResult
    | ReadEvidenceConflictsResult
)


class AskVettedQuestionDecision(ContractModel):
    record_version: Literal["phase4_ask_vetted_question.v1"] = (
        "phase4_ask_vetted_question.v1"
    )
    action: Literal[InterviewerAction.ASK_VETTED_QUESTION] = (
        InterviewerAction.ASK_VETTED_QUESTION
    )
    question: VettedQuestionCandidate
    rendering_mode: Literal["canonical_vetted"] = "canonical_vetted"


class ClarifyExistingEvidenceDecision(ContractModel):
    record_version: Literal["phase4_clarify_existing_evidence.v1"] = (
        "phase4_clarify_existing_evidence.v1"
    )
    action: Literal[InterviewerAction.CLARIFY_EXISTING_EVIDENCE] = (
        InterviewerAction.CLARIFY_EXISTING_EVIDENCE
    )
    clarification_kind: ClarificationKind
    linked_evidence_event_ids: list[StableId]

    @field_validator("linked_evidence_event_ids")
    @classmethod
    def require_unique_links(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("clarification must link at least one evidence id")
        if len(value) != len(set(value)):
            raise ValueError("clarification evidence ids must be unique")
        return value


class PauseAndResumeDecision(ContractModel):
    record_version: Literal["phase4_pause_and_resume.v1"] = (
        "phase4_pause_and_resume.v1"
    )
    action: Literal[InterviewerAction.PAUSE_AND_RESUME] = (
        InterviewerAction.PAUSE_AND_RESUME
    )


InterviewerDecision: TypeAlias = Annotated[
    AskVettedQuestionDecision
    | ClarifyExistingEvidenceDecision
    | PauseAndResumeDecision,
    Field(discriminator="action"),
]
_DECISION_ADAPTER = TypeAdapter(InterviewerDecision)


class InterviewerToolCallRecord(ContractModel):
    record_version: Literal["phase4_interviewer_tool_call.v1"] = (
        "phase4_interviewer_tool_call.v1"
    )
    call_sequence: PositiveCount
    tool: InterviewerTool
    request: ToolRequest
    request_sha256: Sha256Digest
    result: ToolResult
    result_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        expected_types: dict[
            InterviewerTool,
            tuple[type[ContractModel], type[ContractModel]],
        ] = {
            InterviewerTool.READ_POSTERIOR_UNCERTAINTY: (
                ReadPosteriorUncertaintyRequest,
                ReadPosteriorUncertaintyResult,
            ),
            InterviewerTool.READ_CANDIDATE_QUESTION_SCORES: (
                ReadCandidateQuestionScoresRequest,
                ReadCandidateQuestionScoresResult,
            ),
            InterviewerTool.READ_EVIDENCE_COVERAGE: (
                ReadEvidenceCoverageRequest,
                ReadEvidenceCoverageResult,
            ),
            InterviewerTool.READ_EVIDENCE_CONFLICTS: (
                ReadEvidenceConflictsRequest,
                ReadEvidenceConflictsResult,
            ),
        }
        request_type, result_type = expected_types[self.tool]
        if not isinstance(self.request, request_type) or not isinstance(
            self.result, result_type
        ):
            raise ValueError("tool call request/result types do not match tool")
        if self.request_sha256 != content_sha256(self.request):
            raise ValueError("tool request hash does not match request")
        if self.result_sha256 != content_sha256(self.result):
            raise ValueError("tool result hash does not match result")
        return self


class CachedInterviewerOutput(ContractModel):
    record_version: Literal["phase4_cached_interviewer_output.v1"] = (
        "phase4_cached_interviewer_output.v1"
    )
    request_sha256: Sha256Digest
    backend_configuration_sha256: Sha256Digest
    decision: InterviewerDecision
    tool_calls: list[InterviewerToolCallRecord]

    @model_validator(mode="after")
    def require_contiguous_tool_calls(self) -> Self:
        sequences = [call.call_sequence for call in self.tool_calls]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("tool call sequence must be contiguous")
        return self


class InterviewerTurnRecord(ContractModel):
    """Private audit record without raw conversation text."""

    record_version: Literal["phase4_interviewer_turn_record.v1"] = (
        "phase4_interviewer_turn_record.v1"
    )
    session_id: StableId
    turn_index: PositiveCount
    request_sha256: Sha256Digest
    conversation_history_sha256: Sha256Digest
    question_bank_sha256: Sha256Digest
    preference_state_sha256: Sha256Digest
    evidence_cutoff_count: NonNegativeCount
    evidence_event_ids: list[StableId]
    backend: InterviewerBackendConfiguration
    backend_configuration_sha256: Sha256Digest
    decision: InterviewerDecision
    tool_calls: list[InterviewerToolCallRecord]
    output_sha256: Sha256Digest
    cache_hit: bool
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        _require_aware_datetime(value)
        return value

    @model_validator(mode="after")
    def validate_audit_bindings(self) -> Self:
        if self.backend_configuration_sha256 != content_sha256(self.backend):
            raise ValueError("backend configuration hash does not match backend")
        if len(self.evidence_event_ids) != self.evidence_cutoff_count:
            raise ValueError("evidence ids must cover the exact evidence cutoff")
        if len(self.evidence_event_ids) != len(set(self.evidence_event_ids)):
            raise ValueError("audit evidence ids must be unique")
        output = CachedInterviewerOutput(
            request_sha256=self.request_sha256,
            backend_configuration_sha256=self.backend_configuration_sha256,
            decision=self.decision,
            tool_calls=self.tool_calls,
        )
        if self.output_sha256 != content_sha256(output):
            raise ValueError("output hash does not match decision and tool calls")
        if isinstance(self.decision, ClarifyExistingEvidenceDecision) and not set(
            self.decision.linked_evidence_event_ids
        ) <= set(self.evidence_event_ids):
            raise ValueError("audit clarification links unknown evidence")
        return self


class InterviewerToolProvider(Protocol):
    def read_posterior_uncertainty(
        self, request: ReadPosteriorUncertaintyRequest
    ) -> ReadPosteriorUncertaintyResult: ...

    def read_candidate_question_scores(
        self, request: ReadCandidateQuestionScoresRequest
    ) -> ReadCandidateQuestionScoresResult: ...

    def read_evidence_coverage(
        self, request: ReadEvidenceCoverageRequest
    ) -> ReadEvidenceCoverageResult: ...

    def read_evidence_conflicts(
        self, request: ReadEvidenceConflictsRequest
    ) -> ReadEvidenceConflictsResult: ...


class InterviewerBackend(Protocol):
    configuration: InterviewerBackendConfiguration

    def decide(
        self,
        request: InterviewerTurnRequest,
        tools: InterviewerToolProvider,
    ) -> InterviewerDecision: ...


class InterviewerCache(Protocol):
    def get(self, key: str) -> CachedInterviewerOutput | None: ...

    def put(self, key: str, output: CachedInterviewerOutput) -> None: ...


def question_bank_sha256(bank: QuestionBank) -> str:
    return content_sha256(
        [
            {
                "id": item.id,
                "text": item.text,
                "description": item.description,
                "domain": item.domain,
            }
            for item in sorted(bank.items, key=lambda item: item.id)
        ]
    )


def preference_state_sha256(state: PreferenceState) -> str:
    return content_sha256(state_to_dict(state))


def preference_evidence_sha256(evidence: Evidence) -> str:
    payload = asdict(evidence)
    payload["source"] = evidence.source.value
    return content_sha256(payload)


def vetted_question_sha256(question: VettedQuestionCandidate) -> str:
    return content_sha256(
        {
            "question_id": question.question_id,
            "question_version": question.question_version,
            "item_a": question.item_a,
            "item_b": question.item_b,
            "prompt": question.prompt,
            "options": [
                option.model_dump(mode="json") for option in question.options
            ],
            "domain": question.domain,
        }
    )


def _question_candidate(
    bank: QuestionBank,
    model: PreferenceModel,
    state: PreferenceState,
    item_a: ItemId,
    item_b: ItemId,
    question_version: int,
) -> VettedQuestionCandidate:
    question = bank.build_pairwise_question(item_a, item_b)
    options = [
        VettedQuestionOption(
            item_id=option.item_id,
            text=option.text,
            description=option.description or "",
        )
        for option in question.options
    ]
    score = model.get_uncertainty(state, item_a, item_b)
    unhashed = VettedQuestionCandidate.model_construct(
        question_sha256="0" * 64,
        question_id=question.id,
        question_version=question_version,
        item_a=item_a,
        item_b=item_b,
        prompt=question.prompt,
        options=options,
        domain=question.domain,
        score=score,
    )
    return VettedQuestionCandidate(
        question_sha256=vetted_question_sha256(unhashed),
        question_id=question.id,
        question_version=question_version,
        item_a=item_a,
        item_b=item_b,
        prompt=question.prompt,
        options=options,
        domain=question.domain,
        score=score,
    )


class PreferenceInterviewerTools:
    """Read-only typed views over one exact preference-state cutoff.

    Generated vetted questions inherit the verified question-bank version;
    Phase 4B does not maintain independent per-question version counters.
    """

    def __init__(
        self,
        state: PreferenceState,
        model: PreferenceModel,
        bank: QuestionBank,
        evidence_references: list[EvidenceAuditReference],
        question_version: int,
    ) -> None:
        if question_version < 1:
            raise ValueError("question version must be positive")
        self._state = state
        self._model = model
        self._bank = bank
        self._evidence_references = list(evidence_references)
        self._question_version = question_version

    def _require_bank_pair(self, pair: PairReference) -> None:
        item_ids = set(self._bank.item_ids())
        if pair.item_a not in item_ids or pair.item_b not in item_ids:
            raise ValueError("uncertainty request pair must come from the vetted bank")

    def read_posterior_uncertainty(
        self, request: ReadPosteriorUncertaintyRequest
    ) -> ReadPosteriorUncertaintyResult:
        self._require_bank_pair(request.pair)
        return ReadPosteriorUncertaintyResult(
            pair=request.pair,
            posterior_gap_std=self._model.get_uncertainty(
                self._state,
                request.pair.item_a,
                request.pair.item_b,
            ),
            model_version=self._state.model_version,
        )

    def read_candidate_question_scores(
        self, request: ReadCandidateQuestionScoresRequest
    ) -> ReadCandidateQuestionScoresResult:
        excluded_pairs = {
            frozenset((evidence.item_a, evidence.item_b))
            for evidence in self._state.evidence
        }
        excluded_question_ids = set(request.excluded_question_ids)
        item_ids = sorted(self._bank.item_ids())
        candidates = [
            _question_candidate(
                self._bank,
                self._model,
                self._state,
                item_ids[i],
                item_ids[j],
                self._question_version,
            )
            for i in range(len(item_ids))
            for j in range(i + 1, len(item_ids))
            if frozenset((item_ids[i], item_ids[j])) not in excluded_pairs
        ]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.question_id not in excluded_question_ids
        ]
        candidates.sort(key=lambda item: (-item.score, item.question_id))
        return ReadCandidateQuestionScoresResult(
            candidates=candidates[: request.limit],
            model_version=self._state.model_version,
        )

    def read_evidence_coverage(
        self, request: ReadEvidenceCoverageRequest
    ) -> ReadEvidenceCoverageResult:
        del request
        observed_items = {
            item_id
            for ref in self._evidence_references
            for item_id in (ref.item_a, ref.item_b)
        }
        observed_pairs = {
            frozenset((ref.item_a, ref.item_b))
            for ref in self._evidence_references
        }
        domains: list[DomainEvidenceCoverage] = []
        for domain in self._bank.domains():
            domain_items = {
                item.id for item in self._bank.items if item.domain == domain
            }
            domains.append(
                DomainEvidenceCoverage(
                    domain=domain,
                    item_count=len(domain_items),
                    observed_item_count=len(domain_items & observed_items),
                    touching_evidence_count=sum(
                        1
                        for ref in self._evidence_references
                        if ref.item_a in domain_items or ref.item_b in domain_items
                    ),
                )
            )
        item_count = len(self._bank.item_ids())
        return ReadEvidenceCoverageResult(
            evidence_count=len(self._evidence_references),
            item_count=item_count,
            observed_item_count=len(observed_items),
            possible_pair_count=item_count * (item_count - 1) // 2,
            observed_pair_count=len(observed_pairs),
            domains=domains,
        )

    def read_evidence_conflicts(
        self, request: ReadEvidenceConflictsRequest
    ) -> ReadEvidenceConflictsResult:
        del request
        directions: dict[
            tuple[ItemId, ItemId],
            tuple[list[str], list[str]],
        ] = {}
        for ref in self._evidence_references:
            if ref.item_a < ref.item_b:
                pair = (ref.item_a, ref.item_b)
                canonical_value = ref.value
            else:
                pair = (ref.item_b, ref.item_a)
                canonical_value = -ref.value
            positive, negative = directions.setdefault(pair, ([], []))
            if canonical_value > 0:
                positive.append(ref.evidence_event_id)
            elif canonical_value < 0:
                negative.append(ref.evidence_event_id)
        conflicts = [
            EvidenceConflict(
                pair=PairReference(item_a=pair[0], item_b=pair[1]),
                positive_evidence_event_ids=positive,
                negative_evidence_event_ids=negative,
            )
            for pair, (positive, negative) in sorted(directions.items())
            if positive and negative
        ]
        return ReadEvidenceConflictsResult(conflicts=conflicts)


class RecordingInterviewerTools:
    def __init__(self, tools: InterviewerToolProvider) -> None:
        self._tools = tools
        self.records: list[InterviewerToolCallRecord] = []

    def _record(
        self,
        tool: InterviewerTool,
        request: ToolRequest,
        result: ToolResult,
    ) -> None:
        self.records.append(
            InterviewerToolCallRecord(
                call_sequence=len(self.records) + 1,
                tool=tool,
                request=request,
                request_sha256=content_sha256(request),
                result=result,
                result_sha256=content_sha256(result),
            )
        )

    def read_posterior_uncertainty(
        self, request: ReadPosteriorUncertaintyRequest
    ) -> ReadPosteriorUncertaintyResult:
        result = self._tools.read_posterior_uncertainty(request)
        self._record(
            InterviewerTool.READ_POSTERIOR_UNCERTAINTY, request, result
        )
        return result

    def read_candidate_question_scores(
        self, request: ReadCandidateQuestionScoresRequest
    ) -> ReadCandidateQuestionScoresResult:
        result = self._tools.read_candidate_question_scores(request)
        self._record(
            InterviewerTool.READ_CANDIDATE_QUESTION_SCORES, request, result
        )
        return result

    def read_evidence_coverage(
        self, request: ReadEvidenceCoverageRequest
    ) -> ReadEvidenceCoverageResult:
        result = self._tools.read_evidence_coverage(request)
        self._record(
            InterviewerTool.READ_EVIDENCE_COVERAGE, request, result
        )
        return result

    def read_evidence_conflicts(
        self, request: ReadEvidenceConflictsRequest
    ) -> ReadEvidenceConflictsResult:
        result = self._tools.read_evidence_conflicts(request)
        self._record(
            InterviewerTool.READ_EVIDENCE_CONFLICTS, request, result
        )
        return result


class InMemoryInterviewerCache:
    def __init__(self) -> None:
        self._outputs: dict[str, CachedInterviewerOutput] = {}

    def get(self, key: str) -> CachedInterviewerOutput | None:
        return self._outputs.get(key)

    def put(self, key: str, output: CachedInterviewerOutput) -> None:
        existing = self._outputs.get(key)
        if existing is not None and existing != output:
            raise ValueError("interviewer cache key already binds different output")
        self._outputs[key] = output


class JsonDirectoryInterviewerCache:
    """Content-addressed cache without raw conversation text.

    Outputs still contain participant-derived question, coverage, conflict,
    and evidence-link structure. Callers must use an ignored,
    access-controlled directory; the class cannot infer repository policy from
    an arbitrary filesystem path.
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise ValueError("interviewer cache key must be a SHA-256 digest")
        return self._directory / f"{key}.json"

    def get(self, key: str) -> CachedInterviewerOutput | None:
        path = self._path(key)
        if not path.exists():
            return None
        return CachedInterviewerOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def put(self, key: str, output: CachedInterviewerOutput) -> None:
        path = self._path(key)
        if path.exists():
            existing = CachedInterviewerOutput.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if existing != output:
                raise ValueError("interviewer cache key already binds different output")
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


class DeterministicToolUsingBackend:
    """Deterministic backend used to test the provider-neutral boundary."""

    def __init__(self, configuration: InterviewerBackendConfiguration) -> None:
        self.configuration = configuration
        self.call_count = 0

    def decide(
        self,
        request: InterviewerTurnRequest,
        tools: InterviewerToolProvider,
    ) -> InterviewerDecision:
        self.call_count += 1
        tools.read_evidence_coverage(ReadEvidenceCoverageRequest())
        conflicts = tools.read_evidence_conflicts(ReadEvidenceConflictsRequest())
        candidates = tools.read_candidate_question_scores(
            ReadCandidateQuestionScoresRequest(limit=10)
        )
        if candidates.candidates:
            first = candidates.candidates[0]
            tools.read_posterior_uncertainty(
                ReadPosteriorUncertaintyRequest(
                    pair=PairReference(item_a=first.item_a, item_b=first.item_b)
                )
            )
        if conflicts.conflicts:
            conflict = conflicts.conflicts[0]
            return ClarifyExistingEvidenceDecision(
                clarification_kind=ClarificationKind.RESOLVE_CONFLICT,
                linked_evidence_event_ids=(
                    conflict.positive_evidence_event_ids
                    + conflict.negative_evidence_event_ids
                ),
            )
        if candidates.candidates:
            return AskVettedQuestionDecision(question=candidates.candidates[0])
        return PauseAndResumeDecision()


def _validate_reference_against_evidence(
    reference: EvidenceAuditReference,
    evidence: Evidence,
) -> None:
    if (
        (
            evidence.event_id is not None
            and reference.evidence_event_id != evidence.event_id
        )
        or reference.evidence_sha256 != preference_evidence_sha256(evidence)
        or reference.item_a != evidence.item_a
        or reference.item_b != evidence.item_b
        or reference.value != evidence.value
        or reference.confidence != evidence.confidence
    ):
        raise ValueError("evidence reference does not match preference state")


def _require_aware_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")


def build_interviewer_turn_request(
    *,
    state: PreferenceState,
    bank: QuestionBank,
    backend: InterviewerBackendConfiguration,
    question_bank_id: str,
    question_bank_version: int,
    turn_index: int,
    evidence_references: list[EvidenceAuditReference],
    conversation_history: list[InterviewerMessage],
) -> InterviewerTurnRequest:
    """Bind an exact current state and private conversation to a turn input."""

    if state.session_id == "":
        raise ValueError("preference state session id cannot be empty")
    if len(evidence_references) != len(state.evidence):
        raise ValueError("evidence references must cover the current state cutoff")
    for index, (reference, evidence) in enumerate(
        zip(evidence_references, state.evidence, strict=True)
    ):
        if reference.state_evidence_index != index:
            raise ValueError("evidence reference index does not match state order")
        _validate_reference_against_evidence(reference, evidence)
    return InterviewerTurnRequest(
        session_id=state.session_id,
        turn_index=turn_index,
        question_bank_id=question_bank_id,
        question_bank_version=question_bank_version,
        question_bank_sha256=question_bank_sha256(bank),
        preference_state_sha256=preference_state_sha256(state),
        evidence_cutoff_count=len(state.evidence),
        evidence_references=evidence_references,
        conversation_history=conversation_history,
        conversation_history_sha256=content_sha256(
            [message.model_dump(mode="json") for message in conversation_history]
        ),
        backend=backend,
        allowed_actions=list(InterviewerAction),
        allowed_tools=list(InterviewerTool),
    )


def _validate_decision(
    decision: InterviewerDecision,
    request: InterviewerTurnRequest,
    tool_calls: list[InterviewerToolCallRecord],
) -> None:
    if isinstance(decision, AskVettedQuestionDecision):
        offered = {
            candidate.question_sha256: candidate
            for call in tool_calls
            if call.tool is InterviewerTool.READ_CANDIDATE_QUESTION_SCORES
            and isinstance(call.result, ReadCandidateQuestionScoresResult)
            for candidate in call.result.candidates
        }
        if offered.get(decision.question.question_sha256) != decision.question:
            raise ValueError(
                "asked question must be an exact candidate returned by a tool"
            )
    elif isinstance(decision, ClarifyExistingEvidenceDecision):
        eligible_ids = {
            reference.evidence_event_id for reference in request.evidence_references
        }
        if not set(decision.linked_evidence_event_ids) <= eligible_ids:
            raise ValueError("clarification links unknown or later evidence")


def _execute_tool_call(
    tools: InterviewerToolProvider,
    call: InterviewerToolCallRecord,
) -> ToolResult:
    request = call.request
    if call.tool is InterviewerTool.READ_POSTERIOR_UNCERTAINTY:
        if not isinstance(request, ReadPosteriorUncertaintyRequest):
            raise ValueError("uncertainty tool call has the wrong request type")
        return tools.read_posterior_uncertainty(request)
    if call.tool is InterviewerTool.READ_CANDIDATE_QUESTION_SCORES:
        if not isinstance(request, ReadCandidateQuestionScoresRequest):
            raise ValueError("candidate-score tool call has the wrong request type")
        return tools.read_candidate_question_scores(request)
    if call.tool is InterviewerTool.READ_EVIDENCE_COVERAGE:
        if not isinstance(request, ReadEvidenceCoverageRequest):
            raise ValueError("coverage tool call has the wrong request type")
        return tools.read_evidence_coverage(request)
    if call.tool is InterviewerTool.READ_EVIDENCE_CONFLICTS:
        if not isinstance(request, ReadEvidenceConflictsRequest):
            raise ValueError("conflict tool call has the wrong request type")
        return tools.read_evidence_conflicts(request)
    raise ValueError("cached tool call names an unsupported tool")


def _validate_cached_tool_calls(
    tools: InterviewerToolProvider,
    tool_calls: list[InterviewerToolCallRecord],
) -> None:
    """Re-derive pure tool results before trusting a cached provider output."""

    for call in tool_calls:
        live_result = _execute_tool_call(tools, call)
        if (
            live_result != call.result
            or content_sha256(live_result) != call.result_sha256
        ):
            raise ValueError(
                "cached tool result does not match current tool implementation"
            )


class InterviewerOrchestrator:
    """Runs, validates, caches, and audits one constrained interviewer turn."""

    def __init__(
        self,
        *,
        state_model: PreferenceModel,
        bank: QuestionBank,
        question_bank_id: str,
        question_bank_version: int,
        backend: InterviewerBackend,
        cache: InterviewerCache,
    ) -> None:
        if not question_bank_id:
            raise ValueError("question bank id cannot be empty")
        if question_bank_version < 1:
            raise ValueError("question bank version must be positive")
        self._state_model = state_model
        self._bank = bank
        self._question_bank_id = question_bank_id
        self._question_bank_version = question_bank_version
        self._backend = backend
        self._cache = cache

    def run_turn(
        self,
        *,
        state: PreferenceState,
        request: InterviewerTurnRequest,
        created_at: datetime,
    ) -> InterviewerTurnRecord:
        _require_aware_datetime(created_at)
        if request.backend != self._backend.configuration:
            raise ValueError("turn request backend does not match orchestrator")
        if request.session_id != state.session_id:
            raise ValueError("turn request session does not match preference state")
        if request.question_bank_id != self._question_bank_id:
            raise ValueError("turn request question-bank id does not match")
        if request.question_bank_version != self._question_bank_version:
            raise ValueError("turn request question-bank version does not match")
        if request.preference_state_sha256 != preference_state_sha256(state):
            raise ValueError("turn request preference-state hash does not match")
        if request.question_bank_sha256 != question_bank_sha256(self._bank):
            raise ValueError("turn request question-bank hash does not match")
        if request.evidence_cutoff_count != len(state.evidence):
            raise ValueError("turn request evidence cutoff does not match state")
        for reference, evidence in zip(
            request.evidence_references, state.evidence, strict=True
        ):
            _validate_reference_against_evidence(reference, evidence)

        request_hash = content_sha256(request)
        backend_hash = content_sha256(request.backend)
        cached = self._cache.get(request_hash)
        cache_hit = cached is not None
        tools = PreferenceInterviewerTools(
            state,
            self._state_model,
            self._bank,
            request.evidence_references,
            request.question_bank_version,
        )
        if cached is None:
            recording_tools = RecordingInterviewerTools(tools)
            decision = _DECISION_ADAPTER.validate_python(
                self._backend.decide(request.model_copy(deep=True), recording_tools)
            )
            output = CachedInterviewerOutput(
                request_sha256=request_hash,
                backend_configuration_sha256=backend_hash,
                decision=decision,
                tool_calls=recording_tools.records,
            )
            _validate_decision(decision, request, output.tool_calls)
            self._cache.put(request_hash, output)
        else:
            output = cached
            if output.request_sha256 != request_hash:
                raise ValueError("cached output request hash does not match key")
            if output.backend_configuration_sha256 != backend_hash:
                raise ValueError("cached output backend hash does not match request")
            _validate_cached_tool_calls(tools, output.tool_calls)
            _validate_decision(output.decision, request, output.tool_calls)

        return InterviewerTurnRecord(
            session_id=request.session_id,
            turn_index=request.turn_index,
            request_sha256=request_hash,
            conversation_history_sha256=request.conversation_history_sha256,
            question_bank_sha256=request.question_bank_sha256,
            preference_state_sha256=request.preference_state_sha256,
            evidence_cutoff_count=request.evidence_cutoff_count,
            evidence_event_ids=[
                reference.evidence_event_id
                for reference in request.evidence_references
            ],
            backend=request.backend,
            backend_configuration_sha256=backend_hash,
            decision=output.decision,
            tool_calls=output.tool_calls,
            output_sha256=content_sha256(output),
            cache_hit=cache_hit,
            created_at=created_at,
        )
