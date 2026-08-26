from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_capability import TogetherCapabilityPlan
from eval.phase4_capability_adjudication import (
    build_adjudicated_candidate_authorization,
    build_capability_adjudication_policy,
)
from eval.phase4_capability_continuation import (
    candidate_plan_for,
    execute_candidate_capability_preflight,
)
from eval.phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    TogetherCapabilityDeltaPlan,
    build_capability_delta_plan,
    build_capability_delta_source_proof,
    build_delta_candidate_authorization_bundle,
    capability_delta_summary,
    delta_candidate_plan_for,
    execute_delta_candidate_capability_preflight,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
    rerun_calls_for_candidate,
    validate_capability_delta_execution_inputs,
    validate_capability_delta_plan,
    validate_capability_delta_source_proof,
    validate_delta_candidate_execution_state,
)
from eval.phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST,
)
from eval.phase4_readiness import load_readiness_bundle
from eval.phase4_robustness import LLMRole
from eval.phase4_together import load_together_suite
from eval.tests.test_phase4_capability import (
    NOW,
    DeterministicCapabilityTransport,
    TickClock,
    capability_plan,
    public_inputs,
)
from eval.tests.test_phase4_capability_continuation import (
    candidate_authorization as source_candidate_authorization,
    corrected_inputs as source_corrected_inputs,
    corrected_plan as source_corrected_plan,
    failed_source_attempts,
    provisional_schema_failure,
)
from eval.tests.test_phase4_together_live import catalog_bundle


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "eval" / "fixtures"
DELTA_PATH = (
    FIXTURES / "preference_eval_phase4_together_capability_delta_v1.json"
)
SOURCE_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_delta_source_proof_v1.json"
)


def _load_json(model_type, path: Path):
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


class InvalidEvidenceCapabilityTransport(DeterministicCapabilityTransport):
    def _output(self, request):
        if request.binding.role is LLMRole.EVIDENCE_EXTRACTOR:
            return {"unexpected": "content omitted from the diagnostic"}
        return super()._output(request)


def _synthetic_source_attempts():
    continuation, glm_authorization, glm_state, _ = provisional_schema_failure()
    source_plan = source_corrected_plan()
    source_suite, profile, source_readiness, fixture, session, semantic_map = (
        source_corrected_inputs()
    )
    glm_terminal_at = glm_state.provider_journal.finalizations[-1].created_at
    policy = build_capability_adjudication_policy(
        continuation,
        source_plan,
        source_suite,
        profile,
        glm_authorization,
        glm_state,
        policy_id="synthetic_capability_adjudication_v1",
        policy_version=1,
        created_at=glm_terminal_at + timedelta(seconds=1),
    )
    attempts = [(glm_authorization, glm_state, None)]
    historical_suite, _, historical_readiness, _, _, _ = public_inputs()
    continuation_sources = failed_source_attempts()
    for offset, candidate_id in enumerate(
        (
            "together_gpt_oss_120b",
            "together_nemotron_3_ultra_550b_a55b",
        ),
        start=1,
    ):
        plan = candidate_plan_for(continuation, candidate_id)
        authorization = source_candidate_authorization(
            continuation,
            candidate_id,
        )
        adjudicated_authorization = build_adjudicated_candidate_authorization(
            policy,
            authorization,
        )
        clock = TickClock(NOW + timedelta(minutes=10 + offset))
        checkpoints = []
        diagnostics = []
        with pytest.raises(ValueError, match="did not succeed"):
            execute_candidate_capability_preflight(
                continuation,
                capability_plan(),
                source_plan,
                continuation_sources,
                historical_suite,
                historical_readiness,
                plan,
                authorization,
                source_suite,
                profile,
                source_readiness,
                fixture,
                session,
                semantic_map,
                catalog_bundle(source_suite),
                InvalidEvidenceCapabilityTransport(clock),
                state_id=f"{candidate_id}_synthetic_harness_failure_state",
                ledger_id=f"{candidate_id}_synthetic_harness_failure_ledger",
                journal_id=f"{candidate_id}_synthetic_harness_failure_journal",
                clock=clock,
                authorization_binding_sha256=content_sha256(
                    adjudicated_authorization
                ),
                checkpoint=checkpoints.append,
                validation_diagnostic_sink=diagnostics.append,
            )
        assert len(diagnostics) == 1
        attempts.append(
            (
                adjudicated_authorization,
                checkpoints[-1],
                diagnostics[0],
            )
        )
    return (
        policy,
        continuation,
        source_plan,
        source_suite,
        profile,
        attempts,
        source_readiness,
        fixture,
        session,
        semantic_map,
    )


