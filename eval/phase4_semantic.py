"""Reviewed authored option-to-value mappings for Phase 4D.

The fixed-bank classical baselines cannot infer how a new ballot option bears
on the preference ontology from the participant's answers alone.  This module
therefore treats that bridge as a separate, versioned artifact.  The mapping
binds the exact fixture, packet, fixed ontology, and option set; it contains no
participant evidence or posterior state.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

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
from .phase4_prediction import ComponentArtifactReference

StanceWeight = Annotated[
    float,
    Field(ge=-1.0, le=1.0, allow_inf_nan=False),
]


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class AuthoredOptionStance(ContractModel):
    """Sparse relative stance of one option on the fixed value ontology."""

    record_version: Literal["phase4_authored_option_stance.v1"] = (
        "phase4_authored_option_stance.v1"
    )
    option_id: StableId
    dimension_weights: dict[StableId, StanceWeight] = Field(default_factory=dict)

    @field_validator("dimension_weights")
    @classmethod
    def explicit_zero_weights_are_not_canonical(
        cls,
        value: dict[str, float],
    ) -> dict[str, float]:
        if any(weight == 0.0 for weight in value.values()):
            raise ValueError("zero stance weights must be omitted")
        return value


class AuthoredMeasureSemanticMapping(ContractModel):
    """Exact option stance vectors for one versioned measure packet."""

    record_version: Literal["phase4_authored_measure_mapping.v1"] = (
        "phase4_authored_measure_mapping.v1"
    )
    measure_id: StableId
    measure_version: PositiveVersion
    packet_version: PositiveVersion
    packet_sha256: Sha256Digest
    option_stances: list[AuthoredOptionStance] = Field(min_length=2)

    @model_validator(mode="after")
    def option_ids_must_be_unique(self) -> Self:
        _require_unique(
            [item.option_id for item in self.option_stances],
            "authored option stance ids",
        )
        return self


class AuthoredSemanticMapBundle(ContractModel):
    """One reviewable authored mapper for an exact fixture and ontology."""

    schema_version: Literal["phase4_authored_semantic_map.v1"] = (
        "phase4_authored_semantic_map.v1"
    )
    mapper_id: StableId
    mapper_version: PositiveVersion
    development_only: bool
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    ontology: FixedOntologyReference
    author_system: NonEmptyText
    authored_at: datetime
    mappings: list[AuthoredMeasureSemanticMapping] = Field(min_length=1)

    @field_validator("authored_at")
    @classmethod
    def authored_at_must_be_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "authored_at")

    @model_validator(mode="after")
    def measure_bindings_must_be_unique(self) -> Self:
        _require_unique(
            [
                f"{item.measure_id}@{item.measure_version}"
                for item in self.mappings
            ],
            "authored measure mappings",
        )
        return self


def semantic_map_artifact_reference(
    bundle: AuthoredSemanticMapBundle,
) -> ComponentArtifactReference:
    """Return the exact component reference stored on a model configuration."""

    return ComponentArtifactReference(
        artifact_id=bundle.mapper_id,
        artifact_version=str(bundle.mapper_version),
        artifact_sha256=content_sha256(bundle),
    )


def load_authored_semantic_map(path: Path) -> AuthoredSemanticMapBundle:
    """Load one strict semantic-map artifact from JSON."""

    return AuthoredSemanticMapBundle.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def authored_semantic_map_summary(
    bundle: AuthoredSemanticMapBundle,
) -> dict[str, object]:
    """Return aggregate-only metadata safe for validator output."""

    used_dimensions = {
        dimension_id
        for mapping in bundle.mappings
        for stance in mapping.option_stances
        for dimension_id in stance.dimension_weights
    }
    return {
        "schema_version": bundle.schema_version,
        "mapper_id": bundle.mapper_id,
        "mapper_version": bundle.mapper_version,
        "mapper_sha256": content_sha256(bundle),
        "development_only": bundle.development_only,
        "measure_count": len(bundle.mappings),
        "option_count": sum(
            len(mapping.option_stances) for mapping in bundle.mappings
        ),
        "ontology_dimension_count": len(bundle.ontology.item_ids),
        "used_dimension_count": len(used_dimensions),
        "nonzero_weight_count": sum(
            len(stance.dimension_weights)
            for mapping in bundle.mappings
            for stance in mapping.option_stances
        ),
        "participant_content_omitted": True,
    }


def validate_authored_semantic_map(
    bundle: AuthoredSemanticMapBundle,
    fixture: EvaluationFixture,
    ontology: FixedOntologyReference,
) -> None:
    """Validate the complete mapper against its fixture and fixed ontology."""

    if (
        bundle.fixture_id,
        bundle.fixture_version,
        bundle.fixture_sha256,
        bundle.development_only,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
        fixture.development_only,
    ):
        raise ValueError("authored semantic map does not bind the exact fixture")
    if bundle.ontology != ontology:
        raise ValueError("authored semantic map does not bind the exact ontology")

    expected_measure_keys = [
        (measure.measure_id, measure.version) for measure in fixture.measures
    ]
    actual_measure_keys = [
        (mapping.measure_id, mapping.measure_version)
        for mapping in bundle.mappings
    ]
    if actual_measure_keys != expected_measure_keys:
        raise ValueError(
            "authored mappings must follow the exact fixture measure order"
        )

    known_dimensions = set(ontology.item_ids)
    for mapping, measure in zip(bundle.mappings, fixture.measures, strict=True):
        if (
            mapping.packet_version,
            mapping.packet_sha256,
        ) != (
            measure.packet.version,
            content_sha256(measure.packet),
        ):
            raise ValueError("authored mapping packet binding does not match")

        expected_option_ids = [option.option_id for option in measure.options]
        actual_option_ids = [item.option_id for item in mapping.option_stances]
        if actual_option_ids != expected_option_ids:
            raise ValueError(
                "authored option stances must follow exact measure display order"
            )

        used_dimensions = {
            dimension_id
            for stance in mapping.option_stances
            for dimension_id in stance.dimension_weights
        }
        unknown_dimensions = used_dimensions - known_dimensions
        if unknown_dimensions:
            raise ValueError("authored mapping contains an unknown dimension")

        for dimension_id in used_dimensions:
            centered_sum = sum(
                stance.dimension_weights.get(dimension_id, 0.0)
                for stance in mapping.option_stances
            )
            if not math.isclose(
                centered_sum,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    "authored stance weights must be option-centered"
                )

        dense_vectors = [
            tuple(
                stance.dimension_weights.get(dimension_id, 0.0)
                for dimension_id in ontology.item_ids
            )
            for stance in mapping.option_stances
        ]
        if len(set(dense_vectors)) == 1:
            raise ValueError(
                "authored mapping must encode at least one option contrast"
            )


def semantic_mapping_for_measure(
    bundle: AuthoredSemanticMapBundle,
    measure_id: str,
    measure_version: int,
) -> AuthoredMeasureSemanticMapping:
    """Resolve one exact mapping, failing closed on a missing target."""

    for mapping in bundle.mappings:
        if (
            mapping.measure_id,
            mapping.measure_version,
        ) == (measure_id, measure_version):
            return mapping
    raise ValueError("authored semantic map has no mapping for the target")
