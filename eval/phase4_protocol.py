"""Phase 4A architecture and comparison contract.

Phase 3 froze the held-out civic-measure instrument. Phase 4A freezes what the
components around that instrument are allowed to mean before any provider,
prompt, or live LLM implementation is selected. The LLM is an elicitation
orchestrator and an experimental readout control; it is not the durable store
of a participant's preferences. Only an explicit preference model may update
the posterior from typed, eligible evidence.

This module deliberately contains no provider SDK code and does not load the
restricted Phase 3 bank. Its tracked profile binds only to the public Phase 3A
bank profile.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Self, TypeVar

from pydantic import field_validator, model_validator

from .bank_profile import EvaluationBankProfile, ModelExcludedInput
from .contracts import (
    BallotType,
    ContractModel,
    NonEmptyText,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256

EnumValue = TypeVar("EnumValue", bound=Enum)


def _require_complete_enum_set(
    label: str,
    values: list[EnumValue],
    enum_type: type[EnumValue],
    *,
    set_name: str = "v1",
) -> None:
    expected = set(enum_type)
    if set(values) != expected:
        raise ValueError(
            f"{label} must contain the complete {set_name} set"
        )
    if len(values) != len(expected):
        raise ValueError(f"{label} cannot contain duplicates")


class ElicitationPolicy(str, Enum):
    FIXED_SEQUENCE = "fixed_sequence"
    RANDOM = "random"
    MAX_VARIANCE = "max_variance"
    TOOL_USING_LLM = "tool_using_llm"


class EvidenceCondition(str, Enum):
    STRUCTURED_ONLY = "structured_only"
    CONVERSATION_ONLY = "conversation_only"
    COMBINED = "combined"


class PreferenceRepresentation(str, Enum):
    UNIFORM_PRIOR = "uniform_prior"
    GAUSSIAN_LINEAR_FIXED = "gaussian_linear_fixed"
    BRADLEY_TERRY_FIXED = "bradley_terry_fixed"
    TRANSCRIPT_CONTEXT_ONLY = "transcript_context_only"
    EXPLICIT_POSTERIOR_FIXED = "explicit_posterior_fixed"
    EXPLICIT_POSTERIOR_EXPANDING = "explicit_posterior_expanding"


class OntologyMode(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    FIXED = "fixed"
    EXPANDING = "expanding"


class PredictionReadout(str, Enum):
    UNINFORMATIVE_PRIOR = "uninformative_prior"
    AUTHORED_SEMANTIC_MAPPING = "authored_semantic_mapping"
    DIRECT_LLM = "direct_llm"
    LLM_PLUS_EXPLICIT_POSTERIOR = "llm_plus_explicit_posterior"


class ModelArmRole(str, Enum):
    NULL_BASELINE = "null_baseline"
    STRUCTURED_BASELINE = "structured_baseline"
    EXPERIMENTAL_CONTROL = "experimental_control"
    CANDIDATE = "candidate"


class ReplayableComparisonAxis(str, Enum):
    PREFERENCE_REPRESENTATION = "preference_representation"
    EVIDENCE_CONDITION = "evidence_condition"
    PREDICTION_READOUT = "prediction_readout"
    EVIDENCE_WEIGHTING = "evidence_weighting"


class RequiredAblation(str, Enum):
    FIXED_VS_ADAPTIVE_ACQUISITION = "fixed_vs_adaptive_acquisition"
    STRUCTURED_VS_CONFIRMED_LLM_EXTRACTION = (
        "structured_vs_confirmed_llm_extraction"
    )
    STRUCTURED_VS_CONVERSATION_VS_COMBINED = (
        "structured_vs_conversation_vs_combined"
    )
    FIXED_VS_EXPANDING_ONTOLOGY = "fixed_vs_expanding_ontology"
    AUTHORED_VS_DIRECT_LLM_VS_HYBRID_READOUT = (
        "authored_vs_direct_llm_vs_hybrid_readout"
    )
    RELIABILITY_VS_UNIFORM_EVIDENCE_WEIGHTS = (
        "reliability_vs_uniform_evidence_weights"
    )


class AcquisitionClaimSource(str, Enum):
    SEEDED_SYNTHETIC_COUNTERFACTUAL = "seeded_synthetic_counterfactual"
    RANDOMIZED_HUMAN_ASSIGNMENT = "randomized_human_assignment"


class EvaluationOnlyBenchmark(str, Enum):
    PARTY_CONDITIONED_PRIOR_WHERE_SUPPORTED = (
        "party_conditioned_prior_where_supported"
    )


class InterviewerAction(str, Enum):
    ASK_VETTED_QUESTION = "ask_vetted_question"
    CLARIFY_EXISTING_EVIDENCE = "clarify_existing_evidence"
    PAUSE_AND_RESUME = "pause_and_resume"


class InterviewerTool(str, Enum):
    READ_POSTERIOR_UNCERTAINTY = "read_posterior_uncertainty"
    READ_CANDIDATE_QUESTION_SCORES = "read_candidate_question_scores"
    READ_EVIDENCE_COVERAGE = "read_evidence_coverage"
    READ_EVIDENCE_CONFLICTS = "read_evidence_conflicts"


class ArchitectureBoundary(ContractModel):
    """Ownership boundaries shared by every intended product implementation."""

    durable_preference_state_owner: Literal["explicit_preference_posterior"] = (
        "explicit_preference_posterior"
    )
    interviewer_role: Literal["elicitation_orchestrator"] = (
        "elicitation_orchestrator"
    )
    evidence_extractor_role: Literal["propose_typed_evidence"] = (
        "propose_typed_evidence"
    )
    ballot_semantic_mapper_role: Literal[
        "map_packet_options_into_preference_space"
    ] = "map_packet_options_into_preference_space"
    prediction_readout_role: Literal["emit_full_option_probabilities"] = (
        "emit_full_option_probabilities"
    )
    action_policy_role: Literal["apply_user_authorized_selection_rule"] = (
        "apply_user_authorized_selection_rule"
    )
    direct_llm_role: Literal["experimental_prediction_control"] = (
        "experimental_prediction_control"
    )
    posterior_updates_require_typed_evidence: Literal[True] = True
    only_preference_model_updates_posterior: Literal[True] = True
    llm_outputs_cannot_directly_update_posterior: Literal[True] = True
    inferred_evidence_requires_participant_confirmation: Literal[True] = True
    raw_evidence_and_provenance_are_preserved: Literal[True] = True
    corrections_require_explicit_confirmation: Literal[True] = True
    ballot_overrides_never_train_automatically: Literal[True] = True
    passive_non_intervention_has_zero_evidence_weight: Literal[True] = True
    semantic_mapping_is_separate_from_preference_storage: Literal[True] = True


class InterviewerV1Policy(ContractModel):
    """Constrained first LLM interviewer, before generated items are studied."""

    provider_neutral: Literal[True] = True
    allowed_actions: list[InterviewerAction]
    allowed_tools: list[InterviewerTool]
    question_content_authority: Literal[
        "versioned_vetted_bank_and_evidence_linked_clarifications"
    ] = "versioned_vetted_bank_and_evidence_linked_clarifications"
    question_id_and_version_binding_required: Literal[True] = True
    natural_language_rendering_allowed: Literal[True] = True
    rendering_may_add_substantive_content: Literal[False] = False
    rendering_must_preserve_semantics_and_response_scale: Literal[True] = True
    rendering_validation_required_before_presentation: Literal[True] = True
    novel_substantive_question_generation_allowed: Literal[False] = False
    clarification_must_link_existing_evidence_ids: Literal[True] = True
    participant_confirmation_required_before_posterior_update: Literal[True] = True
    provisional_extracted_evidence_weight: Literal[0.0] = 0.0
    no_fixed_conversation_length: Literal[True] = True
    every_turn_and_tool_result_is_versioned: Literal[True] = True

    @model_validator(mode="after")
    def require_complete_v1_surface(self) -> Self:
        _require_complete_enum_set(
            "allowed_actions",
            self.allowed_actions,
            InterviewerAction,
            set_name="Phase 4A v1",
        )
        _require_complete_enum_set(
            "allowed_tools",
            self.allowed_tools,
            InterviewerTool,
            set_name="Phase 4A v1",
        )
        return self


class TargetIsolationPolicy(ContractModel):
    """Input boundary for live model arms, excluding evaluation-only benchmarks."""

    primary_mode: Literal["held_out_delegation_prediction"] = (
        "held_out_delegation_prediction"
    )
    target_packet_visible_to_interviewer_during_elicitation: Literal[False] = False
    target_packet_visible_to_evidence_extractor_during_elicitation: Literal[
        False
    ] = False
    target_packet_visible_to_prediction_readout: Literal[True] = True
    target_specific_questions_after_packet_exposure_allowed: Literal[False] = False
    future_consultation_mode_must_be_reported_separately: Literal[True] = True
    target_response_hidden_until_prediction_is_frozen: Literal[True] = True
    same_frozen_packet_for_participant_and_model: Literal[True] = True
    excluded_model_inputs: list[ModelExcludedInput]

    @field_validator("excluded_model_inputs")
    @classmethod
    def require_complete_exclusion_set(
        cls, value: list[ModelExcludedInput]
    ) -> list[ModelExcludedInput]:
        _require_complete_enum_set(
            "excluded_model_inputs",
            value,
            ModelExcludedInput,
        )
        return value


class ModelArm(ContractModel):
    record_version: Literal["phase4_model_arm.v1"] = "phase4_model_arm.v1"
    arm_id: StableId
    label: NonEmptyText
    role: ModelArmRole
    representation: PreferenceRepresentation
    ontology_mode: OntologyMode
    prediction_readout: PredictionReadout
    evidence_conditions: list[EvidenceCondition]
    uses_explicit_posterior: bool

    @field_validator("evidence_conditions")
    @classmethod
    def evidence_conditions_must_be_unique(
        cls, value: list[EvidenceCondition]
    ) -> list[EvidenceCondition]:
        if len(value) != len(set(value)):
            raise ValueError("model-arm evidence_conditions must be unique")
        return value

    @model_validator(mode="after")
    def validate_component_compatibility(self) -> Self:
        explicit_representations = {
            PreferenceRepresentation.GAUSSIAN_LINEAR_FIXED,
            PreferenceRepresentation.BRADLEY_TERRY_FIXED,
            PreferenceRepresentation.EXPLICIT_POSTERIOR_FIXED,
            PreferenceRepresentation.EXPLICIT_POSTERIOR_EXPANDING,
        }
        if self.uses_explicit_posterior != (
            self.representation in explicit_representations
        ):
            raise ValueError(
                "uses_explicit_posterior must agree with representation"
            )
        if self.ontology_mode is OntologyMode.EXPANDING and not (
            self.representation
            is PreferenceRepresentation.EXPLICIT_POSTERIOR_EXPANDING
        ):
            raise ValueError(
                "expanding ontology requires explicit_posterior_expanding"
            )
        if (
            self.prediction_readout is PredictionReadout.DIRECT_LLM
            and self.role is not ModelArmRole.EXPERIMENTAL_CONTROL
        ):
            raise ValueError("direct LLM readout must remain an experimental control")
        if (
            self.prediction_readout
            is PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR
            and not self.uses_explicit_posterior
        ):
            raise ValueError("hybrid readout requires an explicit posterior")
        if (
            self.representation is PreferenceRepresentation.UNIFORM_PRIOR
            and self.evidence_conditions
        ):
            raise ValueError("uniform prior cannot consume participant evidence")
        return self


ArmSignature = tuple[
    ModelArmRole,
    PreferenceRepresentation,
    OntologyMode,
    PredictionReadout,
    frozenset[EvidenceCondition],
    bool,
]

_ALL_EVIDENCE_CONDITIONS: frozenset[EvidenceCondition] = frozenset(
    EvidenceCondition
)

_REQUIRED_ARM_SIGNATURES: dict[str, ArmSignature] = {
    "uniform_prior": (
        ModelArmRole.NULL_BASELINE,
        PreferenceRepresentation.UNIFORM_PRIOR,
        OntologyMode.NOT_APPLICABLE,
        PredictionReadout.UNINFORMATIVE_PRIOR,
        frozenset(),
        False,
    ),
    "gaussian_linear_fixed": (
        ModelArmRole.STRUCTURED_BASELINE,
        PreferenceRepresentation.GAUSSIAN_LINEAR_FIXED,
        OntologyMode.FIXED,
        PredictionReadout.AUTHORED_SEMANTIC_MAPPING,
        frozenset({EvidenceCondition.STRUCTURED_ONLY}),
        True,
    ),
    "bradley_terry_fixed": (
        ModelArmRole.STRUCTURED_BASELINE,
        PreferenceRepresentation.BRADLEY_TERRY_FIXED,
        OntologyMode.FIXED,
        PredictionReadout.AUTHORED_SEMANTIC_MAPPING,
        frozenset({EvidenceCondition.STRUCTURED_ONLY}),
        True,
    ),
    "direct_llm_control": (
        ModelArmRole.EXPERIMENTAL_CONTROL,
        PreferenceRepresentation.TRANSCRIPT_CONTEXT_ONLY,
        OntologyMode.NOT_APPLICABLE,
        PredictionReadout.DIRECT_LLM,
        _ALL_EVIDENCE_CONDITIONS,
        False,
    ),
    "hybrid_fixed_ontology": (
        ModelArmRole.CANDIDATE,
        PreferenceRepresentation.EXPLICIT_POSTERIOR_FIXED,
        OntologyMode.FIXED,
        PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR,
        _ALL_EVIDENCE_CONDITIONS,
        True,
    ),
    "hybrid_expanding_ontology": (
        ModelArmRole.CANDIDATE,
        PreferenceRepresentation.EXPLICIT_POSTERIOR_EXPANDING,
        OntologyMode.EXPANDING,
        PredictionReadout.LLM_PLUS_EXPLICIT_POSTERIOR,
        _ALL_EVIDENCE_CONDITIONS,
        True,
    ),
}


class ComparisonPolicy(ContractModel):
    acquisition_policies: list[ElicitationPolicy]
    model_arms: list[ModelArm]
    required_evidence_conditions: list[EvidenceCondition]
    required_ablations: list[RequiredAblation]
    replayable_on_same_evidence_stream: list[ReplayableComparisonAxis]
    acquisition_claim_sources: list[AcquisitionClaimSource]
    evaluation_only_benchmarks: list[EvaluationOnlyBenchmark]
    acquisition_policies_produce_different_evidence_streams: Literal[True] = True
    single_participant_acquisition_path_is_descriptive_only: Literal[True] = True
    same_realized_evidence_required_within_replay_comparisons: Literal[True] = True
    same_evidence_cutoff_required_within_replay_comparisons: Literal[True] = True
    same_target_packet_required_for_all_prediction_arms: Literal[True] = True
    direct_llm_control_required: Literal[True] = True
    accuracy_and_calibration_take_priority_over_efficiency: Literal[True] = True
    efficiency_reported_as_learning_curve: Literal[True] = True
    learning_curve_unit: Literal["confirmed_evidence_prefix"] = (
        "confirmed_evidence_prefix"
    )
    one_hard_session_limit_is_a_primary_result: Literal[False] = False
    party_benchmark_uses_post_retest_metadata_only: Literal[True] = True
    party_benchmark_never_enters_live_evidence: Literal[True] = True
    party_benchmark_requires_external_support: Literal[True] = True

    @model_validator(mode="after")
    def validate_frozen_comparison_matrix(self) -> Self:
        _require_complete_enum_set(
            "acquisition_policies",
            self.acquisition_policies,
            ElicitationPolicy,
        )
        _require_complete_enum_set(
            "required_evidence_conditions",
            self.required_evidence_conditions,
            EvidenceCondition,
        )
        _require_complete_enum_set(
            "required_ablations",
            self.required_ablations,
            RequiredAblation,
        )
        _require_complete_enum_set(
            "replayable_on_same_evidence_stream",
            self.replayable_on_same_evidence_stream,
            ReplayableComparisonAxis,
        )
        _require_complete_enum_set(
            "acquisition_claim_sources",
            self.acquisition_claim_sources,
            AcquisitionClaimSource,
        )
        _require_complete_enum_set(
            "evaluation_only_benchmarks",
            self.evaluation_only_benchmarks,
            EvaluationOnlyBenchmark,
        )

        arm_ids = [arm.arm_id for arm in self.model_arms]
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError("model arm ids must be unique")
        if set(arm_ids) != set(_REQUIRED_ARM_SIGNATURES):
            raise ValueError("model_arms must contain the exact Phase 4A v1 matrix")
        for arm in self.model_arms:
            actual = (
                arm.role,
                arm.representation,
                arm.ontology_mode,
                arm.prediction_readout,
                frozenset(arm.evidence_conditions),
                arm.uses_explicit_posterior,
            )
            if actual != _REQUIRED_ARM_SIGNATURES[arm.arm_id]:
                raise ValueError(
                    f"model arm {arm.arm_id!r} does not match its frozen v1 role"
                )
        return self


class ActionPolicy(ContractModel):
    single_choice_selection_rule: Literal[
        "always_select_top_probability_option"
    ] = (
        "always_select_top_probability_option"
    )
    rich_ballot_selection_rule: Literal[
        "emit_complete_measure_declared_ballot_payload"
    ] = "emit_complete_measure_declared_ballot_payload"
    supported_ballot_types: list[BallotType]
    exact_probability_ties_use_frozen_display_order: Literal[True] = True
    full_option_probabilities_required: Literal[True] = True
    format_specific_prediction_required: Literal[True] = True
    rich_ballot_payload_must_validate_against_measure: Literal[True] = True
    confidence_equals_top_option_probability: Literal[True] = True
    confidence_displayed_when_prediction_is_revealed: Literal[True] = True
    model_abstention_allowed: Literal[False] = False
    model_deferral_allowed: Literal[False] = False
    participant_override_allowed: Literal[True] = True
    participant_abstention_allowed: Literal[True] = True
    confidence_thresholds_are_diagnostics_only: Literal[True] = True
    thresholded_authorization_is_future_user_controlled_policy: Literal[True] = True
    binding_civic_action_in_scope: Literal[False] = False
    held_constant_across_phase4_model_arms: Literal[True] = True

    @field_validator("supported_ballot_types")
    @classmethod
    def require_every_supported_ballot_type(
        cls, value: list[BallotType]
    ) -> list[BallotType]:
        _require_complete_enum_set(
            "supported_ballot_types",
            value,
            BallotType,
        )
        return value


class Phase4Protocol(ContractModel):
    schema_version: Literal["preference_eval_phase4_protocol.v1"]
    protocol_id: StableId
    protocol_version: Literal[1]
    created_at: datetime
    bank_profile_id: StableId
    bank_profile_version: PositiveVersion
    bank_profile_sha256: Sha256Digest
    architecture: ArchitectureBoundary
    interviewer: InterviewerV1Policy
    target_isolation: TargetIsolationPolicy
    comparison: ComparisonPolicy
    action_policy: ActionPolicy

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class Phase4ProtocolManifest(ContractModel):
    schema_version: Literal["preference_eval_phase4_protocol_manifest.v1"] = (
        "preference_eval_phase4_protocol_manifest.v1"
    )
    protocol_id: StableId
    protocol_version: PositiveVersion
    protocol_sha256: Sha256Digest
    bank_profile_sha256: Sha256Digest
    architecture_sha256: Sha256Digest
    interviewer_sha256: Sha256Digest
    target_isolation_sha256: Sha256Digest
    comparison_sha256: Sha256Digest
    action_policy_sha256: Sha256Digest


def load_phase4_protocol(path: str | Path) -> Phase4Protocol:
    """Load and validate the public Phase 4A protocol profile."""

    protocol_path = Path(path)
    raw = json.loads(protocol_path.read_text(encoding="utf-8"))
    return Phase4Protocol.model_validate(raw)


def validate_phase4_protocol_against_bank_profile(
    protocol: Phase4Protocol,
    bank_profile: EvaluationBankProfile,
) -> None:
    """Bind Phase 4A to the public bank profile without loading held-out text."""

    if protocol.bank_profile_id != bank_profile.profile_id:
        raise ValueError(
            f"protocol bank_profile_id {protocol.bank_profile_id!r} does not "
            f"match {bank_profile.profile_id!r}"
        )
    if protocol.bank_profile_version != bank_profile.profile_version:
        raise ValueError(
            "protocol bank_profile_version does not match the bank profile"
        )
    expected_hash = content_sha256(bank_profile)
    if protocol.bank_profile_sha256 != expected_hash:
        raise ValueError(
            "protocol bank_profile_sha256 does not match the bank profile"
        )


def build_phase4_protocol_manifest(
    protocol: Phase4Protocol,
) -> Phase4ProtocolManifest:
    """Hash a protocol after its public bank-profile binding is validated."""

    return Phase4ProtocolManifest(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_sha256=content_sha256(protocol),
        bank_profile_sha256=protocol.bank_profile_sha256,
        architecture_sha256=content_sha256(protocol.architecture),
        interviewer_sha256=content_sha256(protocol.interviewer),
        target_isolation_sha256=content_sha256(protocol.target_isolation),
        comparison_sha256=content_sha256(protocol.comparison),
        action_policy_sha256=content_sha256(protocol.action_policy),
    )


def phase4_protocol_summary(protocol: Phase4Protocol) -> dict[str, object]:
    """Return a public, content-free summary for CLI output and review."""

    return {
        "acquisition_policy_count": len(protocol.comparison.acquisition_policies),
        "model_arm_count": len(protocol.comparison.model_arms),
        "evidence_condition_count": len(
            protocol.comparison.required_evidence_conditions
        ),
        "required_ablation_count": len(protocol.comparison.required_ablations),
        "evaluation_only_benchmark_count": len(
            protocol.comparison.evaluation_only_benchmarks
        ),
        "interviewer_tool_count": len(protocol.interviewer.allowed_tools),
        "target_visible_during_elicitation": (
            protocol.target_isolation
            .target_packet_visible_to_interviewer_during_elicitation
        ),
        "model_abstention_allowed": protocol.action_policy.model_abstention_allowed,
        "direct_llm_role": protocol.architecture.direct_llm_role,
    }
