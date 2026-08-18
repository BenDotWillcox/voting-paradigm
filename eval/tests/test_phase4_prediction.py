from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from preferences.types import EvidenceSource

from eval.contracts import (
    BallotType,
    EvaluationRun,
    MeasurePresentation,
    MeasureVersion,
    ParticipantResponse,
    PredictionSnapshot,
    PresentationKind,
    RankingTier,
    ResponseStability,
    ResponseState,
)
from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_evidence import (
    ConversationEvidenceMessage,
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    FixedOntologyReference,
    StructuredPreferenceEvidenceEvent,
    conversation_messages_sha256,
    materialize_evidence,
)
from eval.phase4_interviewer import ConversationRole
from eval.phase4_ontology import (
    ExpandingOntologyLedger,
    ExpandingOntologySeed,
    OntologyDimensionDefinition,
    OntologyExpansionPolicy,
    active_dimension_states,
    evidence_ledger_identity_sha256,
    replay_expanding_ontology,
)
from eval.phase4_prediction import (
    ApprovalPrediction,
    ComponentArtifactReference,
    Phase4EvaluationRun,
    Phase4ModelConfiguration,
    PredictionCheckpoint,
    PredictionInputBinding,
    PredictionSnapshotV2,
    PredictionUnsupportedAssumption,
    QuadraticPrediction,
    RankedPrediction,
    ScorePrediction,
    SingleChoicePrediction,
    as_v1_execution_run,
    assert_v1_record_versions_unchanged,
    materialized_evidence_sha256,
    prediction_model_input_sha256,
    validate_phase4_evaluation_run,
    validate_prediction_v2_for_measure,
)
from eval.phase4_protocol import EvidenceCondition, load_phase4_protocol

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / "eval/fixtures/preference_eval_dev_v1.json")
PROTOCOL = load_phase4_protocol(
    ROOT / "eval/fixtures/preference_eval_phase4_protocol_v1.json"
)
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


def artifact(name: str) -> ComponentArtifactReference:
    return ComponentArtifactReference(
        artifact_id=name,
        artifact_version="development-v1",
        artifact_sha256=content_sha256({"artifact": name}),
    )


def fixed_ontology() -> FixedOntologyReference:
    item_ids = ["autonomy", "collective_welfare"]
    return FixedOntologyReference(
        ontology_id="civic_values",
        ontology_version=1,
        item_ids=item_ids,
        item_ids_sha256=content_sha256(item_ids),
    )


def structured_event(
    *,
    event_id: str = "evidence_one",
    sequence: int = 1,
    created_at: datetime | None = None,
) -> StructuredPreferenceEvidenceEvent:
    return StructuredPreferenceEvidenceEvent(
        evidence_event_id=event_id,
        session_id="session_one",
        sequence=sequence,
        created_at=created_at or at(sequence),
        source=EvidenceSource.SLIDER,
        claim=FixedOntologyClaim(
            claim_text="The participant confirmed an autonomy preference.",
            item_a="autonomy",
            item_b="collective_welfare",
            value=2.0,
        ),
        question_id="structured_question",
        response_id="structured_response",
    )


def evidence_ledger(
    *,
    event: StructuredPreferenceEvidenceEvent | None = None,
    messages: list[ConversationEvidenceMessage] | None = None,
) -> FixedOntologyEvidenceLedger:
    return FixedOntologyEvidenceLedger(
        ledger_id="evidence_ledger_one",
        session_id="session_one",
        ontology=fixed_ontology(),
        messages=messages or [],
        structured_evidence=[event or structured_event()],
        created_at=NOW,
    )


