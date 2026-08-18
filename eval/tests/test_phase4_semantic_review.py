from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from preferences.questions.bank import QuestionBank

import eval.build_phase4_semantic_map as build_map_module
from eval.bank_profile import load_bank_profile
from eval.fixture_io import content_sha256
from eval.phase4_protocol import load_phase4_protocol
from eval.phase4_semantic_review import (
    PHASE4_SEMANTIC_REVIEW_PROMPT_SHA256,
    SemanticDimensionAssignment,
    SemanticImportance,
    SemanticMapAuthoringBundle,
    SemanticMapReviewCategory,
    SemanticMapReviewFinding,
    SemanticMapReviewLog,
    SemanticMeasureAuthoringRecord,
    SemanticMeasureReviewApproval,
    SemanticOptionPosition,
    build_authored_semantic_map,
    build_nonrevealing_semantic_map_review_summary,
    load_semantic_map_authoring_profile,
    semantic_map_authoring_summary,
    reviewed_semantic_mapper_reference,
    validate_locked_semantic_review_prompt,
    validate_semantic_map_artifacts,
    validate_semantic_map_authoring_profile,
    validate_semantic_map_review_log,
)
from eval.review_artifacts import (
    ReviewFindingDisposition,
    ReviewFindingSeverity,
)
from eval.tests.test_bank_profile import _conforming_final_bank_bundle
from eval.validate_phase4_semantic_profile import (
    main as validate_profile_main,
)
from eval.build_phase4_semantic_map import main as build_map_main
from eval.build_phase4_semantic_map import require_safe_semantic_map_output
from eval.validate_phase4_semantic_review import main as validate_review_main

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT
    / "eval/fixtures/preference_eval_semantic_authoring_profile_v1.json"
)
BANK_PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_bank_profile_v1.json"
)
PROTOCOL_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_protocol_v1.json"
)
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
PLANTED_RESTRICTED_TEXT = "PLANTED_SEMANTIC_RATIONALE_MUST_NOT_LEAK"


def artifacts():
    bank_profile, fixture, _, _ = _conforming_final_bank_bundle()
    profile = load_semantic_map_authoring_profile(PROFILE_PATH)
    protocol = load_phase4_protocol(PROTOCOL_PATH)
    return profile, bank_profile, protocol, fixture


def authoring_bundle(
    profile,
    fixture,
) -> SemanticMapAuthoringBundle:
    dimension_id = profile.ontology.item_ids[0]
    records = []
    for measure in fixture.measures:
        positions = [
            SemanticOptionPosition(
                option_id=option.option_id,
                ordinal_position=(-1 if index == 0 else 1),
                supporting_content_paths=[f"/options/{index}/description"],
            )
            for index, option in enumerate(measure.options)
        ]
        records.append(
            SemanticMeasureAuthoringRecord(
                measure_id=measure.measure_id,
                measure_version=measure.version,
                packet_version=measure.packet.version,
                packet_sha256=content_sha256(measure.packet),
                dimension_assignments=[
                    SemanticDimensionAssignment(
                        dimension_id=dimension_id,
                        importance=SemanticImportance.PRIMARY,
                        option_positions=positions,
                        rationale=PLANTED_RESTRICTED_TEXT,
                    )
                ],
            )
        )
    return SemanticMapAuthoringBundle(
        bundle_id="preference_eval_semantic_authoring_test_v1",
        bundle_version=1,
        authoring_profile_id=profile.profile_id,
        authoring_profile_version=profile.profile_version,
        authoring_profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        mapper_id="preference_eval_semantic_map_test_v1",
        mapper_version=1,
        author_system="codex",
        authored_at=NOW,
        measure_records=records,
    )


