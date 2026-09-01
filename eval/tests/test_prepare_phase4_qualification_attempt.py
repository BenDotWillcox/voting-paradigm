from __future__ import annotations

import json
from pathlib import Path

from eval import prepare_phase4_qualification_attempt as prepare_cli
from eval.contracts import ContractModel


PLANTED_PRIVATE_TEXT = "tgp_v1_PRIVATE_PROVIDER_PAYLOAD_DO_NOT_PRINT"


class _FakeProof(ContractModel):
    artifact: str = "proof"
    prior_result_rebuild_passed: bool = True
    prior_candidate_state_audits_passed: bool = True
    prior_carry_observation_bindings_passed: bool = True
    prior_new_observation_bindings_passed: bool = True


class _FakePlan(ContractModel):
    artifact: str = "plan"
    candidate_plans: list[str] = ["candidate_alpha", "candidate_beta"]
    scoped_coordinate_count: int = 304
    carried_success_count: int = 0
    provider_call_count: int = 304
    conformance_stage_call_count: int = 4
    new_projected_cost_microusd: int = 1_234
    new_authorized_max_cost_microusd: int = 2_345
    prior_actual_spend_microusd: int = 97_287
    cumulative_authorized_worst_case_microusd: int = 99_632
    sequential_projected_headroom_microusd: int = 3_900_000


def _argv(
    tmp_path: Path,
    source_proof_output: Path,
    plan_output: Path,
) -> list[str]:
    public_root = tmp_path / "public"
    private_root = tmp_path / "eval" / "private_runs"
    public_paths = [public_root / f"source_{index}.json" for index in range(11)]
    return [
        str(public_paths[0]),
        str(private_root / "attempt_v1" / "carry.json"),
        str(private_root / "attempt_v1" / "authorization.json"),
        str(private_root / "attempt_v1" / "result.json"),
        str(public_paths[1]),
        str(public_paths[2]),
        str(public_paths[3]),
        str(public_paths[4]),
        str(public_paths[5]),
        str(public_paths[6]),
        str(public_paths[7]),
        str(public_paths[8]),
        str(public_paths[9]),
        str(public_paths[10]),
        str(source_proof_output),
        str(plan_output),
        "--prior-candidate-state",
        str(private_root / "attempt_v1" / "candidate_alpha.json"),
        "--prior-candidate-state",
        str(private_root / "attempt_v1" / "candidate_beta.json"),
    ]


