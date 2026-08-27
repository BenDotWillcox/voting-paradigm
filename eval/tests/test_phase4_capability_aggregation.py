from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_capability_aggregation import (
    CandidateCapabilityDisposition,
    CapabilityRoleEvidenceStatus,
    Phase4CapabilityAggregation,
    build_capability_aggregation,
    build_capability_aggregation_source_proof,
    load_capability_aggregation,
    load_capability_aggregation_source_proof,
    validate_capability_aggregation_public_artifacts,
)
from eval.phase4_capability_recovery import (
    build_delta_candidate_authorization_bundle,
    delta_candidate_plan_for,
    execute_delta_candidate_capability_preflight,
)
from eval.phase4_provider import ProviderCallOutcome
from eval.phase4_robustness import BudgetSegment, LLMRole
from eval.phase4_together_live import (
    TogetherLiveAuthorization,
    TogetherPaidStage,
)
from eval import prepare_phase4_capability_aggregation as prepare_cli
from eval import validate_phase4_capability_aggregation as validate_cli
from eval.tests.test_phase4_capability import TickClock
from eval.tests.test_phase4_selector_recovery import (
    SelectorDeltaTransport,
    _catalog_at,
    _public_cli_argv,
    _public_inputs,
    _selector_execution_inputs,
)


FIXTURES = Path(__file__).parents[1] / "fixtures"
AGGREGATION_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_aggregation_v1.json"
)
AGGREGATION_PROOF_PATH = (
    FIXTURES
    / "preference_eval_phase4_together_capability_aggregation_source_proof_v1.json"
)
PLANTED_PRIVATE_STATE_MARKER = "planted_private_capability_state_marker"


class ZeroUsageFailureSelectorTransport(SelectorDeltaTransport):
    """Deterministic provider rejection matching the paid HTTP-400 shape."""

    def invoke(self, request):
        result = super().invoke(request)
        if result.outcome is ProviderCallOutcome.PROVIDER_ERROR:
            return result.model_copy(
                update={
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "failure_code": "together_http_400",
                }
            )
        return result


def test_tracked_capability_aggregation_has_exact_review_handoff_hashes():
    aggregation = load_capability_aggregation(AGGREGATION_PATH)
    proof = load_capability_aggregation_source_proof(
        AGGREGATION_PROOF_PATH
    )

    validate_capability_aggregation_public_artifacts(
        aggregation,
        proof,
        *_public_inputs(),
    )

    assert content_sha256(aggregation) == (
        "e9a0bd7141a9536041e3d242d0696daade3b3325c562cf1bd2a4b5f34dd8452e"
    )
    assert content_sha256(proof) == (
        "de14bde9c424c530a62367ffec202d936f8180ec123db300996baa4956c9a156"
    )
    assert aggregation.cumulative_provider_spend_microusd == 51_042
    assert aggregation.recovery_provider_spend_microusd == 10_815
    assert aggregation.remaining_capability_ceiling_microusd == 98_958


@lru_cache(maxsize=1)
def _attempts():
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
    candidate_order = list(
        dict.fromkeys(item.candidate_id for item in corrected_plan.calls)
    )
    for position, candidate_id in enumerate(candidate_order):
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
            bundle_id=f"{candidate_id}_aggregation_authorization_test",
            approval_id=f"{candidate_id}_aggregation_approval_test",
            approved_at=candidate_approved_at,
            expires_at=candidate_approved_at + timedelta(hours=1),
        )
        checkpoints = []
        transport = (
            ZeroUsageFailureSelectorTransport(clock, fail_at=1)
            if position == 2
            else SelectorDeltaTransport(clock)
        )
        try:
            state = execute_delta_candidate_capability_preflight(
                delta,
                proof,
                corrected_plan,
                candidate_plan,
                authorization,
                suite,
                profile,
                readiness,
                fixture,
                session,
                semantic_map,
                catalog,
                transport,
                state_id=(
                    f"{PLANTED_PRIVATE_STATE_MARKER}_{candidate_id}"
                    if position == 0
                    else f"{candidate_id}_aggregation_state_test"
                ),
                ledger_id=f"{candidate_id}_aggregation_ledger_test",
                journal_id=f"{candidate_id}_aggregation_journal_test",
                clock=clock,
                prior_attempts=prior_attempts,
                checkpoint=checkpoints.append,
            )
        except ValueError as error:
            assert "did not succeed" in str(error)
            state = checkpoints[-1]
        prior_attempts.append((authorization, state))
    return catalog, prior_attempts


