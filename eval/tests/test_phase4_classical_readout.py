from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from preferences.types import EvidenceSource

from eval.contracts import (
    BallotType,
    MeasurePresentation,
    PresentationKind,
)
from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_classical_readout import (
    BradleyTerryModelArtifact,
    ClassicalReadoutPolicy,
    GaussianLinearModelArtifact,
    ballot_prediction_from_probabilities,
    build_classical_prediction_snapshot,
    classical_model_artifact_reference,
    classical_readout_artifact_reference,
    validate_classical_prediction_snapshot,
)
from eval.phase4_evidence import (
    FixedOntologyClaim,
    FixedOntologyEvidenceLedger,
    FixedOntologyReference,
    StructuredPreferenceEvidenceEvent,
)
from eval.phase4_ontology import evidence_ledger_identity_sha256
from eval.phase4_prediction import (
    ApprovalPrediction,
    Phase4EvaluationRun,
    Phase4ModelConfiguration,
    PredictionCheckpoint,
    QuadraticPrediction,
    RankedPrediction,
    ScorePrediction,
    SingleChoicePrediction,
    TOP_OPTION_ABS_TOLERANCE,
    prediction_model_input_sha256,
    validate_phase4_evaluation_run,
)
from eval.phase4_protocol import EvidenceCondition, load_phase4_protocol
from eval.phase4_semantic import (
    AuthoredMeasureSemanticMapping,
    AuthoredOptionStance,
    AuthoredSemanticMapBundle,
    authored_semantic_map_summary,
    load_authored_semantic_map,
    semantic_map_artifact_reference,
    validate_authored_semantic_map,
)
from eval.validate_phase4_semantic_map import main as validate_semantic_map_main

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / "eval/fixtures/preference_eval_dev_v1.json")
PROTOCOL = load_phase4_protocol(
    ROOT / "eval/fixtures/preference_eval_phase4_protocol_v1.json"
)
DEV_SEMANTIC_MAP_PATH = (
    ROOT / "eval/fixtures/preference_eval_dev_semantic_map_v1.json"
)
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


def ontology() -> FixedOntologyReference:
    item_ids = ["autonomy", "collective_welfare"]
    return FixedOntologyReference(
        ontology_id="classical_test_ontology",
        ontology_version=1,
        item_ids=item_ids,
        item_ids_sha256=content_sha256(item_ids),
    )


def ledger(
    *,
    include_evidence: bool = True,
    claim_value: float = 8.0,
) -> FixedOntologyEvidenceLedger:
    structured = []
    if include_evidence:
        structured.append(
            StructuredPreferenceEvidenceEvent(
                evidence_event_id="structured_preference_one",
                session_id="session_one",
                sequence=1,
                created_at=at(1),
                source=EvidenceSource.SLIDER,
                claim=FixedOntologyClaim(
                    claim_text="The participant favors autonomy in this tradeoff.",
                    item_a="autonomy",
                    item_b="collective_welfare",
                    value=claim_value,
                ),
                question_id="question_one",
                response_id="response_one",
            )
        )
    return FixedOntologyEvidenceLedger(
        ledger_id="classical_evidence_ledger",
        session_id="session_one",
        ontology=ontology(),
        structured_evidence=structured,
        created_at=NOW,
    )


def _centered_positions(option_count: int) -> list[float]:
    if option_count == 2:
        return [1.0, -1.0]
    denominator = option_count - 1
    return [
        (option_count - 1 - 2 * index) / denominator
        for index in range(option_count)
    ]


def semantic_map(*, scale: float = 1.0) -> AuthoredSemanticMapBundle:
    mappings = []
    for measure in FIXTURE.measures:
        positions = _centered_positions(len(measure.options))
        stances = []
        for option, position in zip(measure.options, positions, strict=True):
            scaled = scale * position
            weights = (
                {
                    "autonomy": scaled,
                    "collective_welfare": -scaled,
                }
                if scaled != 0.0
                else {}
            )
            stances.append(
                AuthoredOptionStance(
                    option_id=option.option_id,
                    dimension_weights=weights,
                )
            )
        mappings.append(
            AuthoredMeasureSemanticMapping(
                measure_id=measure.measure_id,
                measure_version=measure.version,
                packet_version=measure.packet.version,
                packet_sha256=content_sha256(measure.packet),
                option_stances=stances,
            )
        )
    return AuthoredSemanticMapBundle(
        mapper_id=f"development_semantic_map_{str(scale).replace('.', '_')}",
        mapper_version=1,
        development_only=True,
        fixture_id=FIXTURE.fixture_id,
        fixture_version=FIXTURE.fixture_version,
        fixture_sha256=content_sha256(FIXTURE),
        ontology=ontology(),
        author_system="codex-development-test",
        authored_at=NOW,
        mappings=mappings,
    )


