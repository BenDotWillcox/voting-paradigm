from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_capability import TogetherCapabilityPlan
from eval.phase4_capability_recovery import (
    TogetherDeltaCandidateAuthorizationBundle,
    build_delta_candidate_authorization_bundle,
    delta_candidate_plan_for,
    execute_delta_candidate_capability_preflight,
    load_capability_delta_plan,
    load_capability_delta_source_proof,
    load_executable_capability_delta_plan,
    load_executable_capability_delta_source_proof,
    validate_capability_delta_execution_inputs,
    validate_delta_candidate_execution_state,
)
from eval.phase4_provider_semantics import (
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
)
from eval.phase4_readiness import load_readiness_bundle
from eval.phase4_robustness import LLMRole, load_phase4_robustness_profile
from eval.phase4_selector_recovery import (
    TogetherSelectorRecoveryDeltaPlan,
    TogetherSelectorRecoverySourceProof,
    load_selector_recovery_delta,
    load_selector_recovery_source_proof,
    selector_recovery_summary,
    validate_selector_recovery_public_artifacts,
    validate_selector_recovery_source_proof,
)
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
from eval.phase4_together_live import (
    TogetherCatalogPreflightBundle,
    build_catalog_preflight_authorization,
    build_catalog_preflight_receipt,
)
from eval.prequential import load_session_script
from eval import prepare_phase4_together_selector_recovery as prepare_cli
from eval import validate_phase4_selector_recovery as validate_public_cli
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_capability_recovery import DeltaSemanticTransport
from eval.tests.test_phase4_together_live import (
    account_attestation,
    live_model_payload,
    public_sources,
)


FIXTURES = Path(__file__).parents[1] / "fixtures"
DELTA_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_selector_recovery_delta_v2.json"
)
PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_selector_recovery_source_proof_v2.json"
)
PARENT_DELTA_PATH = (
    FIXTURES / "preference_eval_phase4_together_capability_delta_v1.json"
)
PARENT_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_delta_source_proof_v1.json"
)


def _public_inputs():
    return (
        load_selector_recovery_delta(DELTA_PATH),
        load_selector_recovery_source_proof(PROOF_PATH),
        load_capability_delta_plan(PARENT_DELTA_PATH),
        load_capability_delta_source_proof(PARENT_PROOF_PATH),
        TogetherCapabilityPlan.model_validate_json(
            (
                FIXTURES
                / "preference_eval_phase4_together_capability_v3.json"
            ).read_text(encoding="utf-8")
        ),
        load_together_suite(
            FIXTURES / "preference_eval_phase4_together_v4.json"
        ),
        load_readiness_bundle(
            FIXTURES / "preference_eval_phase4_together_readiness_v4.json"
        ),
        TogetherCapabilityPlan.model_validate_json(
            (
                FIXTURES
                / "preference_eval_phase4_together_capability_v4.json"
            ).read_text(encoding="utf-8")
        ),
        load_together_suite(
            FIXTURES / "preference_eval_phase4_together_v5.json"
        ),
        load_readiness_bundle(
            FIXTURES / "preference_eval_phase4_together_readiness_v5.json"
        ),
        load_phase4_robustness_profile(
            FIXTURES / "preference_eval_phase4_robustness_v1.json"
        ),
        PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2,
        load_fixture(FIXTURES / "preference_eval_dev_v1.json"),
        load_session_script(
            FIXTURES / "preference_eval_dev_session_v1.json"
        ),
        load_authored_semantic_map(
            FIXTURES / "preference_eval_dev_semantic_map_v1.json"
        ),
    )


def _public_cli_argv(delta_path: Path = DELTA_PATH) -> list[str]:
    return [
        str(delta_path),
        str(PROOF_PATH),
        str(PARENT_DELTA_PATH),
        str(PARENT_PROOF_PATH),
        str(FIXTURES / "preference_eval_phase4_together_capability_v3.json"),
        str(FIXTURES / "preference_eval_phase4_together_v4.json"),
        str(FIXTURES / "preference_eval_phase4_together_readiness_v4.json"),
        str(FIXTURES / "preference_eval_phase4_together_capability_v4.json"),
        str(FIXTURES / "preference_eval_phase4_together_v5.json"),
        str(FIXTURES / "preference_eval_phase4_together_readiness_v5.json"),
        str(FIXTURES / "preference_eval_phase4_robustness_v1.json"),
        str(FIXTURES / "preference_eval_dev_v1.json"),
        str(FIXTURES / "preference_eval_dev_session_v1.json"),
        str(FIXTURES / "preference_eval_dev_semantic_map_v1.json"),
    ]