def expansion_ledger(
    evidence: FixedOntologyEvidenceLedger,
    *,
    condition: EvidenceCondition = EvidenceCondition.COMBINED,
) -> ExpandingOntologyLedger:
    dimensions = [
        OntologyDimensionDefinition(
            dimension_id=item_id,
            name=item_id.replace("_", " ").title(),
            definition=f"Preference concerning {item_id}.",
            interpretation=f"Higher values favor {item_id}.",
        )
        for item_id in evidence.ontology.item_ids
    ]
    seed = ExpandingOntologySeed(
        ontology_id=evidence.ontology.ontology_id,
        seed_version=evidence.ontology.ontology_version,
        dimensions=dimensions,
        dimensions_sha256=content_sha256(
            [item.model_dump(mode="json") for item in dimensions]
        ),
    )
    policy = OntologyExpansionPolicy(
        policy_id="ontology_policy_test",
        policy_version=1,
        admission_confirmation_support_weight=0.5,
        evidence_lineage_support_weight=1.0,
        full_weight_support_score=1.5,
        prune_max_support_score=0.5,
        prune_min_idle_sequence_gap=3,
    )
    return ExpandingOntologyLedger(
        ledger_id=f"expansion_{condition.value}",
        session_id=evidence.session_id,
        evidence_condition=condition,
        evidence_ledger_id=evidence.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            evidence
        ),
        seed=seed,
        policy=policy,
        created_at=NOW,
    )


def configuration(
    arm_id: str = "gaussian_linear_fixed",
    condition: EvidenceCondition | None = EvidenceCondition.STRUCTURED_ONLY,
) -> Phase4ModelConfiguration:
    explicit = arm_id in {
        "gaussian_linear_fixed",
        "bradley_terry_fixed",
        "hybrid_fixed_ontology",
        "hybrid_expanding_ontology",
    }
    mapped = arm_id in {
        "gaussian_linear_fixed",
        "bradley_terry_fixed",
        "hybrid_fixed_ontology",
        "hybrid_expanding_ontology",
    }
    llm = arm_id in {
        "direct_llm_control",
        "hybrid_fixed_ontology",
        "hybrid_expanding_ontology",
    }
    return Phase4ModelConfiguration(
        configuration_id=f"config_{arm_id}_{condition.value if condition else 'none'}",
        arm_id=arm_id,
        evidence_condition=condition,
        preference_model=artifact(f"{arm_id}_model") if explicit else None,
        semantic_mapper=artifact(f"{arm_id}_mapper") if mapped else None,
        prediction_readout=artifact(f"{arm_id}_readout"),
        provider_model=artifact(f"{arm_id}_provider") if llm else None,
        prompt=artifact(f"{arm_id}_prompt") if llm else None,
        seed=17,
    )


def presentation(
    measure: MeasureVersion,
    *,
    presented_at: datetime | None = None,
) -> MeasurePresentation:
    return MeasurePresentation(
        presentation_id=f"presentation_{measure.measure_id}",
        session_id="session_one",
        measure_id=measure.measure_id,
        measure_version=measure.version,
        packet_version=measure.packet.version,
        kind=PresentationKind.INITIAL,
        order_seed=31,
        presented_at=presented_at or at(10),
    )


def response(
    measure: MeasureVersion,
    target: MeasurePresentation,
) -> ParticipantResponse:
    return ParticipantResponse(
        response_id=f"response_{measure.measure_id}",
        session_id="session_one",
        presentation_id=target.presentation_id,
        measure_id=measure.measure_id,
        measure_version=measure.version,
        packet_version=measure.packet.version,
        sequence=100,
        response_state=ResponseState.CHOICE,
        selected_option_id=measure.options[0].option_id,
        confidence=0.8,
        preference_strength=7,
        stability=ResponseStability.STABLE,
        created_at=at(20),
    )


def ballot_prediction(measure: MeasureVersion):
    option_ids = [item.option_id for item in measure.options]
    if measure.ballot_type is BallotType.SINGLE_CHOICE:
        return SingleChoicePrediction(selected_option_id=option_ids[0])
    if measure.ballot_type is BallotType.RANKED:
        return RankedPrediction(
            ranking_tiers=[RankingTier(option_ids=[item]) for item in option_ids]
        )
    if measure.ballot_type is BallotType.APPROVAL:
        return ApprovalPrediction(approved_option_ids=[option_ids[0]])
    if measure.ballot_type is BallotType.SCORE:
        return ScorePrediction(
            option_scores={
                option_id: 10 if index == 0 else 0
                for index, option_id in enumerate(option_ids)
            }
        )
    return QuadraticPrediction(
        quadratic_allocations={
            option_id: 2 if index == 0 else 0
            for index, option_id in enumerate(option_ids)
        }
    )


