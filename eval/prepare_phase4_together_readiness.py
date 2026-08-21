"""Build the no-inference Together tokenizer and execution-readiness bundle."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import load_fixture
from .phase4_readiness import (
    ExactTokenCounter,
    build_held_out_calibration_manifest,
    build_qualification_request_manifest,
    build_qualification_resume_cursor,
    build_readiness_bundle,
    load_exact_tokenizer_from_snapshot,
    readiness_summary,
)
from .phase4_robustness import load_phase4_robustness_profile
from .phase4_semantic import load_authored_semantic_map
from .phase4_together import load_together_suite
from .prequential import load_session_script


QUALIFICATION_MINIMUM_HEADROOM_MICROUSD = 400_000
HELD_OUT_MINIMUM_HEADROOM_MICROUSD = 500_000
TOKENIZER_FILE_PATTERNS = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "chat_template.jinja",
    "tokenizer.model",
    "spiece.model",
    "vocab.json",
    "merges.txt",
    "added_tokens.json",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download revision-pinned tokenizer files only, exactly count the "
            "public Phase 4E qualification and held-out calibration payloads, "
            "and write a zero-inference readiness artifact."
        )
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("development_fixture", type=Path)
    parser.add_argument("development_session", type=Path)
    parser.add_argument("development_semantic_map", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--tokenizer-cache",
        type=Path,
        default=Path(".cache/eval-tokenizers/phase4e"),
    )
    parser.add_argument(
        "--download-tokenizers",
        action="store_true",
        help=(
            "Allow Hugging Face tokenizer-file downloads. No model weights, "
            "Together API request, inference call, or provider spend occurs."
        ),
    )
    return parser


def _load_tokenizers(
    suite,
    cache_root: Path,
    *,
    allow_download: bool,
) -> dict[str, ExactTokenCounter]:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError(
            "huggingface-hub is required for tokenizer readiness"
        ) from error
    library_version = importlib.metadata.version("tokenizers")
    counters: dict[str, ExactTokenCounter] = {}
    for container in sorted(
        suite.candidates,
        key=lambda item: item.candidate.candidate_id,
    ):
        candidate = container.candidate
        local_dir = (
            cache_root
            / candidate.candidate_id
            / candidate.upstream_model_revision
        )
        snapshot = snapshot_download(
            repo_id=candidate.upstream_model_id,
            revision=candidate.upstream_model_revision,
            allow_patterns=TOKENIZER_FILE_PATTERNS,
            local_dir=local_dir,
            local_files_only=not allow_download,
        )
        counters[candidate.candidate_id] = load_exact_tokenizer_from_snapshot(
            candidate,
            Path(snapshot),
            tokenizer_library_version=library_version,
        )
    return counters


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suite = load_together_suite(args.suite)
        profile = load_phase4_robustness_profile(args.profile)
        fixture = load_fixture(args.development_fixture)
        session = load_session_script(args.development_session)
        semantic_map = load_authored_semantic_map(
            args.development_semantic_map
        )
        counters = _load_tokenizers(
            suite,
            args.tokenizer_cache,
            allow_download=args.download_tokenizers,
        )
        qualification = build_qualification_request_manifest(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            counters,
        )
        calibration = build_held_out_calibration_manifest(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            counters,
        )
        bundle = build_readiness_bundle(
            suite,
            profile,
            fixture,
            session,
            semantic_map,
            tokenizer_artifacts=[
                counters[candidate_id].artifact
                for candidate_id in sorted(counters)
            ],
            qualification_manifest=qualification,
            held_out_calibration_manifest=calibration,
            qualification_minimum_headroom_microusd=(
                QUALIFICATION_MINIMUM_HEADROOM_MICROUSD
            ),
            held_out_minimum_headroom_microusd=(
                HELD_OUT_MINIMUM_HEADROOM_MICROUSD
            ),
        )
        cursor = build_qualification_resume_cursor(qualification)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"{bundle.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        summary = readiness_summary(bundle)
        summary["dry_run_next_call_id_present"] = cursor.next_call_id is not None
        summary["dry_run_remaining_call_count"] = cursor.remaining_call_count
        print(json.dumps(summary, indent=2, sort_keys=True))
    except (
        OSError,
        RuntimeError,
        ValidationError,
        ValueError,
    ) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
