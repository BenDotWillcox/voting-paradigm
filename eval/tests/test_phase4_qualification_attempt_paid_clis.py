from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval import authorize_phase4_qualification_attempt as authorize_cli
from eval import run_phase4_qualification_attempt as run_cli
from eval.contracts import ContractModel
from eval.phase4_qualification_attempt import ATTEMPT_V2_PROVIDER_CALL_COUNT
from eval.phase4_qualification_attempt_runtime import (
    ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD,
    ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD,
    ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD,
)
from eval.tests.test_phase4_qualification_paid_clis import (
    _redirect_private_root,
)


class _FakePlan(ContractModel):
    plan_id: str = "qualification_attempt_v2_test_plan"


class _FakeAuthorization(ContractModel):
    schema_version: str = "fake_attempt_authorization.v2"
    bundle_id: str = "qualification_attempt_v2_test_authorization"
    authorized_candidate_ids: tuple[str, ...] = ("candidate_a", "candidate_b")
    authorized_call_count: int = ATTEMPT_V2_PROVIDER_CALL_COUNT
    new_authorized_max_spend_microusd: int = (
        ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD
    )
    prior_actual_spend_microusd: int = ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD
    cumulative_authorized_worst_case_microusd: int = (
        ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD
    )


class _FakeState(ContractModel):
    status: str = "completed"
    completed_call_count: int = 152
    provider_spend_microusd: int = 10


class _CatalogParser:
    @staticmethod
    def model_validate_json(_payload: str) -> object:
        return object()


def _public_paths(tmp_path: Path) -> list[str]:
    return [str(tmp_path / f"public_{index}.json") for index in range(9)]


def _authorizer_argv(
    tmp_path: Path,
    output: Path,
    *,
    private_root: Path | None = None,
) -> list[str]:
    private_root = private_root or (tmp_path / "private_runs")
    catalog = private_root / "attempt_v2" / "catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("{}", encoding="utf-8")
    return [
        *_public_paths(tmp_path),
        str(catalog),
        str(output),
        "--approve-call-count",
        str(ATTEMPT_V2_PROVIDER_CALL_COUNT),
        "--approve-max-spend-microusd",
        str(ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD),
        "--confirm-prior-actual-spend-microusd",
        str(ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD),
        "--confirm-cumulative-authorized-max-microusd",
        str(ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD),
        "--confirm-public-development-only",
        "--confirm-no-participant-content",
        "--confirm-paired-execution-order",
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
    catalog = private_root / "attempt_v2" / "catalog.json"
    authorization = private_root / "attempt_v2" / "authorization.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("{}", encoding="utf-8")
    authorization.write_text("{}", encoding="utf-8")
    return [
        *_public_paths(tmp_path),
        str(catalog),
        str(authorization),
        str(output_directory),
        "--execute-paid-qualification-attempt-v2",
        "--confirm-call-count",
        str(ATTEMPT_V2_PROVIDER_CALL_COUNT),
        "--confirm-max-spend-microusd",
        str(ATTEMPT_V2_NEW_AUTHORIZED_MAX_MICROUSD),
        "--confirm-prior-actual-spend-microusd",
        str(ATTEMPT_V2_PRIOR_ACTUAL_SPEND_MICROUSD),
        "--confirm-cumulative-authorized-max-microusd",
        str(ATTEMPT_V2_CUMULATIVE_AUTHORIZED_WORST_CASE_MICROUSD),
    ]


def _patch_public_loaders(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    values = {
        "load_qualification_attempt_v2_source_proof": object(),
        "load_qualification_attempt_v2_plan": _FakePlan(),
        "load_two_deployment_qualification_scope": object(),
        "load_together_suite": object(),
        "load_readiness_bundle": object(),
        "load_phase4_robustness_profile": object(),
        "load_fixture": object(),
        "load_session_script": object(),
        "load_authored_semantic_map": SimpleNamespace(
            ontology=SimpleNamespace(item_ids=("one", "two"))
        ),
    }
    for name, value in values.items():
        monkeypatch.setattr(module, name, lambda _path, value=value: value)
    monkeypatch.setattr(module, "TogetherCatalogPreflightBundle", _CatalogParser)


def test_attempt_authorizer_checks_confirmation_before_file_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("authorizer read before approval")
        ),
    )
    argv = _authorizer_argv(tmp_path, tmp_path / "outside.json")
    argv[argv.index(str(ATTEMPT_V2_PROVIDER_CALL_COUNT))] = "303"

    assert authorize_cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside" not in captured.err


