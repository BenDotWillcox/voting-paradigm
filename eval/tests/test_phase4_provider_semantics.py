from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

import pytest
from pydantic import ValidationError

import eval.phase4_provider_semantics as provider_semantics
from eval.fixture_io import content_sha256
from eval.phase4_provider_semantics import (
    PROVIDER_RESPONSE_BEHAVIOR_SPEC,
    PROVIDER_RESPONSE_INVARIANT_MANIFEST,
    PROVIDER_RESPONSE_VALIDATOR_IMPLEMENTATION_SHA256,
    ProviderInvariantDisposition,
    build_public_capability_question,
    provider_response_adapter_for_role,
    provider_response_schema_for_role,
    validate_provider_response_semantic_runtime,
)
from eval.phase4_robustness import LLMRole
from eval.phase4_together import load_together_suite


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = ROOT / "requirements.txt"
LEGACY_V3_SUITE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_together_v3.json"
)


INVARIANT_ID_TO_EXERCISED_PROBE = {
    item.invariant_id: item.probe_id
    for item in PROVIDER_RESPONSE_BEHAVIOR_SPEC.probes
}


def _property_schema(schema: object, property_name: str) -> dict[str, object]:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            candidate = properties.get(property_name)
            if isinstance(candidate, dict):
                return candidate
        for value in schema.values():
            try:
                return _property_schema(value, property_name)
            except LookupError:
                pass
    elif isinstance(schema, list):
        for value in schema:
            try:
                return _property_schema(value, property_name)
            except LookupError:
                pass
    raise LookupError(property_name)


def test_invariant_manifest_covers_every_role_and_normalizer_binding() -> None:
    manifest = PROVIDER_RESPONSE_INVARIANT_MANIFEST

    assert {item.role for item in manifest.invariants} == set(LLMRole)
    assert {item.invariant_id for item in manifest.invariants} == {
        "interviewer_discriminated_action",
        "interviewer_clarification_lineage",
        "interviewer_capability_question_identity",
        "extractor_source_lineage_nonempty",
        "extractor_source_lineage_unique",
        "extractor_claim_pair_semantics",
        "extractor_claim_ontology_membership",
        "extractor_capability_grounded_nonempty",
        "ontology_source_lineage_nonempty",
        "ontology_reference_lists_canonical",
        "ontology_assumption_flags_canonical",
        "ontology_context_membership",
        "ontology_proposed_dimension_ids_unique",
        "ontology_capability_grounded_nonempty",
        "direct_readout_probability_simplex",
        "direct_readout_exact_option_coverage",
        "direct_readout_evidence_references_canonical",
        "direct_readout_eligible_evidence_only",
        "direct_readout_assumptions_canonical",
        "direct_readout_assumption_option_membership",
        "hybrid_readout_probability_simplex",
        "hybrid_readout_exact_option_coverage",
        "hybrid_readout_evidence_references_canonical",
        "hybrid_readout_eligible_evidence_only",
        "hybrid_readout_assumptions_canonical",
        "hybrid_readout_assumption_option_membership",
    }
    assert manifest.response_schema_versions == {
        LLMRole.INTERVIEWER: 2,
        LLMRole.EVIDENCE_EXTRACTOR: 2,
        LLMRole.ONTOLOGY_PROPOSER: 2,
        LLMRole.DIRECT_READOUT: 1,
        LLMRole.HYBRID_READOUT: 1,
    }
    normalized = [
        item
        for item in manifest.invariants
        if ProviderInvariantDisposition.NORMALIZED in item.dispositions
    ]
    assert normalized
    assert all(item.normalizer_id == manifest.normalizer_id for item in normalized)
    assert all(
        item.normalizer_version == manifest.normalizer_version
        for item in normalized
    )
    assert {
        "extractor_capability_grounded_nonempty",
        "ontology_capability_grounded_nonempty",
        "ontology_proposed_dimension_ids_unique",
        "interviewer_capability_question_identity",
    } <= {item.invariant_id for item in manifest.invariants}


