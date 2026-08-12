"""Tests for the Phase 4A architecture and comparison freeze."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.bank_profile import load_bank_profile
from eval.fixture_io import content_sha256
from eval.phase4_protocol import (
    Phase4Protocol,
    build_phase4_protocol_manifest,
    load_phase4_protocol,
    phase4_protocol_summary,
    validate_phase4_protocol_against_bank_profile,
)
from eval.validate_phase4_protocol import main

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"
PROTOCOL_PATH = FIXTURE_DIR / "preference_eval_phase4_protocol_v1.json"
BANK_PROFILE_PATH = FIXTURE_DIR / "preference_eval_bank_profile_v1.json"


def _raw_protocol() -> dict[str, object]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _arm(raw: dict[str, object], arm_id: str) -> dict[str, object]:
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    arms = comparison["model_arms"]
    assert isinstance(arms, list)
    return next(arm for arm in arms if arm["arm_id"] == arm_id)


def test_frozen_phase4_protocol_validates_and_binds_public_profile():
    protocol = load_phase4_protocol(PROTOCOL_PATH)
    bank_profile = load_bank_profile(BANK_PROFILE_PATH)

    validate_phase4_protocol_against_bank_profile(protocol, bank_profile)

    assert len(protocol.comparison.acquisition_policies) == 4
    assert len(protocol.comparison.model_arms) == 6
    assert protocol.action_policy.model_abstention_allowed is False
    assert (
        protocol.architecture.durable_preference_state_owner
        == "explicit_preference_posterior"
    )


def test_protocol_round_trip_preserves_canonical_hash():
    protocol = load_phase4_protocol(PROTOCOL_PATH)
    round_tripped = Phase4Protocol.model_validate(
        protocol.model_dump(mode="json")
    )

    assert content_sha256(round_tripped) == content_sha256(protocol)


def test_manifest_binds_each_architecture_surface():
    protocol = load_phase4_protocol(PROTOCOL_PATH)
    manifest = build_phase4_protocol_manifest(protocol)

    assert manifest.protocol_sha256 == content_sha256(protocol)
    assert manifest.bank_profile_sha256 == protocol.bank_profile_sha256
    assert manifest.architecture_sha256 == content_sha256(protocol.architecture)
    assert manifest.interviewer_sha256 == content_sha256(protocol.interviewer)
    assert manifest.target_isolation_sha256 == content_sha256(
        protocol.target_isolation
    )
    assert manifest.comparison_sha256 == content_sha256(protocol.comparison)
    assert manifest.action_policy_sha256 == content_sha256(
        protocol.action_policy
    )


def test_protocol_rejects_unknown_fields():
    raw = _raw_protocol()
    raw["provider"] = "not-frozen-in-phase-4a"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Phase4Protocol.model_validate(raw)


def test_protocol_requires_timezone_aware_created_at():
    raw = _raw_protocol()
    raw["created_at"] = "2026-08-11T12:00:00"

    with pytest.raises(
        ValidationError,
        match="created_at must include a timezone",
    ):
        Phase4Protocol.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("durable_preference_state_owner", "llm_weights"),
        ("direct_llm_role", "production_state_owner"),
        ("only_preference_model_updates_posterior", False),
        ("llm_outputs_cannot_directly_update_posterior", False),
        ("inferred_evidence_requires_participant_confirmation", False),
        ("ballot_overrides_never_train_automatically", False),
        ("passive_non_intervention_has_zero_evidence_weight", False),
    ],
)
def test_protocol_rejects_architecture_boundary_drift(field, value):
    raw = _raw_protocol()
    architecture = raw["architecture"]
    assert isinstance(architecture, dict)
    architecture[field] = value

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_interviewer_requires_complete_allowed_action_set():
    raw = _raw_protocol()
    interviewer = raw["interviewer"]
    assert isinstance(interviewer, dict)
    interviewer["allowed_actions"] = ["ask_vetted_question"]

    with pytest.raises(ValidationError, match="complete Phase 4A v1 set"):
        Phase4Protocol.model_validate(raw)


def test_interviewer_requires_complete_model_tool_surface():
    raw = _raw_protocol()
    interviewer = raw["interviewer"]
    assert isinstance(interviewer, dict)
    interviewer["allowed_tools"] = ["read_posterior_uncertainty"]

    with pytest.raises(ValidationError, match="complete Phase 4A v1 set"):
        Phase4Protocol.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("novel_substantive_question_generation_allowed", True),
        ("rendering_may_add_substantive_content", True),
        ("rendering_must_preserve_semantics_and_response_scale", False),
        ("rendering_validation_required_before_presentation", False),
    ],
)
def test_interviewer_v1_rejects_unvalidated_content_authority(field, value):
    raw = _raw_protocol()
    interviewer = raw["interviewer"]
    assert isinstance(interviewer, dict)
    interviewer[field] = value

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_unconfirmed_extracted_evidence_must_have_zero_weight():
    raw = _raw_protocol()
    interviewer = raw["interviewer"]
    assert isinstance(interviewer, dict)
    interviewer["provisional_extracted_evidence_weight"] = 0.25

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_packet_visible_to_interviewer_during_elicitation", True),
        ("target_packet_visible_to_evidence_extractor_during_elicitation", True),
        ("target_specific_questions_after_packet_exposure_allowed", True),
        ("target_response_hidden_until_prediction_is_frozen", False),
    ],
)
def test_primary_eval_rejects_target_leakage(field, value):
    raw = _raw_protocol()
    isolation = raw["target_isolation"]
    assert isinstance(isolation, dict)
    isolation[field] = value

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_target_isolation_requires_every_proxy_exclusion():
    raw = _raw_protocol()
    isolation = raw["target_isolation"]
    assert isinstance(isolation, dict)
    isolation["excluded_model_inputs"] = ["political_identity"]

    with pytest.raises(ValidationError, match="complete v1 set"):
        Phase4Protocol.model_validate(raw)


def test_comparison_requires_every_acquisition_policy():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    comparison["acquisition_policies"] = [
        "fixed_sequence",
        "random",
        "max_variance",
    ]

    with pytest.raises(ValidationError, match="complete v1 set"):
        Phase4Protocol.model_validate(raw)


def test_comparison_requires_exact_model_arm_matrix():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    arms = comparison["model_arms"]
    assert isinstance(arms, list)
    comparison["model_arms"] = arms[:-1]

    with pytest.raises(ValidationError, match="exact Phase 4A v1 matrix"):
        Phase4Protocol.model_validate(raw)


def test_comparison_requires_every_component_ablation():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    ablations = comparison["required_ablations"]
    assert isinstance(ablations, list)
    comparison["required_ablations"] = ablations[:-1]

    with pytest.raises(ValidationError, match="complete v1 set"):
        Phase4Protocol.model_validate(raw)


def test_direct_llm_must_remain_a_control_without_posterior_ownership():
    raw = _raw_protocol()
    arm = _arm(raw, "direct_llm_control")
    arm["role"] = "candidate"

    with pytest.raises(ValidationError, match="experimental control"):
        Phase4Protocol.model_validate(raw)


def test_model_arm_evidence_conditions_must_be_unique():
    raw = _raw_protocol()
    arm = _arm(raw, "direct_llm_control")
    evidence_conditions = arm["evidence_conditions"]
    assert isinstance(evidence_conditions, list)
    evidence_conditions.append("structured_only")

    with pytest.raises(ValidationError, match="must be unique"):
        Phase4Protocol.model_validate(raw)


def test_model_arm_explicit_posterior_flag_must_match_representation():
    raw = _raw_protocol()
    arm = _arm(raw, "gaussian_linear_fixed")
    arm["uses_explicit_posterior"] = False

    with pytest.raises(ValidationError, match="must agree with representation"):
        Phase4Protocol.model_validate(raw)


def test_expanding_ontology_requires_expanding_representation():
    raw = _raw_protocol()
    arm = _arm(raw, "hybrid_expanding_ontology")
    arm["representation"] = "explicit_posterior_fixed"

    with pytest.raises(ValidationError, match="expanding ontology requires"):
        Phase4Protocol.model_validate(raw)


def test_uniform_prior_cannot_consume_participant_evidence():
    raw = _raw_protocol()
    arm = _arm(raw, "uniform_prior")
    arm["evidence_conditions"] = ["structured_only"]

    with pytest.raises(ValidationError, match="uniform prior cannot consume"):
        Phase4Protocol.model_validate(raw)


def test_hybrid_readout_requires_explicit_posterior():
    raw = _raw_protocol()
    arm = _arm(raw, "hybrid_fixed_ontology")
    arm["representation"] = "transcript_context_only"
    arm["uses_explicit_posterior"] = False

    with pytest.raises(ValidationError, match="hybrid readout"):
        Phase4Protocol.model_validate(raw)


def test_single_human_path_cannot_be_promoted_to_acquisition_claim():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    comparison["single_participant_acquisition_path_is_descriptive_only"] = False

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_party_prior_remains_evaluation_only_and_post_retest():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    comparison["party_benchmark_never_enters_live_evidence"] = False

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_party_prior_benchmark_cannot_be_silently_removed():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    comparison["evaluation_only_benchmarks"] = []

    with pytest.raises(ValidationError, match="complete v1 set"):
        Phase4Protocol.model_validate(raw)


def test_efficiency_cannot_be_reduced_to_one_hard_session_limit():
    raw = _raw_protocol()
    comparison = raw["comparison"]
    assert isinstance(comparison, dict)
    comparison["one_hard_session_limit_is_a_primary_result"] = True

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    [
        "model_abstention_allowed",
        "model_deferral_allowed",
    ],
)
def test_action_policy_rejects_model_non_selection(field):
    raw = _raw_protocol()
    action_policy = raw["action_policy"]
    assert isinstance(action_policy, dict)
    action_policy[field] = True

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_action_policy_requires_visible_confidence():
    raw = _raw_protocol()
    action_policy = raw["action_policy"]
    assert isinstance(action_policy, dict)
    action_policy["confidence_displayed_when_prediction_is_revealed"] = False

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


def test_action_policy_requires_valid_outputs_for_every_ballot_type():
    raw = _raw_protocol()
    action_policy = raw["action_policy"]
    assert isinstance(action_policy, dict)
    action_policy["supported_ballot_types"] = ["single_choice"]

    with pytest.raises(ValidationError, match="complete v1 set"):
        Phase4Protocol.model_validate(raw)


def test_action_policy_rejects_top_choice_only_rich_ballots():
    raw = _raw_protocol()
    action_policy = raw["action_policy"]
    assert isinstance(action_policy, dict)
    action_policy["format_specific_prediction_required"] = False

    with pytest.raises(ValidationError):
        Phase4Protocol.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bank_profile_id", "wrong_profile", "bank_profile_id"),
        ("bank_profile_version", 2, "bank_profile_version"),
        ("bank_profile_sha256", "0" * 64, "bank_profile_sha256"),
    ],
)
def test_protocol_rejects_wrong_public_bank_profile_binding(
    field,
    value,
    message,
):
    raw = _raw_protocol()
    raw[field] = value
    protocol = Phase4Protocol.model_validate(raw)
    bank_profile = load_bank_profile(BANK_PROFILE_PATH)

    with pytest.raises(ValueError, match=message):
        validate_phase4_protocol_against_bank_profile(protocol, bank_profile)


def test_summary_reports_only_architecture_aggregates():
    protocol = load_phase4_protocol(PROTOCOL_PATH)

    assert phase4_protocol_summary(protocol) == {
        "acquisition_policy_count": 4,
        "model_arm_count": 6,
        "evidence_condition_count": 3,
        "required_ablation_count": 6,
        "evaluation_only_benchmark_count": 1,
        "interviewer_tool_count": 4,
        "target_visible_during_elicitation": False,
        "model_abstention_allowed": False,
        "direct_llm_role": "experimental_prediction_control",
    }


def test_validator_cli_emits_bound_manifest(tmp_path):
    output = tmp_path / "phase4_manifest.json"

    exit_code = main(
        [
            str(PROTOCOL_PATH),
            str(BANK_PROFILE_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    protocol = load_phase4_protocol(PROTOCOL_PATH)
    assert payload["protocol_sha256"] == content_sha256(protocol)
    assert payload["summary"]["model_arm_count"] == 6


def test_validator_cli_rejects_mismatched_profile_binding(tmp_path, capsys):
    raw = deepcopy(_raw_protocol())
    raw["bank_profile_sha256"] = "0" * 64
    protocol_path = tmp_path / "bad_protocol.json"
    protocol_path.write_text(json.dumps(raw), encoding="utf-8")

    exit_code = main([str(protocol_path), str(BANK_PROFILE_PATH)])

    assert exit_code == 1
    assert "bank_profile_sha256" in capsys.readouterr().err