def option_probabilities(measure: MeasureVersion) -> dict[str, float]:
    option_ids = [item.option_id for item in measure.options]
    remainder = 0.4 / (len(option_ids) - 1)
    return {
        option_id: 0.6 if index == 0 else remainder
        for index, option_id in enumerate(option_ids)
    }


def input_binding(
    *,
    measure: MeasureVersion,
    target: MeasurePresentation,
    evidence: FixedOntologyEvidenceLedger,
    config: Phase4ModelConfiguration,
    cutoff: int = 1,
    expansion: ExpandingOntologyLedger | None = None,
) -> PredictionInputBinding:
    condition = config.evidence_condition
    explicit = config.preference_model is not None
    if condition is None:
        eligible = []
        messages = []
    else:
        eligible = materialize_evidence(
            evidence,
            condition=condition,
            cutoff_sequence=cutoff,
        )
        messages = (
            []
            if condition is EvidenceCondition.STRUCTURED_ONLY
            else [item for item in evidence.messages if item.sequence <= cutoff]
        )
    if explicit and expansion is not None:
        ontology = replay_expanding_ontology(
            expansion,
            evidence,
            cutoff_sequence=cutoff,
        )
        ontology_hash = content_sha256(ontology)
        active_hash = content_sha256(
            sorted(
                item.dimension.dimension_id
                for item in active_dimension_states(ontology)
            )
        )
    elif explicit:
        ontology_hash = content_sha256(evidence.ontology)
        active_hash = content_sha256(sorted(evidence.ontology.item_ids))
    else:
        ontology_hash = None
        active_hash = None
    binding = PredictionInputBinding(
        target_presentation_id=target.presentation_id,
        target_measure_id=measure.measure_id,
        target_measure_version=measure.version,
        target_packet_version=measure.packet.version,
        target_packet_sha256=content_sha256(measure.packet),
        evidence_ledger_id=evidence.ledger_id,
        evidence_ledger_identity_sha256=evidence_ledger_identity_sha256(
            evidence
        ),
        evidence_condition=condition,
        evidence_cutoff_sequence=cutoff,
        eligible_evidence_event_ids=[item.event_id for item in eligible],
        eligible_evidence_sha256=materialized_evidence_sha256(eligible),
        conversation_message_ids=[item.message_id for item in messages],
        conversation_messages_sha256=(
            conversation_messages_sha256(messages)
            if messages
            else content_sha256([])
        ),
        preference_state_sha256=(
            content_sha256({"state": "development"}) if explicit else None
        ),
        ontology_snapshot_sha256=ontology_hash,
        active_ontology_sha256=active_hash,
        model_input_sha256="0" * 64,
    )
    return binding.model_copy(
        update={
            "model_input_sha256": prediction_model_input_sha256(
                binding,
                config,
            )
        }
    )


def snapshot(
    *,
    measure: MeasureVersion,
    target: MeasurePresentation,
    evidence: FixedOntologyEvidenceLedger,
    config: Phase4ModelConfiguration,
    cutoff: int = 1,
    expansion: ExpandingOntologyLedger | None = None,
    created_at: datetime | None = None,
) -> PredictionSnapshotV2:
    binding = input_binding(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=cutoff,
        expansion=expansion,
    )
    probabilities = option_probabilities(measure)
    support_ids = (
        binding.eligible_evidence_event_ids[:1]
        if config.provider_model is not None
        else []
    )
    return PredictionSnapshotV2(
        snapshot_id=f"snapshot_{config.configuration_id}_{cutoff}",
        session_id="session_one",
        model_configuration_id=config.configuration_id,
        model_configuration_sha256=content_sha256(config),
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        input_binding=binding,
        option_probabilities=probabilities,
        top_option_id=measure.options[0].option_id,
        confidence=0.6,
        settled_probability=0.75,
        ballot_prediction=ballot_prediction(measure),
        provider_request_sha256=(
            content_sha256(
                {
                    "configuration_id": config.configuration_id,
                    "cutoff": cutoff,
                }
            )
            if config.provider_model is not None
            else None
        ),
        supporting_evidence_event_ids=support_ids,
        created_at=created_at or at(11),
    )


