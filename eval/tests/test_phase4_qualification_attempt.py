from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_provider import (
    PROVIDER_RESPONSE_JSON_DECODER_POLICY,
    provider_response_json_decoder_implementation_sha256,
)
from eval.phase4_provider_semantics import (
    PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3,
    PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3,
    provider_response_readout_validator_implementation_sha256,
)
from eval.phase4_qualification_attempt import (
    ATTEMPT_V2_READOUT_ROLES,
    QualificationAttemptStage,
    QualificationAttemptV2SourceProof,
    build_qualification_attempt_v2_plan,
    validate_qualification_attempt_v2_plan,
)
from eval.phase4_qualification_scope import FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256
from eval.phase4_readiness import (
    QualificationVariant,
    build_qualification_request_manifest,
    load_readiness_bundle,
)
from eval.phase4_robustness import load_phase4_robustness_profile
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import build_default_together_suite
from eval.phase4_together_live import together_json_decoder_integration_sha256
from eval.prequential import load_session_script


FIXTURES = Path(__file__).parents[1] / "fixtures"
PROFILE_PATH = FIXTURES / "preference_eval_phase4_robustness_v1.json"
DEV_FIXTURE_PATH = FIXTURES / "preference_eval_dev_v1.json"
DEV_SESSION_PATH = FIXTURES / "preference_eval_dev_session_v1.json"
DEV_MAP_PATH = FIXTURES / "preference_eval_dev_semantic_map_v1.json"
READINESS_V5_PATH = (
    FIXTURES / "preference_eval_phase4_together_readiness_v5.json"
)
RUNNABLE_CANDIDATE_IDS = (
    "together_glm_5_2",
    "together_gpt_oss_120b",
)
PLANTED_PRIVATE_OUTPUT = "tgp_v1_PRIVATE_OUTPUT_MUST_NOT_APPEAR"


class _ConstantTokenCounter:
    def count(self, text: str) -> int:
        assert text
        return 1


def _digest(label: str) -> str:
    return content_sha256({"label": label})


@pytest.fixture(scope="module")
def attempt_plan_inputs():
    profile = load_phase4_robustness_profile(PROFILE_PATH)
    suite = build_default_together_suite(profile)
    fixture = load_fixture(DEV_FIXTURE_PATH)
    session = load_session_script(DEV_SESSION_PATH)
    semantic_map = load_authored_semantic_map(DEV_MAP_PATH)
    counters = {
        item.candidate.candidate_id: _ConstantTokenCounter()
        for item in suite.candidates
    }
    manifest = build_qualification_request_manifest(
        suite,
        profile,
        fixture,
        session,
        semantic_map,
        counters,
    )
    legacy_readiness = load_readiness_bundle(READINESS_V5_PATH)
    readiness = legacy_readiness.model_copy(
        update={
            "readiness_version": 6,
            "created_at": manifest.created_at,
            "together_suite_id": suite.suite_id,
            "together_suite_version": suite.suite_version,
            "together_suite_sha256": content_sha256(suite),
            "qualification_manifest": manifest,
            "capability_preflight_call_ids": [
                item.coordinate.call_id for item in manifest.entries[:15]
            ],
        }
    )
    private_source = {"output_payload": PLANTED_PRIVATE_OUTPUT}
    proof = QualificationAttemptV2SourceProof(
        proof_id="qualification_attempt_v2_public_test_proof",
        validated_at=datetime(2026, 8, 28, 20, 40, tzinfo=UTC),
        prior_execution_plan_sha256=_digest("prior_plan"),
        prior_carry_bundle_sha256=_digest("prior_carry"),
        prior_authorization_bundle_sha256=_digest("prior_authorization"),
        prior_private_result_sha256=content_sha256(private_source),
        prior_safe_receipt_sha256=_digest("prior_receipt"),
        prior_scope_sha256=FROZEN_TWO_DEPLOYMENT_SCOPE_SHA256,
        prior_candidate_state_sha256s={
            candidate_id: _digest(f"state:{candidate_id}")
            for candidate_id in RUNNABLE_CANDIDATE_IDS
        },
        source_together_suite_sha256=_digest("source_suite"),
        source_readiness_sha256=_digest("source_readiness"),
        corrected_together_suite_sha256=content_sha256(suite),
        corrected_readiness_sha256=content_sha256(readiness),
        response_invariant_manifest_sha256=content_sha256(
            PROVIDER_RESPONSE_INVARIANT_MANIFEST_V3
        ),
        response_behavior_spec_sha256=content_sha256(
            PROVIDER_RESPONSE_BEHAVIOR_SPEC_V3
        ),
        readout_validator_implementation_sha256=(
            provider_response_readout_validator_implementation_sha256()
        ),
        json_decoder_policy_sha256=content_sha256(
            PROVIDER_RESPONSE_JSON_DECODER_POLICY
        ),
        json_decoder_implementation_sha256=(
            provider_response_json_decoder_implementation_sha256()
        ),
        together_json_decoder_integration_sha256=(
            together_json_decoder_integration_sha256()
        ),
    )
    plan = build_qualification_attempt_v2_plan(
        proof,
        suite,
        readiness,
        plan_id="qualification_attempt_v2_public_test_plan",
        created_at=datetime(2026, 8, 28, 20, 41, tzinfo=UTC),
    )
    return proof, plan, suite, readiness


