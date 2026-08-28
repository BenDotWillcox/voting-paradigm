from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_capability_aggregation import (
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
)
from eval.phase4_capability_retry import (
    load_capability_diagnostic_retry_plan,
    load_capability_diagnostic_retry_source_proof,
)
from eval.phase4_provider import (
    ProviderCallOutcome,
    ProviderHTTPErrorEnvelopeState,
    ProviderHTTPErrorMetadata,
    ProviderHTTPErrorType,
    ProviderSeedStatus,
    ProviderTransportResult,
    ScriptedProviderTransport,
)
from eval.phase4_qualification import Phase4QualificationBundle
from eval.phase4_qualification_scope import (
    AMENDED_SCOPE_PAUSE_OUTCOMES,
    AMENDED_QUALIFICATION_HARD_FAILURE_REASONS,
    FROZEN_TWO_DEPLOYMENT_SCOPE_EVIDENCE_PROOF_SHA256,
    FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256,
    LEGACY_QUALIFICATION_HARD_FAILURE_REASONS,
    QualificationScopePublicInputs,
    QualificationDeploymentScopeStatus,
    TwoDeploymentQualificationScopeAmendment,
    build_two_deployment_qualification_scope,
    build_two_deployment_scope_evidence_proof,
    load_two_deployment_qualification_scope,
    load_two_deployment_scope_evidence_proof,
    validate_two_deployment_qualification_scope,
)
from eval.phase4_robustness import LLMRole
from eval.phase4_together_live import TogetherLiveAuthorization
from eval.tests.test_phase4_capability_aggregation import _built_result
from eval.tests.test_phase4_capability_retry import (
    _execute,
    _synthetic_retry_inputs,
)
from eval.tests.test_phase4_selector_recovery import (
    _public_cli_argv,
    _public_inputs,
)
from eval import validate_phase4_qualification_scope_amendment as validate_cli
from eval import prepare_phase4_qualification_scope_amendment as prepare_cli


FIXTURES = Path(__file__).parents[1] / "fixtures"
AMENDMENT_PATH = (
    FIXTURES
    / "preference_eval_phase4_two_deployment_qualification_scope_v1.json"
)
SCOPE_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_two_deployment_qualification_scope_source_proof_v1.json"
)
AGGREGATION_PATH = (
    FIXTURES / "preference_eval_phase4_together_capability_aggregation_v1.json"
)
AGGREGATION_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_aggregation_source_proof_v1.json"
)
RETRY_PLAN_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_diagnostic_retry_v1.json"
)
RETRY_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_diagnostic_retry_source_proof_v1.json"
)


def _tracked_inputs():
    public_inputs = QualificationScopePublicInputs(*_public_inputs())
    return (
        load_two_deployment_qualification_scope(AMENDMENT_PATH),
        load_two_deployment_scope_evidence_proof(SCOPE_PROOF_PATH),
        load_capability_aggregation(AGGREGATION_PATH),
        load_capability_aggregation_source_proof(AGGREGATION_PROOF_PATH),
        load_capability_diagnostic_retry_plan(RETRY_PLAN_PATH),
        load_capability_diagnostic_retry_source_proof(RETRY_PROOF_PATH),
        public_inputs.corrected_suite,
        public_inputs.corrected_readiness,
        public_inputs.robustness_profile,
        public_inputs,
    )


def test_tracked_two_deployment_scope_validates_and_hashes_exactly() -> None:
    (
        amendment,
        proof,
        aggregation,
        aggregation_proof,
        retry_plan,
        retry_proof,
        suite,
        readiness,
        profile,
        public_inputs,
    ) = _tracked_inputs()

    validate_two_deployment_qualification_scope(
        amendment,
        proof,
        aggregation,
        aggregation_proof,
        retry_plan,
        retry_proof,
        suite,
        readiness,
        profile,
        public_inputs,
    )

    assert content_sha256(amendment) == FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256
    assert content_sha256(proof) == (
        FROZEN_TWO_DEPLOYMENT_SCOPE_EVIDENCE_PROOF_SHA256
    )
    assert proof.diagnostic_retry_state_sha256 == (
        "2abf873bf8dceaa5e23594ad918d9d9cd3f8869df60651e78861888e7f3a68d2"
    )
    assert proof.diagnostic_retry_http_diagnostic_sha256 == (
        "f4ef04c50cdb35946b925ad5e2bc914a38d413972956e5bd273b70c36d076a96"
    )
    assert proof.retry_input_tokens == 0
    assert proof.retry_output_tokens == 0
    assert proof.model_output_present is False