@lru_cache(maxsize=1)
def _cached_delta_inputs():
    (
        policy,
        continuation,
        source_plan,
        source_suite,
        profile,
        attempts,
        source_readiness,
        fixture,
        session,
        semantic_map,
    ) = _synthetic_source_attempts()
    corrected_plan = _load_json(
        TogetherCapabilityPlan,
        FIXTURES / "preference_eval_phase4_together_capability_v3.json",
    )
    corrected_suite = load_together_suite(
        FIXTURES / "preference_eval_phase4_together_v4.json"
    )
    corrected_readiness = load_readiness_bundle(
        FIXTURES / "preference_eval_phase4_together_readiness_v4.json"
    )
    return (
        policy,
        continuation,
        source_plan,
        source_suite,
        profile,
        attempts,
        corrected_plan,
        corrected_suite,
        corrected_readiness,
        source_readiness,
        fixture,
        session,
        semantic_map,
    )


def _delta_inputs():
    return deepcopy(_cached_delta_inputs())


def _build_delta(inputs=None) -> TogetherCapabilityDeltaPlan:
    inputs = inputs or _delta_inputs()
    latest_terminal = max(
        state.provider_journal.finalizations[-1].created_at
        for _, state, _ in inputs[5]
    )
    return build_capability_delta_plan(
        *inputs[:10],
        PROVIDER_RESPONSE_INVARIANT_MANIFEST,
        *inputs[10:],
        plan_id="phase4_together_capability_delta_v1",
        plan_version=1,
        created_at=latest_terminal + timedelta(minutes=1),
    )


def _build_source_proof(delta, inputs):
    return build_capability_delta_source_proof(
        delta,
        *inputs[:10],
        PROVIDER_RESPONSE_INVARIANT_MANIFEST,
        *inputs[10:],
        proof_id="synthetic_capability_delta_source_proof_v1",
        proof_version=1,
        validated_at=delta.created_at,
    )


def test_tracked_delta_source_proof_is_content_free_and_hash_pinned():
    delta = load_capability_delta_plan(DELTA_PATH)
    source_proof = load_capability_delta_source_proof(SOURCE_PROOF_PATH)

    validate_capability_delta_source_proof(source_proof, delta)

    assert content_sha256(delta) == (
        "25d286a8ceb16373e6868bb62bd81d3cf9b4cb0d2255f4ce02f66b2d4687f8e2"
    )
    assert content_sha256(source_proof) == (
        "58d65a797d832a39ae1c3e2f65cddff893a296e04fa88b07f97ab89a187d5b15"
    )
    assert source_proof.full_private_source_rebuild_passed is True
    assert source_proof.values_messages_and_context_omitted is True


def test_delta_partitions_exact_four_carried_and_eleven_rerun_coordinates():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    carried = {
        (item.candidate_id, item.role)
        for item in delta.carried_forward_successes
    }
    rerun = {(item.candidate_id, item.role) for item in delta.rerun_calls}

    assert carried == {
        ("together_glm_5_2", LLMRole.DIRECT_READOUT),
        ("together_glm_5_2", LLMRole.HYBRID_READOUT),
        ("together_gpt_oss_120b", LLMRole.DIRECT_READOUT),
        (
            "together_nemotron_3_ultra_550b_a55b",
            LLMRole.DIRECT_READOUT,
        ),
    }
    assert len(rerun) == 11
    candidate_ids = {item.candidate_id for item in delta.source_attempts}
    assert carried | rerun == {
        (candidate_id, role)
        for candidate_id in candidate_ids
        for role in LLMRole
    }
    assert not carried & rerun
    assert [item.terminal_role for item in delta.source_attempts] == [
        LLMRole.ONTOLOGY_PROPOSER,
        LLMRole.EVIDENCE_EXTRACTOR,
        LLMRole.EVIDENCE_EXTRACTOR,
    ]
    assert [item.provider_call_count for item in delta.source_attempts] == [
        5,
        2,
        2,
    ]
    assert [item.validation_error_count for item in delta.source_attempts] == [
        0,
        1,
        1,
    ]


