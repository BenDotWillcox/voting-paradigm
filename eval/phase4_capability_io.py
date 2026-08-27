"""Ignored-file boundaries shared by candidate capability runners."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import field_validator

from .contracts import ContractModel, Sha256Digest
from .fixture_io import content_sha256
from .phase4_provider import (
    ProviderHTTPErrorDiagnostic,
    ProviderStructuredOutputDiagnostic,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()
AUTHORIZATION_CONSUMPTION_CLAIM_ROOT = (
    PRIVATE_OUTPUT_ROOT / "authorization_consumption_claims"
).resolve()


class CapabilityAuthorizationConsumptionClaim(ContractModel):
    """Private, durable proof that one paid authorization was consumed."""

    record_version: Literal[
        "phase4_capability_authorization_consumption_claim.v1"
    ] = "phase4_capability_authorization_consumption_claim.v1"
    retry_plan_sha256: Sha256Digest
    authorization_bundle_sha256: Sha256Digest
    state_output_path_sha256: Sha256Digest
    claimed_at: datetime

    @field_validator("claimed_at")
    @classmethod
    def require_aware_claimed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "authorization consumption claim must include a timezone"
            )
        return value


def private_capability_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("candidate capability output must stay under private_runs")
    return resolved


def _state_output_path_sha256(state_output: Path) -> str:
    resolved = private_capability_output(state_output)
    private_relative = resolved.relative_to(PRIVATE_OUTPUT_ROOT)
    normalized = os.path.normcase(str(private_relative))
    return content_sha256({"private_state_output": normalized})


def _authorization_consumption_claim_path(
    retry_plan_sha256: Sha256Digest,
) -> Path:
    return (
        AUTHORIZATION_CONSUMPTION_CLAIM_ROOT
        / f"{retry_plan_sha256}.json"
    ).resolve()


def acquire_authorization_consumption_claim(
    retry_plan: ContractModel,
    authorization: ContractModel,
    state_output: Path,
    *,
    claimed_at: datetime,
) -> CapabilityAuthorizationConsumptionClaim:
    """Exclusively consume an authorization before any paid-send preparation."""

    claim = CapabilityAuthorizationConsumptionClaim(
        retry_plan_sha256=content_sha256(retry_plan),
        authorization_bundle_sha256=content_sha256(authorization),
        state_output_path_sha256=_state_output_path_sha256(state_output),
        claimed_at=claimed_at,
    )
    path = _authorization_consumption_claim_path(claim.retry_plan_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{claim.model_dump_json(indent=2)}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(
            "paid authorization is already claimed; manual reconciliation required"
        ) from error
    return claim


def validate_authorization_consumption_claim(
    retry_plan: ContractModel,
    authorization: ContractModel,
    state_output: Path,
) -> CapabilityAuthorizationConsumptionClaim:
    """Require an existing state to match its durable authorization claim."""

    retry_plan_sha256 = content_sha256(retry_plan)
    authorization_sha256 = content_sha256(authorization)
    path = _authorization_consumption_claim_path(retry_plan_sha256)
    if not path.is_file():
        raise ValueError(
            "paid execution state lacks its authorization consumption claim"
        )
    claim = CapabilityAuthorizationConsumptionClaim.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if (
        claim.retry_plan_sha256,
        claim.authorization_bundle_sha256,
        claim.state_output_path_sha256,
    ) != (
        retry_plan_sha256,
        authorization_sha256,
        _state_output_path_sha256(state_output),
    ):
        raise ValueError(
            "paid execution state differs from its authorization consumption claim"
        )
    return claim


def checkpoint_candidate_state(
    path: Path,
    state: ContractModel,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        f"{state.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validation_diagnostic_path(state_output: Path) -> Path:
    return state_output.with_name(
        f"{state_output.stem}_validation_diagnostic.json"
    )


def provider_error_diagnostic_path(state_output: Path) -> Path:
    return state_output.with_name(
        f"{state_output.stem}_provider_error_diagnostic.json"
    )


def write_validation_diagnostic(
    path: Path,
    diagnostic: ProviderStructuredOutputDiagnostic,
) -> None:
    if path.exists():
        existing = ProviderStructuredOutputDiagnostic.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if existing != diagnostic:
            raise ValueError("candidate validation diagnostic already differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        f"{diagnostic.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_provider_error_diagnostic(
    path: Path,
    diagnostic: ProviderHTTPErrorDiagnostic,
) -> None:
    if path.exists():
        existing = ProviderHTTPErrorDiagnostic.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if existing != diagnostic:
            raise ValueError("candidate provider-error diagnostic already differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        f"{diagnostic.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    temporary.replace(path)
