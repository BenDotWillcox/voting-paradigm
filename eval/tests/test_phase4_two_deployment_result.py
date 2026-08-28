from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.contracts import ResponseState
from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_llm_readout import LLMReadoutResponseDraft
from eval.phase4_provider import (
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderSeedStatus,
    provider_request_content_sha256,
)
from eval.phase4_qualification_scope import (
    load_two_deployment_qualification_scope,
)
from eval.phase4_qualification_execution import (
    QualificationCallDisposition,
    load_two_deployment_qualification_plan,
)
from eval.phase4_readiness import (
    QualificationVariant,
    load_readiness_bundle,
    rebuild_qualification_call,
)
from eval.phase4_robustness import (
    BudgetSegment,
    LLMRole,
    ProviderCallUsage,
    load_phase4_robustness_profile,
)
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
from eval.phase4_two_deployment_result import (
    DEVELOPMENT_RISK_THRESHOLDS,
    InterviewerToolReplayStatus,
    QualificationCandidateAttemptStatus,
    QualificationCallObservation,
    QualificationObservationSource,
    QualificationResultSourceBindings,
    QualificationResultStatus,
    build_two_deployment_qualification_aggregate_receipt,
    build_two_deployment_qualification_result,
    validate_two_deployment_qualification_aggregate_receipt,
    validate_two_deployment_qualification_result,
)
from eval.prequential import load_session_script


FIXTURES = Path(__file__).parents[1] / "fixtures"
CREATED_AT = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)


@lru_cache(maxsize=1)
def _inputs():
    scope = load_two_deployment_qualification_scope(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_scope_v1.json"
    )
    readiness = load_readiness_bundle(
        FIXTURES / "preference_eval_phase4_together_readiness_v5.json"
    )
    profile = load_phase4_robustness_profile(
        FIXTURES / "preference_eval_phase4_robustness_v1.json"
    )
    suite = load_together_suite(
        FIXTURES / "preference_eval_phase4_together_v5.json"
    )
    fixture = load_fixture(FIXTURES / "preference_eval_dev_v1.json")
    session = load_session_script(
        FIXTURES / "preference_eval_dev_session_v1.json"
    )
    semantic_map = load_authored_semantic_map(
        FIXTURES / "preference_eval_dev_semantic_map_v1.json"
    )
    execution_plan = load_two_deployment_qualification_plan(
        FIXTURES
        / "preference_eval_phase4_two_deployment_qualification_execution_v1.json"
    )
    return (
        scope,
        readiness,
        profile,
        suite,
        fixture,
        session,
        semantic_map,
        execution_plan,
    )


def _parsed_output(role: LLMRole, measure) -> dict[str, object]:
    if role not in {LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT}:
        return {"public_development_result": role.value}
    probability = 1.0 / len(measure.options)
    return LLMReadoutResponseDraft(
        option_probabilities={
            option.option_id: probability for option in measure.options
        },
        settled_probability=0.5,
    ).model_dump(mode="json")