def test_delta_reruns_glm_extractor_interviewer_and_ontology():
    delta = _build_delta()

    assert [
        item.role
        for item in rerun_calls_for_candidate(delta, "together_glm_5_2")
    ] == [
        LLMRole.EVIDENCE_EXTRACTOR,
        LLMRole.INTERVIEWER,
        LLMRole.ONTOLOGY_PROPOSER,
    ]
    for candidate_id in (
        "together_gpt_oss_120b",
        "together_nemotron_3_ultra_550b_a55b",
    ):
        assert [
            item.role for item in rerun_calls_for_candidate(delta, candidate_id)
        ] == [
            LLMRole.EVIDENCE_EXTRACTOR,
            LLMRole.HYBRID_READOUT,
            LLMRole.INTERVIEWER,
            LLMRole.ONTOLOGY_PROPOSER,
        ]


def test_delta_binds_revalidated_unchanged_outputs_and_semantics_manifest():
    delta = _build_delta()

    assert all(
        item.source_call_plan_sha256 != item.corrected_call_plan_sha256
        and item.source_request_binding_sha256
        != item.corrected_request_binding_sha256
        and item.source_transmitted_payload_sha256
        == item.corrected_transmitted_payload_sha256
        and item.source_output_sha256
        == item.corrected_revalidated_output_sha256
        for item in delta.carried_forward_successes
    )
    assert delta.provider_response_semantics_manifest_sha256 == content_sha256(
        PROVIDER_RESPONSE_INVARIANT_MANIFEST
    )


def test_shape_valid_but_request_invalid_output_cannot_carry():
    inputs = list(_delta_inputs())
    attempts = list(inputs[5])
    authorization, state, diagnostic = attempts[1]
    state = state.model_copy(deep=True)
    output = state.outputs[0]
    payload = output.model_dump(mode="json")["output_payload"]
    payload["supporting_evidence_event_ids"] = ["invented_evidence"]
    output_sha256 = content_sha256(payload)
    state.outputs[0] = output.model_copy(
        update={"output_payload": payload, "output_sha256": output_sha256}
    )
    finalizations = [
        item.model_copy(
            update={"response_sha256": output_sha256}
            if item.call_id == output.call_id
            else {}
        )
        for item in state.provider_journal.finalizations
    ]
    state.provider_journal = state.provider_journal.model_copy(
        update={"finalizations": finalizations}
    )
    attempts[1] = (authorization, state, diagnostic)
    inputs[5] = attempts

    with pytest.raises(ValueError, match="ineligible evidence"):
        _build_delta(tuple(inputs))


def test_delta_reconciles_prior_spend_and_exact_rerun_reservations():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)

    source_spend = sum(
        sum(call.billed_cost_microusd for call in state.provider_ledger.calls)
        for _, state, _ in inputs[5]
    )
    assert delta.preceding_provider_spend_microusd == (
        inputs[1].prior_provider_spend_microusd
    )
    assert delta.prior_provider_spend_microusd == (
        delta.preceding_provider_spend_microusd + source_spend
    )
    assert delta.additional_projected_cost_microusd == sum(
        item.projected_cost_microusd for item in delta.rerun_calls
    )
    assert delta.additional_authorized_max_cost_microusd == sum(
        item.authorized_max_cost_microusd for item in delta.rerun_calls
    )
    assert delta.cumulative_worst_case_spend_microusd == (
        delta.prior_provider_spend_microusd
        + delta.additional_authorized_max_cost_microusd
    )
    assert capability_delta_summary(delta)["rerun_call_count"] == 11


def test_delta_rebuild_rejects_an_unreviewed_semantics_manifest():
    inputs = _delta_inputs()
    delta = _build_delta()
    tampered_manifest = PROVIDER_RESPONSE_INVARIANT_MANIFEST.model_copy(
        update={"manifest_version": 2}
    )

    with pytest.raises(ValueError, match="semantics manifest differs"):
        validate_capability_delta_plan(
            delta,
            *inputs[:10],
            tampered_manifest,
            *inputs[10:],
        )


def test_delta_schema_rejects_a_carried_and_rerun_overlap():
    delta = _build_delta()
    payload = delta.model_dump(mode="json")
    payload["rerun_calls"][0] = next(
        item.model_dump(mode="json")
        for item in _delta_inputs()[6].calls
        if (
            item.candidate_id,
            item.role,
        )
        == ("together_glm_5_2", LLMRole.DIRECT_READOUT)
    )

    with pytest.raises(ValueError, match="overlap"):
        TogetherCapabilityDeltaPlan.model_validate(payload)


