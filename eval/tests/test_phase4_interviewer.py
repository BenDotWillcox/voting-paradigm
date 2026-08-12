"""Tests for the provider-neutral Phase 4B interviewer boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eval.fixture_io import content_sha256
from eval.phase4_interviewer import (
    AskVettedQuestionDecision,
    ClarificationKind,
    ClarifyExistingEvidenceDecision,
    DeterministicToolUsingBackend,
    EvidenceAuditReference,
    InMemoryInterviewerCache,
    InterviewerBackendConfiguration,
    InterviewerMessage,
    InterviewerOrchestrator,
    JsonDirectoryInterviewerCache,
    PairReference,
    PreferenceInterviewerTools,
    ReadCandidateQuestionScoresRequest,
    ReadEvidenceConflictsRequest,
    ReadEvidenceCoverageRequest,
    ReadPosteriorUncertaintyRequest,
    VettedQuestionCandidate,
    build_interviewer_turn_request,
    preference_state_sha256,
    preference_evidence_sha256,
    question_bank_sha256,
    vetted_question_sha256,
)
from eval.phase4_protocol import InterviewerAction, InterviewerTool
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.questions.bank import Item, QuestionBank
from preferences.types import Evidence, EvidenceSource, PreferenceState

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def small_bank(*, reverse: bool = False) -> QuestionBank:
    items = [
        Item(id="a", text="Alpha", description="Alpha detail", domain="one"),
        Item(id="b", text="Beta", description="Beta detail", domain="one"),
        Item(id="c", text="Gamma", description="Gamma detail", domain="two"),
        Item(id="d", text="Delta", description="Delta detail", domain="two"),
    ]
    return QuestionBank(items=list(reversed(items)) if reverse else items)


def backend_configuration(*, seed: int = 7) -> InterviewerBackendConfiguration:
    return InterviewerBackendConfiguration(
        backend_id="deterministic_test_double",
        backend_version=1,
        model_id="deterministic_tool_policy",
        model_version="1.0.0",
        prompt_id="phase4_interviewer_test",
        prompt_version=1,
        prompt_sha256=content_sha256("deterministic test prompt"),
        seed=seed,
    )


def initial_state() -> tuple[GaussianLinearUtilityModel, PreferenceState]:
    model = GaussianLinearUtilityModel()
    return model, model.initialize(
        "participant", "session_one", small_bank().item_ids()
    )


def evidence(
    item_a: str,
    item_b: str,
    value: float,
    *,
    prompt_id: str,
) -> Evidence:
    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=item_a,
        item_b=item_b,
        value=value,
        prompt_id=prompt_id,
    )


def evidence_references(state: PreferenceState) -> list[EvidenceAuditReference]:
    return [
        EvidenceAuditReference(
            evidence_event_id=f"evidence_{index + 1}",
            state_evidence_index=index,
            evidence_sha256=preference_evidence_sha256(item),
            item_a=item.item_a,
            item_b=item.item_b,
            value=item.value,
            confidence=item.confidence,
        )
        for index, item in enumerate(state.evidence)
    ]


def messages(content: str = "I care about the tradeoff.") -> list[InterviewerMessage]:
    return [
        InterviewerMessage(
            message_id="message_1",
            sequence=1,
            role="participant",
            content=content,
        )
    ]


def request_for(
    state: PreferenceState,
    config: InterviewerBackendConfiguration,
    *,
    history: list[InterviewerMessage] | None = None,
):
    return build_interviewer_turn_request(
        state=state,
        bank=small_bank(),
        backend=config,
        question_bank_id="phase4_test_bank",
        question_bank_version=1,
        turn_index=1,
        evidence_references=evidence_references(state),
        conversation_history=history or messages(),
    )


class TestFixedInputBindings:
    def test_request_binds_complete_phase4a_surface(self):
        _, state = initial_state()
        request = request_for(state, backend_configuration())

        assert set(request.allowed_actions) == set(InterviewerAction)
        assert set(request.allowed_tools) == set(InterviewerTool)
        assert request.target_packet_visible is False
        assert request.tool_surface_version == 1
        assert request.tool_implementation_version == 1
        assert request.preference_state_sha256 == preference_state_sha256(state)
        assert request.question_bank_sha256 == question_bank_sha256(small_bank())

    def test_bank_hash_is_independent_of_input_item_order(self):
        assert question_bank_sha256(small_bank()) == question_bank_sha256(
            small_bank(reverse=True)
        )

    def test_private_input_or_seed_change_changes_request_hash(self):
        _, state = initial_state()
        first = request_for(state, backend_configuration(seed=1))
        different_text = request_for(
            state,
            backend_configuration(seed=1),
            history=messages("A different exact private input."),
        )
        different_seed = request_for(state, backend_configuration(seed=2))

        assert content_sha256(first) != content_sha256(different_text)
        assert content_sha256(first) != content_sha256(different_seed)

    def test_rejects_reference_that_does_not_match_state(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 6.0, prompt_id="q1"))
        references = evidence_references(state)
        references[0].value = -6.0

        with pytest.raises(ValueError, match="does not match preference state"):
            build_interviewer_turn_request(
                state=state,
                bank=small_bank(),
                backend=backend_configuration(),
                question_bank_id="phase4_test_bank",
                question_bank_version=1,
                turn_index=2,
                evidence_references=references,
                conversation_history=messages(),
            )

    def test_rejects_incomplete_evidence_cutoff(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 6.0, prompt_id="q1"))

        with pytest.raises(ValueError, match="current state cutoff"):
            build_interviewer_turn_request(
                state=state,
                bank=small_bank(),
                backend=backend_configuration(),
                question_bank_id="phase4_test_bank",
                question_bank_version=1,
                turn_index=2,
                evidence_references=[],
                conversation_history=messages(),
            )

    def test_rejects_naive_audit_timestamp(self):
        model, state = initial_state()
        config = backend_configuration()
        orchestrator = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=(backend := DeterministicToolUsingBackend(config)),
            cache=InMemoryInterviewerCache(),
        )
        with pytest.raises(ValueError, match="timezone-aware"):
            orchestrator.run_turn(
                state=state,
                request=request_for(state, config),
                created_at=datetime(2026, 8, 12, 12, 0),
            )
        assert backend.call_count == 0


class TestReadOnlyTools:
    def test_candidate_scores_are_deterministic_and_exclude_seen_pair(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 7.0, prompt_id="q1"))
        tools = PreferenceInterviewerTools(
            state, model, small_bank(), evidence_references(state)
        )

        first = tools.read_candidate_question_scores(
            ReadCandidateQuestionScoresRequest(limit=10)
        )
        second = tools.read_candidate_question_scores(
            ReadCandidateQuestionScoresRequest(limit=10)
        )

        assert first == second
        assert all(
            {candidate.item_a, candidate.item_b} != {"a", "b"}
            for candidate in first.candidates
        )
        assert first.candidates == sorted(
            first.candidates,
            key=lambda item: (-item.score, item.question_id),
        )

    def test_all_tools_leave_preference_state_unchanged(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 7.0, prompt_id="q1"))
        references = evidence_references(state)
        tools = PreferenceInterviewerTools(state, model, small_bank(), references)
        before = preference_state_sha256(state)

        candidates = tools.read_candidate_question_scores(
            ReadCandidateQuestionScoresRequest(limit=2)
        )
        tools.read_posterior_uncertainty(
            ReadPosteriorUncertaintyRequest(
                pair=PairReference(
                    item_a=candidates.candidates[0].item_a,
                    item_b=candidates.candidates[0].item_b,
                )
            )
        )
        tools.read_evidence_coverage(ReadEvidenceCoverageRequest())
        tools.read_evidence_conflicts(ReadEvidenceConflictsRequest())

        assert preference_state_sha256(state) == before

    def test_uncertainty_rejects_pair_outside_vetted_bank(self):
        model, state = initial_state()
        tools = PreferenceInterviewerTools(state, model, small_bank(), [])
        with pytest.raises(ValueError, match="vetted bank"):
            tools.read_posterior_uncertainty(
                ReadPosteriorUncertaintyRequest(
                    pair=PairReference(item_a="a", item_b="outside")
                )
            )

    def test_coverage_reports_items_pairs_and_domains(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "c", 5.0, prompt_id="q1"))
        tools = PreferenceInterviewerTools(
            state, model, small_bank(), evidence_references(state)
        )
        result = tools.read_evidence_coverage(ReadEvidenceCoverageRequest())

        assert result.evidence_count == 1
        assert result.item_count == 4
        assert result.observed_item_count == 2
        assert result.possible_pair_count == 6
        assert result.observed_pair_count == 1
        assert [domain.domain for domain in result.domains] == ["one", "two"]

    def test_conflict_detection_normalizes_pair_direction(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 7.0, prompt_id="q1"))
        state = model.update(state, evidence("b", "a", 4.0, prompt_id="q2"))
        tools = PreferenceInterviewerTools(
            state, model, small_bank(), evidence_references(state)
        )
        result = tools.read_evidence_conflicts(ReadEvidenceConflictsRequest())

        assert len(result.conflicts) == 1
        assert result.conflicts[0].pair == PairReference(item_a="a", item_b="b")
        assert result.conflicts[0].positive_evidence_event_ids == ["evidence_1"]
        assert result.conflicts[0].negative_evidence_event_ids == ["evidence_2"]


class TestOrchestrator:
    def test_records_versions_seed_cutoff_question_and_every_tool_result(self):
        model, state = initial_state()
        config = backend_configuration(seed=19)
        backend = DeterministicToolUsingBackend(config)
        record = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=backend,
            cache=InMemoryInterviewerCache(),
        ).run_turn(
            state=state,
            request=request_for(state, config),
            created_at=NOW,
        )

        assert isinstance(record.decision, AskVettedQuestionDecision)
        assert record.decision.question.question_version == 1
        assert record.backend.seed == 19
        assert record.evidence_cutoff_count == 0
        assert record.evidence_event_ids == []
        assert [call.tool for call in record.tool_calls] == [
            InterviewerTool.READ_EVIDENCE_COVERAGE,
            InterviewerTool.READ_EVIDENCE_CONFLICTS,
            InterviewerTool.READ_CANDIDATE_QUESTION_SCORES,
            InterviewerTool.READ_POSTERIOR_UNCERTAINTY,
        ]
        assert all(
            call.result.record_version.endswith(".v1")
            for call in record.tool_calls
        )
        assert backend.call_count == 1

    def test_cache_hit_does_not_call_backend_again(self):
        model, state = initial_state()
        config = backend_configuration()
        backend = DeterministicToolUsingBackend(config)
        cache = InMemoryInterviewerCache()
        orchestrator = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=backend,
            cache=cache,
        )
        request = request_for(state, config)

        first = orchestrator.run_turn(state=state, request=request, created_at=NOW)
        second = orchestrator.run_turn(state=state, request=request, created_at=NOW)

        assert first.cache_hit is False
        assert second.cache_hit is True
        assert first.output_sha256 == second.output_sha256
        assert first.decision == second.decision
        assert backend.call_count == 1

    def test_conflicting_evidence_produces_linked_clarification(self):
        model, state = initial_state()
        state = model.update(state, evidence("a", "b", 7.0, prompt_id="q1"))
        state = model.update(state, evidence("a", "b", -6.0, prompt_id="q2"))
        config = backend_configuration()
        record = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=DeterministicToolUsingBackend(config),
            cache=InMemoryInterviewerCache(),
        ).run_turn(
            state=state,
            request=request_for(state, config),
            created_at=NOW,
        )

        assert isinstance(record.decision, ClarifyExistingEvidenceDecision)
        assert record.decision.clarification_kind is ClarificationKind.RESOLVE_CONFLICT
        assert record.decision.linked_evidence_event_ids == [
            "evidence_1",
            "evidence_2",
        ]

    def test_rejects_clarification_link_to_unknown_evidence(self):
        class BadClarificationBackend:
            configuration = backend_configuration()

            def decide(self, request, tools):
                del request, tools
                return ClarifyExistingEvidenceDecision(
                    clarification_kind=ClarificationKind.CONFIRM_SCOPE,
                    linked_evidence_event_ids=["invented_evidence"],
                )

        model, state = initial_state()
        backend = BadClarificationBackend()
        with pytest.raises(ValueError, match="unknown or later evidence"):
            InterviewerOrchestrator(
                state_model=model,
                bank=small_bank(),
                backend=backend,
                cache=InMemoryInterviewerCache(),
            ).run_turn(
                state=state,
                request=request_for(state, backend.configuration),
                created_at=NOW,
            )

    def test_rejects_question_not_returned_by_candidate_tool(self):
        class UnvettedQuestionBackend:
            configuration = backend_configuration()

            def decide(self, request, tools):
                del request
                result = tools.read_candidate_question_scores(
                    ReadCandidateQuestionScoresRequest(limit=1)
                )
                original = result.candidates[0]
                unhashed = original.model_copy(
                    update={
                        "question_id": "invented",
                        "question_sha256": "0" * 64,
                    }
                )
                changed = original.model_copy(
                    update={
                        "question_id": "invented",
                        "question_sha256": vetted_question_sha256(unhashed),
                    }
                )
                return AskVettedQuestionDecision(question=changed)

        model, state = initial_state()
        backend = UnvettedQuestionBackend()
        with pytest.raises(ValueError, match="exact candidate"):
            InterviewerOrchestrator(
                state_model=model,
                bank=small_bank(),
                backend=backend,
                cache=InMemoryInterviewerCache(),
            ).run_turn(
                state=state,
                request=request_for(state, backend.configuration),
                created_at=NOW,
            )

    def test_rejects_state_changed_after_request_was_built(self):
        model, state = initial_state()
        config = backend_configuration()
        request = request_for(state, config)
        changed_state = model.update(
            state, evidence("a", "b", 5.0, prompt_id="q1")
        )

        with pytest.raises(ValueError, match="preference-state hash"):
            InterviewerOrchestrator(
                state_model=model,
                bank=small_bank(),
                backend=DeterministicToolUsingBackend(config),
                cache=InMemoryInterviewerCache(),
            ).run_turn(state=changed_state, request=request, created_at=NOW)


class TestPersistentCache:
    def test_cache_persists_output_without_raw_private_text(self, tmp_path):
        planted = "PLANTED_PRIVATE_CONVERSATION_DO_NOT_PERSIST"
        model, state = initial_state()
        config = backend_configuration()
        request = request_for(state, config, history=messages(planted))
        first_backend = DeterministicToolUsingBackend(config)
        cache_path = tmp_path / "interviewer_cache"

        first = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=first_backend,
            cache=JsonDirectoryInterviewerCache(cache_path),
        ).run_turn(state=state, request=request, created_at=NOW)
        cache_text = next(cache_path.glob("*.json")).read_text(encoding="utf-8")

        second_backend = DeterministicToolUsingBackend(config)
        second = InterviewerOrchestrator(
            state_model=model,
            bank=small_bank(),
            backend=second_backend,
            cache=JsonDirectoryInterviewerCache(cache_path),
        ).run_turn(state=state, request=request, created_at=NOW)

        assert planted not in cache_text
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert first.output_sha256 == second.output_sha256
        assert first_backend.call_count == 1
        assert second_backend.call_count == 0