def test_scope_preserves_roster_and_excludes_only_inconclusive_deployment() -> None:
    amendment = _tracked_inputs()[0]

    assert amendment.original_candidate_ids == [
        "together_glm_5_2",
        "together_gpt_oss_120b",
        "together_nemotron_3_ultra_550b_a55b",
    ]
    assert amendment.runnable_candidate_ids == [
        "together_glm_5_2",
        "together_gpt_oss_120b",
    ]
    assert amendment.excluded_deployment_candidate_id == (
        "together_nemotron_3_ultra_550b_a55b"
    )
    excluded = amendment.deployment_scopes[-1]
    assert excluded.scope_status is (
        QualificationDeploymentScopeStatus.DEPLOYMENT_INCONCLUSIVE_NOT_RUN
    )
    assert excluded.included_in_comparison_and_selection is False
    assert excluded.model_family_capability_rejected is False
    assert amendment.replacement_candidate_ids == []
    assert amendment.model_selection_performed is False


def test_scope_derives_exact_304_10_294_partition_without_renumbering() -> None:
    amendment, *_, readiness, _, _ = _tracked_inputs()
    scoped_entries = [
        item
        for item in readiness.qualification_manifest.entries
        if item.coordinate.candidate_id in amendment.runnable_candidate_ids
    ]
    carried_ids = set(readiness.capability_preflight_call_ids)
    carried = [
        item for item in scoped_entries if item.coordinate.call_id in carried_ids
    ]
    new = [
        item for item in scoped_entries if item.coordinate.call_id not in carried_ids
    ]

    assert len(scoped_entries) == 304
    assert len(carried) == 10
    assert len(new) == 294
    assert [item.coordinate.ordinal for item in scoped_entries] == [
        *range(1, 11),
        *range(16, 310),
    ]
    assert amendment.runnable_entries_sha256 == (
        "2c49cf326feeca35179a6d201fc2141214adb34e1c49ae3041d6e54152fda2f2"
    )
    assert amendment.runnable_entry_sha256s_sha256 == (
        "6bd6214b7d2088656e4fcc26b3d82a5c986d9d47eab5241c47442bbd5e1c14c2"
    )
    assert amendment.runnable_call_ids_sha256 == (
        "a92f447a4fc27179955f3fe215edd141388afbe77f134e444b6aca85a5fbc1eb"
    )
    assert amendment.carried_entries_sha256 == (
        "63648f65b8d9c7f4859b7cff6209d6d2ebbf4524a9d513ad55e73e3bbfd31677"
    )
    assert amendment.carried_call_ids_sha256 == (
        "607bb56e3f2d0a0e763bdf3b7e1023624f78986463b6e97262eef38af8c1d558"
    )
    assert amendment.carried_success_evidence_sha256 == (
        "299ea7a303604062c974bcf399405cddbc409870f1e0423ce832428383ba5db3"
    )
    assert amendment.new_provider_entries_sha256 == (
        "3d8a37ea4c380c0c5d5e04ac9f46f49b4530b5a3101ad5f4077816b72db9c6f6"
    )
    assert amendment.new_provider_call_ids_sha256 == (
        "ca43b9ea2f8058d9f7a048ea0d563ccfe70552b6f04c3cabe786d0ccb7c0055c"
    )
    assert amendment.authorization_policy.new_provider_role_call_counts == {
        LLMRole.INTERVIEWER: 14,
        LLMRole.EVIDENCE_EXTRACTOR: 14,
        LLMRole.ONTOLOGY_PROPOSER: 14,
        LLMRole.DIRECT_READOUT: 126,
        LLMRole.HYBRID_READOUT: 126,
    }