def test_delta_schema_rejects_a_carried_success_from_another_state():
    delta = _build_delta()
    payload = delta.model_dump(mode="json")
    payload["carried_forward_successes"][0]["source_state_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="another source"):
        TogetherCapabilityDeltaPlan.model_validate(payload)


def test_delta_schema_rejects_a_carried_success_from_an_unknown_candidate():
    delta = _build_delta()
    payload = delta.model_dump(mode="json")
    payload["carried_forward_successes"][0]["candidate_id"] = "aaa"

    with pytest.raises(ValidationError, match="another source"):
        TogetherCapabilityDeltaPlan.model_validate(payload)


def test_delta_source_proof_rejects_a_carry_rerun_swap():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    payload = delta.model_dump(mode="json")
    candidate_id = "together_gpt_oss_120b"
    carried = next(
        item
        for item in payload["carried_forward_successes"]
        if item["candidate_id"] == candidate_id
    )
    carried["role"] = LLMRole.HYBRID_READOUT.value
    rerun_calls = [
        item
        for item in payload["rerun_calls"]
        if not (
            item["candidate_id"] == candidate_id
            and item["role"] == LLMRole.HYBRID_READOUT.value
        )
    ]
    rerun_calls.append(
        next(
            item.model_dump(mode="json")
            for item in inputs[6].calls
            if item.candidate_id == candidate_id
            and item.role is LLMRole.DIRECT_READOUT
        )
    )
    rerun_calls.sort(key=lambda item: item["ordinal"])
    payload["rerun_calls"] = rerun_calls
    payload["additional_projected_cost_microusd"] = sum(
        item["projected_cost_microusd"] for item in rerun_calls
    )
    payload["additional_authorized_max_cost_microusd"] = sum(
        item["authorized_max_cost_microusd"] for item in rerun_calls
    )
    payload["cumulative_worst_case_spend_microusd"] = (
        payload["prior_provider_spend_microusd"]
        + payload["additional_authorized_max_cost_microusd"]
    )
    forged_delta = TogetherCapabilityDeltaPlan.model_validate(payload)

    with pytest.raises(ValueError, match="source proof bindings differ"):
        validate_capability_delta_execution_inputs(
            forged_delta,
            source_proof,
            inputs[6],
            inputs[7],
            inputs[4],
            inputs[8],
            inputs[10],
            inputs[11],
            inputs[12],
        )


def test_recovery_sources_never_read_private_runs(monkeypatch):
    original = Path.read_text

    def guarded_read_text(path, *args, **kwargs):
        if "private_runs" in path.parts:
            raise AssertionError("synthetic recovery tests read private_runs")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    _cached_delta_inputs.cache_clear()
    delta = _build_delta(_delta_inputs())

    assert len(delta.source_attempts) == 3


class DeltaSemanticTransport(DeterministicCapabilityTransport):
    def _output(self, request):
        payload = request.input_payload
        assert isinstance(payload, dict)
        conformance = payload.get("provider_response_conformance")
        if request.binding.role is LLMRole.INTERVIEWER:
            assert isinstance(conformance, dict)
            return {
                "record_version": "phase4_ask_vetted_question.v1",
                "action": "ask_vetted_question",
                "question": conformance["expected_vetted_question"],
                "rendering_mode": "canonical_vetted",
            }
        if request.binding.role is LLMRole.EVIDENCE_EXTRACTOR:
            assert isinstance(conformance, dict)
            claim = conformance["required_claim"]
            assert isinstance(claim, dict)
            return [
                {
                    "source_message_ids": [
                        conformance["required_source_message_id"]
                    ],
                    "claim": {
                        "claim_text": "Public capability claim.",
                        **claim,
                    },
                    "extractor_confidence": 0.9,
                    "unsupported_assumptions": [],
                }
            ]
        if request.binding.role is LLMRole.ONTOLOGY_PROPOSER:
            assert isinstance(conformance, dict)
            return [
                {
                    "source_message_ids": [
                        conformance["required_source_message_id"]
                    ],
                    "proposed_dimension": {
                        "dimension_id": "reversible_process_probe",
                        "name": "Reversible process",
                        "definition": (
                            "Preference for a civic process that can repair "
                            "errors."
                        ),
                        "interpretation": (
                            "Higher values favor clearer reversible paths."
                        ),
                    },
                    "supporting_evidence_event_ids": [
                        conformance["required_evidence_event_id"]
                    ],
                    "candidate_duplicate_dimension_ids": [],
                    "extractor_confidence": 0.8,
                    "unsupported_assumptions": [],
                }
            ]
        return super()._output(request)


class InvalidDeltaOntologyTransport(DeltaSemanticTransport):
    def _output(self, request):
        if request.binding.role is LLMRole.ONTOLOGY_PROPOSER:
            return []
        return super()._output(request)


class DeltaTokenOverrunTransport(DeltaSemanticTransport):
    def __init__(self, clock: TickClock, *, input_tokens: int) -> None:
        super().__init__(clock)
        self.input_tokens = input_tokens

    def invoke(self, request):
        result = super().invoke(request)
        return result.model_copy(
            update={"input_tokens": self.input_tokens, "output_tokens": 0}
        )


def test_delta_candidate_authorization_and_execution_follow_exact_order():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    corrected_plan = inputs[6]
    suite = inputs[7]
    readiness = inputs[8]
    profile = inputs[4]
    fixture, session, semantic_map = inputs[10:]
    expected = [
        ("together_glm_5_2", 3),
        ("together_gpt_oss_120b", 4),
        ("together_nemotron_3_ultra_550b_a55b", 4),
    ]
    prior_attempts = []
    for position, (candidate_id, expected_call_count) in enumerate(expected):
        plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            candidate_id,
        )
        now = delta.created_at + timedelta(minutes=1 + position)
        authorization = build_delta_candidate_authorization_bundle(
            delta,
            source_proof,
            plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog_bundle(suite),
            prior_attempts=prior_attempts,
            bundle_id=f"{candidate_id}_delta_authorization_test",
            approval_id=f"{candidate_id}_delta_approval_test",
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        )
        round_tripped = (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                authorization.model_dump_json()
            )
        )
        clock = TickClock(now)
        checkpoints = []
        state = execute_delta_candidate_capability_preflight(
            delta,
            source_proof,
            corrected_plan,
            plan,
            round_tripped,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog_bundle(suite),
            DeltaSemanticTransport(clock),
            state_id=f"{candidate_id}_delta_state_test",
            ledger_id=f"{candidate_id}_delta_ledger_test",
            journal_id=f"{candidate_id}_delta_journal_test",
            clock=clock,
            prior_attempts=prior_attempts,
            checkpoint=checkpoints.append,
        )

        validate_delta_candidate_execution_state(
            state,
            delta,
            plan,
            round_tripped,
            suite,
            profile,
        )
        assert len(plan.calls) == expected_call_count
        assert round_tripped.candidate_position == position
        assert len(round_tripped.prior_candidate_progress) == position
        assert (
            round_tripped.manual_approval.approved_call_count
            == expected_call_count
        )
        assert state.receipt is not None
        assert len(state.receipt.checks) == expected_call_count
        assert len(checkpoints) == expected_call_count + 1
        prior_attempts.append((round_tripped, state))


