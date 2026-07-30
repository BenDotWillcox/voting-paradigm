"""Tests for the human preference-evaluation contracts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.contracts import (
    DimensionStatus,
    EvidenceEvent,
    EvidenceModality,
    EvaluationRun,
    MeasurePresentation,
    MeasureSourceKind,
    MeasureVersion,
    ModelConfiguration,
    OntologyVersion,
    ParticipantResponse,
    PresentationKind,
    PreferenceDimension,
    PredictionSnapshot,
    RankingTier,
    RetestPacketVariant,
    ResponseStability,
    ResponseState,
    validate_prediction_for_measure,
    validate_response_for_measure,
)
from eval.fixture_io import (
    content_sha256,
    load_fixture,
    validate_run_against_fixture,
)

FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_dev_v1.json"
)
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def fixture():
    return load_fixture(FIXTURE_PATH)


def measure_by_id(fixture, measure_id: str) -> MeasureVersion:
    return next(
        measure for measure in fixture.measures if measure.measure_id == measure_id
    )


def response_for(
    measure: MeasureVersion,
    **updates,
) -> ParticipantResponse:
    values = {
        "response_id": f"response_{measure.measure_id}",
        "session_id": "session_one",
        "presentation_id": f"presentation_{measure.measure_id}",
        "measure_id": measure.measure_id,
        "measure_version": measure.version,
        "packet_version": measure.packet.version,
        "sequence": 2,
        "response_state": "choice",
        "selected_option_id": measure.options[0].option_id,
        "confidence": 0.8,
        "preference_strength": 7,
        "stability": "stable",
        "created_at": NOW + timedelta(minutes=1),
    }
    values.update(updates)
    return ParticipantResponse.model_validate(values)


def presentation_for(
    measure: MeasureVersion,
    **updates,
) -> MeasurePresentation:
    values = {
        "presentation_id": f"presentation_{measure.measure_id}",
        "session_id": "session_one",
        "measure_id": measure.measure_id,
        "measure_version": measure.version,
        "packet_version": measure.packet.version,
        "kind": PresentationKind.INITIAL,
        "order_seed": 7,
        "presented_at": NOW,
    }
    values.update(updates)
    return MeasurePresentation.model_validate(values)


class TestMeasureContracts:
    def test_packet_arguments_must_match_options(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        raw = measure.model_dump(mode="json")
        raw["packet"]["arguments_by_option"].pop("increase_reserve")

        with pytest.raises(ValidationError, match="arguments_by_option"):
            MeasureVersion.model_validate(raw)

    def test_option_order_must_be_contiguous_and_stored_in_order(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        raw = measure.model_dump(mode="json")
        raw["options"][1]["display_order"] = 3

        with pytest.raises(ValidationError, match="contiguous display_order"):
            MeasureVersion.model_validate(raw)

    def test_real_world_anchored_measure_requires_url_source(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        raw = measure.model_dump(mode="json")
        raw["source_kind"] = MeasureSourceKind.REAL_WORLD_ANCHORED.value

        with pytest.raises(ValidationError, match="URL-backed source"):
            MeasureVersion.model_validate(raw)


class TestParticipantResponses:
    def test_tie_aware_partial_ranking_is_valid(self, fixture):
        measure = measure_by_id(fixture, "dev_education_calendar")
        response = response_for(
            measure,
            selected_option_id="balanced_calendar",
            ranking_tiers=[
                RankingTier(
                    option_ids=["balanced_calendar", "traditional_calendar"]
                )
            ],
            approved_option_ids=["balanced_calendar", "traditional_calendar"],
            option_scores={
                "traditional_calendar": 7,
                "balanced_calendar": 7,
                "local_choice": 5,
            },
        )

        validate_response_for_measure(response, measure)

    def test_option_cannot_appear_in_two_ranking_tiers(self, fixture):
        measure = measure_by_id(fixture, "dev_education_calendar")

        with pytest.raises(ValidationError, match="across ranking tiers"):
            response_for(
                measure,
                ranking_tiers=[
                    {"option_ids": ["balanced_calendar"]},
                    {"option_ids": ["balanced_calendar", "local_choice"]},
                ],
                approved_option_ids=[],
                option_scores={
                    "traditional_calendar": 5,
                    "balanced_calendar": 8,
                    "local_choice": 6,
                },
            )

    def test_cross_format_inconsistency_is_retained_for_measurement(self, fixture):
        measure = measure_by_id(fixture, "dev_education_calendar")
        response = response_for(
            measure,
            selected_option_id="traditional_calendar",
            ranking_tiers=[
                {"option_ids": ["balanced_calendar"]},
                {"option_ids": ["traditional_calendar"]},
            ],
            approved_option_ids=["balanced_calendar"],
            option_scores={
                "traditional_calendar": 4,
                "balanced_calendar": 8,
                "local_choice": 2,
            },
        )

        validate_response_for_measure(response, measure)

    def test_unsure_and_abstain_are_distinct_non_ballot_states(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        unsure = response_for(
            measure,
            response_id="response_unsure",
            response_state=ResponseState.UNSURE,
            selected_option_id=None,
            stability=ResponseStability.TENTATIVE,
        )
        abstain = response_for(
            measure,
            response_id="response_abstain",
            response_state=ResponseState.ABSTAIN,
            selected_option_id=None,
        )

        validate_response_for_measure(unsure, measure)
        validate_response_for_measure(abstain, measure)
        assert unsure.response_state is ResponseState.UNSURE
        assert abstain.response_state is ResponseState.ABSTAIN

    def test_unsure_response_cannot_smuggle_a_choice(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")

        with pytest.raises(ValidationError, match="cannot include ballot"):
            response_for(
                measure,
                response_state=ResponseState.UNSURE,
                selected_option_id=measure.options[0].option_id,
            )

    def test_response_rejects_unknown_option(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        response = response_for(measure, selected_option_id="unknown_option")

        with pytest.raises(ValueError, match="unknown option"):
            validate_response_for_measure(response, measure)

    def test_response_rejects_fields_not_declared_by_measure(self, fixture):
        measure = measure_by_id(fixture, "dev_fiscal_reserve")
        response = response_for(
            measure,
            ranking_tiers=[
                {"option_ids": [measure.options[0].option_id]}
            ],
        )

        with pytest.raises(ValueError, match="not declared"):
            validate_response_for_measure(response, measure)

    def test_quadratic_response_cannot_exceed_credit_budget(self, fixture):
        measure = measure_by_id(fixture, "dev_governance_digital_budget")
        response = response_for(
            measure,
            selected_option_id="privacy_security",
            quadratic_allocations={
                "service_portal": 8,
                "privacy_security": 7,
            },
        )

        with pytest.raises(ValueError, match="exceeds credit budget 100"):
            validate_response_for_measure(response, measure)

    def test_allocation_contest_rejects_negative_votes(self, fixture):
        measure = measure_by_id(fixture, "dev_governance_digital_budget")
        response = response_for(
            measure,
            selected_option_id="privacy_security",
            quadratic_allocations={"privacy_security": 4, "offline_access": -2},
        )

        with pytest.raises(ValueError, match="does not allow negative"):
            validate_response_for_measure(response, measure)


class TestEvidenceAndLeakage:
    def test_non_intervention_cannot_receive_positive_weight(self):
        with pytest.raises(ValidationError, match="reliability_weight 0"):
            EvidenceEvent(
                event_id="evidence_silence",
                session_id="session_one",
                sequence=1,
                modality=EvidenceModality.NON_INTERVENTION,
                confirmed_by_participant=False,
                stability=ResponseStability.TENTATIVE,
                reliability_weight=0.5,
                occurred_at=NOW,
            )

    def test_raw_response_has_private_ingestion_limit(self):
        with pytest.raises(ValidationError, match="at most 20000 characters"):
            EvidenceEvent(
                event_id="evidence_too_large",
                session_id="session_one",
                sequence=1,
                modality=EvidenceModality.FREE_TEXT_EXTRACTION,
                question_id="question_one",
                question_version=1,
                raw_response="x" * 20_001,
                confirmed_by_participant=False,
                stability=ResponseStability.TENTATIVE,
                reliability_weight=0.5,
                occurred_at=NOW,
            )

    def test_event_sequence_must_agree_with_record_times(self, fixture):
        first = EvidenceEvent(
            event_id="evidence_first",
            session_id="session_one",
            sequence=1,
            modality=EvidenceModality.FREE_TEXT_EXTRACTION,
            confirmed_by_participant=False,
            stability=ResponseStability.TENTATIVE,
            reliability_weight=0.5,
            occurred_at=NOW + timedelta(minutes=2),
        )
        second = EvidenceEvent(
            event_id="evidence_second",
            session_id="session_one",
            sequence=2,
            modality=EvidenceModality.FREE_TEXT_EXTRACTION,
            confirmed_by_participant=False,
            stability=ResponseStability.TENTATIVE,
            reliability_weight=0.5,
            occurred_at=NOW + timedelta(minutes=1),
        )

        with pytest.raises(ValidationError, match="sequence must agree with time"):
            EvaluationRun(
                run_id="run_reversed_time",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                evidence_events=[first, second],
            )

    def test_snapshot_cutoff_cannot_include_future_retest_response(
        self, fixture
    ):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        initial = presentation_for(
            target,
            presentation_id="presentation_initial",
        )
        retest = presentation_for(
            target,
            presentation_id="presentation_retest",
            kind=PresentationKind.RETEST,
            retest_of_presentation_id=initial.presentation_id,
            presented_at=NOW + timedelta(days=14),
        )
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_before_retest",
            session_id="session_one",
            target_presentation_id=initial.presentation_id,
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=5,
            option_probabilities={
                target.options[0].option_id: 0.7,
                target.options[1].option_id: 0.3,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.7,
            settled_probability=0.8,
            model_configuration_id=configuration.configuration_id,
            created_at=NOW + timedelta(seconds=1),
        )
        retest_response = response_for(
            target,
            response_id="response_retest",
            presentation_id=retest.presentation_id,
            sequence=3,
            created_at=NOW + timedelta(days=14, minutes=1),
        )

        with pytest.raises(ValidationError, match="cutoff includes future"):
            EvaluationRun(
                run_id="run_future_retest_cutoff",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                model_configurations=[configuration],
                measure_presentations=[initial, retest],
                prediction_snapshots=[snapshot],
                participant_responses=[retest_response],
            )

    def test_ontology_cutoff_cannot_include_future_record(self, fixture):
        future_event = EvidenceEvent(
            event_id="evidence_after_ontology",
            session_id="session_one",
            sequence=1,
            modality=EvidenceModality.FREE_TEXT_EXTRACTION,
            confirmed_by_participant=False,
            stability=ResponseStability.TENTATIVE,
            reliability_weight=0.5,
            occurred_at=NOW + timedelta(minutes=2),
        )
        ontology = OntologyVersion(
            ontology_version_id="ontology_before_evidence",
            version=1,
            evidence_cutoff_sequence=1,
            created_at=NOW + timedelta(minutes=1),
        )

        with pytest.raises(ValidationError, match="cutoff includes future"):
            EvaluationRun(
                run_id="run_future_ontology_cutoff",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                ontology_versions=[ontology],
                evidence_events=[future_event],
            )

    def test_snapshot_cannot_reference_future_evidence(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        other = measure_by_id(fixture, "dev_health_mobile_clinics")
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        presentation = presentation_for(target)
        evidence = EvidenceEvent(
            event_id="evidence_future",
            session_id="session_one",
            sequence=2,
            modality=EvidenceModality.STRUCTURED_RESPONSE,
            measure_id=other.measure_id,
            measure_version=other.version,
            packet_version=other.packet.version,
            confirmed_by_participant=True,
            stability=ResponseStability.STABLE,
            reliability_weight=1.0,
            occurred_at=NOW,
        )
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_one",
            session_id="session_one",
            target_presentation_id=presentation.presentation_id,
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=1,
            evidence_event_ids=[evidence.event_id],
            option_probabilities={
                target.options[0].option_id: 0.7,
                target.options[1].option_id: 0.3,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.7,
            settled_probability=0.8,
            model_configuration_id=configuration.configuration_id,
            created_at=NOW,
        )

        with pytest.raises(ValidationError, match="future evidence"):
            EvaluationRun(
                run_id="run_one",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                model_configurations=[configuration],
                measure_presentations=[presentation],
                evidence_events=[evidence],
                prediction_snapshots=[snapshot],
            )

    def test_prediction_must_cover_exact_measure_options(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_bad_options",
            session_id="session_one",
            target_presentation_id="presentation_bad_options",
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=0,
            option_probabilities={
                target.options[0].option_id: 0.7,
                "invented_option": 0.3,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.7,
            settled_probability=0.8,
            model_configuration_id="model_config",
            created_at=NOW,
        )

        with pytest.raises(ValueError, match="every measure option exactly"):
            validate_prediction_for_measure(snapshot, target)

    def test_prediction_ties_use_measure_display_order(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_tied",
            session_id="session_one",
            target_presentation_id="presentation_tied",
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=0,
            option_probabilities={
                target.options[0].option_id: 0.5,
                target.options[1].option_id: 0.5,
            },
            top_option_id=target.options[1].option_id,
            confidence=0.5,
            settled_probability=0.8,
            model_configuration_id="model_config",
            created_at=NOW,
        )

        with pytest.raises(ValueError, match="display order"):
            validate_prediction_for_measure(snapshot, target)

    def test_ontology_cannot_use_evidence_after_its_cutoff(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        evidence = EvidenceEvent(
            event_id="evidence_late",
            session_id="session_one",
            sequence=2,
            modality=EvidenceModality.STRUCTURED_RESPONSE,
            measure_id=target.measure_id,
            measure_version=target.version,
            packet_version=target.packet.version,
            confirmed_by_participant=True,
            stability=ResponseStability.STABLE,
            reliability_weight=1.0,
            occurred_at=NOW,
        )
        ontology = OntologyVersion(
            ontology_version_id="ontology_one",
            version=1,
            evidence_cutoff_sequence=1,
            dimensions=[
                PreferenceDimension(
                    dimension_id="fiscal_resilience",
                    name="Fiscal resilience",
                    definition="Preference for reserves against uncertain shocks.",
                    interpretation="Higher values favor larger reserves.",
                    status=DimensionStatus.PROPOSED,
                    supporting_evidence_event_ids=[evidence.event_id],
                    created_by_configuration_id=configuration.configuration_id,
                )
            ],
            created_at=NOW + timedelta(seconds=1),
        )

        with pytest.raises(ValidationError, match="uses future evidence"):
            EvaluationRun(
                run_id="run_ontology_leak",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                model_configurations=[configuration],
                ontology_versions=[ontology],
                evidence_events=[evidence],
            )

    def test_snapshot_must_precede_target_response(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        presentation = presentation_for(target)
        response = response_for(target, sequence=1)
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_late",
            session_id="session_one",
            target_presentation_id=presentation.presentation_id,
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=1,
            option_probabilities={
                target.options[0].option_id: 0.6,
                target.options[1].option_id: 0.4,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.6,
            settled_probability=0.7,
            model_configuration_id=configuration.configuration_id,
            created_at=NOW,
        )

        with pytest.raises(ValidationError, match="after target response"):
            EvaluationRun(
                run_id="run_late",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                model_configurations=[configuration],
                measure_presentations=[presentation],
                prediction_snapshots=[snapshot],
                participant_responses=[response],
            )

    def test_valid_prequential_run_keeps_target_answer_after_snapshot(
        self, fixture
    ):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        other = measure_by_id(fixture, "dev_health_mobile_clinics")
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        presentation = presentation_for(target)
        evidence = EvidenceEvent(
            event_id="evidence_prior",
            session_id="session_one",
            sequence=1,
            modality=EvidenceModality.STRUCTURED_RESPONSE,
            measure_id=other.measure_id,
            measure_version=other.version,
            packet_version=other.packet.version,
            confirmed_by_participant=True,
            stability=ResponseStability.STABLE,
            reliability_weight=1.0,
            occurred_at=NOW,
        )
        snapshot = PredictionSnapshot(
            snapshot_id="snapshot_valid",
            session_id="session_one",
            target_presentation_id=presentation.presentation_id,
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=target.packet.version,
            evidence_cutoff_sequence=1,
            evidence_event_ids=[evidence.event_id],
            option_probabilities={
                target.options[0].option_id: 0.65,
                target.options[1].option_id: 0.35,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.65,
            settled_probability=0.75,
            model_configuration_id=configuration.configuration_id,
            created_at=NOW + timedelta(seconds=1),
        )
        response = response_for(
            target,
            response_id="response_target",
            sequence=2,
            created_at=NOW + timedelta(minutes=1),
        )

        run = EvaluationRun(
            run_id="run_valid",
            fixture_id=fixture.fixture_id,
            fixture_version=fixture.fixture_version,
            fixture_sha256=content_sha256(fixture),
            session_id="session_one",
            created_at=NOW,
            model_configurations=[configuration],
            measure_presentations=[presentation],
            evidence_events=[evidence],
            prediction_snapshots=[snapshot],
            participant_responses=[response],
        )
        replayed = EvaluationRun.model_validate_json(run.model_dump_json())
        validate_run_against_fixture(replayed, fixture)
        assert replayed == run
        assert replayed.prediction_snapshots[0].evidence_cutoff_sequence == 1

    def test_retest_prediction_can_use_original_response_evidence(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        variant_packet = target.packet.model_copy(
            update={
                "version": target.packet.version + 1,
                "status_quo": (
                    "Meridian currently keeps the same reserve policy, "
                    "restated for the retest."
                ),
            }
        )
        variant = RetestPacketVariant(
            variant_id="retest_variant_fiscal_reserve",
            source_measure_id=target.measure_id,
            source_measure_version=target.version,
            packet=variant_packet,
            order_seed=17,
        )
        variant_measure = MeasureVersion.model_validate(
            {
                **target.model_dump(mode="python"),
                "packet": variant_packet.model_dump(mode="python"),
            }
        )
        configuration = ModelConfiguration(
            configuration_id="model_config",
            model_name="test model",
            model_version="v1",
            seed=7,
        )
        initial = presentation_for(
            target,
            presentation_id="presentation_initial",
        )
        initial_response = response_for(
            target,
            response_id="response_initial",
            presentation_id=initial.presentation_id,
            sequence=1,
            created_at=NOW + timedelta(minutes=1),
        )
        initial_evidence = EvidenceEvent(
            event_id="evidence_initial",
            session_id="session_one",
            sequence=2,
            modality=EvidenceModality.STRUCTURED_RESPONSE,
            measure_id=target.measure_id,
            measure_version=target.version,
            packet_version=target.packet.version,
            presentation_id=initial.presentation_id,
            response_id=initial_response.response_id,
            confirmed_by_participant=True,
            stability=ResponseStability.STABLE,
            reliability_weight=1.0,
            occurred_at=NOW + timedelta(minutes=2),
        )
        retest = presentation_for(
            variant_measure,
            presentation_id="presentation_retest",
            kind=PresentationKind.RETEST,
            retest_of_presentation_id=initial.presentation_id,
            order_seed=variant.order_seed,
            presented_at=NOW + timedelta(days=14),
        )
        retest_snapshot = PredictionSnapshot(
            snapshot_id="snapshot_retest",
            session_id="session_one",
            target_presentation_id=retest.presentation_id,
            target_measure_id=target.measure_id,
            target_measure_version=target.version,
            target_packet_version=variant.packet.version,
            evidence_cutoff_sequence=2,
            evidence_event_ids=[initial_evidence.event_id],
            option_probabilities={
                target.options[0].option_id: 0.7,
                target.options[1].option_id: 0.3,
            },
            top_option_id=target.options[0].option_id,
            confidence=0.7,
            settled_probability=0.85,
            model_configuration_id=configuration.configuration_id,
            created_at=NOW + timedelta(days=14, seconds=1),
        )
        retest_response = response_for(
            variant_measure,
            response_id="response_retest",
            presentation_id=retest.presentation_id,
            sequence=3,
            created_at=NOW + timedelta(days=14, minutes=1),
        )

        run = EvaluationRun(
            run_id="run_retest",
            fixture_id=fixture.fixture_id,
            fixture_version=fixture.fixture_version,
            fixture_sha256=content_sha256(fixture),
            session_id="session_one",
            created_at=NOW,
            model_configurations=[configuration],
            measure_presentations=[initial, retest],
            evidence_events=[initial_evidence],
            prediction_snapshots=[retest_snapshot],
            participant_responses=[initial_response, retest_response],
        )

        with pytest.raises(ValueError, match="registered retest variant"):
            validate_run_against_fixture(run, fixture)

        validate_run_against_fixture(
            run,
            fixture,
            retest_variants=[variant],
        )

    def test_evidence_response_reference_must_exist(self, fixture):
        target = measure_by_id(fixture, "dev_fiscal_reserve")
        presentation = presentation_for(target)
        evidence = EvidenceEvent(
            event_id="evidence_orphan",
            session_id="session_one",
            sequence=2,
            modality=EvidenceModality.STRUCTURED_RESPONSE,
            measure_id=target.measure_id,
            measure_version=target.version,
            packet_version=target.packet.version,
            presentation_id=presentation.presentation_id,
            response_id="response_missing",
            confirmed_by_participant=True,
            stability=ResponseStability.STABLE,
            reliability_weight=1.0,
            occurred_at=NOW + timedelta(minutes=2),
        )

        with pytest.raises(ValidationError, match="unknown response"):
            EvaluationRun(
                run_id="run_orphan_evidence",
                fixture_id=fixture.fixture_id,
                fixture_version=fixture.fixture_version,
                fixture_sha256=content_sha256(fixture),
                session_id="session_one",
                created_at=NOW,
                measure_presentations=[presentation],
                evidence_events=[evidence],
            )

    def test_run_must_bind_measure_references_to_fixture(self, fixture):
        invented_presentation = MeasurePresentation(
            presentation_id="presentation_invented",
            session_id="session_one",
            measure_id="totally_invented_measure",
            measure_version=99,
            packet_version=99,
            kind=PresentationKind.INITIAL,
            order_seed=7,
            presented_at=NOW,
        )
        run = EvaluationRun(
            run_id="run_invented_measure",
            fixture_id=fixture.fixture_id,
            fixture_version=fixture.fixture_version,
            fixture_sha256=content_sha256(fixture),
            session_id="session_one",
            created_at=NOW,
            measure_presentations=[invented_presentation],
        )

        with pytest.raises(ValueError, match="unknown measure"):
            validate_run_against_fixture(run, fixture)
