"""Tests for the frozen Phase 3 bank-authoring profile."""

from collections import Counter
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.bank_profile import (
    EvaluationBankProfile,
    NeutralityCheck,
    bank_profile_summary,
    build_bank_profile_manifest,
    load_bank_profile,
    validate_final_fixture_against_profile,
)
from eval.contracts import (
    BallotType,
    GeneralizationTier,
    MeasureDomain,
    MeasureSourceKind,
)
from eval.fixture_io import load_fixture
from eval.validate_bank_profile import main

PROFILE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_bank_profile_v1.json"
)
DEVELOPMENT_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_dev_v1.json"
)


def _raw_profile() -> dict[str, object]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_profile_loads_and_round_trips_without_database():
    profile = load_bank_profile(PROFILE_PATH)

    replayed = EvaluationBankProfile.model_validate_json(
        profile.model_dump_json()
    )

    assert replayed == profile
    assert len(profile.slots) == 48
    assert profile.jurisdiction.jurisdiction_id == "meridian_harborview"


def test_profile_manifest_pins_the_phase_3a_inputs():
    profile = load_bank_profile(PROFILE_PATH)

    manifest = build_bank_profile_manifest(profile)

    assert (
        manifest.profile_sha256
        == "60f9103841fff123d0c65c5cb0e876f394eba681cfc061dab3d4b52de0df6ea7"
    )
    assert (
        manifest.jurisdiction_sha256
        == "3a3568a083f34937b7b6810f549f2f2fe3f6638ca913026fbf07179dec0d8a43"
    )
    assert (
        manifest.slot_plan_sha256
        == "48e729a5e6fa6c5e21aaf07c731d6dd6251be12ef513988b4db17f5c3a27df9a"
    )


def test_each_domain_has_the_frozen_source_and_tier_balance():
    profile = load_bank_profile(PROFILE_PATH)

    for domain in MeasureDomain:
        slots = [slot for slot in profile.slots if slot.domain is domain]

        assert len(slots) == 6
        assert Counter(slot.source_kind for slot in slots) == {
            MeasureSourceKind.REAL_WORLD_ANCHORED: 4,
            MeasureSourceKind.CONSTRUCTED: 2,
        }
        assert Counter(
            slot.intended_generalization_tier for slot in slots
        ) == {
            GeneralizationTier.FAMILIAR: 2,
            GeneralizationTier.ADJACENT: 2,
            GeneralizationTier.NOVEL: 2,
        }


def test_source_tier_rotation_avoids_a_constructed_novel_shortcut():
    profile = load_bank_profile(PROFILE_PATH)

    counts = Counter(
        (slot.source_kind, slot.intended_generalization_tier)
        for slot in profile.slots
    )

    assert counts == {
        (
            MeasureSourceKind.REAL_WORLD_ANCHORED,
            GeneralizationTier.FAMILIAR,
        ): 11,
        (
            MeasureSourceKind.REAL_WORLD_ANCHORED,
            GeneralizationTier.ADJACENT,
        ): 11,
        (
            MeasureSourceKind.REAL_WORLD_ANCHORED,
            GeneralizationTier.NOVEL,
        ): 10,
        (
            MeasureSourceKind.CONSTRUCTED,
            GeneralizationTier.FAMILIAR,
        ): 5,
        (
            MeasureSourceKind.CONSTRUCTED,
            GeneralizationTier.ADJACENT,
        ): 5,
        (
            MeasureSourceKind.CONSTRUCTED,
            GeneralizationTier.NOVEL,
        ): 6,
    }


def test_profile_freezes_the_ballot_mix():
    profile = load_bank_profile(PROFILE_PATH)

    assert Counter(slot.ballot_type for slot in profile.slots) == {
        BallotType.SINGLE_CHOICE: 38,
        BallotType.RANKED: 3,
        BallotType.APPROVAL: 3,
        BallotType.SCORE: 3,
        BallotType.QUADRATIC: 1,
    }


def test_profile_freezes_cold_ai_assisted_review_path():
    profile = load_bank_profile(PROFILE_PATH)

    exposure = profile.case_study_exposure_policy
    assert exposure.exposure_mode == "cold_first_exposure"
    assert exposure.packet_author_system == "codex"
    assert exposure.content_reviewer_system == "claude"
    assert exposure.exact_packet_content_withheld_from_participant
    assert exposure.describe_as_ai_assisted_not_human_review
    assert exposure.human_content_review_required_before_external_pilot
    assert (
        NeutralityCheck.MATERIAL_CONTEXT_SUFFICIENCY
        in profile.neutrality_review_policy.required_checks
    )


def test_profile_rejects_removing_contextual_sufficiency_review():
    raw = _raw_profile()
    policy = raw["neutrality_review_policy"]
    assert isinstance(policy, dict)
    checks = policy["required_checks"]
    assert isinstance(checks, list)
    checks.remove("material_context_sufficiency")

    with pytest.raises(ValidationError, match="complete v1 neutrality set"):
        EvaluationBankProfile.model_validate(raw)


def test_profile_rejects_a_slot_allocation_change():
    raw = _raw_profile()
    slots = raw["slots"]
    assert isinstance(slots, list)
    assert isinstance(slots[0], dict)
    slots[0]["source_kind"] = "constructed"

    with pytest.raises(ValidationError, match="source kind counts"):
        EvaluationBankProfile.model_validate(raw)


def test_profile_rejects_removing_a_political_cue_exclusion():
    raw = _raw_profile()
    policy = raw["packet_and_model_policy"]
    assert isinstance(policy, dict)
    exclusions = policy["excluded_participant_packet_cues"]
    assert isinstance(exclusions, list)
    exclusions.remove("party_labels")

    with pytest.raises(ValidationError, match="complete v1 exclusion set"):
        EvaluationBankProfile.model_validate(raw)


def test_profile_rejects_incomplete_calibration_provenance():
    raw = _raw_profile()
    sources = raw["jurisdiction_calibration_sources"]
    assert isinstance(sources, list)
    assert isinstance(sources[0], dict)
    del sources[0]["adaptation_notes"]

    with pytest.raises(
        ValidationError,
        match="calibration sources require publisher",
    ):
        EvaluationBankProfile.model_validate(raw)


def test_development_fixture_cannot_pass_as_the_final_bank():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = load_fixture(DEVELOPMENT_FIXTURE_PATH)

    with pytest.raises(ValueError, match="must not be marked development_only"):
        validate_final_fixture_against_profile(fixture, profile)


def test_cli_prints_manifest_and_inspectable_summary(capsys):
    exit_code = main([str(PROFILE_PATH)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert (
        output["schema_version"]
        == "preference_eval_bank_profile_manifest.v1"
    )
    assert output["summary"] == bank_profile_summary(
        load_bank_profile(PROFILE_PATH)
    )
    assert output["summary"]["measure_count"] == 48
    assert output["summary"]["case_study_exposure_mode"] == (
        "cold_first_exposure"
    )
    assert output["summary"]["content_reviewer_system"] == "claude"


def test_cli_reports_malformed_profile_without_traceback(tmp_path, capsys):
    invalid_path = tmp_path / "invalid_profile.json"
    invalid_path.write_text("{not-json", encoding="utf-8")

    exit_code = main([str(invalid_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert "Traceback" not in captured.err
