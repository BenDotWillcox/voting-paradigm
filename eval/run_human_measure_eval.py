"""Run the deterministic Phase 2 development replay.

The command writes only the aggregate allowlisted artifact. Private replay
records remain in memory and must be stored under ``eval/private_runs/`` by any
future explicitly approved human workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .development import (
    FIXTURE_PATH,
    SESSION_SCRIPT_PATH,
    build_development_adapters,
    development_public_model_descriptors,
)
from .fixture_io import load_fixture, validate_development_fixture
from .human_metrics import compute_human_measure_metrics
from .prequential import (
    DEFAULT_DELEGATION_THRESHOLDS,
    load_session_script,
    run_prequential_session,
    validate_session_script_against_fixture,
)
from .public_artifact import build_public_artifact, render_public_summary

DEFAULT_OUTPUT_PATH = (
    Path(__file__).parent
    / "results"
    / "human_measure_dev_phase2.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the synthetic human-measure development session and "
            "write an aggregate public-safe artifact."
        )
    )
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument(
        "--session-script",
        type=Path,
        default=SESSION_SCRIPT_PATH,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--threshold",
        type=float,
        action="append",
        dest="thresholds",
        help=(
            "Delegation threshold to report; repeat for multiple values "
            "(default: 0.65, 0.75, 0.85, 0.95)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    thresholds = tuple(args.thresholds or DEFAULT_DELEGATION_THRESHOLDS)
    try:
        fixture = load_fixture(args.fixture)
        validate_development_fixture(fixture)
        script = load_session_script(args.session_script)
        validate_session_script_against_fixture(script, fixture)
        replay = run_prequential_session(
            fixture=fixture,
            script=script,
            adapters=build_development_adapters(fixture),
            delegation_thresholds=thresholds,
        )
        metrics = compute_human_measure_metrics(
            replay,
            candidate_thresholds=thresholds,
        )
        artifact = build_public_artifact(
            fixture=fixture,
            replay=replay,
            metrics=metrics,
            public_model_descriptors=(
                development_public_model_descriptors()
            ),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            artifact.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(render_public_summary(artifact))
    print(f"\nPublic artifact written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