@lru_cache(maxsize=1)
def _built_result():
    public_inputs = _public_inputs()
    catalog, attempts = _attempts()
    created_at = max(
        state.provider_journal.finalizations[-1].created_at
        for _, state in attempts
    ) + timedelta(seconds=1)
    aggregation = build_capability_aggregation(
        *public_inputs,
        catalog,
        attempts,
        aggregation_id="phase4_capability_aggregation_test",
        created_at=created_at,
    )
    proof = build_capability_aggregation_source_proof(
        aggregation,
        *public_inputs,
        catalog,
        attempts,
        proof_id="phase4_capability_aggregation_proof_test",
        validated_at=created_at + timedelta(seconds=1),
    )
    return aggregation, proof, public_inputs, catalog, attempts


def test_aggregation_rebuilds_exact_role_matrix_and_scientific_dispositions():
    aggregation, proof, public_inputs, _, _ = _built_result()

    validate_capability_aggregation_public_artifacts(
        aggregation,
        proof,
        *public_inputs,
    )

    assert aggregation.capability_passed_candidate_count == 2
    assert aggregation.provider_deployment_inconclusive_candidate_count == 1
    assert aggregation.model_capability_rejected_candidate_count == 0
    assert aggregation.role_coordinate_count == 15
    assert aggregation.carried_success_count == 5
    assert aggregation.observed_success_count == 6
    assert aggregation.provider_failure_count == 1
    assert aggregation.unattempted_role_count == 3
    assert aggregation.recovery_provider_call_count == 7
    assert aggregation.capability_preflight_receipt_sha256 is None
    assert aggregation.qualification_authorization_sha256 is None
    assert aggregation.selected_model_candidate_id is None
    assert aggregation.replacement_candidate_ids == []
    assert [item.disposition for item in aggregation.candidate_outcomes] == [
        CandidateCapabilityDisposition.CAPABILITY_PASSED,
        CandidateCapabilityDisposition.CAPABILITY_PASSED,
        CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE,
    ]


def test_provider_error_is_not_model_rejection_and_leaves_exact_suffix():
    aggregation, _, _, _, _ = _built_result()
    outcome = aggregation.candidate_outcomes[-1]
    statuses = [item.status for item in outcome.role_evidence]

    assert outcome.disposition is (
        CandidateCapabilityDisposition.PROVIDER_DEPLOYMENT_INCONCLUSIVE
    )
    assert statuses.count(CapabilityRoleEvidenceStatus.CARRIED_SUCCESS) == 1
    assert statuses.count(
        CapabilityRoleEvidenceStatus.PROVIDER_DEPLOYMENT_INCONCLUSIVE
    ) == 1
    assert statuses[-3:] == [
        CapabilityRoleEvidenceStatus.NOT_ATTEMPTED_AFTER_PROVIDER_FAILURE
    ] * 3


def test_aggregation_records_no_v1_qualification_authorization():
    aggregation, _, _, _, _ = _built_result()

    assert aggregation.capability_preflight_receipt_sha256 is None
    with pytest.raises(
        ValidationError,
        match="qualification authorization requires capability receipt",
    ):
        TogetherLiveAuthorization(
            authorization_id="partial_aggregate_cannot_authorize",
            authorization_version=1,
            together_suite_id="suite",
            together_suite_version=1,
            together_suite_sha256="0" * 64,
            robustness_profile_sha256="1" * 64,
            account_privacy_attestation_sha256="2" * 64,
            catalog_preflight_receipt_sha256="3" * 64,
            token_readiness_receipt_sha256="4" * 64,
            headroom_policy_sha256="5" * 64,
            capability_preflight_receipt_sha256=None,
            stage=TogetherPaidStage.QUALIFICATION,
            budget_segment=BudgetSegment.QUALIFICATION,
            authorized_candidate_ids=["candidate"],
            authorized_roles=sorted(LLMRole, key=lambda item: item.value),
            approved_max_spend_microusd=1,
            approved_at=aggregation.created_at,
            expires_at=aggregation.created_at + timedelta(minutes=1),
        )
    for field_name in (
        "capability_preflight_receipt_sha256",
        "qualification_authorization_sha256",
    ):
        payload = aggregation.model_dump(mode="json")
        payload[field_name] = "9" * 64
        with pytest.raises(ValidationError):
            Phase4CapabilityAggregation.model_validate(payload)