def run(
    *,
    evidence: FixedOntologyEvidenceLedger | None = None,
    configs: list[Phase4ModelConfiguration] | None = None,
    presentations: list[MeasurePresentation] | None = None,
    snapshots: list[PredictionSnapshotV2] | None = None,
    responses: list[ParticipantResponse] | None = None,
    expansions: list[ExpandingOntologyLedger] | None = None,
) -> Phase4EvaluationRun:
    bound_evidence = evidence or evidence_ledger()
    return Phase4EvaluationRun(
        run_id="phase4_run_one",
        fixture_id=FIXTURE.fixture_id,
        fixture_version=FIXTURE.fixture_version,
        fixture_sha256=content_sha256(FIXTURE),
        phase4_protocol_id=PROTOCOL.protocol_id,
        phase4_protocol_version=PROTOCOL.protocol_version,
        phase4_protocol_sha256=content_sha256(PROTOCOL),
        session_id="session_one",
        created_at=NOW,
        evidence_ledger=bound_evidence,
        expanding_ontology_ledgers=expansions or [],
        model_configurations=configs or [],
        measure_presentations=presentations or [],
        prediction_snapshots=snapshots or [],
        participant_responses=responses or [],
    )


def test_conforming_v2_run_round_trips_and_validates():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration()
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
    )
    built = run(
        evidence=evidence,
        configs=[config],
        presentations=[target],
        snapshots=[prediction],
        responses=[response(measure, target)],
    )

    restored = Phase4EvaluationRun.model_validate(
        built.model_dump(mode="json")
    )
    validate_phase4_evaluation_run(restored, FIXTURE, PROTOCOL)

    assert restored == built
    assert restored.record_version == "evaluation_run.v2"
    assert restored.prediction_snapshots[0].record_version == (
        "prediction_snapshot.v2"
    )


@pytest.mark.parametrize(
    "arm_id,condition",
    [
        ("uniform_prior", None),
        ("gaussian_linear_fixed", EvidenceCondition.STRUCTURED_ONLY),
        ("bradley_terry_fixed", EvidenceCondition.STRUCTURED_ONLY),
        ("direct_llm_control", EvidenceCondition.COMBINED),
        ("hybrid_fixed_ontology", EvidenceCondition.CONVERSATION_ONLY),
        ("hybrid_expanding_ontology", EvidenceCondition.COMBINED),
    ],
)
def test_all_frozen_model_arm_configuration_shapes_validate(
    arm_id: str,
    condition: EvidenceCondition | None,
):
    built = run(configs=[configuration(arm_id, condition)])
    validate_phase4_evaluation_run(built, FIXTURE, PROTOCOL)


def test_configuration_rejects_uniform_evidence_condition():
    bad = configuration("uniform_prior", EvidenceCondition.STRUCTURED_ONLY)
    with pytest.raises(ValueError, match="uniform-prior"):
        validate_phase4_evaluation_run(run(configs=[bad]), FIXTURE, PROTOCOL)


def test_configuration_rejects_missing_components_for_an_arm():
    direct = configuration("direct_llm_control", EvidenceCondition.COMBINED)
    missing_provider = direct.model_copy(
        update={"provider_model": None, "prompt": None}
    )
    with pytest.raises(ValueError, match="requires provider_model"):
        validate_phase4_evaluation_run(
            run(configs=[missing_provider]), FIXTURE, PROTOCOL
        )

    hybrid = configuration("hybrid_fixed_ontology", EvidenceCondition.COMBINED)
    missing_mapper = hybrid.model_copy(update={"semantic_mapper": None})
    with pytest.raises(ValueError, match="requires semantic_mapper"):
        validate_phase4_evaluation_run(
            run(configs=[missing_mapper]), FIXTURE, PROTOCOL
        )


@pytest.mark.parametrize("measure", FIXTURE.measures)
def test_every_ballot_type_emits_probabilities_and_a_separate_valid_action(
    measure: MeasureVersion,
):
    evidence = evidence_ledger()
    target = presentation(measure)
    config = configuration("uniform_prior", None)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=0,
    )

    validate_prediction_v2_for_measure(prediction, measure)
    assert sum(prediction.option_probabilities.values()) == pytest.approx(1.0)
    assert prediction.ballot_prediction.ballot_type is measure.ballot_type


