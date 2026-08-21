"""Run the authenticated, zero-inference Together catalog preflight.

This command never accepts an API key value as an argument.  It reads either
``TOGETHER_API_KEY`` from the process environment or one explicitly supplied
Git-ignored ``.env.local`` file.  The output must stay under
``eval/private_runs/`` and contains no secret or provider request content.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from .authoring_cli import safe_authoring_error
from .fixture_io import content_sha256
from .phase4_together import load_together_suite
from .phase4_together_live import (
    TogetherAccountPrivacyAttestation,
    TogetherCatalogPreflightBundle,
    TogetherCatalogPreflightClient,
    TogetherCatalogPreflightReceipt,
    build_catalog_preflight_authorization,
    fetch_public_source_reverification,
    load_together_api_key,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT_ROOT = (REPOSITORY_ROOT / "eval" / "private_runs").resolve()


def _context_window_diagnostics(
    receipt: TogetherCatalogPreflightReceipt,
) -> tuple[int, int]:
    mismatches = 0
    maximum_relative_difference_ppm = 0
    for item in receipt.candidate_checks:
        advertised = item.advertised_context_window_tokens
        live = item.live_context_window_tokens
        if advertised == live:
            continue
        mismatches += 1
        difference_ppm = (
            abs(live - advertised) * 1_000_000 + advertised - 1
        ) // advertised
        maximum_relative_difference_ppm = max(
            maximum_relative_difference_ppm,
            difference_ppm,
        )
    return mismatches, maximum_relative_difference_ppm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Revalidate public Together sources and the authenticated model "
            "catalog without invoking inference or spending provider credit."
        )
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--api-key-file",
        type=Path,
        help=(
            "Ignored local file containing TOGETHER_API_KEY; omit to use the "
            "process environment."
        ),
    )
    parser.add_argument(
        "--confirm-project-scoped-key",
        action="store_true",
    )
    parser.add_argument(
        "--confirm-training-sharing-disabled",
        action="store_true",
    )
    parser.add_argument(
        "--confirm-default-nonstorage",
        action="store_true",
    )
    parser.add_argument(
        "--acknowledge-temporary-caching",
        action="store_true",
    )
    parser.add_argument(
        "--execute-zero-spend",
        action="store_true",
        help="Required acknowledgement that authenticated network GETs will run.",
    )
    return parser


def _require_private_output(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE_OUTPUT_ROOT):
        raise ValueError("Together preflight output must stay under private_runs")
    return resolved


def _require_manual_confirmations(args: argparse.Namespace) -> None:
    if not all(
        (
            args.confirm_project_scoped_key,
            args.confirm_training_sharing_disabled,
            args.confirm_default_nonstorage,
            args.acknowledge_temporary_caching,
            args.execute_zero_spend,
        )
    ):
        raise ValueError("Together manual preflight confirmations are incomplete")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _require_manual_confirmations(args)
        output = _require_private_output(args.output)
        suite = load_together_suite(args.suite)
        api_key = load_together_api_key(local_env_file=args.api_key_file)
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        account = TogetherAccountPrivacyAttestation(
            attestation_id=f"together_account_privacy_{timestamp}",
            attestation_version=1,
            together_suite_id=suite.suite_id,
            together_suite_version=suite.suite_version,
            together_suite_sha256=content_sha256(suite),
            provider_terms_sha256=content_sha256(suite.provider_terms),
            checked_at=now,
        )
        with httpx.Client(
            follow_redirects=True,
            trust_env=False,
        ) as public_client:
            public_sources = fetch_public_source_reverification(
                suite,
                client=public_client,
                receipt_id=f"together_public_sources_{timestamp}",
                checked_at=now,
            )
        authorization = build_catalog_preflight_authorization(
            suite,
            account,
            public_sources,
            authorization_id=f"together_catalog_authorization_{timestamp}",
            approved_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        with httpx.Client(
            follow_redirects=False,
            trust_env=False,
        ) as authenticated_client:
            receipt = TogetherCatalogPreflightClient(
                suite,
                account,
                public_sources,
                authorization,
                api_key,
                client=authenticated_client,
                now=now,
            ).run(receipt_id=f"together_catalog_receipt_{timestamp}")
        bundle = TogetherCatalogPreflightBundle(
            bundle_id=f"together_catalog_bundle_{timestamp}",
            bundle_version=1,
            account_privacy_attestation=account,
            public_source_reverification=public_sources,
            authorization=authorization,
            receipt=receipt,
        )
        context_mismatches, maximum_context_difference_ppm = (
            _context_window_diagnostics(receipt)
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            f"{bundle.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "record_version": "phase4_together_catalog_preflight_cli.v1",
                    "bundle_sha256": content_sha256(bundle),
                    "candidate_count": len(receipt.candidate_checks),
                    "advertised_live_context_mismatch_count": (
                        context_mismatches
                    ),
                    "maximum_context_window_relative_difference_ppm": (
                        maximum_context_difference_ppm
                    ),
                    "public_source_request_count": len(
                        public_sources.source_checks
                    ),
                    "authenticated_catalog_request_count": 1,
                    "inference_request_count": 0,
                    "provider_spend_microusd": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
        httpx.HTTPError,
    ) as error:
        print(f"error: {safe_authoring_error(error)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
