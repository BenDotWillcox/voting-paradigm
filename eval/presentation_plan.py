"""Deterministic Phase 3C presentation planning and run validation.

The plan is content-bearing because it identifies exact measures, variants,
and option orders. Keep real-participant plans in the restricted authoring
tree until the blinded protocol is complete.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Literal, Self, TypeVar

from pydantic import Field, field_validator, model_validator

from .bank_profile import (
    EvaluationBankProfile,
    RetestVariantRegistry,
    validate_final_fixture_against_profile,
    validate_retest_registry_against_bank,
)
from .contracts import (
    ContractModel,
    EvaluationFixture,
    EvaluationRun,
    MeasureDomain,
    MeasureVersion,
    PresentationKind,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256, validate_run_against_fixture

OrderValue = TypeVar("OrderValue")


def _seeded_digest(seed: int, namespace: str, identity: str) -> bytes:
    payload = json.dumps(
        [seed, namespace, identity],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()


def _seeded_order(
    values: list[OrderValue],
    *,
    seed: int,
    namespace: str,
    identity: Callable[[OrderValue], str],
) -> list[OrderValue]:
    return sorted(
        values,
        key=lambda value: (
            _seeded_digest(seed, namespace, identity(value)),
            identity(value),
        ),
    )


def _derived_seed(seed: int, namespace: str, identity: str) -> int:
    digest = _seeded_digest(seed, namespace, identity)
    return int.from_bytes(digest[:8], "big") % (2**31)


def _measure_ref(measure: MeasureVersion) -> str:
    return f"{measure.measure_id}@{measure.version}"


class PlannedInitialPresentation(ContractModel):
    """One canonical presentation in the frozen six-wave order."""

    record_version: Literal["planned_initial_presentation.v1"] = (
        "planned_initial_presentation.v1"
    )
    plan_entry_id: StableId
    measure_id: StableId
    measure_version: PositiveVersion
    packet_version: PositiveVersion
    wave_index: int = Field(ge=0)
    position_in_wave: int = Field(ge=0)
    option_order_seed: int = Field(ge=0)
    ordered_option_ids: list[StableId] = Field(min_length=2)

    @field_validator("ordered_option_ids")
    @classmethod
    def option_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("planned option ids must be unique")
        return value


class PlannedRetestPresentation(ContractModel):
    """One alternate packet and option order for a later retest."""

    record_version: Literal["planned_retest_presentation.v1"] = (
        "planned_retest_presentation.v1"
    )
    plan_entry_id: StableId
    variant_id: StableId
    source_measure_id: StableId
    source_measure_version: PositiveVersion
    packet_version: PositiveVersion
    source_initial_plan_entry_id: StableId
    option_order_seed: int = Field(ge=0)
    ordered_option_ids: list[StableId] = Field(min_length=2)

    @field_validator("ordered_option_ids")
    @classmethod
    def option_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("planned option ids must be unique")
        return value


class EvaluationPresentationPlan(ContractModel):
    """Frozen initial waves, retest links, and per-presentation option order."""

    schema_version: Literal["preference_eval_presentation_plan.v1"] = (
        "preference_eval_presentation_plan.v1"
    )
    plan_id: StableId
    plan_version: PositiveVersion
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
    order_seed: int = Field(ge=0)
    initial_presentations: list[PlannedInitialPresentation] = Field(
        min_length=48,
        max_length=48,
    )
    retest_presentations: list[PlannedRetestPresentation] = Field(
        min_length=12,
        max_length=12,
    )

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
    def require_unique_plan_bindings(self) -> Self:
        entry_ids = [
            entry.plan_entry_id
            for entry in [
                *self.initial_presentations,
                *self.retest_presentations,
            ]
        ]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("presentation-plan entry ids must be unique")
        initial_refs = [
            (entry.measure_id, entry.measure_version)
            for entry in self.initial_presentations
        ]
        if len(initial_refs) != len(set(initial_refs)):
            raise ValueError(
                "initial presentation measure references must be unique"
            )
        wave_positions = [
            (entry.wave_index, entry.position_in_wave)
            for entry in self.initial_presentations
        ]
        if len(wave_positions) != len(set(wave_positions)):
            raise ValueError("initial wave positions must be unique")
        variant_ids = [
            entry.variant_id for entry in self.retest_presentations
        ]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("planned retest variant ids must be unique")
        return self


class CompletedRunValidationManifest(ContractModel):
    """Hash-bound proof that a completed run followed one frozen plan."""

    schema_version: Literal["preference_eval_run_validation.v1"] = (
        "preference_eval_run_validation.v1"
    )
    run_id: StableId
    run_sha256: Sha256Digest
    plan_id: StableId
    plan_version: PositiveVersion
    plan_sha256: Sha256Digest
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    retest_registry_id: StableId
    retest_registry_version: PositiveVersion
    retest_registry_sha256: Sha256Digest
    validated_at: datetime
    initial_presentation_count: Literal[48] = 48
    retest_presentation_count: Literal[12] = 12
    wave_membership_valid: Literal[True] = True
    option_order_seeds_valid: Literal[True] = True
    retest_timing_valid: Literal[True] = True

    @field_validator("validated_at")
    @classmethod
    def validated_at_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validated_at must include a timezone")
        return value


def load_presentation_plan(path: str | Path) -> EvaluationPresentationPlan:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvaluationPresentationPlan.model_validate(raw)


def option_order_for_seed(
    measure: MeasureVersion,
    *,
    seed: int,
    namespace: str,
) -> list[str]:
    """Return the cross-runtime stable option order recorded in a plan."""

    return _seeded_order(
        [option.option_id for option in measure.options],
        seed=seed,
        namespace=namespace,
        identity=lambda option_id: option_id,
    )


def build_presentation_plan(
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    *,
    plan_id: str,
    plan_version: int,
    created_at: datetime,
) -> EvaluationPresentationPlan:
    """Build the deterministic plan frozen by the Phase 3A order policy."""

    validate_final_fixture_against_profile(fixture, profile)
    validate_retest_registry_against_bank(registry, fixture, profile)
    policy = profile.presentation_order_policy
    measures_by_domain = {
        domain: [
            measure for measure in fixture.measures if measure.domain is domain
        ]
        for domain in MeasureDomain
    }
    assigned_by_domain = {
        domain: _seeded_order(
            measures,
            seed=policy.order_seed,
            namespace=f"initial-wave:{domain.value}",
            identity=_measure_ref,
        )
        for domain, measures in measures_by_domain.items()
    }
    if any(
        len(measures) != policy.wave_count
        for measures in assigned_by_domain.values()
    ):
        raise ValueError(
            "seeded stratification requires one measure per domain per wave"
        )

    initial_presentations: list[PlannedInitialPresentation] = []
    for wave_index in range(policy.wave_count):
        wave_measures = [
            assigned_by_domain[domain][wave_index]
            for domain in MeasureDomain
        ]
        ordered_wave = _seeded_order(
            wave_measures,
            seed=policy.order_seed,
            namespace=f"initial-position:{wave_index}",
            identity=_measure_ref,
        )
        for position_in_wave, measure in enumerate(ordered_wave):
            identity = _measure_ref(measure)
            option_seed = _derived_seed(
                policy.order_seed,
                "initial-option-order",
                identity,
            )
            initial_presentations.append(
                PlannedInitialPresentation(
                    plan_entry_id=(
                        f"initial_w{wave_index + 1:02d}_"
                        f"p{position_in_wave + 1:02d}"
                    ),
                    measure_id=measure.measure_id,
                    measure_version=measure.version,
                    packet_version=measure.packet.version,
                    wave_index=wave_index,
                    position_in_wave=position_in_wave,
                    option_order_seed=option_seed,
                    ordered_option_ids=option_order_for_seed(
                        measure,
                        seed=option_seed,
                        namespace="initial-options",
                    ),
                )
            )

    initial_by_ref = {
        (entry.measure_id, entry.measure_version): entry
        for entry in initial_presentations
    }
    measure_by_ref = {
        (measure.measure_id, measure.version): measure
        for measure in fixture.measures
    }
    ordered_variants = _seeded_order(
        list(registry.variants),
        seed=policy.order_seed,
        namespace="retest-registry-order",
        identity=lambda variant: variant.variant_id,
    )
    retest_presentations: list[PlannedRetestPresentation] = []
    for index, variant in enumerate(ordered_variants):
        measure_ref = (
            variant.source_measure_id,
            variant.source_measure_version,
        )
        measure = measure_by_ref[measure_ref]
        initial = initial_by_ref[measure_ref]
        attempt = 0
        while True:
            option_seed = _derived_seed(
                policy.order_seed,
                "retest-option-order",
                f"{variant.variant_id}:{attempt}",
            )
            option_order = option_order_for_seed(
                measure,
                seed=option_seed,
                namespace="retest-options",
            )
            if option_order != initial.ordered_option_ids:
                break
            attempt += 1
        retest_presentations.append(
            PlannedRetestPresentation(
                plan_entry_id=f"retest_{index + 1:02d}",
                variant_id=variant.variant_id,
                source_measure_id=variant.source_measure_id,
                source_measure_version=variant.source_measure_version,
                packet_version=variant.packet.version,
                source_initial_plan_entry_id=initial.plan_entry_id,
                option_order_seed=option_seed,
                ordered_option_ids=option_order,
            )
        )

    return EvaluationPresentationPlan(
        plan_id=plan_id,
        plan_version=plan_version,
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
        order_seed=policy.order_seed,
        initial_presentations=initial_presentations,
        retest_presentations=retest_presentations,
    )


def validate_presentation_plan_against_bundle(
    plan: EvaluationPresentationPlan,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
) -> None:
    """Validate exact bindings and reproduce every deterministic plan entry."""

    expected_bindings = (
        plan.profile_id,
        plan.profile_version,
        plan.profile_sha256,
        plan.fixture_id,
        plan.fixture_version,
        plan.fixture_sha256,
        plan.retest_registry_id,
        plan.retest_registry_version,
        plan.retest_registry_sha256,
        plan.order_seed,
    )
    actual_bindings = (
        profile.profile_id,
        profile.profile_version,
        content_sha256(profile),
        fixture.fixture_id,
        fixture.fixture_version,
        content_sha256(fixture),
        registry.registry_id,
        registry.registry_version,
        content_sha256(registry),
        profile.presentation_order_policy.order_seed,
    )
    if expected_bindings != actual_bindings:
        raise ValueError(
            "presentation plan does not match the frozen evaluation bundle"
        )
    expected = build_presentation_plan(
        fixture,
        profile,
        registry,
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        created_at=plan.created_at,
    )
    if plan != expected:
        raise ValueError(
            "presentation plan entries do not match the deterministic policy"
        )


def _validate_run_against_plan(
    run: EvaluationRun,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    plan: EvaluationPresentationPlan,
    *,
    require_complete: bool,
) -> None:
    validate_presentation_plan_against_bundle(
        plan,
        fixture,
        profile,
        registry,
    )
    validate_run_against_fixture(
        run,
        fixture,
        retest_variants=registry.variants,
    )

    expected_initial_refs = [
        (entry.measure_id, entry.measure_version)
        for entry in plan.initial_presentations
    ]
    initial_plan_by_ref = {
        (entry.measure_id, entry.measure_version): entry
        for entry in plan.initial_presentations
    }
    retest_plan_by_ref = {
        (
            entry.source_measure_id,
            entry.source_measure_version,
            entry.packet_version,
        ): entry
        for entry in plan.retest_presentations
    }
    actual_initials = [
        presentation
        for presentation in run.measure_presentations
        if presentation.kind is PresentationKind.INITIAL
    ]
    actual_retests = [
        presentation
        for presentation in run.measure_presentations
        if presentation.kind is PresentationKind.RETEST
    ]
    actual_initial_refs = [
        (presentation.measure_id, presentation.measure_version)
        for presentation in actual_initials
    ]
    if actual_initial_refs != expected_initial_refs[: len(actual_initials)]:
        raise ValueError(
            "initial presentations do not follow the frozen wave order"
        )
    for previous, current in zip(actual_initials, actual_initials[1:]):
        if current.presented_at < previous.presented_at:
            raise ValueError(
                "initial presentation times do not follow the frozen order"
            )
    for presentation in actual_initials:
        planned = initial_plan_by_ref[
            (presentation.measure_id, presentation.measure_version)
        ]
        if (
            presentation.packet_version,
            presentation.order_seed,
        ) != (
            planned.packet_version,
            planned.option_order_seed,
        ):
            raise ValueError(
                "initial presentation does not match its planned packet and "
                "option-order seed"
            )

    seen_retest_refs: set[tuple[str, int, int]] = set()
    presentation_by_id = {
        presentation.presentation_id: presentation
        for presentation in run.measure_presentations
    }
    response_by_presentation_id = {
        response.presentation_id: response
        for response in run.participant_responses
    }
    minimum_interval = timedelta(days=profile.retest_target.interval_min_days)
    maximum_interval = timedelta(days=profile.retest_target.interval_max_days)
    for presentation in actual_retests:
        retest_ref = (
            presentation.measure_id,
            presentation.measure_version,
            presentation.packet_version,
        )
        if retest_ref in seen_retest_refs:
            raise ValueError("run contains a duplicate planned retest")
        seen_retest_refs.add(retest_ref)
        planned = retest_plan_by_ref.get(retest_ref)
        if planned is None:
            raise ValueError("run contains a retest outside the frozen plan")
        if presentation.order_seed != planned.option_order_seed:
            raise ValueError(
                "retest presentation does not match its option-order seed"
            )
        original = presentation_by_id[
            presentation.retest_of_presentation_id or ""
        ]
        elapsed = presentation.presented_at - original.presented_at
        if elapsed < minimum_interval or elapsed > maximum_interval:
            raise ValueError(
                "retest presentation falls outside the frozen interval"
            )
        original_response = response_by_presentation_id.get(
            original.presentation_id
        )
        if original_response is None:
            raise ValueError(
                "retest presentation requires the original response"
            )
        if original_response.created_at > presentation.presented_at:
            raise ValueError(
                "retest presentation must follow the original response"
            )
        retest_response = response_by_presentation_id.get(
            presentation.presentation_id
        )
        if (
            retest_response is not None
            and retest_response.sequence <= original_response.sequence
        ):
            raise ValueError(
                "retest response must follow its original response"
            )

    ordered_responses = sorted(
        run.participant_responses,
        key=lambda response: response.sequence,
    )
    initial_response_refs = [
        (response.measure_id, response.measure_version)
        for response in ordered_responses
        if presentation_by_id[response.presentation_id].kind
        is PresentationKind.INITIAL
    ]
    if initial_response_refs != expected_initial_refs[: len(initial_response_refs)]:
        raise ValueError(
            "initial responses do not follow the frozen wave order"
        )

    if not require_complete:
        return
    if len(actual_initials) != len(plan.initial_presentations):
        raise ValueError("completed run must contain every initial presentation")
    if len(actual_retests) != len(plan.retest_presentations):
        raise ValueError("completed run must contain every retest presentation")
    if len(run.participant_responses) != len(run.measure_presentations):
        raise ValueError("completed run requires one response per presentation")


def validate_run_progress_against_plan(
    run: EvaluationRun,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    plan: EvaluationPresentationPlan,
) -> None:
    """Validate any realized prefix without claiming the run is complete."""

    _validate_run_against_plan(
        run,
        fixture,
        profile,
        registry,
        plan,
        require_complete=False,
    )


def validate_completed_run_against_plan(
    run: EvaluationRun,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    plan: EvaluationPresentationPlan,
) -> None:
    """Require all 48 initials, 12 retests, order seeds, and timing windows."""

    _validate_run_against_plan(
        run,
        fixture,
        profile,
        registry,
        plan,
        require_complete=True,
    )


def build_completed_run_validation_manifest(
    run: EvaluationRun,
    fixture: EvaluationFixture,
    profile: EvaluationBankProfile,
    registry: RetestVariantRegistry,
    plan: EvaluationPresentationPlan,
    *,
    validated_at: datetime,
) -> CompletedRunValidationManifest:
    validate_completed_run_against_plan(
        run,
        fixture,
        profile,
        registry,
        plan,
    )
    return CompletedRunValidationManifest(
        run_id=run.run_id,
        run_sha256=content_sha256(run),
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        plan_sha256=content_sha256(plan),
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=content_sha256(fixture),
        retest_registry_id=registry.registry_id,
        retest_registry_version=registry.registry_version,
        retest_registry_sha256=content_sha256(registry),
        validated_at=validated_at,
    )
