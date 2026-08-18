"""Tests for provider-neutral direct and hybrid Phase 4D readouts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from preferences.types import EvidenceSource

from eval.contracts import MeasurePresentation, PresentationKind
from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_classical_readout import (
    GaussianLinearModelArtifact,
    classical_model_artifact_reference,
)
from eval.phase4_evidence import (
    ConversationEvidenceMessage,
    EvidenceExtractorConfiguration,
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    StructuredPreferenceEvidenceEvent,
)
from eval.phase4_interviewer import ConversationRole
from eval.phase4_llm_readout import (
    DeterministicLLMReadoutBackend,
    InMemoryLLMReadoutCache,
    JsonDirectoryLLMReadoutCache,
    LLMProviderModelArtifact,
    LLMReadoutExecutor,
    LLMReadoutPolicy,
    LLMReadoutPromptArtifact,
    build_direct_llm_prediction_snapshot,
    build_hybrid_prediction_snapshot,
    llm_prompt_artifact_reference,
    llm_provider_artifact_reference,
    llm_readout_artifact_reference,
    validate_llm_prediction_snapshot,
)
from eval.phase4_ontology import (
    ExpandingOntologyLedger,
    ExpandingOntologySeed,
    OntologyDimensionDefinition,
    OntologyDimensionProposal,
    OntologyExpansionPolicy,
    OntologyProposalDecision,
    OntologyProposalDecisionKind,
    build_ontology_proposal_context,
    evidence_ledger_identity_sha256,
)
from eval.phase4_prediction import (
    Phase4EvaluationRun,
    Phase4ModelConfiguration,
    PredictionCheckpoint,
    active_ontology_input_sha256,
    validate_phase4_evaluation_run,
    validate_prediction_v2_for_measure,
)
from eval.phase4_protocol import EvidenceCondition, load_phase4_protocol
from eval.phase4_semantic import (
    load_authored_semantic_map,
    semantic_map_artifact_reference,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / "eval/fixtures/preference_eval_dev_v1.json")
PROTOCOL = load_phase4_protocol(
    ROOT / "eval/fixtures/preference_eval_phase4_protocol_v1.json"
)
SEMANTIC_MAP = load_authored_semantic_map(
    ROOT / "eval/fixtures/preference_eval_dev_semantic_map_v1.json"
)
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


def extractor_configuration() -> EvidenceExtractorConfiguration:
    return EvidenceExtractorConfiguration(
        configuration_id="phase4_llm_test_extractor",
        backend_id="deterministic_test_double",
        backend_version=1,
        model_id="test_evidence_extractor",
        model_version="1.0.0",
        prompt_id="test_evidence_prompt",
        prompt_version=1,
        prompt_sha256=content_sha256("test extraction prompt"),
        implementation_version=1,
        seed=11,
    )


def messages() -> list[ConversationEvidenceMessage]:
    return [
        ConversationEvidenceMessage(
            message_id="message_one",
            session_id="session_one",
            sequence=1,
            created_at=at(1),
            role=ConversationRole.PARTICIPANT,
            content="A planted private preference statement.",
        ),
        ConversationEvidenceMessage(
            message_id="message_two",
            session_id="session_one",
            sequence=2,
            created_at=at(2),
            role=ConversationRole.INTERVIEWER,
            content="A neutral follow-up question.",
        ),
    ]


def evidence_event() -> StructuredPreferenceEvidenceEvent:
    item_a, item_b = SEMANTIC_MAP.ontology.item_ids[:2]
    return StructuredPreferenceEvidenceEvent(
        evidence_event_id="evidence_one",
        session_id="session_one",
        sequence=3,
        created_at=at(3),
        source=EvidenceSource.PAIRWISE,
        claim=FixedOntologyClaim(
            claim_text="The participant confirmed the structured tradeoff.",
            item_a=item_a,
            item_b=item_b,
            value=3.0,
        ),
        question_id="question_one",
        response_id="response_one",
    )


def evidence_ledger() -> FixedOntologyEvidenceLedger:
    return FixedOntologyEvidenceLedger(
        ledger_id="phase4_llm_evidence",
        session_id="session_one",
        ontology=SEMANTIC_MAP.ontology,
        extractor_configurations=[extractor_configuration()],
        messages=messages(),
        structured_evidence=[evidence_event()],
        created_at=NOW,
    )


def model_artifact() -> GaussianLinearModelArtifact:
    return GaussianLinearModelArtifact(
        artifact_id="phase4_hybrid_gaussian",
        artifact_version=1,
    )


def provider_artifact() -> LLMProviderModelArtifact:
    return LLMProviderModelArtifact(
        artifact_id="phase4_test_provider_model",
        artifact_version=1,
        backend_id="deterministic_test_double",
        backend_version=1,
        model_id="deterministic_readout",
        model_version="1.0.0",
        implementation_version=1,
    )


def prompt_artifact() -> LLMReadoutPromptArtifact:
    return LLMReadoutPromptArtifact(
        artifact_id="phase4_test_readout_prompt",
        artifact_version=1,
        system_instruction=(
            "Return a probability for every exact option, cite only eligible "
            "evidence, and flag unsupported assumptions."
        ),
    )


def readout_policy() -> LLMReadoutPolicy:
    return LLMReadoutPolicy(
        artifact_id="phase4_test_llm_readout",
        artifact_version=1,
    )


def configuration(
    arm_id: str,
    condition: EvidenceCondition,
) -> Phase4ModelConfiguration:
    hybrid = arm_id in {
        "hybrid_fixed_ontology",
        "hybrid_expanding_ontology",
    }
    return Phase4ModelConfiguration(
        configuration_id=f"config_{arm_id}_{condition.value}",
        arm_id=arm_id,
        evidence_condition=condition,
        preference_model=(
            classical_model_artifact_reference(model_artifact())
            if hybrid
            else None
        ),
        semantic_mapper=(
            semantic_map_artifact_reference(SEMANTIC_MAP)
            if hybrid
            else None
        ),
        prediction_readout=llm_readout_artifact_reference(readout_policy()),
        provider_model=llm_provider_artifact_reference(provider_artifact()),
        prompt=llm_prompt_artifact_reference(prompt_artifact()),
        seed=41,
    )


def presentation(measure_index: int = 0) -> MeasurePresentation:
    measure = FIXTURE.measures[measure_index]
    return MeasurePresentation(
        presentation_id=f"presentation_{measure.measure_id}",
        session_id="session_one",
        measure_id=measure.measure_id,
        measure_version=measure.version,
        packet_version=measure.packet.version,
        kind=PresentationKind.INITIAL,
        order_seed=91 + measure_index,
        presented_at=at(10),
    )


def executor(
    *,
    cache=None,
    backend=None,
):
    selected_backend = backend or DeterministicLLMReadoutBackend(
        provider_artifact(),
        prompt_artifact(),
    )
    return (
        selected_backend,
        LLMReadoutExecutor(
            backend=selected_backend,
            cache=cache or InMemoryLLMReadoutCache(),
        ),
    )


def expansion_ledger(
    ledger: FixedOntologyEvidenceLedger,
) -> ExpandingOntologyLedger:
    dimensions = [
        OntologyDimensionDefinition(
            dimension_id=item_id,
            name=item_id.replace("_", " ").title(),
            definition=f"Preference concerning {item_id}.",
            interpretation=f"Higher values favor {item_id}.",
        )
        for item_id in ledger.ontology.item_ids
    ]
    seed = ExpandingOntologySeed(
        ontology_id=ledger.ontology.ontology_id,
        seed_version=ledger.ontology.ontology_version,
        dimensions=dimensions,
        dimensions_sha256=content_sha256(
            [item.model_dump(mode="json") for item in dimensions]
        ),
    )
    return ExpandingOntologyLedger(
        ledger_id="phase4_llm_expansion",
        session_id=ledger.session_id,
        evidence_condition=EvidenceCondition.COMBINED,
        evidence_ledger_id=ledger.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            ledger
        ),
        seed=seed,
        policy=OntologyExpansionPolicy(
            policy_id="phase4_llm_expansion_policy",
            policy_version=1,
            admission_confirmation_support_weight=0.5,
            evidence_lineage_support_weight=1.0,
            full_weight_support_score=1.5,
            prune_max_support_score=0.5,
            prune_min_idle_sequence_gap=3,
        ),
        created_at=NOW,
    )


def expansion_with_admission(
    ledger: FixedOntologyEvidenceLedger,
) -> ExpandingOntologyLedger:
    expansion = expansion_ledger(ledger)
    context = build_ontology_proposal_context(
        context_id="readout_context",
        expansion_ledger=expansion,
        evidence_ledger=ledger,
        configuration=extractor_configuration(),
        sequence=4,
        created_at=at(4),
        message_cutoff_sequence=2,
        evidence_cutoff_sequence=3,
    )
    proposed = OntologyDimensionDefinition(
        dimension_id="community_voice",
        name="Community voice",
        definition="Preference for direct community influence on decisions.",
        interpretation="Higher values favor more direct community influence.",
    )
    proposal = OntologyDimensionProposal(
        proposal_id="readout_proposal",
        context_id=context.context_id,
        context_sha256=content_sha256(context),
        session_id=ledger.session_id,
        sequence=5,
        created_at=at(5),
        source_message_ids=["message_one"],
        proposed_dimension=proposed,
        supporting_evidence_event_ids=["evidence_one"],
        extractor_confidence=0.8,
    )
    decision = OntologyProposalDecision(
        decision_id="readout_decision",
        proposal_id=proposal.proposal_id,
        decision=OntologyProposalDecisionKind.ADMIT_NEW,
        admitted_dimension=proposed,
        session_id=ledger.session_id,
        sequence=6,
        created_at=at(6),
    )
    return expansion.model_copy(
        update={
            "contexts": [context],
            "proposals": [proposal],
            "decisions": [decision],
        }
    )


def build_direct(
    *,
    condition: EvidenceCondition = EvidenceCondition.COMBINED,
    selected_executor: LLMReadoutExecutor,
    measure_index: int = 0,
):
    return build_direct_llm_prediction_snapshot(
        snapshot_id=f"direct_snapshot_{measure_index}_{condition.value}",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[measure_index],
        presentation=presentation(measure_index),
        evidence_ledger=evidence_ledger(),
        configuration=configuration("direct_llm_control", condition),
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=3,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
    )


def test_direct_llm_binds_exact_inputs_caches_and_rebuilds() -> None:
    backend, selected_executor = executor()
    snapshot = build_direct(selected_executor=selected_executor)
    repeated = build_direct(selected_executor=selected_executor)

    assert repeated == snapshot
    assert backend.call_count == 1
    request = backend.requests[0]
    assert request.readout_kind == "direct_llm"
    assert request.posterior is None
    assert request.target_packet_visible is True
    assert request.target_response_visible is False
    assert snapshot.provider_request_sha256 == content_sha256(request)
    assert [item.evidence_event_id for item in request.eligible_evidence] == [
        "evidence_one"
    ]
    assert [item.message_id for item in request.conversation_messages] == [
        "message_one",
        "message_two",
    ]
    assert snapshot.input_binding.preference_state_sha256 is None
    assert snapshot.supporting_evidence_event_ids == ["evidence_one"]

    tampered_request = request.model_copy(
        update={"model_input_sha256": "0" * 64}
    )
    with pytest.raises(ValueError, match="model input hash"):
        selected_executor.run(tampered_request)

    validate_llm_prediction_snapshot(
        snapshot,
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=presentation(),
        evidence_ledger=evidence_ledger(),
        configuration=configuration(
            "direct_llm_control",
            EvidenceCondition.COMBINED,
        ),
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
    )
    assert backend.call_count == 1

    empty_backend, empty_executor = executor()
    with pytest.raises(ValueError, match="existing cached response"):
        validate_llm_prediction_snapshot(
            snapshot,
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=presentation(),
            evidence_ledger=evidence_ledger(),
            configuration=configuration(
                "direct_llm_control",
                EvidenceCondition.COMBINED,
            ),
            readout_policy=readout_policy(),
            provider_model=provider_artifact(),
            prompt=prompt_artifact(),
            executor=empty_executor,
        )
    assert empty_backend.call_count == 0

    forged = snapshot.model_copy(update={"settled_probability": 0.0})
    with pytest.raises(ValueError, match="does not reproduce"):
        validate_llm_prediction_snapshot(
            forged,
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=presentation(),
            evidence_ledger=evidence_ledger(),
            configuration=configuration(
                "direct_llm_control",
                EvidenceCondition.COMBINED,
            ),
            readout_policy=readout_policy(),
            provider_model=provider_artifact(),
            prompt=prompt_artifact(),
            executor=selected_executor,
        )


def test_evidence_conditions_control_the_exact_provider_surface() -> None:
    observed = {}
    for condition in EvidenceCondition:
        backend, selected_executor = executor()
        build_direct(condition=condition, selected_executor=selected_executor)
        observed[condition] = backend.requests[0]

    assert observed[EvidenceCondition.STRUCTURED_ONLY].eligible_evidence
    assert not observed[EvidenceCondition.STRUCTURED_ONLY].conversation_messages
    assert not observed[EvidenceCondition.CONVERSATION_ONLY].eligible_evidence
    assert observed[EvidenceCondition.CONVERSATION_ONLY].conversation_messages
    assert observed[EvidenceCondition.COMBINED].eligible_evidence
    assert observed[EvidenceCondition.COMBINED].conversation_messages


def test_fixed_and_empty_expanding_hybrids_share_one_model_input_and_output() -> None:
    ledger = evidence_ledger()
    backend, selected_executor = executor()
    fixed = build_hybrid_prediction_snapshot(
        snapshot_id="hybrid_fixed_snapshot",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=presentation(),
        evidence_ledger=ledger,
        configuration=configuration(
            "hybrid_fixed_ontology",
            EvidenceCondition.COMBINED,
        ),
        model_artifact=model_artifact(),
        semantic_map=SEMANTIC_MAP,
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=3,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
    )
    expanding = build_hybrid_prediction_snapshot(
        snapshot_id="hybrid_expanding_snapshot",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=presentation(),
        evidence_ledger=ledger,
        configuration=configuration(
            "hybrid_expanding_ontology",
            EvidenceCondition.COMBINED,
        ),
        model_artifact=model_artifact(),
        semantic_map=SEMANTIC_MAP,
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=3,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
        expansion_ledger=expansion_ledger(ledger),
    )

    assert backend.call_count == 1
    assert fixed.input_binding.model_input_sha256 == (
        expanding.input_binding.model_input_sha256
    )
    assert fixed.input_binding.active_ontology_sha256 == (
        expanding.input_binding.active_ontology_sha256
    )
    assert fixed.option_probabilities == expanding.option_probabilities
    assert fixed.ballot_prediction == expanding.ballot_prediction
    assert (
        fixed.input_binding.ontology_snapshot_sha256
        != expanding.input_binding.ontology_snapshot_sha256
    )
    posterior = backend.requests[0].posterior
    assert posterior is not None
    assert len(posterior.pairwise_summaries) == 1
    assert posterior.pairwise_summaries[0].difference_standard_deviation > 0.0


def test_direct_and_both_hybrids_validate_together_in_a_phase4_run() -> None:
    ledger = evidence_ledger()
    target = presentation()
    expansion = expansion_ledger(ledger)
    direct_configuration = configuration(
        "direct_llm_control",
        EvidenceCondition.COMBINED,
    )
    fixed_configuration = configuration(
        "hybrid_fixed_ontology",
        EvidenceCondition.COMBINED,
    )
    expanding_configuration = configuration(
        "hybrid_expanding_ontology",
        EvidenceCondition.COMBINED,
    )
    _, selected_executor = executor()
    direct = build_direct(selected_executor=selected_executor)
    fixed = build_hybrid_prediction_snapshot(
        snapshot_id="run_hybrid_fixed_snapshot",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=target,
        evidence_ledger=ledger,
        configuration=fixed_configuration,
        model_artifact=model_artifact(),
        semantic_map=SEMANTIC_MAP,
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=3,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
    )
    expanding = build_hybrid_prediction_snapshot(
        snapshot_id="run_hybrid_expanding_snapshot",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=target,
        evidence_ledger=ledger,
        configuration=expanding_configuration,
        model_artifact=model_artifact(),
        semantic_map=SEMANTIC_MAP,
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=3,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
        expansion_ledger=expansion,
    )
    run = Phase4EvaluationRun(
        run_id="phase4_llm_integration_run",
        fixture_id=FIXTURE.fixture_id,
        fixture_version=FIXTURE.fixture_version,
        fixture_sha256=content_sha256(FIXTURE),
        phase4_protocol_id=PROTOCOL.protocol_id,
        phase4_protocol_version=PROTOCOL.protocol_version,
        phase4_protocol_sha256=content_sha256(PROTOCOL),
        session_id=ledger.session_id,
        created_at=NOW,
        evidence_ledger=ledger,
        expanding_ontology_ledgers=[expansion],
        model_configurations=[
            direct_configuration,
            fixed_configuration,
            expanding_configuration,
        ],
        measure_presentations=[target],
        prediction_snapshots=[direct, fixed, expanding],
    )

    validate_phase4_evaluation_run(run, FIXTURE, PROTOCOL)
    assert fixed.input_binding.model_input_sha256 == (
        expanding.input_binding.model_input_sha256
    )
    assert fixed.option_probabilities == expanding.option_probabilities


def test_active_admitted_dimension_enters_expanding_provider_input_hash() -> None:
    ledger = evidence_ledger()
    backend, selected_executor = executor()
    snapshot = build_hybrid_prediction_snapshot(
        snapshot_id="hybrid_admitted_snapshot",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=presentation(),
        evidence_ledger=ledger,
        configuration=configuration(
            "hybrid_expanding_ontology",
            EvidenceCondition.COMBINED,
        ),
        model_artifact=model_artifact(),
        semantic_map=SEMANTIC_MAP,
        readout_policy=readout_policy(),
        provider_model=provider_artifact(),
        prompt=prompt_artifact(),
        executor=selected_executor,
        evidence_cutoff_sequence=6,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
        expansion_ledger=expansion_with_admission(ledger),
    )

    posterior = backend.requests[0].posterior
    assert posterior is not None
    assert [
        item.dimension.dimension_id
        for item in posterior.active_expanded_dimensions
    ] == ["community_voice"]
    fixed_hash = active_ontology_input_sha256(ledger.ontology.item_ids)
    assert snapshot.input_binding.active_ontology_sha256 != fixed_hash
    assert posterior.active_ontology_sha256 == (
        snapshot.input_binding.active_ontology_sha256
    )


class IneligibleCitationBackend(DeterministicLLMReadoutBackend):
    def predict(self, request):
        response = super().predict(request)
        return response.model_copy(
            update={"supporting_evidence_event_ids": ["invented_evidence"]}
        )


def test_provider_output_cannot_cite_or_predict_outside_bound_input() -> None:
    backend = IneligibleCitationBackend(
        provider_artifact(),
        prompt_artifact(),
    )
    _, selected_executor = executor(backend=backend)

    with pytest.raises(ValueError, match="ineligible evidence"):
        build_direct(selected_executor=selected_executor)


def test_private_json_cache_omits_provider_request_text(tmp_path: Path) -> None:
    cache = JsonDirectoryLLMReadoutCache(tmp_path / "llm_cache")
    first_backend, first_executor = executor(cache=cache)
    first = build_direct(selected_executor=first_executor)
    assert first_backend.call_count == 1

    second_backend, second_executor = executor(cache=cache)
    second = build_direct(selected_executor=second_executor)
    assert second == first
    assert second_backend.call_count == 0
    cache_files = list((tmp_path / "llm_cache").glob("*.json"))
    assert len(cache_files) == 1
    cache_text = cache_files[0].read_text(encoding="utf-8")
    assert "A planted private preference statement." not in cache_text


def test_all_ballot_formats_reuse_the_common_action_policy() -> None:
    backend, selected_executor = executor()
    for measure_index, measure in enumerate(FIXTURE.measures):
        snapshot = build_direct(
            selected_executor=selected_executor,
            measure_index=measure_index,
        )
        validate_prediction_v2_for_measure(snapshot, measure)
        assert snapshot.ballot_prediction.ballot_type is measure.ballot_type
    assert backend.call_count == len(FIXTURE.measures)


def test_configuration_and_backend_artifact_drift_fail_closed() -> None:
    backend, selected_executor = executor()
    drifted = configuration(
        "direct_llm_control",
        EvidenceCondition.COMBINED,
    ).model_copy(
        update={
            "prompt": llm_prompt_artifact_reference(
                prompt_artifact().model_copy(
                    update={"system_instruction": "Different prompt text."}
                )
            )
        }
    )
    with pytest.raises(ValueError, match="exact prompt"):
        build_direct_llm_prediction_snapshot(
            snapshot_id="drifted",
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=presentation(),
            evidence_ledger=evidence_ledger(),
            configuration=drifted,
            readout_policy=readout_policy(),
            provider_model=provider_artifact(),
            prompt=prompt_artifact(),
            executor=selected_executor,
            evidence_cutoff_sequence=3,
            checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
            wave_index=0,
            created_at=at(11),
        )
    assert backend.call_count == 0