def review_log(profile, fixture, bundle, semantic_map):
    first_mapping = semantic_map.mappings[0]
    finding = SemanticMapReviewFinding(
        finding_id="semantic_finding_001",
        measure_id=first_mapping.measure_id,
        measure_version=first_mapping.measure_version,
        dimension_id=profile.ontology.item_ids[0],
        category=SemanticMapReviewCategory.PACKET_ONLY_GROUNDING,
        severity=ReviewFindingSeverity.NOTE,
        finding_text=PLANTED_RESTRICTED_TEXT,
        disposition=ReviewFindingDisposition.DEFENDED,
        resolution_notes="The exact restricted comparison supports it.",
    )
    approvals = [
        SemanticMeasureReviewApproval(
            measure_id=mapping.measure_id,
            measure_version=mapping.measure_version,
            mapping_sha256=content_sha256(mapping),
            findings_count=(1 if mapping is first_mapping else 0),
            completed_checks=list(SemanticMapReviewCategory),
        )
        for mapping in semantic_map.mappings
    ]
    return SemanticMapReviewLog(
        log_id="preference_eval_semantic_review_test_v1",
        log_version=1,
        authoring_profile_id=profile.profile_id,
        authoring_profile_version=profile.profile_version,
        authoring_profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        authoring_bundle_id=bundle.bundle_id,
        authoring_bundle_version=bundle.bundle_version,
        authoring_bundle_sha256=content_sha256(bundle),
        mapper_id=semantic_map.mapper_id,
        mapper_version=semantic_map.mapper_version,
        mapper_sha256=content_sha256(semantic_map),
        reviewer_type="ai",
        reviewer_system="claude",
        reviewer_model_version="claude-review-test",
        review_prompt_sha256=PHASE4_SEMANTIC_REVIEW_PROMPT_SHA256,
        completed_at=NOW + timedelta(days=1),
        findings=[finding],
        measure_approvals=approvals,
    )


def write_model(path: Path, model) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def test_locked_semantic_review_prompt_hash_is_current() -> None:
    validate_locked_semantic_review_prompt()


def test_public_authoring_profile_binds_all_upstream_inputs() -> None:
    profile, bank_profile, protocol, _ = artifacts()

    validate_semantic_map_authoring_profile(
        profile,
        bank_profile,
        protocol,
        QuestionBank.load_default(),
    )

    assert content_sha256(profile) == (
        "baec5e626b41c46e0363e3966af9be02"
        "683056b371173c76c57b13db3fbd2dd3"
    )


def test_authoring_bundle_derives_centered_coarse_runtime_map() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)

    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    validate_semantic_map_artifacts(
        semantic_map,
        bundle,
        profile,
        fixture,
    )

    first = semantic_map.mappings[0]
    dimension_id = profile.ontology.item_ids[0]
    weights = [
        stance.dimension_weights[dimension_id]
        for stance in first.option_stances
    ]
    assert sum(weights) == pytest.approx(0.0, abs=1e-12)
    assert max(abs(value) for value in weights) == 1.0
    summary = semantic_map_authoring_summary(
        semantic_map,
        bundle,
        profile,
    )
    assert PLANTED_RESTRICTED_TEXT not in json.dumps(summary)


def test_runtime_map_cannot_drift_from_restricted_rationale() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    first_mapping = semantic_map.mappings[0]
    first_stance = first_mapping.option_stances[0]
    dimension_id = profile.ontology.item_ids[0]
    drifted_stance = first_stance.model_copy(
        update={"dimension_weights": {dimension_id: -0.75}}
    )
    drifted_mapping = first_mapping.model_copy(
        update={
            "option_stances": [
                drifted_stance,
                *first_mapping.option_stances[1:],
            ]
        }
    )
    drifted = semantic_map.model_copy(
        update={
            "mappings": [drifted_mapping, *semantic_map.mappings[1:]]
        }
    )

    with pytest.raises(ValueError, match="exact derived authoring bundle"):
        validate_semantic_map_artifacts(
            drifted,
            bundle,
            profile,
            fixture,
        )


def test_authoring_rejects_nonparticipant_packet_paths() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    first_record = bundle.measure_records[0]
    assignment = first_record.dimension_assignments[0]
    first_position = assignment.option_positions[0].model_copy(
        update={"supporting_content_paths": ["/packet/sources/0/url"]}
    )
    invalid_assignment = assignment.model_copy(
        update={
            "option_positions": [
                first_position,
                *assignment.option_positions[1:],
            ]
        }
    )
    invalid_record = first_record.model_copy(
        update={"dimension_assignments": [invalid_assignment]}
    )
    invalid = bundle.model_copy(
        update={
            "measure_records": [
                invalid_record,
                *bundle.measure_records[1:],
            ]
        }
    )

    with pytest.raises(ValueError, match="participant-facing packet field"):
        build_authored_semantic_map(invalid, profile, fixture)


