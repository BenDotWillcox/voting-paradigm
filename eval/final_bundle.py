"""Assembly and aggregate validation for the frozen Phase 3C bundle."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import field_validator

from .bank_authoring import DomainBankBatch
from .bank_profile import (
    BankReviewLedger,
    EvaluationBankProfile,
    RetestVariantRegistry,
    validate_final_bank_bundle,
)
from .contracts import (
    ContractModel,
    EvaluationFixture,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .presentation_plan import (
    EvaluationPresentationPlan,
    validate_presentation_plan_against_bundle,
)
from .retest_review import (
    RetestRegistryReviewLog,
    build_retest_review_ledger_entries,
)
from .review_artifacts import (
    DomainBatchReviewLog,
    bank_review_ledger_entries_for_batch,
)


class FinalExecutionBundleManifest(ContractModel):
    """Participant-safe hashes and counts for one accepted Phase 3C bundle."""

    schema_version: Literal["preference_eval_final_bundle_manifest.v1"] = (
        "preference_eval_final_bundle_manifest.v1"
    )
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    retest_registry_id: StableId
    retest_registry_version: PositiveVersion
    retest_registry_sha256: Sha256Digest
    review_ledger_id: StableId
    review_ledger_version: PositiveVersion
    review_ledger_sha256: Sha256Digest
    presentation_plan_id: StableId
    presentation_plan_version: PositiveVersion
    presentation_plan_sha256: Sha256Digest
    created_at: datetime
    measure_count: Literal[48] = 48
    retest_variant_count: Literal[12] = 12
    wave_count: Literal[6] = 6
    measures_per_wave: Literal[8] = 8
    exact_content_omitted: Literal[True] = True
    validation_status: Literal["passed"] = "passed"

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


def assemble_final_review_ledger(
    profile: EvaluationBankProfile,
    fixture: EvaluationFixture,
    registry: RetestVariantRegistry,
    batch_reviews: list[tuple[DomainBankBatch, DomainBatchReviewLog]],
    retest_review: RetestRegistryReviewLog,
    *,
    ledger_id: str,
    ledger_version: int,
    created_at: datetime,
) -> BankReviewLedger:
    """Assemble exact measure and retest approvals in frozen profile order."""

    entries_by_slot = {}
    for batch, review in batch_reviews:
        for entry in bank_review_ledger_entries_for_batch(
            review,
            batch,
            profile,
        ):
            if entry.slot_id in entries_by_slot:
                raise ValueError(
                    "reviewed batches contain a duplicate bank slot"
                )
            entries_by_slot[entry.slot_id] = entry
    expected_slot_ids = [slot.slot_id for slot in profile.slots]
    if set(entries_by_slot) != set(expected_slot_ids):
        raise ValueError(
            "reviewed batches do not cover every frozen bank slot"
        )
    retest_entries = build_retest_review_ledger_entries(
        retest_review,
        registry,
        fixture,
        profile,
    )
    ledger = BankReviewLedger(
        ledger_id=ledger_id,
        ledger_version=ledger_version,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        retest_registry_id=registry.registry_id,
        retest_registry_version=registry.registry_version,
        retest_registry_sha256=content_sha256(registry),
        created_at=created_at,
        measure_entries=[
            entries_by_slot[slot_id] for slot_id in expected_slot_ids
        ],
        retest_entries=retest_entries,
    )
    validate_final_bank_bundle(fixture, profile, registry, ledger)
    return ledger


def validate_final_execution_bundle(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    ledger: BankReviewLedger,
    plan: EvaluationPresentationPlan,
) -> None:
    validate_final_bank_bundle(fixture, profile, registry, ledger)
    validate_presentation_plan_against_bundle(
        plan,
        fixture,
        profile,
        registry,
    )


def build_final_execution_bundle_manifest(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    ledger: BankReviewLedger,
    plan: EvaluationPresentationPlan,
    *,
    created_at: datetime,
) -> FinalExecutionBundleManifest:
    validate_final_execution_bundle(
        fixture,
        profile,
        registry,
        ledger,
        plan,
    )
    policy = profile.presentation_order_policy
    return FinalExecutionBundleManifest(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        retest_registry_id=registry.registry_id,
        retest_registry_version=registry.registry_version,
        retest_registry_sha256=content_sha256(registry),
        review_ledger_id=ledger.ledger_id,
        review_ledger_version=ledger.ledger_version,
        review_ledger_sha256=content_sha256(ledger),
        presentation_plan_id=plan.plan_id,
        presentation_plan_version=plan.plan_version,
        presentation_plan_sha256=content_sha256(plan),
        created_at=created_at,
        measure_count=len(fixture.measures),
        retest_variant_count=len(registry.variants),
        wave_count=policy.wave_count,
        measures_per_wave=policy.measures_per_wave,
    )