@lru_cache(maxsize=1)
def _observations() -> tuple[QualificationCallObservation, ...]:
    (
        scope,
        readiness,
        profile,
        suite,
        fixture,
        session,
        semantic_map,
        _,
    ) = _inputs()
    measure_by_id = {item.measure_id: item for item in fixture.measures}
    carried_ids = set(readiness.capability_preflight_call_ids)
    entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id in scope.runnable_candidate_ids
    ]
    observations: list[QualificationCallObservation] = []
    for index, entry in enumerate(entries):
        created_at = CREATED_AT + timedelta(microseconds=index + 1)
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=created_at,
        )
        binding = rebuilt.request.binding
        output = _parsed_output(
            entry.coordinate.role,
            measure_by_id[entry.coordinate.measure_id],
        )
        output_sha256 = content_sha256(output)
        authorization_sha256 = content_sha256(
            {"test_authorization": entry.coordinate.call_id}
        )
        usage = ProviderCallUsage(
            call_id=entry.coordinate.call_id,
            segment=BudgetSegment.QUALIFICATION,
            model_candidate_id=entry.coordinate.candidate_id,
            request_sha256=provider_request_content_sha256(binding),
            authorization_sha256=authorization_sha256,
            billed_cost_microusd=0,
            input_tokens=0,
            output_tokens=0,
            cache_hit=False,
            created_at=created_at,
        )
        finalization = ProviderCallFinalization(
            record_version="phase4_provider_call_finalization.v2",
            call_id=entry.coordinate.call_id,
            request_binding_sha256=content_sha256(binding),
            authorization_sha256=authorization_sha256,
            usage_sha256=content_sha256(usage),
            outcome=ProviderCallOutcome.SUCCESS,
            response_sha256=output_sha256,
            response_validation_context_sha256=content_sha256(
                {"test_context": entry.coordinate.call_id}
            ),
            provider_seed_status=ProviderSeedStatus.PROVIDER_CONFIRMED,
            tool_call_count=(
                1 if entry.coordinate.role is LLMRole.INTERVIEWER else 0
            ),
            latency_ms=10.0,
            created_at=created_at,
        )
        carried = entry.coordinate.call_id in carried_ids
        observations.append(
            QualificationCallObservation(
                source_manifest_ordinal=entry.coordinate.ordinal,
                source_entry_sha256=content_sha256(entry),
                call_id=entry.coordinate.call_id,
                candidate_id=entry.coordinate.candidate_id,
                measure_id=entry.coordinate.measure_id,
                measure_version=entry.coordinate.measure_version,
                role=entry.coordinate.role,
                variant_id=entry.coordinate.variant_id,
                source=(
                    QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS
                    if carried
                    else QualificationObservationSource.NEW_QUALIFICATION_CALL
                ),
                request_binding=binding,
                request_binding_sha256=content_sha256(binding),
                request_content_sha256=provider_request_content_sha256(binding),
                usage=usage,
                usage_sha256=content_sha256(usage),
                finalization=finalization,
                finalization_sha256=content_sha256(finalization),
                output_sha256=output_sha256,
                parsed_output=output,
                exact_role_contract_valid=True,
                interviewer_tool_replay_status=(
                    InterviewerToolReplayStatus.HISTORICAL_UNVERIFIABLE
                    if carried and entry.coordinate.role is LLMRole.INTERVIEWER
                    else (
                        InterviewerToolReplayStatus.VERIFIED
                        if entry.coordinate.role is LLMRole.INTERVIEWER
                        else InterviewerToolReplayStatus.NOT_APPLICABLE
                    )
                ),
            )
        )
    return tuple(observations)


def _source_bindings(
    *,
    statuses: dict[str, QualificationCandidateAttemptStatus] | None = None,
) -> QualificationResultSourceBindings:
    scope, _, _, _, _, _, _, execution_plan = _inputs()
    resolved = statuses or {
        item: QualificationCandidateAttemptStatus.COMPLETED
        for item in scope.runnable_candidate_ids
    }
    return QualificationResultSourceBindings(
        execution_plan_sha256=content_sha256(execution_plan),
        carry_bundle_sha256=content_sha256({"test": "carry"}),
        authorization_bundle_sha256=content_sha256({"test": "authorization"}),
        candidate_state_sha256s={
            candidate_id: content_sha256(
                {
                    "test_candidate_state": candidate_id,
                    "status": resolved[candidate_id].value,
                }
            )
            for candidate_id in scope.runnable_candidate_ids
        },
        candidate_attempt_statuses=resolved,
    )


def _build(
    observations: list[QualificationCallObservation] | None = None,
    *,
    source_bindings: QualificationResultSourceBindings | None = None,
):
    scope, readiness, profile, suite, fixture, session, _, execution_plan = (
        _inputs()
    )
    return build_two_deployment_qualification_result(
        scope,
        readiness,
        profile,
        suite,
        fixture,
        session,
        execution_plan,
        source_bindings or _source_bindings(),
        list(observations or _observations()),
        qualification_id="phase4_two_deployment_test",
        qualification_version=1,
        created_at=CREATED_AT + timedelta(hours=1),
    )


def _replace_observation(
    observations: list[QualificationCallObservation],
    replacement: QualificationCallObservation,
) -> list[QualificationCallObservation]:
    return [
        replacement if item.call_id == replacement.call_id else item
        for item in observations
    ]