def test_authoring_requires_a_primary_dimension() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    record = bundle.measure_records[0]
    secondary = record.dimension_assignments[0].model_copy(
        update={"importance": SemanticImportance.SECONDARY}
    )

    with pytest.raises(ValidationError, match="primary dimension"):
        SemanticMeasureAuthoringRecord(
            measure_id=record.measure_id,
            measure_version=record.measure_version,
            packet_version=record.packet_version,
            packet_sha256=record.packet_sha256,
            dimension_assignments=[secondary],
        )


def test_conforming_review_builds_nonrevealing_summary() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    log = review_log(profile, fixture, bundle, semantic_map)

    validate_semantic_map_review_log(
        log,
        semantic_map,
        bundle,
        profile,
        fixture,
    )
    summary = build_nonrevealing_semantic_map_review_summary(
        log,
        semantic_map,
        bundle,
        profile,
        fixture,
    )

    assert summary.reviewed_measure_count == 48
    assert summary.findings_count == 1
    assert summary.all_mappings_approved is True
    assert PLANTED_RESTRICTED_TEXT not in summary.model_dump_json()
    approval = reviewed_semantic_mapper_reference(summary)
    assert approval.semantic_mapper.artifact_sha256 == summary.mapper_sha256
    assert approval.review_summary_sha256 == content_sha256(summary)
    assert approval.approved_measure_count == 48


def test_final_map_output_is_restricted_but_development_output_is_not() -> None:
    tracked_output = (
        ROOT / "eval/fixtures/accidental_held_out_semantic_map.json"
    )

    with pytest.raises(ValueError, match="eval/restricted_bank"):
        require_safe_semantic_map_output(
            tracked_output,
            development_only=False,
        )
    require_safe_semantic_map_output(
        tracked_output,
        development_only=True,
    )