def test_provider_response_behavior_identity_is_frozen() -> None:
    assert PROVIDER_RESPONSE_VALIDATOR_IMPLEMENTATION_SHA256 == (
        "f077e2713b7ba0e6735f07e0ee367cc6d2203074841f78afda86ca450c009a09"
    )


def test_behavior_identity_binds_conformance_field(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_semantics,
        "PROVIDER_CONFORMANCE_FIELD",
        "changed_provider_conformance_field",
    )

    assert content_sha256(
        provider_semantics._provider_response_validator_implementation_payload()
    ) != PROVIDER_RESPONSE_VALIDATOR_IMPLEMENTATION_SHA256


def test_provider_semantic_runtime_version_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(provider_semantics.pydantic, "__version__", "0.0.0")

    with pytest.raises(RuntimeError, match="require pydantic 2.13.4"):
        validate_provider_response_semantic_runtime()


def test_paid_provider_semantic_runtime_dependency_is_pinned() -> None:
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()

    assert "pydantic==2.13.4" in requirements


def test_v1_schemas_still_bind_the_exact_historical_v3_suite() -> None:
    legacy = load_together_suite(LEGACY_V3_SUITE_PATH)

    assert content_sha256(legacy) == (
        "657ec77bec315bc55b01bae8bbc3c5fb95b1f584a2a49d9979c515621f9cd9fa"
    )
    for contract in legacy.shared_role_contracts:
        assert contract.response_schema_version == 1
        assert contract.response_schema_sha256 == content_sha256(
            provider_response_schema_for_role(contract.role, 1)
        )


@pytest.mark.parametrize(
    ("role", "property_name", "minimum"),
    [
        (LLMRole.INTERVIEWER, "linked_evidence_event_ids", 1),
        (LLMRole.EVIDENCE_EXTRACTOR, "source_message_ids", 1),
        (LLMRole.ONTOLOGY_PROPOSER, "source_message_ids", 1),
        (LLMRole.DIRECT_READOUT, "affected_option_ids", 1),
        (LLMRole.HYBRID_READOUT, "affected_option_ids", 1),
    ],
)
def test_v2_schema_exposes_list_constraints(
    role: LLMRole,
    property_name: str,
    minimum: int,
) -> None:
    schema = provider_response_schema_for_role(role, 2)
    prop = _property_schema(schema, property_name)

    assert prop["uniqueItems"] is True
    assert prop["minItems"] == minimum
    assert "phase4_provider_response_normalizer.v1" in schema["description"]


def test_interviewer_adapter_requires_the_exact_public_question() -> None:
    question = build_public_capability_question(["item_b", "item_a"])
    input_payload = {
        "provider_response_conformance": {
            "contract_version": 1,
            "expected_vetted_question": question.model_dump(mode="json"),
        }
    }
    adapter = provider_response_adapter_for_role(
        LLMRole.INTERVIEWER,
        response_schema_version=2,
        input_payload=input_payload,
    )

    accepted = adapter.validate_python(
        {
            "record_version": "phase4_ask_vetted_question.v1",
            "action": "ask_vetted_question",
            "question": question.model_dump(mode="json"),
            "rendering_mode": "canonical_vetted",
        }
    )
    assert accepted.question == question

    with pytest.raises(ValidationError, match="exact vetted question"):
        adapter.validate_python(
            {
                "record_version": "phase4_pause_and_resume.v1",
                "action": "pause_and_resume",
            }
        )


