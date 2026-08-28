from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_qualification_io import (
    acquire_qualification_execution_claim,
    checkpoint_qualification_candidate_state,
    load_private_qualification_contract,
    normalized_private_output_directory,
    private_qualification_output,
    validate_qualification_execution_claim,
)


NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


class _TestPlan(ContractModel):
    plan_id: str


class _TestAuthorization(ContractModel):
    authorization_id: str


class _TestCandidateState(ContractModel):
    sequence: int


def _redirect_private_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    import eval.phase4_qualification_io as qualification_io

    private_root = (tmp_path / "private_runs").resolve()
    monkeypatch.setattr(
        qualification_io,
        "PRIVATE_OUTPUT_ROOT",
        private_root,
    )
    monkeypatch.setattr(
        qualification_io,
        "QUALIFICATION_EXECUTION_CLAIM_ROOT",
        (private_root / "qualification_execution_claims").resolve(),
    )
    return private_root


def test_private_paths_are_confined_and_directory_binding_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    canonical = private_root / "qualification" / "run_one"
    lexical_alias = canonical / "child" / ".."

    assert private_qualification_output(canonical / "state.json") == (
        canonical / "state.json"
    ).resolve()
    assert normalized_private_output_directory(canonical) == (
        normalized_private_output_directory(lexical_alias)
    )
    with pytest.raises(ValueError, match="must stay under private_runs"):
        private_qualification_output(tmp_path / "public.json")
    with pytest.raises(ValueError, match="must be run-specific"):
        normalized_private_output_directory(private_root)


def test_claim_binds_plan_authorization_and_normalized_output_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    plan = _TestPlan(plan_id="plan_one")
    authorization = _TestAuthorization(authorization_id="authorization_one")
    output_directory = private_root / "qualification" / "run_one"

    claim = acquire_qualification_execution_claim(
        plan,
        authorization,
        output_directory / "child" / "..",
        claimed_at=NOW,
    )

    assert claim.execution_plan_sha256 == content_sha256(plan)
    assert claim.authorization_bundle_sha256 == content_sha256(authorization)
    assert claim.normalized_private_output_directory == (
        normalized_private_output_directory(output_directory)
    )
    assert validate_qualification_execution_claim(
        plan,
        authorization,
        output_directory,
    ) == claim
    with pytest.raises(ValueError, match="differs from its durable claim"):
        validate_qualification_execution_claim(
            plan,
            _TestAuthorization(authorization_id="replacement"),
            output_directory,
        )
    with pytest.raises(ValueError, match="differs from its durable claim"):
        validate_qualification_execution_claim(
            plan,
            authorization,
            private_root / "qualification" / "another_run",
        )


def test_existing_claim_always_blocks_automatic_rerun(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    plan = _TestPlan(plan_id="plan_one")
    authorization = _TestAuthorization(authorization_id="authorization_one")
    output_directory = private_root / "qualification" / "run_one"
    acquire_qualification_execution_claim(
        plan,
        authorization,
        output_directory,
        claimed_at=NOW,
    )

    with pytest.raises(ValueError, match="manual reconciliation required"):
        acquire_qualification_execution_claim(
            plan,
            authorization,
            output_directory,
            claimed_at=NOW,
        )
    with pytest.raises(ValueError, match="manual reconciliation required"):
        acquire_qualification_execution_claim(
            plan,
            _TestAuthorization(authorization_id="replacement"),
            private_root / "qualification" / "replacement_run",
            claimed_at=NOW,
        )


def test_claim_creation_is_exclusive_and_fsynced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    plan = _TestPlan(plan_id="plan_one")
    authorization = _TestAuthorization(authorization_id="authorization_one")
    barrier = Barrier(2)
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracked_fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr("eval.phase4_qualification_io.os.fsync", tracked_fsync)

    def attempt(index: int) -> str:
        barrier.wait()
        try:
            acquire_qualification_execution_claim(
                plan,
                authorization,
                private_root / "qualification" / f"run_{index}",
                claimed_at=NOW,
            )
        except ValueError as error:
            return str(error)
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    assert sorted(outcomes) == [
        "claimed",
        (
            "qualification execution plan is already claimed; "
            "manual reconciliation required"
        ),
    ]
    assert len(fsync_calls) == 1


def test_candidate_checkpoint_is_atomic_and_loads_typed_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    state_path = private_root / "qualification" / "run_one" / "candidate.json"

    checkpoint_qualification_candidate_state(
        state_path,
        _TestCandidateState(sequence=1),
    )
    checkpoint_qualification_candidate_state(
        state_path,
        _TestCandidateState(sequence=2),
    )

    assert load_private_qualification_contract(
        state_path,
        _TestCandidateState,
    ) == _TestCandidateState(sequence=2)
    assert state_path.read_text(encoding="utf-8").endswith("\n")
    assert list(state_path.parent.glob(f".{state_path.name}.*.tmp")) == []


def test_failed_atomic_replace_preserves_last_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    state_path = private_root / "qualification" / "run_one" / "candidate.json"
    checkpoint_qualification_candidate_state(
        state_path,
        _TestCandidateState(sequence=1),
    )

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("eval.phase4_qualification_io.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        checkpoint_qualification_candidate_state(
            state_path,
            _TestCandidateState(sequence=2),
        )

    assert load_private_qualification_contract(
        state_path,
        _TestCandidateState,
    ) == _TestCandidateState(sequence=1)
    assert list(state_path.parent.glob(f".{state_path.name}.*.tmp")) == []


def test_claim_requires_timezone_and_load_rejects_public_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_root = _redirect_private_roots(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="must include a timezone"):
        acquire_qualification_execution_claim(
            _TestPlan(plan_id="plan_one"),
            _TestAuthorization(authorization_id="authorization_one"),
            private_root / "qualification" / "run_one",
            claimed_at=datetime(2026, 8, 28),
        )
    public_path = tmp_path / "public.json"
    public_path.write_text('{"sequence":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="must stay under private_runs"):
        load_private_qualification_contract(public_path, _TestCandidateState)
