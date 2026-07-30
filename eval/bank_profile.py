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
from datetime import datetime
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
    ResponseField,
    Sha256Digest,
    SourceRecord,
    StableId,
)
from .fixture_io import content_sha256

CountKey = TypeVar("CountKey")


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
    """Cold-exposure and reviewer-provenance rules for Ben's case study."""

    exposure_mode: Literal["cold_first_exposure"] = "cold_first_exposure"
    packet_author_system: Literal["codex"] = "codex"
    content_reviewer_system: Literal["claude"] = "claude"
    exact_packet_content_withheld_from_participant: Literal[True] = True
    participant_receives_nonrevealing_review_summary_only: Literal[True] = True
    describe_as_ai_assisted_not_human_review: Literal[True] = True
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

        self._require_count(
            "source kind",
            Counter(slot.source_kind for slot in self.slots),
            {
                MeasureSourceKind.REAL_WORLD_ANCHORED: (
                    self.composition.real_world_anchored
                ),
                MeasureSourceKind.CONSTRUCTED: self.composition.constructed,
            },
        )
        self._require_count(
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
        self._require_count(
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
        self._require_count(
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
            self._require_count(
                f"{domain.value} source kind",
                Counter(slot.source_kind for slot in domain_slots),
                {
                    MeasureSourceKind.REAL_WORLD_ANCHORED: 4,
                    MeasureSourceKind.CONSTRUCTED: 2,
                },
            )
            self._require_count(
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
        self._require_count(
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

    @staticmethod
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


def validate_final_fixture_against_profile(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
) -> None:
    """Enforce all machine-checkable final-bank requirements.

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

    rich_fields = [
        ResponseField.TOP_CHOICE,
        ResponseField.RANKING,
        ResponseField.APPROVAL,
        ResponseField.SCORES,
    ]
    for measure in fixture.measures:
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
        else:
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

        source_policy = profile.source_policy
        url_sources = [
            source
            for source in measure.packet.sources
            if source.url is not None
        ]
        required_urls = (
            source_policy.real_world_min_url_sources
            if measure.source_kind
            is MeasureSourceKind.REAL_WORLD_ANCHORED
            else source_policy.constructed_min_context_url_sources
        )
        if len(url_sources) < required_urls:
            raise ValueError(
                f"{measure.measure_id} requires at least {required_urls} "
                "URL-backed source records"
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
        "domain_count": len(MeasureDomain),
        "measure_count": len(profile.slots),
        "source_tier_counts": {
            f"{source_kind}/{tier}": count
            for (source_kind, tier), count in sorted(
                source_tier_counts.items()
            )
        },
    }
