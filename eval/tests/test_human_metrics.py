"""Tests for Phase 2 option and delegation metrics."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest

from eval.contracts import (
    EvaluationRun,
    MeasurePresentation,
    ParticipantResponse,
    PredictionSnapshot,
    PresentationKind,
)
from eval.development import (
    build_development_adapters,
    load_development_inputs,
)
from eval.human_metrics import compute_human_measure_metrics
from eval.prequential import (
    PrequentialReplay,
    SnapshotCheckpoint,
    SnapshotTrace,
    run_prequential_session,
)


@pytest.fixture(scope="module")
def development_result():
    fixture, script = load_development_inputs()
    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=build_development_adapters(fixture),
    )
    metrics = compute_human_measure_metrics(replay)
    return fixture, replay, metrics


def metric_by_configuration(metrics, configuration_id: str):
    return next(
        model
        for model in metrics.models
        if model.configuration_id == configuration_id
    )


def test_primary_metrics_include_tentative_choices(development_result):
    _, _, metrics = development_result
    uniform = metric_by_configuration(metrics, "uniform_prior_v1")

    expected_log_loss = (
        math.log(2)
        + math.log(2)
        + math.log(3)
        + math.log(4)
        + math.log(4)
        + math.log(4)
    ) / 6
    assert uniform.choice.count == 6
    assert uniform.stable_choice.count == 5
    assert uniform.tentative_choice.count == 1
    assert uniform.choice.mean_log_loss == pytest.approx(expected_log_loss)
    assert uniform.choice.top_choice_accuracy == pytest.approx(0.5)


def test_risk_coverage_reports_unsupported_nonchoice_votes(
    development_result,
):
    _, _, metrics = development_result
    scripted = metric_by_configuration(
        metrics,
        "scripted_test_double_v1",
    )
    threshold_65 = next(
        point
        for point in scripted.candidate_thresholds
        if point.threshold == 0.65
    )

    assert threshold_65.eligible_choice_count == 6
    assert threshold_65.nonchoice_count == 2
    assert threshold_65.automatic_choice_vote_count == 2
    assert threshold_65.coverage == pytest.approx(2 / 6)
    assert threshold_65.wrong_vote_count == 1
    assert threshold_65.risk == pytest.approx(0.5)
    assert threshold_65.unsupported_vote_count == 2
    assert threshold_65.unsupported_vote_rate == pytest.approx(1.0)


def test_uniform_prior_defers_at_candidate_thresholds(development_result):
    _, _, metrics = development_result
    uniform = metric_by_configuration(metrics, "uniform_prior_v1")

    assert all(
        point.automatic_choice_vote_count == 0
        for point in uniform.candidate_thresholds
    )
    assert all(
        point.risk is None for point in uniform.candidate_thresholds
    )


def test_retest_response_is_excluded_from_primary_metrics(
    development_result,
):
    fixture, replay, original_metrics = development_result
    run = replay.run
    initial = next(
        presentation
        for presentation in run.measure_presentations
        if presentation.measure_id == "dev_fiscal_reserve"
    )
    initial_response = next(
        response
        for response in run.participant_responses
        if response.presentation_id == initial.presentation_id
    )
    source_snapshot = next(
        snapshot
        for snapshot in run.prediction_snapshots
        if (
            snapshot.model_configuration_id == "uniform_prior_v1"
            and snapshot.target_presentation_id == initial.presentation_id
        )
    )
    retest_time = replay.completed_at + timedelta(days=14)
    retest = MeasurePresentation(
        presentation_id="presentation_retest_fiscal",
        session_id=run.session_id,
        measure_id=initial.measure_id,
        measure_version=initial.measure_version,
        packet_version=initial.packet_version,
        kind=PresentationKind.RETEST,
        retest_of_presentation_id=initial.presentation_id,
        order_seed=initial.order_seed,
        presented_at=retest_time,
    )
    retest_snapshot = PredictionSnapshot(
        **{
            **source_snapshot.model_dump(),
            "snapshot_id": "snapshot_retest_fiscal",
            "target_presentation_id": retest.presentation_id,
            "evidence_cutoff_sequence": 18,
            "evidence_event_ids": [
                event.event_id for event in run.evidence_events
            ],
            "created_at": retest_time + timedelta(seconds=1),
        }
    )
    retest_response = ParticipantResponse(
        **{
            **initial_response.model_dump(),
            "response_id": "response_retest_fiscal",
            "presentation_id": retest.presentation_id,
            "sequence": 19,
            "created_at": retest_time + timedelta(seconds=2),
        }
    )
    extended_run = EvaluationRun(
        **{
            **run.model_dump(),
            "measure_presentations": [
                *run.measure_presentations,
                retest,
            ],
            "prediction_snapshots": [
                *run.prediction_snapshots,
                retest_snapshot,
            ],
            "participant_responses": [
                *run.participant_responses,
                retest_response,
            ],
        }
    )
    extended_replay = PrequentialReplay(
        session_script_id=replay.session_script_id,
        session_script_version=replay.session_script_version,
        session_script_sha256=replay.session_script_sha256,
        completed_at=retest_response.created_at,
        run=extended_run,
        snapshot_traces=[
            *replay.snapshot_traces,
            SnapshotTrace(
                snapshot_id=retest_snapshot.snapshot_id,
                checkpoint=SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER,
                wave_index=2,
                response_order=8,
            ),
        ],
    )

    extended_metrics = compute_human_measure_metrics(extended_replay)

    assert [
        model.choice.count for model in extended_metrics.models
    ] == [
        model.choice.count for model in original_metrics.models
    ]
