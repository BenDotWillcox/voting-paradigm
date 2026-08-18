"""Blinded authoring and independent review for the final Phase 4 semantic map.

The runtime semantic-map contract intentionally contains only the sparse
option-to-ontology weights consumed by prediction models. This module keeps
the higher-risk authoring judgments separate and reviewable: a public profile
freezes the allowed evidence surface and coarse ordinal rubric, a restricted
authoring bundle records packet-grounded rationales, and a restricted review
log approves every exact derived mapping before use.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from preferences.questions.bank import QuestionBank

from .bank_authoring import (
    is_participant_text_pointer,
    resolve_json_pointer,
)
from .bank_profile import (
    EvaluationBankProfile,
    ReviewActorType,
    validate_final_fixture_against_profile,
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
from .phase4_evidence import FixedOntologyReference
from .phase4_protocol import (
    Phase4Protocol,
    validate_phase4_protocol_against_bank_profile,
)
from .phase4_prediction import (
    ComponentArtifactReference,
    ReviewedSemanticMapperReference,
)
from .phase4_semantic import (
    AuthoredMeasureSemanticMapping,
    AuthoredOptionStance,
    AuthoredSemanticMapBundle,
    authored_semantic_map_summary,
    validate_authored_semantic_map,
)
from .review_artifacts import (
    NonNegativeCount,
    ReviewFindingDisposition,
    ReviewFindingSeverity,
    canonical_text_sha256,
    review_system_matches,
)

PHASE4_SEMANTIC_REVIEW_PROMPT_PATH = (
    Path(__file__).parent / "prompts" / "phase4_semantic_review_v1.md"
)
PHASE4_SEMANTIC_REVIEW_PROMPT_SHA256 = (
    "08c71f8ab8359c6c749741239c7a3615"
    "d3c7c5816b4ad9b6fd532783bede172f"
)

OrdinalSemanticPosition = Literal[-1, 0, 1]
ImportanceWeight = Annotated[
    float,
    Field(gt=0.0, le=1.0, allow_inf_nan=False),
]


class SemanticImportance(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class SemanticMapExcludedInput(str, Enum):
    PARTICIPANT_RESPONSE = "participant_response"
    PREFERENCE_EVIDENCE = "preference_evidence"
    POSTERIOR_STATE = "posterior_state"
    POLITICAL_IDENTITY = "political_identity"
    PARTISAN_VOTING_HISTORY = "partisan_voting_history"
    DEMOGRAPHIC_PROXY = "demographic_proxy"
    OUTSIDE_POLICY_FACT = "outside_policy_fact"


class SemanticMapReviewCategory(str, Enum):
    CANONICAL_BINDING = "canonical_binding"
    PACKET_ONLY_GROUNDING = "packet_only_grounding"
    DIMENSION_SEMANTIC_FIDELITY = "dimension_semantic_fidelity"
    DIRECTIONAL_ACCURACY = "directional_accuracy"
    RELATIVE_MAGNITUDE = "relative_magnitude"
    OPTION_SYMMETRY = "option_symmetry"
    SPARSITY_AND_OMISSION = "sparsity_and_omission"
    POLITICAL_CUE_EXCLUSION = "political_cue_exclusion"


class SemanticMapAuthoringProfile(ContractModel):
    """Public precommitment for deriving the held-out semantic map."""

    schema_version: Literal["phase4_semantic_authoring_profile.v1"] = (
        "phase4_semantic_authoring_profile.v1"
    )
    profile_id: StableId
    profile_version: PositiveVersion
    bank_profile_id: StableId
    bank_profile_version: PositiveVersion
    bank_profile_sha256: Sha256Digest
    phase4_protocol_id: StableId
    phase4_protocol_version: PositiveVersion
    phase4_protocol_sha256: Sha256Digest
    ontology: FixedOntologyReference
    ontology_definitions_sha256: Sha256Digest
    expected_measure_count: int = Field(ge=1)
    author_system: Literal["codex"] = "codex"
    ai_reviewer_system: Literal["claude"] = "claude"
    input_authority: Literal[
        "exact_participant_packet_and_frozen_ontology_only"
    ] = "exact_participant_packet_and_frozen_ontology_only"
    excluded_inputs: list[SemanticMapExcludedInput]
    ordinal_positions: list[OrdinalSemanticPosition]
    importance_weights: dict[SemanticImportance, ImportanceWeight]
    at_least_one_primary_dimension_per_measure: Literal[True] = True
    unsupported_relationships_are_omitted: Literal[True] = True
    exact_packet_path_required_per_option_position: Literal[True] = True
    restricted_rationale_required_per_dimension: Literal[True] = True
    option_centering_is_derived: Literal[True] = True
    absolute_scale_normalized_at_runtime: Literal[True] = True
    participant_blind_to_exact_mapping_until_completion: Literal[True] = True
    participant_receives_nonrevealing_summary_only: Literal[True] = True
    participant_independent_review_required: Literal[True] = True
    human_content_review_required_before_external_pilot: Literal[True] = True
    required_review_checks: list[SemanticMapReviewCategory]

    @model_validator(mode="after")
    def require_complete_v1_rubric(self) -> Self:
        if self.excluded_inputs != list(SemanticMapExcludedInput):
            raise ValueError(
                "semantic-map profile must list every excluded input in "
                "canonical order"
            )
        if self.ordinal_positions != [-1, 0, 1]:
            raise ValueError(
                "semantic-map ordinal positions must be exactly [-1, 0, 1]"
            )
        if set(self.importance_weights) != set(SemanticImportance):
            raise ValueError(
                "semantic-map profile must define every importance tier"
            )
        if not math.isclose(
            self.importance_weights[SemanticImportance.PRIMARY],
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.importance_weights[SemanticImportance.SECONDARY],
            0.5,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "semantic-map v1 importance weights must be primary=1 and "
                "secondary=0.5"
            )
        if self.required_review_checks != list(SemanticMapReviewCategory):
            raise ValueError(
                "semantic-map profile must list every v1 review check in "
                "canonical order"
            )
        return self


class SemanticOptionPosition(ContractModel):
    """One option's coarse relative position on an assigned dimension."""

    record_version: Literal["phase4_semantic_option_position.v1"] = (
        "phase4_semantic_option_position.v1"
    )
    option_id: StableId
    ordinal_position: OrdinalSemanticPosition
    supporting_content_paths: list[str] = Field(min_length=1)

    @field_validator("supporting_content_paths")
    @classmethod
    def require_unique_paths(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("semantic option-position paths must be unique")
        return value


class SemanticDimensionAssignment(ContractModel):
    """Packet-grounded relative positions for one ontology dimension."""

    record_version: Literal["phase4_semantic_dimension_assignment.v1"] = (
        "phase4_semantic_dimension_assignment.v1"
    )
    dimension_id: StableId
    importance: SemanticImportance
    option_positions: list[SemanticOptionPosition] = Field(min_length=2)
    rationale: NonEmptyText

    @model_validator(mode="after")
    def require_unique_contrasting_positions(self) -> Self:
        option_ids = [item.option_id for item in self.option_positions]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("semantic assignment option ids must be unique")
        if len(
            {item.ordinal_position for item in self.option_positions}
        ) == 1:
            raise ValueError(
                "semantic dimension assignment must distinguish options"
            )
        return self


class SemanticMeasureAuthoringRecord(ContractModel):
    """Restricted rationale record for one exact measure mapping."""

    record_version: Literal["phase4_semantic_measure_authoring.v1"] = (
        "phase4_semantic_measure_authoring.v1"
    )
    measure_id: StableId
    measure_version: PositiveVersion
    packet_version: PositiveVersion
    packet_sha256: Sha256Digest
    dimension_assignments: list[SemanticDimensionAssignment] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def require_unique_dimensions_and_primary(self) -> Self:
        dimension_ids = [
            item.dimension_id for item in self.dimension_assignments
        ]
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError(
                "semantic measure assignments must use unique dimensions"
            )
        if not any(
            item.importance is SemanticImportance.PRIMARY
            for item in self.dimension_assignments
        ):
            raise ValueError(
                "semantic measure authoring requires a primary dimension"
            )
        return self


class SemanticMapAuthoringBundle(ContractModel):
    """Restricted packet-grounded source from which the runtime map is built."""

    schema_version: Literal["phase4_semantic_authoring_bundle.v1"] = (
        "phase4_semantic_authoring_bundle.v1"
    )
    bundle_id: StableId
    bundle_version: PositiveVersion
    authoring_profile_id: StableId
    authoring_profile_version: PositiveVersion
    authoring_profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    mapper_id: StableId
    mapper_version: PositiveVersion
    author_system: NonEmptyText
    authored_at: datetime
    measure_records: list[SemanticMeasureAuthoringRecord] = Field(
        min_length=1
    )

    @field_validator("authored_at")
    @classmethod
    def authored_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authored_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_measure_records(self) -> Self:
        measure_refs = [
            (item.measure_id, item.measure_version)
            for item in self.measure_records
        ]
        if len(measure_refs) != len(set(measure_refs)):
            raise ValueError(
                "semantic authoring measure references must be unique"
            )
        return self


class SemanticMapReviewFinding(ContractModel):
    """One exact-content finding kept in the restricted review log."""

    record_version: Literal["phase4_semantic_review_finding.v1"] = (
        "phase4_semantic_review_finding.v1"
    )
    finding_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    dimension_id: StableId | None = None
    category: SemanticMapReviewCategory
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
                "blocking semantic-map findings must be resolved before "
                "approval"
            )
        return self