def test_extractor_adapter_canonicalizes_pair_and_requires_exact_grounding() -> None:
    input_payload = {
        "participant_messages": [
            {
                "message_id": "public_extractor_conformance_message",
                "text": "I prefer item_a over item_b with strength 1.",
            }
        ],
        "active_ontology_dimension_ids": ["item_a", "item_b"],
        "provider_response_conformance": {
            "contract_version": 1,
            "required_source_message_id": "public_extractor_conformance_message",
            "required_claim": {
                "item_a": "item_a",
                "item_b": "item_b",
                "value": 1.0,
            },
        },
    }
    adapter = provider_response_adapter_for_role(
        LLMRole.EVIDENCE_EXTRACTOR,
        response_schema_version=2,
        input_payload=input_payload,
    )
    assert adapter.json_schema(mode="validation") == (
        provider_response_schema_for_role(LLMRole.EVIDENCE_EXTRACTOR, 2)
    )
    payload = [
        {
            "source_message_ids": [
                "public_extractor_conformance_message",
                "public_extractor_conformance_message",
            ],
            "claim": {
                "claim_text": "item_a matters more than item_b.",
                "item_a": "item_b",
                "item_b": "item_a",
                "value": -1.0,
            },
            "extractor_confidence": 0.9,
            "unsupported_assumptions": [],
        }
    ]

    accepted = adapter.validate_python(payload)
    assert accepted[0].source_message_ids == [
        "public_extractor_conformance_message"
    ]
    assert accepted[0].claim.item_a == "item_a"
    assert accepted[0].claim.item_b == "item_b"
    assert accepted[0].claim.value == 1.0

    with pytest.raises(ValidationError, match="exact grounded claim"):
        adapter.validate_python([])

    self_pair = payload[0].copy()
    self_pair["claim"] = {
        "claim_text": "item_a is compared with itself.",
        "item_a": "item_a",
        "item_b": "item_a",
        "value": 0.0,
    }
    with pytest.raises(ValidationError, match="claim items must be distinct"):
        adapter.validate_python([self_pair])


def _ontology_payload(dimension_id: str) -> dict[str, object]:
    return {
        "source_message_ids": ["public_ontology_gap_message"],
        "proposed_dimension": {
            "dimension_id": dimension_id,
            "name": "Reversible process",
            "definition": "Preference for a civic process that can repair errors.",
            "interpretation": "Higher values favor clearer reversible paths.",
        },
        "supporting_evidence_event_ids": ["public_ontology_gap_evidence"],
        "candidate_duplicate_dimension_ids": [],
        "extractor_confidence": 0.8,
        "unsupported_assumptions": [],
    }


def test_ontology_adapter_requires_grounding_and_unique_fresh_ids() -> None:
    input_payload = {
        "participant_messages": [
            {
                "message_id": "public_ontology_gap_message",
                "text": "This public preference is outside the active ontology.",
            }
        ],
        "active_ontology_dimension_ids": ["existing_dimension"],
        "retired_ontology_dimension_ids": [],
        "eligible_evidence_event_ids": ["public_ontology_gap_evidence"],
        "provider_response_conformance": {
            "contract_version": 1,
            "required_source_message_id": "public_ontology_gap_message",
            "required_evidence_event_id": "public_ontology_gap_evidence",
            "require_fresh_dimension": True,
        },
    }
    adapter = provider_response_adapter_for_role(
        LLMRole.ONTOLOGY_PROPOSER,
        response_schema_version=2,
        input_payload=input_payload,
    )

    accepted = adapter.validate_python([_ontology_payload("reversible_process")])
    assert accepted[0].proposed_dimension.dimension_id == "reversible_process"

    with pytest.raises(ValidationError, match="must be unique"):
        adapter.validate_python(
            [
                _ontology_payload("reversible_process"),
                _ontology_payload("reversible_process"),
            ]
        )
    with pytest.raises(ValidationError, match="grounded fresh proposal"):
        adapter.validate_python([])


@pytest.mark.parametrize(
    "role",
    [LLMRole.DIRECT_READOUT, LLMRole.HYBRID_READOUT],
)
def test_readout_adapter_requires_exact_options_and_eligible_citation(
    role: LLMRole,
) -> None:
    adapter = provider_response_adapter_for_role(
        role,
        response_schema_version=1,
        input_payload={
            "canonical_option_ids": ["option_a", "option_b"],
            "eligible_evidence_event_ids": ["evidence_one"],
        },
        bind_request_semantics=True,
    )
    assert adapter.json_schema(mode="validation") == (
        provider_response_schema_for_role(role, 1)
    )
    accepted = adapter.validate_python(
        {
            "option_probabilities": {"option_a": 0.4, "option_b": 0.6},
            "settled_probability": 0.6,
            "supporting_evidence_event_ids": ["evidence_one", "evidence_one"],
            "unsupported_assumptions": [],
        }
    )
    assert accepted.supporting_evidence_event_ids == ["evidence_one"]

    with pytest.raises(ValidationError, match="must cite eligible evidence"):
        adapter.validate_python(
            {
                "option_probabilities": {"option_a": 0.4, "option_b": 0.6},
                "settled_probability": 0.6,
                "supporting_evidence_event_ids": [],
                "unsupported_assumptions": [],
            }
        )