def test_scope_budget_reconciles_new_calls_and_historical_spend() -> None:
    amendment = _tracked_inputs()[0]

    assert amendment.scoped_projected_cost_microusd == 1_466_671
    assert amendment.scoped_authorized_max_cost_microusd == 2_384_400
    assert amendment.carried_projected_cost_microusd == 45_147
    assert amendment.carried_authorized_max_cost_microusd == 87_000
    assert amendment.new_projected_cost_microusd == 1_421_524
    assert amendment.new_authorized_max_cost_microusd == 2_297_400
    assert amendment.maximum_single_call_reservation_microusd == 25_400
    assert amendment.prior_capability_spend_microusd == 51_042
    assert amendment.cumulative_qualification_worst_case_microusd == 2_348_442
    assert amendment.remaining_qualification_segment_microusd == 1_651_558
    assert amendment.sequential_projected_headroom_microusd == 2_502_034


def test_scope_preserves_frozen_selection_and_legacy_contracts() -> None:
    amendment = _tracked_inputs()[0]

    assert amendment.result_policy.selection_policy.record_version == (
        "phase4_qualification_selection_policy.v1"
    )
    assert amendment.result_policy.legacy_three_candidate_qualification_bundle_forbidden
    assert amendment.authorization_policy.legacy_live_authorization_forbidden
    assert amendment.authorization_policy.carried_success_replay_forbidden
    assert amendment.authorization_policy.candidate_isolated_execution_states_required
    assert amendment.result_policy.legacy_hard_failure_reasons_in_order == list(
        LEGACY_QUALIFICATION_HARD_FAILURE_REASONS
    )
    assert (
        amendment.result_policy.amended_candidate_hard_failure_reasons_in_order
        == list(AMENDED_QUALIFICATION_HARD_FAILURE_REASONS)
    )
    assert (
        set(LEGACY_QUALIFICATION_HARD_FAILURE_REASONS)
        - set(AMENDED_QUALIFICATION_HARD_FAILURE_REASONS)
        == {"provider_call_failure"}
    )
    assert (
        amendment.result_policy.provider_call_failure_is_sole_legacy_hard_gate_override
    )
    assert amendment.result_policy.legacy_provider_failure_outcomes_in_order == list(
        AMENDED_SCOPE_PAUSE_OUTCOMES
    )
    assert "preference_eval_phase4_qualification.v1" in (
        Phase4QualificationBundle.model_fields["schema_version"].annotation.__args__
    )
    assert "phase4_together_live_authorization.v1" in (
        TogetherLiveAuthorization.model_fields["record_version"].annotation.__args__
    )
    assert "phase4_together_live_authorization.v2" in (
        TogetherLiveAuthorization.model_fields["record_version"].annotation.__args__
    )


def test_scope_tampering_fails_closed() -> None:
    (
        amendment,
        proof,
        aggregation,
        aggregation_proof,
        retry_plan,
        retry_proof,
        suite,
        readiness,
        profile,
        public_inputs,
    ) = _tracked_inputs()
    payload = amendment.model_dump(mode="json")
    payload["runnable_candidate_ids"][-1] = payload[
        "excluded_deployment_candidate_id"
    ]

    with pytest.raises(ValidationError, match="scope excluded deployment"):
        TwoDeploymentQualificationScopeAmendment.model_validate(payload)

    payload = amendment.model_dump(mode="json")
    payload["new_authorized_max_cost_microusd"] += 1
    with pytest.raises(ValidationError, match="totals do not reconcile"):
        TwoDeploymentQualificationScopeAmendment.model_validate(payload)

    proof_payload = proof.model_dump(mode="json")
    proof_payload["diagnostic_retry_source_state_sha256"] = "0" * 64
    tampered_proof = type(proof).model_validate(proof_payload)
    with pytest.raises(ValueError, match="evidence proof bindings differ"):
        build_two_deployment_qualification_scope(
            aggregation,
            aggregation_proof,
            retry_plan,
            retry_proof,
            tampered_proof,
            suite,
            readiness,
            profile,
            public_inputs,
            amendment_id=amendment.amendment_id,
            created_at=amendment.created_at,
        )


