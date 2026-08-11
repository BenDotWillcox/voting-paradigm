from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eval.bank_authoring import assemble_final_fixture
from eval.bank_profile import load_bank_review_ledger
from eval.build_final_review_ledger import main as build_ledger_main
from eval.final_bundle import (
    assemble_final_review_ledger,
    build_final_execution_bundle_manifest,
    validate_final_execution_bundle,
)
from eval.fixture_io import content_sha256
from eval.presentation_plan import build_presentation_plan
from eval.retest_review import (
    PHASE3_RETEST_REVIEW_PROMPT_SHA256,
    RetestRegistryReviewLog,
    RetestReviewCategory,
    RetestVariantReviewApproval,
)
from eval.tests.test_bank_authoring import _domain_batches, _review_log
from eval.tests.test_bank_profile import _retest_registry
from eval.validate_final_bundle import main

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _final_execution_bundle():
    profile, batches = _domain_batches()
    fixture = assemble_final_fixture(
        profile,
        batches,
        fixture_id="preference_eval_final_bundle_test_v1",
        fixture_version=1,
        created_at=NOW,
    )
    registry = _retest_registry(profile, fixture)
    retest_review = RetestRegistryReviewLog(
        log_id="preference_eval_retest_review_bundle_test_v1",
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
        variant_approvals=[
            RetestVariantReviewApproval(
                variant_id=variant.variant_id,
                source_measure_id=variant.source_measure_id,
                source_measure_version=variant.source_measure_version,
                packet_sha256=content_sha256(variant.packet),
                findings_count=0,
                completed_checks=list(RetestReviewCategory),
            )
            for variant in registry.variants
        ],
    )
    ledger = assemble_final_review_ledger(
        profile,
        fixture,
        registry,
        [(batch, _review_log(batch, profile)) for batch in batches],
        retest_review,
        ledger_id="preference_eval_bank_review_bundle_test_v1",
        ledger_version=1,
        created_at=NOW + timedelta(days=2),
    )
    plan = build_presentation_plan(
        fixture,
        profile,
        registry,
        plan_id="preference_eval_presentation_plan_bundle_test_v1",
        plan_version=1,
        created_at=NOW + timedelta(days=2),
    )
    return profile, fixture, registry, ledger, plan, batches, retest_review


def test_conforming_final_execution_bundle_passes_and_builds_manifest():
    profile, fixture, registry, ledger, plan, _, _ = (
        _final_execution_bundle()
    )

    validate_final_execution_bundle(
        fixture,
        profile,
        registry,
        ledger,
        plan,
    )
    manifest = build_final_execution_bundle_manifest(
        fixture,
        profile,
        registry,
        ledger,
        plan,
        created_at=NOW + timedelta(days=3),
    )

    assert manifest.measure_count == 48
    assert manifest.retest_variant_count == 12
    assert manifest.review_ledger_sha256 == content_sha256(ledger)
    assert manifest.presentation_plan_sha256 == content_sha256(plan)


def test_final_review_ledger_rejects_duplicate_batch_coverage():
    profile, fixture, registry, _, _, batches, retest_review = (
        _final_execution_bundle()
    )
    duplicate_reviews = [
        (batch, _review_log(batch, profile)) for batch in batches
    ]
    duplicate_reviews.append(
        (batches[0], _review_log(batches[0], profile))
    )

    with pytest.raises(ValueError, match="duplicate bank slot"):
        assemble_final_review_ledger(
            profile,
            fixture,
            registry,
            duplicate_reviews,
            retest_review,
            ledger_id="invalid_duplicate_ledger",
            ledger_version=1,
            created_at=NOW + timedelta(days=2),
        )


def test_build_final_review_ledger_cli_writes_ledger_with_safe_stdout(
    tmp_path,
    capsys,
):
    profile, fixture, registry, expected, _, batches, retest_review = (
        _final_execution_bundle()
    )
    profile_path = tmp_path / "profile.json"
    fixture_path = tmp_path / "fixture.json"
    registry_path = tmp_path / "registry.json"
    retest_review_path = tmp_path / "retest_review.json"
    output_path = tmp_path / "ledger.json"
    for path, model in (
        (profile_path, profile),
        (fixture_path, fixture),
        (registry_path, registry),
        (retest_review_path, retest_review),
    ):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    batch_review_args = []
    planted_review_text = None
    for index, batch in enumerate(batches):
        review = _review_log(batch, profile)
        if planted_review_text is None and review.findings:
            planted_review_text = review.findings[0].finding_text
        batch_path = tmp_path / f"batch_{index}.json"
        review_path = tmp_path / f"review_{index}.json"
        batch_path.write_text(
            batch.model_dump_json(indent=2),
            encoding="utf-8",
        )
        review_path.write_text(
            review.model_dump_json(indent=2),
            encoding="utf-8",
        )
        batch_review_args.extend(
            ["--batch-review", str(batch_path), str(review_path)]
        )

    exit_code = build_ledger_main(
        [
            str(profile_path),
            str(fixture_path),
            str(registry_path),
            str(retest_review_path),
            *batch_review_args,
            "--ledger-id",
            expected.ledger_id,
            "--ledger-version",
            str(expected.ledger_version),
            "--created-at",
            expected.created_at.isoformat(),
            "--output",
            str(output_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert load_bank_review_ledger(output_path) == expected
    assert '"measure_entry_count": 48' in captured.out
    assert '"retest_entry_count": 12' in captured.out
    if planted_review_text is not None:
        assert planted_review_text not in captured.out


def test_final_bundle_cli_emits_only_aggregate_manifest(tmp_path, capsys):
    profile, fixture, registry, ledger, plan, _, _ = (
        _final_execution_bundle()
    )
    paths = [tmp_path / name for name in (
        "profile.json",
        "fixture.json",
        "registry.json",
        "ledger.json",
        "plan.json",
    )]
    for path, model in zip(
        paths,
        (profile, fixture, registry, ledger, plan),
    ):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    exit_code = main(
        [
            *(str(path) for path in paths),
            "--created-at",
            (NOW + timedelta(days=3)).isoformat(),
            "--manifest-output",
            str(manifest_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"measure_count": 48' in captured.out
    assert '"exact_content_omitted": true' in captured.out
    assert manifest_path.is_file()
