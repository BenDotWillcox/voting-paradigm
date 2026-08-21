from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_capability import (
    CAPABILITY_CALL_COUNT,
    CAPABILITY_MAX_SPEND_MICROUSD,
    CapabilityInterviewerTools,
    TogetherCapabilityExecutionState,
    TogetherCapabilityPlan,
    build_capability_authorization_bundle,
    capability_plan_summary,
    execute_capability_preflight,
    validate_capability_execution_state,
    validate_capability_plan,
)
from eval.phase4_interviewer import (
    PairReference,
    ReadCandidateQuestionScoresRequest,
    ReadEvidenceConflictsRequest,
    ReadEvidenceCoverageRequest,
    ReadPosteriorUncertaintyRequest,
)
from eval.phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderCallOutcome,
    ProviderSeedStatus,
    ProviderTransportResult,
)
from eval.phase4_readiness import (
    load_readiness_bundle,
    rebuild_qualification_call,
)
from eval.phase4_robustness import BudgetSegment, LLMRole
from eval.phase4_robustness import load_phase4_robustness_profile
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
from eval.prequential import load_session_script
from eval.prepare_phase4_together_capability import main as prepare_main
from eval.run_phase4_together_capability import main as run_main
from eval.tests.test_phase4_together_live import catalog_bundle
from eval.validate_phase4_capability import main as validate_main


FIXTURES = Path(__file__).parents[1] / "fixtures"
PLAN_PATH = FIXTURES / "preference_eval_phase4_together_capability_v1.json"
READINESS_PATH = (
    FIXTURES / "preference_eval_phase4_together_readiness_v2.json"
)
SUITE_PATH = FIXTURES / "preference_eval_phase4_together_v2.json"
PROFILE_PATH = FIXTURES / "preference_eval_phase4_robustness_v1.json"
DEV_FIXTURE_PATH = FIXTURES / "preference_eval_dev_v1.json"
DEV_SESSION_PATH = FIXTURES / "preference_eval_dev_session_v1.json"
DEV_MAP_PATH = FIXTURES / "preference_eval_dev_semantic_map_v1.json"
NOW = datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc)


def public_inputs():
    return (
        load_together_suite(SUITE_PATH),
        load_phase4_robustness_profile(PROFILE_PATH),
        load_readiness_bundle(READINESS_PATH),
        load_fixture(DEV_FIXTURE_PATH),
        load_session_script(DEV_SESSION_PATH),
        load_authored_semantic_map(DEV_MAP_PATH),
    )


def capability_plan() -> TogetherCapabilityPlan:
    return TogetherCapabilityPlan.model_validate_json(
        PLAN_PATH.read_text(encoding="utf-8")
    )