def _selector_execution_inputs():
    inputs = _public_inputs()
    return (
        inputs[0],
        inputs[1],
        inputs[7],
        inputs[8],
        inputs[10],
        inputs[9],
        inputs[12],
        inputs[13],
        inputs[14],
    )


def _catalog_at(loaded, approved_at):
    attestation = account_attestation(loaded)
    sources = public_sources(loaded)
    authorization = build_catalog_preflight_authorization(
        loaded,
        attestation,
        sources,
        authorization_id="selector_recovery_catalog_authorization_test",
        approved_at=approved_at,
        expires_at=approved_at + timedelta(hours=1),
    )
    receipt = build_catalog_preflight_receipt(
        loaded,
        authorization,
        live_model_payload(loaded),
        receipt_id="selector_recovery_catalog_receipt_test",
        checked_at=approved_at,
    )
    return TogetherCatalogPreflightBundle(
        bundle_id="selector_recovery_catalog_bundle_test",
        bundle_version=1,
        account_privacy_attestation=attestation,
        public_source_reverification=sources,
        authorization=authorization,
        receipt=receipt,
    )


class SelectorDeltaTransport(DeltaSemanticTransport):
    """No-network provider result carrying exact current-tool context."""

    def invoke(self, request):
        result = super().invoke(request)
        if request.binding.role is not LLMRole.INTERVIEWER:
            return result
        payload = request.input_payload
        assert isinstance(payload, dict)
        conformance = payload["provider_response_conformance"]
        assert isinstance(conformance, dict)
        question = conformance["expected_vetted_question"]
        assert isinstance(question, dict)
        context = {
            "record_version": "phase4_interviewer_tool_result_context.v1",
            "candidate_question_results": [
                {
                    "record_version": (
                        "read_candidate_question_scores_result.v1"
                    ),
                    "candidates": [question],
                    "model_version": "capability_preflight_v1",
                }
            ],
        }
        result_payload = result.model_dump(mode="python")
        result_payload.update(
            {
                "record_version": "phase4_provider_transport_result.v2",
                "output_payload": {
                    "record_version": (
                        "phase4_ask_vetted_question_selector.v1"
                    ),
                    "action": "ask_vetted_question",
                    "selected_question_id": question["question_id"],
                    "rendering_mode": "canonical_vetted",
                },
                "response_validation_context": context,
                "response_validation_context_sha256": content_sha256(
                    context
                ),
            }
        )
        return type(result).model_validate(result_payload)


def test_tracked_selector_recovery_chain_validates_without_private_sources():
    inputs = _public_inputs()
    delta, proof, parent_delta, parent_proof = inputs[:4]

    validate_selector_recovery_public_artifacts(*inputs)

    assert content_sha256(parent_delta) == (
        "25d286a8ceb16373e6868bb62bd81d3cf9b4cb0d2255f4ce02f66b2d4687f8e2"
    )
    assert content_sha256(parent_proof) == (
        "58d65a797d832a39ae1c3e2f65cddff893a296e04fa88b07f97ab89a187d5b15"
    )
    assert content_sha256(delta) == (
        "0a09365d59e01694fbe33a3d4d3b6af335c35a01f0e45ae658467309bd53adb4"
    )
    assert content_sha256(proof) == (
        "c60ca23180894287f18f964e503f91ecb59a70a497f0d9a54fee075145be8261"
    )
    assert proof.full_private_source_rebuild_passed is True
    assert proof.values_messages_and_context_omitted is True


def test_public_selector_recovery_validator_cli_is_aggregate_only(capsys):
    delta = load_selector_recovery_delta(DELTA_PATH)

    assert validate_public_cli.main(_public_cli_argv()) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["source_attempt_count"] == 4
    assert summary["carried_forward_success_count"] == 5
    assert summary["rerun_call_count"] == 10
    assert summary["public_input_count"] == 14
    assert "together_glm_5_2" not in captured.out
    assert "interviewer" not in captured.out
    assert delta.latest_selector_state_sha256 not in captured.out
    assert "private_runs" not in captured.out