class SemanticMeasureReviewApproval(ContractModel):
    """Approval of one exact derived measure mapping."""

    record_version: Literal["phase4_semantic_measure_approval.v1"] = (
        "phase4_semantic_measure_approval.v1"
    )
    measure_id: StableId
    measure_version: PositiveVersion
    mapping_sha256: Sha256Digest
    findings_count: NonNegativeCount
    completed_checks: list[SemanticMapReviewCategory]
    approved: Literal[True] = True

    @field_validator("completed_checks")
    @classmethod
    def require_every_review_check(
        cls,
        value: list[SemanticMapReviewCategory],
    ) -> list[SemanticMapReviewCategory]:
        if value != list(SemanticMapReviewCategory):
            raise ValueError(
                "semantic-map approval must record every v1 check in "
                "canonical order"
            )
        return value


class SemanticMapReviewLog(ContractModel):
    """Restricted independent review of one exact derived semantic map."""

    schema_version: Literal["phase4_semantic_review_log.v1"] = (
        "phase4_semantic_review_log.v1"
    )
    log_id: StableId
    log_version: PositiveVersion
    authoring_profile_id: StableId
    authoring_profile_version: PositiveVersion
    authoring_profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    authoring_bundle_id: StableId
    authoring_bundle_version: PositiveVersion
    authoring_bundle_sha256: Sha256Digest
    mapper_id: StableId
    mapper_version: PositiveVersion
    mapper_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: NonEmptyText
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    completed_at: datetime
    findings: list[SemanticMapReviewFinding] = Field(default_factory=list)
    measure_approvals: list[SemanticMeasureReviewApproval] = Field(
        min_length=1
    )

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_unique_and_reconciled_approvals(self) -> Self:
        if self.reviewer_type is ReviewActorType.AI and (
            self.reviewer_model_version is None
            or self.review_prompt_sha256 is None
        ):
            raise ValueError(
                "AI semantic-map review requires model and prompt provenance"
            )
        approval_refs = [
            (item.measure_id, item.measure_version)
            for item in self.measure_approvals
        ]
        if len(approval_refs) != len(set(approval_refs)):
            raise ValueError(
                "semantic-map approval references must be unique"
            )
        finding_ids = [item.finding_id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("semantic-map finding ids must be unique")
        finding_counts = Counter(
            (item.measure_id, item.measure_version)
            for item in self.findings
        )
        approval_by_ref = {
            (item.measure_id, item.measure_version): item
            for item in self.measure_approvals
        }
        if set(finding_counts) - set(approval_by_ref):
            raise ValueError(
                "semantic-map findings reference measures without approval"
            )
        for measure_ref, approval in approval_by_ref.items():
            if approval.findings_count != finding_counts[measure_ref]:
                raise ValueError(
                    "semantic-map findings_count does not match the "
                    "restricted log"
                )
        return self


class NonrevealingSemanticMapReviewSummary(ContractModel):
    """Aggregate review evidence safe for the mapping-blind participant."""

    schema_version: Literal[
        "phase4_nonrevealing_semantic_review_summary.v1"
    ] = "phase4_nonrevealing_semantic_review_summary.v1"
    summary_id: StableId
    authoring_profile_id: StableId
    authoring_profile_version: PositiveVersion
    authoring_profile_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    authoring_bundle_sha256: Sha256Digest
    mapper_id: StableId
    mapper_version: PositiveVersion
    mapper_sha256: Sha256Digest
    review_log_id: StableId
    review_log_version: PositiveVersion
    review_log_sha256: Sha256Digest
    reviewer_type: ReviewActorType
    reviewer_system: NonEmptyText
    reviewer_model_version: str | None = Field(default=None, min_length=1)
    review_prompt_sha256: Sha256Digest | None = None
    reviewed_measure_count: int = Field(ge=1)
    reviewed_option_count: int = Field(ge=2)
    used_dimension_count: int = Field(ge=1)
    dimension_assignment_count: int = Field(ge=1)
    findings_count: NonNegativeCount
    findings_by_category: dict[
        SemanticMapReviewCategory,
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
    all_mappings_approved: Literal[True] = True
    exact_packets_weights_rationales_and_findings_omitted: Literal[True] = True

    @model_validator(mode="after")
    def validate_complete_aggregate_counts(self) -> Self:
        groups = (
            (self.findings_by_category, set(SemanticMapReviewCategory)),
            (self.findings_by_severity, set(ReviewFindingSeverity)),
            (
                self.findings_by_disposition,
                set(ReviewFindingDisposition),
            ),
        )
        for actual, expected in groups:
            if set(actual) != expected:
                raise ValueError(
                    "semantic-map safe counts must include every enum value"
                )
            if sum(actual.values()) != self.findings_count:
                raise ValueError(
                    "semantic-map safe counts must sum to findings_count"
                )
        return self


def ontology_definition_payload(
    question_bank: QuestionBank,
) -> list[dict[str, str]]:
    """Canonical public ontology definitions used during map authoring."""

    return [
        {
            "item_id": item.id,
            "text": item.text,
            "description": item.description,
            "domain": item.domain or "",
        }
        for item in sorted(question_bank.items, key=lambda item: item.id)
    ]


def load_semantic_map_authoring_profile(
    path: str | Path,
) -> SemanticMapAuthoringProfile:
    return SemanticMapAuthoringProfile.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_semantic_map_authoring_bundle(
    path: str | Path,
) -> SemanticMapAuthoringBundle:
    return SemanticMapAuthoringBundle.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_semantic_map_review_log(
    path: str | Path,
) -> SemanticMapReviewLog:
    return SemanticMapReviewLog.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def validate_semantic_map_authoring_profile(
    profile: SemanticMapAuthoringProfile,
    bank_profile: EvaluationBankProfile,
    protocol: Phase4Protocol,
    question_bank: QuestionBank,
) -> None:
    """Validate the public profile against every upstream public artifact."""

    validate_phase4_protocol_against_bank_profile(protocol, bank_profile)
    if (
        profile.bank_profile_id,
        profile.bank_profile_version,
        profile.bank_profile_sha256,
    ) != (
        bank_profile.profile_id,
        bank_profile.profile_version,
        content_sha256(bank_profile),
    ):
        raise ValueError(
            "semantic-map authoring profile does not bind the bank profile"
        )
    if (
        profile.phase4_protocol_id,
        profile.phase4_protocol_version,
        profile.phase4_protocol_sha256,
    ) != (
        protocol.protocol_id,
        protocol.protocol_version,
        content_sha256(protocol),
    ):
        raise ValueError(
            "semantic-map authoring profile does not bind the Phase 4 protocol"
        )
    ontology_payload = ontology_definition_payload(question_bank)
    item_ids = [item["item_id"] for item in ontology_payload]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("semantic-map ontology item ids must be unique")
    if (
        profile.ontology.ontology_id,
        profile.ontology.ontology_version,
        profile.ontology.item_ids,
        profile.ontology.item_ids_sha256,
        profile.ontology_definitions_sha256,
    ) != (
        "preference_seed_items",
        1,
        item_ids,
        content_sha256(item_ids),
        content_sha256(ontology_payload),
    ):
        raise ValueError(
            "semantic-map authoring profile does not bind the exact ontology"
        )
    if profile.expected_measure_count != len(bank_profile.slots):
        raise ValueError(
            "semantic-map expected measure count does not match bank profile"
        )
    exposure = bank_profile.case_study_exposure_policy
    if not review_system_matches(
        profile.author_system,
        exposure.packet_author_system,
    ) or not review_system_matches(
        profile.ai_reviewer_system,
        exposure.content_reviewer_system,
    ):
        raise ValueError(
            "semantic-map author and reviewer must match the exposure policy"
        )
    if (
        profile.participant_receives_nonrevealing_summary_only
        != exposure.participant_receives_nonrevealing_review_summary_only
        or profile.human_content_review_required_before_external_pilot
        != exposure.human_content_review_required_before_external_pilot
    ):
        raise ValueError(
            "semantic-map review rules must match the exposure policy"
        )


def validate_semantic_map_authoring_bundle(
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
    fixture: EvaluationFixture,
) -> None:
    """Validate restricted rationales against exact packets and public rules."""

    if (
        bundle.authoring_profile_id,
        bundle.authoring_profile_version,
        bundle.authoring_profile_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
    ):
        raise ValueError(
            "semantic-map authoring bundle does not bind the public profile"
        )
    if (
        bundle.fixture_id,
        bundle.fixture_version,
        bundle.fixture_sha256,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
    ):
        raise ValueError(
            "semantic-map authoring bundle does not bind the exact fixture"
        )
    if not review_system_matches(bundle.author_system, profile.author_system):
        raise ValueError("semantic-map author does not match the public profile")
    if len(bundle.measure_records) != profile.expected_measure_count:
        raise ValueError(
            "semantic-map authoring bundle has the wrong measure count"
        )

    expected_measure_refs = [
        (measure.measure_id, measure.version) for measure in fixture.measures
    ]
    actual_measure_refs = [
        (record.measure_id, record.measure_version)
        for record in bundle.measure_records
    ]
    if actual_measure_refs != expected_measure_refs:
        raise ValueError(
            "semantic-map authoring records must follow fixture order"
        )

    known_dimensions = set(profile.ontology.item_ids)
    for record, measure in zip(
        bundle.measure_records,
        fixture.measures,
        strict=True,
    ):
        if (
            record.packet_version,
            record.packet_sha256,
        ) != (
            measure.packet.version,
            content_sha256(measure.packet),
        ):
            raise ValueError(
                "semantic-map authoring record does not bind the exact packet"
            )
        expected_option_ids = [option.option_id for option in measure.options]
        measure_document = measure.model_dump(mode="json")
        for assignment in record.dimension_assignments:
            if assignment.dimension_id not in known_dimensions:
                raise ValueError(
                    "semantic-map assignment uses an unknown dimension"
                )
            actual_option_ids = [
                item.option_id for item in assignment.option_positions
            ]
            if actual_option_ids != expected_option_ids:
                raise ValueError(
                    "semantic-map option positions must follow display order"
                )
            for position in assignment.option_positions:
                for path in position.supporting_content_paths:
                    if not is_participant_text_pointer(path):
                        raise ValueError(
                            "semantic-map support must name a participant-"
                            "facing packet field"
                        )
                    value = resolve_json_pointer(measure_document, path)
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            "semantic-map support path must resolve to text"
                        )


def _derived_dimension_weights(
    assignment: SemanticDimensionAssignment,
    profile: SemanticMapAuthoringProfile,
) -> dict[str, float]:
    positions = [
        float(item.ordinal_position) for item in assignment.option_positions
    ]
    mean_position = math.fsum(positions) / len(positions)
    centered = [position - mean_position for position in positions]
    max_absolute = max(abs(value) for value in centered)
    importance = profile.importance_weights[assignment.importance]
    return {
        item.option_id: (value / max_absolute) * importance
        for item, value in zip(
            assignment.option_positions,
            centered,
            strict=True,
        )
        if value != 0.0
    }


def build_authored_semantic_map(
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
    fixture: EvaluationFixture,
) -> AuthoredSemanticMapBundle:
    """Derive the exact runtime map from the coarse restricted rationale."""

    validate_semantic_map_authoring_bundle(bundle, profile, fixture)
    mappings = []
    for record, measure in zip(
        bundle.measure_records,
        fixture.measures,
        strict=True,
    ):
        weights_by_option: dict[str, dict[str, float]] = {
            option.option_id: {} for option in measure.options
        }
        for assignment in record.dimension_assignments:
            for option_id, weight in _derived_dimension_weights(
                assignment,
                profile,
            ).items():
                weights_by_option[option_id][assignment.dimension_id] = weight
        mappings.append(
            AuthoredMeasureSemanticMapping(
                measure_id=record.measure_id,
                measure_version=record.measure_version,
                packet_version=record.packet_version,
                packet_sha256=record.packet_sha256,
                option_stances=[
                    AuthoredOptionStance(
                        option_id=option.option_id,
                        dimension_weights=weights_by_option[option.option_id],
                    )
                    for option in measure.options
                ],
            )
        )
    semantic_map = AuthoredSemanticMapBundle(
        mapper_id=bundle.mapper_id,
        mapper_version=bundle.mapper_version,
        development_only=fixture.development_only,
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        ontology=profile.ontology,
        author_system=bundle.author_system,
        authored_at=bundle.authored_at,
        mappings=mappings,
    )
    validate_authored_semantic_map(
        semantic_map,
        fixture,
        profile.ontology,
    )
    return semantic_map


def validate_semantic_map_artifacts(
    semantic_map: AuthoredSemanticMapBundle,
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
    fixture: EvaluationFixture,
) -> None:
    """Fail closed unless the runtime map is the exact deterministic output."""

    expected = build_authored_semantic_map(bundle, profile, fixture)
    if semantic_map != expected:
        raise ValueError(
            "semantic map does not match the exact derived authoring bundle"
        )


def validate_locked_semantic_review_prompt() -> None:
    actual = canonical_text_sha256(PHASE4_SEMANTIC_REVIEW_PROMPT_PATH)
    if actual != PHASE4_SEMANTIC_REVIEW_PROMPT_SHA256:
        raise ValueError(
            "Phase 4 semantic-review prompt does not match its locked v1 hash"
        )


def validate_semantic_map_review_log(
    log: SemanticMapReviewLog,
    semantic_map: AuthoredSemanticMapBundle,
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
    fixture: EvaluationFixture,
) -> None:
    """Validate exact approvals, reviewer independence, and prompt provenance."""

    validate_semantic_map_artifacts(semantic_map, bundle, profile, fixture)
    if (
        log.authoring_profile_id,
        log.authoring_profile_version,
        log.authoring_profile_sha256,
        log.fixture_id,
        log.fixture_version,
        log.fixture_sha256,
        log.authoring_bundle_id,
        log.authoring_bundle_version,
        log.authoring_bundle_sha256,
        log.mapper_id,
        log.mapper_version,
        log.mapper_sha256,
    ) != (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
        bundle.bundle_id,
        bundle.bundle_version,
        content_sha256(bundle),
        semantic_map.mapper_id,
        semantic_map.mapper_version,
        content_sha256(semantic_map),
    ):
        raise ValueError(
            "semantic-map review log does not bind the exact artifacts"
        )
    if review_system_matches(log.reviewer_system, bundle.author_system):
        raise ValueError(
            "semantic-map reviewer must differ from the mapping author"
        )
    if log.reviewer_type is ReviewActorType.AI:
        if not review_system_matches(
            log.reviewer_system,
            profile.ai_reviewer_system,
        ):
            raise ValueError(
                "AI semantic-map reviewer does not match the public profile"
            )
        validate_locked_semantic_review_prompt()
        if log.review_prompt_sha256 != PHASE4_SEMANTIC_REVIEW_PROMPT_SHA256:
            raise ValueError(
                "AI semantic-map review does not use the locked v1 prompt"
            )

    mapping_by_ref = {
        (mapping.measure_id, mapping.measure_version): mapping
        for mapping in semantic_map.mappings
    }
    approval_by_ref = {
        (approval.measure_id, approval.measure_version): approval
        for approval in log.measure_approvals
    }
    if list(approval_by_ref) != list(mapping_by_ref):
        raise ValueError(
            "semantic-map review must approve every mapping in fixture order"
        )
    for measure_ref, approval in approval_by_ref.items():
        if approval.mapping_sha256 != content_sha256(
            mapping_by_ref[measure_ref]
        ):
            raise ValueError(
                "semantic-map approval does not bind the exact mapping"
            )
    known_dimensions = set(profile.ontology.item_ids)
    if any(
        finding.dimension_id is not None
        and finding.dimension_id not in known_dimensions
        for finding in log.findings
    ):
        raise ValueError(
            "semantic-map finding references an unknown dimension"
        )


def semantic_map_authoring_profile_summary(
    profile: SemanticMapAuthoringProfile,
) -> dict[str, object]:
    return {
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "profile_sha256": content_sha256(profile),
        "expected_measure_count": profile.expected_measure_count,
        "ontology_dimension_count": len(profile.ontology.item_ids),
        "importance_tier_count": len(profile.importance_weights),
        "review_check_count": len(profile.required_review_checks),
        "participant_blinded": (
            profile.participant_blind_to_exact_mapping_until_completion
        ),
        "exact_mapping_content_omitted": True,
    }


def semantic_map_authoring_summary(
    semantic_map: AuthoredSemanticMapBundle,
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
) -> dict[str, object]:
    base = authored_semantic_map_summary(semantic_map)
    return {
        **base,
        "authoring_profile_sha256": content_sha256(profile),
        "authoring_bundle_sha256": content_sha256(bundle),
        "dimension_assignment_count": sum(
            len(record.dimension_assignments)
            for record in bundle.measure_records
        ),
        "restricted_rationales_omitted": True,
    }


def build_nonrevealing_semantic_map_review_summary(
    log: SemanticMapReviewLog,
    semantic_map: AuthoredSemanticMapBundle,
    bundle: SemanticMapAuthoringBundle,
    profile: SemanticMapAuthoringProfile,
    fixture: EvaluationFixture,
) -> NonrevealingSemanticMapReviewSummary:
    validate_semantic_map_review_log(
        log,
        semantic_map,
        bundle,
        profile,
        fixture,
    )
    category_counts = Counter(item.category for item in log.findings)
    severity_counts = Counter(item.severity for item in log.findings)
    disposition_counts = Counter(item.disposition for item in log.findings)
    used_dimensions = {
        assignment.dimension_id
        for record in bundle.measure_records
        for assignment in record.dimension_assignments
    }
    return NonrevealingSemanticMapReviewSummary(
        summary_id=f"{log.log_id}_summary",
        authoring_profile_id=profile.profile_id,
        authoring_profile_version=profile.profile_version,
        authoring_profile_sha256=content_sha256(profile),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        authoring_bundle_sha256=content_sha256(bundle),
        mapper_id=semantic_map.mapper_id,
        mapper_version=semantic_map.mapper_version,
        mapper_sha256=content_sha256(semantic_map),
        review_log_id=log.log_id,
        review_log_version=log.log_version,
        review_log_sha256=content_sha256(log),
        reviewer_type=log.reviewer_type,
        reviewer_system=log.reviewer_system,
        reviewer_model_version=log.reviewer_model_version,
        review_prompt_sha256=log.review_prompt_sha256,
        reviewed_measure_count=len(semantic_map.mappings),
        reviewed_option_count=sum(
            len(mapping.option_stances) for mapping in semantic_map.mappings
        ),
        used_dimension_count=len(used_dimensions),
        dimension_assignment_count=sum(
            len(record.dimension_assignments)
            for record in bundle.measure_records
        ),
        findings_count=len(log.findings),
        findings_by_category={
            category: category_counts[category]
            for category in SemanticMapReviewCategory
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


def reviewed_semantic_mapper_reference(
    summary: NonrevealingSemanticMapReviewSummary,
) -> ReviewedSemanticMapperReference:
    """Build the exact aggregate-safe mapper approval stored on final runs."""

    return ReviewedSemanticMapperReference(
        semantic_mapper=ComponentArtifactReference(
            artifact_id=summary.mapper_id,
            artifact_version=str(summary.mapper_version),
            artifact_sha256=summary.mapper_sha256,
        ),
        authoring_profile_id=summary.authoring_profile_id,
        authoring_profile_version=summary.authoring_profile_version,
        authoring_profile_sha256=summary.authoring_profile_sha256,
        review_log_id=summary.review_log_id,
        review_log_version=summary.review_log_version,
        review_log_sha256=summary.review_log_sha256,
        review_summary_id=summary.summary_id,
        review_summary_sha256=content_sha256(summary),
        reviewer_type=summary.reviewer_type,
        reviewer_system=summary.reviewer_system,
        reviewer_model_version=summary.reviewer_model_version,
        review_prompt_sha256=summary.review_prompt_sha256,
        approved_measure_count=summary.reviewed_measure_count,
        all_mappings_approved=True,
    )


def validate_final_semantic_map_authoring_inputs(
    profile: SemanticMapAuthoringProfile,
    bank_profile: EvaluationBankProfile,
    protocol: Phase4Protocol,
    question_bank: QuestionBank,
    fixture: EvaluationFixture,
) -> None:
    """Validate every public precommitment before restricted work is consumed."""

    validate_semantic_map_authoring_profile(
        profile,
        bank_profile,
        protocol,
        question_bank,
    )
    validate_final_fixture_against_profile(fixture, bank_profile)
