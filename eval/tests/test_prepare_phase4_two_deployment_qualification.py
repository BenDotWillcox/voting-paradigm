from __future__ import annotations

import json
from pathlib import Path

from eval import prepare_phase4_two_deployment_qualification as prepare_cli
from eval.phase4_qualification_execution import (
    load_two_deployment_carry_bundle,
    load_two_deployment_qualification_plan,
)
from eval.tests.test_phase4_qualification_execution import (
    _synthetic_carry_bundle,
    _tracked_execution_plan,
)


def _argv(tmp_path: Path, plan_output: Path, carry_output: Path) -> list[str]:
    public_inputs = [str(tmp_path / f"public_{index}.json") for index in range(14)]
    return [
        *public_inputs,
        str(tmp_path / "scope.json"),
        str(tmp_path / "scope_proof.json"),
        str(tmp_path / "aggregation.json"),
        str(plan_output),
        str(carry_output),
        "--source-state",
        str(tmp_path / "private_state_one.json"),
        "--source-state",
        str(tmp_path / "private_state_two.json"),
    ]


def _patch_successful_build(monkeypatch, plan_output: Path, carry_output: Path):
    plan, _, _, _ = _tracked_execution_plan()
    carry = _synthetic_carry_bundle()
    public_inputs = tuple(f"public_{index}" for index in range(15))
    scope = object()
    proof = object()
    aggregation = object()
    source_states = [object(), object()]
    events: list[str] = []

    monkeypatch.setattr(
        prepare_cli,
        "load_selector_recovery_public_inputs",
        lambda _args: public_inputs,
    )
    monkeypatch.setattr(
        prepare_cli,
        "load_two_deployment_qualification_scope",
        lambda _path: scope,
    )
    monkeypatch.setattr(
        prepare_cli,
        "load_two_deployment_scope_evidence_proof",
        lambda _path: proof,
    )
    monkeypatch.setattr(
        prepare_cli,
        "load_capability_aggregation",
        lambda _path: aggregation,
    )
    monkeypatch.setattr(
        prepare_cli,
        "_load_source_states",
        lambda _paths: source_states,
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_two_deployment_qualification_plan",
        lambda *args, **kwargs: plan,
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_two_deployment_carry_bundle",
        lambda *args, **kwargs: carry,
    )

    def validate_plan(*_args, **_kwargs) -> None:
        assert not plan_output.exists()
        assert not carry_output.exists()
        events.append("plan_validated")

    def validate_carry(*_args, **_kwargs) -> None:
        assert not plan_output.exists()
        assert not carry_output.exists()
        events.append("carry_validated")

    monkeypatch.setattr(
        prepare_cli,
        "validate_two_deployment_qualification_plan",
        validate_plan,
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_two_deployment_carry_bundle",
        validate_carry,
    )
    return plan, carry, events


def test_prepare_cli_validates_both_before_writing_and_reports_aggregates(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    private_root = tmp_path / "eval" / "private_runs"
    plan_output = tmp_path / "eval" / "fixtures" / "plan.json"
    carry_output = private_root / "phase4" / "carry.json"
    monkeypatch.setattr(prepare_cli, "PRIVATE_RUNS_ROOT", private_root)
    plan, carry, events = _patch_successful_build(
        monkeypatch,
        plan_output,
        carry_output,
    )

    assert prepare_cli.main(_argv(tmp_path, plan_output, carry_output)) == 0

    assert events == ["plan_validated", "carry_validated"]
    assert load_two_deployment_qualification_plan(plan_output) == plan
    assert load_two_deployment_carry_bundle(carry_output) == carry
    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["scoped_entry_count"] == 304
    assert summary["carried_success_count"] == 10
    assert summary["provider_call_count"] == 294
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert "together_glm" not in captured.out
    assert "output_payload" not in captured.out
    assert "private_runs" not in captured.out


def test_prepare_cli_rejects_nonprivate_carry_before_reading_inputs(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    private_root = tmp_path / "eval" / "private_runs"
    plan_output = tmp_path / "eval" / "fixtures" / "plan.json"
    carry_output = tmp_path / "carry.json"
    reads: list[Path] = []

    monkeypatch.setattr(prepare_cli, "PRIVATE_RUNS_ROOT", private_root)

    def forbidden_read(path: Path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("inputs must not be read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)

    assert prepare_cli.main(_argv(tmp_path, plan_output, carry_output)) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
    assert reads == []
    assert not plan_output.exists()
    assert not carry_output.exists()


def test_source_state_loader_is_applied_to_every_repeated_path(
    tmp_path,
    monkeypatch,
) -> None:
    paths = [tmp_path / "one.json", tmp_path / "two.json"]
    loaded: list[Path] = []

    def fake_loader(path: Path):
        loaded.append(path)
        return path.name

    monkeypatch.setattr(prepare_cli, "load_capability_source_state", fake_loader)

    assert prepare_cli._load_source_states(paths) == ["one.json", "two.json"]
    assert loaded == paths