def test_aggregation_rejects_private_attempts_out_of_exact_order():
    public_inputs = _public_inputs()
    catalog, attempts = _attempts()

    with pytest.raises(ValueError, match="authorization"):
        build_capability_aggregation(
            *public_inputs,
            catalog,
            [attempts[1], attempts[0], attempts[2]],
            aggregation_id="misordered_capability_aggregation",
            created_at=(
                attempts[-1][1].provider_journal.finalizations[-1].created_at
                + timedelta(seconds=1)
            ),
        )


def test_aggregation_rejects_an_unreviewed_provider_failure_class():
    public_inputs = _public_inputs()
    catalog, attempts = _attempts()
    payload = attempts[-1][1].model_dump(mode="json")
    payload["provider_journal"]["finalizations"][-1]["failure_code"] = (
        "together_http_500"
    )
    changed_state = type(attempts[-1][1]).model_validate(payload)
    changed_attempts = [*attempts[:-1], (attempts[-1][0], changed_state)]

    with pytest.raises(ValueError, match="differs from reviewed HTTP 400"):
        build_capability_aggregation(
            *public_inputs,
            catalog,
            changed_attempts,
            aggregation_id="unreviewed_failure_capability_aggregation",
            created_at=(
                changed_state.provider_journal.finalizations[-1].created_at
                + timedelta(seconds=1)
            ),
        )


def test_interviewer_tool_failure_cannot_become_provider_inconclusive():
    public_inputs = _public_inputs()
    catalog, attempts = _attempts()
    payload = attempts[-1][1].model_dump(mode="json")
    finalization = payload["provider_journal"]["finalizations"][-1]
    finalization["outcome"] = "invalid_output"
    finalization["failure_code"] = "together_required_tool_call_missing"
    changed_state = type(attempts[-1][1]).model_validate(payload)
    changed_attempts = [*attempts[:-1], (attempts[-1][0], changed_state)]

    with pytest.raises(ValueError, match="separate scientific review"):
        build_capability_aggregation(
            *public_inputs,
            catalog,
            changed_attempts,
            aggregation_id="tool_failure_capability_aggregation",
            created_at=(
                changed_state.provider_journal.finalizations[-1].created_at
                + timedelta(seconds=1)
            ),
        )


def test_aggregation_tamper_fails_closed():
    aggregation, _, _, _, _ = _built_result()
    payload = aggregation.model_dump(mode="json")
    payload["candidate_outcomes"][0]["disposition"] = (
        "provider_deployment_inconclusive"
    )

    with pytest.raises(ValidationError, match="provider-inconclusive outcome"):
        Phase4CapabilityAggregation.model_validate(payload)


def test_private_source_proof_cannot_bless_schema_valid_audit_hash_tamper():
    aggregation, _, public_inputs, catalog, attempts = _built_result()
    payload = aggregation.model_dump(mode="json")
    payload["candidate_outcomes"][0]["provider_ledger_sha256"] = "8" * 64
    tampered = Phase4CapabilityAggregation.model_validate(payload)

    with pytest.raises(ValueError, match="does not rebuild"):
        build_capability_aggregation_source_proof(
            tampered,
            *public_inputs,
            catalog,
            attempts,
            proof_id="tampered_capability_aggregation_proof",
            validated_at=aggregation.created_at + timedelta(seconds=2),
        )


def test_public_validator_rejects_schema_valid_aggregate_proof_mismatch():
    aggregation, proof, public_inputs, _, _ = _built_result()
    payload = aggregation.model_dump(mode="json")
    payload["candidate_outcomes"][0]["provider_journal_sha256"] = "7" * 64
    tampered = Phase4CapabilityAggregation.model_validate(payload)

    with pytest.raises(ValueError, match="proof bindings differ"):
        validate_capability_aggregation_public_artifacts(
            tampered,
            proof,
            *public_inputs,
        )