def _truncate_candidate_after(
    observations: list[QualificationCallObservation],
    terminal: QualificationCallObservation,
) -> list[QualificationCallObservation]:
    execution_plan = _inputs()[7]
    candidate_plan = next(
        item
        for item in execution_plan.candidate_plans
        if item.candidate_id == terminal.candidate_id
    )
    carried_ids = {
        item.call_id
        for item in candidate_plan.calls
        if item.disposition is QualificationCallDisposition.CARRIED_SUCCESS
    }
    provider_ids = [
        item.call_id
        for item in candidate_plan.calls
        if item.disposition is QualificationCallDisposition.EXECUTE_PROVIDER
    ]
    terminal_index = provider_ids.index(terminal.call_id)
    retained_ids = carried_ids | set(provider_ids[: terminal_index + 1])
    return [
        item
        for item in observations
        if item.candidate_id != terminal.candidate_id
        or item.call_id in retained_ids
    ]


def test_complete_result_builds_128_robustness_aggregates_and_selects() -> None:
    result = _build()
    scope, readiness, profile, suite, fixture, session, _, execution_plan = (
        _inputs()
    )

    validate_two_deployment_qualification_result(
        result,
        scope,
        readiness,
        profile,
        suite,
        fixture,
        session,
        execution_plan,
    )

    assert len(result.observations) == 304
    assert len(result.coordinate_results) == 304
    assert result.execution_plan_sha256 == content_sha256(execution_plan)
    assert result.metric_policy_sha256 == execution_plan.metric_policy_sha256
    assert len(result.robustness_slices) == 32
    assert sum(len(item.aggregates) for item in result.robustness_slices) == 128
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id == "together_gpt_oss_120b"
    for candidate in result.candidate_results:
        assert candidate.robustness_aggregate_count == 64
        assert candidate.historical_interviewer_replay_unverifiable_count == 1
        assert candidate.direct_development_metrics is not None
        assert candidate.hybrid_development_metrics is not None
        assert [
            item.threshold
            for item in candidate.direct_development_metrics.risk_coverage
        ] == list(DEVELOPMENT_RISK_THRESHOLDS)


def test_development_accuracy_uses_fractional_credit_for_exact_ties() -> None:
    result = _build()
    fixture = _inputs()[4]
    session = _inputs()[5]
    options_by_measure = {
        item.measure_id: len(item.options) for item in fixture.measures
    }
    expected = sum(
        1.0 / options_by_measure[item.measure_id]
        for item in session.responses
        if item.response_state is ResponseState.CHOICE
    ) / 6

    for candidate in result.candidate_results:
        assert candidate.direct_development_metrics is not None
        assert math.isclose(
            candidate.direct_development_metrics.top_choice_accuracy,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        )


def test_aggregate_receipt_omits_provider_and_parsed_payloads() -> None:
    result = _build()
    receipt = build_two_deployment_qualification_aggregate_receipt(
        result,
        receipt_id="phase4_two_deployment_test_receipt",
    )

    validate_two_deployment_qualification_aggregate_receipt(receipt, result)
    serialized = receipt.model_dump_json()
    assert receipt.coordinate_result_count == 304
    assert receipt.observation_count == 304
    assert '"parsed_output"' not in serialized
    assert '"request_binding"' not in serialized
    assert '"finalization"' not in serialized
    assert '"usage"' not in serialized


def test_aggregate_receipt_omits_planted_provider_output_text() -> None:
    marker = "PLANTED_PROVIDER_OUTPUT_MUST_STAY_PRIVATE"
    observations = list(_observations())
    source = next(
        item
        for item in observations
        if item.role is LLMRole.EVIDENCE_EXTRACTOR
    )
    output = {"planted_private_provider_output": marker}
    output_sha256 = content_sha256(output)
    finalization = source.finalization.model_copy(
        update={"response_sha256": output_sha256}
    )
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "finalization": finalization.model_dump(mode="json"),
            "finalization_sha256": content_sha256(finalization),
            "output_sha256": output_sha256,
            "parsed_output": output,
        }
    )
    result = _build(
        _replace_observation(
            observations,
            QualificationCallObservation.model_validate(payload),
        )
    )
    receipt = build_two_deployment_qualification_aggregate_receipt(
        result,
        receipt_id="phase4_two_deployment_leakage_test_receipt",
    )

    assert marker not in receipt.model_dump_json()


