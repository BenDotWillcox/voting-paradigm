"""Versioned provider-response schemas and request-bound semantic checks.

Pydantic's generated JSON Schema cannot express every relational invariant used
by the Phase 4 role contracts.  This module makes that boundary explicit:

* v1 wire schemas remain byte-for-byte historical;
* v2 adds provider-visible JSON Schema constraints and prompt guidance;
* interviewer v3 selects a tool-returned question for trusted local hydration;
  and
* corrected adapters, including v1 readouts, bind request-relative semantics
  before a provider call can be recorded as successful.

The invariant manifest is deliberately executable documentation.  Its tests
fail if a provider-facing role or enforcement disposition silently disappears.
"""

from __future__ import annotations

import inspect
import textwrap
from copy import deepcopy
from enum import Enum
from typing import Annotated, Any, Callable, Literal, Self

import pydantic
import pydantic_core
from pydantic import (
    AfterValidator,
    Field,
    TypeAdapter,
    WithJsonSchema,
    model_validator,
)

from .contracts import (
    ContractModel,
    JsonValue,
    NonEmptyText,
    PositiveVersion,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_evidence import (
    EvidenceProposalDraft,
    FixedOntologyClaim,
    _deduplicate_in_order,
    canonical_unsupported_assumptions,
)
from .phase4_interviewer import (
    AskVettedQuestionDecision,
    ClarifyExistingEvidenceDecision,
    InterviewerAction,
    InterviewerDecision,
    PauseAndResumeDecision,
    ReadCandidateQuestionScoresResult,
    VettedQuestionCandidate,
    VettedQuestionOption,
    vetted_question_sha256,
)
from .phase4_llm_readout import LLMReadoutResponseDraft
from .phase4_ontology import OntologyDimensionProposalDraft
from .phase4_prediction import PredictionUnsupportedAssumption
from .phase4_provider import (
    PROVIDER_RESPONSE_CONTEXT_FAILURE_CODES,
    PrivateStructuredProviderRequest,
    ProviderResponseContract,
    ProviderResponseContextError,
    ProviderResponseSelectionError,
    ProviderResponseValidatorRegistration,
    ProviderResponseValidatorRegistry,
    bind_provider_response_contract,
)
from .phase4_robustness import LLMRole


PROVIDER_RESPONSE_NORMALIZER_ID = "phase4_provider_response_normalizer"
PROVIDER_RESPONSE_NORMALIZER_VERSION = 1
PROVIDER_RESPONSE_SCHEMA_VERSION = 2
PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION = 3
PROVIDER_CONFORMANCE_FIELD = "provider_response_conformance"
PROVIDER_RESPONSE_VALIDATOR_ID = "phase4_provider_response_semantics"
PROVIDER_RESPONSE_VALIDATOR_VERSION = 1
PROVIDER_RESPONSE_SELECTOR_VALIDATOR_VERSION = 2
REQUIRED_PROVIDER_PYDANTIC_VERSION = "2.13.4"
REQUIRED_PROVIDER_PYDANTIC_CORE_VERSION = "2.46.4"


class ProviderAskVettedQuestionSelectorDecision(ContractModel):
    """Provider wire response selecting a trusted question without echoing it."""

    record_version: Literal["phase4_ask_vetted_question_selector.v1"] = (
        "phase4_ask_vetted_question_selector.v1"
    )
    action: Literal[InterviewerAction.ASK_VETTED_QUESTION] = (
        InterviewerAction.ASK_VETTED_QUESTION
    )
    selected_question_id: StableId
    rendering_mode: Literal["canonical_vetted"] = "canonical_vetted"


ProviderInterviewerDecisionV3 = Annotated[
    ProviderAskVettedQuestionSelectorDecision
    | ClarifyExistingEvidenceDecision
    | PauseAndResumeDecision,
    Field(discriminator="action"),
]


class InterviewerQuestionSelectionContext(ContractModel):
    """Private exact tool results available to one interviewer invocation."""

    record_version: Literal[
        "phase4_interviewer_tool_result_context.v1"
    ] = "phase4_interviewer_tool_result_context.v1"
    candidate_question_results: list[ReadCandidateQuestionScoresResult] = (
        Field(default_factory=list)
    )


class ProviderInvariantDisposition(str, Enum):
    """How one provider-output invariant is made enforceable."""

    SCHEMA = "schema"
    PROMPT = "prompt"
    NORMALIZED = "normalized"
    POST_PARSE = "post_parse"


class ProviderResponseInvariant(ContractModel):
    """Machine-readable disposition for one response-contract invariant."""

    invariant_id: StableId
    role: LLMRole
    description: str
    dispositions: list[ProviderInvariantDisposition]
    normalizer_id: StableId | None = None
    normalizer_version: PositiveVersion | None = None

    @model_validator(mode="after")
    def require_complete_disposition(self) -> Self:
        if not self.dispositions or len(self.dispositions) != len(
            set(self.dispositions)
        ):
            raise ValueError("provider invariant dispositions must be unique")
        normalized = ProviderInvariantDisposition.NORMALIZED in self.dispositions
        if normalized != (self.normalizer_id is not None):
            raise ValueError("normalized invariant must bind a normalizer")
        if normalized != (self.normalizer_version is not None):
            raise ValueError("normalized invariant must bind a normalizer version")
        return self


class ProviderResponseInvariantManifest(ContractModel):
    """Complete provider-facing invariant inventory for all five roles."""

    record_version: Literal[
        "phase4_provider_response_invariants.v1",
        "phase4_provider_response_invariants.v2",
    ] = (
        "phase4_provider_response_invariants.v1"
    )
    manifest_id: Literal["phase4_provider_response_invariants"] = (
        "phase4_provider_response_invariants"
    )
    manifest_version: Literal[1, 2] = 1
    response_schema_versions: dict[LLMRole, PositiveVersion] = Field(
        default_factory=lambda: {
            LLMRole.INTERVIEWER: 2,
            LLMRole.EVIDENCE_EXTRACTOR: 2,
            LLMRole.ONTOLOGY_PROPOSER: 2,
            LLMRole.DIRECT_READOUT: 1,
            LLMRole.HYBRID_READOUT: 1,
        }
    )
    normalizer_id: Literal["phase4_provider_response_normalizer"] = (
        "phase4_provider_response_normalizer"
    )
    normalizer_version: Literal[1] = 1
    invariants: list[ProviderResponseInvariant]

    @model_validator(mode="after")
    def require_complete_roles_and_ids(self) -> Self:
        if {item.role for item in self.invariants} != set(LLMRole):
            raise ValueError("provider invariant manifest must cover every role")
        expected_versions = {
            1: {
                LLMRole.INTERVIEWER: 2,
                LLMRole.EVIDENCE_EXTRACTOR: 2,
                LLMRole.ONTOLOGY_PROPOSER: 2,
                LLMRole.DIRECT_READOUT: 1,
                LLMRole.HYBRID_READOUT: 1,
            },
            2: {
                LLMRole.INTERVIEWER: 3,
                LLMRole.EVIDENCE_EXTRACTOR: 2,
                LLMRole.ONTOLOGY_PROPOSER: 2,
                LLMRole.DIRECT_READOUT: 1,
                LLMRole.HYBRID_READOUT: 1,
            },
        }[self.manifest_version]
        if self.response_schema_versions != expected_versions:
            raise ValueError("provider invariant schema-version matrix differs")
        expected_record_version = (
            f"phase4_provider_response_invariants.v{self.manifest_version}"
        )
        if self.record_version != expected_record_version:
            raise ValueError("provider invariant record version differs")
        ids = [item.invariant_id for item in self.invariants]
        if len(ids) != len(set(ids)):
            raise ValueError("provider invariant ids must be unique")
        return self


class ProviderResponseProbeExpectation(str, Enum):
    REJECTION = "rejection"
    NORMALIZATION = "normalization"
    MIXED = "mixed"


class ProviderResponseBehaviorProbe(ContractModel):
    """One public adversarial behavior that pins a declared invariant."""

    invariant_id: StableId
    role: LLMRole
    probe_id: StableId
    expectation: ProviderResponseProbeExpectation


class ProviderResponseBehaviorSpec(ContractModel):
    """Cross-runtime-stable behavior surface executed by the test suite."""

    record_version: Literal[
        "phase4_provider_response_behavior.v1",
        "phase4_provider_response_behavior.v2",
    ] = (
        "phase4_provider_response_behavior.v1"
    )
    behavior_id: Literal["phase4_provider_response_behavior"] = (
        "phase4_provider_response_behavior"
    )
    behavior_version: Literal[1, 2] = 1
    probes: list[ProviderResponseBehaviorProbe]

    @model_validator(mode="after")
    def require_exact_invariant_bijection(self) -> Self:
        manifest = (
            PROVIDER_RESPONSE_INVARIANT_MANIFEST
            if self.behavior_version == 1
            else PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2
        )
        invariant_by_id = {
            item.invariant_id: item
            for item in manifest.invariants
        }
        if {item.invariant_id for item in self.probes} != set(invariant_by_id):
            raise ValueError("provider behavior probes must cover every invariant")
        if len({item.probe_id for item in self.probes}) != len(self.probes):
            raise ValueError("provider behavior probe ids must be unique")
        if any(
            item.role is not invariant_by_id[item.invariant_id].role
            for item in self.probes
        ):
            raise ValueError("provider behavior probe roles differ")
        expected_record_version = (
            f"phase4_provider_response_behavior.v{self.behavior_version}"
        )
        if self.record_version != expected_record_version:
            raise ValueError("provider behavior record version differs")
        return self


def _invariant(
    invariant_id: str,
    role: LLMRole,
    description: str,
    *dispositions: ProviderInvariantDisposition,
) -> ProviderResponseInvariant:
    normalized = ProviderInvariantDisposition.NORMALIZED in dispositions
    return ProviderResponseInvariant(
        invariant_id=invariant_id,
        role=role,
        description=description,
        dispositions=list(dispositions),
        normalizer_id=PROVIDER_RESPONSE_NORMALIZER_ID if normalized else None,
        normalizer_version=(
            PROVIDER_RESPONSE_NORMALIZER_VERSION if normalized else None
        ),
    )


_SCHEMA = ProviderInvariantDisposition.SCHEMA
_PROMPT = ProviderInvariantDisposition.PROMPT
_NORMALIZED = ProviderInvariantDisposition.NORMALIZED
_POST_PARSE = ProviderInvariantDisposition.POST_PARSE


PROVIDER_RESPONSE_INVARIANT_MANIFEST = ProviderResponseInvariantManifest(
    invariants=[
        _invariant(
            "interviewer_discriminated_action",
            LLMRole.INTERVIEWER,
            "The decision uses exactly one allowed discriminated action shape.",
            _SCHEMA,
        ),
        _invariant(
            "interviewer_clarification_lineage",
            LLMRole.INTERVIEWER,
            "Clarification references are nonempty and unique.",
            _SCHEMA,
        ),
        _invariant(
            "interviewer_capability_question_identity",
            LLMRole.INTERVIEWER,
            "The public probe asks the exact vetted question returned by tools.",
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "extractor_source_lineage_nonempty",
            LLMRole.EVIDENCE_EXTRACTOR,
            "Every proposal cites at least one supplied participant message.",
            _SCHEMA,
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "extractor_source_lineage_unique",
            LLMRole.EVIDENCE_EXTRACTOR,
            "Repeated source ids and identical assumption flags are canonicalized.",
            _SCHEMA,
            _NORMALIZED,
        ),
        _invariant(
            "extractor_claim_pair_semantics",
            LLMRole.EVIDENCE_EXTRACTOR,
            "Claims use two distinct items; reversed order preserves polarity.",
            _PROMPT,
            _NORMALIZED,
        ),
        _invariant(
            "extractor_claim_ontology_membership",
            LLMRole.EVIDENCE_EXTRACTOR,
            "Claim items belong to the supplied active ontology.",
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "extractor_capability_grounded_nonempty",
            LLMRole.EVIDENCE_EXTRACTOR,
            "The marked public probe yields at least one grounded claim.",
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "ontology_source_lineage_nonempty",
            LLMRole.ONTOLOGY_PROPOSER,
            "Every proposal cites at least one supplied participant message.",
            _SCHEMA,
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "ontology_reference_lists_canonical",
            LLMRole.ONTOLOGY_PROPOSER,
            "Repeated lineage and duplicate-candidate ids are canonicalized.",
            _SCHEMA,
            _NORMALIZED,
        ),
        _invariant(
            "ontology_assumption_flags_canonical",
            LLMRole.ONTOLOGY_PROPOSER,
            "Identical assumption flags are deduplicated and sorted by id.",
            _SCHEMA,
            _NORMALIZED,
        ),
        _invariant(
            "ontology_context_membership",
            LLMRole.ONTOLOGY_PROPOSER,
            "Lineage, duplicate candidates, and fresh ids match the supplied context.",
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "ontology_proposed_dimension_ids_unique",
            LLMRole.ONTOLOGY_PROPOSER,
            "One response cannot propose the same fresh dimension id twice.",
            _PROMPT,
            _POST_PARSE,
        ),
        _invariant(
            "ontology_capability_grounded_nonempty",
            LLMRole.ONTOLOGY_PROPOSER,
            "The marked public gap probe yields at least one fresh grounded proposal.",
            _PROMPT,
            _POST_PARSE,
        ),
        *[
            item
            for role, prefix in (
                (LLMRole.DIRECT_READOUT, "direct_readout"),
                (LLMRole.HYBRID_READOUT, "hybrid_readout"),
            )
            for item in (
                _invariant(
                    f"{prefix}_probability_simplex",
                    role,
                    "Option probabilities are finite and sum to one.",
                    _PROMPT,
                    _POST_PARSE,
                ),
                _invariant(
                    f"{prefix}_exact_option_coverage",
                    role,
                    "Probability keys cover every canonical target option exactly.",
                    _PROMPT,
                    _POST_PARSE,
                ),
                _invariant(
                    f"{prefix}_evidence_references_canonical",
                    role,
                    "Supporting evidence ids are unique and canonicalized.",
                    _NORMALIZED,
                ),
                _invariant(
                    f"{prefix}_eligible_evidence_only",
                    role,
                    "Citations use eligible ids and are nonempty when evidence exists.",
                    _PROMPT,
                    _POST_PARSE,
                ),
                _invariant(
                    f"{prefix}_assumptions_canonical",
                    role,
                    "Assumption ids and affected-option ids are canonicalized.",
                    _NORMALIZED,
                ),
                _invariant(
                    f"{prefix}_assumption_option_membership",
                    role,
                    "Every affected option belongs to the target option set.",
                    _PROMPT,
                    _POST_PARSE,
                ),
            )
        ],
    ]
)


_PROVIDER_BEHAVIOR_PROBES: dict[
    str,
    tuple[str, ProviderResponseProbeExpectation],
] = {
    "interviewer_discriminated_action": (
        "interviewer_discriminator",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "interviewer_clarification_lineage": (
        "interviewer_lineage",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "interviewer_capability_question_identity": (
        "interviewer_exact_question",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "extractor_source_lineage_nonempty": (
        "extractor_source_references",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "extractor_source_lineage_unique": (
        "extractor_reference_normalization",
        ProviderResponseProbeExpectation.NORMALIZATION,
    ),
    "extractor_claim_pair_semantics": (
        "extractor_pair_normalization",
        ProviderResponseProbeExpectation.NORMALIZATION,
    ),
    "extractor_claim_ontology_membership": (
        "extractor_unknown_item",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "extractor_capability_grounded_nonempty": (
        "extractor_grounded_nonempty",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "ontology_source_lineage_nonempty": (
        "ontology_source_references",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "ontology_reference_lists_canonical": (
        "ontology_reference_normalization",
        ProviderResponseProbeExpectation.NORMALIZATION,
    ),
    "ontology_assumption_flags_canonical": (
        "ontology_assumption_normalization",
        ProviderResponseProbeExpectation.MIXED,
    ),
    "ontology_context_membership": (
        "ontology_context_references",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "ontology_proposed_dimension_ids_unique": (
        "ontology_unique_proposed_ids",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "ontology_capability_grounded_nonempty": (
        "ontology_grounded_nonempty",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "direct_readout_probability_simplex": (
        "direct_probability_simplex",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "direct_readout_exact_option_coverage": (
        "direct_option_coverage",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "direct_readout_evidence_references_canonical": (
        "direct_evidence_normalization",
        ProviderResponseProbeExpectation.NORMALIZATION,
    ),
    "direct_readout_eligible_evidence_only": (
        "direct_evidence_eligibility",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "direct_readout_assumptions_canonical": (
        "direct_assumption_normalization",
        ProviderResponseProbeExpectation.MIXED,
    ),
    "direct_readout_assumption_option_membership": (
        "direct_assumption_options",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "hybrid_readout_probability_simplex": (
        "hybrid_probability_simplex",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "hybrid_readout_exact_option_coverage": (
        "hybrid_option_coverage",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "hybrid_readout_evidence_references_canonical": (
        "hybrid_evidence_normalization",
        ProviderResponseProbeExpectation.NORMALIZATION,
    ),
    "hybrid_readout_eligible_evidence_only": (
        "hybrid_evidence_eligibility",
        ProviderResponseProbeExpectation.REJECTION,
    ),
    "hybrid_readout_assumptions_canonical": (
        "hybrid_assumption_normalization",
        ProviderResponseProbeExpectation.MIXED,
    ),
    "hybrid_readout_assumption_option_membership": (
        "hybrid_assumption_options",
        ProviderResponseProbeExpectation.REJECTION,
    ),
}


PROVIDER_RESPONSE_BEHAVIOR_SPEC = ProviderResponseBehaviorSpec(
    probes=[
        ProviderResponseBehaviorProbe(
            invariant_id=invariant.invariant_id,
            role=invariant.role,
            probe_id=_PROVIDER_BEHAVIOR_PROBES[invariant.invariant_id][0],
            expectation=_PROVIDER_BEHAVIOR_PROBES[invariant.invariant_id][1],
        )
        for invariant in PROVIDER_RESPONSE_INVARIANT_MANIFEST.invariants
    ]
)


PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2 = ProviderResponseInvariantManifest(
    record_version="phase4_provider_response_invariants.v2",
    manifest_version=2,
    response_schema_versions={
        LLMRole.INTERVIEWER: 3,
        LLMRole.EVIDENCE_EXTRACTOR: 2,
        LLMRole.ONTOLOGY_PROPOSER: 2,
        LLMRole.DIRECT_READOUT: 1,
        LLMRole.HYBRID_READOUT: 1,
    },
    invariants=[
        *PROVIDER_RESPONSE_INVARIANT_MANIFEST.invariants[:2],
        _invariant(
            "interviewer_question_selector_shape",
            LLMRole.INTERVIEWER,
            "The provider returns only a question id selector for ask actions.",
            _SCHEMA,
        ),
        _invariant(
            "interviewer_current_tool_question_grounding",
            LLMRole.INTERVIEWER,
            "Post-parse lookup accepts only a question id returned by this "
            "invocation.",
            _POST_PARSE,
        ),
        _invariant(
            "interviewer_exact_local_question_materialization",
            LLMRole.INTERVIEWER,
            "Trusted local code restores the exact canonical candidate by selector.",
            _NORMALIZED,
            _POST_PARSE,
        ),
        *PROVIDER_RESPONSE_INVARIANT_MANIFEST.invariants[3:],
    ],
)


_PROVIDER_BEHAVIOR_PROBES_V2 = {
    key: value
    for key, value in _PROVIDER_BEHAVIOR_PROBES.items()
    if key != "interviewer_capability_question_identity"
}
_PROVIDER_BEHAVIOR_PROBES_V2.update(
    {
        "interviewer_question_selector_shape": (
            "interviewer_selector_shape",
            ProviderResponseProbeExpectation.REJECTION,
        ),
        "interviewer_current_tool_question_grounding": (
            "interviewer_current_tool_grounding",
            ProviderResponseProbeExpectation.REJECTION,
        ),
        "interviewer_exact_local_question_materialization": (
            "interviewer_local_materialization",
            ProviderResponseProbeExpectation.NORMALIZATION,
        ),
    }
)


PROVIDER_RESPONSE_BEHAVIOR_SPEC_V2 = ProviderResponseBehaviorSpec(
    record_version="phase4_provider_response_behavior.v2",
    behavior_version=2,
    probes=[
        ProviderResponseBehaviorProbe(
            invariant_id=invariant.invariant_id,
            role=invariant.role,
            probe_id=_PROVIDER_BEHAVIOR_PROBES_V2[invariant.invariant_id][0],
            expectation=_PROVIDER_BEHAVIOR_PROBES_V2[invariant.invariant_id][1],
        )
        for invariant in PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2.invariants
    ],
)


def _base_response_type(role: LLMRole) -> Any:
    return {
        LLMRole.INTERVIEWER: InterviewerDecision,
        LLMRole.EVIDENCE_EXTRACTOR: list[EvidenceProposalDraft],
        LLMRole.ONTOLOGY_PROPOSER: list[OntologyDimensionProposalDraft],
        LLMRole.DIRECT_READOUT: LLMReadoutResponseDraft,
        LLMRole.HYBRID_READOUT: LLMReadoutResponseDraft,
    }[role]


def _walk_schema(value: JsonValue):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_schema(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_schema(child)


def _annotate_array_property(
    schema: dict[str, JsonValue],
    property_name: str,
    *,
    description: str,
    min_items: int | None = None,
) -> None:
    for node in _walk_schema(schema):
        properties = node.get("properties")
        if not isinstance(properties, dict):
            continue
        prop = properties.get(property_name)
        if not isinstance(prop, dict):
            continue
        prop["uniqueItems"] = True
        prop["description"] = description
        if min_items is not None:
            prop["minItems"] = min_items


def _annotate_property(
    schema: dict[str, JsonValue],
    property_name: str,
    description: str,
) -> None:
    for node in _walk_schema(schema):
        properties = node.get("properties")
        if not isinstance(properties, dict):
            continue
        prop = properties.get(property_name)
        if isinstance(prop, dict):
            prop["description"] = description


def _inline_local_schema_refs(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Inline local definitions so ``WithJsonSchema`` remains self-contained."""

    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return schema

    def resolve(value: JsonValue, stack: tuple[str, ...] = ()) -> JsonValue:
        if isinstance(value, list):
            return [resolve(item, stack) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            target = definitions.get(name)
            if target is None or name in stack:
                raise ValueError("provider response schema has unresolved recursion")
            replacement = resolve(deepcopy(target), (*stack, name))
            if not isinstance(replacement, dict):
                raise ValueError("provider response schema definition is not an object")
            for key, child in value.items():
                if key != "$ref":
                    replacement[key] = resolve(child, stack)
            return replacement
        resolved = {
            key: resolve(child, stack)
            for key, child in value.items()
            if key != "$defs"
        }
        discriminator = resolved.get("discriminator")
        if isinstance(discriminator, dict):
            discriminator.pop("mapping", None)
        return resolved

    result = resolve(schema)
    if not isinstance(result, dict):
        raise ValueError("provider response schema root is not an object")
    return result


def provider_response_schema_for_role(
    role: LLMRole,
    response_schema_version: int = 1,
) -> dict[str, JsonValue]:
    """Return a historical schema or the interviewer selector wire schema."""

    base = TypeAdapter(_base_response_type(role)).json_schema(mode="validation")
    if response_schema_version == 1:
        return base
    if response_schema_version == PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION:
        if role is not LLMRole.INTERVIEWER:
            raise ValueError("provider schema v3 is interviewer-only")
        schema = TypeAdapter(ProviderInterviewerDecisionV3).json_schema(
            mode="validation"
        )
        schema["description"] = (
            "Phase 4 interviewer response schema v3. Ask actions select one "
            "question returned by the current tool invocation; trusted local "
            "code materializes the canonical question."
        )
        _annotate_array_property(
            schema,
            "linked_evidence_event_ids",
            min_items=1,
            description="Unique eligible evidence ids; at least one is required.",
        )
        return _inline_local_schema_refs(schema)
    if response_schema_version != PROVIDER_RESPONSE_SCHEMA_VERSION:
        raise ValueError("unsupported provider response schema version")
    schema = deepcopy(base)
    schema["description"] = (
        "Phase 4 provider response schema v2. Nonsemantic list normalization "
        f"uses {PROVIDER_RESPONSE_NORMALIZER_ID}.v"
        f"{PROVIDER_RESPONSE_NORMALIZER_VERSION}; request-relative rules are "
        "validated after parsing."
    )
    if role is LLMRole.INTERVIEWER:
        _annotate_array_property(
            schema,
            "linked_evidence_event_ids",
            min_items=1,
            description="Unique eligible evidence ids; at least one is required.",
        )
    elif role is LLMRole.EVIDENCE_EXTRACTOR:
        _annotate_array_property(
            schema,
            "source_message_ids",
            min_items=1,
            description="Unique ids from the supplied participant_messages list.",
        )
        _annotate_array_property(
            schema,
            "unsupported_assumptions",
            description="Assumption records must use distinct flag_id values.",
        )
        _annotate_property(
            schema,
            "value",
            "Signed preference for item_a over item_b; reversing the pair "
            "reverses the sign.",
        )
    elif role is LLMRole.ONTOLOGY_PROPOSER:
        for property_name, description, min_items in (
            (
                "source_message_ids",
                "Unique ids from the supplied participant_messages list.",
                1,
            ),
            (
                "supporting_evidence_event_ids",
                "Unique ids from eligible_evidence_event_ids.",
                None,
            ),
            (
                "candidate_duplicate_dimension_ids",
                "Unique ids from active_ontology_dimension_ids.",
                None,
            ),
            (
                "unsupported_assumptions",
                "Assumption records must use distinct flag_id values.",
                None,
            ),
        ):
            _annotate_array_property(
                schema,
                property_name,
                description=description,
                min_items=min_items,
            )
    else:
        _annotate_array_property(
            schema,
            "supporting_evidence_event_ids",
            description="Unique ids from eligible_evidence_event_ids.",
        )
        _annotate_array_property(
            schema,
            "unsupported_assumptions",
            description="Assumption records must use distinct assumption_id values.",
        )
        _annotate_array_property(
            schema,
            "affected_option_ids",
            min_items=1,
            description="Unique ids from canonical_option_ids.",
        )
        _annotate_property(
            schema,
            "option_probabilities",
            "Keys must equal canonical_option_ids and values must sum to 1.0.",
        )
    return _inline_local_schema_refs(schema)


def provider_invariant_prompt_suffix(
    role: LLMRole,
    response_schema_version: int | None = None,
) -> str:
    """Return versioned guidance for rules JSON Schema cannot express."""

    # One-argument behavior is frozen for historical suite-v4 reconstruction.
    version = 2 if response_schema_version is None else response_schema_version
    if (
        role is LLMRole.INTERVIEWER
        and version == PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION
    ):
        return (
            "Call read_candidate_question_scores before asking a question. For "
            "ask_vetted_question, return selected_question_id copied from one "
            "candidate returned by that tool in this invocation. Do not echo the "
            "question text, checksum, options, score, or other candidate fields; "
            "trusted local code materializes them. For a marked public conformance "
            "probe, select the expected candidate."
        )
    if version not in {1, 2}:
        raise ValueError("unsupported provider prompt schema version")

    return {
        LLMRole.INTERVIEWER: (
            "For a marked public conformance probe, return ask_vetted_question "
            "with the exact vetted question supplied in the input and by the tool."
        ),
        LLMRole.EVIDENCE_EXTRACTOR: (
            "Cite only supplied participant message ids and active ontology item "
            "ids. Each claim must use two distinct active ontology item ids. The "
            "signed value means preference for item_a over item_b; pair order may "
            "be normalized with the sign reversed. A marked public conformance "
            "probe requires at least one grounded proposal."
        ),
        LLMRole.ONTOLOGY_PROPOSER: (
            "Cite only supplied participant message and eligible evidence ids; "
            "duplicate candidates must be active dimension ids and the proposed "
            "dimension id must be fresh. Use a different proposed_dimension."
            "dimension_id for each proposal. A marked public gap probe requires "
            "at least one grounded proposal."
        ),
        LLMRole.DIRECT_READOUT: (
            "Use every canonical_option_id exactly once as a probability key, make "
            "probabilities sum to 1.0, cite only eligible evidence ids, and cite at "
            "least one when eligible evidence is supplied."
        ),
        LLMRole.HYBRID_READOUT: (
            "Use every canonical_option_id exactly once as a probability key, make "
            "probabilities sum to 1.0, cite only eligible evidence ids, and cite at "
            "least one when eligible evidence is supplied."
        ),
    }[role]


def build_public_capability_question(item_ids: list[str]) -> VettedQuestionCandidate:
    """Build the exact public question shared by input, tools, and output checks."""

    canonical_items = sorted(set(item_ids))
    if len(canonical_items) < 2:
        raise ValueError("public capability question requires two ontology items")
    item_a, item_b = canonical_items[:2]
    question_id = "phase4_public_capability_question"
    question_version = 1
    prompt = "Which of these two public capability-test values matters more to you?"
    options = [
        VettedQuestionOption(item_id=item_a, text=item_a),
        VettedQuestionOption(item_id=item_b, text=item_b),
    ]
    hash_payload = {
        "question_id": question_id,
        "question_version": question_version,
        "item_a": item_a,
        "item_b": item_b,
        "prompt": prompt,
        "options": [item.model_dump(mode="json") for item in options],
        "domain": "public capability conformance",
    }
    return VettedQuestionCandidate(
        question_id=question_id,
        question_version=question_version,
        question_sha256=content_sha256(hash_payload),
        item_a=item_a,
        item_b=item_b,
        prompt=prompt,
        options=options,
        domain="public capability conformance",
        score=1.0,
    )


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string_set(value: JsonValue | None, label: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string list")
    return set(value)


def _participant_message_ids(input_payload: dict[str, JsonValue]) -> set[str]:
    messages = input_payload.get("participant_messages")
    if not isinstance(messages, list):
        return set()
    ids: set[str] = set()
    for message in messages:
        item = _object(message, "participant message")
        message_id = item.get("message_id")
        if not isinstance(message_id, str):
            raise ValueError("participant message id must be a string")
        ids.add(message_id)
    return ids


def _conformance(input_payload: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    marker = input_payload.get(PROVIDER_CONFORMANCE_FIELD)
    if marker is None:
        return None
    return _object(marker, "provider response conformance marker")


def _validate_interviewer(
    response: object,
    input_payload: dict[str, JsonValue],
) -> None:
    marker = _conformance(input_payload)
    if marker is None:
        return
    expected_payload = marker.get("expected_vetted_question")
    if expected_payload is None:
        return
    expected = VettedQuestionCandidate.model_validate(expected_payload)
    if (
        not isinstance(response, AskVettedQuestionDecision)
        or response.question != expected
    ):
        raise ValueError(
            "interviewer conformance response must ask exact vetted question"
        )


def _interviewer_question_candidates(
    response_validation_context: JsonValue | None,
) -> dict[str, VettedQuestionCandidate]:
    """Index exact current-invocation candidates and reject context conflicts."""

    if response_validation_context is None:
        raise ProviderResponseContextError(
            failure_code="response_validation_context_missing"
        )
    try:
        context = InterviewerQuestionSelectionContext.model_validate(
            response_validation_context
        )
    except (pydantic.ValidationError, TypeError, ValueError) as error:
        raise ProviderResponseContextError(
            failure_code="response_validation_context_invalid"
        ) from error

    by_id: dict[str, VettedQuestionCandidate] = {}
    id_by_sha256: dict[str, str] = {}
    for result in context.candidate_question_results:
        for candidate in result.candidates:
            previous = by_id.get(candidate.question_id)
            sha_id = id_by_sha256.get(candidate.question_sha256)
            if (
                (previous is not None and previous != candidate)
                or (sha_id is not None and sha_id != candidate.question_id)
            ):
                raise ProviderResponseContextError(
                    failure_code="response_validation_context_conflict"
                )
            by_id[candidate.question_id] = candidate
            id_by_sha256[candidate.question_sha256] = candidate.question_id
    return by_id


def _interviewer_selector_materializer(
    input_payload: dict[str, JsonValue],
) -> Callable[[object, JsonValue | None], object]:
    """Hydrate a provider selector from trusted current-invocation tool output."""

    def materialize(
        wire_value: object,
        response_validation_context: JsonValue | None,
    ) -> object:
        candidates = _interviewer_question_candidates(
            response_validation_context
        )
        if isinstance(wire_value, ProviderAskVettedQuestionSelectorDecision):
            question = candidates.get(wire_value.selected_question_id)
            if question is None:
                raise ProviderResponseSelectionError(
                    path=("selected_question_id",),
                    error_type="question_selector_not_returned",
                )
            decision: object = AskVettedQuestionDecision(
                question=question,
                rendering_mode=wire_value.rendering_mode,
            )
        else:
            decision = wire_value

        try:
            _validate_interviewer(decision, input_payload)
        except ValueError as error:
            raise ProviderResponseSelectionError(
                path=("selected_question_id",),
                error_type="question_selector_conformance_mismatch",
            ) from error
        return decision

    return materialize


def _validate_extractor(
    response: object,
    input_payload: dict[str, JsonValue],
) -> None:
    if not isinstance(response, list) or any(
        not isinstance(item, EvidenceProposalDraft) for item in response
    ):
        raise ValueError("extractor response type does not match role")
    allowed_messages = _participant_message_ids(input_payload)
    active_items = _string_set(
        input_payload.get("active_ontology_dimension_ids"),
        "active ontology dimension ids",
    )
    for proposal in response:
        if not set(proposal.source_message_ids) <= allowed_messages:
            raise ValueError("extractor response cites an unknown participant message")
        if {proposal.claim.item_a, proposal.claim.item_b} - active_items:
            raise ValueError("extractor response cites an unknown ontology item")
    marker = _conformance(input_payload)
    if marker is None:
        return
    required_source = marker.get("required_source_message_id")
    required_claim = marker.get("required_claim")
    if not isinstance(required_source, str) or not isinstance(required_claim, dict):
        raise ValueError("extractor conformance marker is incomplete")
    expected_item_a = required_claim.get("item_a")
    expected_item_b = required_claim.get("item_b")
    expected_value = required_claim.get("value")
    matched = any(
        required_source in proposal.source_message_ids
        and proposal.claim.item_a == expected_item_a
        and proposal.claim.item_b == expected_item_b
        and proposal.claim.value == expected_value
        for proposal in response
    )
    if not matched:
        raise ValueError("extractor conformance response lacks exact grounded claim")


def _validate_ontology(
    response: object,
    input_payload: dict[str, JsonValue],
) -> None:
    if not isinstance(response, list) or any(
        not isinstance(item, OntologyDimensionProposalDraft) for item in response
    ):
        raise ValueError("ontology response type does not match role")
    allowed_messages = _participant_message_ids(input_payload)
    active_ids = _string_set(
        input_payload.get("active_ontology_dimension_ids"),
        "active ontology dimension ids",
    )
    retired_ids = _string_set(
        input_payload.get("retired_ontology_dimension_ids", []),
        "retired ontology dimension ids",
    )
    eligible_evidence_ids = _string_set(
        input_payload.get("eligible_evidence_event_ids", []),
        "eligible evidence event ids",
    )
    proposed_ids = [
        proposal.proposed_dimension.dimension_id for proposal in response
    ]
    if len(proposed_ids) != len(set(proposed_ids)):
        raise ValueError("ontology response proposed dimension ids must be unique")
    for proposal in response:
        if not set(proposal.source_message_ids) <= allowed_messages:
            raise ValueError("ontology response cites an unknown participant message")
        if not set(proposal.supporting_evidence_event_ids) <= eligible_evidence_ids:
            raise ValueError("ontology response cites ineligible evidence")
        if not set(proposal.candidate_duplicate_dimension_ids) <= active_ids:
            raise ValueError("ontology response names an unknown duplicate dimension")
        dimension_id = proposal.proposed_dimension.dimension_id
        if dimension_id in active_ids or dimension_id in retired_ids:
            raise ValueError("ontology response must propose a fresh dimension id")
    marker = _conformance(input_payload)
    if marker is None:
        return
    required_source = marker.get("required_source_message_id")
    required_evidence = marker.get("required_evidence_event_id")
    if not isinstance(required_source, str) or not isinstance(
        required_evidence, str
    ):
        raise ValueError("ontology conformance marker is incomplete")
    matched = any(
        required_source in proposal.source_message_ids
        and required_evidence in proposal.supporting_evidence_event_ids
        and proposal.proposed_dimension.dimension_id not in active_ids
        and proposal.proposed_dimension.dimension_id not in retired_ids
        for proposal in response
    )
    if not matched:
        raise ValueError("ontology conformance response lacks grounded fresh proposal")


def _validate_readout(
    response: object,
    input_payload: dict[str, JsonValue],
) -> None:
    if not isinstance(response, LLMReadoutResponseDraft):
        raise ValueError("readout response type does not match role")
    option_ids = _string_set(
        input_payload.get("canonical_option_ids"),
        "canonical option ids",
    )
    if set(response.option_probabilities) != option_ids:
        raise ValueError("readout response must cover canonical options exactly")
    if "eligible_evidence_event_ids" in input_payload:
        eligible_ids = _string_set(
            input_payload.get("eligible_evidence_event_ids"),
            "eligible evidence event ids",
        )
    else:
        eligible_ids = set()
        history = input_payload.get("evidence_history")
        if not isinstance(history, list):
            raise ValueError("readout evidence history must be a list")
        for record in history:
            if not isinstance(record, dict) or record.get("source") != (
                "public_synthetic_onboarding"
            ):
                continue
            event = record.get("event")
            if not isinstance(event, dict):
                raise ValueError("readout onboarding evidence must be an object")
            event_id = event.get("event_id")
            if not isinstance(event_id, str):
                raise ValueError("readout onboarding evidence id must be a string")
            eligible_ids.add(event_id)
    if not set(response.supporting_evidence_event_ids) <= eligible_ids:
        raise ValueError("readout response cites ineligible evidence")
    if eligible_ids and not response.supporting_evidence_event_ids:
        raise ValueError("readout response must cite eligible evidence")
    for assumption in response.unsupported_assumptions:
        if not set(assumption.affected_option_ids) <= option_ids:
            raise ValueError("readout assumption names an unknown option")


def _semantic_validator(
    role: LLMRole,
    input_payload: dict[str, JsonValue],
) -> Callable[[object], object]:
    validator = {
        LLMRole.INTERVIEWER: _validate_interviewer,
        LLMRole.EVIDENCE_EXTRACTOR: _validate_extractor,
        LLMRole.ONTOLOGY_PROPOSER: _validate_ontology,
        LLMRole.DIRECT_READOUT: _validate_readout,
        LLMRole.HYBRID_READOUT: _validate_readout,
    }[role]

    def validate(value: object) -> object:
        validator(value, input_payload)
        return value

    return validate


def provider_response_adapter_for_role(
    role: LLMRole,
    *,
    response_schema_version: int = 1,
    input_payload: JsonValue | None = None,
    bind_request_semantics: bool | None = None,
) -> ProviderResponseContract:
    """Build the exact parser used by both planning and paid execution."""

    base_type = _base_response_type(role)
    semantics_enabled = (
        response_schema_version >= 2
        if bind_request_semantics is None
        else bind_request_semantics
    )
    if response_schema_version == 1:
        readout_role = role in {
            LLMRole.DIRECT_READOUT,
            LLMRole.HYBRID_READOUT,
        }
        if semantics_enabled and not readout_role:
            raise ValueError(
                "provider v1 request semantics are supported only for readouts"
            )
        if semantics_enabled and not isinstance(input_payload, dict):
            raise ValueError("provider v1 readout semantics require an object input")
        if semantics_enabled:
            annotated_type = Annotated[
                base_type,
                AfterValidator(_semantic_validator(role, input_payload)),
            ]
            adapter = TypeAdapter(annotated_type)
        else:
            adapter = TypeAdapter(base_type)
        return bind_provider_response_contract(
            adapter,
            role=role,
            input_payload=input_payload,
            validator_id=(
                PROVIDER_RESPONSE_VALIDATOR_ID if semantics_enabled else None
            ),
            validator_version=(
                PROVIDER_RESPONSE_VALIDATOR_VERSION
                if semantics_enabled
                else None
            ),
            implementation_sha256=(
                provider_response_validator_implementation_sha256()
                if semantics_enabled
                else None
            ),
        )
    if response_schema_version == PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION:
        if role is not LLMRole.INTERVIEWER:
            raise ValueError("provider schema v3 is interviewer-only")
        if not semantics_enabled:
            raise ValueError("provider interviewer schema v3 requires semantics")
        if not isinstance(input_payload, dict):
            raise ValueError(
                "provider interviewer schema v3 adapter requires an object input"
            )
        schema = provider_response_schema_for_role(role, response_schema_version)
        wire_type = Annotated[
            ProviderInterviewerDecisionV3,
            WithJsonSchema(schema, mode="validation"),
        ]
        return bind_provider_response_contract(
            TypeAdapter(wire_type),
            role=role,
            input_payload=input_payload,
            validator_id=PROVIDER_RESPONSE_VALIDATOR_ID,
            validator_version=PROVIDER_RESPONSE_SELECTOR_VALIDATOR_VERSION,
            implementation_sha256=(
                provider_response_selector_validator_implementation_sha256()
            ),
            output_adapter=TypeAdapter(InterviewerDecision),
            materializer=_interviewer_selector_materializer(input_payload),
        )
    if response_schema_version != PROVIDER_RESPONSE_SCHEMA_VERSION:
        raise ValueError("unsupported provider response schema version")
    if not semantics_enabled:
        raise ValueError("provider schema v2 requires bound request semantics")
    if not isinstance(input_payload, dict):
        raise ValueError("provider schema v2 adapter requires an object input")
    schema = provider_response_schema_for_role(role, response_schema_version)
    annotated_type = Annotated[
        base_type,
        AfterValidator(_semantic_validator(role, input_payload)),
        WithJsonSchema(schema, mode="validation"),
    ]
    return bind_provider_response_contract(
        TypeAdapter(annotated_type),
        role=role,
        input_payload=input_payload,
        validator_id=PROVIDER_RESPONSE_VALIDATOR_ID,
        validator_version=PROVIDER_RESPONSE_VALIDATOR_VERSION,
        implementation_sha256=(
            provider_response_validator_implementation_sha256()
        ),
    )


def _provider_response_contract_from_request(
    request: PrivateStructuredProviderRequest,
) -> ProviderResponseContract:
    """Rebuild the frozen v1 validator for historical schema versions."""

    if request.binding.response_schema_version > 2:
        raise ValueError("legacy provider validator cannot resolve schema v3")

    return provider_response_adapter_for_role(
        request.binding.role,
        response_schema_version=request.binding.response_schema_version,
        input_payload=request.input_payload,
        bind_request_semantics=True,
    )


def _provider_response_selector_contract_from_request(
    request: PrivateStructuredProviderRequest,
) -> ProviderResponseContract:
    """Rebuild the selector validator from the exact private request inputs."""

    if (
        request.binding.role is not LLMRole.INTERVIEWER
        or request.binding.response_schema_version
        != PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION
    ):
        raise ValueError("selector provider validator requires interviewer schema v3")
    return provider_response_adapter_for_role(
        request.binding.role,
        response_schema_version=request.binding.response_schema_version,
        input_payload=request.input_payload,
        bind_request_semantics=True,
    )


def _normalized_callable_source_sha256(value: object) -> str:
    """Hash reviewed source text independent of checkout line endings."""

    source = textwrap.dedent(inspect.getsource(value)).replace("\r\n", "\n")
    normalized = "\n".join(line.rstrip() for line in source.splitlines()) + "\n"
    return content_sha256(normalized)


def validate_provider_response_semantic_runtime() -> None:
    """Fail closed when the reviewed parsing runtime is not installed."""

    if (
        pydantic.__version__ != REQUIRED_PROVIDER_PYDANTIC_VERSION
        or pydantic_core.__version__ != REQUIRED_PROVIDER_PYDANTIC_CORE_VERSION
    ):
        raise RuntimeError(
            "provider response semantics require pydantic 2.13.4 "
            "and pydantic-core 2.46.4"
        )


def _build_provider_response_validator_registry(
) -> ProviderResponseValidatorRegistry:
    return ProviderResponseValidatorRegistry(
        registrations=(
            ProviderResponseValidatorRegistration(
                validator_id=PROVIDER_RESPONSE_VALIDATOR_ID,
                validator_version=PROVIDER_RESPONSE_VALIDATOR_VERSION,
                implementation_sha256=(
                    provider_response_validator_implementation_sha256()
                ),
                factory=_provider_response_contract_from_request,
            ),
            ProviderResponseValidatorRegistration(
                validator_id=PROVIDER_RESPONSE_VALIDATOR_ID,
                validator_version=(
                    PROVIDER_RESPONSE_SELECTOR_VALIDATOR_VERSION
                ),
                implementation_sha256=(
                    provider_response_selector_validator_implementation_sha256()
                ),
                factory=_provider_response_selector_contract_from_request,
            ),
        )
    )


def _provider_response_selector_validator_implementation_payload(
) -> dict[str, JsonValue]:
    validate_provider_response_semantic_runtime()
    callables: dict[str, object] = {
        "base_response_type": _base_response_type,
        "schema_walk": _walk_schema,
        "schema_annotate_array": _annotate_array_property,
        "schema_annotate_property": _annotate_property,
        "schema_inline_refs": _inline_local_schema_refs,
        "schema_for_role": provider_response_schema_for_role,
        "prompt_suffix": provider_invariant_prompt_suffix,
        "capability_question": build_public_capability_question,
        "object_input": _object,
        "string_set_input": _string_set,
        "participant_message_ids": _participant_message_ids,
        "conformance_input": _conformance,
        "validate_interviewer": _validate_interviewer,
        "selector_context_index": _interviewer_question_candidates,
        "selector_materializer": _interviewer_selector_materializer,
        "validate_extractor": _validate_extractor,
        "validate_ontology": _validate_ontology,
        "validate_readout": _validate_readout,
        "semantic_validator": _semantic_validator,
        "adapter_for_role": provider_response_adapter_for_role,
        "contract_from_request": _provider_response_contract_from_request,
        "selector_contract_from_request": (
            _provider_response_selector_contract_from_request
        ),
        "canonical_claim_pair": FixedOntologyClaim.canonicalize_pair,
        "canonical_evidence_draft": EvidenceProposalDraft.validate_draft,
        "deduplicate_evidence_lineage": _deduplicate_in_order,
        "canonical_ontology_draft": (
            OntologyDimensionProposalDraft.validate_draft
        ),
        "canonical_readout": LLMReadoutResponseDraft.validate_response,
        "canonical_prediction_assumption_options": (
            PredictionUnsupportedAssumption.canonicalize_affected_option_ids
        ),
        "canonical_assumption_flags": canonical_unsupported_assumptions,
        "interviewer_clarification_lineage": (
            ClarifyExistingEvidenceDecision.require_unique_links
        ),
        "interviewer_question_identity": (
            VettedQuestionCandidate.validate_pair_and_options
        ),
        "interviewer_question_hash": vetted_question_sha256,
        "shared_contract_model": ContractModel,
        "semantic_runtime_guard": validate_provider_response_semantic_runtime,
        "provider_contract_schema": ProviderResponseContract.json_schema,
        "provider_contract_pairing": ProviderResponseContract.__post_init__,
        "provider_contract_validate": ProviderResponseContract.validate_python,
        "provider_contract_dump": ProviderResponseContract.dump_python,
        "provider_contract_bind": bind_provider_response_contract,
        "provider_context_error": ProviderResponseContextError.__init__,
        "provider_selection_error": ProviderResponseSelectionError.__init__,
        "provider_registry_resolve": ProviderResponseValidatorRegistry.resolve,
        "provider_registry_builder": (
            _build_provider_response_validator_registry
        ),
    }
    schema_versions = (
        PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2.response_schema_versions
    )
    return {
        "implementation_id": PROVIDER_RESPONSE_VALIDATOR_ID,
        "implementation_version": (
            PROVIDER_RESPONSE_SELECTOR_VALIDATOR_VERSION
        ),
        "semantic_constants": {
            "normalizer_id": PROVIDER_RESPONSE_NORMALIZER_ID,
            "normalizer_version": PROVIDER_RESPONSE_NORMALIZER_VERSION,
            "legacy_schema_version": PROVIDER_RESPONSE_SCHEMA_VERSION,
            "selector_schema_version": (
                PROVIDER_RESPONSE_SELECTOR_SCHEMA_VERSION
            ),
            "conformance_field": PROVIDER_CONFORMANCE_FIELD,
            "validator_id": PROVIDER_RESPONSE_VALIDATOR_ID,
            "validator_version": (
                PROVIDER_RESPONSE_SELECTOR_VALIDATOR_VERSION
            ),
            "required_pydantic_version": REQUIRED_PROVIDER_PYDANTIC_VERSION,
            "required_pydantic_core_version": (
                REQUIRED_PROVIDER_PYDANTIC_CORE_VERSION
            ),
            "response_context_failure_codes": sorted(
                PROVIDER_RESPONSE_CONTEXT_FAILURE_CODES
            ),
        },
        "semantic_runtime": {
            "pydantic_version": pydantic.__version__,
            "pydantic_core_version": pydantic_core.__version__,
            "contract_model_config": {
                "extra": ContractModel.model_config.get("extra"),
                "str_strip_whitespace": ContractModel.model_config.get(
                    "str_strip_whitespace"
                ),
                "validate_assignment": ContractModel.model_config.get(
                    "validate_assignment"
                ),
            },
            "normalization_probes": {
                "stable_id": TypeAdapter(StableId).validate_python(
                    "  provider_probe_id  "
                ),
                "nonempty_text": TypeAdapter(NonEmptyText).validate_python(
                    "  provider probe text  "
                ),
            },
        },
        "manifest_sha256": content_sha256(
            PROVIDER_RESPONSE_INVARIANT_MANIFEST_V2
        ),
        "interviewer_tool_context_schema_sha256": content_sha256(
            TypeAdapter(InterviewerQuestionSelectionContext).json_schema(
                mode="validation"
            )
        ),
        "behavior_spec_sha256": content_sha256(
            PROVIDER_RESPONSE_BEHAVIOR_SPEC_V2
        ),
        "normalized_source_sha256": {
            name: _normalized_callable_source_sha256(value)
            for name, value in sorted(callables.items())
        },
        "response_schema_sha256": {
            role.value: content_sha256(
                provider_response_schema_for_role(role, schema_versions[role])
            )
            for role in LLMRole
        },
        "prompt_suffix_sha256": {
            role.value: content_sha256(
                provider_invariant_prompt_suffix(role, schema_versions[role])
            )
            for role in LLMRole
        },
    }


PROVIDER_RESPONSE_VALIDATOR_IMPLEMENTATION_SHA256 = (
    "f077e2713b7ba0e6735f07e0ee367cc6d2203074841f78afda86ca450c009a09"
)
PROVIDER_RESPONSE_SELECTOR_VALIDATOR_IMPLEMENTATION_SHA256 = content_sha256(
    _provider_response_selector_validator_implementation_payload()
)


def provider_response_validator_implementation_sha256() -> str:
    """Return the frozen v1 identity used by schemas v1 and v2."""

    return PROVIDER_RESPONSE_VALIDATOR_IMPLEMENTATION_SHA256


def provider_response_selector_validator_implementation_sha256() -> str:
    """Return the v2 selector/hydration behavior identity."""

    return PROVIDER_RESPONSE_SELECTOR_VALIDATOR_IMPLEMENTATION_SHA256


PROVIDER_RESPONSE_VALIDATOR_REGISTRY = (
    _build_provider_response_validator_registry()
)


def provider_response_invariant_manifest_sha256() -> str:
    """Return the stable identity available to review and test tooling."""

    return content_sha256(PROVIDER_RESPONSE_INVARIANT_MANIFEST)