@lru_cache(maxsize=1)
def _synthetic_http_500_scope_inputs():
    retry_inputs = _synthetic_retry_inputs()
    aggregation, aggregation_proof, _, _, _ = _built_result()
    completed_at = retry_inputs[-1] + timedelta(seconds=3)
    state = _execute(
        ScriptedProviderTransport(
            [
                ProviderTransportResult(
                    record_version="phase4_provider_transport_result.v3",
                    outcome=ProviderCallOutcome.PROVIDER_ERROR,
                    provider_http_error_metadata=ProviderHTTPErrorMetadata(
                        http_status_code=500,
                        envelope_state=ProviderHTTPErrorEnvelopeState.STANDARD,
                        error_type=ProviderHTTPErrorType.SERVER_ERROR,
                    ),
                    output_payload=None,
                    input_tokens=0,
                    output_tokens=0,
                    provider_request_id=None,
                    provider_request_sent=True,
                    provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
                    latency_ms=5.0,
                    failure_code="together_http_500",
                    completed_at=completed_at,
                )
            ]
        )
    )
    public_inputs = QualificationScopePublicInputs(*_public_inputs())
    return retry_inputs, aggregation, aggregation_proof, state, public_inputs


def test_private_retry_http_500_rebuilds_content_free_scope_proof() -> None:
    (
        retry_inputs,
        aggregation,
        aggregation_proof,
        state,
        public_inputs,
    ) = _synthetic_http_500_scope_inputs()
    completed_at = state.completed_at
    assert completed_at is not None
    proof = build_two_deployment_scope_evidence_proof(
        aggregation,
        aggregation_proof,
        retry_inputs[0],
        retry_inputs[1],
        retry_inputs[2],
        state,
        retry_inputs[15],
        retry_inputs[6],
        retry_inputs[8],
        retry_inputs[7],
        retry_inputs[13],
        public_inputs,
        proof_id="synthetic_two_deployment_scope_proof",
        validated_at=completed_at + timedelta(seconds=2),
    )
    amendment = build_two_deployment_qualification_scope(
        aggregation,
        aggregation_proof,
        retry_inputs[0],
        retry_inputs[1],
        proof,
        retry_inputs[6],
        retry_inputs[8],
        retry_inputs[7],
        public_inputs,
        amendment_id="synthetic_two_deployment_scope",
        created_at=proof.validated_at + timedelta(seconds=1),
    )

    assert proof.provider_inference_calls_executed_by_proof_creation == 0
    assert proof.provider_spend_microusd_by_proof_creation == 0
    assert amendment.new_provider_call_count == 294
    assert amendment.provider_inference_calls_executed == 0
    assert amendment.provider_spend_microusd == 0


