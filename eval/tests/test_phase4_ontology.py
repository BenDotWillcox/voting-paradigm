"""Tests for the participant-governed expanding-ontology lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_evidence import (
    ConversationEvidenceMessage,
    EvidenceCorrectionEvent,
    EvidenceExtractorConfiguration,
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    FixedOntologyReference,
    StructuredPreferenceEvidenceEvent,
    UnsupportedAssumptionFlag,
)
from eval.phase4_ontology import (
    DeterministicOntologyExpansionBackend,
    ExpandingDimensionStatus,
    ExpandingOntologyLedger,
    ExpandingOntologySeed,
    OntologyDimensionDefinition,
    OntologyDimensionMergeEvent,
    OntologyDimensionProposal,
    OntologyDimensionProposalDraft,
    OntologyDimensionPruneEvent,
    OntologyDimensionSupportEvent,
    OntologyExpansionPolicy,
    OntologyProposalDecision,
    OntologyProposalDecisionKind,
    active_confirmed_evidence_references,
    active_dimension_states,
    build_ontology_proposal_context,
    confirmed_evidence_references,
    dimension_semantic_sha256,
    evidence_ledger_identity_sha256,
    replay_expanding_ontology,
    run_ontology_expansion_backend,
    validate_expanding_ontology_ledger,
)
from eval.phase4_protocol import EvidenceCondition
from preferences.types import EvidenceSource

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def at(sequence: int) -> datetime:
    return NOW + timedelta(minutes=sequence)


def dimension(
    dimension_id: str,
    *,
    name: str | None = None,
    definition: str | None = None,
    interpretation: str | None = None,
) -> OntologyDimensionDefinition:
    display = name or dimension_id.replace("_", " ").title()
    return OntologyDimensionDefinition(
        dimension_id=dimension_id,
        name=display,
        definition=definition or f"Preference concerning {display}.",
        interpretation=interpretation or f"Higher values favor {display}.",
    )


def fixed_ontology() -> FixedOntologyReference:
    item_ids = ["autonomy", "collective_welfare"]
    return FixedOntologyReference(
        ontology_id="civic_values",
        ontology_version=1,
        item_ids=item_ids,
        item_ids_sha256=content_sha256(item_ids),
    )


def seed() -> ExpandingOntologySeed:
    dimensions = [
        dimension("autonomy"),
        dimension("collective_welfare"),
    ]
    return ExpandingOntologySeed(
        ontology_id="civic_values",
        seed_version=1,
        dimensions=dimensions,
        dimensions_sha256=content_sha256(
            [item.model_dump(mode="json") for item in dimensions]
        ),
    )


def policy(**updates) -> OntologyExpansionPolicy:
    values = {
        "policy_id": "expansion_policy_test",
        "policy_version": 1,
        "admission_confirmation_support_weight": 0.5,
        "evidence_lineage_support_weight": 1.0,
        "full_weight_support_score": 1.5,
        "prune_max_support_score": 0.5,
        "prune_min_idle_sequence_gap": 3,
    }
    values.update(updates)
    return OntologyExpansionPolicy(**values)


def configuration() -> EvidenceExtractorConfiguration:
    return EvidenceExtractorConfiguration(
        configuration_id="ontology_extractor_test",
        backend_id="deterministic_test_double",
        backend_version=1,
        model_id="scripted_ontology_proposer",
        model_version="1.0.0",
        prompt_id="phase4_ontology_test",
        prompt_version=1,
        prompt_sha256=content_sha256("propose missing preference dimensions"),
        implementation_version=1,
        seed=29,
    )


def messages() -> list[ConversationEvidenceMessage]:
    return [
        ConversationEvidenceMessage(
            message_id="message_one",
            session_id="session_one",
            sequence=1,
            created_at=at(1),
            role="participant",
            content="Community voice matters independently of the listed values.",
        ),
        ConversationEvidenceMessage(
            message_id="message_two",
            session_id="session_one",
            sequence=2,
            created_at=at(2),
            role="interviewer",
            content="I will ask you to confirm any proposed new dimension.",
        ),
        ConversationEvidenceMessage(
            message_id="message_three",
            session_id="session_one",
            sequence=3,
            created_at=at(3),
            role="participant",
            content="It is about voice, not merely aggregate welfare.",
        ),
    ]


def evidence_event(event_id: str, sequence: int) -> StructuredPreferenceEvidenceEvent:
    return StructuredPreferenceEvidenceEvent(
        evidence_event_id=event_id,
        session_id="session_one",
        sequence=sequence,
        created_at=at(sequence),
        source=EvidenceSource.PAIRWISE,
        claim=FixedOntologyClaim(
            claim_text=f"Confirmed preference {event_id}.",
            item_a="autonomy",
            item_b="collective_welfare",
            value=float(sequence - 3),
        ),
        question_id=f"question_{event_id}",
        response_id=f"response_{event_id}",
    )


def evidence_ledger(
    *,
    corrections: list[EvidenceCorrectionEvent] | None = None,
) -> FixedOntologyEvidenceLedger:
    return FixedOntologyEvidenceLedger(
        ledger_id="evidence_ledger_one",
        session_id="session_one",
        ontology=fixed_ontology(),
        extractor_configurations=[configuration()],
        messages=messages(),
        structured_evidence=[
            evidence_event("evidence_one", 4),
            evidence_event("evidence_two", 5),
            evidence_event("evidence_three", 6),
            evidence_event("evidence_four", 7),
        ],
        corrections=[] if corrections is None else corrections,
        created_at=NOW,
    )


def empty_expansion(
    evidence: FixedOntologyEvidenceLedger | None = None,
    *,
    expansion_policy: OntologyExpansionPolicy | None = None,
    condition: EvidenceCondition = EvidenceCondition.COMBINED,
) -> ExpandingOntologyLedger:
    bound_evidence = evidence or evidence_ledger()
    return ExpandingOntologyLedger(
        ledger_id="ontology_ledger_one",
        session_id="session_one",
        evidence_condition=condition,
        evidence_ledger_id=bound_evidence.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            bound_evidence
        ),
        seed=seed(),
        policy=expansion_policy or policy(),
        created_at=NOW,
    )


def context_for(
    expansion: ExpandingOntologyLedger,
    evidence: FixedOntologyEvidenceLedger,
    *,
    sequence: int = 10,
    evidence_cutoff_sequence: int = 7,
):
    return build_ontology_proposal_context(
        context_id=f"context_{sequence}",
        expansion_ledger=expansion,
        evidence_ledger=evidence,
        configuration=configuration(),
        sequence=sequence,
        created_at=at(sequence),
        message_cutoff_sequence=3,
        evidence_cutoff_sequence=evidence_cutoff_sequence,
    )


def proposal_for(
    context,
    *,
    proposal_id: str = "proposal_one",
    sequence: int = 11,
    proposed_dimension: OntologyDimensionDefinition | None = None,
    support: list[str] | None = None,
    candidates: list[str] | None = None,
    assumptions: list[UnsupportedAssumptionFlag] | None = None,
) -> OntologyDimensionProposal:
    return OntologyDimensionProposal(
        proposal_id=proposal_id,
        context_id=context.context_id,
        context_sha256=content_sha256(context),
        session_id="session_one",
        sequence=sequence,
        created_at=at(sequence),
        source_message_ids=["message_one", "message_three"],
        proposed_dimension=proposed_dimension or dimension("community_voice"),
        supporting_evidence_event_ids=([] if support is None else support),
        candidate_duplicate_dimension_ids=candidates or [],
        extractor_confidence=0.71,
        unsupported_assumptions=assumptions or [],
    )


def admit_decision(
    proposal: OntologyDimensionProposal,
    *,
    sequence: int = 12,
    admitted_dimension: OntologyDimensionDefinition | None = None,
) -> OntologyProposalDecision:
    return OntologyProposalDecision(
        decision_id=f"decision_{sequence}",
        proposal_id=proposal.proposal_id,
        decision=OntologyProposalDecisionKind.ADMIT_NEW,
        admitted_dimension=admitted_dimension or proposal.proposed_dimension,
        acknowledged_candidate_dimension_ids=(
            proposal.candidate_duplicate_dimension_ids
        ),
        acknowledged_assumption_flag_ids=[
            flag.flag_id for flag in proposal.unsupported_assumptions
        ],
        session_id="session_one",
        sequence=sequence,
        created_at=at(sequence),
    )


def expansion_with_admission(
    evidence: FixedOntologyEvidenceLedger | None = None,
    *,
    proposed_dimension: OntologyDimensionDefinition | None = None,
    support: list[str] | None = None,
    expansion_policy: OntologyExpansionPolicy | None = None,
) -> ExpandingOntologyLedger:
    bound_evidence = evidence or evidence_ledger()
    expansion = empty_expansion(
        bound_evidence,
        expansion_policy=expansion_policy,
    )
    context = context_for(expansion, bound_evidence)
    proposal = proposal_for(
        context,
        proposed_dimension=proposed_dimension,
        support=support,
    )
    return expansion.model_copy(
        update={
            "contexts": [context],
            "proposals": [proposal],
            "decisions": [admit_decision(proposal)],
        }
    )


def state_by_id(snapshot):
    return {item.dimension.dimension_id: item for item in snapshot.dimensions}


class TestContractsAndBindings:
    def test_policy_rejects_incoherent_thresholds(self):
        with pytest.raises(ValidationError, match="admission support weight"):
            policy(admission_confirmation_support_weight=1.5)

        with pytest.raises(ValidationError, match="admission-only"):
            policy(prune_max_support_score=0.25)

        with pytest.raises(ValidationError, match="prune support threshold"):
            policy(prune_max_support_score=1.5)

    def test_seed_rejects_duplicate_normalized_semantics(self):
        dimensions = [
            dimension("a", name="Shared"),
            dimension("b", name=" shared "),
        ]
        dimensions[1] = dimensions[1].model_copy(
            update={
                "definition": dimensions[0].definition.upper(),
                "interpretation": dimensions[0].interpretation.upper(),
            }
        )

        with pytest.raises(ValidationError, match="semantics"):
            ExpandingOntologySeed(
                ontology_id="duplicate",
                seed_version=1,
                dimensions=dimensions,
                dimensions_sha256=content_sha256(
                    [item.model_dump(mode="json") for item in dimensions]
                ),
            )

    def test_seed_must_exactly_define_fixed_ontology(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence).model_copy(
            update={
                "seed": seed().model_copy(update={"ontology_id": "wrong"})
            }
        )

        with pytest.raises(ValueError, match="wrong fixed ontology"):
            validate_expanding_ontology_ledger(expansion, evidence)

    def test_context_binds_exact_inputs_and_active_ontology(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)

        assert context.input_message_ids == [
            "message_one",
            "message_two",
            "message_three",
        ]
        assert context.eligible_evidence_event_ids == [
            "evidence_one",
            "evidence_two",
            "evidence_three",
            "evidence_four",
        ]
        assert context.eligible_evidence[0].claim.claim_text == (
            "Confirmed preference evidence_one."
        )
        assert [item.dimension_id for item in context.active_dimensions] == [
            "autonomy",
            "collective_welfare",
        ]
        assert context.target_packet_visible is False
        assert context.evidence_condition is EvidenceCondition.COMBINED

    def test_structured_only_uses_seed_without_conversation_proposals(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(
            evidence,
            condition=EvidenceCondition.STRUCTURED_ONLY,
        )

        validate_expanding_ontology_ledger(expansion, evidence)
        snapshot = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=7,
        )
        assert set(state_by_id(snapshot)) == {
            "autonomy",
            "collective_welfare",
        }
        with pytest.raises(ValueError, match="cannot use conversation proposals"):
            context_for(expansion, evidence)

    def test_structured_only_rejects_expansion_records_at_ledger_boundary(self):
        evidence = evidence_ledger()
        combined = empty_expansion(evidence)
        context = context_for(combined, evidence).model_copy(
            update={"evidence_condition": EvidenceCondition.STRUCTURED_ONLY}
        )
        payload = combined.model_dump(mode="json")
        payload["evidence_condition"] = EvidenceCondition.STRUCTURED_ONLY.value
        payload["contexts"] = [context.model_dump(mode="json")]

        with pytest.raises(ValidationError, match="cannot contain expansion"):
            ExpandingOntologyLedger.model_validate(payload)

    def test_condition_specific_evidence_prevents_cross_origin_leakage(self):
        correction = EvidenceCorrectionEvent(
            correction_id="correction_conversation",
            evidence_event_id="evidence_one_conversation_correction",
            supersedes_evidence_event_id="evidence_one",
            session_id="session_one",
            sequence=13,
            created_at=at(13),
            corrected_claim=FixedOntologyClaim(
                claim_text="Conversation correction to structured evidence.",
                item_a="autonomy",
                item_b="collective_welfare",
                value=0.25,
            ),
            origin="conversation",
            source_message_ids=["message_three"],
        )
        evidence = evidence_ledger(corrections=[correction])

        structured = active_confirmed_evidence_references(
            evidence,
            cutoff_sequence=13,
            condition=EvidenceCondition.STRUCTURED_ONLY,
        )
        conversation = active_confirmed_evidence_references(
            evidence,
            cutoff_sequence=13,
            condition=EvidenceCondition.CONVERSATION_ONLY,
        )
        combined = active_confirmed_evidence_references(
            evidence,
            cutoff_sequence=13,
            condition=EvidenceCondition.COMBINED,
        )

        assert "evidence_one" in {
            item.evidence_event_id for item in structured
        }
        assert [item.evidence_event_id for item in conversation] == [
            "evidence_one_conversation_correction"
        ]
        assert "evidence_one_conversation_correction" in {
            item.evidence_event_id for item in combined
        }

    def test_context_parent_snapshot_tamper_is_rejected(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence).model_copy(
            update={"parent_snapshot_sha256": "0" * 64}
        )
        tampered = expansion.model_copy(update={"contexts": [context]})

        with pytest.raises(ValueError, match="parent snapshot hash"):
            validate_expanding_ontology_ledger(tampered, evidence)

    def test_pending_proposals_are_fully_validated(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        pending = proposal_for(context).model_copy(
            update={"source_message_ids": ["message_two"]}
        )
        tampered = expansion.model_copy(
            update={"contexts": [context], "proposals": [pending]}
        )

        with pytest.raises(ValueError, match="participant messages"):
            validate_expanding_ontology_ledger(tampered, evidence)

    def test_proposal_weight_is_always_zero(self):
        evidence = evidence_ledger()
        context = context_for(empty_expansion(evidence), evidence)
        payload = proposal_for(context).model_dump(mode="json")
        payload["provisional_dimension_weight"] = 0.2

        with pytest.raises(ValidationError, match="provisional_dimension_weight"):
            OntologyDimensionProposal.model_validate(payload)


class TestProviderBoundary:
    def test_draft_canonicalizes_nonsemantic_provider_lists(self):
        first = UnsupportedAssumptionFlag(
            flag_id="a_assumption",
            description="The first assumption.",
        )
        second = UnsupportedAssumptionFlag(
            flag_id="z_assumption",
            description="The second assumption.",
        )
        draft = OntologyDimensionProposalDraft(
            source_message_ids=["message_one", "message_one"],
            proposed_dimension=dimension("community_voice"),
            supporting_evidence_event_ids=["evidence_one", "evidence_one"],
            candidate_duplicate_dimension_ids=["b", "a", "b"],
            extractor_confidence=0.71,
            unsupported_assumptions=[second, first, second],
        )

        assert draft.source_message_ids == ["message_one"]
        assert draft.supporting_evidence_event_ids == ["evidence_one"]
        assert draft.candidate_duplicate_dimension_ids == ["a", "b"]
        assert [item.flag_id for item in draft.unsupported_assumptions] == [
            "a_assumption",
            "z_assumption",
        ]

    def test_draft_preserves_nonempty_source_lineage(self):
        with pytest.raises(ValidationError, match="participant messages"):
            OntologyDimensionProposalDraft(
                source_message_ids=[],
                proposed_dimension=dimension("community_voice"),
                supporting_evidence_event_ids=[],
                extractor_confidence=0.71,
            )

    def test_draft_rejects_conflicting_duplicate_assumption_ids(self):
        with pytest.raises(
            ValidationError,
            match="unsupported assumption flag ids must be unique",
        ):
            OntologyDimensionProposalDraft(
                source_message_ids=["message_one"],
                proposed_dimension=dimension("community_voice"),
                supporting_evidence_event_ids=[],
                extractor_confidence=0.71,
                unsupported_assumptions=[
                    UnsupportedAssumptionFlag(
                        flag_id="scope_assumption",
                        description="The first interpretation.",
                    ),
                    UnsupportedAssumptionFlag(
                        flag_id="scope_assumption",
                        description="A conflicting interpretation.",
                    ),
                ],
            )

    def test_provider_output_is_revalidated_and_stays_provisional(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        draft = OntologyDimensionProposalDraft(
            source_message_ids=["message_one", "message_three"],
            proposed_dimension=dimension("community_voice"),
            supporting_evidence_event_ids=["evidence_one"],
            extractor_confidence=0.71,
        )
        backend = DeterministicOntologyExpansionBackend(
            configuration(),
            [draft],
        )

        output = run_ontology_expansion_backend(
            context=context,
            expansion_ledger=expansion,
            evidence_ledger=evidence,
            backend=backend,
            proposal_ids=["proposal_one"],
            proposal_sequences=[11],
            created_at=at(11),
        )

        assert backend.call_count == 1
        assert output[0].provisional_dimension_weight == 0.0
        assert output[0].proposed_dimension == draft.proposed_dimension

    def test_provider_cannot_use_interviewer_message_as_source(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        draft = OntologyDimensionProposalDraft(
            source_message_ids=["message_two"],
            proposed_dimension=dimension("community_voice"),
            supporting_evidence_event_ids=["evidence_one"],
            extractor_confidence=0.71,
        )
        backend = DeterministicOntologyExpansionBackend(configuration(), [draft])

        with pytest.raises(ValueError, match="participant messages"):
            run_ontology_expansion_backend(
                context=context,
                expansion_ledger=expansion,
                evidence_ledger=evidence,
                backend=backend,
                proposal_ids=["proposal_one"],
                proposal_sequences=[11],
                created_at=at(11),
            )

    def test_provider_must_flag_exact_semantic_duplicate(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        duplicate = dimension(
            "renamed_autonomy",
            name="  AUTONOMY ",
            definition="PREFERENCE CONCERNING AUTONOMY.",
            interpretation="HIGHER VALUES FAVOR AUTONOMY.",
        )
        draft = OntologyDimensionProposalDraft(
            source_message_ids=["message_one"],
            proposed_dimension=duplicate,
            supporting_evidence_event_ids=["evidence_one"],
            extractor_confidence=0.71,
        )
        backend = DeterministicOntologyExpansionBackend(configuration(), [draft])

        with pytest.raises(ValueError, match="exact semantic duplicate"):
            run_ontology_expansion_backend(
                context=context,
                expansion_ledger=expansion,
                evidence_ledger=evidence,
                backend=backend,
                proposal_ids=["proposal_one"],
                proposal_sequences=[11],
                created_at=at(11),
            )

    def test_provider_output_model_instances_are_revalidated(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        draft = OntologyDimensionProposalDraft(
            source_message_ids=["message_one"],
            proposed_dimension=dimension("community_voice"),
            supporting_evidence_event_ids=[],
            extractor_confidence=0.71,
        ).model_copy(update={"extractor_confidence": 0.0})

        class InvalidBackend:
            configuration = configuration()

            def propose(self, request_context, input_messages):
                return [draft]

        with pytest.raises(ValidationError, match="extractor_confidence"):
            run_ontology_expansion_backend(
                context=context,
                expansion_ledger=expansion,
                evidence_ledger=evidence,
                backend=InvalidBackend(),
                proposal_ids=["proposal_one"],
                proposal_sequences=[11],
                created_at=at(11),
            )

    def test_provider_rejects_model_copy_that_bypasses_context_literal(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence).model_copy(
            update={"target_packet_visible": True}
        )
        backend = DeterministicOntologyExpansionBackend(
            configuration(),
            [
                OntologyDimensionProposalDraft(
                    source_message_ids=["message_one"],
                    proposed_dimension=dimension("community_voice"),
                    supporting_evidence_event_ids=[],
                    extractor_confidence=0.71,
                )
            ],
        )

        with pytest.raises(ValidationError, match="target_packet_visible"):
            run_ontology_expansion_backend(
                context=context,
                expansion_ledger=expansion,
                evidence_ledger=evidence,
                backend=backend,
                proposal_ids=["proposal_one"],
                proposal_sequences=[11],
                created_at=at(11),
            )

    def test_provider_validates_context_against_real_parent_before_call(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        fabricated_dimensions = [
            *context.active_dimensions,
            dimension("fabricated_dimension"),
        ]
        fabricated = context.model_copy(
            update={
                "active_dimensions": fabricated_dimensions,
                "active_dimensions_sha256": content_sha256(
                    [
                        item.model_dump(mode="json")
                        for item in fabricated_dimensions
                    ]
                ),
            }
        )
        backend = DeterministicOntologyExpansionBackend(
            configuration(),
            [],
        )

        with pytest.raises(ValueError, match="active dimensions do not match"):
            run_ontology_expansion_backend(
                context=fabricated,
                expansion_ledger=expansion,
                evidence_ledger=evidence,
                backend=backend,
                proposal_ids=[],
                proposal_sequences=[],
                created_at=at(11),
            )
        assert backend.call_count == 0


class TestAdmissionAndMapping:
    def test_pending_and_rejected_proposals_do_not_change_ontology(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        proposal = proposal_for(context)
        pending = expansion.model_copy(
            update={"contexts": [context], "proposals": [proposal]}
        )
        pending_snapshot = replay_expanding_ontology(
            pending,
            evidence,
            cutoff_sequence=11,
        )

        rejection = OntologyProposalDecision(
            decision_id="decision_reject",
            proposal_id=proposal.proposal_id,
            decision=OntologyProposalDecisionKind.REJECT,
            session_id="session_one",
            sequence=12,
            created_at=at(12),
        )
        rejected = pending.model_copy(update={"decisions": [rejection]})
        rejected_snapshot = replay_expanding_ontology(
            rejected,
            evidence,
            cutoff_sequence=12,
        )

        assert set(state_by_id(pending_snapshot)) == {
            "autonomy",
            "collective_welfare",
        }
        assert rejected_snapshot == pending_snapshot.model_copy(
            update={"event_cutoff_sequence": 12}
        )

    def test_admission_requires_explicit_decision_and_starts_shrunk(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)

        before = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=11,
        )
        after = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=12,
        )

        assert "community_voice" not in state_by_id(before)
        admitted = state_by_id(after)["community_voice"]
        assert admitted.status is ExpandingDimensionStatus.ACTIVE
        assert admitted.independent_evidence_lineage_count == 0
        assert admitted.support_score == 0.5
        assert admitted.shrinkage_weight == pytest.approx(1 / 3)

    def test_admission_can_precede_fixed_ontology_evidence(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        proposal = proposal_for(context, support=[])
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [admit_decision(proposal)],
            }
        )

        snapshot = replay_expanding_ontology(
            built,
            evidence,
            cutoff_sequence=12,
        )

        admitted = state_by_id(snapshot)["community_voice"]
        assert admitted.admission_confirmation_count == 1
        assert admitted.supporting_evidence_event_ids == []
        assert admitted.independent_evidence_lineage_count == 0
        assert admitted.support_score == 0.5
        assert admitted.shrinkage_weight == pytest.approx(1 / 3)

    def test_participant_can_edit_definition_at_admission(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        proposal = proposal_for(context)
        edited = proposal.proposed_dimension.model_copy(
            update={"definition": "Participant-authored exact definition."}
        )
        decision = admit_decision(proposal, admitted_dimension=edited)
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [decision],
            }
        )

        snapshot = replay_expanding_ontology(
            built,
            evidence,
            cutoff_sequence=12,
        )

        assert state_by_id(snapshot)["community_voice"].dimension == edited

    def test_assumptions_and_duplicate_candidates_require_acknowledgement(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        proposal = proposal_for(
            context,
            candidates=["autonomy"],
            assumptions=[
                UnsupportedAssumptionFlag(
                    flag_id="scope_flag",
                    description="The stated scope may be broader than the evidence.",
                )
            ],
        )
        decision = admit_decision(proposal).model_copy(
            update={
                "acknowledged_candidate_dimension_ids": [],
                "acknowledged_assumption_flag_ids": [],
            }
        )
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [decision],
            }
        )

        with pytest.raises(ValueError, match="acknowledge duplicate candidates"):
            validate_expanding_ontology_ledger(built, evidence)

    def test_exact_semantic_duplicate_cannot_be_admitted(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        duplicate = seed().dimensions[0].model_copy(
            update={"dimension_id": "renamed_autonomy"}
        )
        proposal = proposal_for(
            context,
            proposed_dimension=duplicate,
            support=["evidence_one"],
            candidates=["autonomy"],
        )
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [admit_decision(proposal)],
            }
        )

        with pytest.raises(ValueError, match="semantic duplicate"):
            validate_expanding_ontology_ledger(built, evidence)

    def test_reviewed_duplicate_can_map_to_existing_dimension(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        duplicate = seed().dimensions[0].model_copy(
            update={"dimension_id": "renamed_autonomy"}
        )
        proposal = proposal_for(
            context,
            proposed_dimension=duplicate,
            support=["evidence_one"],
            candidates=["autonomy"],
        )
        decision = OntologyProposalDecision(
            decision_id="decision_map",
            proposal_id=proposal.proposal_id,
            decision=OntologyProposalDecisionKind.MAP_TO_EXISTING,
            mapped_dimension_id="autonomy",
            acknowledged_candidate_dimension_ids=["autonomy"],
            session_id="session_one",
            sequence=12,
            created_at=at(12),
        )
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [decision],
            }
        )

        snapshot = replay_expanding_ontology(
            built,
            evidence,
            cutoff_sequence=12,
        )

        assert "renamed_autonomy" not in state_by_id(snapshot)
        assert state_by_id(snapshot)["autonomy"].supporting_evidence_event_ids == [
            "evidence_one"
        ]

    def test_mapping_requires_target_to_be_a_reviewed_candidate(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        context = context_for(expansion, evidence)
        proposal = proposal_for(context)
        decision = OntologyProposalDecision(
            decision_id="decision_map",
            proposal_id=proposal.proposal_id,
            decision=OntologyProposalDecisionKind.MAP_TO_EXISTING,
            mapped_dimension_id="autonomy",
            session_id="session_one",
            sequence=12,
            created_at=at(12),
        )
        built = expansion.model_copy(
            update={
                "contexts": [context],
                "proposals": [proposal],
                "decisions": [decision],
            }
        )

        with pytest.raises(ValueError, match="reviewed duplicate"):
            validate_expanding_ontology_ledger(built, evidence)


class TestShrinkageMergeAndPrune:
    def test_independent_support_reaches_full_weight(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)
        support = OntologyDimensionSupportEvent(
            support_id="support_two",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_two"],
            support_rationale="A second independent answer supports the dimension.",
            session_id="session_one",
            sequence=13,
            created_at=at(13),
        )
        expansion = expansion.model_copy(update={"support_events": [support]})

        snapshot = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=13,
        )
        state = state_by_id(snapshot)["community_voice"]

        assert state.independent_evidence_lineage_count == 1
        assert state.support_score == 1.5
        assert state.shrinkage_weight == 1.0

    def test_non_dyadic_score_saturates_at_exact_full_weight(self):
        evidence = evidence_ledger()
        decimal_policy = policy(
            admission_confirmation_support_weight=0.1,
            evidence_lineage_support_weight=0.2,
            full_weight_support_score=0.3,
            prune_max_support_score=0.1,
        )
        expansion = expansion_with_admission(
            evidence,
            expansion_policy=decimal_policy,
        )
        support = OntologyDimensionSupportEvent(
            support_id="support_decimal_full",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_two"],
            support_rationale=(
                "A second independent answer reaches the decimal threshold."
            ),
            session_id="session_one",
            sequence=13,
            created_at=at(13),
        )
        expansion = expansion.model_copy(update={"support_events": [support]})

        snapshot = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=13,
        )
        state = state_by_id(snapshot)["community_voice"]

        assert state.support_score == pytest.approx(0.3)
        assert state.shrinkage_weight == 1.0

    def test_correction_does_not_double_count_one_evidence_lineage(self):
        correction = EvidenceCorrectionEvent(
            correction_id="correction_one",
            evidence_event_id="evidence_one_corrected",
            supersedes_evidence_event_id="evidence_one",
            session_id="session_one",
            sequence=13,
            created_at=at(13),
            corrected_claim=FixedOntologyClaim(
                claim_text="Corrected confirmed preference.",
                item_a="autonomy",
                item_b="collective_welfare",
                value=0.5,
            ),
            origin="structured",
            question_id="question_correction",
            response_id="response_correction",
        )
        evidence = evidence_ledger(corrections=[correction])
        expansion = expansion_with_admission(evidence)
        support = OntologyDimensionSupportEvent(
            support_id="support_correction",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_one_corrected"],
            support_rationale="The correction preserves this support lineage.",
            session_id="session_one",
            sequence=14,
            created_at=at(14),
        )
        expansion = expansion.model_copy(update={"support_events": [support]})

        references = confirmed_evidence_references(evidence)
        active = active_confirmed_evidence_references(
            evidence,
            cutoff_sequence=13,
        )
        snapshot = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=14,
        )
        state = state_by_id(snapshot)["community_voice"]

        assert references[0].evidence_lineage_id == "evidence_one"
        assert next(
            item for item in references if item.evidence_event_id.endswith("corrected")
        ).evidence_lineage_id == "evidence_one"
        assert "evidence_one" not in {
            item.evidence_event_id for item in active
        }
        assert len(state.supporting_evidence_lineage_ids) == 1
        assert state.independent_evidence_lineage_count == 1
        assert state.support_score == 1.5
        assert state.shrinkage_weight == 1.0

    def test_support_must_be_active_and_prior(self):
        correction = EvidenceCorrectionEvent(
            correction_id="correction_one",
            evidence_event_id="evidence_one_corrected",
            supersedes_evidence_event_id="evidence_one",
            session_id="session_one",
            sequence=13,
            created_at=at(13),
            corrected_claim=FixedOntologyClaim(
                claim_text="Corrected confirmed preference.",
                item_a="autonomy",
                item_b="collective_welfare",
                value=0.5,
            ),
            origin="structured",
            question_id="question_correction",
            response_id="response_correction",
        )
        evidence = evidence_ledger(corrections=[correction])
        expansion = expansion_with_admission(evidence)
        stale_support = OntologyDimensionSupportEvent(
            support_id="support_stale",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_one"],
            support_rationale="Deliberately stale support for the rejection test.",
            session_id="session_one",
            sequence=14,
            created_at=at(14),
        )
        expansion = expansion.model_copy(
            update={"support_events": [stale_support]}
        )

        with pytest.raises(ValueError, match="active prior confirmed evidence"):
            validate_expanding_ontology_ledger(expansion, evidence)

    def test_merge_preserves_sources_and_unions_support(self):
        evidence = evidence_ledger()
        first = expansion_with_admission(evidence)
        second_context = context_for(first, evidence, sequence=13)
        second_proposal = proposal_for(
            second_context,
            proposal_id="proposal_two",
            sequence=14,
            proposed_dimension=dimension("local_knowledge"),
            support=["evidence_two"],
        )
        second_decision = admit_decision(second_proposal, sequence=15)
        merge = OntologyDimensionMergeEvent(
            merge_id="merge_one",
            source_dimension_ids=["community_voice", "local_knowledge"],
            merged_dimension=dimension("community_agency"),
            merge_rationale="The participant confirmed these describe one value.",
            session_id="session_one",
            sequence=16,
            created_at=at(16),
        )
        built = first.model_copy(
            update={
                "contexts": [*first.contexts, second_context],
                "proposals": [*first.proposals, second_proposal],
                "decisions": [*first.decisions, second_decision],
                "merge_events": [merge],
            }
        )

        snapshot = replay_expanding_ontology(
            built,
            evidence,
            cutoff_sequence=16,
        )
        states = state_by_id(snapshot)

        assert states["community_voice"].status is ExpandingDimensionStatus.MERGED
        assert states["community_voice"].shrinkage_weight is None
        assert states["local_knowledge"].merged_into_dimension_id == (
            "community_agency"
        )
        assert states["local_knowledge"].shrinkage_weight is None
        assert states[
            "community_agency"
        ].independent_evidence_lineage_count == 1
        assert states["community_agency"].support_score == 1.5
        assert states["community_agency"].shrinkage_weight == 1.0
        assert {
            item.dimension.dimension_id
            for item in active_dimension_states(snapshot)
        } == {"autonomy", "collective_welfare", "community_agency"}

    def test_seed_dimensions_cannot_be_merged_or_pruned(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        merge = OntologyDimensionMergeEvent(
            merge_id="merge_seed",
            source_dimension_ids=["autonomy", "collective_welfare"],
            merged_dimension=dimension("combined_seed"),
            merge_rationale="Test attempted an impermissible seed merge.",
            session_id="session_one",
            sequence=10,
            created_at=at(10),
        )
        merge_ledger = expansion.model_copy(update={"merge_events": [merge]})

        with pytest.raises(ValueError, match="seed dimensions cannot be merged"):
            validate_expanding_ontology_ledger(merge_ledger, evidence)

        prune = OntologyDimensionPruneEvent(
            prune_id="prune_seed",
            dimension_id="autonomy",
            reason="Test attempted seed removal.",
            session_id="session_one",
            sequence=10,
            created_at=at(10),
        )
        prune_ledger = expansion.model_copy(update={"prune_events": [prune]})
        with pytest.raises(ValueError, match="seed dimensions cannot be pruned"):
            validate_expanding_ontology_ledger(prune_ledger, evidence)

    def test_weak_idle_dimension_can_be_pruned_but_history_remains(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)
        prune = OntologyDimensionPruneEvent(
            prune_id="prune_one",
            dimension_id="community_voice",
            reason="Participant confirmed the weak dimension is redundant.",
            session_id="session_one",
            sequence=15,
            created_at=at(15),
        )
        expansion = expansion.model_copy(update={"prune_events": [prune]})

        before = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=14,
        )
        after = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=15,
        )

        assert state_by_id(before)["community_voice"].status is (
            ExpandingDimensionStatus.ACTIVE
        )
        assert state_by_id(after)["community_voice"].status is (
            ExpandingDimensionStatus.PRUNED
        )
        assert state_by_id(after)["community_voice"].shrinkage_weight is None

    def test_prune_accepts_non_dyadic_score_at_exact_policy_boundary(self):
        evidence = evidence_ledger()
        decimal_policy = policy(
            admission_confirmation_support_weight=0.1,
            evidence_lineage_support_weight=0.2,
            full_weight_support_score=0.4,
            prune_max_support_score=0.3,
        )
        expansion = expansion_with_admission(
            evidence,
            expansion_policy=decimal_policy,
        )
        support = OntologyDimensionSupportEvent(
            support_id="support_decimal_boundary",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_two"],
            support_rationale=(
                "A second independent answer reaches the prune boundary."
            ),
            session_id="session_one",
            sequence=13,
            created_at=at(13),
        )
        prune = OntologyDimensionPruneEvent(
            prune_id="prune_decimal_boundary",
            dimension_id="community_voice",
            reason="The participant confirmed the boundary case is redundant.",
            session_id="session_one",
            sequence=16,
            created_at=at(16),
        )
        expansion = expansion.model_copy(
            update={
                "support_events": [support],
                "prune_events": [prune],
            }
        )

        snapshot = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=16,
        )
        state = state_by_id(snapshot)["community_voice"]

        assert state.status is ExpandingDimensionStatus.PRUNED
        assert state.support_score == pytest.approx(0.3)
        assert state.shrinkage_weight is None

    def test_retired_dimension_is_visible_and_cannot_be_reproposed(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)
        prune = OntologyDimensionPruneEvent(
            prune_id="prune_one",
            dimension_id="community_voice",
            reason="Participant confirmed the weak dimension is redundant.",
            session_id="session_one",
            sequence=15,
            created_at=at(15),
        )
        pruned = expansion.model_copy(update={"prune_events": [prune]})
        context = context_for(pruned, evidence, sequence=16)
        reproposed = proposal_for(
            context,
            proposal_id="proposal_recycled",
            sequence=17,
            proposed_dimension=dimension("community_voice").model_copy(
                update={"dimension_id": "community_voice_recycled"}
            ),
        )
        built = pruned.model_copy(
            update={
                "contexts": [*pruned.contexts, context],
                "proposals": [*pruned.proposals, reproposed],
            }
        )

        assert [item.dimension_id for item in context.retired_dimensions] == [
            "community_voice"
        ]
        with pytest.raises(ValueError, match="retired dimension semantics"):
            validate_expanding_ontology_ledger(built, evidence)

    def test_prune_fails_when_not_idle_or_too_well_supported(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)
        too_soon = OntologyDimensionPruneEvent(
            prune_id="prune_soon",
            dimension_id="community_voice",
            reason="Too soon.",
            session_id="session_one",
            sequence=14,
            created_at=at(14),
        )
        with pytest.raises(ValueError, match="not idle long enough"):
            validate_expanding_ontology_ledger(
                expansion.model_copy(update={"prune_events": [too_soon]}),
                evidence,
            )

        support = OntologyDimensionSupportEvent(
            support_id="support_two",
            dimension_id="community_voice",
            evidence_event_ids=["evidence_two"],
            support_rationale="A second independent answer supports the dimension.",
            session_id="session_one",
            sequence=13,
            created_at=at(13),
        )
        prune_supported = too_soon.model_copy(
            update={
                "prune_id": "prune_supported",
                "sequence": 16,
                "created_at": at(16),
            }
        )
        supported = expansion.model_copy(
            update={
                "support_events": [support],
                "prune_events": [prune_supported],
            }
        )
        with pytest.raises(ValueError, match="too much support"):
            validate_expanding_ontology_ledger(supported, evidence)


class TestReplayAndAudit:
    def test_round_trip_and_replay_are_deterministic(self):
        evidence = evidence_ledger()
        expansion = expansion_with_admission(evidence)
        payload = expansion.model_dump(mode="json")
        restored = ExpandingOntologyLedger.model_validate(payload)

        first = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=12,
        )
        second = replay_expanding_ontology(
            restored,
            evidence,
            cutoff_sequence=12,
        )

        assert first == second
        assert content_sha256(first) == content_sha256(second)

    def test_dimension_semantic_hash_ignores_case_and_whitespace_not_id(self):
        original = dimension("one", name="Community Voice")
        renamed = dimension(
            "two",
            name="  COMMUNITY   VOICE ",
            definition=original.definition.upper(),
            interpretation=original.interpretation.upper(),
        )

        assert dimension_semantic_sha256(original) == dimension_semantic_sha256(
            renamed
        )

    def test_expansion_and_evidence_records_cannot_share_sequence(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        prune = OntologyDimensionPruneEvent(
            prune_id="colliding_prune",
            dimension_id="autonomy",
            reason="Collision probe.",
            session_id="session_one",
            sequence=7,
            created_at=at(7),
        )
        collision = expansion.model_copy(update={"prune_events": [prune]})

        with pytest.raises(ValueError, match="cannot share a sequence"):
            validate_expanding_ontology_ledger(collision, evidence)

    def test_evidence_ledger_hash_drift_fails_closed(self):
        evidence = evidence_ledger()
        expansion = empty_expansion(evidence)
        altered = evidence.model_copy(
            update={"created_at": NOW - timedelta(minutes=1)}
        )

        with pytest.raises(ValueError, match="hash does not match"):
            validate_expanding_ontology_ledger(expansion, altered)

    def test_future_evidence_can_append_without_rewriting_prior_context(self):
        original_evidence = evidence_ledger()
        expansion = expansion_with_admission(original_evidence)
        future = evidence_event("evidence_future", 13)
        extended_evidence = original_evidence.model_copy(
            update={
                "structured_evidence": [
                    *original_evidence.structured_evidence,
                    future,
                ]
            }
        )

        validate_expanding_ontology_ledger(expansion, extended_evidence)
        snapshot = replay_expanding_ontology(
            expansion,
            extended_evidence,
            cutoff_sequence=12,
        )

        assert "community_voice" in state_by_id(snapshot)
