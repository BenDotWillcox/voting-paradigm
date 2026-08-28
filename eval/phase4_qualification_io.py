"""Ignored private-file boundary for two-deployment qualification runs.

The paid runner must acquire its durable execution claim before it loads a
credential or constructs an HTTP client.  The claim is intentionally
single-use: once it exists, no automatic rerun is permitted even when the
authorization and output directory are unchanged.  A crash after claiming
therefore requires manual provider-side reconciliation instead of risking a
duplicate paid send.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import field_validator

from .contracts import ContractModel, NonEmptyText, Sha256Digest
from .fixture_io import content_sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()
QUALIFICATION_EXECUTION_CLAIM_ROOT = (
    PRIVATE_OUTPUT_ROOT / "qualification_execution_claims"
).resolve()

PrivateContract = TypeVar("PrivateContract", bound=ContractModel)


class QualificationExecutionClaim(ContractModel):
    """Durable private proof that an exact paid plan was consumed once."""

    record_version: Literal[
        "phase4_two_deployment_qualification_execution_claim.v1"
    ] = "phase4_two_deployment_qualification_execution_claim.v1"
    execution_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    normalized_private_output_directory: NonEmptyText
    claimed_at: datetime

    @field_validator("claimed_at")
    @classmethod
    def require_aware_claimed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("qualification execution claim must include a timezone")
        return value


def private_qualification_output(path: Path) -> Path:
    """Resolve one file or directory and confine it below ``private_runs``."""

    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("qualification output must stay under private_runs")
    return resolved


def private_qualification_output_directory(path: Path) -> Path:
    """Resolve a run-specific directory below the ignored private root."""

    resolved = private_qualification_output(path)
    if resolved == PRIVATE_OUTPUT_ROOT:
        raise ValueError("qualification output directory must be run-specific")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("qualification output directory must be a directory")
    return resolved


def normalized_private_output_directory(path: Path) -> str:
    """Return the canonical machine-local directory binding stored in claims."""

    resolved = private_qualification_output_directory(path)
    relative = resolved.relative_to(PRIVATE_OUTPUT_ROOT)
    normalized = os.path.normcase(relative.as_posix()).replace("\\", "/")
    if normalized in {"", "."}:
        raise ValueError("qualification output directory must be run-specific")
    return normalized


def qualification_execution_claim_path(
    execution_plan_sha256: Sha256Digest,
) -> Path:
    """Return the private claim path keyed only by the exact execution plan."""

    return private_qualification_output(
        QUALIFICATION_EXECUTION_CLAIM_ROOT
        / f"{execution_plan_sha256}.json"
    )


def acquire_qualification_execution_claim(
    execution_plan: ContractModel,
    authorization: ContractModel,
    private_output_directory: Path,
    *,
    claimed_at: datetime,
) -> QualificationExecutionClaim:
    """Irreversibly claim a paid plan before credential or client preparation."""

    claim = QualificationExecutionClaim(
        execution_plan_sha256=content_sha256(execution_plan),
        authorization_bundle_sha256=content_sha256(authorization),
        normalized_private_output_directory=normalized_private_output_directory(
            private_output_directory
        ),
        claimed_at=claimed_at,
    )
    path = qualification_execution_claim_path(claim.execution_plan_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{claim.model_dump_json(indent=2)}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(
            "qualification execution plan is already claimed; "
            "manual reconciliation required"
        ) from error
    return claim


def validate_qualification_execution_claim(
    execution_plan: ContractModel,
    authorization: ContractModel,
    private_output_directory: Path,
) -> QualificationExecutionClaim:
    """Validate the durable claim without making it reusable."""

    execution_plan_sha256 = content_sha256(execution_plan)
    path = qualification_execution_claim_path(execution_plan_sha256)
    if not path.is_file():
        raise ValueError("qualification execution state lacks its durable claim")
    claim = QualificationExecutionClaim.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    expected = (
        execution_plan_sha256,
        content_sha256(authorization),
        normalized_private_output_directory(private_output_directory),
    )
    actual = (
        claim.execution_plan_sha256,
        claim.authorization_bundle_sha256,
        claim.normalized_private_output_directory,
    )
    if actual != expected:
        raise ValueError(
            "qualification execution state differs from its durable claim"
        )
    return claim


def _atomic_write_contract(path: Path, value: ContractModel) -> None:
    resolved = private_qualification_output(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=resolved.parent,
        prefix=f".{resolved.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{value.model_dump_json(indent=2)}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, resolved)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def checkpoint_qualification_candidate_state(
    path: Path,
    state: ContractModel,
) -> None:
    """Atomically replace one candidate's private progressive state."""

    _atomic_write_contract(path, state)


def load_private_qualification_contract(
    path: Path,
    model_type: type[PrivateContract],
) -> PrivateContract:
    """Load a typed contract only from the ignored private boundary."""

    resolved = private_qualification_output(path)
    return model_type.model_validate_json(resolved.read_text(encoding="utf-8"))
