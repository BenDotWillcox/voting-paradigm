from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from eval.build_presentation_plan import main as build_plan_main
from eval.bank_profile import load_retest_variant_registry
from eval.contracts import (
    EvaluationRun,
    MeasureDomain,
    MeasurePresentation,
    ParticipantResponse,
    PresentationKind,
    ResponseStability,
    ResponseState,
)
from eval.fixture_io import content_sha256
from eval.presentation_plan import (
    build_completed_run_validation_manifest,
    build_presentation_plan,
    load_presentation_plan,
    option_order_for_seed,
    validate_completed_run_against_plan,
    validate_presentation_plan_against_bundle,
    validate_run_progress_against_plan,
)
from eval.tests.test_bank_profile import _conforming_final_bank_bundle

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _plan_bundle():
    profile, fixture, registry, _ = _conforming_final_bank_bundle()
    plan = build_presentation_plan(
        fixture,
        profile,
        registry,
        plan_id="preference_eval_presentation_plan_test_v1",
        plan_version=1,
        created_at=NOW,
    )
    return profile, fixture, registry, plan


def _unsure_response(
    presentation: MeasurePresentation,
    *,
    sequence: int,
    created_at: datetime,
) -> ParticipantResponse:
    return ParticipantResponse(
        response_id=f"response_{presentation.presentation_id}",
        session_id=presentation.session_id,
        presentation_id=presentation.presentation_id,
        measure_id=presentation.measure_id,
        measure_version=presentation.measure_version,
        packet_version=presentation.packet_version,
        sequence=sequence,
        response_state=ResponseState.UNSURE,
        confidence=0.5,
        preference_strength=0,
        stability=ResponseStability.TENTATIVE,
        created_at=created_at,
    )


def _complete_run(fixture, plan) -> EvaluationRun:
    session_id = "phase3c_session_test"
    initial_presentations = []
    responses = []
    presentation_by_plan_entry = {}
    sequence = 0
    for index, entry in enumerate(plan.initial_presentations):
        presented_at = NOW + timedelta(minutes=index)
        presentation = MeasurePresentation(
            presentation_id=f"initial_presentation_{index + 1:02d}",
            session_id=session_id,
            measure_id=entry.measure_id,
            measure_version=entry.measure_version,
            packet_version=entry.packet_version,
            kind=PresentationKind.INITIAL,
            order_seed=entry.option_order_seed,
            presented_at=presented_at,
        )
        initial_presentations.append(presentation)
        presentation_by_plan_entry[entry.plan_entry_id] = presentation
        sequence += 1
        responses.append(
            _unsure_response(
                presentation,
                sequence=sequence,
                created_at=presented_at + timedelta(seconds=30),
            )
        )

    retest_rows = []
    for entry in plan.retest_presentations:
        original = presentation_by_plan_entry[
            entry.source_initial_plan_entry_id
        ]
        presented_at = original.presented_at + timedelta(days=8)
        retest_rows.append((presented_at, entry, original))
    retest_rows.sort(key=lambda row: row[0])

    retest_presentations = []
    for index, (presented_at, entry, original) in enumerate(retest_rows):
        presentation = MeasurePresentation(
            presentation_id=f"retest_presentation_{index + 1:02d}",
            session_id=session_id,
            measure_id=entry.source_measure_id,
            measure_version=entry.source_measure_version,
            packet_version=entry.packet_version,
            kind=PresentationKind.RETEST,
            retest_of_presentation_id=original.presentation_id,
            order_seed=entry.option_order_seed,
            presented_at=presented_at,
        )
        retest_presentations.append(presentation)
        sequence += 1
        responses.append(
            _unsure_response(
                presentation,
                sequence=sequence,
                created_at=presented_at + timedelta(seconds=30),
            )
        )

    return EvaluationRun(
        run_id="phase3c_run_test_v1",
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        session_id=session_id,
        created_at=NOW,
        measure_presentations=[
            *initial_presentations,
            *retest_presentations,
        ],
        participant_responses=responses,
    )


def test_presentation_plan_is_deterministic_and_stratified():
    profile, fixture, registry, first = _plan_bundle()
    second = build_presentation_plan(
        fixture,
        profile,
        registry,
        plan_id=first.plan_id,
        plan_version=first.plan_version,
        created_at=first.created_at,
    )

    assert first == second
    validate_presentation_plan_against_bundle(
        first,
        fixture,
        profile,
        registry,
    )
    assert Counter(
        entry.wave_index for entry in first.initial_presentations
    ) == {index: 8 for index in range(6)}
    measure_by_ref = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    for wave_index in range(6):
        assert Counter(
            measure_by_ref[(entry.measure_id, entry.measure_version)].domain
            for entry in first.initial_presentations
            if entry.wave_index == wave_index
        ) == {domain: 1 for domain in MeasureDomain}


def test_every_retest_uses_a_different_option_order():
    _, fixture, _, plan = _plan_bundle()
    initial_by_id = {
        entry.plan_entry_id: entry for entry in plan.initial_presentations
    }
    measure_by_ref = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }

    assert all(
        entry.ordered_option_ids
        != initial_by_id[
            entry.source_initial_plan_entry_id
        ].ordered_option_ids
        for entry in plan.retest_presentations
    )
    assert all(
        entry.ordered_option_ids
        == option_order_for_seed(
            measure_by_ref[
                (entry.source_measure_id, entry.source_measure_version)
            ],
            seed=entry.option_order_seed,
            namespace="retest-options",
        )
        for entry in plan.retest_presentations
    )