def test_rich_ballot_payload_must_be_complete_and_top_option_coherent():
    ranked_measure = next(
        item for item in FIXTURE.measures if item.ballot_type is BallotType.RANKED
    )
    evidence = evidence_ledger()
    config = configuration("uniform_prior", None)
    target = presentation(ranked_measure)
    prediction = snapshot(
        measure=ranked_measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=0,
    )
    incomplete = RankedPrediction(
        ranking_tiers=[RankingTier(option_ids=[ranked_measure.options[0].option_id])]
    )
    with pytest.raises(ValueError, match="cover every option"):
        validate_prediction_v2_for_measure(
            prediction.model_copy(update={"ballot_prediction": incomplete}),
            ranked_measure,
        )

    approval_measure = next(
        item for item in FIXTURE.measures if item.ballot_type is BallotType.APPROVAL
    )
    target = presentation(approval_measure)
    approval_prediction = snapshot(
        measure=approval_measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=0,
    )
    missing_top = ApprovalPrediction(
        approved_option_ids=[approval_measure.options[1].option_id]
    )
    with pytest.raises(ValueError, match="approve the top option"):
        validate_prediction_v2_for_measure(
            approval_prediction.model_copy(
                update={"ballot_prediction": missing_top}
            ),
            approval_measure,
        )


def test_quadratic_prediction_rejects_zero_and_over_budget_actions():
    measure = next(
        item for item in FIXTURE.measures if item.ballot_type is BallotType.QUADRATIC
    )
    option_ids = [item.option_id for item in measure.options]
    with pytest.raises(ValidationError, match="all-zero"):
        QuadraticPrediction(
            quadratic_allocations={option_id: 0 for option_id in option_ids}
        )

    evidence = evidence_ledger()
    config = configuration("uniform_prior", None)
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=0,
    )
    over_budget = QuadraticPrediction(
        quadratic_allocations={
            option_id: 11 if index == 0 else 0
            for index, option_id in enumerate(option_ids)
        }
    )
    with pytest.raises(ValueError, match="exceeds"):
        validate_prediction_v2_for_measure(
            prediction.model_copy(update={"ballot_prediction": over_budget}),
            measure,
        )