def test_public_selector_recovery_validator_cli_fails_safely_on_tamper(
    tmp_path,
    capsys,
):
    marker = "planted_private_selector_value"
    payload = load_selector_recovery_delta(DELTA_PATH).model_dump(mode="json")
    payload["parent_delta_plan_sha256"] = "0" * 64
    payload["plan_id"] = marker
    tampered = tmp_path / "tampered_selector_delta.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    assert validate_public_cli.main(_public_cli_argv(tampered)) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: authoring validation failed; restricted details omitted\n"
    )
    assert marker not in captured.err
    assert "0" * 64 not in captured.err


def test_public_selector_recovery_validator_rejects_private_path_before_read(
    tmp_path,
    monkeypatch,
    capsys,
):
    private_delta = tmp_path / "private_runs" / "planted_delta.json"
    original_read_text = Path.read_text

    def guarded_read_text(path, *args, **kwargs):
        assert "private_runs" not in {
            part.casefold() for part in path.parts
        }
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    assert validate_public_cli.main(_public_cli_argv(private_delta)) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: authoring validation failed; restricted details omitted\n"
    )
    assert "planted_delta" not in captured.err


def test_execution_loader_dispatches_v1_and_selector_v2_exactly(tmp_path):
    selector_delta = load_executable_capability_delta_plan(DELTA_PATH)
    selector_proof = load_executable_capability_delta_source_proof(PROOF_PATH)
    historical_delta = load_executable_capability_delta_plan(PARENT_DELTA_PATH)
    historical_proof = load_executable_capability_delta_source_proof(
        PARENT_PROOF_PATH
    )

    assert isinstance(selector_delta, TogetherSelectorRecoveryDeltaPlan)
    assert isinstance(selector_proof, TogetherSelectorRecoverySourceProof)
    assert content_sha256(historical_delta) == (
        "25d286a8ceb16373e6868bb62bd81d3cf9b4cb0d2255f4ce02f66b2d4687f8e2"
    )
    assert content_sha256(historical_proof) == (
        "58d65a797d832a39ae1c3e2f65cddff893a296e04fa88b07f97ab89a187d5b15"
    )

    unsupported = tmp_path / "unsupported_delta.json"
    unsupported.write_text(
        json.dumps({"schema_version": "unsupported_delta.v99"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="plan schema is unsupported"):
        load_executable_capability_delta_plan(unsupported)


def test_selector_delta_builds_exact_executable_candidate_subsets():
    (
        delta,
        proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    ) = _selector_execution_inputs()
    validate_capability_delta_execution_inputs(
        delta,
        proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    )

    expected = {
        "together_glm_5_2": (2, 17_664, 38_200),
        "together_gpt_oss_120b": (4, 4_051, 7_500),
        "together_nemotron_3_ultra_550b_a55b": (4, 21_869, 34_800),
    }
    for candidate_id, totals in expected.items():
        candidate_plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            candidate_id,
        )
        assert (
            len(candidate_plan.calls),
            candidate_plan.projected_cost_microusd,
            candidate_plan.candidate_capability_max_spend_microusd,
        ) == totals


def test_selector_delta_rejects_a_mismatched_proof_and_manifest():
    (
        delta,
        _,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    ) = _selector_execution_inputs()
    historical_proof = load_capability_delta_source_proof(PARENT_PROOF_PATH)

    with pytest.raises(ValueError, match="source proof schema differs"):
        validate_capability_delta_execution_inputs(
            delta,
            historical_proof,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )

    changed_delta = delta.model_copy(
        update={"provider_response_semantics_manifest_sha256": "0" * 64}
    )
    changed_proof = load_selector_recovery_source_proof(PROOF_PATH).model_copy(
        update={
            "selector_recovery_delta_sha256": content_sha256(changed_delta),
            "provider_response_semantics_manifest_sha256": "0" * 64,
        }
    )
    with pytest.raises(ValueError, match="execution bindings differ"):
        validate_capability_delta_execution_inputs(
            changed_delta,
            changed_proof,
            corrected_plan,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
        )


def test_selector_delta_authorizes_and_executes_in_exact_order_without_network():
    (
        delta,
        proof,
        corrected_plan,
        suite,
        profile,
        readiness,
        fixture,
        session,
        semantic_map,
    ) = _selector_execution_inputs()
    approved_at = delta.created_at + timedelta(minutes=1)
    catalog = _catalog_at(suite, approved_at)
    clock = TickClock(approved_at)
    prior_attempts = []
    completed_states = []
    expected = [
        ("together_glm_5_2", 2),
        ("together_gpt_oss_120b", 4),
        ("together_nemotron_3_ultra_550b_a55b", 4),
    ]
    for position, (candidate_id, call_count) in enumerate(expected):
        candidate_plan = delta_candidate_plan_for(
            delta,
            corrected_plan,
            suite,
            profile,
            readiness,
            candidate_id,
        )
        candidate_approved_at = approved_at if position == 0 else clock()
        authorization = build_delta_candidate_authorization_bundle(
            delta,
            proof,
            candidate_plan,
            corrected_plan,
            suite,
            profile,
            readiness,
            catalog,
            prior_attempts=prior_attempts,
            bundle_id=f"{candidate_id}_selector_delta_authorization_test",
            approval_id=f"{candidate_id}_selector_delta_approval_test",
            approved_at=candidate_approved_at,
            expires_at=candidate_approved_at + timedelta(hours=1),
        )
        round_tripped = (
            TogetherDeltaCandidateAuthorizationBundle.model_validate_json(
                authorization.model_dump_json()
            )
        )
        checkpoints = []
        state = execute_delta_candidate_capability_preflight(
            delta,
            proof,
            corrected_plan,
            candidate_plan,
            round_tripped,
            suite,
            profile,
            readiness,
            fixture,
            session,
            semantic_map,
            catalog,
            SelectorDeltaTransport(clock),
            state_id=f"{candidate_id}_selector_delta_state_test",
            ledger_id=f"{candidate_id}_selector_delta_ledger_test",
            journal_id=f"{candidate_id}_selector_delta_journal_test",
            clock=clock,
            prior_attempts=prior_attempts,
            checkpoint=checkpoints.append,
        )

        validate_delta_candidate_execution_state(
            state,
            delta,
            candidate_plan,
            round_tripped,
            suite,
            profile,
        )
        assert state.receipt is not None
        assert len(state.receipt.checks) == call_count
        assert len(checkpoints) == call_count + 1
        assert round_tripped.candidate_position == position
        assert round_tripped.cumulative_worst_case_spend_microusd <= 120_727
        prior_attempts.append((round_tripped, state))
        completed_states.append(state)

    glm_state = completed_states[0]
    assert glm_state.provider_journal.finalizations[0].record_version == (
        "phase4_provider_call_finalization.v2"
    )
    assert (
        glm_state.provider_journal.finalizations[0]
        .response_validation_context_sha256
    )
    assert "response_validation_context" not in glm_state.model_dump(mode="json")


def test_selector_recovery_derives_five_carries_and_ten_reruns():
    delta = load_selector_recovery_delta(DELTA_PATH)
    carried = {
        (item.candidate_id, item.role)
        for item in delta.carried_forward_successes
    }

    assert carried == {
        ("together_glm_5_2", LLMRole.DIRECT_READOUT),
        ("together_glm_5_2", LLMRole.EVIDENCE_EXTRACTOR),
        ("together_glm_5_2", LLMRole.HYBRID_READOUT),
        ("together_gpt_oss_120b", LLMRole.DIRECT_READOUT),
        (
            "together_nemotron_3_ultra_550b_a55b",
            LLMRole.DIRECT_READOUT,
        ),
    }
    assert len(delta.rerun_calls) == 10
    assert delta.prior_provider_spend_microusd == 40_227
    assert delta.additional_projected_cost_microusd == 43_584
    assert delta.additional_authorized_max_cost_microusd == 80_500
    assert delta.cumulative_worst_case_spend_microusd == 120_727


def test_selector_recovery_binds_exact_latest_attempt_and_manifest_v2():
    delta = load_selector_recovery_delta(DELTA_PATH)

    assert delta.latest_selector_authorization_sha256 == (
        "7a18c3c66dbc51f21a00c11a876a5d071541e5d6ad2133f08ab685d4b4d9e2fe"
    )
    assert delta.latest_selector_state_sha256 == (
        "6f3d4ebab8c511b8c34c28eec5a88f7512ab03bb1e942cc8b5449bcab28ba1ef"
    )
    assert delta.latest_selector_diagnostic_sha256 == (
        "45a67467be0f3a1e783f415c53ce7779553b5953d8126ee62576a9182af4da28"
    )
    assert delta.provider_response_semantics_manifest_sha256 == (
        content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2)
    )
    assert delta.source_attempts[-1].provider_spend_microusd == 8_588
    assert delta.source_attempts[-1].terminal_role is LLMRole.INTERVIEWER