def test_builder_cli_refuses_final_map_outside_restricted_root(
    tmp_path,
    capsys,
) -> None:
    profile, bank_profile, protocol, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    input_models = [profile, bank_profile, protocol, fixture, bundle]
    input_paths = [
        tmp_path / f"input_{index}.json" for index in range(len(input_models))
    ]
    for path, model in zip(input_paths, input_models, strict=True):
        write_model(path, model)
    output_path = tmp_path / "accidental_final_map.json"

    exit_code = build_map_main(
        [
            str(input_paths[4]),
            str(input_paths[0]),
            str(input_paths[1]),
            str(input_paths[2]),
            str(input_paths[3]),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert not output_path.exists()
    assert PLANTED_RESTRICTED_TEXT not in captured.err


def test_review_rejects_author_as_reviewer_and_wrong_ai() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    log = review_log(profile, fixture, bundle, semantic_map)

    with pytest.raises(ValueError, match="must differ"):
        validate_semantic_map_review_log(
            log.model_copy(update={"reviewer_system": "codex"}),
            semantic_map,
            bundle,
            profile,
            fixture,
        )
    with pytest.raises(ValueError, match="does not match the public profile"):
        validate_semantic_map_review_log(
            log.model_copy(update={"reviewer_system": "other_ai"}),
            semantic_map,
            bundle,
            profile,
            fixture,
        )


def test_review_rejects_wrong_prompt_and_mapping_hash() -> None:
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    log = review_log(profile, fixture, bundle, semantic_map)

    with pytest.raises(ValueError, match="locked v1 prompt"):
        validate_semantic_map_review_log(
            log.model_copy(update={"review_prompt_sha256": "0" * 64}),
            semantic_map,
            bundle,
            profile,
            fixture,
        )
    first = log.measure_approvals[0].model_copy(
        update={"mapping_sha256": "0" * 64}
    )
    with pytest.raises(ValueError, match="exact mapping"):
        validate_semantic_map_review_log(
            log.model_copy(
                update={
                    "measure_approvals": [
                        first,
                        *log.measure_approvals[1:],
                    ]
                }
            ),
            semantic_map,
            bundle,
            profile,
            fixture,
        )


def test_approval_requires_every_check_and_unresolved_blocking_is_impossible():
    profile, _, _, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    mapping = semantic_map.mappings[0]

    with pytest.raises(ValidationError, match="every v1 check"):
        SemanticMeasureReviewApproval(
            measure_id=mapping.measure_id,
            measure_version=mapping.measure_version,
            mapping_sha256=content_sha256(mapping),
            findings_count=0,
            completed_checks=list(SemanticMapReviewCategory)[:-1],
        )
    with pytest.raises(ValidationError, match="must be resolved"):
        SemanticMapReviewFinding(
            finding_id="unresolved_blocker",
            measure_id=mapping.measure_id,
            measure_version=mapping.measure_version,
            category=SemanticMapReviewCategory.DIRECTIONAL_ACCURACY,
            severity=ReviewFindingSeverity.BLOCKING,
            finding_text=PLANTED_RESTRICTED_TEXT,
            disposition=ReviewFindingDisposition.DEFENDED,
            resolution_notes="Not resolved.",
        )


def test_profile_cli_emits_only_public_aggregate(capsys) -> None:
    exit_code = validate_profile_main(
        [str(PROFILE_PATH), str(BANK_PROFILE_PATH), str(PROTOCOL_PATH)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    output = json.loads(captured.out)
    assert output["expected_measure_count"] == 48
    assert output["exact_mapping_content_omitted"] is True


def test_build_and_review_clis_never_emit_restricted_prose(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    profile, bank_profile, protocol, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    log = review_log(profile, fixture, bundle, semantic_map)
    paths = {
        "profile": tmp_path / "profile.json",
        "bank": tmp_path / "bank.json",
        "protocol": tmp_path / "protocol.json",
        "fixture": tmp_path / "fixture.json",
        "bundle": tmp_path / "bundle.json",
        "map": tmp_path / "eval/restricted_bank/map.json",
        "review": tmp_path / "review.json",
        "summary": tmp_path / "summary.json",
    }
    for key, model in (
        ("profile", profile),
        ("bank", bank_profile),
        ("protocol", protocol),
        ("fixture", fixture),
        ("bundle", bundle),
        ("review", log),
    ):
        write_model(paths[key], model)
    monkeypatch.setattr(
        build_map_module,
        "RESTRICTED_OUTPUT_ROOT",
        tmp_path / "eval/restricted_bank",
    )

    build_exit = build_map_main(
        [
            str(paths["bundle"]),
            str(paths["profile"]),
            str(paths["bank"]),
            str(paths["protocol"]),
            str(paths["fixture"]),
            "--output",
            str(paths["map"]),
        ]
    )
    build_output = capsys.readouterr()
    assert build_exit == 0
    assert PLANTED_RESTRICTED_TEXT not in build_output.out

    review_exit = validate_review_main(
        [
            str(paths["review"]),
            str(paths["map"]),
            str(paths["bundle"]),
            str(paths["profile"]),
            str(paths["bank"]),
            str(paths["protocol"]),
            str(paths["fixture"]),
            "--summary-output",
            str(paths["summary"]),
        ]
    )
    review_output = capsys.readouterr()
    assert review_exit == 0
    assert PLANTED_RESTRICTED_TEXT not in review_output.out
    assert PLANTED_RESTRICTED_TEXT not in paths["summary"].read_text(
        encoding="utf-8"
    )


def test_review_cli_error_does_not_echo_restricted_prose(
    tmp_path,
    capsys,
) -> None:
    profile, bank_profile, protocol, fixture = artifacts()
    bundle = authoring_bundle(profile, fixture)
    semantic_map = build_authored_semantic_map(bundle, profile, fixture)
    log = review_log(profile, fixture, bundle, semantic_map).model_copy(
        update={"mapper_sha256": "0" * 64}
    )
    models = [
        log,
        semantic_map,
        bundle,
        profile,
        bank_profile,
        protocol,
        fixture,
    ]
    paths = [tmp_path / f"artifact_{index}.json" for index in range(7)]
    for path, model in zip(paths, models, strict=True):
        write_model(path, model)

    exit_code = validate_review_main(
        [
            *(str(path) for path in paths),
            "--summary-output",
            str(tmp_path / "summary.json"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert PLANTED_RESTRICTED_TEXT not in captured.err