def test_attempt_v2_plans_every_coordinate_fresh_and_exact_conformance_ids(
    attempt_plan_inputs,
) -> None:
    proof, plan, suite, readiness = attempt_plan_inputs

    validate_qualification_attempt_v2_plan(plan, proof, suite, readiness)
    calls = [
        call for candidate in plan.candidate_plans for call in candidate.calls
    ]
    conformance_ids = {
        call.call_id
        for call in calls
        if call.execution_stage is QualificationAttemptStage.READOUT_CONFORMANCE
    }
    expected_ids = {
        entry.coordinate.call_id
        for entry in readiness.qualification_manifest.entries
        if entry.coordinate.candidate_id in RUNNABLE_CANDIDATE_IDS
        and entry.coordinate.call_id in readiness.capability_preflight_call_ids
        and entry.coordinate.role in ATTEMPT_V2_READOUT_ROLES
        and entry.coordinate.variant_id is QualificationVariant.CANONICAL
    }

    assert plan.scoped_coordinate_count == 304
    assert plan.carried_success_count == 0
    assert plan.provider_call_count == 304
    assert len(calls) == 304
    assert conformance_ids == expected_ids
    assert len(conformance_ids) == 4


def test_attempt_v2_interleaves_candidates_after_front_loaded_conformance(
    attempt_plan_inputs,
) -> None:
    _proof, plan, _suite, _readiness = attempt_plan_inputs
    calls_by_id = {
        call.call_id: (candidate.candidate_id, local_index, call.execution_stage)
        for candidate in plan.candidate_plans
        for local_index, call in enumerate(candidate.calls)
    }
    ordered = [calls_by_id[call_id] for call_id in plan.execution_order_call_ids]

    assert all(
        stage is QualificationAttemptStage.READOUT_CONFORMANCE
        for _candidate_id, _local_index, stage in ordered[:4]
    )
    assert all(
        stage is QualificationAttemptStage.FULL_QUALIFICATION
        for _candidate_id, _local_index, stage in ordered[4:]
    )
    for stage in QualificationAttemptStage:
        stage_order = [item for item in ordered if item[2] is stage]
        first_candidate_ids = []
        for offset in range(0, len(stage_order), 2):
            pair = stage_order[offset : offset + 2]
            assert sorted(item[0] for item in pair) == sorted(
                RUNNABLE_CANDIDATE_IDS
            )
            assert pair[0][1] == pair[1][1]
            first_candidate_ids.append(pair[0][0])
        assert first_candidate_ids == [
            RUNNABLE_CANDIDATE_IDS[index % 2]
            for index in range(len(first_candidate_ids))
        ]
        first_position_counts = [
            first_candidate_ids.count(candidate_id)
            for candidate_id in RUNNABLE_CANDIDATE_IDS
        ]
        assert max(first_position_counts) - min(first_position_counts) <= 1


def test_attempt_v2_rejects_decoder_and_headroom_tampering(
    attempt_plan_inputs,
) -> None:
    proof, plan, suite, readiness = attempt_plan_inputs
    wrong_digest = "0" * 64

    bad_proof = proof.model_copy(
        update={"json_decoder_implementation_sha256": wrong_digest}
    )
    with pytest.raises(ValidationError, match="JSON decoder differs"):
        QualificationAttemptV2SourceProof.model_validate(
            bad_proof.model_dump(mode="json")
        )

    bad_integration = proof.model_copy(
        update={"together_json_decoder_integration_sha256": wrong_digest}
    )
    with pytest.raises(ValidationError, match="JSON decoder differs"):
        QualificationAttemptV2SourceProof.model_validate(
            bad_integration.model_dump(mode="json")
        )

    bad_plan = plan.model_copy(
        update={"json_decoder_implementation_sha256": wrong_digest}
    )
    with pytest.raises(ValueError, match="source bindings differ"):
        validate_qualification_attempt_v2_plan(
            bad_plan,
            proof,
            suite,
            readiness,
        )

    insufficient_headroom = plan.model_copy(
        update={
            "qualification_minimum_headroom_microusd": (
                plan.sequential_projected_headroom_microusd + 1
            )
        }
    )
    with pytest.raises(ValidationError, match="lacks sequential headroom"):
        type(plan).model_validate(insufficient_headroom.model_dump(mode="json"))


def test_attempt_v2_rejects_same_id_candidate_or_price_drift(
    attempt_plan_inputs,
) -> None:
    proof, _plan, suite, readiness = attempt_plan_inputs
    original = suite.candidates[0]
    changed_price = original.price_card.model_copy(
        update={
            "input_microusd_per_million_tokens": (
                original.price_card.input_microusd_per_million_tokens + 1
            )
        }
    )
    changed_suite = suite.model_copy(
        update={
            "candidates": [
                original.model_copy(update={"price_card": changed_price}),
                *suite.candidates[1:],
            ]
        }
    )

    with pytest.raises(ValueError, match="corrected sources differ"):
        build_qualification_attempt_v2_plan(
            proof,
            changed_suite,
            readiness,
            plan_id="qualification_attempt_v2_drifted_test_plan",
            created_at=datetime(2026, 8, 28, 20, 41, tzinfo=UTC),
        )


def test_attempt_v2_tracked_artifacts_omit_private_output(
    attempt_plan_inputs,
) -> None:
    proof, plan, _suite, _readiness = attempt_plan_inputs
    serialized = "\n".join(
        (
            proof.model_dump_json(),
            plan.model_dump_json(),
        )
    )

    assert PLANTED_PRIVATE_OUTPUT not in serialized
    assert proof.prior_private_result_sha256 in serialized