def _interviewer_probe_adapter():
    question = build_public_capability_question(["item_b", "item_a"])
    adapter = provider_response_adapter_for_role(
        LLMRole.INTERVIEWER,
        response_schema_version=2,
        input_payload={
            "provider_response_conformance": {
                "contract_version": 1,
                "expected_vetted_question": question.model_dump(mode="json"),
            }
        },
    )
    return adapter, question


def _extractor_probe_adapter():
    input_payload = {
        "participant_messages": [
            {
                "message_id": "public_extractor_conformance_message",
                "text": "I prefer item_a over item_b with strength 1.",
            }
        ],
        "active_ontology_dimension_ids": ["item_a", "item_b"],
        "provider_response_conformance": {
            "contract_version": 1,
            "required_source_message_id": "public_extractor_conformance_message",
            "required_claim": {
                "item_a": "item_a",
                "item_b": "item_b",
                "value": 1.0,
            },
        },
    }
    return provider_response_adapter_for_role(
        LLMRole.EVIDENCE_EXTRACTOR,
        response_schema_version=2,
        input_payload=input_payload,
    )


def _extractor_probe_payload() -> list[dict[str, object]]:
    return [
        {
            "source_message_ids": ["public_extractor_conformance_message"],
            "claim": {
                "claim_text": "item_a matters more than item_b.",
                "item_a": "item_a",
                "item_b": "item_b",
                "value": 1.0,
            },
            "extractor_confidence": 0.9,
            "unsupported_assumptions": [],
        }
    ]


def _ontology_probe_adapter():
    return provider_response_adapter_for_role(
        LLMRole.ONTOLOGY_PROPOSER,
        response_schema_version=2,
        input_payload={
            "participant_messages": [
                {
                    "message_id": "public_ontology_gap_message",
                    "text": "This public preference is outside the active ontology.",
                }
            ],
            "active_ontology_dimension_ids": ["existing_dimension"],
            "retired_ontology_dimension_ids": ["retired_dimension"],
            "eligible_evidence_event_ids": ["public_ontology_gap_evidence"],
            "provider_response_conformance": {
                "contract_version": 1,
                "required_source_message_id": "public_ontology_gap_message",
                "required_evidence_event_id": "public_ontology_gap_evidence",
                "require_fresh_dimension": True,
            },
        },
    )


def _readout_probe_adapter(role: LLMRole):
    return provider_response_adapter_for_role(
        role,
        response_schema_version=1,
        input_payload={
            "canonical_option_ids": ["option_a", "option_b"],
            "eligible_evidence_event_ids": ["evidence_one"],
        },
        bind_request_semantics=True,
    )


def _readout_probe_payload() -> dict[str, object]:
    return {
        "option_probabilities": {"option_a": 0.4, "option_b": 0.6},
        "settled_probability": 0.6,
        "supporting_evidence_event_ids": ["evidence_one"],
        "unsupported_assumptions": [],
    }


def _probe_interviewer_discriminator() -> None:
    adapter, _ = _interviewer_probe_adapter()
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        adapter.validate_python({"action": "invented_action"})


def _probe_interviewer_lineage() -> None:
    adapter, _ = _interviewer_probe_adapter()
    payload = {
        "record_version": "phase4_clarify_existing_evidence.v1",
        "action": "clarify_existing_evidence",
        "clarification_kind": "confirm_scope",
        "linked_evidence_event_ids": [],
    }
    with pytest.raises(ValidationError, match="at least one evidence id"):
        adapter.validate_python(payload)
    payload["linked_evidence_event_ids"] = ["evidence_one", "evidence_one"]
    with pytest.raises(ValidationError, match="must be unique"):
        adapter.validate_python(payload)


