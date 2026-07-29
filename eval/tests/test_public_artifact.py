"""Tests for the public allowlist serializer and Phase 2 CLI."""

from __future__ import annotations

import json

import pytest

from eval.development import (
    build_development_adapters,
    development_public_model_descriptors,
    load_development_inputs,
)
from eval.human_metrics import compute_human_measure_metrics
from eval.prequential import (
    AdapterPrediction,
    PredictionRequest,
    UniformPredictionAdapter,
    run_prequential_session,
)
from eval.public_artifact import (
    PUBLIC_THRESHOLD_GRID,
    PublicHumanMeasureArtifact,
    PublicModelDescriptor,
    build_public_artifact,
)
from eval.run_human_measure_eval import main


class SensitiveUniformAdapter(UniformPredictionAdapter):
    def __init__(self, secret: str) -> None:
        super().__init__(configuration_id="sensitive_configuration")
        self.secret = secret

    @property
    def configuration(self):
        configuration = super().configuration
        configuration.model_name = self.secret
        configuration.parameters = {"private_parameter": self.secret}
        return configuration

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        prediction = super().predict(request)
        return prediction.model_copy(
            update={"metadata": {"private_trace": self.secret}},
        )


def build_development_artifact_with_thresholds(
    thresholds: tuple[float, ...],
) -> PublicHumanMeasureArtifact:
    fixture, script = load_development_inputs()
    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=build_development_adapters(fixture),
        delegation_thresholds=thresholds,
    )
    metrics = compute_human_measure_metrics(
        replay,
        candidate_thresholds=thresholds,
    )
    artifact = build_public_artifact(
        fixture=fixture,
        replay=replay,
        metrics=metrics,
        public_model_descriptors=development_public_model_descriptors(),
    )
    return artifact


def test_public_artifact_omits_every_private_replay_surface():
    fixture, source_script = load_development_inputs()
    secret = "planted_sensitive_value"
    script_data = source_script.model_dump(mode="json")
    script_data["run_id"] = "secret_run"
    script_data["session_id"] = "secret_session"
    for event in script_data["onboarding_evidence"]:
        event["session_id"] = "secret_session"
        event["raw_response"] = secret
        event["normalized_claims"] = [secret]
        event["metadata"] = {"private_note": secret}
    script = source_script.__class__.model_validate(script_data)
    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=[SensitiveUniformAdapter(secret)],
    )
    metrics = compute_human_measure_metrics(replay)

    artifact = build_public_artifact(
        fixture=fixture,
        replay=replay,
        metrics=metrics,
        public_model_descriptors={
            "sensitive_configuration": PublicModelDescriptor(
                model_name="Approved public model label",
                model_version="v1",
                seed=0,
                model_role="candidate_model",
            )
        },
    )
    serialized = artifact.model_dump_json()

    private_values = {
        secret,
        replay.session_script_id,
        replay.session_script_sha256,
        metrics.run_sha256,
        replay.run.run_id,
        replay.run.session_id,
        replay.run.model_configurations[0].configuration_id,
        replay.run.model_configurations[0].model_name,
        *(
            presentation.presentation_id
            for presentation in replay.run.measure_presentations
        ),
        *(
            response.response_id
            for response in replay.run.participant_responses
        ),
        *(event.event_id for event in replay.run.evidence_events),
        *(
            snapshot.snapshot_id
            for snapshot in replay.run.prediction_snapshots
        ),
    }
    assert all(value not in serialized for value in private_values)
    for private_field in (
        "run_id",
        "session_id",
        "raw_response",
        "normalized_claims",
        "metadata",
        "presentation_id",
        "response_id",
        "snapshot_id",
        "evidence_event_ids",
        "risk_coverage_curve",
        "wrong_vote_confidences",
        "checkpoint_slices",
    ):
        assert f'"{private_field}"' not in serialized


def test_cli_writes_reproducible_public_artifact(tmp_path, capsys):
    output_path = tmp_path / "public_eval.json"
    custom_output_path = tmp_path / "public_eval_custom_threshold.json"

    first_exit = main(["--output", str(output_path)])
    first_content = output_path.read_text(encoding="utf-8")
    first_stdout = capsys.readouterr().out
    second_exit = main(["--output", str(output_path)])
    second_content = output_path.read_text(encoding="utf-8")
    custom_exit = main(
        [
            "--threshold",
            "0.4413",
            "--output",
            str(custom_output_path),
        ]
    )
    custom_artifact = json.loads(
        custom_output_path.read_text(encoding="utf-8")
    )

    assert first_exit == 0
    assert second_exit == 0
    assert custom_exit == 0
    assert first_content == second_content
    artifact = json.loads(first_content)
    assert artifact["schema_version"] == "public_human_measure_eval.v1"
    assert artifact["choice_eligibility"] == (
        "initial_choice_including_tentative"
    )
    assert len(artifact["models"]) == 2
    assert "Human-measure prequential evaluation" in first_stdout
    assert "TEST DOUBLE -- not a research result" in first_stdout
    assert "synthetic_development_session" not in first_content
    assert {
        model["model_role"] for model in artifact["models"]
    } == {"research_baseline", "test_double"}
    for model in artifact["models"]:
        assert "risk_coverage_curve" not in model
        assert "wrong_vote_confidences" not in model
        assert "checkpoint_slices" not in model
        assert [
            point["threshold"]
            for point in model["candidate_thresholds"]
        ] == list(PUBLIC_THRESHOLD_GRID)
    for model in custom_artifact["models"]:
        assert [
            point["threshold"]
            for point in model["candidate_thresholds"]
        ] == list(PUBLIC_THRESHOLD_GRID)


def test_public_artifact_rejects_metrics_missing_fixed_thresholds():
    private_thresholds = (0.4413, 0.5527, 0.6631)
    fixture, script = load_development_inputs()
    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=build_development_adapters(fixture),
        delegation_thresholds=private_thresholds,
    )
    metrics = compute_human_measure_metrics(
        replay,
        candidate_thresholds=private_thresholds,
    )

    with pytest.raises(ValueError, match="fixed public threshold"):
        build_public_artifact(
            fixture=fixture,
            replay=replay,
            metrics=metrics,
            public_model_descriptors=(
                development_public_model_descriptors()
            ),
        )


def test_public_schema_rejects_an_off_grid_threshold():
    thresholds = tuple(
        sorted(set(PUBLIC_THRESHOLD_GRID).union({0.4413}))
    )
    artifact = build_development_artifact_with_thresholds(thresholds)
    artifact_data = artifact.model_dump(mode="json")
    injected_point = dict(
        artifact_data["models"][0]["candidate_thresholds"][0]
    )
    injected_point["threshold"] = 0.4413
    artifact_data["models"][0]["candidate_thresholds"].append(
        injected_point
    )

    with pytest.raises(ValueError, match="fixed public threshold grid"):
        PublicHumanMeasureArtifact.model_validate(artifact_data)


def test_public_artifact_requires_explicit_model_labels():
    fixture, script = load_development_inputs()
    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=[UniformPredictionAdapter()],
    )
    metrics = compute_human_measure_metrics(replay)

    with pytest.raises(ValueError, match="descriptors"):
        build_public_artifact(
            fixture=fixture,
            replay=replay,
            metrics=metrics,
            public_model_descriptors={},
        )