def test_prepare_cli_writes_only_zero_spend_scope_artifacts(
    tmp_path,
    capsys,
) -> None:
    (
        retry_inputs,
        aggregation,
        aggregation_proof,
        state,
        _,
    ) = _synthetic_http_500_scope_inputs()
    paths = {
        "aggregation": tmp_path / "aggregation.json",
        "aggregation_proof": tmp_path / "aggregation_proof.json",
        "retry_plan": tmp_path / "retry_plan.json",
        "retry_proof": tmp_path / "retry_proof.json",
        "retry_authorization": tmp_path / "retry_authorization.json",
        "retry_state": tmp_path / "retry_state.json",
        "retry_source_state": tmp_path / "retry_source_state.json",
        "fresh_catalog": tmp_path / "fresh_catalog.json",
        "output": tmp_path / "scope.json",
        "scope_proof": tmp_path / "scope_proof.json",
    }
    models = {
        "aggregation": aggregation,
        "aggregation_proof": aggregation_proof,
        "retry_plan": retry_inputs[0],
        "retry_proof": retry_inputs[1],
        "retry_authorization": retry_inputs[2],
        "retry_state": state,
        "retry_source_state": retry_inputs[15],
        "fresh_catalog": retry_inputs[13],
    }
    for name, model in models.items():
        paths[name].write_text(
            model.model_dump_json(indent=2),
            encoding="utf-8",
        )

    assert prepare_cli.main(
        [
            *_public_cli_argv(),
            str(paths["aggregation"]),
            str(paths["aggregation_proof"]),
            str(paths["retry_plan"]),
            str(paths["retry_proof"]),
            str(paths["retry_authorization"]),
            str(paths["retry_state"]),
            str(paths["retry_source_state"]),
            str(paths["fresh_catalog"]),
            str(paths["output"]),
            str(paths["scope_proof"]),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["new_provider_call_count"] == 294
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert "together_glm" not in captured.out
    assert "private_runs" not in captured.out
    assert load_two_deployment_qualification_scope(paths["output"])
    assert load_two_deployment_scope_evidence_proof(paths["scope_proof"])


def test_prepare_cli_rejects_aliased_outputs_before_writing(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    shared_output = tmp_path / "shared.json"
    reads: list[Path] = []

    def forbidden_read(path: Path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("authoring inputs must not be read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    argv = [*_public_cli_argv(), *([str(tmp_path / "input.json")] * 8)]
    argv.extend([str(shared_output), str(shared_output)])

    assert prepare_cli.main(argv) == 1

    captured = capsys.readouterr()
    assert "authoring validation failed; restricted details omitted" in captured.err
    assert reads == []
    assert not shared_output.exists()


def test_prepare_cli_rejects_output_that_aliases_an_input_before_read(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    input_path = tmp_path / "input.json"
    proof_output = tmp_path / "proof.json"
    reads: list[Path] = []

    def forbidden_read(path: Path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("authoring inputs must not be read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    argv = [*_public_cli_argv(), *([str(input_path)] * 8)]
    argv.extend([str(input_path), str(proof_output)])

    assert prepare_cli.main(argv) == 1

    captured = capsys.readouterr()
    assert "authoring validation failed; restricted details omitted" in captured.err
    assert reads == []
    assert not proof_output.exists()


def _public_validator_argv(
    amendment_path: Path = AMENDMENT_PATH,
    proof_path: Path = SCOPE_PROOF_PATH,
) -> list[str]:
    return [
        *_public_cli_argv(),
        str(amendment_path),
        str(proof_path),
        str(AGGREGATION_PATH),
        str(AGGREGATION_PROOF_PATH),
        str(RETRY_PLAN_PATH),
        str(RETRY_PROOF_PATH),
    ]


def test_public_validator_is_aggregate_only(capsys) -> None:
    assert validate_cli.main(_public_validator_argv()) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["runnable_candidate_count"] == 2
    assert summary["new_provider_call_count"] == 294
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert "together_glm" not in captured.out
    assert "together_nemotron" not in captured.out
    assert "private_runs" not in captured.out


def test_public_validator_rejects_jointly_tampered_scope_and_proof(
    tmp_path,
    capsys,
) -> None:
    amendment, proof, *_ = _tracked_inputs()
    proof_payload = proof.model_dump(mode="json")
    proof_payload["diagnostic_retry_state_sha256"] = "0" * 64
    tampered_proof = type(proof).model_validate(proof_payload)
    amendment_payload = amendment.model_dump(mode="json")
    amendment_payload["diagnostic_retry_scope_evidence_proof_sha256"] = (
        content_sha256(tampered_proof)
    )
    tampered_amendment = type(amendment).model_validate(amendment_payload)
    amendment_path = tmp_path / "scope.json"
    proof_path = tmp_path / "proof.json"
    amendment_path.write_text(
        tampered_amendment.model_dump_json(indent=2),
        encoding="utf-8",
    )
    proof_path.write_text(
        tampered_proof.model_dump_json(indent=2),
        encoding="utf-8",
    )

    assert validate_cli.main(
        _public_validator_argv(amendment_path, proof_path)
    ) == 1

    captured = capsys.readouterr()
    assert "authoring validation failed; restricted details omitted" in captured.err


def test_public_validator_rejects_private_path_before_read(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    private_path = tmp_path / "private_runs" / "planted_secret.json"
    reads: list[Path] = []
    original = Path.read_text

    def guarded_read(path: Path, *args, **kwargs):
        reads.append(path)
        if "private_runs" in {part.casefold() for part in path.parts}:
            raise AssertionError("private path was read")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert validate_cli.main(_public_validator_argv(private_path)) == 1

    captured = capsys.readouterr()
    assert "restricted details omitted" in captured.err
    assert reads == []