def gaussian_artifact() -> GaussianLinearModelArtifact:
    return GaussianLinearModelArtifact(
        artifact_id="gaussian_linear_development",
        artifact_version=1,
    )


def bradley_terry_artifact() -> BradleyTerryModelArtifact:
    return BradleyTerryModelArtifact(
        artifact_id="bradley_terry_development",
        artifact_version=1,
    )


def readout_policy(
    *,
    comparison_tolerance: float = 1e-12,
) -> ClassicalReadoutPolicy:
    return ClassicalReadoutPolicy(
        artifact_id="classical_common_readout_development",
        artifact_version=1,
        action_policy={"comparison_tolerance": comparison_tolerance},
    )


def configuration(
    model_artifact: GaussianLinearModelArtifact | BradleyTerryModelArtifact,
    mapping: AuthoredSemanticMapBundle,
    policy: ClassicalReadoutPolicy | None = None,
) -> Phase4ModelConfiguration:
    bound_policy = policy or readout_policy()
    arm_id = (
        "gaussian_linear_fixed"
        if isinstance(model_artifact, GaussianLinearModelArtifact)
        else "bradley_terry_fixed"
    )
    return Phase4ModelConfiguration(
        configuration_id=f"config_{arm_id}_{mapping.mapper_id}",
        arm_id=arm_id,
        evidence_condition=EvidenceCondition.STRUCTURED_ONLY,
        preference_model=classical_model_artifact_reference(model_artifact),
        semantic_mapper=semantic_map_artifact_reference(mapping),
        prediction_readout=classical_readout_artifact_reference(
            bound_policy
        ),
        seed=17,
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
        order_seed=31,
        presented_at=at(10),
    )


def build_snapshot(
    *,
    measure_index: int = 0,
    model_artifact: (
        GaussianLinearModelArtifact | BradleyTerryModelArtifact | None
    ) = None,
    mapping: AuthoredSemanticMapBundle | None = None,
    evidence: FixedOntologyEvidenceLedger | None = None,
    policy: ClassicalReadoutPolicy | None = None,
    cutoff: int = 1,
):
    bound_model = model_artifact or gaussian_artifact()
    bound_mapping = mapping or semantic_map()
    bound_evidence = evidence or ledger()
    bound_policy = policy or readout_policy()
    target = presentation(measure_index)
    config = configuration(bound_model, bound_mapping, bound_policy)
    snapshot = build_classical_prediction_snapshot(
        snapshot_id=f"snapshot_{config.configuration_id}_{measure_index}",
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[measure_index],
        presentation=target,
        evidence_ledger=bound_evidence,
        configuration=config,
        model_artifact=bound_model,
        semantic_map=bound_mapping,
        readout_policy=bound_policy,
        evidence_cutoff_sequence=cutoff,
        checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
        wave_index=0,
        created_at=at(11),
    )
    return snapshot, target, config, bound_evidence


def test_semantic_map_round_trips_and_binds_exact_fixture_and_ontology():
    mapping = semantic_map()

    validate_authored_semantic_map(mapping, FIXTURE, ontology())
    round_tripped = AuthoredSemanticMapBundle.model_validate_json(
        mapping.model_dump_json()
    )

    assert round_tripped == mapping
    assert semantic_map_artifact_reference(mapping).artifact_sha256 == (
        content_sha256(mapping)
    )


