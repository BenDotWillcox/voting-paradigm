from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval import authorize_phase4_two_deployment_qualification as authorize_cli
from eval import run_phase4_two_deployment_qualification as run_cli
from eval.contracts import ContractModel
from eval.phase4_qualification_scope import NEW_PROVIDER_CALL_COUNT


class _FakePlan(ContractModel):
    plan_id: str = "plan_public_qualification"


class _FakeAuthorization(ContractModel):
    schema_version: str = "fake_authorization.v1"
    bundle_id: str = "authorization_public_qualification"
    authorization_id: str = "authorization_public_qualification"
    execution_plan_sha256: str = "a" * 64
    authorized_candidate_ids: tuple[str, ...] = (
        "together_glm_5_2",
        "together_gpt_oss_120b",
    )
    authorized_requests: tuple[str, ...] = tuple(
        f"request_{index}" for index in range(NEW_PROVIDER_CALL_COUNT)
    )
    new_authorized_max_spend_microusd: int = (
        authorize_cli.QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
    )
    prior_qualification_spend_microusd: int = (
        authorize_cli.QUALIFICATION_PRIOR_SPEND_MICROUSD
    )


class _FakeState(ContractModel):
    candidate_id: str
    completed_call_count: int = 147


class _CatalogParser:
    @staticmethod
    def model_validate_json(_payload: str) -> object:
        return object()


def _public_paths(tmp_path: Path) -> list[str]:
    return [str(tmp_path / f"public_{index}.json") for index in range(14)]


def _authorization_argv(
    tmp_path: Path,
    output: Path,
    *,
    private_root: Path | None = None,
) -> list[str]:
    private_root = private_root or (tmp_path / "private_runs")
    catalog = private_root / "qualification" / "catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("{}", encoding="utf-8")
    return [
        *_public_paths(tmp_path),
        str(tmp_path / "scope.json"),
        str(tmp_path / "scope-proof.json"),
        str(tmp_path / "aggregation.json"),
        str(tmp_path / "plan.json"),
        str(private_root / "qualification" / "carry.json"),
        str(catalog),
        str(output),
        "--source-state",
        str(private_root / "qualification" / "source-state.json"),
        "--approve-call-count",
        str(NEW_PROVIDER_CALL_COUNT),
        "--approve-max-spend-microusd",
        str(authorize_cli.QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD),
        "--confirm-cumulative-authorized-max-microusd",
        str(authorize_cli.QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD),
        "--confirm-public-development-only",
        "--confirm-no-participant-content",
        "--confirm-no-automatic-retry",
        "--confirm-no-fallback-or-replacement",
    ]


def _runner_argv(
    tmp_path: Path,
    output_directory: Path,
    *,
    private_root: Path | None = None,
) -> list[str]:
    private_root = private_root or (tmp_path / "private_runs")
    catalog = private_root / "qualification" / "catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("{}", encoding="utf-8")
    return [
        *_public_paths(tmp_path),
        str(tmp_path / "scope.json"),
        str(tmp_path / "scope-proof.json"),
        str(tmp_path / "aggregation.json"),
        str(tmp_path / "plan.json"),
        str(private_root / "qualification" / "carry.json"),
        str(catalog),
        str(private_root / "qualification" / "authorization.json"),
        str(output_directory),
        "--source-state",
        str(private_root / "qualification" / "source-state.json"),
        "--execute-paid-two-deployment-qualification",
        "--confirm-call-count",
        str(NEW_PROVIDER_CALL_COUNT),
        "--confirm-max-spend-microusd",
        str(run_cli.QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD),
        "--confirm-cumulative-authorized-max-microusd",
        str(run_cli.QUALIFICATION_CUMULATIVE_AUTHORIZED_MAX_MICROUSD),
    ]


def _redirect_private_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    import eval.phase4_qualification_io as qualification_io

    private_root = (tmp_path / "private_runs").resolve()
    monkeypatch.setattr(qualification_io, "PRIVATE_OUTPUT_ROOT", private_root)
    monkeypatch.setattr(
        qualification_io,
        "QUALIFICATION_EXECUTION_CLAIM_ROOT",
        (private_root / "qualification_execution_claims").resolve(),
    )
    return private_root


