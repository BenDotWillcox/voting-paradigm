"""Frozen authoring profile for the final human-measure evaluation bank.

Phase 1 defined the persisted fixture contracts, and Phase 2 defined replay
and scoring.  This module defines the narrower Phase 3 acceptance boundary:
the common jurisdiction, the exact 48-slot authoring matrix, packet sourcing
and neutrality rules, presentation ordering, and the retest target.

The profile is intentionally separate from ``EvaluationFixture``.  Adding
authoring-only fields to the v1 fixture models would change the canonical hash
of the already-frozen development fixture.  The final bank will be validated
against both contracts and bound to this profile by hash.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self, TypeVar

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import (
    BallotType,
    ContractModel,
    EvaluationFixture,
    GeneralizationTier,
    JurisdictionVersion,
    MeasureDomain,
    MeasureSourceKind,
    MeasureVersion,
    PositiveVersion,
    ResponseField,
    RetestPacketVariant,
    Sha256Digest,
    SourceRecord,
    StableId,
)
from .fixture_io import content_sha256

CountKey = TypeVar("CountKey")


def _require_count(
    label: str,
    actual: Counter[CountKey],
    expected: dict[CountKey, int],
) -> None:
    if actual != Counter(expected):
        raise ValueError(
            f"bank {label} counts do not match the frozen target; "
            f"expected={dict(expected)}, actual={dict(actual)}"
        )


class ParticipantPacketExcludedCue(str, Enum):
    PARTY_LABELS = "party_labels"
    POLITICIAN_NAMES = "politician_names"
    SPONSORS_AND_CAMPAIGNS = "sponsors_and_campaigns"
    ENDORSEMENTS = "endorsements"
    POLLING = "polling"
    CAMPAIGN_SLOGANS = "campaign_slogans"


class ModelExcludedInput(str, Enum):
    POLITICAL_IDENTITY = "political_identity"
    PARTISAN_VOTING_HISTORY = "partisan_voting_history"
    DEMOGRAPHIC_PROXIES = "demographic_proxies"


class ReviewActorType(str, Enum):
    HUMAN = "human"
    AI = "ai"


class NeutralityCheck(str, Enum):
    OPTION_DISTINCTNESS = "option_distinctness"
    WORD_COUNT_BALANCE = "word_count_balance"
    SPECIFICITY_BALANCE = "specificity_balance"
    VALENCE_BALANCE = "valence_balance"
    COST_AND_BENEFIT_SYMMETRY = "cost_and_benefit_symmetry"
    UNCERTAINTY_SYMMETRY = "uncertainty_symmetry"
    MATERIAL_CONTEXT_SUFFICIENCY = "material_context_sufficiency"


class RetestVariantRule(str, Enum):
    PARAPHRASE_WITHOUT_MATERIAL_CHANGE = "paraphrase_without_material_change"
    REORDER_OPTIONS = "reorder_options"
    PRESERVE_FACTS_AND_FISCAL_ESTIMATES = "preserve_facts_and_fiscal_estimates"
    PRESERVE_OPTION_SET = "preserve_option_set"
    HIDE_PRIOR_RESPONSE_AND_PREDICTION = "hide_prior_response_and_prediction"


class SourceTierTarget(ContractModel):
    real_world_familiar: Literal[11] = 11
    real_world_adjacent: Literal[11] = 11
    real_world_novel: Literal[10] = 10
    constructed_familiar: Literal[5] = 5
    constructed_adjacent: Literal[5] = 5
    constructed_novel: Literal[6] = 6


class BankCompositionTarget(ContractModel):
    total_measures: Literal[48] = 48
    measures_per_domain: Literal[6] = 6
    real_world_anchored: Literal[32] = 32
    constructed: Literal[16] = 16
    familiar: Literal[16] = 16
    adjacent: Literal[16] = 16
    novel: Literal[16] = 16
    single_choice: Literal[38] = 38
    ranked: Literal[3] = 3
    approval: Literal[3] = 3
    score: Literal[3] = 3
    quadratic: Literal[1] = 1
    source_tier: SourceTierTarget


class BankSlot(ContractModel):
    """One required authoring position, before final measure text is frozen."""

    record_version: Literal["preference_eval_bank_slot.v1"] = (
        "preference_eval_bank_slot.v1"
    )
    slot_id: StableId
    domain: MeasureDomain
    source_kind: MeasureSourceKind
    intended_generalization_tier: GeneralizationTier
    ballot_type: BallotType
    authoring_brief: str = Field(min_length=20)
    concept_ids: list[StableId] = Field(min_length=2)

    @field_validator("concept_ids")
    @classmethod
    def concept_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("slot concept_ids must be unique")
        return value


class BankSourcePolicy(ContractModel):
    """Source requirements that are partly automated and partly reviewed."""

    real_world_min_url_sources: Literal[2] = 2
    real_world_min_primary_official_sources: Literal[1] = 1
    constructed_min_context_url_sources: Literal[1] = 1
    require_publisher: Literal[True] = True
    require_accessed_date: Literal[True] = True
    require_adaptation_notes: Literal[True] = True
    primary_source_role_recorded_in_review_ledger: Literal[True] = True
    preserve_source_and_adapted_text: Literal[True] = True


class PacketAndModelPolicy(ContractModel):
    same_frozen_packet_for_participant_and_model: Literal[True] = True
    measures_are_independent_from_common_baseline: Literal[True] = True
    political_identity_collected_only_after_retest: Literal[True] = True
    unstated_material_context_remains_explicitly_unknown: Literal[True] = True
    models_must_not_invent_participant_circumstances: Literal[True] = True
    excluded_participant_packet_cues: list[ParticipantPacketExcludedCue]
    excluded_model_inputs: list[ModelExcludedInput]

    @model_validator(mode="after")
    def require_all_exclusions(self) -> Self:
        if set(self.excluded_participant_packet_cues) != set(
            ParticipantPacketExcludedCue
        ):
            raise ValueError(
                "excluded_participant_packet_cues must contain the complete "
                "v1 exclusion set"
            )
        if len(self.excluded_participant_packet_cues) != len(
            ParticipantPacketExcludedCue
        ):
            raise ValueError(
                "excluded_participant_packet_cues cannot contain duplicates"
            )
        if set(self.excluded_model_inputs) != set(ModelExcludedInput):
            raise ValueError(
                "excluded_model_inputs must contain the complete v1 "
                "exclusion set"
            )
        if len(self.excluded_model_inputs) != len(ModelExcludedInput):
            raise ValueError("excluded_model_inputs cannot contain duplicates")
        return self


class NeutralityReviewPolicy(ContractModel):
    required_checks: list[NeutralityCheck]
    factual_traceability_review_required: Literal[True] = True
    contextual_sufficiency_review_required: Literal[True] = True
    adversarial_neutrality_review_required: Literal[True] = True
    participant_independent_approval_required: Literal[True] = True
    reviewer_type_and_version_required: Literal[True] = True
    review_prompt_hash_required_when_ai: Literal[True] = True
    disposition_log_required: Literal[True] = True

    @model_validator(mode="after")
    def require_all_checks(self) -> Self:
        if set(self.required_checks) != set(NeutralityCheck):
            raise ValueError(
                "required_checks must contain the complete v1 neutrality set"
            )
        if len(self.required_checks) != len(NeutralityCheck):
            raise ValueError("required_checks cannot contain duplicates")
        return self


class CaseStudyExposurePolicy(ContractModel):
    """Packet-blind exposure and reviewer rules for Ben's case study."""

    exposure_mode: Literal["cold_to_exact_packet_content"] = (
        "cold_to_exact_packet_content"
    )
    packet_author_system: Literal["codex"] = "codex"
    content_reviewer_system: Literal["claude"] = "claude"
    topic_level_authoring_briefs_disclosed: Literal[True] = True
    topic_brief_disclosure_date: date
    exact_packet_text_options_and_values_withheld: Literal[True] = True
    participant_receives_nonrevealing_review_summary_only: Literal[True] = True
    describe_as_ai_assisted_not_human_review: Literal[True] = True
    topic_exposure_caveat_required_for_novel_analysis: Literal[True] = True
    human_content_review_required_before_external_pilot: Literal[True] = True