def test_committed_development_map_is_complete_and_cli_is_aggregate_only(
    capsys,
):
    mapping = load_authored_semantic_map(DEV_SEMANTIC_MAP_PATH)

    validate_authored_semantic_map(mapping, FIXTURE, mapping.ontology)
    summary = authored_semantic_map_summary(mapping)
    exit_code = validate_semantic_map_main(
        [
            str(DEV_SEMANTIC_MAP_PATH),
            str(ROOT / "eval/fixtures/preference_eval_dev_v1.json"),
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 0
    assert payload == summary
    assert payload["measure_count"] == len(FIXTURE.measures)
    assert payload["option_count"] == sum(
        len(measure.options) for measure in FIXTURE.measures
    )
    assert "increase_reserve" not in output


def test_semantic_map_rejects_packet_dimension_centering_and_order_drift():
    mapping = semantic_map()
    first = mapping.mappings[0]

    bad_packet = mapping.model_copy(
        update={
            "mappings": [
                first.model_copy(update={"packet_sha256": "0" * 64}),
                *mapping.mappings[1:],
            ]
        }
    )
    with pytest.raises(ValueError, match="packet binding"):
        validate_authored_semantic_map(bad_packet, FIXTURE, ontology())

    first_stance = first.option_stances[0]
    unknown_dimension = first_stance.model_copy(
        update={"dimension_weights": {"invented_dimension": 1.0}}
    )
    bad_dimension = mapping.model_copy(
        update={
            "mappings": [
                first.model_copy(
                    update={
                        "option_stances": [
                            unknown_dimension,
                            *first.option_stances[1:],
                        ]
                    }
                ),
                *mapping.mappings[1:],
            ]
        }
    )
    with pytest.raises(ValueError, match="unknown dimension"):
        validate_authored_semantic_map(bad_dimension, FIXTURE, ontology())

    noncentered_stance = first_stance.model_copy(
        update={"dimension_weights": {"autonomy": 0.75}}
    )
    bad_center = mapping.model_copy(
        update={
            "mappings": [
                first.model_copy(
                    update={
                        "option_stances": [
                            noncentered_stance,
                            *first.option_stances[1:],
                        ]
                    }
                ),
                *mapping.mappings[1:],
            ]
        }
    )
    with pytest.raises(ValueError, match="option-centered"):
        validate_authored_semantic_map(bad_center, FIXTURE, ontology())

    bad_order = mapping.model_copy(
        update={"mappings": list(reversed(mapping.mappings))}
    )
    with pytest.raises(ValueError, match="fixture measure order"):
        validate_authored_semantic_map(bad_order, FIXTURE, ontology())


def test_zero_evidence_is_uniform_and_mapping_scale_cannot_change_readout():
    empty_ledger = ledger(include_evidence=False)
    full_scale, _, _, _ = build_snapshot(
        mapping=semantic_map(scale=1.0),
        evidence=empty_ledger,
        cutoff=0,
    )
    half_scale, _, _, _ = build_snapshot(
        mapping=semantic_map(scale=0.5),
        evidence=empty_ledger,
        cutoff=0,
    )

    assert set(full_scale.option_probabilities.values()) == {0.5}
    assert full_scale.option_probabilities == half_scale.option_probabilities
    assert full_scale.settled_probability == pytest.approx(0.5)


def test_configurable_rich_ballot_tolerance_cannot_change_contract_top_option():
    policy = readout_policy(comparison_tolerance=1e-6)
    prediction, _, _, _ = build_snapshot(
        evidence=ledger(claim_value=-1e-5),
        policy=policy,
    )
    first_option_id, second_option_id = [
        option.option_id for option in FIXTURE.measures[0].options
    ]
    difference = (
        prediction.option_probabilities[second_option_id]
        - prediction.option_probabilities[first_option_id]
    )

    assert 1e-12 < difference < policy.action_policy.comparison_tolerance
    assert prediction.top_option_id == second_option_id
    assert isinstance(prediction.ballot_prediction, SingleChoicePrediction)
    assert prediction.ballot_prediction.selected_option_id == second_option_id


def test_rich_ballot_tolerance_cannot_be_tighter_than_contract_top_tie():
    with pytest.raises(ValidationError):
        readout_policy(comparison_tolerance=1e-15)

    policy = readout_policy(
        comparison_tolerance=TOP_OPTION_ABS_TOLERANCE,
    )
    assert (
        policy.action_policy.comparison_tolerance
        == TOP_OPTION_ABS_TOLERANCE
    )


def test_gaussian_and_bradley_terry_replay_same_evidence_through_common_map():
    mapping = semantic_map()
    gaussian, target, gaussian_config, evidence = build_snapshot(
        model_artifact=gaussian_artifact(),
        mapping=mapping,
    )
    bradley_terry, _, bt_config, _ = build_snapshot(
        model_artifact=bradley_terry_artifact(),
        mapping=mapping,
        evidence=evidence,
    )

    first_option_id = FIXTURE.measures[0].options[0].option_id
    assert gaussian.top_option_id == first_option_id
    assert bradley_terry.top_option_id == first_option_id
    assert gaussian.option_probabilities != bradley_terry.option_probabilities
    assert gaussian.input_binding.eligible_evidence_event_ids == [
        "structured_preference_one"
    ]
    assert bradley_terry.input_binding.eligible_evidence_event_ids == [
        "structured_preference_one"
    ]
    assert gaussian.input_binding.preference_state_sha256 != (
        bradley_terry.input_binding.preference_state_sha256
    )

    run = Phase4EvaluationRun(
        run_id="classical_run",
        fixture_id=FIXTURE.fixture_id,
        fixture_version=FIXTURE.fixture_version,
        fixture_sha256=content_sha256(FIXTURE),
        phase4_protocol_id=PROTOCOL.protocol_id,
        phase4_protocol_version=PROTOCOL.protocol_version,
        phase4_protocol_sha256=content_sha256(PROTOCOL),
        session_id=evidence.session_id,
        created_at=NOW,
        evidence_ledger=evidence,
        model_configurations=[gaussian_config, bt_config],
        measure_presentations=[target],
        prediction_snapshots=[gaussian, bradley_terry],
    )
    validate_phase4_evaluation_run(run, FIXTURE, PROTOCOL)


def test_configuration_cannot_substitute_an_unbound_model_or_mapping():
    mapping = semantic_map()
    model = gaussian_artifact()
    config = configuration(model, mapping)
    target = presentation()
    evidence = ledger()

    wrong_model = config.model_copy(
        update={
            "preference_model": classical_model_artifact_reference(
                model.model_copy(update={"prior_variance": 2.0})
            )
        }
    )
    with pytest.raises(ValueError, match="exact model artifact"):
        build_classical_prediction_snapshot(
            snapshot_id="snapshot_wrong_model",
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=target,
            evidence_ledger=evidence,
            configuration=wrong_model,
            model_artifact=model,
            semantic_map=mapping,
            readout_policy=readout_policy(),
            evidence_cutoff_sequence=1,
            checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
            wave_index=0,
            created_at=at(11),
        )

    wrong_map = config.model_copy(
        update={
            "semantic_mapper": semantic_map_artifact_reference(
                semantic_map(scale=0.5)
            )
        }
    )
    with pytest.raises(ValueError, match="exact semantic map"):
        build_classical_prediction_snapshot(
            snapshot_id="snapshot_wrong_map",
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=target,
            evidence_ledger=evidence,
            configuration=wrong_map,
            model_artifact=model,
            semantic_map=mapping,
            readout_policy=readout_policy(),
            evidence_cutoff_sequence=1,
            checkpoint=PredictionCheckpoint.IMMEDIATE_PRE_ANSWER,
            wave_index=0,
            created_at=at(11),
        )


def test_every_ballot_type_uses_one_common_deterministic_action_policy():
    expected_types = {
        BallotType.SINGLE_CHOICE: SingleChoicePrediction,
        BallotType.RANKED: RankedPrediction,
        BallotType.APPROVAL: ApprovalPrediction,
        BallotType.SCORE: ScorePrediction,
        BallotType.QUADRATIC: QuadraticPrediction,
    }
    observed_types = set()

    for index, measure in enumerate(FIXTURE.measures):
        snapshot, _, _, _ = build_snapshot(measure_index=index)
        observed_types.add(measure.ballot_type)
        assert isinstance(
            snapshot.ballot_prediction,
            expected_types[measure.ballot_type],
        )

    assert observed_types == set(BallotType)


def test_uniform_rich_ballots_are_neutral_and_complete():
    policy = readout_policy().action_policy
    for measure in FIXTURE.measures:
        probability = 1.0 / len(measure.options)
        probabilities = {
            option.option_id: probability for option in measure.options
        }
        action = ballot_prediction_from_probabilities(
            measure,
            probabilities,
            policy,
        )
        if isinstance(action, RankedPrediction):
            assert len(action.ranking_tiers) == 1
        elif isinstance(action, ApprovalPrediction):
            assert action.approved_option_ids == [
                option.option_id for option in measure.options
            ]
        elif isinstance(action, ScorePrediction):
            assert set(action.option_scores.values()) == {5}
        elif isinstance(action, QuadraticPrediction):
            budget = measure.quadratic_credit_budget
            assert budget is not None
            assert sum(
                value * value
                for value in action.quadratic_allocations.values()
            ) <= budget


def test_snapshot_binds_reproducible_ledger_and_artifact_hashes():
    snapshot, target, config, evidence = build_snapshot()

    assert snapshot.model_configuration_sha256 == content_sha256(config)
    assert snapshot.input_binding.evidence_ledger_identity_sha256 == (
        evidence_ledger_identity_sha256(evidence)
    )
    assert snapshot.input_binding.model_input_sha256 != "0" * 64

    validate_classical_prediction_snapshot(
        snapshot,
        fixture=FIXTURE,
        protocol=PROTOCOL,
        measure=FIXTURE.measures[0],
        presentation=target,
        evidence_ledger=evidence,
        configuration=config,
        model_artifact=gaussian_artifact(),
        semantic_map=semantic_map(),
        readout_policy=readout_policy(),
    )


def test_artifact_aware_validator_rejects_a_self_consistent_forged_state_hash():
    snapshot, target, config, evidence = build_snapshot()
    forged_binding = snapshot.input_binding.model_copy(
        update={"preference_state_sha256": "0" * 64}
    )
    forged_binding = forged_binding.model_copy(
        update={
            "model_input_sha256": prediction_model_input_sha256(
                forged_binding,
                config,
            )
        }
    )
    forged = snapshot.model_copy(update={"input_binding": forged_binding})

    with pytest.raises(ValueError, match="reproducible model readout"):
        validate_classical_prediction_snapshot(
            forged,
            fixture=FIXTURE,
            protocol=PROTOCOL,
            measure=FIXTURE.measures[0],
            presentation=target,
            evidence_ledger=evidence,
            configuration=config,
            model_artifact=gaussian_artifact(),
            semantic_map=semantic_map(),
            readout_policy=readout_policy(),
        )