def test_historical_interviewer_replay_cannot_be_upgraded_to_verified() -> None:
    observation = next(
        item
        for item in _observations()
        if item.source
        is QualificationObservationSource.CARRIED_CAPABILITY_SUCCESS
        and item.role is LLMRole.INTERVIEWER
    )
    payload = observation.model_dump(mode="json")
    payload["interviewer_tool_replay_status"] = "verified"

    with pytest.raises(ValidationError, match="overclaims evidence"):
        QualificationCallObservation.model_validate(payload)


def test_execution_plan_metric_policy_is_authoritative() -> None:
    scope, readiness, profile, suite, fixture, session, _, execution_plan = (
        _inputs()
    )
    tampered = execution_plan.model_copy(
        update={"metric_policy_sha256": content_sha256({"wrong": "policy"})}
    )
    bindings = _source_bindings().model_copy(
        update={"execution_plan_sha256": content_sha256(tampered)}
    )

    with pytest.raises(ValueError, match="execution plan binding differs"):
        build_two_deployment_qualification_result(
            scope,
            readiness,
            profile,
            suite,
            fixture,
            session,
            tampered,
            bindings,
            list(_observations()),
            qualification_id="phase4_two_deployment_bad_policy",
            qualification_version=1,
            created_at=CREATED_AT + timedelta(hours=1),
        )


def test_missing_exact_observation_blocks_result() -> None:
    with pytest.raises(
        ValueError,
        match="completed qualification candidate is partial",
    ):
        _build(list(_observations())[:-1])


def test_provider_failure_pauses_globally_without_selection() -> None:
    observations = list(_observations())
    source = next(
        item
        for item in observations
        if item.source is QualificationObservationSource.NEW_QUALIFICATION_CALL
        and item.role is LLMRole.ONTOLOGY_PROPOSER
    )
    finalization = source.finalization.model_copy(
        update={
            "outcome": ProviderCallOutcome.PROVIDER_ERROR,
            "response_sha256": None,
            "failure_code": "together_http_500",
        }
    )
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "finalization": finalization.model_dump(mode="json"),
            "finalization_sha256": content_sha256(finalization),
            "output_sha256": None,
            "parsed_output": None,
            "exact_role_contract_valid": None,
        }
    )
    replacement = QualificationCallObservation.model_validate(payload)
    observations = _replace_observation(observations, replacement)
    observations = _truncate_candidate_after(observations, replacement)
    statuses = {
        candidate_id: (
            QualificationCandidateAttemptStatus.PROVIDER_PAUSED
            if candidate_id == replacement.candidate_id
            else QualificationCandidateAttemptStatus.COMPLETED
        )
        for candidate_id in _inputs()[0].runnable_candidate_ids
    }
    result = _build(
        observations,
        source_bindings=_source_bindings(statuses=statuses),
    )

    assert result.status is (
        QualificationResultStatus.PAUSED_PENDING_PROVIDER_REVIEW
    )
    assert result.selected_candidate_id is None
    affected = next(
        item
        for item in result.candidate_results
        if item.candidate_id == replacement.candidate_id
    )
    assert affected.passed_hard_gates is None
    assert affected.non_observed_coordinate_count > 0
    assert len(result.coordinate_results) == 304