def _probe_interviewer_exact_question() -> None:
    adapter, _ = _interviewer_probe_adapter()
    with pytest.raises(ValidationError, match="exact vetted question"):
        adapter.validate_python(
            {
                "record_version": "phase4_pause_and_resume.v1",
                "action": "pause_and_resume",
            }
        )


def _probe_extractor_source_references() -> None:
    adapter = _extractor_probe_adapter()
    payload = _extractor_probe_payload()
    payload[0]["source_message_ids"] = []
    with pytest.raises(ValidationError, match="requires participant source"):
        adapter.validate_python(payload)
    payload[0]["source_message_ids"] = ["invented_message"]
    with pytest.raises(ValidationError, match="unknown participant message"):
        adapter.validate_python(payload)


def _probe_extractor_reference_normalization() -> None:
    adapter = _extractor_probe_adapter()
    payload = _extractor_probe_payload()
    payload[0]["source_message_ids"] = [
        "public_extractor_conformance_message",
        "public_extractor_conformance_message",
    ]
    assumption = {
        "flag_id": "assumption_one",
        "description": "A public assumption.",
    }
    payload[0]["unsupported_assumptions"] = [assumption, assumption]
    accepted = adapter.validate_python(payload)
    assert accepted[0].source_message_ids == [
        "public_extractor_conformance_message"
    ]
    assert len(accepted[0].unsupported_assumptions) == 1


def _probe_extractor_pair_normalization() -> None:
    adapter = _extractor_probe_adapter()
    payload = _extractor_probe_payload()
    claim = payload[0]["claim"]
    assert isinstance(claim, dict)
    claim.update({"item_a": "item_b", "item_b": "item_a", "value": -1.0})
    accepted = adapter.validate_python(payload)
    assert accepted[0].claim.item_a == "item_a"
    assert accepted[0].claim.item_b == "item_b"
    assert accepted[0].claim.value == 1.0


def _probe_extractor_unknown_item() -> None:
    adapter = _extractor_probe_adapter()
    payload = _extractor_probe_payload()
    claim = payload[0]["claim"]
    assert isinstance(claim, dict)
    claim["item_b"] = "invented_item"
    with pytest.raises(ValidationError, match="unknown ontology item"):
        adapter.validate_python(payload)


def _probe_extractor_grounded_nonempty() -> None:
    with pytest.raises(ValidationError, match="exact grounded claim"):
        _extractor_probe_adapter().validate_python([])


def _probe_ontology_source_references() -> None:
    adapter = _ontology_probe_adapter()
    payload = _ontology_payload("reversible_process")
    payload["source_message_ids"] = []
    with pytest.raises(ValidationError, match="requires participant messages"):
        adapter.validate_python([payload])
    payload["source_message_ids"] = ["invented_message"]
    with pytest.raises(ValidationError, match="unknown participant message"):
        adapter.validate_python([payload])


def _probe_ontology_reference_normalization() -> None:
    adapter = _ontology_probe_adapter()
    payload = _ontology_payload("reversible_process")
    payload["source_message_ids"] = [
        "public_ontology_gap_message",
        "public_ontology_gap_message",
    ]
    payload["supporting_evidence_event_ids"] = [
        "public_ontology_gap_evidence",
        "public_ontology_gap_evidence",
    ]
    payload["candidate_duplicate_dimension_ids"] = [
        "existing_dimension",
        "existing_dimension",
    ]
    accepted = adapter.validate_python([payload])[0]
    assert accepted.source_message_ids == ["public_ontology_gap_message"]
    assert accepted.supporting_evidence_event_ids == [
        "public_ontology_gap_evidence"
    ]
    assert accepted.candidate_duplicate_dimension_ids == ["existing_dimension"]


