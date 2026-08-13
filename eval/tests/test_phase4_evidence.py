"""Tests for confirmed fixed-ontology conversational evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_evidence import (
    ConversationEvidenceMessage,
    ConversationalEvidenceProposal,
    DeterministicEvidenceExtractor,
    EvidenceCorrectionEvent,
    EvidenceDecisionKind,
    EvidenceExtractionRequest,
    EvidenceExtractorConfiguration,
    EvidenceProposalDraft,
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    FixedOntologyReference,
    ParticipantEvidenceDecision,
    StructuredPreferenceEvidenceEvent,
    UnsupportedAssumptionFlag,
    build_extraction_request,
    materialize_all_evidence_conditions,
    materialize_evidence,
    replay_preference_state,
    run_evidence_extractor,
)
from eval.phase4_protocol import EvidenceCondition
from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.serialization import state_from_dict, state_to_dict
from preferences.types import Evidence, EvidenceSource, PreferenceState

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def at(sequence: int) -> datetime:
    return NOW + timedelta(minutes=sequence)


def ontology() -> FixedOntologyReference:
    item_ids = ["a", "b", "c", "d"]
    return FixedOntologyReference(
        ontology_id="fixed_civic_values",
        ontology_version=1,
        item_ids=item_ids,
        item_ids_sha256=content_sha256(item_ids),
    )


def configuration() -> EvidenceExtractorConfiguration:
    return EvidenceExtractorConfiguration(
        configuration_id="extractor_test",
        backend_id="deterministic_test_double",
        backend_version=1,
        model_id="scripted_extractor",
        model_version="1.0.0",
        prompt_id="phase4_extractor_test",
        prompt_version=1,
        prompt_sha256=content_sha256("extract pairwise preference claims"),
        implementation_version=1,
        seed=17,
    )


def claim(
    text: str = "I favor A over B.",
    *,
    item_a: str = "a",
    item_b: str = "b",
    value: float = 6.0,
) -> FixedOntologyClaim:
    return FixedOntologyClaim(
        claim_text=text,
        item_a=item_a,
        item_b=item_b,
        value=value,
    )


def messages() -> list[ConversationEvidenceMessage]:
    return [
        ConversationEvidenceMessage(
            message_id="message_participant",
            session_id="session_one",
            sequence=1,
            role="participant",
            content="I favor A over B, though not overwhelmingly.",
            created_at=at(1),
        ),
        ConversationEvidenceMessage(
            message_id="message_interviewer",
            session_id="session_one",
            sequence=2,
            role="interviewer",
            content="I will ask you to confirm each inferred claim.",
            created_at=at(2),
        ),
        ConversationEvidenceMessage(
            message_id="message_correction",
            session_id="session_one",
            sequence=9,
            role="participant",
            content="Actually, my preference is weaker than I first said.",
            created_at=at(9),
        ),
    ]


def request() -> EvidenceExtractionRequest:
    return build_extraction_request(
        request_id="extraction_one",
        session_id="session_one",
        sequence=3,
        created_at=at(3),
        ontology=ontology(),
        configuration=configuration(),
        messages=messages(),
        message_cutoff_sequence=2,
    )


def drafts() -> list[EvidenceProposalDraft]:
    return [
        EvidenceProposalDraft(
            source_message_ids=["message_participant"],
            claim=claim(),
            extractor_confidence=0.62,
            unsupported_assumptions=[
                UnsupportedAssumptionFlag(
                    flag_id="scope_assumption",
                    description="The statement may not apply in every domain.",
                )
            ],
        ),
        EvidenceProposalDraft(
            source_message_ids=["message_participant"],
            claim=claim(
                "I slightly favor C over D.",
                item_a="c",
                item_b="d",
                value=2.0,
            ),
            extractor_confidence=0.55,
        ),
    ]


def proposals() -> list[ConversationalEvidenceProposal]:
    backend = DeterministicEvidenceExtractor(configuration(), drafts())
    return run_evidence_extractor(
        request=request(),
        messages=messages(),
        backend=backend,
        proposal_ids=["proposal_one", "proposal_two"],
        proposal_sequences=[4, 5],
        created_at=at(5),
    )


def accepted_decision() -> ParticipantEvidenceDecision:
    return ParticipantEvidenceDecision(
        decision_id="decision_accept",
        session_id="session_one",
        sequence=7,
        created_at=at(7),
        proposal_id="proposal_one",
        decision=EvidenceDecisionKind.ACCEPT,
        evidence_event_id="evidence_conversation_one",
        acknowledged_assumption_flag_ids=["scope_assumption"],
    )


def rejected_decision() -> ParticipantEvidenceDecision:
    return ParticipantEvidenceDecision(
        decision_id="decision_reject",
        session_id="session_one",
        sequence=8,
        created_at=at(8),
        proposal_id="proposal_two",
        decision=EvidenceDecisionKind.REJECT,
    )


def structured_event() -> StructuredPreferenceEvidenceEvent:
    return StructuredPreferenceEvidenceEvent(
        evidence_event_id="evidence_structured_one",
        session_id="session_one",
        sequence=6,
        created_at=at(6),
        source=EvidenceSource.PAIRWISE,
        claim=claim(
            "I strongly favor A over C.",
            item_a="a",
            item_b="c",
            value=8.0,
        ),
        question_id="question_a_c",
        response_id="response_a_c",
    )


def correction() -> EvidenceCorrectionEvent:
    return EvidenceCorrectionEvent(
        correction_id="correction_one",
        evidence_event_id="evidence_conversation_two",
        supersedes_evidence_event_id="evidence_conversation_one",
        session_id="session_one",
        sequence=10,
        created_at=at(10),
        corrected_claim=claim(
            "I only slightly favor A over B.",
            value=2.0,
        ),
        origin="conversation",
        source_message_ids=["message_correction"],
    )


def structured_correction() -> EvidenceCorrectionEvent:
    return EvidenceCorrectionEvent(
        correction_id="correction_structured",
        evidence_event_id="evidence_structured_two",
        supersedes_evidence_event_id="evidence_structured_one",
        session_id="session_one",
        sequence=10,
        created_at=at(10),
        corrected_claim=claim(
            "I moderately favor A over C.",
            item_a="a",
            item_b="c",
            value=5.0,
        ),
        origin="structured",
        question_id="question_a_c_correction",
        response_id="response_a_c_correction",
    )


def ledger(
    *,
    decisions: list[ParticipantEvidenceDecision] | None = None,
    corrections: list[EvidenceCorrectionEvent] | None = None,
    proposals_override: list[ConversationalEvidenceProposal] | None = None,
) -> FixedOntologyEvidenceLedger:
    return FixedOntologyEvidenceLedger(
        ledger_id="ledger_one",
        session_id="session_one",
        ontology=ontology(),
        extractor_configurations=[configuration()],
        messages=messages(),
        extraction_requests=[request()],
        proposals=proposals() if proposals_override is None else proposals_override,
        decisions=(
            [accepted_decision(), rejected_decision()]
            if decisions is None
            else decisions
        ),
        structured_evidence=[structured_event()],
        corrections=[correction()] if corrections is None else corrections,
        created_at=NOW,
    )


class TestProposalBoundary:
    def test_request_binds_exact_conversation_prefix(self):
        built = request()

        assert built.input_message_ids == [
            "message_participant",
            "message_interviewer",
        ]
        assert built.input_messages_sha256 == content_sha256(
            [
                message.model_dump(mode="json")
                for message in messages()[:2]
            ]
        )
        assert built.target_packet_visible is False

    def test_deterministic_extractor_is_provider_neutral_test_double(self):
        backend = DeterministicEvidenceExtractor(configuration(), drafts())

        output = run_evidence_extractor(
            request=request(),
            messages=messages(),
            backend=backend,
            proposal_ids=["proposal_one", "proposal_two"],
            proposal_sequences=[4, 5],
            created_at=at(5),
        )

        assert backend.call_count == 1
        assert [proposal.claim for proposal in output] == [
            draft.claim for draft in drafts()
        ]
        assert all(proposal.provisional_model_weight == 0.0 for proposal in output)

    def test_raw_message_content_is_not_duplicated_into_proposal(self):
        proposal_json = proposals()[0].model_dump_json()

        assert messages()[0].content not in proposal_json

    def test_extractor_rejects_tampered_message_binding(self):
        altered = messages()
        altered[0] = altered[0].model_copy(
            update={"content": "Different private participant text."}
        )
        backend = DeterministicEvidenceExtractor(configuration(), drafts())

        with pytest.raises(ValueError, match="message hash does not match"):
            run_evidence_extractor(
                request=request(),
                messages=altered,
                backend=backend,
                proposal_ids=["proposal_one", "proposal_two"],
                proposal_sequences=[4, 5],
                created_at=at(5),
            )

    def test_extractor_rejects_interviewer_message_as_claim_source(self):
        bad_draft = drafts()[0].model_copy(
            update={"source_message_ids": ["message_interviewer"]}
        )
        backend = DeterministicEvidenceExtractor(configuration(), [bad_draft])

        with pytest.raises(ValueError, match="participant messages"):
            run_evidence_extractor(
                request=request(),
                messages=messages(),
                backend=backend,
                proposal_ids=["proposal_one"],
                proposal_sequences=[4],
                created_at=at(4),
            )

    def test_extractor_rejects_claim_outside_fixed_ontology(self):
        bad_draft = drafts()[0].model_copy(
            update={"claim": claim(item_a="a", item_b="outside")}
        )
        backend = DeterministicEvidenceExtractor(configuration(), [bad_draft])

        with pytest.raises(ValueError, match="outside the fixed ontology"):
            run_evidence_extractor(
                request=request(),
                messages=messages(),
                backend=backend,
                proposal_ids=["proposal_one"],
                proposal_sequences=[4],
                created_at=at(4),
            )

    def test_extractor_output_is_revalidated_at_provider_boundary(self):
        class InvalidBackend:
            configuration = configuration()

            def extract(self, request, input_messages):
                return [
                    {
                        "source_message_ids": ["message_participant"],
                        "claim": claim().model_dump(mode="json"),
                        "extractor_confidence": 0.0,
                    }
                ]

        with pytest.raises(ValidationError, match="extractor_confidence"):
            run_evidence_extractor(
                request=request(),
                messages=messages(),
                backend=InvalidBackend(),
                proposal_ids=["proposal_one"],
                proposal_sequences=[4],
                created_at=at(4),
            )

    def test_provisional_weight_cannot_be_raised(self):
        payload = proposals()[0].model_dump(mode="json")
        payload["provisional_model_weight"] = 0.1

        with pytest.raises(ValidationError, match="provisional_model_weight"):
            ConversationalEvidenceProposal.model_validate(payload)


class TestParticipantDecisionBoundary:
    def test_each_claim_has_an_independent_decision(self):
        built = ledger(corrections=[])

        assert [decision.proposal_id for decision in built.decisions] == [
            "proposal_one",
            "proposal_two",
        ]
        assert [decision.decision for decision in built.decisions] == [
            EvidenceDecisionKind.ACCEPT,
            EvidenceDecisionKind.REJECT,
        ]

    def test_pending_proposal_never_materializes(self):
        built = ledger(decisions=[], corrections=[])

        assert [item.event_id for item in materialize_evidence(
            built,
            condition=EvidenceCondition.COMBINED,
            cutoff_sequence=10,
        )] == ["evidence_structured_one"]

    def test_rejected_proposal_never_materializes(self):
        events = materialize_evidence(
            ledger(corrections=[]),
            condition=EvidenceCondition.COMBINED,
            cutoff_sequence=8,
        )

        assert [event.event_id for event in events] == [
            "evidence_structured_one",
            "evidence_conversation_one",
        ]

    def test_confirmation_controls_eligibility_not_extractor_weight(self):
        events = materialize_evidence(
            ledger(corrections=[]),
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=8,
        )

        assert len(events) == 1
        assert events[0].confirmed_by_participant is True
        assert events[0].confidence == 1.0
        assert events[0].metadata["extractor_confidence"] == 0.62
        assert events[0].metadata["unsupported_assumptions"][0][
            "flag_id"
        ] == "scope_assumption"
        assert events[0].raw_response is None

    def test_unsupported_assumptions_must_be_explicitly_acknowledged(self):
        unacknowledged = accepted_decision().model_copy(
            update={"acknowledged_assumption_flag_ids": []}
        )

        with pytest.raises(ValidationError, match="acknowledge every"):
            ledger(
                decisions=[unacknowledged, rejected_decision()],
                corrections=[],
            )

    def test_confirmed_conversation_evidence_updates_existing_model(self):
        evidence = materialize_evidence(
            ledger(corrections=[]),
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=8,
        )[0]
        model = GaussianLinearUtilityModel()
        state = model.initialize(
            "participant", "session_one", ontology().item_ids
        )

        updated = model.update(state, evidence)

        assert updated.evidence == [evidence]
        assert updated.mu != state.mu

    def test_edit_materializes_only_the_participant_edited_claim(self):
        edit = accepted_decision().model_copy(
            update={
                "decision_id": "decision_edit",
                "decision": EvidenceDecisionKind.EDIT,
                "edited_claim": claim("I barely favor A over B.", value=1.0),
            }
        )
        built = ledger(decisions=[edit, rejected_decision()], corrections=[])

        events = materialize_evidence(
            built,
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=8,
        )

        assert events[0].value == 1.0
        assert events[0].extracted_claims == ["I barely favor A over B."]
        assert events[0].metadata["decision"] == "edit"

    def test_accept_cannot_smuggle_an_edit(self):
        with pytest.raises(ValidationError, match="cannot carry an edited claim"):
            ParticipantEvidenceDecision(
                decision_id="decision_bad_accept",
                session_id="session_one",
                sequence=7,
                created_at=at(7),
                proposal_id="proposal_one",
                decision=EvidenceDecisionKind.ACCEPT,
                evidence_event_id="evidence_bad",
                edited_claim=claim(value=1.0),
            )

    def test_proposal_cannot_receive_two_decisions(self):
        duplicate = accepted_decision().model_copy(
            update={
                "decision_id": "decision_second",
                "sequence": 8,
                "created_at": at(8),
                "evidence_event_id": "evidence_second",
            }
        )

        with pytest.raises(ValidationError, match="only one participant decision"):
            ledger(
                decisions=[accepted_decision(), duplicate],
                corrections=[],
            )


class TestAppendOnlyCorrectionsAndViews:
    def test_correction_supersedes_without_mutating_prior_cutoff(self):
        built = ledger()

        before = materialize_evidence(
            built,
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=8,
        )
        after = materialize_evidence(
            built,
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=10,
        )

        assert [(item.event_id, item.value) for item in before] == [
            ("evidence_conversation_one", 6.0)
        ]
        assert [(item.event_id, item.value) for item in after] == [
            ("evidence_conversation_two", 2.0)
        ]
        assert after[0].metadata["supersedes_evidence_event_id"] == (
            "evidence_conversation_one"
        )

    def test_posterior_replay_removes_superseded_observation(self):
        model = GaussianLinearUtilityModel()
        built = ledger()

        before = replay_preference_state(
            model=model,
            ledger=built,
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=8,
            user_id="participant",
        )
        after = replay_preference_state(
            model=model,
            ledger=built,
            condition=EvidenceCondition.CONVERSATION_ONLY,
            cutoff_sequence=10,
            user_id="participant",
        )

        assert [item.event_id for item in before.evidence] == [
            "evidence_conversation_one"
        ]
        assert [item.event_id for item in after.evidence] == [
            "evidence_conversation_two"
        ]
        assert before.mu != after.mu

    def test_correction_cannot_target_an_already_superseded_event(self):
        second = correction().model_copy(
            update={
                "correction_id": "correction_two",
                "evidence_event_id": "evidence_conversation_three",
                "sequence": 11,
                "created_at": at(11),
            }
        )

        with pytest.raises(ValidationError, match="active evidence event"):
            ledger(corrections=[correction(), second])

    def test_all_conditions_use_the_identical_cutoff(self):
        views = materialize_all_evidence_conditions(
            ledger(), cutoff_sequence=8
        )

        assert [item.event_id for item in views[EvidenceCondition.STRUCTURED_ONLY]] == [
            "evidence_structured_one"
        ]
        assert [
            item.event_id
            for item in views[EvidenceCondition.CONVERSATION_ONLY]
        ] == ["evidence_conversation_one"]
        assert [item.event_id for item in views[EvidenceCondition.COMBINED]] == [
            "evidence_structured_one",
            "evidence_conversation_one",
        ]

    def test_conversation_correction_does_not_leak_into_structured_only(self):
        cross_origin = correction().model_copy(
            update={
                "evidence_event_id": "evidence_structured_two",
                "supersedes_evidence_event_id": "evidence_structured_one",
            }
        )
        built = ledger(corrections=[cross_origin])

        views = materialize_all_evidence_conditions(built, cutoff_sequence=10)

        assert [item.event_id for item in views[EvidenceCondition.STRUCTURED_ONLY]] == [
            "evidence_structured_one"
        ]
        assert [
            item.event_id
            for item in views[EvidenceCondition.CONVERSATION_ONLY]
        ] == ["evidence_conversation_one", "evidence_structured_two"]
        assert [item.event_id for item in views[EvidenceCondition.COMBINED]] == [
            "evidence_conversation_one",
            "evidence_structured_two",
        ]

    def test_structured_reanswer_updates_structured_and_combined_views(self):
        built = ledger(corrections=[structured_correction()])

        views = materialize_all_evidence_conditions(built, cutoff_sequence=10)

        assert [item.event_id for item in views[EvidenceCondition.STRUCTURED_ONLY]] == [
            "evidence_structured_two"
        ]
        assert [
            item.event_id
            for item in views[EvidenceCondition.CONVERSATION_ONLY]
        ] == ["evidence_conversation_one"]
        assert [item.event_id for item in views[EvidenceCondition.COMBINED]] == [
            "evidence_conversation_one",
            "evidence_structured_two",
        ]

    def test_correction_provenance_shape_must_match_its_origin(self):
        payload = correction().model_dump(mode="json")
        payload["origin"] = "structured"

        with pytest.raises(ValidationError, match="conversation messages"):
            EvidenceCorrectionEvent.model_validate(payload)


def test_preference_state_round_trip_preserves_durable_evidence_event_id():
    evidence = Evidence(
        event_id="evidence_round_trip",
        source=EvidenceSource.FREE_TEXT_EXTRACTION,
        item_a="a",
        item_b="b",
        value=4.0,
    )
    state = PreferenceState(
        user_id="participant",
        session_id="session_one",
        item_ids=["a", "b"],
        mu=[0.0, 0.0],
        sigma_flat=[1.0, 0.0, 1.0],
        evidence=[evidence],
    )

    restored = state_from_dict(state_to_dict(state))

    assert restored.evidence[0].event_id == "evidence_round_trip"
