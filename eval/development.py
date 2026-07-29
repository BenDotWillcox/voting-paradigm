"""Versioned development inputs for the Phase 2 human-measure runner."""

from __future__ import annotations

from pathlib import Path

from .contracts import EvaluationFixture, ModelConfiguration
from .fixture_io import (
    content_sha256,
    load_fixture,
    validate_development_fixture,
)
from .prequential import (
    PrequentialSessionScript,
    PredictionModelAdapter,
    ScriptedPredictionAdapter,
    UniformPredictionAdapter,
    load_session_script,
    validate_session_script_against_fixture,
)
from .public_artifact import PublicModelDescriptor

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "preference_eval_dev_v1.json"
)
SESSION_SCRIPT_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "preference_eval_dev_session_v1.json"
)


def load_development_inputs() -> tuple[
    EvaluationFixture,
    PrequentialSessionScript,
]:
    fixture = load_fixture(FIXTURE_PATH)
    validate_development_fixture(fixture)
    script = load_session_script(SESSION_SCRIPT_PATH)
    validate_session_script_against_fixture(script, fixture)
    return fixture, script


def build_development_adapters(
    fixture: EvaluationFixture,
) -> list[PredictionModelAdapter]:
    """Return a real null baseline and an explicitly test-only adapter."""

    scripted_probabilities = {
        "dev_fiscal_reserve": {
            "increase_reserve": 0.8,
            "retain_program_funding": 0.2,
        },
        "dev_health_mobile_clinics": {
            "fund_mobile_clinics": 0.3,
            "maintain_current_grants": 0.7,
        },
        "dev_education_calendar": {
            "traditional_calendar": 0.25,
            "balanced_calendar": 0.6,
            "local_choice": 0.15,
        },
        "dev_housing_zoning_tools": {
            "accessory_units": 0.15,
            "transit_density": 0.55,
            "vacancy_fee": 0.2,
            "retain_local_rules": 0.1,
        },
        "dev_transport_investment": {
            "road_repairs": 0.35,
            "bus_frequency": 0.1,
            "rural_connections": 0.1,
            "safe_streets": 0.45,
        },
        "dev_energy_building_standard": {
            "adopt_standard": 0.8,
            "retain_incentives": 0.2,
        },
        "dev_justice_oversight": {
            "create_independent_board": 0.7,
            "retain_internal_review": 0.3,
        },
        "dev_governance_digital_budget": {
            "service_portal": 0.2,
            "privacy_security": 0.5,
            "open_data": 0.15,
            "offline_access": 0.15,
        },
    }
    scripted_settledness = {
        "dev_fiscal_reserve": 0.9,
        "dev_health_mobile_clinics": 0.65,
        "dev_education_calendar": 0.85,
        "dev_housing_zoning_tools": 0.8,
        "dev_transport_investment": 0.75,
        "dev_energy_building_standard": 0.3,
        "dev_justice_oversight": 0.8,
        "dev_governance_digital_budget": 0.75,
    }
    fixture_measure_ids = {measure.measure_id for measure in fixture.measures}
    if set(scripted_probabilities) != fixture_measure_ids:
        raise ValueError(
            "development scripted predictions must cover every fixture measure"
        )
    prediction_table_sha256 = content_sha256(
        {
            "probabilities_by_measure": scripted_probabilities,
            "settled_probability_by_measure": scripted_settledness,
        }
    )

    return [
        UniformPredictionAdapter(),
        ScriptedPredictionAdapter(
            configuration=ModelConfiguration(
                configuration_id="scripted_test_double_v1",
                model_name="Scripted test double",
                model_version="v1",
                seed=1701,
                parameters={
                    "role": "test_double",
                    "research_baseline": False,
                    "prediction_table_sha256": prediction_table_sha256,
                },
            ),
            probabilities_by_measure=scripted_probabilities,
            settled_probability_by_measure=scripted_settledness,
            prediction_metadata={"development_only": True},
        ),
    ]


def development_public_model_descriptors() -> dict[
    str,
    PublicModelDescriptor,
]:
    """Return the only model labels approved for the development artifact."""

    return {
        "uniform_prior_v1": PublicModelDescriptor(
            model_name="Uniform prior",
            model_version="v1",
            seed=0,
            model_role="research_baseline",
        ),
        "scripted_test_double_v1": PublicModelDescriptor(
            model_name="Scripted test double",
            model_version="v1",
            seed=1701,
            model_role="test_double",
        ),
    }