def _probe_ontology_assumption_normalization() -> None:
    adapter = _ontology_probe_adapter()
    payload = _ontology_payload("reversible_process")
    assumption = {
        "flag_id": "assumption_one",
        "description": "A public assumption.",
    }
    payload["unsupported_assumptions"] = [assumption, assumption]
    accepted = adapter.validate_python([payload])[0]
    assert len(accepted.unsupported_assumptions) == 1
    conflicting = deepcopy(assumption)
    conflicting["description"] = "A conflicting description."
    payload["unsupported_assumptions"] = [assumption, conflicting]
    with pytest.raises(ValidationError, match="flag ids must be unique"):
        adapter.validate_python([payload])


def _probe_ontology_context_references() -> None:
    adapter = _ontology_probe_adapter()
    cases = [
        (
            {"supporting_evidence_event_ids": ["invented_evidence"]},
            "ineligible evidence",
        ),
        (
            {"candidate_duplicate_dimension_ids": ["invented_dimension"]},
            "unknown duplicate dimension",
        ),
        (
            {
                "proposed_dimension": {
                    "dimension_id": "existing_dimension",
                    "name": "Existing",
                    "definition": "An existing active dimension.",
                    "interpretation": "Higher means more of the existing value.",
                }
            },
            "fresh dimension id",
        ),
        (
            {
                "proposed_dimension": {
                    "dimension_id": "retired_dimension",
                    "name": "Retired",
                    "definition": "A retired ontology dimension.",
                    "interpretation": "Higher means more of the retired value.",
                }
            },
            "fresh dimension id",
        ),
    ]
    for updates, message in cases:
        payload = _ontology_payload("reversible_process")
        payload.update(updates)
        with pytest.raises(ValidationError, match=message):
            adapter.validate_python([payload])


def _probe_ontology_unique_proposed_ids() -> None:
    adapter = _ontology_probe_adapter()
    with pytest.raises(ValidationError, match="must be unique"):
        adapter.validate_python(
            [
                _ontology_payload("reversible_process"),
                _ontology_payload("reversible_process"),
            ]
        )


def _probe_ontology_grounded_nonempty() -> None:
    with pytest.raises(ValidationError, match="grounded fresh proposal"):
        _ontology_probe_adapter().validate_python([])


