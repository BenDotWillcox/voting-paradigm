"""Tests for the frozen Phase 3 bank-authoring profile."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.bank_profile import (
    BankReviewLedger,
    BankReviewLedgerEntry,
    EvaluationBankProfile,
    NeutralityCheck,
    PacketReviewRecord,
    RetestReviewLedgerEntry,
    RetestVariantRegistry,
    ReviewActorType,
    bank_profile_summary,
    build_bank_profile_manifest,
    load_bank_profile,
    validate_final_bank_bundle,
    validate_final_fixture_against_profile,
    validate_review_ledger_against_bank,
    validate_retest_registry_against_bank,
)
from eval.contracts import (
    BallotType,
    EvaluationFixture,
    GeneralizationTier,
    MeasureOption,
    MeasurePacket,
    MeasureDomain,
    MeasureSourceKind,
    MeasureVersion,
    ResponseField,
    RetestPacketVariant,
    SourceRecord,
)
from eval.fixture_io import content_sha256, load_fixture
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
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
RETEST_SLOT_IDS = (
    "fiscal_02",
    "transportation_03",
    "justice_05",
    "governance_06",
    "health_01",
    "education_05",
    "housing_06",
    "environment_01",
    "education_01",
    "housing_02",
    "environment_04",
    "health_04",
)


def _raw_profile() -> dict[str, object]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _source_records(
    slot_id: str,
    count: int,
) -> list[SourceRecord]:
    return [
        SourceRecord(
            source_id=f"{slot_id}_source_{index}",
            title=f"Source {index} for {slot_id}",
            publisher=f"Meridian public source {index}",
            url=f"https://example.gov/{slot_id}/{index}",
            accessed_date=NOW.date(),
            adaptation_notes=(
                "Synthetic test provenance used to exercise final-bank "
                "validation."
            ),
        )
        for index in range(count)
    ]


def _measure_for_slot(
    slot,
) -> MeasureVersion:
    option_count = (
        2 if slot.ballot_type is BallotType.SINGLE_CHOICE else 3
    )
    options = [
        MeasureOption(
            option_id=f"{slot.slot_id}_option_{index}",
            label=f"Option {index + 1}",
            description=f"Test option {index + 1} for {slot.slot_id}.",
            display_order=index,
        )
        for index in range(option_count)
    ]
    source_count = (
        2
        if slot.source_kind
        is MeasureSourceKind.REAL_WORLD_ANCHORED
        else 1
    )
    response_fields = (
        [ResponseField.TOP_CHOICE]
        if slot.ballot_type is BallotType.SINGLE_CHOICE
        else (
            [ResponseField.QUADRATIC]
            if slot.ballot_type is BallotType.QUADRATIC
            else [
                ResponseField.TOP_CHOICE,
                ResponseField.RANKING,
                ResponseField.APPROVAL,
                ResponseField.SCORES,
            ]
        )
    )
    packet = MeasurePacket(
        packet_id=f"{slot.slot_id}_packet",
        version=1,
        status_quo=f"Current test policy for {slot.slot_id}.",
        proposal=f"Proposed test change for {slot.slot_id}.",
        who_is_affected="Residents represented in the test fixture.",
        fiscal_or_operational_effects=(
            "A documented synthetic implementation effect."
        ),
        arguments_by_option={
            option.option_id: f"Good-faith argument for {option.option_id}."
            for option in options
        },
        uncertainties=["The synthetic estimate remains uncertain."],
        definitions={"test term": "A definition used only by this test."},
        sources=_source_records(slot.slot_id, source_count),
        authored_at=NOW,
    )
    return MeasureVersion(
        measure_id=f"measure_{slot.slot_id}",
        version=1,
        title=f"Measure for {slot.slot_id}",
        domain=slot.domain,
        ballot_type=slot.ballot_type,
        response_fields=response_fields,
        source_kind=slot.source_kind,
        intended_generalization_tier=(
            slot.intended_generalization_tier
        ),
        options=options,
        packet=packet,
        quadratic_credit_budget=(
            100 if slot.ballot_type is BallotType.QUADRATIC else None
        ),
        quadratic_allow_negative=(
            False if slot.ballot_type is BallotType.QUADRATIC else None
        ),
    )


def _conforming_final_fixture(
    profile: EvaluationBankProfile,
) -> EvaluationFixture:
    return EvaluationFixture(
        schema_version="preference_eval_fixture.v1",
        fixture_id="preference_eval_final_test_v1",
        fixture_version=1,
        development_only=False,
        order_seed=profile.presentation_order_policy.order_seed,
        created_at=NOW,
        jurisdiction=profile.jurisdiction,
        measures=[
            _measure_for_slot(slot)
            for slot in profile.slots
        ],
    )


def _retest_registry(
    profile: EvaluationBankProfile,
    fixture: EvaluationFixture,
    *,
    slot_ids: tuple[str, ...] = RETEST_SLOT_IDS,
) -> RetestVariantRegistry:
    measure_by_slot_id = {
        measure.measure_id.removeprefix("measure_"): measure
        for measure in fixture.measures
    }
    variants = []
    for index, slot_id in enumerate(slot_ids):
        measure = measure_by_slot_id[slot_id]
        canonical = measure.packet
        packet = canonical.model_copy(
            update={
                "version": canonical.version + 1,
                "status_quo": (
                    f"Retest paraphrase of the status quo for {slot_id}."
                ),
                "proposal": (
                    f"Retest paraphrase of the proposal for {slot_id}."
                ),
                "authored_at": NOW + timedelta(days=1),
            }
        )
        variants.append(
            RetestPacketVariant(
                variant_id=f"{slot_id}_retest",
                source_measure_id=measure.measure_id,
                source_measure_version=measure.version,
                packet=packet,
                order_seed=(
                    profile.presentation_order_policy.order_seed + index + 1
                ),
            )
        )
    return RetestVariantRegistry(
        registry_id="preference_eval_retest_registry_test_v1",
        registry_version=1,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        created_at=NOW + timedelta(days=2),
        variants=variants,
    )


def _approval_record() -> PacketReviewRecord:
    return PacketReviewRecord(
        reviewer_type=ReviewActorType.AI,
        reviewer_system="claude",
        reviewer_model_version="claude-review-test",
        review_prompt_sha256="1" * 64,
        findings_count=0,
        disposition_log_sha256="2" * 64,
        approved=True,
        completed_at=NOW + timedelta(days=3),
    )


def _review_ledger(
    profile: EvaluationBankProfile,
    fixture: EvaluationFixture,
    registry: RetestVariantRegistry,
) -> BankReviewLedger:
    measure_by_slot_id = {
        measure.measure_id.removeprefix("measure_"): measure
        for measure in fixture.measures
    }
    measure_entries = []
    for slot in profile.slots:
        measure = measure_by_slot_id[slot.slot_id]
        primary_source_ids = (
            [measure.packet.sources[0].source_id]
            if measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
            else []
        )
        measure_entries.append(
            BankReviewLedgerEntry(
                slot_id=slot.slot_id,
                measure_id=measure.measure_id,
                measure_version=measure.version,
                measure_sha256=content_sha256(measure),
                primary_official_source_ids=primary_source_ids,
                factual_traceability_reviewed=True,
                contextual_sufficiency_reviewed=True,
                adversarial_neutrality_reviewed=True,
                approval=_approval_record(),
            )
        )
    retest_entries = [
        RetestReviewLedgerEntry(
            variant_id=variant.variant_id,
            source_measure_id=variant.source_measure_id,
            source_measure_version=variant.source_measure_version,
            packet_sha256=content_sha256(variant.packet),
            paraphrase_without_material_change_reviewed=True,
            facts_and_fiscal_estimates_preserved=True,
            option_set_preserved=True,
            prior_response_and_prediction_hidden_by_protocol=True,
            approval=_approval_record(),
        )
        for variant in registry.variants
    ]
    return BankReviewLedger(
        ledger_id="preference_eval_bank_review_test_v1",
        ledger_version=1,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        retest_registry_id=registry.registry_id,
        retest_registry_version=registry.registry_version,
        retest_registry_sha256=content_sha256(registry),
        created_at=NOW + timedelta(days=4),
        measure_entries=measure_entries,
        retest_entries=retest_entries,
    )


def _conforming_final_bank_bundle():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    registry = _retest_registry(profile, fixture)
    ledger = _review_ledger(profile, fixture, registry)
    return profile, fixture, registry, ledger


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
        == "f2d456de6ddd23925cb360eb000aaa96f53329be27b5f8462c27070e03156564"
    )
    assert (
        manifest.jurisdiction_sha256
        == "71ade34979911843a63f2634def50b41be9823b9708a79b12f0ee7a031268671"
    )
    assert (
        manifest.slot_plan_sha256
        == "48e729a5e6fa6c5e21aaf07c731d6dd6251be12ef513988b4db17f5c3a27df9a"
    )
    assert (
        manifest.calibration_sources_sha256
        == "e3370e49f753e343364fccfceb1a457ca0c546f7dc8e0d3374933473a14ee274"
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


def test_profile_records_packet_blind_ai_assisted_review_path():
    profile = load_bank_profile(PROFILE_PATH)

    exposure = profile.case_study_exposure_policy
    assert exposure.exposure_mode == "cold_to_exact_packet_content"
    assert exposure.packet_author_system == "codex"
    assert exposure.content_reviewer_system == "claude"
    assert exposure.topic_level_authoring_briefs_disclosed
    assert exposure.topic_brief_disclosure_date.isoformat() == "2026-07-30"
    assert exposure.exact_packet_text_options_and_values_withheld
    assert exposure.describe_as_ai_assisted_not_human_review
    assert exposure.topic_exposure_caveat_required_for_novel_analysis
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


def test_conforming_final_bank_bundle_passes_every_gate():
    profile, fixture, registry, ledger = _conforming_final_bank_bundle()

    validate_final_bank_bundle(
        fixture,
        profile,
        registry,
        ledger,
    )


def test_final_bank_rejects_an_allocation_mismatch():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    first = fixture.measures[0]
    mismatched = first.model_copy(
        update={"source_kind": MeasureSourceKind.CONSTRUCTED}
    )
    invalid = fixture.model_copy(
        update={"measures": [mismatched, *fixture.measures[1:]]}
    )

    with pytest.raises(ValueError, match="allocation"):
        validate_final_fixture_against_profile(invalid, profile)


def test_final_bank_rejects_jurisdiction_drift():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    drifted_jurisdiction = fixture.jurisdiction.model_copy(
        update={"description": "A changed jurisdiction baseline."}
    )
    invalid = fixture.model_copy(
        update={"jurisdiction": drifted_jurisdiction}
    )

    with pytest.raises(ValueError, match="jurisdiction"):
        validate_final_fixture_against_profile(invalid, profile)


def test_final_bank_rejects_order_seed_drift():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    invalid = fixture.model_copy(
        update={"order_seed": fixture.order_seed + 1}
    )

    with pytest.raises(ValueError, match="order_seed"):
        validate_final_fixture_against_profile(invalid, profile)


def test_final_bank_rejects_insufficient_sources():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    first = fixture.measures[0]
    packet = first.packet.model_copy(
        update={"sources": first.packet.sources[:1]}
    )
    invalid_measure = first.model_copy(update={"packet": packet})
    invalid = fixture.model_copy(
        update={
            "measures": [invalid_measure, *fixture.measures[1:]],
        }
    )

    with pytest.raises(ValueError, match="at least 2 source records"):
        validate_final_fixture_against_profile(invalid, profile)


def test_final_bank_rejects_incomplete_source_fields():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    first = fixture.measures[0]
    incomplete_source = first.packet.sources[0].model_copy(
        update={"publisher": None}
    )
    packet = first.packet.model_copy(
        update={
            "sources": [
                incomplete_source,
                *first.packet.sources[1:],
            ]
        }
    )
    invalid_measure = first.model_copy(update={"packet": packet})
    invalid = fixture.model_copy(
        update={
            "measures": [invalid_measure, *fixture.measures[1:]],
        }
    )

    with pytest.raises(ValueError, match="requires publisher"):
        validate_final_fixture_against_profile(invalid, profile)


def test_final_bank_rejects_negative_quadratic_allocations():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    quadratic_index = next(
        index
        for index, measure in enumerate(fixture.measures)
        if measure.ballot_type is BallotType.QUADRATIC
    )
    quadratic = fixture.measures[quadratic_index].model_copy(
        update={"quadratic_allow_negative": True}
    )
    measures = list(fixture.measures)
    measures[quadratic_index] = quadratic
    invalid = fixture.model_copy(update={"measures": measures})

    with pytest.raises(ValueError, match="prohibit negative"):
        validate_final_fixture_against_profile(invalid, profile)


def test_retest_registry_rejects_the_wrong_tier_composition():
    profile = load_bank_profile(PROFILE_PATH)
    fixture = _conforming_final_fixture(profile)
    invalid_slot_ids = (
        *RETEST_SLOT_IDS[:-1],
        "health_02",
    )
    registry = _retest_registry(
        profile,
        fixture,
        slot_ids=invalid_slot_ids,
    )

    with pytest.raises(
        ValueError,
        match="retest generalization tier",
    ):
        validate_retest_registry_against_bank(
            registry,
            fixture,
            profile,
        )


def test_review_ledger_rejects_an_unbound_slot():
    profile, fixture, registry, ledger = _conforming_final_bank_bundle()
    first = ledger.measure_entries[0].model_copy(
        update={"slot_id": "slot_not_in_profile"}
    )
    invalid = ledger.model_copy(
        update={
            "measure_entries": [first, *ledger.measure_entries[1:]],
        }
    )

    with pytest.raises(ValueError, match="every bank slot"):
        validate_review_ledger_against_bank(
            invalid,
            fixture,
            profile,
            registry,
        )


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
        "cold_to_exact_packet_content"
    )
    assert output["summary"]["content_reviewer_system"] == "claude"


def test_cli_writes_the_manifest_to_an_output_path(tmp_path, capsys):
    output_path = tmp_path / "profile_manifest.json"

    exit_code = main(
        [
            str(PROFILE_PATH),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert (
        written["profile_sha256"]
        == build_bank_profile_manifest(
            load_bank_profile(PROFILE_PATH)
        ).profile_sha256
    )


def test_cli_reports_malformed_profile_without_traceback(tmp_path, capsys):
    invalid_path = tmp_path / "invalid_profile.json"
    invalid_path.write_text("{not-json", encoding="utf-8")

    exit_code = main([str(invalid_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert "Traceback" not in captured.err
