"""Allowlisted public output for private human-measure evaluation replays."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .contracts import (
    ContractModel,
    EvaluationFixture,
    PositiveVersion,
    Probability,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .human_metrics import (
    ChoiceMetricSummary,
    HumanMeasureMetrics,
    RiskCoveragePoint,
    SettlednessMetricSummary,
)
from .prequential import PrequentialReplay

PublicModelRole = Literal[
    "research_baseline",
    "candidate_model",
    "test_double",
]
PUBLIC_THRESHOLD_GRID = (0.65, 0.75, 0.85, 0.95)


class PublicChoiceMetrics(ContractModel):
    count: int = Field(ge=0)
    mean_log_loss: float | None = Field(default=None, ge=0.0)
    top_choice_accuracy: Probability | None = Field(
        default=None,
        description="Mean top-choice credit with fractional credit for ties.",
    )
    mean_brier_score: float | None = Field(default=None, ge=0.0)


class PublicSettlednessMetrics(ContractModel):
    count: int = Field(ge=0)
    mean_brier_score: Probability | None = None


class PublicRiskCoveragePoint(ContractModel):
    threshold: Probability
    eligible_choice_count: int = Field(ge=0)
    nonchoice_count: int = Field(ge=0)
    automatic_choice_vote_count: int = Field(ge=0)
    coverage: Probability
    wrong_vote_count: int = Field(ge=0)
    risk: Probability | None = None
    unsupported_vote_count: int = Field(ge=0)
    unsupported_vote_rate: Probability | None = None


class PublicModelMetrics(ContractModel):
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    seed: int = Field(ge=0)
    model_role: PublicModelRole
    choice: PublicChoiceMetrics
    stable_choice: PublicChoiceMetrics
    tentative_choice: PublicChoiceMetrics
    settledness: PublicSettlednessMetrics
    candidate_thresholds: list[PublicRiskCoveragePoint]

    @model_validator(mode="after")
    def thresholds_match_public_grid(self) -> "PublicModelMetrics":
        published_thresholds = tuple(
            point.threshold for point in self.candidate_thresholds
        )
        if published_thresholds != PUBLIC_THRESHOLD_GRID:
            raise ValueError(
                "candidate thresholds must match the fixed public threshold "
                f"grid {PUBLIC_THRESHOLD_GRID}"
            )
        return self


class PublicModelDescriptor(ContractModel):
    """Explicitly approved public label for one private configuration id."""

    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    seed: int = Field(ge=0)
    model_role: PublicModelRole


class PublicHumanMeasureArtifact(ContractModel):
    """Allowlisted publication candidate requiring explicit release review.

    Aggregate metrics are not a formal ballot-confidentiality guarantee,
    especially for a single participant or a publicly reproducible model.
    """

    schema_version: Literal["public_human_measure_eval.v1"] = (
        "public_human_measure_eval.v1"
    )
    fixture_id: StableId
    fixture_version: PositiveVersion
    fixture_sha256: Sha256Digest
    development_only: bool
    choice_eligibility: Literal[
        "initial_choice_including_tentative"
    ] = "initial_choice_including_tentative"
    nonchoice_policy: Literal[
        "unsure_and_abstain_excluded_from_option_metrics"
    ] = "unsure_and_abstain_excluded_from_option_metrics"
    retest_policy: Literal["excluded_from_primary_metrics"] = (
        "excluded_from_primary_metrics"
    )
    log_loss_epsilon: float = Field(gt=0.0, lt=1.0)
    models: list[PublicModelMetrics]


def _public_choice(
    summary: ChoiceMetricSummary,
) -> PublicChoiceMetrics:
    return PublicChoiceMetrics(
        count=summary.count,
        mean_log_loss=summary.mean_log_loss,
        top_choice_accuracy=summary.top_choice_accuracy,
        mean_brier_score=summary.mean_brier_score,
    )


def _public_settledness(
    summary: SettlednessMetricSummary,
) -> PublicSettlednessMetrics:
    return PublicSettlednessMetrics(
        count=summary.count,
        mean_brier_score=summary.mean_brier_score,
    )


def _public_risk(
    point: RiskCoveragePoint,
) -> PublicRiskCoveragePoint:
    return PublicRiskCoveragePoint(
        threshold=point.threshold,
        eligible_choice_count=point.eligible_choice_count,
        nonchoice_count=point.nonchoice_count,
        automatic_choice_vote_count=point.automatic_choice_vote_count,
        coverage=point.coverage,
        wrong_vote_count=point.wrong_vote_count,
        risk=point.risk,
        unsupported_vote_count=point.unsupported_vote_count,
        unsupported_vote_rate=point.unsupported_vote_rate,
    )


def _fixed_public_risk_points(
    points: list[RiskCoveragePoint],
) -> list[PublicRiskCoveragePoint]:
    selected: list[PublicRiskCoveragePoint] = []
    for threshold in PUBLIC_THRESHOLD_GRID:
        matches = [
            point for point in points if point.threshold == threshold
        ]
        if len(matches) != 1:
            raise ValueError(
                "private metrics must contain exactly one point for every "
                "fixed public threshold; "
                f"threshold={threshold}, count={len(matches)}"
            )
        selected.append(_public_risk(matches[0]))
    return selected


def build_public_artifact(
    *,
    fixture: EvaluationFixture,
    replay: PrequentialReplay,
    metrics: HumanMeasureMetrics,
    public_model_descriptors: dict[str, PublicModelDescriptor],
) -> PublicHumanMeasureArtifact:
    """Construct public output field by field; never dump the private replay."""

    fixture_sha256 = content_sha256(fixture)
    if (
        replay.run.fixture_id,
        replay.run.fixture_version,
        replay.run.fixture_sha256,
    ) != (
        fixture.fixture_id,
        fixture.fixture_version,
        fixture_sha256,
    ):
        raise ValueError("public artifact fixture does not match private replay")
    if metrics.run_sha256 != content_sha256(replay.run):
        raise ValueError("public artifact metrics do not match private replay")

    configuration_ids = {
        configuration.configuration_id
        for configuration in replay.run.model_configurations
    }
    metric_configuration_ids = {
        model_metrics.configuration_id for model_metrics in metrics.models
    }
    descriptor_ids = set(public_model_descriptors)
    if descriptor_ids != metric_configuration_ids:
        missing = sorted(metric_configuration_ids - descriptor_ids)
        extra = sorted(descriptor_ids - metric_configuration_ids)
        raise ValueError(
            "public model descriptors must cover every metric model exactly; "
            f"missing={missing}, extra={extra}"
        )
    public_models: list[PublicModelMetrics] = []
    public_labels: set[tuple[str, str, int]] = set()
    for model_metrics in metrics.models:
        if model_metrics.configuration_id not in configuration_ids:
            raise ValueError(
                "metrics reference unknown model configuration "
                f"{model_metrics.configuration_id}"
            )
        descriptor = public_model_descriptors[
            model_metrics.configuration_id
        ]
        public_label = (
            descriptor.model_name,
            descriptor.model_version,
            descriptor.seed,
        )
        if public_label in public_labels:
            raise ValueError(
                "public model name, version, and seed must be unique"
            )
        public_labels.add(public_label)
        public_models.append(
            PublicModelMetrics(
                model_name=descriptor.model_name,
                model_version=descriptor.model_version,
                seed=descriptor.seed,
                model_role=descriptor.model_role,
                choice=_public_choice(model_metrics.choice),
                stable_choice=_public_choice(model_metrics.stable_choice),
                tentative_choice=_public_choice(
                    model_metrics.tentative_choice
                ),
                settledness=_public_settledness(
                    model_metrics.settledness
                ),
                candidate_thresholds=_fixed_public_risk_points(
                    model_metrics.candidate_thresholds
                ),
            )
        )
    return PublicHumanMeasureArtifact(
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=fixture_sha256,
        development_only=fixture.development_only,
        log_loss_epsilon=metrics.log_loss_epsilon,
        models=public_models,
    )


def render_public_summary(
    artifact: PublicHumanMeasureArtifact,
) -> str:
    """Render a concise deterministic human-readable result."""

    lines = [
        "Human-measure prequential evaluation",
        (
            f"fixture={artifact.fixture_id}@{artifact.fixture_version} "
            f"development_only={str(artifact.development_only).lower()}"
        ),
        "",
        (
            f"{'model':<24} {'choices':>7} {'log loss':>10} "
            f"{'accuracy':>10} {'settled Brier':>15}"
        ),
        "-" * 70,
    ]
    for model in artifact.models:
        log_loss = (
            f"{model.choice.mean_log_loss:.4f}"
            if model.choice.mean_log_loss is not None
            else "-"
        )
        accuracy = (
            f"{model.choice.top_choice_accuracy:.3f}"
            if model.choice.top_choice_accuracy is not None
            else "-"
        )
        settled_brier = (
            f"{model.settledness.mean_brier_score:.4f}"
            if model.settledness.mean_brier_score is not None
            else "-"
        )
        lines.append(
            f"{model.model_name:<24} {model.choice.count:>7} "
            f"{log_loss:>10} {accuracy:>10} {settled_brier:>15}"
        )
    lines.extend(
        [
            "",
            "Primary option metrics include tentative CHOICE responses.",
            "UNSURE, ABSTAIN, and RETEST are excluded from option metrics.",
        ]
    )
    test_doubles = [
        model.model_name
        for model in artifact.models
        if model.model_role == "test_double"
    ]
    if test_doubles:
        lines.append(
            "TEST DOUBLE -- not a research result: "
            + ", ".join(test_doubles)
            + "."
        )
    return "\n".join(lines)
