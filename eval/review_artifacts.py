"""Auditable Phase 3B content-review logs and participant-safe summaries."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .bank_authoring import (
    DomainBankBatch,
    SourceCaptureRole,
    validate_domain_bank_batch,
)
from .bank_profile import (
    BankReviewLedgerEntry,
    EvaluationBankProfile,
    PacketReviewRecord,
    ReviewActorType,
)
from .contracts import (
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256

PHASE3_PACKET_REVIEW_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "phase3_packet_review_v1.md"
)
PHASE3_PACKET_REVIEW_PROMPT_SHA256 = (
    "b2e0cc374e0de755fb45ed8e6997cbde"
    "eefc32f75827fcedf5e6abac435f7f32"
)
NonNegativeCount = Annotated[int, Field(ge=0)]


class PacketReviewCategory(str, Enum):
    SLOT_FIDELITY = "slot_fidelity"
    FACTUAL_TRACEABILITY = "factual_traceability"
    SOURCE_INTEGRITY = "source_integrity"
    CONTEXTUAL_SUFFICIENCY = "contextual_sufficiency"
    OPTION_DISTINCTNESS = "option_distinctness"
    WORD_COUNT_BALANCE = "word_count_balance"
    SPECIFICITY_BALANCE = "specificity_balance"
    VALENCE_BALANCE = "valence_balance"
    COST_AND_BENEFIT_SYMMETRY = "cost_and_benefit_symmetry"
    UNCERTAINTY_SYMMETRY = "uncertainty_symmetry"
    POLITICAL_CUE_EXCLUSION = "political_cue_exclusion"
    FORMAT_FIDELITY = "format_fidelity"


class ReviewFindingSeverity(str, Enum):
    NOTE = "note"
    MINOR = "minor"
    MAJOR = "major"
    BLOCKING = "blocking"


class ReviewFindingDisposition(str, Enum):
    RESOLVED = "resolved"
    DEFENDED = "defended"
    ACCEPTED_LIMITATION = "accepted_limitation"


class PacketReviewFinding(ContractModel):
    """One exact-content finding in the restricted disposition log."""

    record_version: Literal["packet_review_finding.v1"] = (
        "packet_review_finding.v1"
    )
    finding_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    category: PacketReviewCategory
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
                "blocking review findings must be resolved before approval"
            )
        return self


class MeasureReviewApproval(ContractModel):
    """Approval of one exact measure hash within a reviewed domain batch."""

    record_version: Literal["measure_review_approval.v1"] = (
        "measure_review_approval.v1"
    )
    measure_id: StableId
    measure_version: PositiveVersion
    measure_sha256: Sha256Digest
    findings_count: NonNegativeCount
    completed_checks: list[PacketReviewCategory]
    approved: Literal[True] = True

    @field_validator("completed_checks")
    @classmethod
    def require_every_review_check(
        cls,
        value: list[PacketReviewCategory],
    ) -> list[PacketReviewCategory]:
        if value != list(PacketReviewCategory):
            raise ValueError(
                "measure approval must record every v1 packet-review check "
                "in canonical order"
            )
        return value


class DomainBatchReviewLog(ContractModel):
    """Restricted exact-content disposition log for one final batch version."""

    schema_version: Literal["preference_eval_batch_review_log.v1"] = (
        "preference_eval_batch_review_log.v1"
    )
    log_id: StableId
    log_version: PositiveVersion
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    batch_id: StableId
    batch_version: PositiveVersion
    batch_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: str = Field(min_length=1)
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    completed_at: datetime
    findings: list[PacketReviewFinding] = Field(default_factory=list)
    measure_approvals: list[MeasureReviewApproval] = Field(
        min_length=6,
        max_length=6,
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
    def validate_final_review_log(self) -> Self:
        if self.reviewer_type is ReviewActorType.AI and (
            self.reviewer_model_version is None
            or self.review_prompt_sha256 is None
        ):
            raise ValueError(
                "AI review requires reviewer_model_version and "
                "review_prompt_sha256"
            )

        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("packet-review finding ids must be unique")

        approval_refs = [
            (approval.measure_id, approval.measure_version)
            for approval in self.measure_approvals
        ]
        if len(approval_refs) != len(set(approval_refs)):
            raise ValueError(
                "measure-review approval references must be unique"
            )

        approval_by_ref = {
            (approval.measure_id, approval.measure_version): approval
            for approval in self.measure_approvals
        }
        finding_counts = Counter(
            (finding.measure_id, finding.measure_version)
            for finding in self.findings
        )
        unknown_findings = set(finding_counts) - set(approval_by_ref)
        if unknown_findings:
            raise ValueError(
                "review findings reference measures without an approval"
            )
        for measure_ref, approval in approval_by_ref.items():
            if approval.findings_count != finding_counts[measure_ref]:
                raise ValueError(
                    "measure-review findings_count does not match the "
                    "restricted disposition log"
                )
        return self


def load_domain_batch_review_log(
    path: str | Path,
) -> DomainBatchReviewLog:
    """Load one restricted exact-content batch-review log."""

    log_path = Path(path)
    raw = json.loads(log_path.read_text(encoding="utf-8"))
    return DomainBatchReviewLog.model_validate(raw)


def canonical_text_sha256(path: str | Path) -> str:
    """Hash UTF-8 text after Unicode and newline normalization."""

    text = Path(path).read_text(encoding="utf-8-sig")
    normalized = unicodedata.normalize(
        "NFC",
        text.replace("\r\n", "\n").replace("\r", "\n"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_locked_review_prompt() -> None:
    """Fail closed if the v1 review prompt changes without a version bump."""

    actual = canonical_text_sha256(PHASE3_PACKET_REVIEW_PROMPT_PATH)
    if actual != PHASE3_PACKET_REVIEW_PROMPT_SHA256:
        raise ValueError(
            "Phase 3 packet-review prompt does not match its locked v1 hash"
        )


def validate_domain_batch_review_log(
    log: DomainBatchReviewLog,
    batch: DomainBankBatch,
    profile: EvaluationBankProfile,
) -> None:
    """Validate exact batch bindings, reviewer independence, and provenance."""

    validate_domain_bank_batch(batch, profile)
    if (
        log.profile_id,
        log.profile_version,
        log.profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError("review log does not match the bank profile")
    if (
        log.batch_id,
        log.batch_version,
        log.batch_sha256,
    ) != (
        batch.batch_id,
        batch.batch_version,
        content_sha256(batch),
    ):
        raise ValueError("review log does not match the exact domain batch")

    measure_by_ref = {
        (item.measure.measure_id, item.measure.version): item.measure
        for item in batch.items
    }
    approval_by_ref = {
        (approval.measure_id, approval.measure_version): approval
        for approval in log.measure_approvals
    }
    if list(approval_by_ref) != list(measure_by_ref):
        raise ValueError(
            "review log must approve every batch measure exactly once in "
            "batch order"
        )
    for measure_ref, approval in approval_by_ref.items():
        if approval.measure_sha256 != content_sha256(
            measure_by_ref[measure_ref]
        ):
            raise ValueError(
                "measure-review approval does not match the exact measure"
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
        validate_locked_review_prompt()
        if (
            log.review_prompt_sha256
            != PHASE3_PACKET_REVIEW_PROMPT_SHA256
        ):
            raise ValueError(
                "AI review log does not use the locked Phase 3 prompt"
            )


def review_system_matches(left: str, right: str) -> bool:
    return left.casefold() == right.casefold()


def _packet_review_record_for_measure(
    log: DomainBatchReviewLog,
    *,
    measure_id: str,
    measure_version: int,
) -> PacketReviewRecord:
    """Create the final-ledger approval record for one reviewed measure."""

    approval = next(
        (
            candidate
            for candidate in log.measure_approvals
            if (
                candidate.measure_id,
                candidate.measure_version,
            )
            == (measure_id, measure_version)
        ),
        None,
    )
    if approval is None:
        raise ValueError("review log has no approval for the requested measure")
    return PacketReviewRecord(
        reviewer_type=log.reviewer_type,
        reviewer_system=log.reviewer_system,
        reviewer_model_version=log.reviewer_model_version,
        review_prompt_sha256=log.review_prompt_sha256,
        findings_count=approval.findings_count,
        disposition_log_sha256=content_sha256(log),
        approved=True,
        completed_at=log.completed_at,
    )


def packet_review_record_for_measure(
    log: DomainBatchReviewLog,
    batch: DomainBankBatch,
    profile: EvaluationBankProfile,
    *,
    measure_id: str,
    measure_version: int,
) -> PacketReviewRecord:
    """Validate a reviewed batch and return one final-ledger approval."""

    validate_domain_batch_review_log(log, batch, profile)
    return _packet_review_record_for_measure(
        log,
        measure_id=measure_id,
        measure_version=measure_version,
    )


def bank_review_ledger_entries_for_batch(
    log: DomainBatchReviewLog,
    batch: DomainBankBatch,
    profile: EvaluationBankProfile,
) -> list[BankReviewLedgerEntry]:
    """Build exact final-ledger entries from one validated reviewed batch."""

    validate_domain_batch_review_log(log, batch, profile)
    item_by_slot = {item.slot_id: item for item in batch.items}
    entries = []
    for slot in profile.slots:
        if slot.domain is not batch.domain:
            continue
        item = item_by_slot[slot.slot_id]
        primary_source_ids = [
            capture.source_id
            for capture in item.source_evidence.source_captures
            if (
                capture.source_role
                is SourceCaptureRole.PRIMARY_OFFICIAL
            )
        ]
        entries.append(
            BankReviewLedgerEntry(
                slot_id=slot.slot_id,
                measure_id=item.measure.measure_id,
                measure_version=item.measure.version,
                measure_sha256=content_sha256(item.measure),
                primary_official_source_ids=primary_source_ids,
                factual_traceability_reviewed=True,
                contextual_sufficiency_reviewed=True,
                adversarial_neutrality_reviewed=True,
                approval=_packet_review_record_for_measure(
                    log,
                    measure_id=item.measure.measure_id,
                    measure_version=item.measure.version,
                ),
            )
        )
    return entries


class NonrevealingReviewSummary(ContractModel):
    """Aggregate review evidence safe for the packet-blind participant."""

    schema_version: Literal[
        "preference_eval_nonrevealing_review_summary.v1"
    ] = "preference_eval_nonrevealing_review_summary.v1"
    summary_id: StableId
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    batch_id: StableId
    batch_version: PositiveVersion
    batch_sha256: Sha256Digest
    review_log_id: StableId
    review_log_version: PositiveVersion
    review_log_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: str = Field(min_length=1)
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    reviewed_measure_count: int = Field(ge=1)
    findings_count: int = Field(ge=0)
    findings_by_category: dict[
        PacketReviewCategory,
        NonNegativeCount,
    ]
    findings_by_severity: dict[
        ReviewFindingSeverity,
        NonNegativeCount,
    ]
    findings_by_disposition: dict[
        ReviewFindingDisposition,
        NonNegativeCount,
    ]
    all_packets_approved: Literal[True] = True
    exact_packet_content_omitted: Literal[True] = True

    @model_validator(mode="after")
    def validate_complete_aggregate_counts(self) -> Self:
        count_groups = (
            (self.findings_by_category, set(PacketReviewCategory)),
            (self.findings_by_severity, set(ReviewFindingSeverity)),
            (
                self.findings_by_disposition,
                set(ReviewFindingDisposition),
            ),
        )
        for actual, expected in count_groups:
            if set(actual) != expected:
                raise ValueError(
                    "nonrevealing review counts must include every enum value"
                )
            if sum(actual.values()) != self.findings_count:
                raise ValueError(
                    "nonrevealing review counts must sum to findings_count"
                )
        return self


def build_nonrevealing_review_summary(
    log: DomainBatchReviewLog,
    batch: DomainBankBatch,
    profile: EvaluationBankProfile,
) -> NonrevealingReviewSummary:
    """Aggregate a restricted log without copying any free-text finding."""

    validate_domain_batch_review_log(log, batch, profile)
    category_counts = Counter(
        finding.category for finding in log.findings
    )
    severity_counts = Counter(
        finding.severity for finding in log.findings
    )
    disposition_counts = Counter(
        finding.disposition for finding in log.findings
    )
    return NonrevealingReviewSummary(
        summary_id=f"{log.log_id}_summary",
        profile_id=log.profile_id,
        profile_version=log.profile_version,
        profile_sha256=log.profile_sha256,
        batch_id=log.batch_id,
        batch_version=log.batch_version,
        batch_sha256=log.batch_sha256,
        review_log_id=log.log_id,
        review_log_version=log.log_version,
        review_log_sha256=content_sha256(log),
        reviewer_type=log.reviewer_type,
        reviewer_system=log.reviewer_system,
        reviewer_model_version=log.reviewer_model_version,
        review_prompt_sha256=log.review_prompt_sha256,
        reviewed_measure_count=len(log.measure_approvals),
        findings_count=len(log.findings),
        findings_by_category={
            category: category_counts[category]
            for category in PacketReviewCategory
        },
        findings_by_severity={
            severity: severity_counts[severity]
            for severity in ReviewFindingSeverity
        },
        findings_by_disposition={
            disposition: disposition_counts[disposition]
            for disposition in ReviewFindingDisposition
        },
        all_packets_approved=True,
        exact_packet_content_omitted=True,
    )
