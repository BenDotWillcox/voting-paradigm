"""Participant-safe error rendering for exact-content authoring commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from pydantic import ValidationError


def aware_datetime_arg(value: str) -> datetime:
    """Parse a timezone-aware ISO-8601 CLI argument."""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "created-at must be an ISO-8601 datetime"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "created-at must include a timezone"
        )
    return parsed


def safe_authoring_error(error: Exception) -> str:
    """Describe an authoring failure without echoing restricted input values."""

    if isinstance(error, ValidationError):
        return (
            "schema validation failed with "
            f"{error.error_count()} issue(s); restricted details omitted"
        )
    if isinstance(error, json.JSONDecodeError):
        return (
            "JSON parsing failed at "
            f"line {error.lineno}, column {error.colno}; "
            "restricted details omitted"
        )
    if isinstance(error, OSError):
        return "authoring file operation failed; restricted details omitted"
    return "authoring validation failed; restricted details omitted"
