"""Phase 4E model qualification, robustness, privacy, and budget contracts.

Phase 4A-D define what each component is allowed to see and emit.  This module
defines how an open-weight implementation is qualified and frozen before any
held-out participant response is available.  It deliberately contains no
provider SDK calls and no restricted packet content.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from statistics import fmean
from types import MappingProxyType
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from .contracts import (
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    Probability,
    Sha256Digest,
    StableId,
    require_complete_enum_set,
)
from .fixture_io import content_sha256
from .phase4_prediction import expected_top_option_id
from .phase4_protocol import Phase4Protocol
from .phase4_semantic_review import NonrevealingSemanticMapReviewSummary

Microusd = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]
DiagnosticRepeatIndex = Annotated[int, Field(ge=1, le=3)]
NonNegativeCount = Annotated[int, Field(ge=0)]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]


class LLMRole(str, Enum):
    INTERVIEWER = "interviewer"
    EVIDENCE_EXTRACTOR = "evidence_extractor"
    ONTOLOGY_PROPOSER = "ontology_proposer"
    DIRECT_READOUT = "direct_readout"
    HYBRID_READOUT = "hybrid_readout"


class ModelCapability(str, Enum):
    TOOL_CALLING = "tool_calling"
    STRICT_STRUCTURED_OUTPUT = "strict_structured_output"


class DeploymentMode(str, Enum):
    HOSTED_API = "hosted_api"
    SELF_HOSTED = "self_hosted"


class BudgetSegment(str, Enum):
    QUALIFICATION = "qualification"
    HELD_OUT_STUDY = "held_out_study"
    RETRY_RESERVE = "retry_reserve"


class RobustnessPerturbationKind(str, Enum):
    PROMPT_PARAPHRASE = "prompt_paraphrase"
    OPTION_ORDER = "option_order"
    OPTION_LABEL = "option_label"
    STOCHASTIC_REPEAT = "stochastic_repeat"


class RobustnessExpectation(str, Enum):
    STRICT_EQUIVARIANCE = "strict_equivariance"
    SENSITIVITY_DIAGNOSTIC = "sensitivity_diagnostic"


PHASE4E_PERTURBATION_EXPECTATIONS = MappingProxyType(
    {
        RobustnessPerturbationKind.PROMPT_PARAPHRASE: (
            RobustnessExpectation.SENSITIVITY_DIAGNOSTIC
        ),
        RobustnessPerturbationKind.OPTION_ORDER: (
            RobustnessExpectation.STRICT_EQUIVARIANCE
        ),
        RobustnessPerturbationKind.OPTION_LABEL: (
            RobustnessExpectation.STRICT_EQUIVARIANCE
        ),
        RobustnessPerturbationKind.STOCHASTIC_REPEAT: (
            RobustnessExpectation.SENSITIVITY_DIAGNOSTIC
        ),
    }
)


class RobustnessMetric(str, Enum):
    INVALID_OUTPUT_RATE = "invalid_output_rate"
    TOP_CHOICE_FLIP_RATE = "top_choice_flip_rate"
    MAX_ABSOLUTE_PROBABILITY_DELTA = "max_absolute_probability_delta"
    JENSEN_SHANNON_DIVERGENCE = "jensen_shannon_divergence"
    UNSUPPORTED_ASSUMPTION_DELTA = "unsupported_assumption_delta"


class QualificationCriterion(str, Enum):
    SCHEMA_AND_TOOL_COMPLIANCE = "schema_and_tool_compliance"
    STRICT_TRANSFORM_EQUIVARIANCE = "strict_transform_equivariance"
    PROMPT_AND_STOCHASTIC_ROBUSTNESS = "prompt_and_stochastic_robustness"
    DEVELOPMENT_PREDICTION_QUALITY = "development_prediction_quality"
    PROJECTED_COST = "projected_cost"
    LATENCY = "latency"


class PrimaryOutcome(str, Enum):
    PREQUENTIAL_LOG_LOSS = "prequential_log_loss"
    HIGH_CONFIDENCE_DELEGATED_ERROR = "high_confidence_delegated_error"


class SecondaryMetric(str, Enum):
    MULTICLASS_BRIER = "multiclass_brier"
    TOP_CHOICE_ACCURACY = "top_choice_accuracy"
    CALIBRATION = "calibration"
    FIXED_VS_EXPANDING_ONTOLOGY = "fixed_vs_expanding_ontology"
    DIRECT_VS_HYBRID_READOUT = "direct_vs_hybrid_readout"
    TEST_RETEST_CONSISTENCY = "test_retest_consistency"
    GENERALIZATION_TIER_GAP = "generalization_tier_gap"
    CONFIRMED_EVIDENCE_LEARNING_CURVE = (
        "confirmed_evidence_learning_curve"
    )
    RICH_BALLOT_FIDELITY = "rich_ballot_fidelity"
    UNSUPPORTED_ASSUMPTION_RATE = "unsupported_assumption_rate"
    ROBUSTNESS_SENSITIVITY = "robustness_sensitivity"
    API_COST_AND_LATENCY = "api_cost_and_latency"


class OpenWeightModelPolicy(ContractModel):
    """Qualification requirements that do not select a model by name."""

    record_version: Literal["phase4_open_weight_model_policy.v1"] = (
        "phase4_open_weight_model_policy.v1"
    )
    open_weight_required: Literal[True] = True
    closed_weight_models_allowed: Literal[False] = False
    hosted_inference_allowed: Literal[True] = True
    local_inference_required: Literal[False] = False
    development_candidate_count: Literal[3] = 3
    same_model_required_across_llm_roles: Literal[True] = True
    exact_upstream_revision_required: Literal[True] = True
    weights_manifest_hash_required: Literal[True] = True
    license_provenance_required: Literal[True] = True
    provider_serving_revision_required: Literal[True] = True
    provider_terms_hash_required: Literal[True] = True
    model_specific_orchestration_branches_forbidden: Literal[True] = True
    model_upgrade_requires_new_candidate_artifact: Literal[True] = True
    results_report_exact_candidate_revision: Literal[True] = True
    required_roles: list[LLMRole]
    required_capabilities: list[ModelCapability]

    @model_validator(mode="after")
    def require_complete_frozen_sets(self) -> Self:
        require_complete_enum_set(
            "Phase 4E LLM roles",
            self.required_roles,
            LLMRole,
            set_name="Phase 4E v1",
        )
        require_complete_enum_set(
            "Phase 4E model capabilities",
            self.required_capabilities,
            ModelCapability,
            set_name="Phase 4E v1",
        )
        return self


class OpenWeightModelCandidate(ContractModel):
    """Auditable identity of one self-hosted or hosted open-weight candidate."""

    record_version: Literal["phase4_open_weight_model_candidate.v1"] = (
        "phase4_open_weight_model_candidate.v1"
    )
    candidate_id: StableId
    artifact_id: StableId
    artifact_version: PositiveVersion
    upstream_model_id: NonEmptyText
    upstream_model_revision: NonEmptyText
    weights_manifest_sha256: Sha256Digest
    license_id: NonEmptyText
    license_sha256: Sha256Digest
    deployment_mode: DeploymentMode
    backend_id: StableId
    backend_version: PositiveVersion
    serving_model_id: NonEmptyText
    serving_model_revision: NonEmptyText
    provider_terms_sha256: Sha256Digest
    provider_trains_on_requests: Literal[False] = False
    quantization: str | None = Field(default=None, min_length=1)
    context_window_tokens: PositiveCount
    capabilities: list[ModelCapability]

    @model_validator(mode="after")
    def require_complete_capabilities(self) -> Self:
        require_complete_enum_set(
            "open-weight candidate capabilities",
            self.capabilities,
            ModelCapability,
            set_name="Phase 4E v1",
        )
        return self


class ParticipantPrivacyPolicy(ContractModel):
    """Pseudonymous provider boundary for the personal study and later pilots."""

    record_version: Literal["phase4_participant_privacy_policy.v1"] = (
        "phase4_participant_privacy_policy.v1"
    )
    opaque_participant_id_required: Literal[True] = True
    direct_identifiers_forbidden: Literal[True] = True
    contact_and_consent_stored_separately: Literal[True] = True
    political_identity_forbidden: Literal[True] = True
    demographic_proxies_forbidden: Literal[True] = True
    local_identifier_scan_before_transmission: Literal[True] = True
    flagged_identifier_requires_redaction_or_false_positive_confirmation: (
        Literal[True]
    ) = True
    provider_training_on_requests_allowed: Literal[False] = False
    provider_retention_terms_must_be_recorded: Literal[True] = True
    public_outputs_are_aggregate_only: Literal[True] = True
    pseudonymization_not_anonymity_guarantee: Literal[True] = True


class ParticipantInteractionPolicy(ContractModel):
    """Operational sequencing that keeps the preference label unanchored."""

    record_version: Literal["phase4_participant_interaction_policy.v1"] = (
        "phase4_participant_interaction_policy.v1"
    )
    prediction_frozen_before_answer: Literal[True] = True
    sincere_answer_recorded_before_prediction_reveal: Literal[True] = True
    prediction_and_confidence_revealed_after_answer: Literal[True] = True
    override_intent_reported_separately: Literal[True] = True
    participant_paced_elicitation: Literal[True] = True
    fixed_question_limit_is_primary_endpoint: Literal[False] = False
    pause_and_resume_allowed: Literal[True] = True
    learning_curve_uses_confirmed_evidence_prefix: Literal[True] = True
    turns_and_active_time_are_secondary_effort_units: Literal[True] = True
    unresolved_confirmations_block_prediction_checkpoint: Literal[True] = True
    resource_caps_pause_instead_of_truncate: Literal[True] = True
    target_specific_questions_after_exposure_allowed: Literal[False] = False


class ProviderBudgetPolicy(ContractModel):
    """Exact microusd allocation for the personal Phase 4 study."""

    record_version: Literal["phase4_provider_budget_policy.v1"] = (
        "phase4_provider_budget_policy.v1"
    )
    currency: Literal["USD"] = "USD"
    hard_total_microusd: Literal[20_000_000] = 20_000_000
    segment_caps_microusd: dict[BudgetSegment, Microusd]
    price_card_binding_required: Literal[True] = True
    projected_max_cost_required_before_call: Literal[True] = True
    calls_over_segment_or_total_cap_rejected: Literal[True] = True
    cache_hits_have_zero_provider_cost: Literal[True] = True
    retries_use_retry_reserve: Literal[True] = True
    billed_usage_recorded_per_call: Literal[True] = True

    @model_validator(mode="after")
    def require_exact_partition(self) -> Self:
        if set(self.segment_caps_microusd) != set(BudgetSegment):
            raise ValueError("budget policy must define every v1 segment")
        if len(self.segment_caps_microusd) != len(BudgetSegment):
            raise ValueError("budget policy cannot duplicate segments")
        if sum(self.segment_caps_microusd.values()) != self.hard_total_microusd:
            raise ValueError("budget segment caps must sum to the hard total")
        expected = {
            BudgetSegment.QUALIFICATION: 4_000_000,
            BudgetSegment.HELD_OUT_STUDY: 13_000_000,
            BudgetSegment.RETRY_RESERVE: 3_000_000,
        }
        if self.segment_caps_microusd != expected:
            raise ValueError("Phase 4E v1 budget partition must be 4/13/3 USD")
        return self


class ProviderCallAuthorization(ContractModel):
    """Durable pre-call reservation against one exact budget and request."""

    record_version: Literal["phase4_provider_call_authorization.v1"] = (
        "phase4_provider_call_authorization.v1"
    )
    call_id: StableId
    segment: BudgetSegment
    model_candidate_id: StableId
    request_sha256: Sha256Digest
    retry_of_call_id: StableId | None = None
    authorized_max_cost_microusd: Microusd
    segment_remaining_before_microusd: Microusd
    total_remaining_before_microusd: Microusd
    created_at: datetime
    approved: Literal[True] = True

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError(
                "provider authorization created_at must include a timezone"
            )
        if self.retry_of_call_id is None and (
            self.segment is BudgetSegment.RETRY_RESERVE
        ):
            raise ValueError(
                "retry-reserve authorization must reference an earlier call"
            )
        if self.retry_of_call_id is not None and (
            self.segment is not BudgetSegment.RETRY_RESERVE
        ):
            raise ValueError("provider retry authorization must use the reserve")
        return self


class ProviderCallUsage(ContractModel):
    """Content-free usage and billing record for one attempted provider call."""

    record_version: Literal["phase4_provider_call_usage.v2"] = (
        "phase4_provider_call_usage.v2"
    )
    call_id: StableId
    segment: BudgetSegment
    model_candidate_id: StableId
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    billed_cost_microusd: Microusd
    authorization_overrun_microusd: Microusd = 0
    input_tokens: NonNegativeCount
    output_tokens: NonNegativeCount
    cache_hit: bool
    retry_of_call_id: StableId | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_usage_shape(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("provider usage created_at must include a timezone")
        if self.cache_hit and any(
            value != 0
            for value in (
                self.billed_cost_microusd,
                self.input_tokens,
                self.output_tokens,
            )
        ):
            raise ValueError("cache hits cannot report provider usage or cost")
        if self.retry_of_call_id is None and (
            self.segment is BudgetSegment.RETRY_RESERVE
        ):
            raise ValueError("retry-reserve usage must reference an earlier call")
        if self.retry_of_call_id is not None and (
            self.segment is not BudgetSegment.RETRY_RESERVE
        ):
            raise ValueError("provider retries must use the retry reserve")
        return self


class ProviderUsageLedger(ContractModel):
    """Append-only aggregate-safe provider usage for one exact profile."""

    schema_version: Literal["phase4_provider_usage_ledger.v2"] = (
        "phase4_provider_usage_ledger.v2"
    )
    ledger_id: StableId
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    authorizations: list[ProviderCallAuthorization] = Field(
        default_factory=list
    )
    calls: list[ProviderCallUsage] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_authorized_calls_and_valid_retry_links(self) -> Self:
        authorization_ids = [item.call_id for item in self.authorizations]
        if len(authorization_ids) != len(set(authorization_ids)):
            raise ValueError("provider authorization call ids must be unique")
        ids = [item.call_id for item in self.calls]
        if len(ids) != len(set(ids)):
            raise ValueError("provider usage call ids must be unique")
        authorizations_by_id = {
            item.call_id: item for item in self.authorizations
        }
        seen: dict[str, ProviderCallUsage] = {}
        for item in self.calls:
            authorization = authorizations_by_id.get(item.call_id)
            if authorization is None:
                raise ValueError("provider usage must bind an authorization")
            if item.authorization_sha256 != content_sha256(authorization):
                raise ValueError("provider usage authorization hash does not match")
            if (
                item.segment,
                item.model_candidate_id,
                item.request_sha256,
                item.retry_of_call_id,
            ) != (
                authorization.segment,
                authorization.model_candidate_id,
                authorization.request_sha256,
                authorization.retry_of_call_id,
            ):
                raise ValueError("provider usage does not match its authorization")
            expected_overrun = max(
                0,
                item.billed_cost_microusd
                - authorization.authorized_max_cost_microusd,
            )
            if item.authorization_overrun_microusd != expected_overrun:
                raise ValueError(
                    "provider authorization overrun does not reconcile"
                )
            if item.created_at < authorization.created_at:
                raise ValueError("provider usage cannot predate its authorization")
            if item.retry_of_call_id is not None:
                original = seen.get(item.retry_of_call_id)
                if original is None:
                    raise ValueError(
                        "provider retry must reference an earlier call"
                    )
                if (
                    item.model_candidate_id != original.model_candidate_id
                    or item.request_sha256 != original.request_sha256
                ):
                    raise ValueError(
                        "provider retry must preserve model and request"
                    )
                if item.created_at < original.created_at:
                    raise ValueError(
                        "provider retry cannot predate the original call"
                    )
            seen[item.call_id] = item
        return self


class RobustnessPolicy(ContractModel):
    """Staged, non-factorial sensitivity plan for one selected model."""

    record_version: Literal["phase4_robustness_policy.v1"] = (
        "phase4_robustness_policy.v1"
    )
    primary_estimator: Literal["single_call"] = "single_call"
    primary_call_count: Literal[1] = 1
    diagnostic_repeat_count: Literal[3] = 3
    ensemble_is_development_candidate_only: Literal[True] = True
    canonical_prompt_count: Literal[1] = 1
    prompt_paraphrase_count: Literal[2] = 2
    alternate_option_order_count: Literal[1] = 1
    alternate_option_label_count: Literal[1] = 1
    full_cross_product_required: Literal[False] = False
    perturbations_are_shadow_diagnostics: Literal[True] = True
    shadow_results_cannot_change_primary_prediction: Literal[True] = True
    repeated_calls_are_not_independent_human_observations: Literal[True] = True
    strict_transform_top_choice_flips_allowed: Literal[0] = 0
    invalid_outputs_allowed: Literal[0] = 0
    probability_thresholds_calibrated_on_public_development_only: Literal[
        True
    ] = True
    thresholds_freeze_before_held_out_responses: Literal[True] = True
    perturbation_expectations: dict[
        RobustnessPerturbationKind,
        RobustnessExpectation,
    ]
    required_metrics: list[RobustnessMetric]

    @model_validator(mode="after")
    def require_complete_robustness_surface(self) -> Self:
        if (
            self.perturbation_expectations
            != PHASE4E_PERTURBATION_EXPECTATIONS
        ):
            raise ValueError("Phase 4E perturbation expectations do not match v1")
        require_complete_enum_set(
            "Phase 4E robustness metrics",
            self.required_metrics,
            RobustnessMetric,
            set_name="Phase 4E v1",
        )
        return self


class QualificationPolicy(ContractModel):
    """How three open-weight candidates are narrowed to one before holdout."""

    record_version: Literal["phase4_qualification_policy.v1"] = (
        "phase4_qualification_policy.v1"
    )
    public_development_fixture_only: Literal[True] = True
    restricted_participant_responses_visible: Literal[False] = False
    candidate_count: Literal[3] = 3
    one_primary_model_selected: Literal[True] = True
    same_selected_model_used_for_every_llm_role: Literal[True] = True
    invalid_outputs_are_hard_failure: Literal[True] = True
    option_order_or_label_flip_is_hard_failure: Literal[True] = True
    no_closed_weight_fallback: Literal[True] = True
    selection_criteria_in_priority_order: list[QualificationCriterion]

    @model_validator(mode="after")
    def require_frozen_priority_order(self) -> Self:
        if self.selection_criteria_in_priority_order != list(
            QualificationCriterion
        ):
            raise ValueError(
                "qualification criteria must use canonical Phase 4E v1 order"
            )
        return self


class MetricPolicy(ContractModel):
    """Predeclared outcomes and claim limits for the personal case study."""

    record_version: Literal["phase4_metric_policy.v1"] = (
        "phase4_metric_policy.v1"
    )
    primary_outcomes: list[PrimaryOutcome]
    delegated_risk_thresholds: list[Probability]
    secondary_metrics: list[SecondaryMetric]
    participant_case_study_is_descriptive: Literal[True] = True
    population_superiority_claim_allowed: Literal[False] = False
    acquisition_causal_claim_requires_synthetic_or_randomized_data: Literal[
        True
    ] = True
    held_out_responses_cannot_select_model_prompt_or_threshold: Literal[True] = (
        True
    )
    settled_probability_not_comparable_across_model_families: Literal[True] = (
        True
    )

    @model_validator(mode="after")
    def require_frozen_metrics(self) -> Self:
        if self.primary_outcomes != list(PrimaryOutcome):
            raise ValueError("primary outcomes must use canonical Phase 4E order")
        if self.delegated_risk_thresholds != [0.65, 0.75, 0.85, 0.95]:
            raise ValueError("delegated-risk thresholds must match the public grid")
        require_complete_enum_set(
            "Phase 4E secondary metrics",
            self.secondary_metrics,
            SecondaryMetric,
            set_name="Phase 4E v1",
        )
        return self


class Phase4ERobustnessProfile(ContractModel):
    """Public precommitment for qualification and the final Phase 4E freeze."""

    schema_version: Literal["preference_eval_phase4_robustness.v1"] = (
        "preference_eval_phase4_robustness.v1"
    )
    profile_id: StableId
    profile_version: PositiveVersion
    created_at: datetime
    phase4_protocol_id: StableId
    phase4_protocol_version: PositiveVersion
    phase4_protocol_sha256: Sha256Digest
    semantic_review_summary_id: StableId
    semantic_review_summary_sha256: Sha256Digest
    model_policy: OpenWeightModelPolicy
    privacy_policy: ParticipantPrivacyPolicy
    interaction_policy: ParticipantInteractionPolicy
    budget_policy: ProviderBudgetPolicy
    robustness_policy: RobustnessPolicy
    qualification_policy: QualificationPolicy
    metric_policy: MetricPolicy

    @model_validator(mode="after")
    def created_at_must_be_aware(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("robustness profile created_at must include a timezone")
        return self


class RobustnessEvaluationBinding(ContractModel):
    """Exact public profile and open-weight candidate under evaluation."""

    record_version: Literal["phase4_robustness_evaluation_binding.v1"] = (
        "phase4_robustness_evaluation_binding.v1"
    )
    robustness_profile_id: StableId
    robustness_profile_version: PositiveVersion
    robustness_profile_sha256: Sha256Digest
    model_candidate_id: StableId
    model_candidate_artifact_version: PositiveVersion
    model_candidate_sha256: Sha256Digest


class OptionOrderVariant(ContractModel):
    """Restricted deterministic display-order perturbation for one option set."""

    record_version: Literal["phase4_option_order_variant.v1"] = (
        "phase4_option_order_variant.v1"
    )
    seed: Annotated[int, Field(ge=0)]
    canonical_option_ids: list[StableId] = Field(min_length=2)
    variant_option_ids: list[StableId] = Field(min_length=2)

    @model_validator(mode="after")
    def require_nonidentity_permutation(self) -> Self:
        if len(self.canonical_option_ids) != len(set(self.canonical_option_ids)):
            raise ValueError("canonical option ids must be unique")
        if set(self.variant_option_ids) != set(self.canonical_option_ids):
            raise ValueError("option-order variant must preserve the option set")
        if len(self.variant_option_ids) != len(set(self.variant_option_ids)):
            raise ValueError("option-order variant ids must be unique")
        if self.variant_option_ids == self.canonical_option_ids:
            raise ValueError("option-order variant must change display order")
        return self


class OptionLabelAlias(ContractModel):
    canonical_option_id: StableId
    provider_alias: StableId


class OptionLabelVariant(ContractModel):
    """Restricted deterministic neutral aliases mapped back before scoring."""

    record_version: Literal["phase4_option_label_variant.v1"] = (
        "phase4_option_label_variant.v1"
    )
    seed: Annotated[int, Field(ge=0)]
    aliases: list[OptionLabelAlias] = Field(min_length=2)

    @model_validator(mode="after")
    def require_bijection(self) -> Self:
        option_ids = [item.canonical_option_id for item in self.aliases]
        aliases = [item.provider_alias for item in self.aliases]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("option-label canonical ids must be unique")
        if len(aliases) != len(set(aliases)):
            raise ValueError("option-label provider aliases must be unique")
        if set(option_ids) & set(aliases):
            raise ValueError(
                "option-label aliases must be disjoint from canonical ids"
            )
        return self


class RobustnessVariantBinding(ContractModel):
    """Exact prompt, order, label, or stochastic probe used by one shadow."""

    record_version: Literal["phase4_robustness_variant_binding.v1"] = (
        "phase4_robustness_variant_binding.v1"
    )
    variant_id: StableId
    variant_version: PositiveVersion
    perturbation_kind: RobustnessPerturbationKind
    variant_sha256: Sha256Digest
    seed: Annotated[int, Field(ge=0)] | None = None
    repeat_index: DiagnosticRepeatIndex | None = None

    @model_validator(mode="after")
    def validate_probe_coordinates(self) -> Self:
        seeded_kinds = {
            RobustnessPerturbationKind.OPTION_ORDER,
            RobustnessPerturbationKind.OPTION_LABEL,
        }
        if self.perturbation_kind in seeded_kinds and self.seed is None:
            raise ValueError("seeded robustness variant must bind its seed")
        if (
            self.perturbation_kind
            is RobustnessPerturbationKind.STOCHASTIC_REPEAT
        ):
            if self.repeat_index is None or self.seed is None:
                raise ValueError(
                    "stochastic-repeat variant must bind request seed and repeat index"
                )
        elif self.repeat_index is not None:
            raise ValueError(
                "only a stochastic-repeat variant may bind a repeat index"
            )
        return self


class RobustnessPrediction(ContractModel):
    """Canonicalized provider output safe for pairwise robustness calculation."""

    record_version: Literal["phase4_robustness_prediction.v1"] = (
        "phase4_robustness_prediction.v1"
    )
    prediction_id: StableId
    evaluation_binding: RobustnessEvaluationBinding
    variant_binding: RobustnessVariantBinding | None = None
    request_sha256: Sha256Digest
    response_sha256: Sha256Digest | None = None
    canonical_option_order: list[StableId] = Field(min_length=2)
    option_probabilities: dict[StableId, Probability] | None = None
    top_option_id: StableId | None = None
    unsupported_assumption_count: NonNegativeCount = 0
    output_valid: bool
    failure_code: StableId | None = None

    @model_validator(mode="after")
    def validate_prediction(self) -> Self:
        if len(self.canonical_option_order) != len(
            set(self.canonical_option_order)
        ):
            raise ValueError("robustness canonical option order must be unique")
        if self.output_valid:
            if (
                self.response_sha256 is None
                or self.option_probabilities is None
                or self.top_option_id is None
                or self.failure_code is not None
            ):
                raise ValueError("valid robustness output is incomplete")
            if set(self.option_probabilities) != set(
                self.canonical_option_order
            ):
                raise ValueError("robustness probabilities do not match options")
            if not math.isclose(
                sum(self.option_probabilities.values()),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("robustness probabilities must sum to one")
            expected_top = expected_top_option_id(
                self.canonical_option_order,
                self.option_probabilities,
            )
            if self.top_option_id != expected_top:
                raise ValueError(
                    "robustness top option must use canonical display order "
                    "within the shared probability-tie tolerance"
                )
        else:
            if any(
                value is not None
                for value in (
                    self.response_sha256,
                    self.option_probabilities,
                    self.top_option_id,
                )
            ) or self.failure_code is None:
                raise ValueError("invalid robustness output must be content-free")
            if self.unsupported_assumption_count != 0:
                raise ValueError("invalid output cannot report parsed assumptions")
        return self


class RobustnessComparison(ContractModel):
    """One canonical-versus-shadow comparison with no participant text."""

    record_version: Literal["phase4_robustness_comparison.v1"] = (
        "phase4_robustness_comparison.v1"
    )
    comparison_id: StableId
    evaluation_binding: RobustnessEvaluationBinding
    variant_binding: RobustnessVariantBinding
    perturbation_kind: RobustnessPerturbationKind
    expectation: RobustnessExpectation
    canonical_prediction_sha256: Sha256Digest
    variant_prediction_sha256: Sha256Digest
    variant_output_valid: bool
    top_choice_flipped: bool | None = None
    max_absolute_probability_delta: NonNegativeFiniteFloat | None = None
    jensen_shannon_divergence: Probability | None = None
    unsupported_assumption_delta: int | None = None

    @model_validator(mode="after")
    def metrics_follow_output_validity(self) -> Self:
        if (
            self.perturbation_kind
            is not self.variant_binding.perturbation_kind
        ):
            raise ValueError(
                "robustness comparison kind does not match variant binding"
            )
        if (
            self.expectation
            is not PHASE4E_PERTURBATION_EXPECTATIONS[self.perturbation_kind]
        ):
            raise ValueError(
                "robustness expectation does not match perturbation kind"
            )
        metrics = (
            self.top_choice_flipped,
            self.max_absolute_probability_delta,
            self.jensen_shannon_divergence,
            self.unsupported_assumption_delta,
        )
        if self.variant_output_valid and any(value is None for value in metrics):
            raise ValueError("valid robustness comparison requires every metric")
        if not self.variant_output_valid and any(
            value is not None for value in metrics
        ):
            raise ValueError("invalid robustness comparison cannot report metrics")
        return self


class RobustnessAggregate(ContractModel):
    """Participant-safe aggregate diagnostics for one perturbation kind."""

    record_version: Literal["phase4_robustness_aggregate.v1"] = (
        "phase4_robustness_aggregate.v1"
    )
    evaluation_binding: RobustnessEvaluationBinding
    comparison_sha256s: list[Sha256Digest] = Field(min_length=1)
    perturbation_kind: RobustnessPerturbationKind
    expectation: RobustnessExpectation
    comparison_count: PositiveCount
    invalid_output_count: NonNegativeCount
    invalid_output_rate: Probability
    valid_comparison_count: NonNegativeCount
    top_choice_flip_count: NonNegativeCount
    top_choice_flip_rate: Probability | None = None
    mean_max_absolute_probability_delta: NonNegativeFiniteFloat | None = None
    maximum_absolute_probability_delta: NonNegativeFiniteFloat | None = None
    mean_jensen_shannon_divergence: Probability | None = None
    maximum_jensen_shannon_divergence: Probability | None = None
    unsupported_assumption_delta_total: int

    @model_validator(mode="after")
    def counts_and_rates_must_reconcile(self) -> Self:
        if len(self.comparison_sha256s) != self.comparison_count:
            raise ValueError("robustness aggregate comparison hashes do not count")
        if len(self.comparison_sha256s) != len(set(self.comparison_sha256s)):
            raise ValueError("robustness aggregate comparison hashes must be unique")
        if self.invalid_output_count + self.valid_comparison_count != (
            self.comparison_count
        ):
            raise ValueError("robustness aggregate counts do not reconcile")
        expected_invalid_rate = self.invalid_output_count / self.comparison_count
        if not math.isclose(
            self.invalid_output_rate,
            expected_invalid_rate,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("robustness invalid-output rate does not match")
        continuous = (
            self.top_choice_flip_rate,
            self.mean_max_absolute_probability_delta,
            self.maximum_absolute_probability_delta,
            self.mean_jensen_shannon_divergence,
            self.maximum_jensen_shannon_divergence,
        )
        if self.valid_comparison_count == 0:
            if self.top_choice_flip_count != 0 or any(
                value is not None for value in continuous
            ):
                raise ValueError("empty robustness aggregate cannot report metrics")
        else:
            if any(value is None for value in continuous):
                raise ValueError("nonempty robustness aggregate requires metrics")
            expected_flip_rate = (
                self.top_choice_flip_count / self.valid_comparison_count
            )
            if self.top_choice_flip_rate is None:
                raise ValueError("nonempty robustness aggregate requires metrics")
            if not math.isclose(
                self.top_choice_flip_rate,
                expected_flip_rate,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("robustness top-choice flip rate does not match")
        return self


def load_phase4_robustness_profile(path: Path) -> Phase4ERobustnessProfile:
    return Phase4ERobustnessProfile.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_semantic_review_summary(
    path: Path,
) -> NonrevealingSemanticMapReviewSummary:
    return NonrevealingSemanticMapReviewSummary.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def build_robustness_evaluation_binding(
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
) -> RobustnessEvaluationBinding:
    return RobustnessEvaluationBinding(
        robustness_profile_id=profile.profile_id,
        robustness_profile_version=profile.profile_version,
        robustness_profile_sha256=content_sha256(profile),
        model_candidate_id=candidate.candidate_id,
        model_candidate_artifact_version=candidate.artifact_version,
        model_candidate_sha256=content_sha256(candidate),
    )


def validate_robustness_evaluation_binding(
    binding: RobustnessEvaluationBinding,
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
) -> None:
    if binding != build_robustness_evaluation_binding(profile, candidate):
        raise ValueError(
            "robustness evaluation does not bind the exact profile and candidate"
        )


def validate_phase4_robustness_profile(
    profile: Phase4ERobustnessProfile,
    protocol: Phase4Protocol,
    semantic_summary: NonrevealingSemanticMapReviewSummary,
) -> None:
    if (
        profile.phase4_protocol_id,
        profile.phase4_protocol_version,
        profile.phase4_protocol_sha256,
    ) != (
        protocol.protocol_id,
        protocol.protocol_version,
        content_sha256(protocol),
    ):
        raise ValueError("Phase 4E profile does not bind the Phase 4 protocol")
    if (
        profile.semantic_review_summary_id,
        profile.semantic_review_summary_sha256,
    ) != (
        semantic_summary.summary_id,
        content_sha256(semantic_summary),
    ):
        raise ValueError("Phase 4E profile does not bind the semantic approval")


def provider_usage_totals(
    ledger: ProviderUsageLedger,
) -> dict[BudgetSegment, int]:
    totals = Counter[BudgetSegment]()
    for item in ledger.calls:
        totals[item.segment] += item.billed_cost_microusd
    return {segment: totals[segment] for segment in BudgetSegment}


def provider_committed_totals(
    ledger: ProviderUsageLedger,
    *,
    before: datetime | None = None,
) -> dict[BudgetSegment, int]:
    """Return billed spend plus maximum cost reserved by outstanding calls."""

    totals = Counter[BudgetSegment]()
    calls_by_id = {item.call_id: item for item in ledger.calls}
    for item in ledger.authorizations:
        if before is not None and item.created_at >= before:
            continue
        call = calls_by_id.get(item.call_id)
        if call is not None and (
            before is None or call.created_at < before
        ):
            totals[item.segment] += call.billed_cost_microusd
        else:
            totals[item.segment] += item.authorized_max_cost_microusd
    return {segment: totals[segment] for segment in BudgetSegment}


def validate_provider_usage_ledger(
    ledger: ProviderUsageLedger,
    profile: Phase4ERobustnessProfile,
) -> None:
    if (
        ledger.robustness_profile_id,
        ledger.robustness_profile_version,
        ledger.robustness_profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError("provider usage ledger does not bind the exact profile")
    usage_totals = provider_usage_totals(ledger)
    calls_by_id = {item.call_id: item for item in ledger.calls}
    committed_totals = provider_committed_totals(ledger)
    previous_authorized_at: datetime | None = None
    for authorization in ledger.authorizations:
        if (
            previous_authorized_at is not None
            and authorization.created_at <= previous_authorized_at
        ):
            raise ValueError(
                "provider authorizations must use strict issuance order"
            )
        totals_before = provider_committed_totals(
            ledger,
            before=authorization.created_at,
        )
        expected_segment_remaining = (
            profile.budget_policy.segment_caps_microusd[authorization.segment]
            - totals_before[authorization.segment]
        )
        expected_total_remaining = (
            profile.budget_policy.hard_total_microusd
            - sum(totals_before.values())
        )
        if (
            authorization.segment_remaining_before_microusd
            != expected_segment_remaining
            or authorization.total_remaining_before_microusd
            != expected_total_remaining
        ):
            raise ValueError(
                "provider authorization remaining-budget proof does not match"
            )
        if authorization.retry_of_call_id is not None:
            original = calls_by_id.get(authorization.retry_of_call_id)
            if original is None or original.created_at > authorization.created_at:
                raise ValueError(
                    "provider retry authorization must bind an earlier call"
                )
            if (
                authorization.model_candidate_id
                != original.model_candidate_id
                or authorization.request_sha256 != original.request_sha256
            ):
                raise ValueError(
                    "provider retry authorization must preserve model and request"
                )
        previous_authorized_at = authorization.created_at

    for label, totals in (
        ("usage", usage_totals),
        ("committed spend", committed_totals),
    ):
        for segment, total in totals.items():
            if total > profile.budget_policy.segment_caps_microusd[segment]:
                raise ValueError(f"provider {label} exceeds a segment cap")
        if sum(totals.values()) > profile.budget_policy.hard_total_microusd:
            raise ValueError(f"provider {label} exceeds the hard total cap")


def authorize_provider_call(
    ledger: ProviderUsageLedger,
    profile: Phase4ERobustnessProfile,
    *,
    call_id: str,
    segment: BudgetSegment,
    model_candidate_id: str,
    request_sha256: str,
    maximum_cost_microusd: int,
    created_at: datetime,
    retry_of_call_id: str | None = None,
) -> ProviderCallAuthorization:
    validate_provider_usage_ledger(ledger, profile)
    if maximum_cost_microusd < 0:
        raise ValueError("provider maximum call cost cannot be negative")
    if any(
        item.call_id == call_id
        for item in (*ledger.authorizations, *ledger.calls)
    ):
        raise ValueError("provider call id already exists")
    if (
        ledger.authorizations
        and created_at <= ledger.authorizations[-1].created_at
    ):
        raise ValueError(
            "provider authorization must follow the earlier issuance time"
        )
    if retry_of_call_id is not None:
        original = next(
            (
                item
                for item in ledger.calls
                if item.call_id == retry_of_call_id
            ),
            None,
        )
        if original is None:
            raise ValueError("provider retry must reference an earlier call")
        if created_at < original.created_at:
            raise ValueError("provider retry cannot predate the original call")
        if (
            model_candidate_id != original.model_candidate_id
            or request_sha256 != original.request_sha256
        ):
            raise ValueError("provider retry must preserve model and request")
    totals = provider_committed_totals(ledger)
    segment_remaining = (
        profile.budget_policy.segment_caps_microusd[segment] - totals[segment]
    )
    total_remaining = (
        profile.budget_policy.hard_total_microusd - sum(totals.values())
    )
    if maximum_cost_microusd > segment_remaining:
        raise ValueError("provider call exceeds the remaining segment budget")
    if maximum_cost_microusd > total_remaining:
        raise ValueError("provider call exceeds the remaining total budget")
    return ProviderCallAuthorization(
        call_id=call_id,
        segment=segment,
        model_candidate_id=model_candidate_id,
        request_sha256=request_sha256,
        retry_of_call_id=retry_of_call_id,
        authorized_max_cost_microusd=maximum_cost_microusd,
        segment_remaining_before_microusd=segment_remaining,
        total_remaining_before_microusd=total_remaining,
        created_at=created_at,
    )


def _stable_rank(value: str, *, seed: int, namespace: str) -> str:
    return hashlib.sha256(
        f"{namespace}:{seed}:{value}".encode("utf-8")
    ).hexdigest()


def build_option_order_variant(
    option_ids: list[str],
    *,
    seed: int,
) -> OptionOrderVariant:
    if len(option_ids) < 2 or len(option_ids) != len(set(option_ids)):
        raise ValueError("option-order source must contain unique option ids")
    variant = sorted(
        option_ids,
        key=lambda value: _stable_rank(
            value,
            seed=seed,
            namespace="phase4_option_order_v1",
        ),
    )
    if variant == option_ids:
        variant = [*variant[1:], variant[0]]
    return OptionOrderVariant(
        seed=seed,
        canonical_option_ids=option_ids,
        variant_option_ids=variant,
    )


def _alphabetic_alias(index: int) -> str:
    letters = ""
    value = index
    while True:
        value, remainder = divmod(value, 26)
        letters = chr(ord("a") + remainder) + letters
        if value == 0:
            break
        value -= 1
    return letters


def build_option_label_variant(
    option_ids: list[str],
    *,
    seed: int,
) -> OptionLabelVariant:
    if len(option_ids) < 2 or len(option_ids) != len(set(option_ids)):
        raise ValueError("option-label source must contain unique option ids")
    ranked = sorted(
        option_ids,
        key=lambda value: _stable_rank(
            value,
            seed=seed,
            namespace="phase4_option_label_v1",
        ),
    )
    nonce = 0
    while True:
        prefix = f"option_alias_{seed}_{nonce}"
        aliases = [
            f"{prefix}_{_alphabetic_alias(index)}"
            for index in range(len(ranked))
        ]
        if set(aliases).isdisjoint(option_ids):
            break
        nonce += 1
    alias_by_id = dict(zip(ranked, aliases, strict=True))
    return OptionLabelVariant(
        seed=seed,
        aliases=[
            OptionLabelAlias(
                canonical_option_id=option_id,
                provider_alias=alias_by_id[option_id],
            )
            for option_id in option_ids
        ],
    )


def _jensen_shannon_divergence(
    left: list[float],
    right: list[float],
) -> float:
    """Return Jensen-Shannon divergence in bits, bounded to ``[0, 1]``."""

    midpoint = [(a + b) / 2.0 for a, b in zip(left, right, strict=True)]

    def kl_divergence(values: list[float]) -> float:
        return math.fsum(
            value * math.log2(value / middle)
            for value, middle in zip(values, midpoint, strict=True)
            if value > 0.0
        )

    return max(0.0, (kl_divergence(left) + kl_divergence(right)) / 2.0)


def compare_robustness_predictions(
    canonical: RobustnessPrediction,
    variant: RobustnessPrediction,
    *,
    comparison_id: str,
) -> RobustnessComparison:
    if not canonical.output_valid:
        raise ValueError("canonical robustness prediction must be valid")
    if canonical.evaluation_binding != variant.evaluation_binding:
        raise ValueError("robustness predictions do not share an evaluation")
    if canonical.variant_binding is not None:
        raise ValueError("canonical robustness prediction cannot bind a variant")
    if variant.variant_binding is None:
        raise ValueError("shadow robustness prediction must bind its variant")
    if canonical.canonical_option_order != variant.canonical_option_order:
        raise ValueError("robustness comparison option order does not match")
    perturbation_kind = variant.variant_binding.perturbation_kind
    expectation = PHASE4E_PERTURBATION_EXPECTATIONS[perturbation_kind]
    if not variant.output_valid:
        return RobustnessComparison(
            comparison_id=comparison_id,
            evaluation_binding=canonical.evaluation_binding,
            variant_binding=variant.variant_binding,
            perturbation_kind=perturbation_kind,
            expectation=expectation,
            canonical_prediction_sha256=content_sha256(canonical),
            variant_prediction_sha256=content_sha256(variant),
            variant_output_valid=False,
        )
    if (
        canonical.option_probabilities is None
        or variant.option_probabilities is None
        or canonical.top_option_id is None
        or variant.top_option_id is None
    ):
        raise ValueError("valid robustness prediction is incomplete")
    option_ids = canonical.canonical_option_order
    left = [canonical.option_probabilities[item] for item in option_ids]
    right = [variant.option_probabilities[item] for item in option_ids]
    return RobustnessComparison(
        comparison_id=comparison_id,
        evaluation_binding=canonical.evaluation_binding,
        variant_binding=variant.variant_binding,
        perturbation_kind=perturbation_kind,
        expectation=expectation,
        canonical_prediction_sha256=content_sha256(canonical),
        variant_prediction_sha256=content_sha256(variant),
        variant_output_valid=True,
        top_choice_flipped=(canonical.top_option_id != variant.top_option_id),
        max_absolute_probability_delta=max(
            abs(a - b) for a, b in zip(left, right, strict=True)
        ),
        jensen_shannon_divergence=_jensen_shannon_divergence(left, right),
        unsupported_assumption_delta=(
            variant.unsupported_assumption_count
            - canonical.unsupported_assumption_count
        ),
    )


def aggregate_robustness_comparisons(
    comparisons: list[RobustnessComparison],
) -> RobustnessAggregate:
    if not comparisons:
        raise ValueError("robustness aggregate requires comparisons")
    kinds = {item.perturbation_kind for item in comparisons}
    expectations = {item.expectation for item in comparisons}
    bindings = {content_sha256(item.evaluation_binding) for item in comparisons}
    if len(kinds) != 1 or len(expectations) != 1:
        raise ValueError("robustness aggregate requires one perturbation class")
    if len(bindings) != 1:
        raise ValueError(
            "robustness aggregate requires one exact evaluation binding"
        )
    kind = next(iter(kinds))
    if kind is RobustnessPerturbationKind.STOCHASTIC_REPEAT:
        repeat_indices = [
            item.variant_binding.repeat_index for item in comparisons
        ]
        if len(repeat_indices) != len(set(repeat_indices)):
            raise ValueError(
                "stochastic robustness repeats must use distinct indices"
            )
    evaluation_binding = comparisons[0].evaluation_binding
    comparison_sha256s = [content_sha256(item) for item in comparisons]
    valid = [item for item in comparisons if item.variant_output_valid]
    invalid_count = len(comparisons) - len(valid)
    if not valid:
        return RobustnessAggregate(
            evaluation_binding=evaluation_binding,
            comparison_sha256s=comparison_sha256s,
            perturbation_kind=next(iter(kinds)),
            expectation=next(iter(expectations)),
            comparison_count=len(comparisons),
            invalid_output_count=invalid_count,
            invalid_output_rate=invalid_count / len(comparisons),
            valid_comparison_count=0,
            top_choice_flip_count=0,
            unsupported_assumption_delta_total=0,
        )
    probability_deltas = [
        cast(float, item.max_absolute_probability_delta) for item in valid
    ]
    divergences = [
        cast(float, item.jensen_shannon_divergence) for item in valid
    ]
    top_choice_flip_count = sum(
        item.top_choice_flipped is True for item in valid
    )
    return RobustnessAggregate(
        evaluation_binding=evaluation_binding,
        comparison_sha256s=comparison_sha256s,
        perturbation_kind=next(iter(kinds)),
        expectation=next(iter(expectations)),
        comparison_count=len(comparisons),
        invalid_output_count=invalid_count,
        invalid_output_rate=invalid_count / len(comparisons),
        valid_comparison_count=len(valid),
        top_choice_flip_count=top_choice_flip_count,
        top_choice_flip_rate=top_choice_flip_count / len(valid),
        mean_max_absolute_probability_delta=fmean(probability_deltas),
        maximum_absolute_probability_delta=max(probability_deltas),
        mean_jensen_shannon_divergence=fmean(divergences),
        maximum_jensen_shannon_divergence=max(divergences),
        unsupported_assumption_delta_total=sum(
            item.unsupported_assumption_delta or 0 for item in valid
        ),
    )


def validate_robustness_aggregate_against_policy(
    aggregate: RobustnessAggregate,
    profile: Phase4ERobustnessProfile,
    candidate: OpenWeightModelCandidate,
) -> None:
    validate_robustness_evaluation_binding(
        aggregate.evaluation_binding,
        profile,
        candidate,
    )
    policy = profile.robustness_policy
    expected = policy.perturbation_expectations[aggregate.perturbation_kind]
    if aggregate.expectation is not expected:
        raise ValueError("robustness aggregate expectation does not match policy")
    expected_count = {
        RobustnessPerturbationKind.PROMPT_PARAPHRASE: (
            policy.prompt_paraphrase_count
        ),
        RobustnessPerturbationKind.OPTION_ORDER: (
            policy.alternate_option_order_count
        ),
        RobustnessPerturbationKind.OPTION_LABEL: (
            policy.alternate_option_label_count
        ),
        RobustnessPerturbationKind.STOCHASTIC_REPEAT: (
            policy.diagnostic_repeat_count
        ),
    }[aggregate.perturbation_kind]
    if aggregate.comparison_count != expected_count:
        raise ValueError("robustness aggregate count does not match policy")
    if aggregate.invalid_output_count > policy.invalid_outputs_allowed:
        raise ValueError("robustness aggregate exceeds invalid-output allowance")
    if (
        aggregate.expectation is RobustnessExpectation.STRICT_EQUIVARIANCE
        and aggregate.top_choice_flip_count
        > policy.strict_transform_top_choice_flips_allowed
    ):
        raise ValueError("strict robustness transform changed the top choice")


def phase4_robustness_profile_summary(
    profile: Phase4ERobustnessProfile,
) -> dict[str, object]:
    return {
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "profile_sha256": content_sha256(profile),
        "open_weight_required": profile.model_policy.open_weight_required,
        "hosted_inference_allowed": (
            profile.model_policy.hosted_inference_allowed
        ),
        "development_candidate_count": (
            profile.model_policy.development_candidate_count
        ),
        "llm_role_count": len(profile.model_policy.required_roles),
        "hard_api_budget_usd": (
            profile.budget_policy.hard_total_microusd / 1_000_000
        ),
        "primary_call_count": profile.robustness_policy.primary_call_count,
        "diagnostic_repeat_count": (
            profile.robustness_policy.diagnostic_repeat_count
        ),
        "perturbation_count": len(
            profile.robustness_policy.perturbation_expectations
        ),
        "primary_outcome_count": len(profile.metric_policy.primary_outcomes),
        "secondary_metric_count": len(profile.metric_policy.secondary_metrics),
        "participant_content_omitted": True,
    }
