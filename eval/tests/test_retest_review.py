from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.retest_review import (
    PHASE3_RETEST_REVIEW_PROMPT_SHA256,
    RetestRegistryReviewLog,
    RetestReviewCategory,
    RetestReviewFinding,
    RetestVariantReviewApproval,
    build_nonrevealing_retest_review_summary,
    build_retest_review_ledger_entries,
    validate_locked_retest_review_prompt,
    validate_retest_review_log,
)
from eval.review_artifacts import (
    ReviewFindingDisposition,
    ReviewFindingSeverity,
)
from eval.tests.test_bank_profile import _conforming_final_bank_bundle
from eval.validate_retest_review import main

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
PLANTED_RESTRICTED_TEXT = "PLANTED_RETEST_FINDING_MUST_NOT_LEAK"


def _review_bundle():
    profile, fixture, registry, _ = _conforming_final_bank_bundle()
    first_variant = registry.variants[0]
    finding = RetestReviewFinding(
        finding_id="retest_finding_001",
        variant_id=first_variant.variant_id,
        category=RetestReviewCategory.SEMANTIC_EQUIVALENCE,
        severity=ReviewFindingSeverity.NOTE,
        finding_text=PLANTED_RESTRICTED_TEXT,
        disposition=ReviewFindingDisposition.DEFENDED,
        resolution_notes="The exact comparison supports the defense.",
    )
    approvals = [
        RetestVariantReviewApproval(
            variant_id=variant.variant_id,
            source_measure_id=variant.source_measure_id,
            source_measure_version=variant.source_measure_version,
            packet_sha256=content_sha256(variant.packet),
            findings_count=(1 if variant is first_variant else 0),
            completed_checks=list(RetestReviewCategory),
        )
        for variant in registry.variants
    ]
    log = RetestRegistryReviewLog(
        log_id="preference_eval_retest_review_test_v1",
        log_version=1,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        registry_id=registry.registry_id,
        registry_version=registry.registry_version,
        registry_sha256=content_sha256(registry),
        reviewer_type="ai",
        reviewer_system="claude",
        reviewer_model_version="claude-review-test",
        review_prompt_sha256=PHASE3_RETEST_REVIEW_PROMPT_SHA256,
        completed_at=NOW + timedelta(days=1),
        findings=[finding],
        variant_approvals=approvals,
    )
    return profile, fixture, registry, log


def test_locked_retest_review_prompt_hash_is_current():
    validate_locked_retest_review_prompt()


def test_conforming_retest_review_builds_ledger_and_safe_summary():
    profile, fixture, registry, log = _review_bundle()

    validate_retest_review_log(log, registry, fixture, profile)
    entries = build_retest_review_ledger_entries(
        log,
        registry,
        fixture,
        profile,
    )
    summary = build_nonrevealing_retest_review_summary(
        log,
        registry,
        fixture,
        profile,
    )

    assert len(entries) == 12
    assert all(
        entry.approval.disposition_log_sha256 == content_sha256(log)
        for entry in entries
    )
    assert summary.reviewed_variant_count == 12
    assert summary.findings_count == 1
    assert PLANTED_RESTRICTED_TEXT not in summary.model_dump_json()


def test_retest_approval_requires_every_check_in_order():
    _, _, registry, _ = _review_bundle()
    variant = registry.variants[0]

    with pytest.raises(ValidationError, match="every v1 check"):
        RetestVariantReviewApproval(
            variant_id=variant.variant_id,
            source_measure_id=variant.source_measure_id,
            source_measure_version=variant.source_measure_version,
            packet_sha256=content_sha256(variant.packet),
            findings_count=0,
            completed_checks=list(RetestReviewCategory)[:-1],
        )


def test_retest_review_rejects_wrong_prompt_hash():
    profile, fixture, registry, log = _review_bundle()
    invalid = log.model_copy(update={"review_prompt_sha256": "0" * 64})

    with pytest.raises(ValueError, match="locked Phase 3 prompt"):
        validate_retest_review_log(invalid, registry, fixture, profile)


def test_retest_review_rejects_packet_hash_drift():
    profile, fixture, registry, log = _review_bundle()
    first = log.variant_approvals[0]
    invalid = log.model_copy(
        update={
            "variant_approvals": [
                first.model_copy(update={"packet_sha256": "0" * 64}),
                *log.variant_approvals[1:],
            ]
        }
    )

    with pytest.raises(ValueError, match="exact variant packet"):
        validate_retest_review_log(invalid, registry, fixture, profile)


def test_retest_review_cli_emits_only_safe_aggregate(
    tmp_path,
    capsys,
):
    profile, fixture, registry, log = _review_bundle()
    profile_path = tmp_path / "profile.json"
    fixture_path = tmp_path / "fixture.json"
    registry_path = tmp_path / "registry.json"
    log_path = tmp_path / "review.json"
    summary_path = tmp_path / "summary.json"
    for path, model in (
        (profile_path, profile),
        (fixture_path, fixture),
        (registry_path, registry),
        (log_path, log),
    ):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            str(profile_path),
            str(fixture_path),
            str(registry_path),
            str(log_path),
            "--summary-output",
            str(summary_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert PLANTED_RESTRICTED_TEXT not in captured.out
    assert PLANTED_RESTRICTED_TEXT not in summary_path.read_text(
        encoding="utf-8"
    )


def test_retest_review_cli_error_does_not_echo_restricted_text(
    tmp_path,
    capsys,
):
    profile, fixture, registry, log = _review_bundle()
    invalid = log.model_copy(update={"registry_sha256": "0" * 64})
    paths = [tmp_path / name for name in (
        "profile.json",
        "fixture.json",
        "registry.json",
        "review.json",
    )]
    for path, model in zip(paths, (profile, fixture, registry, invalid)):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            *(str(path) for path in paths),
            "--summary-output",
            str(tmp_path / "summary.json"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert PLANTED_RESTRICTED_TEXT not in captured.err