def test_snapshot_binds_exact_configuration_packet_and_evidence_view():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration()
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
    )

    wrong_configuration_hash = prediction.model_copy(
        update={"model_configuration_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError, match="configuration hash"):
        run(
            evidence=evidence,
            configs=[config],
            presentations=[target],
            snapshots=[wrong_configuration_hash],
        )

    wrong_packet = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={"target_packet_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="packet hash"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[wrong_packet],
            ),
            FIXTURE,
            PROTOCOL,
        )

    wrong_evidence = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={
                    "eligible_evidence_event_ids": ["invented_evidence"],
                    "eligible_evidence_sha256": content_sha256(
                        ["invented_evidence"]
                    ),
                }
            )
        }
    )
    with pytest.raises(ValueError, match="exact eligible evidence"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[wrong_evidence],
            ),
            FIXTURE,
            PROTOCOL,
        )

    wrong_model_input = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={"model_input_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="model input hash"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[wrong_model_input],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_uniform_prior_cannot_bind_participant_evidence():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration("uniform_prior", None)
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=0,
    )
    contaminated = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={
                    "eligible_evidence_event_ids": ["evidence_one"],
                    "eligible_evidence_sha256": content_sha256(["evidence_one"]),
                }
            )
        }
    )
    with pytest.raises(ValueError, match="cannot bind participant evidence"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[contaminated],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_post_exposure_evidence_is_rejected_even_before_target_response():
    measure = FIXTURE.measures[0]
    late_event = structured_event(created_at=at(12))
    evidence = evidence_ledger(event=late_event)
    config = configuration()
    target = presentation(measure, presented_at=at(10))
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        created_at=at(13),
    )
    with pytest.raises(ValueError, match="post-exposure event"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[prediction],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_conversation_condition_binds_the_exact_pre_exposure_prefix():
    measure = FIXTURE.measures[0]
    message = ConversationEvidenceMessage(
        message_id="message_one",
        session_id="session_one",
        sequence=2,
        created_at=at(2),
        role=ConversationRole.PARTICIPANT,
        content="Private participant statement.",
    )
    evidence = evidence_ledger(messages=[message])
    config = configuration("direct_llm_control", EvidenceCondition.COMBINED)
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        cutoff=2,
    )
    built = run(
        evidence=evidence,
        configs=[config],
        presentations=[target],
        snapshots=[prediction],
    )
    validate_phase4_evaluation_run(built, FIXTURE, PROTOCOL)

    omitted = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={
                    "conversation_message_ids": [],
                    "conversation_messages_sha256": content_sha256([]),
                }
            )
        }
    )
    with pytest.raises(ValueError, match="exact conversation prefix"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[omitted],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_llm_predictions_cite_evidence_and_keep_private_assumption_flags():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration("direct_llm_control", EvidenceCondition.STRUCTURED_ONLY)
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
    )
    unbound_request = prediction.model_copy(
        update={"provider_request_sha256": None}
    )
    with pytest.raises(ValueError, match="exact provider request"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[unbound_request],
            ),
            FIXTURE,
            PROTOCOL,
        )
    uncited = prediction.model_copy(update={"supporting_evidence_event_ids": []})
    with pytest.raises(ValueError, match="must cite"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[uncited],
            ),
            FIXTURE,
            PROTOCOL,
        )

    assumption = PredictionUnsupportedAssumption(
        assumption_id="missing_context",
        description="The available evidence does not settle one premise.",
        affected_option_ids=[measure.options[0].option_id],
    )
    flagged = prediction.model_copy(update={"unsupported_assumptions": [assumption]})
    validate_phase4_evaluation_run(
        run(
            evidence=evidence,
            configs=[config],
            presentations=[target],
            snapshots=[flagged],
        ),
        FIXTURE,
        PROTOCOL,
    )


