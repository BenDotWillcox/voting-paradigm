"""Ignored-file boundaries shared by candidate capability runners."""

from __future__ import annotations

from pathlib import Path

from .contracts import ContractModel
from .phase4_provider import ProviderStructuredOutputDiagnostic


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()


def private_capability_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("candidate capability output must stay under private_runs")
    return resolved


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