def test_delta_candidate_manual_approval_cannot_claim_five_calls_for_glm():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    plan = delta_candidate_plan_for(
        delta,
        inputs[6],
        inputs[7],
        inputs[4],
        inputs[8],
        "together_glm_5_2",
    )
    now = delta.created_at + timedelta(minutes=1)
    authorization = build_delta_candidate_authorization_bundle(
        delta,
        source_proof,
        plan,
        inputs[6],
        inputs[7],
        inputs[4],
        inputs[8],
        catalog_bundle(inputs[7]),
        bundle_id="glm_delta_authorization_test",
        approval_id="glm_delta_approval_test",
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    payload = authorization.model_dump(mode="json")
    payload["manual_approval"]["approved_call_count"] = 5

    with pytest.raises(ValueError, match="count differs"):
        TogetherDeltaCandidateAuthorizationBundle.model_validate(payload)


def test_second_delta_candidate_cannot_omit_the_first_terminal_attempt():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    plan = delta_candidate_plan_for(
        delta,
        inputs[6],
        inputs[7],
        inputs[4],
        inputs[8],
        "together_gpt_oss_120b",
    )
    now = delta.created_at + timedelta(minutes=1)

    with pytest.raises(ValueError, match="outside exact order"):
        build_delta_candidate_authorization_bundle(
            delta,
            source_proof,
            plan,
            inputs[6],
            inputs[7],
            inputs[4],
            inputs[8],
            catalog_bundle(inputs[7]),
            bundle_id="gpt_delta_authorization_without_prefix",
            approval_id="gpt_delta_approval_without_prefix",
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        )


def test_delta_spend_overrun_checkpoints_and_blocks_later_authorization():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    corrected_plan, suite, readiness = inputs[6:9]
    profile = inputs[4]
    fixture, session, semantic_map = inputs[10:]
    glm_plan = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        "together_glm_5_2",
    )
    now = delta.created_at + timedelta(minutes=1)
    glm_authorization = build_delta_candidate_authorization_bundle(
        delta,
        source_proof,
        glm_plan,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle(suite),
        bundle_id="glm_delta_overrun_authorization",
        approval_id="glm_delta_overrun_approval",
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    clock = TickClock(now)
    checkpoints = []
    with pytest.raises(ValueError, match="did not succeed"):
        execute_delta_candidate_capability_preflight(
            delta,
            source_proof,
            corrected_plan,
            glm_plan,
            glm_authorization,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog_bundle(suite),
            DeltaTokenOverrunTransport(clock, input_tokens=72_000),
            state_id="glm_delta_overrun_state",
            ledger_id="glm_delta_overrun_ledger",
            journal_id="glm_delta_overrun_journal",
            clock=clock,
            checkpoint=checkpoints.append,
        )
    terminal_state = checkpoints[-1]

    validate_delta_candidate_execution_state(
        terminal_state,
        delta,
        glm_plan,
        glm_authorization,
        suite,
        profile,
    )
    assert terminal_state.receipt is None
    assert terminal_state.manual_spend_ceiling_breached is True
    assert terminal_state.manual_spend_overrun_microusd > 0
    assert terminal_state.provider_budget_limit_breached is False
    resume_transport = DeltaSemanticTransport(clock)
    with pytest.raises(ValueError, match="attempt is terminal"):
        execute_delta_candidate_capability_preflight(
            delta,
            source_proof,
            corrected_plan,
            glm_plan,
            glm_authorization,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog_bundle(suite),
            resume_transport,
            state_id=terminal_state.state_id,
            ledger_id=terminal_state.provider_ledger.ledger_id,
            journal_id=terminal_state.provider_journal.journal_id,
            clock=clock,
            prior_state=terminal_state,
        )
    assert resume_transport.requests == []

    gpt_plan = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        "together_gpt_oss_120b",
    )
    with pytest.raises(ValueError, match="spend breach blocks"):
        build_delta_candidate_authorization_bundle(
            delta,
            source_proof,
            gpt_plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog_bundle(suite),
            prior_attempts=[(glm_authorization, terminal_state)],
            bundle_id="gpt_delta_after_overrun_authorization",
            approval_id="gpt_delta_after_overrun_approval",
            approved_at=clock(),
            expires_at=clock() + timedelta(hours=1),
        )


