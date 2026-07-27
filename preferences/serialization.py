"""
Serialization helpers for PreferenceState <-> JSON (for DB storage).

The state is already serializable via dataclass.asdict, but we keep an explicit
module to isolate the JSON shape from the dataclass layout.

Back-compat: states written before the Evidence contract carry a `responses`
list (question_id / chosen_option_id / strength) and model_version
"thurstone_v1". `state_from_dict` upgrades them in place: legacy responses are
converted to pairwise Evidence (the item pair is recovered from the
"q{n}_{a}_vs_{b}" question-id convention) and the version is mapped to
"gaussian_linear_v1" — the posterior math is unchanged, only the name was
wrong.
"""

from dataclasses import asdict
from typing import Any, Optional

from .types import Evidence, EvidenceSource, PreferenceState

_LEGACY_VERSION_MAP = {"thurstone_v1": "gaussian_linear_v1"}


def state_to_dict(state: PreferenceState) -> dict[str, Any]:
    """Convert PreferenceState to a plain dict suitable for JSONB storage."""
    data = asdict(state)
    for ev in data.get("evidence", []):
        # asdict keeps the Enum instance; store the plain string.
        ev["source"] = (
            ev["source"].value
            if isinstance(ev["source"], EvidenceSource)
            else str(ev["source"])
        )
    return data


def state_from_dict(data: dict[str, Any]) -> PreferenceState:
    """Rebuild PreferenceState from a dict (as read from JSONB)."""
    if data.get("evidence") is not None:
        evidence = [_evidence_from_dict(e) for e in data["evidence"]]
    else:
        evidence = [
            ev
            for r in (data.get("responses") or [])
            if (ev := _legacy_response_to_evidence(r)) is not None
        ]
    model_version = data.get("model_version", "gaussian_linear_v1")
    model_version = _LEGACY_VERSION_MAP.get(model_version, model_version)
    return PreferenceState(
        user_id=data["user_id"],
        session_id=data["session_id"],
        item_ids=list(data["item_ids"]),
        mu=list(data["mu"]),
        sigma_flat=list(data["sigma_flat"]),
        evidence=evidence,
        n_questions_asked=data.get("n_questions_asked", 0),
        asked_question_ids=list(data.get("asked_question_ids", [])),
        model_version=model_version,
    )


def _evidence_from_dict(data: dict[str, Any]) -> Evidence:
    return Evidence(
        source=EvidenceSource(data["source"]),
        item_a=data["item_a"],
        item_b=data["item_b"],
        value=float(data["value"]),
        confidence=float(data.get("confidence", 1.0)),
        prompt_id=data.get("prompt_id"),
        raw_response=data.get("raw_response"),
        extracted_claims=list(data.get("extracted_claims", [])),
        response_time_ms=data.get("response_time_ms"),
        timestamp=data.get("timestamp"),
        metadata=dict(data.get("metadata", {})),
    )


def _legacy_response_to_evidence(data: dict[str, Any]) -> Optional[Evidence]:
    """Best-effort upgrade of a pre-Evidence response dict.

    The item pair only lived in the question id ("q{n}_{a}_vs_{b}"); if that
    convention doesn't parse, the response is dropped from the trail (the
    posterior in mu/sigma already reflects it, so nothing is lost except one
    audit entry).
    """
    question_id = data.get("question_id", "")
    try:
        rest = question_id.split("_", 1)[1]  # "{a}_vs_{b}"
        item_a, item_b = rest.split("_vs_")
    except (IndexError, ValueError):
        return None
    if not item_a or not item_b:
        return None

    chosen = data.get("chosen_option_id")
    strength = data.get("strength")
    abs_strength = abs(strength) if strength is not None else 5.0
    if chosen == item_a:
        value = abs_strength
    elif chosen == item_b:
        value = -abs_strength
    else:
        return None

    return Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a=item_a,
        item_b=item_b,
        value=value,
        prompt_id=question_id,
        response_time_ms=data.get("response_time_ms"),
        timestamp=data.get("timestamp"),
        metadata={"upgraded_from": "legacy_response"},
    )
