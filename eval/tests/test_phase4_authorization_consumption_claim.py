from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from eval.contracts import ContractModel
from eval.phase4_capability_io import (
    acquire_authorization_consumption_claim,
    validate_authorization_consumption_claim,
)


class _TestAuthorization(ContractModel):
    authorization_id: str


class _TestPlan(ContractModel):
    plan_id: str


def _redirect_private_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import eval.phase4_capability_io as capability_io

    monkeypatch.setattr(capability_io, "PRIVATE_OUTPUT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        capability_io,
        "AUTHORIZATION_CONSUMPTION_CLAIM_ROOT",
        (tmp_path / "claims").resolve(),
    )


def test_one_retry_plan_cannot_claim_two_authorizations_or_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _redirect_private_roots(monkeypatch, tmp_path)
    plan = _TestPlan(plan_id="one")
    first_authorization = _TestAuthorization(authorization_id="one")
    replacement_authorization = _TestAuthorization(authorization_id="two")
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"

    with pytest.raises(ValueError, match="lacks its authorization"):
        validate_authorization_consumption_claim(
            plan,
            first_authorization,
            first_output,
        )
    acquire_authorization_consumption_claim(
        plan,
        first_authorization,
        first_output,
        claimed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="authorization is already claimed"):
        acquire_authorization_consumption_claim(
            plan,
            replacement_authorization,
            first_output,
            claimed_at=datetime(2026, 8, 27, 0, 0, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="authorization is already claimed"):
        acquire_authorization_consumption_claim(
            plan,
            first_authorization,
            second_output,
            claimed_at=datetime(2026, 8, 27, 0, 0, 2, tzinfo=timezone.utc),
        )
    validate_authorization_consumption_claim(
        plan,
        first_authorization,
        first_output,
    )
    with pytest.raises(ValueError, match="differs from its authorization"):
        validate_authorization_consumption_claim(
            plan,
            first_authorization,
            second_output,
        )


def test_authorization_claim_creation_is_exclusive_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _redirect_private_roots(monkeypatch, tmp_path)
    plan = _TestPlan(plan_id="one")
    authorization = _TestAuthorization(authorization_id="one")
    barrier = Barrier(2)

    def attempt(index: int) -> str:
        barrier.wait()
        try:
            acquire_authorization_consumption_claim(
                plan,
                authorization,
                tmp_path / f"state_{index}.json",
                claimed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )
        except ValueError as error:
            return str(error)
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, range(2)))

    assert sorted(outcomes) == [
        "claimed",
        "paid authorization is already claimed; manual reconciliation required",
    ]