def test_public_validator_rejects_reconciled_but_wrong_public_spend():
    aggregation, proof, public_inputs, _, _ = _built_result()
    payload = aggregation.model_dump(mode="json")
    payload["prior_provider_spend_microusd"] += 1
    payload["cumulative_provider_spend_microusd"] += 1
    payload["remaining_capability_ceiling_microusd"] -= 1
    tampered = Phase4CapabilityAggregation.model_validate(payload)
    tampered_proof = proof.model_copy(
        update={"aggregation_sha256": content_sha256(tampered)}
    )

    with pytest.raises(ValueError, match="public totals differ"):
        validate_capability_aggregation_public_artifacts(
            tampered,
            tampered_proof,
            *public_inputs,
        )


def _public_validator_argv(aggregation_path: Path, proof_path: Path):
    return [
        str(aggregation_path),
        str(proof_path),
        *_public_cli_argv(),
    ]


def test_public_validator_cli_is_aggregate_only(tmp_path, capsys):
    aggregation, proof, _, _, _ = _built_result()
    aggregation_path = tmp_path / "aggregation.json"
    proof_path = tmp_path / "proof.json"
    aggregation_path.write_text(
        aggregation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    proof_path.write_text(proof.model_dump_json(indent=2), encoding="utf-8")

    assert validate_cli.main(
        _public_validator_argv(aggregation_path, proof_path)
    ) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["candidate_count"] == 3
    assert summary["capability_passed_candidate_count"] == 2
    assert summary["provider_deployment_inconclusive_candidate_count"] == 1
    assert summary["public_input_count"] == 16
    assert "together_glm_5_2" not in captured.out
    assert "together_http" not in captured.out
    assert aggregation.candidate_outcomes[0].state_sha256 not in captured.out
    assert PLANTED_PRIVATE_STATE_MARKER not in captured.out
    assert PLANTED_PRIVATE_STATE_MARKER not in aggregation_path.read_text(
        encoding="utf-8"
    )
    assert PLANTED_PRIVATE_STATE_MARKER not in proof_path.read_text(
        encoding="utf-8"
    )
    assert "private_runs" not in captured.out


def test_public_validator_rejects_private_path_before_read(
    tmp_path,
    monkeypatch,
    capsys,
):
    private_aggregation = tmp_path / "private_runs" / "planted.json"
    proof_path = tmp_path / "proof.json"
    proof_path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def guarded_read_text(path, *args, **kwargs):
        assert "private_runs" not in {
            part.casefold() for part in path.parts
        }
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    assert validate_cli.main(
        _public_validator_argv(private_aggregation, proof_path)
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: authoring validation failed; restricted details omitted\n"
    )
    assert "planted" not in captured.err


def test_prepare_cli_is_zero_spend_and_writes_only_content_free_artifacts(
    tmp_path,
    capsys,
):
    _, _, _, catalog, attempts = _built_result()
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    attempt_args = []
    for index, (authorization, state) in enumerate(attempts, start=1):
        authorization_path = tmp_path / f"authorization_{index}.json"
        state_path = tmp_path / f"state_{index}.json"
        authorization_path.write_text(
            authorization.model_dump_json(indent=2),
            encoding="utf-8",
        )
        state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        attempt_args.extend(
            ["--attempt", str(authorization_path), str(state_path)]
        )
    output = tmp_path / "aggregate.json"
    proof_output = tmp_path / "aggregate_proof.json"
    argv = [
        *_public_cli_argv(),
        str(catalog_path),
        str(output),
        str(proof_output),
        *attempt_args,
    ]

    assert prepare_cli.main(argv) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["provider_inference_calls_executed_by_aggregation"] == 0
    assert summary["provider_spend_microusd_by_aggregation"] == 0
    assert content_sha256(
        Phase4CapabilityAggregation.model_validate_json(
            output.read_text(encoding="utf-8")
        )
    ) == summary["aggregation_sha256"]
    assert "together_glm_5_2" not in captured.out
    assert "output_payload" not in output.read_text(encoding="utf-8")
    assert PLANTED_PRIVATE_STATE_MARKER not in captured.out
    assert PLANTED_PRIVATE_STATE_MARKER not in output.read_text(
        encoding="utf-8"
    )
    assert PLANTED_PRIVATE_STATE_MARKER not in proof_output.read_text(
        encoding="utf-8"
    )