class PresentationOrderPolicy(ContractModel):
    measure_ordering: Literal["seeded_stratified_six_waves"] = (
        "seeded_stratified_six_waves"
    )
    wave_count: Literal[6] = 6
    measures_per_wave: Literal[8] = 8
    option_ordering: Literal["seeded_per_presentation"] = (
        "seeded_per_presentation"
    )
    order_seed: Literal[20260729] = 20260729


class RetestTarget(ContractModel):
    target_count: Literal[12] = 12
    interval_min_days: Literal[7] = 7
    interval_max_days: Literal[14] = 14
    minimum_per_domain: Literal[1] = 1
    real_world_anchored: Literal[8] = 8
    constructed: Literal[4] = 4
    familiar: Literal[4] = 4
    adjacent: Literal[4] = 4
    novel: Literal[4] = 4
    single_choice: Literal[8] = 8
    ranked: Literal[1] = 1
    approval: Literal[1] = 1
    score: Literal[1] = 1
    quadratic: Literal[1] = 1
    variant_rules: list[RetestVariantRule]

    @model_validator(mode="after")
    def validate_retest_target(self) -> Self:
        if self.real_world_anchored + self.constructed != self.target_count:
            raise ValueError("retest source counts must sum to target_count")
        if self.familiar + self.adjacent + self.novel != self.target_count:
            raise ValueError("retest tier counts must sum to target_count")
        if (
            self.single_choice
            + self.ranked
            + self.approval
            + self.score
            + self.quadratic
            != self.target_count
        ):
            raise ValueError("retest ballot counts must sum to target_count")
        if set(self.variant_rules) != set(RetestVariantRule):
            raise ValueError(
                "variant_rules must contain the complete v1 retest rule set"
            )
        if len(self.variant_rules) != len(RetestVariantRule):
            raise ValueError("variant_rules cannot contain duplicates")
        return self