def _probe_readout_probability_simplex(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    payload["option_probabilities"] = {"option_a": 0.4, "option_b": 0.5}
    with pytest.raises(ValidationError, match="probabilities must sum to one"):
        _readout_probe_adapter(role).validate_python(payload)


def _probe_readout_option_coverage(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    payload["option_probabilities"] = {"option_a": 0.4, "option_c": 0.6}
    with pytest.raises(ValidationError, match="canonical options exactly"):
        _readout_probe_adapter(role).validate_python(payload)


def _probe_readout_evidence_normalization(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    payload["supporting_evidence_event_ids"] = ["evidence_one", "evidence_one"]
    accepted = _readout_probe_adapter(role).validate_python(payload)
    assert accepted.supporting_evidence_event_ids == ["evidence_one"]


def _probe_readout_evidence_eligibility(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    payload["supporting_evidence_event_ids"] = ["invented_evidence"]
    with pytest.raises(ValidationError, match="ineligible evidence"):
        _readout_probe_adapter(role).validate_python(payload)
    payload["supporting_evidence_event_ids"] = []
    with pytest.raises(ValidationError, match="must cite eligible evidence"):
        _readout_probe_adapter(role).validate_python(payload)


def _probe_readout_assumption_normalization(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    assumption = {
        "assumption_id": "assumption_one",
        "description": "A public assumption.",
        "affected_option_ids": ["option_b", "option_a", "option_b"],
    }
    payload["unsupported_assumptions"] = [assumption, assumption]
    accepted = _readout_probe_adapter(role).validate_python(payload)
    assert len(accepted.unsupported_assumptions) == 1
    assert accepted.unsupported_assumptions[0].affected_option_ids == [
        "option_a",
        "option_b",
    ]
    conflicting = deepcopy(assumption)
    conflicting["description"] = "A conflicting description."
    payload["unsupported_assumptions"] = [assumption, conflicting]
    with pytest.raises(ValidationError, match="assumption ids must be unique"):
        _readout_probe_adapter(role).validate_python(payload)


def _probe_readout_assumption_options(role: LLMRole) -> None:
    payload = _readout_probe_payload()
    payload["unsupported_assumptions"] = [
        {
            "assumption_id": "assumption_one",
            "description": "A public assumption.",
            "affected_option_ids": ["invented_option"],
        }
    ]
    with pytest.raises(ValidationError, match="unknown option"):
        _readout_probe_adapter(role).validate_python(payload)


ADVERSARIAL_PROBES: dict[str, Callable[[], None]] = {
    "interviewer_discriminator": _probe_interviewer_discriminator,
    "interviewer_lineage": _probe_interviewer_lineage,
    "interviewer_exact_question": _probe_interviewer_exact_question,
    "extractor_source_references": _probe_extractor_source_references,
    "extractor_reference_normalization": _probe_extractor_reference_normalization,
    "extractor_pair_normalization": _probe_extractor_pair_normalization,
    "extractor_unknown_item": _probe_extractor_unknown_item,
    "extractor_grounded_nonempty": _probe_extractor_grounded_nonempty,
    "ontology_source_references": _probe_ontology_source_references,
    "ontology_reference_normalization": _probe_ontology_reference_normalization,
    "ontology_assumption_normalization": _probe_ontology_assumption_normalization,
    "ontology_context_references": _probe_ontology_context_references,
    "ontology_unique_proposed_ids": _probe_ontology_unique_proposed_ids,
    "ontology_grounded_nonempty": _probe_ontology_grounded_nonempty,
    "direct_probability_simplex": lambda: _probe_readout_probability_simplex(
        LLMRole.DIRECT_READOUT
    ),
    "direct_option_coverage": lambda: _probe_readout_option_coverage(
        LLMRole.DIRECT_READOUT
    ),
    "direct_evidence_normalization": lambda: (
        _probe_readout_evidence_normalization(LLMRole.DIRECT_READOUT)
    ),
    "direct_evidence_eligibility": lambda: _probe_readout_evidence_eligibility(
        LLMRole.DIRECT_READOUT
    ),
    "direct_assumption_normalization": lambda: (
        _probe_readout_assumption_normalization(LLMRole.DIRECT_READOUT)
    ),
    "direct_assumption_options": lambda: _probe_readout_assumption_options(
        LLMRole.DIRECT_READOUT
    ),
    "hybrid_probability_simplex": lambda: _probe_readout_probability_simplex(
        LLMRole.HYBRID_READOUT
    ),
    "hybrid_option_coverage": lambda: _probe_readout_option_coverage(
        LLMRole.HYBRID_READOUT
    ),
    "hybrid_evidence_normalization": lambda: (
        _probe_readout_evidence_normalization(LLMRole.HYBRID_READOUT)
    ),
    "hybrid_evidence_eligibility": lambda: _probe_readout_evidence_eligibility(
        LLMRole.HYBRID_READOUT
    ),
    "hybrid_assumption_normalization": lambda: (
        _probe_readout_assumption_normalization(LLMRole.HYBRID_READOUT)
    ),
    "hybrid_assumption_options": lambda: _probe_readout_assumption_options(
        LLMRole.HYBRID_READOUT
    ),
}


def test_every_manifest_invariant_has_one_exercised_adversarial_probe() -> None:
    manifest_ids = {
        item.invariant_id for item in PROVIDER_RESPONSE_INVARIANT_MANIFEST.invariants
    }

    assert set(INVARIANT_ID_TO_EXERCISED_PROBE) == manifest_ids
    assert set(INVARIANT_ID_TO_EXERCISED_PROBE.values()) == set(
        ADVERSARIAL_PROBES
    )


@pytest.mark.parametrize("probe_name", sorted(ADVERSARIAL_PROBES))
def test_provider_response_adversarial_probe(probe_name: str) -> None:
    ADVERSARIAL_PROBES[probe_name]()