def test_prepare_cli_builds_before_atomic_writes_and_reports_only_aggregates(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    tracked_root = tmp_path / "eval" / "fixtures"
    private_root = tmp_path / "eval" / "private_runs"
    source_proof_output = tracked_root / "attempt_v2_source_proof.json"
    plan_output = tracked_root / "attempt_v2_plan.json"
    proof = _FakeProof()
    plan = _FakePlan()
    inputs = prepare_cli._PreparationInputs(
        prior_plan=object(),
        prior_carry=object(),
        prior_authorization=object(),
        prior_result=PLANTED_PRIVATE_TEXT,
        prior_receipt=object(),
        prior_scope=object(),
        prior_states=[object(), object()],
        source_suite=object(),
        source_readiness=object(),
        corrected_suite=object(),
        corrected_readiness=object(),
        profile=object(),
        fixture=object(),
        session=object(),
        semantic_map=object(),
    )
    events: list[str] = []

    monkeypatch.setattr(prepare_cli, "PRIVATE_RUNS_ROOT", private_root)
    monkeypatch.setattr(prepare_cli, "TRACKED_FIXTURES_ROOT", tracked_root)
    monkeypatch.setattr(prepare_cli, "_load_inputs", lambda _args: inputs)
    monkeypatch.setattr(
        prepare_cli,
        "build_together_suite_v5",
        lambda _profile: inputs.source_suite,
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_default_together_suite",
        lambda _profile: inputs.corrected_suite,
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_together_suite",
        lambda *_args, **_kwargs: events.append("suite_validated"),
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_readiness_bundle",
        lambda *_args, **_kwargs: events.append("readiness_validated"),
    )

    def build_proof(*_args, **_kwargs):
        assert not source_proof_output.exists()
        assert not plan_output.exists()
        events.append("proof")
        return proof

    def build_plan(*_args, **_kwargs):
        assert not source_proof_output.exists()
        assert not plan_output.exists()
        events.append("plan")
        return plan

    monkeypatch.setattr(
        prepare_cli,
        "build_qualification_attempt_v2_source_proof",
        build_proof,
    )
    monkeypatch.setattr(
        prepare_cli,
        "build_qualification_attempt_v2_plan",
        build_plan,
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_qualification_attempt_v2_source_proof",
        lambda *_args, **_kwargs: events.append("proof_validated"),
    )
    monkeypatch.setattr(
        prepare_cli,
        "validate_qualification_attempt_v2_plan",
        lambda *_args, **_kwargs: events.append("plan_validated"),
    )
    assert prepare_cli.main(
        _argv(tmp_path, source_proof_output, plan_output)
    ) == 0

    assert events == [
        "suite_validated",
        "suite_validated",
        "readiness_validated",
        "readiness_validated",
        "proof",
        "proof_validated",
        "plan",
        "plan_validated",
    ]
    assert json.loads(source_proof_output.read_text(encoding="utf-8")) == (
        proof.model_dump(mode="json")
    )
    assert json.loads(plan_output.read_text(encoding="utf-8")) == (
        plan.model_dump(mode="json")
    )
    assert PLANTED_PRIVATE_TEXT not in source_proof_output.read_text(
        encoding="utf-8"
    )
    assert PLANTED_PRIVATE_TEXT not in plan_output.read_text(encoding="utf-8")

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["candidate_count"] == 2
    assert summary["scoped_coordinate_count"] == 304
    assert summary["carried_success_count"] == 0
    assert summary["provider_call_count"] == 304
    assert summary["conformance_stage_call_count"] == 4
    assert summary["prior_result_rebuild_passed"] is True
    assert summary["prior_candidate_state_audits_passed"] is True
    assert summary["prior_carry_observation_bindings_passed"] is True
    assert summary["prior_new_observation_bindings_passed"] is True
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert PLANTED_PRIVATE_TEXT not in captured.out
    assert "candidate_alpha" not in captured.out
    assert "private_payload" not in captured.out
    assert "private_runs" not in captured.out
    assert list(tracked_root.glob(".*.tmp")) == []


def test_prepare_cli_rejects_untracked_plan_before_reading_any_input(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    tracked_root = tmp_path / "eval" / "fixtures"
    private_root = tmp_path / "eval" / "private_runs"
    source_proof_output = tracked_root / "attempt_v2_source_proof.json"
    plan_output = tmp_path / "untracked_plan.json"
    reads: list[Path] = []

    monkeypatch.setattr(prepare_cli, "PRIVATE_RUNS_ROOT", private_root)
    monkeypatch.setattr(prepare_cli, "TRACKED_FIXTURES_ROOT", tracked_root)

    def forbidden_read(path: Path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("inputs must not be read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)

    assert prepare_cli.main(
        _argv(tmp_path, source_proof_output, plan_output)
    ) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
    assert reads == []
    assert not source_proof_output.exists()
    assert not plan_output.exists()


def test_prepare_cli_requires_exactly_two_prior_candidate_states(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    tracked_root = tmp_path / "eval" / "fixtures"
    private_root = tmp_path / "eval" / "private_runs"
    source_proof_output = tracked_root / "attempt_v2_source_proof.json"
    plan_output = tracked_root / "attempt_v2_plan.json"
    argv = _argv(tmp_path, source_proof_output, plan_output)
    del argv[-2:]

    monkeypatch.setattr(prepare_cli, "PRIVATE_RUNS_ROOT", private_root)
    monkeypatch.setattr(prepare_cli, "TRACKED_FIXTURES_ROOT", tracked_root)

    assert prepare_cli.main(argv) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
    assert not source_proof_output.exists()
    assert not plan_output.exists()