class EvaluationBankProfile(ContractModel):
    schema_version: Literal["preference_eval_bank_profile.v1"]
    profile_id: StableId
    profile_version: Literal[1]
    created_at: datetime
    jurisdiction: JurisdictionVersion
    jurisdiction_calibration_sources: list[SourceRecord] = Field(min_length=1)
    composition: BankCompositionTarget
    source_policy: BankSourcePolicy
    packet_and_model_policy: PacketAndModelPolicy
    neutrality_review_policy: NeutralityReviewPolicy
    case_study_exposure_policy: CaseStudyExposurePolicy
    presentation_order_policy: PresentationOrderPolicy
    retest_target: RetestTarget
    slots: list[BankSlot] = Field(min_length=48, max_length=48)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        source_ids = [
            source.source_id for source in self.jurisdiction_calibration_sources
        ]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(
                "jurisdiction calibration source ids must be unique"
            )
        for source in self.jurisdiction_calibration_sources:
            if (
                source.publisher is None
                or source.url is None
                or source.accessed_date is None
                or source.adaptation_notes is None
            ):
                raise ValueError(
                    "jurisdiction calibration sources require publisher, "
                    "URL, accessed_date, and adaptation_notes"
                )

        slot_ids = [slot.slot_id for slot in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("bank slot ids must be unique")

        _require_count(
            "source kind",
            Counter(slot.source_kind for slot in self.slots),
            {
                MeasureSourceKind.REAL_WORLD_ANCHORED: (
                    self.composition.real_world_anchored
                ),
                MeasureSourceKind.CONSTRUCTED: self.composition.constructed,
            },
        )
        _require_count(
            "generalization tier",
            Counter(
                slot.intended_generalization_tier for slot in self.slots
            ),
            {
                GeneralizationTier.FAMILIAR: self.composition.familiar,
                GeneralizationTier.ADJACENT: self.composition.adjacent,
                GeneralizationTier.NOVEL: self.composition.novel,
            },
        )
        _require_count(
            "ballot type",
            Counter(slot.ballot_type for slot in self.slots),
            {
                BallotType.SINGLE_CHOICE: self.composition.single_choice,
                BallotType.RANKED: self.composition.ranked,
                BallotType.APPROVAL: self.composition.approval,
                BallotType.SCORE: self.composition.score,
                BallotType.QUADRATIC: self.composition.quadratic,
            },
        )

        domain_counts = Counter(slot.domain for slot in self.slots)
        _require_count(
            "domain",
            domain_counts,
            {
                domain: self.composition.measures_per_domain
                for domain in MeasureDomain
            },
        )
        for domain in MeasureDomain:
            domain_slots = [
                slot for slot in self.slots if slot.domain is domain
            ]
            _require_count(
                f"{domain.value} source kind",
                Counter(slot.source_kind for slot in domain_slots),
                {
                    MeasureSourceKind.REAL_WORLD_ANCHORED: 4,
                    MeasureSourceKind.CONSTRUCTED: 2,
                },
            )
            _require_count(
                f"{domain.value} generalization tier",
                Counter(
                    slot.intended_generalization_tier
                    for slot in domain_slots
                ),
                {
                    GeneralizationTier.FAMILIAR: 2,
                    GeneralizationTier.ADJACENT: 2,
                    GeneralizationTier.NOVEL: 2,
                },
            )

        source_tier_counts = Counter(
            (slot.source_kind, slot.intended_generalization_tier)
            for slot in self.slots
        )
        source_tier = self.composition.source_tier
        _require_count(
            "source/tier",
            source_tier_counts,
            {
                (
                    MeasureSourceKind.REAL_WORLD_ANCHORED,
                    GeneralizationTier.FAMILIAR,
                ): source_tier.real_world_familiar,
                (
                    MeasureSourceKind.REAL_WORLD_ANCHORED,
                    GeneralizationTier.ADJACENT,
                ): source_tier.real_world_adjacent,
                (
                    MeasureSourceKind.REAL_WORLD_ANCHORED,
                    GeneralizationTier.NOVEL,
                ): source_tier.real_world_novel,
                (
                    MeasureSourceKind.CONSTRUCTED,
                    GeneralizationTier.FAMILIAR,
                ): source_tier.constructed_familiar,
                (
                    MeasureSourceKind.CONSTRUCTED,
                    GeneralizationTier.ADJACENT,
                ): source_tier.constructed_adjacent,
                (
                    MeasureSourceKind.CONSTRUCTED,
                    GeneralizationTier.NOVEL,
                ): source_tier.constructed_novel,
            },
        )
        return self

class RetestVariantRegistry(ContractModel):
    """The twelve linked packet variants used for the final retest."""

    schema_version: Literal["preference_eval_retest_registry.v1"] = (
        "preference_eval_retest_registry.v1"
    )
    registry_id: StableId
    registry_version: PositiveVersion
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    created_at: datetime
    variants: list[RetestPacketVariant] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_variants(self) -> Self:
        variant_ids = [variant.variant_id for variant in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("retest variant ids must be unique")
        measure_refs = [
            (
                variant.source_measure_id,
                variant.source_measure_version,
            )
            for variant in self.variants
        ]
        if len(measure_refs) != len(set(measure_refs)):
            raise ValueError(
                "retest variants must reference distinct source measures"
            )
        packet_refs = [
            (
                variant.packet.packet_id,
                variant.packet.version,
            )
            for variant in self.variants
        ]
        if len(packet_refs) != len(set(packet_refs)):
            raise ValueError("retest packet id/version pairs must be unique")
        return self


class PacketReviewRecord(ContractModel):
    """Auditable participant-independent approval of exact frozen content."""

    record_version: Literal["packet_review.v1"] = "packet_review.v1"
    reviewer_type: ReviewActorType
    reviewer_system: str = Field(min_length=1)
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    findings_count: int = Field(ge=0)
    disposition_log_sha256: Sha256Digest
    approved: Literal[True] = True
    completed_at: datetime

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
    def require_ai_provenance(self) -> Self:
        if self.reviewer_type is ReviewActorType.AI and (
            self.reviewer_model_version is None
            or self.review_prompt_sha256 is None
        ):
            raise ValueError(
                "AI review requires reviewer_model_version and "
                "review_prompt_sha256"
            )
        return self


class BankReviewLedgerEntry(ContractModel):
    """Bind one authored slot to one exact reviewed canonical measure."""

    record_version: Literal["bank_review_entry.v1"] = "bank_review_entry.v1"
    slot_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    measure_sha256: Sha256Digest
    primary_official_source_ids: list[StableId] = Field(default_factory=list)
    factual_traceability_reviewed: Literal[True] = True
    contextual_sufficiency_reviewed: Literal[True] = True
    adversarial_neutrality_reviewed: Literal[True] = True
    approval: PacketReviewRecord

    @field_validator("primary_official_source_ids")
    @classmethod
    def primary_source_ids_must_be_unique(
        cls,
        value: list[str],
    ) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("primary official source ids must be unique")
        return value


class RetestReviewLedgerEntry(ContractModel):
    """Bind one linked retest variant to its semantic-preservation review."""

    record_version: Literal["retest_review_entry.v1"] = (
        "retest_review_entry.v1"
    )
    variant_id: StableId
    source_measure_id: StableId
    source_measure_version: PositiveVersion
    packet_sha256: Sha256Digest
    paraphrase_without_material_change_reviewed: Literal[True] = True
    facts_and_fiscal_estimates_preserved: Literal[True] = True
    option_set_preserved: Literal[True] = True
    prior_response_and_prediction_hidden_by_protocol: Literal[True] = True
    approval: PacketReviewRecord


class BankReviewLedger(ContractModel):
    """Review provenance and one-to-one bindings for a final bank bundle."""

    schema_version: Literal["preference_eval_bank_review_ledger.v1"] = (
        "preference_eval_bank_review_ledger.v1"
    )
    ledger_id: StableId
    ledger_version: PositiveVersion
    profile_id: StableId
    profile_version: PositiveVersion
    profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    retest_registry_id: StableId
    retest_registry_version: PositiveVersion
    retest_registry_sha256: Sha256Digest
    created_at: datetime
    measure_entries: list[BankReviewLedgerEntry] = Field(min_length=1)
    retest_entries: list[RetestReviewLedgerEntry] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_bindings(self) -> Self:
        slot_ids = [entry.slot_id for entry in self.measure_entries]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("review-ledger slot ids must be unique")
        measure_refs = [
            (entry.measure_id, entry.measure_version)
            for entry in self.measure_entries
        ]
        if len(measure_refs) != len(set(measure_refs)):
            raise ValueError(
                "review-ledger canonical measure references must be unique"
            )
        variant_ids = [entry.variant_id for entry in self.retest_entries]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError(
                "review-ledger retest variant ids must be unique"
            )
        return self


class BankProfileManifest(ContractModel):
    schema_version: Literal["preference_eval_bank_profile_manifest.v1"] = (
        "preference_eval_bank_profile_manifest.v1"
    )
    profile_id: StableId
    profile_version: Literal[1]
    profile_sha256: Sha256Digest
    jurisdiction_sha256: Sha256Digest
    slot_plan_sha256: Sha256Digest
    calibration_sources_sha256: Sha256Digest


def load_bank_profile(path: str | Path) -> EvaluationBankProfile:
    """Load and validate one Phase 3 bank-authoring profile."""

    profile_path = Path(path)
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    return EvaluationBankProfile.model_validate(raw)


def load_retest_variant_registry(
    path: str | Path,
) -> RetestVariantRegistry:
    """Load and validate one linked retest-variant registry."""

    registry_path = Path(path)
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    return RetestVariantRegistry.model_validate(raw)


def load_bank_review_ledger(path: str | Path) -> BankReviewLedger:
    """Load and validate one final-bank review ledger."""

    ledger_path = Path(path)
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    return BankReviewLedger.model_validate(raw)


def build_bank_profile_manifest(
    profile: EvaluationBankProfile,
) -> BankProfileManifest:
    return BankProfileManifest(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=content_sha256(profile),
        jurisdiction_sha256=content_sha256(profile.jurisdiction),
        slot_plan_sha256=content_sha256(
            [slot.model_dump(mode="json") for slot in profile.slots]
        ),
        calibration_sources_sha256=content_sha256(
            [
                source.model_dump(mode="json")
                for source in profile.jurisdiction_calibration_sources
            ]
        ),
    )


def _slot_allocation_key(
    *,
    domain: MeasureDomain,
    source_kind: MeasureSourceKind,
    tier: GeneralizationTier,
    ballot_type: BallotType,
) -> tuple[MeasureDomain, MeasureSourceKind, GeneralizationTier, BallotType]:
    return (domain, source_kind, tier, ballot_type)


def validate_final_measure_against_profile(
    measure: MeasureVersion,
    profile: EvaluationBankProfile,
) -> None:
    """Enforce the final-bank requirements local to one exact measure."""

    rich_fields = [
        ResponseField.TOP_CHOICE,
        ResponseField.RANKING,
        ResponseField.APPROVAL,
        ResponseField.SCORES,
    ]
    if measure.ballot_type is BallotType.SINGLE_CHOICE:
        if measure.response_fields != [ResponseField.TOP_CHOICE]:
            raise ValueError(
                f"{measure.measure_id} must record only top_choice"
            )
        if len(measure.options) != 2:
            raise ValueError(
                f"{measure.measure_id} binary initiative must have "
                "exactly two options"
            )
    elif measure.ballot_type in {
        BallotType.RANKED,
        BallotType.APPROVAL,
        BallotType.SCORE,
    }:
        if measure.response_fields != rich_fields:
            raise ValueError(
                f"{measure.measure_id} ordinary multi-option contest must "
                "record top_choice, ranking, approval, and scores in the "
                "frozen order"
            )
        if len(measure.options) < 3:
            raise ValueError(
                f"{measure.measure_id} multi-option contest requires "
                "at least three options"
            )
    elif measure.ballot_type is BallotType.QUADRATIC:
        if measure.response_fields != [ResponseField.QUADRATIC]:
            raise ValueError(
                f"{measure.measure_id} quadratic contest must record only "
                "quadratic allocations"
            )
        if measure.quadratic_credit_budget != 100:
            raise ValueError(
                f"{measure.measure_id} quadratic contest must use the "
                "frozen 100-credit budget"
            )
        if measure.quadratic_allow_negative is not False:
            raise ValueError(
                f"{measure.measure_id} quadratic contest must prohibit "
                "negative allocations"
            )
    else:
        raise ValueError(
            f"{measure.measure_id} uses unsupported ballot type "
            f"{measure.ballot_type!r}"
        )

    source_policy = profile.source_policy
    required_sources = (
        source_policy.real_world_min_url_sources
        if measure.source_kind
        is MeasureSourceKind.REAL_WORLD_ANCHORED
        else source_policy.constructed_min_context_url_sources
    )
    if len(measure.packet.sources) < required_sources:
        raise ValueError(
            f"{measure.measure_id} requires at least {required_sources} "
            "source records"
        )
    for source in measure.packet.sources:
        if (
            source.publisher is None
            or source.url is None
            or source.accessed_date is None
            or source.adaptation_notes is None
        ):
            raise ValueError(
                f"{measure.measure_id} source {source.source_id} requires "
                "publisher, URL, accessed_date, and adaptation_notes"
            )


def validate_final_fixture_against_profile(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> None:
    """Enforce fixture-shape requirements represented in the bank profile.

    Primary-official source classification, factual review, contextual-
    sufficiency review, adversarial neutrality review, reviewer provenance,
    and participant-independent approval remain explicit review-ledger gates.
    They cannot be inferred safely from publisher strings or prose.
    """

    if fixture.development_only:
        raise ValueError("final bank must not be marked development_only")
    if content_sha256(fixture.jurisdiction) != content_sha256(
        profile.jurisdiction
    ):
        raise ValueError(
            "final bank jurisdiction does not match the frozen profile"
        )
    if (
        fixture.order_seed
        != profile.presentation_order_policy.order_seed
    ):
        raise ValueError(
            "final bank order_seed does not match the frozen order policy"
        )

    expected_allocations = Counter(
        _slot_allocation_key(
            domain=slot.domain,
            source_kind=slot.source_kind,
            tier=slot.intended_generalization_tier,
            ballot_type=slot.ballot_type,
        )
        for slot in profile.slots
    )
    actual_allocations = Counter(
        _slot_allocation_key(
            domain=measure.domain,
            source_kind=measure.source_kind,
            tier=measure.intended_generalization_tier,
            ballot_type=measure.ballot_type,
        )
        for measure in fixture.measures
    )
    if actual_allocations != expected_allocations:
        raise ValueError(
            "final bank allocation does not match the frozen 48-slot matrix"
        )

    for measure in fixture.measures:
        validate_final_measure_against_profile(measure, profile)


def validate_retest_registry_against_bank(
    registry: RetestVariantRegistry,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> None:
    """Validate linked retest packets and their frozen selection target."""

    if (
        registry.profile_id,
        registry.profile_version,
        registry.profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError("retest registry does not match the bank profile")
    if (
        registry.fixture_id,
        registry.fixture_version,
        registry.fixture_sha256,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
    ):
        raise ValueError("retest registry does not match the final fixture")

    target = profile.retest_target
    if len(registry.variants) != target.target_count:
        raise ValueError(
            "retest registry count does not match the frozen target"
        )

    measure_by_ref = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    selected_measures: list[MeasureVersion] = []
    for variant in registry.variants:
        measure_ref = (
            variant.source_measure_id,
            variant.source_measure_version,
        )
        measure = measure_by_ref.get(measure_ref)
        if measure is None:
            raise ValueError(
                f"retest variant {variant.variant_id} references unknown "
                f"measure {variant.source_measure_id}@"
                f"{variant.source_measure_version}"
            )
        if variant.packet.packet_id != measure.packet.packet_id:
            raise ValueError(
                f"retest variant {variant.variant_id} must retain packet_id "
                f"{measure.packet.packet_id!r}"
            )
        if variant.packet.version <= measure.packet.version:
            raise ValueError(
                f"retest variant {variant.variant_id} packet version must be "
                f"greater than canonical version {measure.packet.version}"
            )
        if set(variant.packet.arguments_by_option) != {
            option.option_id for option in measure.options
        }:
            raise ValueError(
                f"retest variant {variant.variant_id} must preserve the "
                "canonical option ids"
            )
        if {
            source.source_id for source in variant.packet.sources
        } != {
            source.source_id for source in measure.packet.sources
        }:
            raise ValueError(
                f"retest variant {variant.variant_id} must preserve the "
                "canonical source set"
            )
        selected_measures.append(measure)

    domain_counts = Counter(measure.domain for measure in selected_measures)
    missing_domains = [
        domain.value
        for domain in MeasureDomain
        if domain_counts[domain] < target.minimum_per_domain
    ]
    if missing_domains:
        raise ValueError(
            "retest registry does not meet minimum domain coverage; "
            f"missing={missing_domains}"
        )

    _require_count(
        "retest source kind",
        Counter(measure.source_kind for measure in selected_measures),
        {
            MeasureSourceKind.REAL_WORLD_ANCHORED: (
                target.real_world_anchored
            ),
            MeasureSourceKind.CONSTRUCTED: target.constructed,
        },
    )
    _require_count(
        "retest generalization tier",
        Counter(
            measure.intended_generalization_tier
            for measure in selected_measures
        ),
        {
            GeneralizationTier.FAMILIAR: target.familiar,
            GeneralizationTier.ADJACENT: target.adjacent,
            GeneralizationTier.NOVEL: target.novel,
        },
    )
    _require_count(
        "retest ballot type",
        Counter(measure.ballot_type for measure in selected_measures),
        {
            BallotType.SINGLE_CHOICE: target.single_choice,
            BallotType.RANKED: target.ranked,
            BallotType.APPROVAL: target.approval,
            BallotType.SCORE: target.score,
            BallotType.QUADRATIC: target.quadratic,
        },
    )


def _validate_review_actor(
    review: PacketReviewRecord,
    profile: EvaluationBankProfile,
) -> None:
    exposure = profile.case_study_exposure_policy
    if review.reviewer_system.casefold() == (
        exposure.packet_author_system.casefold()
    ):
        raise ValueError(
            "participant-independent reviewer must differ from packet author"
        )
    if (
        review.reviewer_type is ReviewActorType.AI
        and review.reviewer_system.casefold()
        != exposure.content_reviewer_system.casefold()
    ):
        raise ValueError(
            "reviewer system does not match the frozen exposure policy"
        )


def validate_review_ledger_against_bank(
    ledger: BankReviewLedger,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
) -> None:
    """Validate exact slot bindings and review provenance for a final bank."""

    if (
        ledger.profile_id,
        ledger.profile_version,
        ledger.profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError("review ledger does not match the bank profile")
    if (
        ledger.fixture_id,
        ledger.fixture_version,
        ledger.fixture_sha256,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
    ):
        raise ValueError("review ledger does not match the final fixture")
    if (
        ledger.retest_registry_id,
        ledger.retest_registry_version,
        ledger.retest_registry_sha256,
    ) != (
        registry.registry_id,
        registry.registry_version,
        content_sha256(registry),
    ):
        raise ValueError("review ledger does not match the retest registry")

    slot_by_id = {slot.slot_id: slot for slot in profile.slots}
    measure_by_ref = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    if {entry.slot_id for entry in ledger.measure_entries} != set(slot_by_id):
        raise ValueError(
            "review ledger must contain exactly one entry for every bank slot"
        )
    if {
        (entry.measure_id, entry.measure_version)
        for entry in ledger.measure_entries
    } != set(measure_by_ref):
        raise ValueError(
            "review ledger must bind every canonical measure exactly once"
        )

    for entry in ledger.measure_entries:
        slot = slot_by_id[entry.slot_id]
        measure = measure_by_ref[
            (entry.measure_id, entry.measure_version)
        ]
        if _slot_allocation_key(
            domain=measure.domain,
            source_kind=measure.source_kind,
            tier=measure.intended_generalization_tier,
            ballot_type=measure.ballot_type,
        ) != _slot_allocation_key(
            domain=slot.domain,
            source_kind=slot.source_kind,
            tier=slot.intended_generalization_tier,
            ballot_type=slot.ballot_type,
        ):
            raise ValueError(
                f"review entry {entry.slot_id} binds a measure with the "
                "wrong slot allocation"
            )
        if entry.measure_sha256 != content_sha256(measure):
            raise ValueError(
                f"review entry {entry.slot_id} measure hash does not match"
            )
        packet_source_ids = {
            source.source_id for source in measure.packet.sources
        }
        if not set(entry.primary_official_source_ids).issubset(
            packet_source_ids
        ):
            raise ValueError(
                f"review entry {entry.slot_id} classifies an unknown source"
            )
        if (
            measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
            and len(entry.primary_official_source_ids)
            < profile.source_policy.real_world_min_primary_official_sources
        ):
            raise ValueError(
                f"review entry {entry.slot_id} lacks the required primary "
                "official source classification"
            )
        _validate_review_actor(entry.approval, profile)

    variant_by_id = {
        variant.variant_id: variant for variant in registry.variants
    }
    if {
        entry.variant_id for entry in ledger.retest_entries
    } != set(variant_by_id):
        raise ValueError(
            "review ledger must contain exactly one entry for every retest "
            "variant"
        )
    for entry in ledger.retest_entries:
        variant = variant_by_id[entry.variant_id]
        if (
            entry.source_measure_id,
            entry.source_measure_version,
        ) != (
            variant.source_measure_id,
            variant.source_measure_version,
        ):
            raise ValueError(
                f"retest review {entry.variant_id} references the wrong "
                "canonical measure"
            )
        if entry.packet_sha256 != content_sha256(variant.packet):
            raise ValueError(
                f"retest review {entry.variant_id} packet hash does not match"
            )
        _validate_review_actor(entry.approval, profile)


def validate_final_bank_bundle(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    ledger: BankReviewLedger,
) -> None:
    """Validate the canonical bank, retest registry, and review bindings."""

    validate_final_fixture_against_profile(fixture, profile)
    validate_retest_registry_against_bank(registry, fixture, profile)
    validate_review_ledger_against_bank(
        ledger,
        fixture,
        profile,
        registry,
    )


def bank_profile_summary(profile: EvaluationBankProfile) -> JsonValue:
    """Return an inspectable, deterministic summary for CLI output."""

    source_tier_counts = Counter(
        (
            slot.source_kind.value,
            slot.intended_generalization_tier.value,
        )
        for slot in profile.slots
    )
    return {
        "case_study_exposure_mode": (
            profile.case_study_exposure_policy.exposure_mode
        ),
        "content_reviewer_system": (
            profile.case_study_exposure_policy.content_reviewer_system
        ),
        "domain_count": len({slot.domain for slot in profile.slots}),
        "measure_count": len(profile.slots),
        "source_tier_counts": {
            f"{source_kind}/{tier}": count
            for (source_kind, tier), count in sorted(
                source_tier_counts.items()
            )
        },
    }
