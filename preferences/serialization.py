"""
Serialization helpers for PreferenceState <-> JSON (for DB storage).

The state is already serializable via dataclass.asdict, but we keep an explicit
module to isolate the JSON shape from the dataclass layout.
"""

from dataclasses import asdict
from typing import Any

from .types import PreferenceState, Response


def state_to_dict(state: PreferenceState) -> dict[str, Any]:
    """Convert PreferenceState to a plain dict suitable for JSONB storage."""
    return asdict(state)


def state_from_dict(data: dict[str, Any]) -> PreferenceState:
    """Rebuild PreferenceState from a dict (as read from JSONB)."""
    responses = [
        Response(
            question_id=r["question_id"],
            chosen_option_id=r["chosen_option_id"],
            strength=r.get("strength"),
            response_time_ms=r.get("response_time_ms"),
            timestamp=r.get("timestamp"),
        )
        for r in data.get("responses", [])
    ]
    return PreferenceState(
        user_id=data["user_id"],
        session_id=data["session_id"],
        item_ids=list(data["item_ids"]),
        mu=list(data["mu"]),
        sigma_flat=list(data["sigma_flat"]),
        responses=responses,
        n_questions_asked=data.get("n_questions_asked", 0),
        asked_question_ids=list(data.get("asked_question_ids", [])),
        model_version=data.get("model_version", "thurstone_v1"),
    )