def test_non_llm_prediction_cannot_emit_llm_assumption_flags():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration()
    target = presentation(measure)
    assumption = PredictionUnsupportedAssumption(
        assumption_id="invented_flag",
        description="This flag does not belong on an authored readout.",
        affected_option_ids=[measure.options[0].option_id],
    )
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
    ).model_copy(update={"unsupported_assumptions": [assumption]})
    with pytest.raises(ValueError, match="non-LLM"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[prediction],
            ),
            FIXTURE,
            PROTOCOL,
        )

    provider_bound = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
    ).model_copy(
        update={"provider_request_sha256": content_sha256("not an LLM")}
    )
    with pytest.raises(ValueError, match="non-LLM prediction"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[provider_bound],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_comparison_snapshots_must_share_cutoff_and_same_condition_view():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    gaussian = configuration()
    direct = configuration(
        "direct_llm_control", EvidenceCondition.STRUCTURED_ONLY
    )
    target = presentation(measure)
    gaussian_prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=gaussian,
        cutoff=1,
    )
    direct_prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=direct,
        cutoff=0,
    )
    with pytest.raises(ValueError, match="one evidence cutoff"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[gaussian, direct],
                presentations=[target],
                snapshots=[gaussian_prediction, direct_prediction],
            ),
            FIXTURE,
            PROTOCOL,
        )

    same_cutoff = direct_prediction.model_copy(
        update={
            "snapshot_id": "snapshot_direct_same_cutoff",
            "input_binding": direct_prediction.input_binding.model_copy(
                update={"evidence_cutoff_sequence": 1}
            ),
        }
    )
    with pytest.raises(ValueError, match="exact eligible evidence"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[gaussian, direct],
                presentations=[target],
                snapshots=[gaussian_prediction, same_cutoff],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_expanding_arm_binds_exact_full_and_active_ontology_snapshots():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    expansion = expansion_ledger(evidence)
    config = configuration(
        "hybrid_expanding_ontology", EvidenceCondition.COMBINED
    )
    target = presentation(measure)
    prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        expansion=expansion,
    )
    built = run(
        evidence=evidence,
        configs=[config],
        presentations=[target],
        snapshots=[prediction],
        expansions=[expansion],
    )
    validate_phase4_evaluation_run(built, FIXTURE, PROTOCOL)

    tampered = prediction.model_copy(
        update={
            "input_binding": prediction.input_binding.model_copy(
                update={"active_ontology_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="active ontology"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[config],
                presentations=[target],
                snapshots=[tampered],
                expansions=[expansion],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_fixed_and_expanding_same_stack_cannot_diverge_on_identical_inputs():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    expansion = expansion_ledger(evidence)
    fixed = configuration("hybrid_fixed_ontology", EvidenceCondition.COMBINED)
    expanding = configuration(
        "hybrid_expanding_ontology", EvidenceCondition.COMBINED
    ).model_copy(
        update={
            "preference_model": fixed.preference_model,
            "semantic_mapper": fixed.semantic_mapper,
            "prediction_readout": fixed.prediction_readout,
            "provider_model": fixed.provider_model,
            "prompt": fixed.prompt,
            "seed": fixed.seed,
        }
    )
    target = presentation(measure)
    fixed_prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=fixed,
    )
    expanding_prediction = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=expanding,
        expansion=expansion,
    )
    conforming = run(
        evidence=evidence,
        configs=[fixed, expanding],
        presentations=[target],
        snapshots=[fixed_prediction, expanding_prediction],
        expansions=[expansion],
    )
    validate_phase4_evaluation_run(conforming, FIXTURE, PROTOCOL)

    one_ulp_payload = expanding_prediction.model_dump(mode="python")
    one_ulp_option_ids = list(one_ulp_payload["option_probabilities"])
    first_option_id, second_option_id = one_ulp_option_ids
    first_probability = one_ulp_payload["option_probabilities"][
        first_option_id
    ]
    next_probability = math.nextafter(first_probability, 1.0)
    perturbation = next_probability - first_probability
    one_ulp_payload["option_probabilities"][first_option_id] = next_probability
    one_ulp_payload["option_probabilities"][second_option_id] -= perturbation
    one_ulp_payload["confidence"] = next_probability
    one_ulp_prediction = PredictionSnapshotV2.model_validate(one_ulp_payload)
    validate_phase4_evaluation_run(
        run(
            evidence=evidence,
            configs=[fixed, expanding],
            presentations=[target],
            snapshots=[fixed_prediction, one_ulp_prediction],
            expansions=[expansion],
        ),
        FIXTURE,
        PROTOCOL,
    )

    payload = expanding_prediction.model_dump(mode="python")
    option_ids = list(payload["option_probabilities"])
    payload["option_probabilities"] = {
        option_id: 0.7 if index == 0 else 0.3 / (len(option_ids) - 1)
        for index, option_id in enumerate(option_ids)
    }
    payload["confidence"] = 0.7
    divergent = PredictionSnapshotV2.model_validate(payload)
    with pytest.raises(ValueError, match="diverge on identical active inputs"):
        validate_phase4_evaluation_run(
            run(
                evidence=evidence,
                configs=[fixed, expanding],
                presentations=[target],
                snapshots=[fixed_prediction, divergent],
                expansions=[expansion],
            ),
            FIXTURE,
            PROTOCOL,
        )


def test_snapshot_must_precede_target_response():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    config = configuration()
    target = presentation(measure)
    late = snapshot(
        measure=measure,
        target=target,
        evidence=evidence,
        config=config,
        created_at=at(20),
    )
    with pytest.raises(ValidationError, match="must precede target response"):
        run(
            evidence=evidence,
            configs=[config],
            presentations=[target],
            snapshots=[late],
            responses=[response(measure, target)],
        )


def test_v2_projects_onto_v1_execution_without_touching_v1_contracts():
    measure = FIXTURE.measures[0]
    evidence = evidence_ledger()
    target = presentation(measure)
    built = run(
        evidence=evidence,
        presentations=[target],
        responses=[response(measure, target)],
    )

    assert_v1_record_versions_unchanged()
    projection = as_v1_execution_run(built)

    assert isinstance(projection, EvaluationRun)
    assert projection.record_version == "evaluation_run.v1"
    assert projection.prediction_snapshots == []
    assert PredictionSnapshot.model_fields["record_version"].default == (
        "prediction_snapshot.v1"
    )