def test_carried_successes_support_bound_to_bound_validator_changes():
    delta = load_selector_recovery_delta(DELTA_PATH)

    for carried in delta.carried_forward_successes:
        assert carried.source_response_validator_sha256
        assert carried.corrected_response_validator_sha256
        assert (
            carried.source_transmitted_payload_sha256
            == carried.corrected_transmitted_payload_sha256
        )
        assert (
            carried.source_output_sha256
            == carried.corrected_revalidated_output_sha256
        )
        assert "validator_provenance_added_to_corrected_request" not in (
            carried.model_dump()
        )

    payload = delta.model_dump(mode="json")
    payload["carried_forward_successes"][0][
        "source_response_validator_sha256"
    ] = "0" * 64
    payload["carried_forward_successes"][0][
        "corrected_response_validator_sha256"
    ] = "1" * 64
    round_tripped = TogetherSelectorRecoveryDeltaPlan.model_validate(payload)
    assert (
        round_tripped.carried_forward_successes[0]
        .source_response_validator_sha256
        != round_tripped.carried_forward_successes[0]
        .corrected_response_validator_sha256
    )


def test_selector_recovery_schema_rejects_a_changed_carried_wire_payload():
    delta = load_selector_recovery_delta(DELTA_PATH)
    payload = delta.model_dump(mode="json")
    payload["carried_forward_successes"][0][
        "corrected_transmitted_payload_sha256"
    ] = "0" * 64

    with pytest.raises(ValidationError, match="wire payload changed"):
        TogetherSelectorRecoveryDeltaPlan.model_validate(payload)


