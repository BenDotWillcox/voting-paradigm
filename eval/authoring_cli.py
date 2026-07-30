"""Participant-safe error rendering for exact-content authoring commands."""

from __future__ import annotations

import json

from pydantic import ValidationError


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