def test_build_presentation_plan_cli_writes_exact_plan_with_safe_stdout(
    tmp_path,
    capsys,
):
    profile, fixture, registry, expected = _plan_bundle()
    profile_path = tmp_path / "profile.json"
    fixture_path = tmp_path / "fixture.json"
    registry_path = tmp_path / "registry.json"
    output_path = tmp_path / "plan.json"
    for path, model in (
        (profile_path, profile),
        (fixture_path, fixture),
        (registry_path, registry),
    ):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    exit_code = build_plan_main(
        [
            str(profile_path),
            str(fixture_path),
            str(registry_path),
            "--plan-id",
            expected.plan_id,
            "--plan-version",
            str(expected.plan_version),
            "--created-at",
            expected.created_at.isoformat(),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert load_presentation_plan(output_path) == expected
    assert '"initial_presentation_count": 48' in captured.out
    assert '"retest_presentation_count": 12' in captured.out
    assert fixture.measures[0].packet.status_quo not in captured.out
    assert load_retest_variant_registry(registry_path) == registry


def test_presentation_plan_rejects_a_seed_drift():
    profile, fixture, registry, plan = _plan_bundle()
    first = plan.initial_presentations[0]
    invalid = plan.model_copy(
        update={
            "initial_presentations": [
                first.model_copy(
                    update={"option_order_seed": first.option_order_seed + 1}
                ),
                *plan.initial_presentations[1:],
            ]
        }
    )

    with pytest.raises(ValueError, match="deterministic policy"):
        validate_presentation_plan_against_bundle(
            invalid,
            fixture,
            profile,
            registry,
        )


def test_completed_run_passes_every_execution_gate():
    profile, fixture, registry, plan = _plan_bundle()
    run = _complete_run(fixture, plan)

    validate_completed_run_against_plan(
        run,
        fixture,
        profile,
        registry,
        plan,
    )
    manifest = build_completed_run_validation_manifest(
        run,
        fixture,
        profile,
        registry,
        plan,
        validated_at=NOW + timedelta(days=9),
    )

    assert manifest.initial_presentation_count == 48
    assert manifest.retest_presentation_count == 12
    assert manifest.run_sha256 == content_sha256(run)


def test_run_rejects_an_initial_outside_frozen_wave_order():
    profile, fixture, registry, plan = _plan_bundle()
    run = _complete_run(fixture, plan)
    presentations = list(run.measure_presentations)
    presentations[0], presentations[1] = presentations[1], presentations[0]
    invalid = run.model_copy(update={"measure_presentations": presentations})

    with pytest.raises(ValueError, match="frozen wave order"):
        validate_completed_run_against_plan(
            invalid,
            fixture,
            profile,
            registry,
            plan,
        )


def test_run_rejects_a_retest_outside_timing_window():
    profile, fixture, registry, plan = _plan_bundle()
    run = _complete_run(fixture, plan)
    presentations = list(run.measure_presentations)
    retest_index = next(
        index
        for index, presentation in enumerate(presentations)
        if presentation.kind is PresentationKind.RETEST
    )
    retest = presentations[retest_index]
    original = next(
        presentation
        for presentation in presentations
        if presentation.presentation_id
        == retest.retest_of_presentation_id
    )
    presentations[retest_index] = retest.model_copy(
        update={"presented_at": original.presented_at + timedelta(days=6)}
    )
    invalid = run.model_copy(update={"measure_presentations": presentations})

    with pytest.raises(ValueError, match="frozen interval"):
        validate_completed_run_against_plan(
            invalid,
            fixture,
            profile,
            registry,
            plan,
        )


def test_run_rejects_retest_shown_before_original_response():
    profile, fixture, registry, plan = _plan_bundle()
    run = _complete_run(fixture, plan)
    retest = next(
        presentation
        for presentation in run.measure_presentations
        if presentation.kind is PresentationKind.RETEST
    )
    original_response = next(
        response
        for response in run.participant_responses
        if response.presentation_id == retest.retest_of_presentation_id
    )
    delayed_base = max(
        presentation.presented_at
        for presentation in run.measure_presentations
    ) + timedelta(hours=1)
    delayed_responses = [
        response.model_copy(
            update={
                "created_at": delayed_base
                + timedelta(seconds=response.sequence)
            }
        )
        if response.sequence >= original_response.sequence
        else response
        for response in run.participant_responses
    ]
    invalid = EvaluationRun.model_validate(
        {
            **run.model_dump(mode="python"),
            "participant_responses": delayed_responses,
        }
    )

    with pytest.raises(ValueError, match="follow the original response"):
        validate_completed_run_against_plan(
            invalid,
            fixture,
            profile,
            registry,
            plan,
        )


def test_progress_validator_accepts_an_initial_prefix_only():
    profile, fixture, registry, plan = _plan_bundle()
    run = _complete_run(fixture, plan)
    prefix_presentations = run.measure_presentations[:8]
    prefix_ids = {
        presentation.presentation_id for presentation in prefix_presentations
    }
    prefix = run.model_copy(
        update={
            "measure_presentations": prefix_presentations,
            "participant_responses": [
                response
                for response in run.participant_responses
                if response.presentation_id in prefix_ids
            ],
        }
    )

    validate_run_progress_against_plan(
        prefix,
        fixture,
        profile,
        registry,
        plan,
    )
    with pytest.raises(ValueError, match="every initial presentation"):
        validate_completed_run_against_plan(
            prefix,
            fixture,
            profile,
            registry,
            plan,
        )