def test_selector_recovery_schema_rejects_prior_spend_drift():
    delta = load_selector_recovery_delta(DELTA_PATH)
    payload = delta.model_dump(mode="json")
    payload["prior_provider_spend_microusd"] += 1

    with pytest.raises(ValidationError, match="prior spend"):
        TogetherSelectorRecoveryDeltaPlan.model_validate(payload)


def test_selector_recovery_source_proof_rejects_a_rerun_change():
    delta = load_selector_recovery_delta(DELTA_PATH)
    proof = load_selector_recovery_source_proof(PROOF_PATH)
    payload = proof.model_dump(mode="json")
    payload["rerun_calls_sha256"] = "0" * 64
    tampered = TogetherSelectorRecoverySourceProof.model_validate(payload)

    with pytest.raises(ValueError, match="source proof bindings differ"):
        validate_selector_recovery_source_proof(tampered, delta)


def test_selector_recovery_summary_is_aggregate_only():
    delta = load_selector_recovery_delta(DELTA_PATH)
    encoded = json.dumps(selector_recovery_summary(delta), sort_keys=True)

    assert "together_glm_5_2" not in encoded
    assert "interviewer" not in encoded
    assert delta.latest_selector_state_sha256 not in encoded
    assert "private_runs" not in encoded


def test_prepare_selector_recovery_cli_prints_only_aggregate_data(
    monkeypatch,
    tmp_path,
    capsys,
):
    delta = load_selector_recovery_delta(DELTA_PATH)
    proof = load_selector_recovery_source_proof(PROOF_PATH)
    monkeypatch.setattr(
        prepare_cli,
        "load_selector_recovery_authoring_inputs",
        lambda args: (),
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_selector_recovery_delta_plan",
        lambda *args, **kwargs: delta,
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_selector_recovery_delta_plan",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_selector_recovery_source_proof",
        lambda *args, **kwargs: proof,
    )
    positional = [str(tmp_path / f"input_{index}.json") for index in range(15)]
    output = tmp_path / "delta.json"
    proof_output = tmp_path / "proof.json"
    argv = [
        *positional,
        str(output),
        str(proof_output),
        "--parent-source-state",
        str(tmp_path / "state_1.json"),
        "--parent-source-state",
        str(tmp_path / "state_2.json"),
        "--parent-source-state",
        str(tmp_path / "state_3.json"),
    ]

    assert prepare_cli.main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "together_glm_5_2" not in captured.out
    assert delta.latest_selector_state_sha256 not in captured.out
    assert json.loads(output.read_text(encoding="utf-8"))[
        "schema_version"
    ] == delta.schema_version