def test_delta_semantic_failure_checkpoints_before_writing_diagnostic():
    inputs = _delta_inputs()
    delta = _build_delta(inputs)
    source_proof = _build_source_proof(delta, inputs)
    corrected_plan, suite, readiness = inputs[6:9]
    profile = inputs[4]
    fixture, session, semantic_map = inputs[10:]
    plan = delta_candidate_plan_for(
        delta,
        corrected_plan,
        suite,
        profile,
        readiness,
        "together_glm_5_2",
    )
    now = delta.created_at + timedelta(minutes=1)
    authorization = build_delta_candidate_authorization_bundle(
        delta,
        source_proof,
        plan,
        corrected_plan,
        suite,
        profile,
        readiness,
        catalog_bundle(suite),
        bundle_id="glm_delta_failure_authorization_test",
        approval_id="glm_delta_failure_approval_test",
        approved_at=now,
        expires_at=now + timedelta(hours=1),
    )
    clock = TickClock(now)
    checkpoints = []
    diagnostics = []

    with pytest.raises(ValueError, match="did not succeed"):
        execute_delta_candidate_capability_preflight(
            delta,
            source_proof,
            corrected_plan,
            plan,
            authorization,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog_bundle(suite),
            InvalidDeltaOntologyTransport(clock),
            state_id="glm_delta_failure_state_test",
            ledger_id="glm_delta_failure_ledger_test",
            journal_id="glm_delta_failure_journal_test",
            clock=clock,
            checkpoint=checkpoints.append,
            validation_diagnostic_sink=diagnostics.append,
        )

    assert len(checkpoints) == len(plan.calls)
    assert checkpoints[-1].receipt is None
    assert len(checkpoints[-1].provider_journal.finalizations) == len(plan.calls)
    assert len(diagnostics) == 1
    assert diagnostics[0].role is LLMRole.ONTOLOGY_PROPOSER