def test_attempt_authorizer_is_zero_network_private_and_aggregate_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = _redirect_private_root(monkeypatch, tmp_path)
    _patch_public_loaders(monkeypatch, authorize_cli)
    authorization = _FakeAuthorization()
    checkpoints = []
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("zero-spend authorizer used the network")
        ),
    )
    monkeypatch.setattr(
        authorize_cli,
        "build_qualification_attempt_v2_authorization",
        lambda *_args, **_kwargs: authorization,
    )
    monkeypatch.setattr(
        authorize_cli,
        "checkpoint_qualification_candidate_state",
        lambda path, value: checkpoints.append((path, value)),
    )
    output = private_root / "attempt_v2" / "authorization.json"

    assert authorize_cli.main(
        _authorizer_argv(tmp_path, output, private_root=private_root)
    ) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured.err == ""
    assert summary["authorized_call_count"] == 304
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert checkpoints == [(output.resolve(), authorization)]
    assert "candidate_a" not in captured.out


def test_attempt_runner_checks_confirmation_before_file_key_or_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runner read before confirmation")
        ),
    )
    monkeypatch.setattr(
        run_cli,
        "load_together_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runner loaded key before confirmation")
        ),
    )
    monkeypatch.setattr(
        run_cli.httpx,
        "Client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runner created client before confirmation")
        ),
    )
    argv = _runner_argv(tmp_path, tmp_path / "outside")
    argv.remove("--execute-paid-qualification-attempt-v2")

    assert run_cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside" not in captured.err


def test_attempt_runner_claims_before_key_and_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = _redirect_private_root(monkeypatch, tmp_path)
    _patch_public_loaders(monkeypatch, run_cli)
    authorization = _FakeAuthorization()
    events: list[str] = []
    monkeypatch.setattr(
        run_cli,
        "load_private_qualification_contract",
        lambda *_args, **_kwargs: authorization,
    )
    monkeypatch.setattr(
        run_cli,
        "validate_qualification_attempt_v2_authorization",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(run_cli, "load_exact_tokenizers", lambda *_a, **_k: {})
    monkeypatch.setattr(
        run_cli,
        "TogetherExactTokenCounterSet",
        lambda _counters: object(),
    )
    monkeypatch.setattr(
        run_cli,
        "CapabilityInterviewerTools",
        lambda _ids: object(),
    )
    monkeypatch.setattr(
        run_cli,
        "AuditedQualificationInterviewerToolExecutor",
        lambda _tools: object(),
    )
    monkeypatch.setattr(
        run_cli,
        "acquire_qualification_execution_claim",
        lambda *_args, **_kwargs: events.append("claim"),
    )

    def load_key(*_args: object, **_kwargs: object) -> str:
        assert events == ["claim"]
        events.append("key")
        return "tgp_v1_PLANTED_SECRET"

    monkeypatch.setattr(run_cli, "load_together_api_key", load_key)

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            assert events == ["claim", "key"]
            events.append("client")

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(run_cli.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        run_cli,
        "QualificationAttemptV2TogetherTransport",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        run_cli,
        "checkpoint_qualification_candidate_state",
        lambda *_args, **_kwargs: events.append("checkpoint"),
    )
    monkeypatch.setattr(
        run_cli,
        "execute_qualification_attempt_v2",
        lambda *_args, **_kwargs: {
            candidate_id: _FakeState()
            for candidate_id in authorization.authorized_candidate_ids
        },
    )
    monkeypatch.setattr(
        run_cli,
        "qualification_attempt_v2_candidate_state_summary",
        lambda state: state.model_dump(mode="json"),
    )
    output = private_root / "attempt_v2" / "run_one"

    assert run_cli.main(
        _runner_argv(tmp_path, output, private_root=private_root)
    ) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert events[:3] == ["claim", "key", "client"]
    assert "tgp_v1_PLANTED_SECRET" not in captured.out
    assert "candidate_a" not in captured.out