def capability_authorization():
    suite, profile, readiness, _, _, _ = public_inputs()
    return build_capability_authorization_bundle(
        capability_plan(),
        suite,
        profile,
        readiness,
        catalog_bundle(suite),
        bundle_id="together_capability_authorization_test",
        approval_id="together_capability_approval_test",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


class TickClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


class DeterministicCapabilityTransport:
    def __init__(
        self,
        clock: TickClock,
        *,
        fail_at: int | None = None,
        omit_interviewer_tool: bool = False,
    ) -> None:
        self.clock = clock
        self.fail_at = fail_at
        self.omit_interviewer_tool = omit_interviewer_tool
        self.requests: list[PrivateStructuredProviderRequest] = []

    def validate_execution(
        self,
        request: PrivateStructuredProviderRequest,
        *,
        segment: BudgetSegment,
    ) -> None:
        assert segment is BudgetSegment.QUALIFICATION
        self.requests.append(request.model_copy(deep=True))

    def _output(self, request: PrivateStructuredProviderRequest):
        role = request.binding.role
        if role is LLMRole.INTERVIEWER:
            return {
                "record_version": "phase4_pause_and_resume.v1",
                "action": "pause_and_resume",
            }
        if role in {LLMRole.EVIDENCE_EXTRACTOR, LLMRole.ONTOLOGY_PROPOSER}:
            return []
        input_payload = request.input_payload
        assert isinstance(input_payload, dict)
        target = input_payload["target_measure"]
        assert isinstance(target, dict)
        options = target["options"]
        assert isinstance(options, list)
        option_ids = [item["option_id"] for item in options]
        probability = 1.0 / len(option_ids)
        return {
            "record_version": "phase4_llm_readout_response.v1",
            "option_probabilities": {
                option_id: probability for option_id in option_ids
            },
            "settled_probability": probability,
            "supporting_evidence_event_ids": [],
            "unsupported_assumptions": [],
        }

    def invoke(
        self,
        request: PrivateStructuredProviderRequest,
    ) -> ProviderTransportResult:
        call_number = len(self.requests)
        failed = call_number == self.fail_at
        interviewer = request.binding.role is LLMRole.INTERVIEWER
        tool_count = int(
            interviewer and not self.omit_interviewer_tool and not failed
        )
        return ProviderTransportResult(
            outcome=(
                ProviderCallOutcome.PROVIDER_ERROR
                if failed
                else ProviderCallOutcome.SUCCESS
            ),
            output_payload=None if failed else self._output(request),
            input_tokens=10,
            output_tokens=10,
            provider_request_id=f"capability-request-{call_number}",
            provider_request_sent=True,
            provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
            tool_call_count=tool_count,
            tool_call_failure_count=0,
            latency_ms=1.0,
            failure_code="test_provider_failure" if failed else None,
            completed_at=self.clock(),
        )


def execute_with(
    transport: DeterministicCapabilityTransport,
    clock: TickClock,
    *,
    prior_state: TogetherCapabilityExecutionState | None = None,
    checkpoints: list[TogetherCapabilityExecutionState] | None = None,
) -> TogetherCapabilityExecutionState:
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()
    return execute_capability_preflight(
        capability_plan(),
        capability_authorization(),
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
        transport,
        state_id="together_capability_state_test",
        ledger_id="together_capability_ledger_test",
        journal_id="together_capability_journal_test",
        clock=clock,
        prior_state=prior_state,
        checkpoint=(checkpoints.append if checkpoints is not None else None),
    )


def test_tracked_capability_plan_validates_and_records_zero_spend():
    plan = capability_plan()
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()

    validate_capability_plan(
        plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )
    summary = capability_plan_summary(plan)

    assert summary["plan_sha256"] == (
        "0b64351c2fb914a0e9d7e21628a291fedddd9647c619ed71c6a532537f9c850f"
    )
    assert summary["call_count"] == CAPABILITY_CALL_COUNT
    assert summary["interviewer_tool_probe_count"] == 3
    assert summary["projected_cost_microusd"] == 76_505
    assert summary["all_calls_authorized_max_cost_microusd"] == 129_000
    assert summary["capability_max_spend_microusd"] == 150_000
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0


def test_qualification_calls_rebuild_at_fresh_times_without_semantic_drift():
    plan = capability_plan()
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()

    for index, (call, entry) in enumerate(
        zip(plan.calls, readiness.qualification_manifest.entries),
        start=1,
    ):
        created_at = NOW + timedelta(seconds=index)
        rebuilt = rebuild_qualification_call(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            entry,
            created_at=created_at,
        )
        assert rebuilt.request.binding.created_at == created_at
        assert rebuilt.request.binding.call_id == call.call_id
        assert rebuilt.request.binding.model_candidate_id == call.candidate_id
        assert rebuilt.request.binding.role is call.role
        if index == CAPABILITY_CALL_COUNT:
            break


def test_capability_interviewer_tools_cover_the_complete_live_surface():
    tools = CapabilityInterviewerTools(["item_a", "item_b"])
    uncertainty = tools.read_posterior_uncertainty(
        ReadPosteriorUncertaintyRequest(
            pair=PairReference(item_a="item_a", item_b="item_b")
        )
    )
    scores = tools.read_candidate_question_scores(
        ReadCandidateQuestionScoresRequest()
    )
    coverage = tools.read_evidence_coverage(ReadEvidenceCoverageRequest())
    conflicts = tools.read_evidence_conflicts(ReadEvidenceConflictsRequest())

    assert uncertainty.posterior_gap_std == 1.0
    assert scores.candidates == []
    assert coverage.item_count == 2
    assert coverage.possible_pair_count == 1
    assert conflicts.conflicts == []


def test_capability_plan_rejects_a_tampered_readiness_binding():
    payload = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    payload["calls"][0]["request_template_sha256"] = "0" * 64
    plan = TogetherCapabilityPlan.model_validate(payload)
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()

    with pytest.raises(ValueError, match="does not rebuild"):
        validate_capability_plan(
            plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )


def test_execution_revalidates_the_plan_before_reaching_transport():
    payload = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    original = payload["calls"][0]["authorized_max_cost_microusd"]
    payload["calls"][0]["authorized_max_cost_microusd"] = 0
    payload["all_calls_authorized_max_cost_microusd"] -= original
    plan = TogetherCapabilityPlan.model_validate(payload)
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()
    clock = TickClock(NOW)
    transport = DeterministicCapabilityTransport(clock)

    with pytest.raises(ValueError, match="does not rebuild"):
        execute_capability_preflight(
            plan,
            capability_authorization(),
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            transport,
            state_id="tampered_capability_state",
            ledger_id="tampered_capability_ledger",
            journal_id="tampered_capability_journal",
            clock=clock,
        )
    assert transport.requests == []


def test_successful_capability_execution_builds_an_exact_receipt():
    clock = TickClock(NOW)
    checkpoints: list[TogetherCapabilityExecutionState] = []
    transport = DeterministicCapabilityTransport(clock)

    state = execute_with(transport, clock, checkpoints=checkpoints)
    suite, profile, _, _, _, _ = public_inputs()
    validate_capability_execution_state(
        state,
        capability_plan(),
        capability_authorization(),
        suite,
        profile,
    )

    assert state.receipt is not None
    assert len(state.receipt.checks) == CAPABILITY_CALL_COUNT
    assert len(state.outputs) == CAPABILITY_CALL_COUNT
    assert len(checkpoints) == CAPABILITY_CALL_COUNT + 1
    assert state.receipt.provider_spend_microusd < (
        CAPABILITY_MAX_SPEND_MICROUSD
    )
    assert sum(
        item.interviewer_tool_calling_passed is True
        for item in state.receipt.checks
    ) == 3


def test_progressive_output_metadata_is_bound_to_the_exact_plan():
    clock = TickClock(NOW)
    state = execute_with(DeterministicCapabilityTransport(clock), clock)
    state.outputs[0].candidate_id = state.outputs[5].candidate_id
    suite, profile, _, _, _, _ = public_inputs()

    with pytest.raises(ValueError, match="cover successful calls"):
        validate_capability_execution_state(
            state,
            capability_plan(),
            capability_authorization(),
            suite,
            profile,
        )


def test_failed_attempt_checkpoints_and_cannot_resume_past_failure():
    clock = TickClock(NOW)
    checkpoints: list[TogetherCapabilityExecutionState] = []
    transport = DeterministicCapabilityTransport(clock, fail_at=2)

    with pytest.raises(ValueError, match="did not succeed"):
        execute_with(transport, clock, checkpoints=checkpoints)

    failed = checkpoints[-1]
    assert len(failed.provider_ledger.calls) == 2
    assert len(failed.outputs) == 1
    with pytest.raises(ValueError, match="attempt is terminal"):
        execute_with(
            DeterministicCapabilityTransport(clock),
            clock,
            prior_state=failed,
        )


def test_interviewer_without_a_real_tool_call_fails_the_gate():
    clock = TickClock(NOW)
    checkpoints: list[TogetherCapabilityExecutionState] = []
    transport = DeterministicCapabilityTransport(
        clock,
        omit_interviewer_tool=True,
    )

    with pytest.raises(ValueError, match="did not call a tool"):
        execute_with(transport, clock, checkpoints=checkpoints)

    assert len(checkpoints[-1].provider_ledger.calls) == 4
    assert checkpoints[-1].receipt is None
    with pytest.raises(ValueError, match="attempt is terminal"):
        execute_with(
            DeterministicCapabilityTransport(clock),
            clock,
            prior_state=checkpoints[-1],
        )


def test_execution_rejects_an_expired_manual_approval_before_transport():
    plan = capability_plan()
    suite, profile, readiness, fixture, session, semantic_map = public_inputs()
    authorization = capability_authorization()
    clock = TickClock(authorization.manual_approval.expires_at)
    transport = DeterministicCapabilityTransport(clock)

    with pytest.raises(ValueError, match="approval is not active"):
        execute_capability_preflight(
            plan,
            authorization,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            transport,
            state_id="expired_capability_state",
            ledger_id="expired_capability_ledger",
            journal_id="expired_capability_journal",
            clock=clock,
        )
    assert transport.requests == []


def test_prepare_cli_rebuilds_the_tracked_plan_without_network(tmp_path, capsys):
    output = tmp_path / "capability-plan.json"
    result = prepare_main(
        [
            str(SUITE_PATH),
            str(PROFILE_PATH),
            str(READINESS_PATH),
            str(DEV_FIXTURE_PATH),
            str(DEV_SESSION_PATH),
            str(DEV_MAP_PATH),
            str(output),
        ]
    )

    assert result == 0
    rebuilt = TogetherCapabilityPlan.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert rebuilt == capability_plan()
    assert "provider_spend_microusd" in capsys.readouterr().out


def test_run_cli_cannot_reach_files_or_network_without_paid_confirmation(
    capsys,
    monkeypatch,
):
    def reject_file_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("paid runner read a file before confirmation")

    monkeypatch.setattr(Path, "read_text", reject_file_read)
    missing = "missing.json"
    result = run_main(
        [
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            "--confirm-max-spend-microusd",
            str(CAPABILITY_MAX_SPEND_MICROUSD),
        ]
    )

    assert result == 1
    assert "authoring validation failed" in capsys.readouterr().err


def test_validation_cli_emits_only_aggregate_plan_fields(capsys):
    result = validate_main(
        [
            str(PLAN_PATH),
            str(SUITE_PATH),
            str(PROFILE_PATH),
            str(READINESS_PATH),
            str(DEV_FIXTURE_PATH),
            str(DEV_SESSION_PATH),
            str(DEV_MAP_PATH),
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "call_count" in output
    assert capability_plan().calls[0].call_id not in output
    assert content_sha256(load_fixture(DEV_FIXTURE_PATH)) not in output
