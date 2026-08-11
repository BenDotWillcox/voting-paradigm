"""Restricted retest-variant review contracts and safe aggregate summaries."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .bank_profile import (
    EvaluationBankProfile,
    PacketReviewRecord,
    RetestReviewLedgerEntry,
    RetestVariantRegistry,
    ReviewActorType,
    validate_retest_registry_against_bank,
)
from .contracts import (
    ContractModel,
    EvaluationFixture,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .review_artifacts import (
    NonNegativeCount,
    ReviewFindingDisposition,
    ReviewFindingSeverity,
    canonical_text_sha256,
    review_system_matches,
)

PHASE3_RETEST_REVIEW_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "phase3_retest_review_v1.md"
)
PHASE3_RETEST_REVIEW_PROMPT_SHA256 = (
    "f12ff8b812fcb395b620d759340b2dad"
    "5a54ff58126ed0ee66f8fd0958b98786"
)


class RetestReviewCategory(str, Enum):
    CANONICAL_LINKAGE = "canonical_linkage"
    SEMANTIC_EQUIVALENCE = "semantic_equivalence"
    FACT_AND_VALUE_PRESERVATION = "fact_and_value_preservation"
    OPTION_AND_SOURCE_PRESERVATION = "option_and_source_preservation"
    NEUTRALITY_PRESERVATION = "neutrality_preservation"
    FORMAT_FIDELITY = "format_fidelity"
    PRIOR_RESPONSE_EXCLUSION = "prior_response_exclusion"


class RetestReviewFinding(ContractModel):
    """One exact-content finding kept in the restricted retest log."""

    record_version: Literal["retest_review_finding.v1"] = (
        "retest_review_finding.v1"
    )
    finding_id: StableId
    variant_id: StableId
    category: RetestReviewCategory
    severity: ReviewFindingSeverity
    finding_text: NonEmptyText
    disposition: ReviewFindingDisposition
    resolution_notes: NonEmptyText

    @model_validator(mode="after")
    def blocking_findings_must_be_resolved(self) -> Self:
        if (
            self.severity is ReviewFindingSeverity.BLOCKING
            and self.disposition is not ReviewFindingDisposition.RESOLVED
        ):
            raise ValueError(
                "blocking retest findings must be resolved before approval"
            )
        return self


class RetestVariantReviewApproval(ContractModel):
    """Approval of one exact alternate packet hash."""

    record_version: Literal["retest_variant_review_approval.v1"] = (
        "retest_variant_review_approval.v1"
    )
    variant_id: StableId
    source_measure_id: StableId
    source_measure_version: PositiveVersion
    packet_sha256: Sha256Digest
    findings_count: NonNegativeCount
    completed_checks: list[RetestReviewCategory]
    approved: Literal[True] = True

    @field_validator("completed_checks")
    @classmethod
    def require_every_review_check(
        cls,
        value: list[RetestReviewCategory],
    ) -> list[RetestReviewCategory]:
        if value != list(RetestReviewCategory):
            raise ValueError(
                "retest approval must record every v1 check in canonical order"
            )
        return value


class RetestRegistryReviewLog(ContractModel):
    """Restricted dispositions and approvals for one exact registry."""

    schema_version: Literal["preference_eval_retest_review_log.v1"] = (
        "preference_eval_retest_review_log.v1"
    )
    log_id: StableId
    log_version: PositiveVersion
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    registry_id: StableId
    registry_version: PositiveVersion
    registry_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: str = Field(min_length=1)
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    completed_at: datetime
    findings: list[RetestReviewFinding] = Field(default_factory=list)
    variant_approvals: list[RetestVariantReviewApproval] = Field(
        min_length=12,
        max_length=12,
    )

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_and_reconciled_approvals(self) -> Self:
        approval_ids = [
            approval.variant_id for approval in self.variant_approvals
        ]
        if len(approval_ids) != len(set(approval_ids)):
            raise ValueError("retest approval variant ids must be unique")
        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("retest review finding ids must be unique")
        finding_counts = Counter(
            finding.variant_id for finding in self.findings
        )
        unknown = set(finding_counts) - set(approval_ids)
        if unknown:
            raise ValueError(
                "retest findings reference variants without approval"
            )
        for approval in self.variant_approvals:
            if approval.findings_count != finding_counts[approval.variant_id]:
                raise ValueError(
                    "retest findings_count does not match the disposition log"
                )
        return self


class NonrevealingRetestReviewSummary(ContractModel):
    """Aggregate retest review evidence safe for a blinded participant."""

    schema_version: Literal[
        "preference_eval_nonrevealing_retest_review_summary.v1"
    ] = "preference_eval_nonrevealing_retest_review_summary.v1"
    summary_id: StableId
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    registry_id: StableId
    registry_version: PositiveVersion
    registry_sha256: Sha256Digest
    review_log_id: StableId
    review_log_version: PositiveVersion
    review_log_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: str = Field(min_length=1)
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    reviewed_variant_count: Literal[12] = 12
    findings_count: NonNegativeCount
    findings_by_category: dict[RetestReviewCategory, NonNegativeCount]
    findings_by_severity: dict[ReviewFindingSeverity, NonNegativeCount]
    findings_by_disposition: dict[
        ReviewFindingDisposition,
        NonNegativeCount,
    ]
    all_variants_approved: Literal[True] = True
    exact_variant_content_omitted: Literal[True] = True

    @model_validator(mode="after")
    def validate_complete_aggregate_counts(self) -> Self:
        groups = (
            (self.findings_by_category, set(RetestReviewCategory)),
            (self.findings_by_severity, set(ReviewFindingSeverity)),
            (self.findings_by_disposition, set(ReviewFindingDisposition)),
        )
        for actual, expected in groups:
            if set(actual) != expected:
                raise ValueError(
                    "nonrevealing retest counts must include every enum value"
                )
            if sum(actual.values()) != self.findings_count:
                raise ValueError(
                    "nonrevealing retest counts must sum to findings_count"
                )
        return self


def load_retest_review_log(path: str | Path) -> RetestRegistryReviewLog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return RetestRegistryReviewLog.model_validate(raw)


def validate_locked_retest_review_prompt() -> None:
    actual = canonical_text_sha256(PHASE3_RETEST_REVIEW_PROMPT_PATH)
    if actual != PHASE3_RETEST_REVIEW_PROMPT_SHA256:
        raise ValueError(
            "Phase 3 retest-review prompt does not match its locked v1 hash"
        )


def validate_retest_review_log(
    log: RetestRegistryReviewLog,
    registry: RetestVariantRegistry,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> None:
    validate_retest_registry_against_bank(registry, fixture, profile)
    if (
        log.profile_id,
        log.profile_version,
        log.profile_sha256,
        log.fixture_id,
        log.fixture_version,
        log.fixture_sha256,
        log.registry_id,
        log.registry_version,
        log.registry_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
        registry.registry_id,
        registry.registry_version,
        content_sha256(registry),
    ):
        raise ValueError(
            "retest review log does not match the exact evaluation bundle"
        )
    exposure = profile.case_study_exposure_policy
    if review_system_matches(
        log.reviewer_system,
        exposure.packet_author_system,
    ):
        raise ValueError(
            "participant-independent reviewer must differ from packet author"
        )
    if log.reviewer_type is ReviewActorType.AI:
        if not review_system_matches(
            log.reviewer_system,
            exposure.content_reviewer_system,
        ):
            raise ValueError(
                "AI reviewer system does not match the frozen exposure policy"
            )
        validate_locked_retest_review_prompt()
        if log.review_prompt_sha256 != PHASE3_RETEST_REVIEW_PROMPT_SHA256:
            raise ValueError(
                "AI retest review does not use the locked Phase 3 prompt"
            )

    variant_by_id = {
        variant.variant_id: variant for variant in registry.variants
    }
    approval_by_id = {
        approval.variant_id: approval
        for approval in log.variant_approvals
    }
    if list(approval_by_id) != list(variant_by_id):
        raise ValueError(
            "retest review must approve every variant exactly once in "
            "registry order"
        )
    for variant_id, approval in approval_by_id.items():
        variant = variant_by_id[variant_id]
        if (
            approval.source_measure_id,
            approval.source_measure_version,
            approval.packet_sha256,
        ) != (
            variant.source_measure_id,
            variant.source_measure_version,
            content_sha256(variant.packet),
        ):
            raise ValueError(
                "retest approval does not match the exact variant packet"
            )


def build_retest_review_ledger_entries(
    log: RetestRegistryReviewLog,
    registry: RetestVariantRegistry,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> list[RetestReviewLedgerEntry]:
    validate_retest_review_log(log, registry, fixture, profile)
    approval_by_id = {
        approval.variant_id: approval
        for approval in log.variant_approvals
    }
    entries = []
    for variant in registry.variants:
        approval = approval_by_id[variant.variant_id]
        entries.append(
            RetestReviewLedgerEntry(
                variant_id=variant.variant_id,
                source_measure_id=variant.source_measure_id,
                source_measure_version=variant.source_measure_version,
                packet_sha256=content_sha256(variant.packet),
                paraphrase_without_material_change_reviewed=True,
                facts_and_fiscal_estimates_preserved=True,
                option_set_preserved=True,
                prior_response_and_prediction_hidden_by_protocol=True,
                approval=PacketReviewRecord(
                    reviewer_type=log.reviewer_type,
                    reviewer_system=log.reviewer_system,
                    reviewer_model_version=log.reviewer_model_version,
                    review_prompt_sha256=log.review_prompt_sha256,
                    findings_count=approval.findings_count,
                    disposition_log_sha256=content_sha256(log),
                    approved=True,
                    completed_at=log.completed_at,
                ),
            )
        )
    return entries


def build_nonrevealing_retest_review_summary(
    log: RetestRegistryReviewLog,
    registry: RetestVariantRegistry,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> NonrevealingRetestReviewSummary:
    validate_retest_review_log(log, registry, fixture, profile)
    category_counts = Counter(finding.category for finding in log.findings)
    severity_counts = Counter(finding.severity for finding in log.findings)
    disposition_counts = Counter(
        finding.disposition for finding in log.findings
    )
    return NonrevealingRetestReviewSummary(
        summary_id=f"{log.log_id}_summary",
        profile_id=log.profile_id,
        profile_version=log.profile_version,
        profile_sha256=log.profile_sha256,
        fixture_id=log.fixture_id,
        fixture_version=log.fixture_version,
        fixture_sha256=log.fixture_sha256,
        registry_id=log.registry_id,
        registry_version=log.registry_version,
        registry_sha256=log.registry_sha256,
        review_log_id=log.log_id,
        review_log_version=log.log_version,
        review_log_sha256=content_sha256(log),
        reviewer_type=log.reviewer_type,
        reviewer_system=log.reviewer_system,
        reviewer_model_version=log.reviewer_model_version,
        review_prompt_sha256=log.review_prompt_sha256,
        reviewed_variant_count=len(log.variant_approvals),
        findings_count=len(log.findings),
        findings_by_category={
            category: category_counts[category]
            for category in RetestReviewCategory
        },
        findings_by_severity={
            severity: severity_counts[severity]
            for severity in ReviewFindingSeverity
        },
        findings_by_disposition={
            disposition: disposition_counts[disposition]
            for disposition in ReviewFindingDisposition
        },
    )