def test_partial_substantive_failure_allows_complete_candidate_selection() -> None:
    observations = list(_observations())
    source = next(
        item
        for item in observations
        if item.candidate_id == "together_glm_5_2"
        and item.source is QualificationObservationSource.NEW_QUALIFICATION_CALL
    )
    finalization = source.finalization.model_copy(
        update={
            "outcome": ProviderCallOutcome.INVALID_OUTPUT,
            "response_sha256": None,
            "failure_code": "structured_output_invalid",
        }
    )
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "finalization": finalization.model_dump(mode="json"),
            "finalization_sha256": content_sha256(finalization),
            "output_sha256": None,
            "parsed_output": None,
            "exact_role_contract_valid": False,
        }
    )
    replacement = QualificationCallObservation.model_validate(payload)
    observations = _replace_observation(observations, replacement)
    observations = _truncate_candidate_after(observations, replacement)
    statuses = {
        candidate_id: (
            QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE
            if candidate_id == replacement.candidate_id
            else QualificationCandidateAttemptStatus.COMPLETED
        )
        for candidate_id in _inputs()[0].runnable_candidate_ids
    }

    result = _build(
        observations,
        source_bindings=_source_bindings(statuses=statuses),
    )

    failed = next(
        item
        for item in result.candidate_results
        if item.candidate_id == replacement.candidate_id
    )
    assert failed.passed_hard_gates is False
    assert failed.non_observed_coordinate_count > 0
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id == "together_gpt_oss_120b"


def test_invalid_final_output_preserves_clean_interviewer_tool_replay() -> None:
    observations = list(_observations())
    source = next(
        item
        for item in observations
        if item.candidate_id == "together_glm_5_2"
        and item.source is QualificationObservationSource.NEW_QUALIFICATION_CALL
        and item.role is LLMRole.INTERVIEWER
    )
    finalization = source.finalization.model_copy(
        update={
            "outcome": ProviderCallOutcome.INVALID_OUTPUT,
            "response_sha256": None,
            "failure_code": "structured_output_invalid",
        }
    )
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "finalization": finalization.model_dump(mode="json"),
            "finalization_sha256": content_sha256(finalization),
            "output_sha256": None,
            "parsed_output": None,
            "exact_role_contract_valid": False,
            "interviewer_tool_replay_status": "verified",
        }
    )
    replacement = QualificationCallObservation.model_validate(payload)
    observations = _replace_observation(observations, replacement)
    observations = _truncate_candidate_after(observations, replacement)
    statuses = {
        candidate_id: (
            QualificationCandidateAttemptStatus.CANDIDATE_HARD_FAILURE
            if candidate_id == replacement.candidate_id
            else QualificationCandidateAttemptStatus.COMPLETED
        )
        for candidate_id in _inputs()[0].runnable_candidate_ids
    }

    result = _build(
        observations,
        source_bindings=_source_bindings(statuses=statuses),
    )

    failed = next(
        item
        for item in result.candidate_results
        if item.candidate_id == replacement.candidate_id
    )
    assert failed.interviewer_tool_replay_failure_count == 0
    assert "interviewer_tool_replay_failure" not in failed.hard_failure_reasons
    assert "invalid_structured_output" in failed.hard_failure_reasons


def test_strict_transform_failure_does_not_block_other_candidate_selection() -> None:
    observations = list(_observations())
    source = next(
        item
        for item in observations
        if item.candidate_id == "together_glm_5_2"
        and item.role is LLMRole.DIRECT_READOUT
        and item.variant_id is QualificationVariant.OPTION_ORDER_1
    )
    fixture = _inputs()[4]
    measure = next(
        item for item in fixture.measures if item.measure_id == source.measure_id
    )
    probabilities = {item.option_id: 0.0 for item in measure.options}
    probabilities[measure.options[1].option_id] = 1.0
    output = LLMReadoutResponseDraft(
        option_probabilities=probabilities,
        settled_probability=1.0,
    ).model_dump(mode="json")
    output_sha256 = content_sha256(output)
    finalization = source.finalization.model_copy(
        update={"response_sha256": output_sha256}
    )
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "finalization": finalization.model_dump(mode="json"),
            "finalization_sha256": content_sha256(finalization),
            "output_sha256": output_sha256,
            "parsed_output": output,
        }
    )
    replacement = QualificationCallObservation.model_validate(payload)
    result = _build(_replace_observation(observations, replacement))

    glm = next(
        item
        for item in result.candidate_results
        if item.candidate_id == "together_glm_5_2"
    )
    assert glm.passed_hard_gates is False
    assert "strict_transform_top_choice_flip" in glm.hard_failure_reasons
    assert result.status is QualificationResultStatus.SELECTED
    assert result.selected_candidate_id == "together_gpt_oss_120b"