def _patch_artifact_loaders(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> tuple[object, ...]:
    public = tuple(object() for _ in range(14)) + (
        SimpleNamespace(ontology=SimpleNamespace(item_ids=("one", "two"))),
    )
    monkeypatch.setattr(
        module,
        "load_selector_recovery_public_inputs",
        lambda _args: public,
    )
    monkeypatch.setattr(
        module,
        "load_two_deployment_qualification_scope",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        module,
        "load_two_deployment_scope_evidence_proof",
        lambda _path: object(),
    )
    monkeypatch.setattr(module, "load_capability_aggregation", lambda _path: object())
    monkeypatch.setattr(
        module,
        "load_two_deployment_qualification_plan",
        lambda _path: _FakePlan(),
    )
    monkeypatch.setattr(
        module,
        "load_two_deployment_carry_bundle",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        module,
        "load_capability_source_states",
        lambda _paths: (object(),),
    )
    monkeypatch.setattr(module, "TogetherCatalogPreflightBundle", _CatalogParser)
    return public


def test_authorizer_checks_confirmation_before_any_file_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_read(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("authorizer read a file before approval")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    argv = _authorization_argv(tmp_path, tmp_path / "outside.json")
    argv[argv.index(str(NEW_PROVIDER_CALL_COUNT))] = str(
        NEW_PROVIDER_CALL_COUNT - 1
    )

    assert authorize_cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside" not in captured.err


def test_runner_checks_confirmation_before_file_key_or_client_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_read(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("runner read a file before confirmation")

    def forbidden_key(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("runner loaded the key before confirmation")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    monkeypatch.setattr(run_cli, "load_together_api_key", forbidden_key)
    monkeypatch.setattr(run_cli.httpx, "Client", forbidden_key)
    argv = _runner_argv(tmp_path, tmp_path / "outside")
    argv.remove("--execute-paid-two-deployment-qualification")

    assert run_cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside" not in captured.err


def test_authorizer_rejects_public_output_before_loading_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _redirect_private_root(monkeypatch, tmp_path)

    def forbidden_loader(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("authorizer loaded an artifact before confinement")

    monkeypatch.setattr(
        authorize_cli,
        "load_selector_recovery_public_inputs",
        forbidden_loader,
    )
    output = tmp_path / "tracked" / "authorization.json"

    assert authorize_cli.main(_authorization_argv(tmp_path, output)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "authorization.json" not in captured.err


def test_authorizer_is_aggregate_only_zero_network_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = _redirect_private_root(monkeypatch, tmp_path)
    _patch_artifact_loaders(monkeypatch, authorize_cli)
    authorization = _FakeAuthorization()
    checkpoints: list[tuple[Path, ContractModel]] = []

    def forbidden_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("zero-spend authorizer attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(
        authorize_cli,
        "build_two_deployment_qualification_authorization",
        lambda *_args, **_kwargs: authorization,
    )
    monkeypatch.setattr(
        authorize_cli,
        "checkpoint_qualification_candidate_state",
        lambda path, value: checkpoints.append((path, value)),
    )
    output = private_root / "qualification" / "authorization.json"

    assert authorize_cli.main(
        _authorization_argv(tmp_path, output, private_root=private_root)
    ) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary == {
        "authorized_call_count": NEW_PROVIDER_CALL_COUNT,
        "authorized_max_spend_microusd": (
            authorize_cli.QUALIFICATION_NEW_AUTHORIZED_MAX_MICROUSD
        ),
        "bundle_id": authorization.bundle_id,
        "bundle_sha256": summary["bundle_sha256"],
        "candidate_count": 2,
        "participant_content_present": False,
        "prior_qualification_spend_microusd": (
            authorize_cli.QUALIFICATION_PRIOR_SPEND_MICROUSD
        ),
        "schema_version": authorization.schema_version,
    }
    assert checkpoints == [(output.resolve(), authorization)]
    assert checkpoints[0][0].is_relative_to(private_root)
    assert "together_glm_5_2" not in captured.out
    assert "source-state" not in captured.out


def _patch_successful_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> tuple[Path, _FakeAuthorization]:
    private_root = _redirect_private_root(monkeypatch, tmp_path)
    _patch_artifact_loaders(monkeypatch, run_cli)
    authorization = _FakeAuthorization()
    monkeypatch.setattr(
        run_cli,
        "load_private_qualification_contract",
        lambda _path, _type: authorization,
    )
    monkeypatch.setattr(
        run_cli,
        "validate_two_deployment_qualification_authorization",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(run_cli, "load_exact_tokenizers", lambda *_a, **_k: object())
    monkeypatch.setattr(
        run_cli,
        "TogetherExactTokenCounterSet",
        lambda _counters: object(),
    )
    monkeypatch.setattr(run_cli, "CapabilityInterviewerTools", lambda _ids: object())
    monkeypatch.setattr(
        run_cli,
        "AuditedQualificationInterviewerToolExecutor",
        lambda _provider: object(),
    )
    monkeypatch.setattr(
        run_cli,
        "acquire_qualification_execution_claim",
        lambda *_args, **_kwargs: events.append("claim"),
    )

    secret = "tgp_v1_PLANTED_LOCAL_SECRET"

    def load_key(*_args: object, **_kwargs: object) -> str:
        assert "claim" in events
        events.append("key")
        return secret

    monkeypatch.setattr(run_cli, "load_together_api_key", load_key)

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            assert "claim" in events
            events.append("client")

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(run_cli.httpx, "Client", FakeClient)

    def transport(*_args: object, **_kwargs: object) -> object:
        assert "claim" in events
        assert "key" in events
        assert "client" in events
        events.append("transport")
        return object()

    monkeypatch.setattr(run_cli, "ScopedQualificationTogetherTransport", transport)
    monkeypatch.setattr(
        run_cli,
        "checkpoint_qualification_candidate_state",
        lambda _path, _state: events.append("checkpoint"),
    )

    def execute(*_args: object, **kwargs: object) -> dict[str, _FakeState]:
        events.append("execute")
        checkpoint = kwargs["checkpoint"]
        states = {
            candidate_id: _FakeState(candidate_id=candidate_id)
            for candidate_id in authorization.authorized_candidate_ids
        }
        for candidate_id, state in states.items():
            checkpoint(candidate_id, state)
        return states

    monkeypatch.setattr(run_cli, "execute_two_deployment_qualification", execute)
    monkeypatch.setattr(
        run_cli,
        "qualification_candidate_state_summary",
        lambda state: {
            "completed_call_count": state.completed_call_count,
            "terminal_status": "complete",
        },
    )
    return private_root, authorization


def test_runner_claims_before_key_and_client_and_executes_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    private_root, authorization = _patch_successful_runner(
        tmp_path,
        monkeypatch,
        events,
    )
    output_directory = private_root / "qualification" / "run_one"

    assert run_cli.main(
        _runner_argv(
            tmp_path,
            output_directory,
            private_root=private_root,
        )
    ) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["execution_plan_sha256"] == authorization.execution_plan_sha256
    assert len(summary["candidate_states"]) == 2
    assert summary["participant_content_present"] is False
    assert "tgp_v1_PLANTED_LOCAL_SECRET" not in captured.out
    assert "together_glm_5_2" not in captured.out
    assert events.index("claim") < events.index("key") < events.index("client")
    assert events.count("checkpoint") == 2
    assert events[-1] == "execute" or "execute" in events


def test_runner_existing_state_blocks_before_claim_key_and_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    private_root, authorization = _patch_successful_runner(
        tmp_path,
        monkeypatch,
        events,
    )
    output_directory = private_root / "qualification" / "run_state_exists"
    output_directory.mkdir(parents=True)
    state_path = output_directory / (
        f"{authorization.authorized_candidate_ids[0]}_qualification_state_v1.json"
    )
    state_path.write_text("{}", encoding="utf-8")

    assert run_cli.main(
        _runner_argv(
            tmp_path,
            output_directory,
            private_root=private_root,
        )
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "claim" not in events
    assert "key" not in events
    assert "client" not in events
    assert authorization.authorized_candidate_ids[0] not in captured.err


def test_runner_existing_claim_blocks_before_key_and_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    private_root, _authorization = _patch_successful_runner(
        tmp_path,
        monkeypatch,
        events,
    )

    def existing_claim(*_args: object, **_kwargs: object) -> None:
        events.append("claim")
        raise ValueError(
            "qualification execution plan is already claimed; "
            "manual reconciliation required"
        )

    monkeypatch.setattr(
        run_cli,
        "acquire_qualification_execution_claim",
        existing_claim,
    )
    output_directory = private_root / "qualification" / "run_claim_exists"

    assert run_cli.main(
        _runner_argv(
            tmp_path,
            output_directory,
            private_root=private_root,
        )
    ) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert events == ["claim"]
    assert "tgp_v1" not in captured.err
