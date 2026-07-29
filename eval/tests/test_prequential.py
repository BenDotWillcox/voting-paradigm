"""Tests for the deterministic Phase 2 prequential runner."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from eval.contracts import ModelConfiguration
from eval.development import (
    build_development_adapters,
    load_development_inputs,
)
from eval.fixture_io import canonical_json
from eval.prequential import (
    AdapterPrediction,
    PredictionRequest,
    SnapshotCheckpoint,
    UniformPredictionAdapter,
    run_prequential_session,
)


def test_development_replay_is_deterministic_and_complete():
    fixture, script = load_development_inputs()

    first = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=build_development_adapters(fixture),
    )
    second = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=build_development_adapters(fixture),
    )

    assert canonical_json(first) == canonical_json(second)
    assert len(first.run.measure_presentations) == 8
    assert len(first.run.participant_responses) == 8
    assert len(first.run.evidence_events) == 10
    assert len(first.run.prediction_snapshots) == 56
    assert len(first.snapshot_traces) == 56

    checkpoint_counts = {
        checkpoint: sum(
            trace.checkpoint is checkpoint
            for trace in first.snapshot_traces
        )
        for checkpoint in SnapshotCheckpoint
    }
    assert checkpoint_counts == {
        SnapshotCheckpoint.ZERO_EVIDENCE: 16,
        SnapshotCheckpoint.POST_ONBOARDING: 16,
        SnapshotCheckpoint.POST_WAVE: 8,
        SnapshotCheckpoint.IMMEDIATE_PRE_ANSWER: 16,
    }

    stream_sequences = sorted(
        [event.sequence for event in first.run.evidence_events]
        + [
            response.sequence
            for response in first.run.participant_responses
        ]
    )
    assert stream_sequences == list(range(1, 19))


@dataclass
class RecordingAdapter:
    requests: list[PredictionRequest] = field(default_factory=list)
    _delegate: UniformPredictionAdapter = field(
        default_factory=lambda: UniformPredictionAdapter(
            configuration_id="recording_uniform_v1"
        )
    )

    @property
    def configuration(self) -> ModelConfiguration:
        return self._delegate.configuration

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        self.requests.append(request)
        return self._delegate.predict(request)


def test_adapter_receives_only_evidence_available_at_snapshot_cutoff():
    fixture, script = load_development_inputs()
    adapter = RecordingAdapter()

    replay = run_prequential_session(
        fixture=fixture,
        script=script,
        adapters=[adapter],
    )

    assert len(adapter.requests) == len(replay.run.prediction_snapshots)
    trace_by_id = {
        trace.snapshot_id: trace for trace in replay.snapshot_traces
    }
    response_by_presentation = {
        response.presentation_id: response
        for response in replay.run.participant_responses
    }
    for request, snapshot in zip(
        adapter.requests,
        replay.run.prediction_snapshots,
    ):
        trace = trace_by_id[snapshot.snapshot_id]
        assert request.checkpoint is trace.checkpoint
        assert request.target_presentation.presentation_id == (
            snapshot.target_presentation_id
        )
        assert [event.event_id for event in request.evidence_events] == (
            snapshot.evidence_event_ids
        )
        assert all(
            event.sequence <= snapshot.evidence_cutoff_sequence
            for event in request.evidence_events
        )
        assert all(
            event.presentation_id != snapshot.target_presentation_id
            for event in request.evidence_events
        )
        target_response = response_by_presentation[
            snapshot.target_presentation_id
        ]
        assert target_response.sequence > snapshot.evidence_cutoff_sequence
        assert target_response.created_at > snapshot.created_at


class InvalidOptionAdapter:
    @property
    def configuration(self) -> ModelConfiguration:
        return ModelConfiguration(
            configuration_id="invalid_options_v1",
            model_name="Invalid options",
            model_version="v1",
            seed=0,
        )

    def predict(self, request: PredictionRequest) -> AdapterPrediction:
        return AdapterPrediction(
            option_probabilities={
                "invented_option": 0.5,
                "other_invented_option": 0.5,
            },
            settled_probability=0.5,
        )


def test_runner_rejects_adapter_options_outside_target_measure():
    fixture, script = load_development_inputs()

    with pytest.raises(ValueError, match="wrong options"):
        run_prequential_session(
            fixture=fixture,
            script=script,
            adapters=[InvalidOptionAdapter()],
        )


def test_session_script_is_bound_to_exact_fixture_hash():
    fixture, script = load_development_inputs()
    invalid = script.model_copy(
        update={"fixture_sha256": "0" * 64},
    )

    with pytest.raises(ValueError, match="fixture_sha256"):
        run_prequential_session(
            fixture=fixture,
            script=invalid,
            adapters=[UniformPredictionAdapter()],
        )
