"""Zero-spend adjudication policy for candidate capability schema failures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import (
    ContractModel,
    JsonValue,
    PositiveVersion,
    Sha256Digest,
    StableId,
)
from .fixture_io import content_sha256
from .phase4_capability import TogetherCapabilityPlan
from .phase4_capability_continuation import (
    TogetherCandidateCapabilityAuthorizationBundle,
    TogetherCandidateCapabilityExecutionState,
    TogetherCapabilityContinuationPlan,
    candidate_plan_for,
    validate_candidate_capability_execution_state,
)
from .phase4_provider import (
    ProviderCallFinalization,
    ProviderCallOutcome,
    ProviderRequestBinding,
)
from .phase4_robustness import LLMRole, Phase4ERobustnessProfile
from .phase4_together import Phase4TogetherSuite


class TogetherCapabilityAdjudicationPolicy(ContractModel):
    """Predeclared interpretation of repeated exact-schema failures."""

    schema_version: Literal[
        "preference_eval_phase4_capability_adjudication.v1"
    ] = "preference_eval_phase4_capability_adjudication.v1"
    policy_id: StableId
    policy_version: PositiveVersion
    created_at: datetime
    continuation_plan_sha256: Sha256Digest
    corrected_capability_plan_sha256: Sha256Digest
    together_suite_sha256: Sha256Digest
    provisional_authorization_sha256: Sha256Digest
    provisional_state_sha256: Sha256Digest
    provisional_candidate_id: StableId
    provisional_role: LLMRole
    provisional_outcome: Literal[ProviderCallOutcome.INVALID_OUTPUT]
    provisional_failure_code: Literal["structured_output_invalid"]
    provisional_response_schema_sha256: Sha256Digest
    provisional_diagnostic_available: Literal[False] = False
    provisional_candidate_rejection_final: Literal[False] = False
    all_candidate_ids: list[StableId] = Field(min_length=3, max_length=3)
    remaining_candidate_ids: list[StableId] = Field(min_length=2, max_length=2)
    uniform_failure_required_candidate_count: Literal[3] = 3
    uniform_failure_requires_same_role: Literal[True] = True
    uniform_failure_requires_exact_response_schema: Literal[True] = True
    uniform_failure_disposition: Literal[
        "shared_harness_review_before_candidate_rejection"
    ] = "shared_harness_review_before_candidate_rejection"
    nonuniform_failure_disposition: Literal[
        "candidate_specific_review_using_content_free_diagnostics"
    ] = "candidate_specific_review_using_content_free_diagnostics"
    future_invalid_output_diagnostic_required: Literal[True] = True
    diagnostic_record_version: Literal[
        "phase4_provider_structured_output_diagnostic.v1"
    ] = "phase4_provider_structured_output_diagnostic.v1"
    provider_inference_calls_executed_by_policy_creation: Literal[0] = 0
    provider_spend_microusd_by_policy_creation: Literal[0] = 0

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capability adjudication created_at needs timezone")
        return value

    @model_validator(mode="after")
    def require_candidate_partition(self) -> Self:
        if self.all_candidate_ids != sorted(self.all_candidate_ids) or len(
            set(self.all_candidate_ids)
        ) != len(self.all_candidate_ids):
            raise ValueError("adjudication candidate ids must be canonical")
        if self.remaining_candidate_ids != sorted(
            self.remaining_candidate_ids
        ) or len(set(self.remaining_candidate_ids)) != len(
            self.remaining_candidate_ids
        ):
            raise ValueError("adjudication remaining ids must be canonical")
        if set(self.remaining_candidate_ids) != (
            set(self.all_candidate_ids) - {self.provisional_candidate_id}
        ):
            raise ValueError("adjudication candidate partition differs")
        if self.uniform_failure_required_candidate_count != len(
            self.all_candidate_ids
        ):
            raise ValueError("uniform failure count must cover every candidate")
        return self


class TogetherAdjudicatedCandidateCapabilityAuthorization(ContractModel):
    """Private future-candidate authorization bound to the frozen policy."""

    schema_version: Literal[
        "preference_eval_phase4_adjudicated_candidate_authorization.v1"
    ] = "preference_eval_phase4_adjudicated_candidate_authorization.v1"
    adjudication_policy_sha256: Sha256Digest
    provisional_state_sha256: Sha256Digest
    candidate_id: StableId
    candidate_authorization: TogetherCandidateCapabilityAuthorizationBundle

    @model_validator(mode="after")
    def require_candidate_match(self) -> Self:
        if (
            self.candidate_id
            != self.candidate_authorization.manual_approval.candidate_id
        ):
            raise ValueError("adjudicated authorization candidate differs")
        return self


def _terminal_binding(
    state: TogetherCandidateCapabilityExecutionState,
) -> tuple[ProviderCallFinalization, ProviderRequestBinding]:
    if state.receipt is not None or not state.provider_journal.finalizations:
        raise ValueError("adjudication requires one terminal failed state")
    finalization = state.provider_journal.finalizations[-1]
    bindings = {
        item.call_id: item for item in state.provider_journal.request_bindings
    }
    return finalization, bindings[finalization.call_id]


def build_capability_adjudication_policy(
    continuation: TogetherCapabilityContinuationPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    provisional_authorization: TogetherCandidateCapabilityAuthorizationBundle,
    provisional_state: TogetherCandidateCapabilityExecutionState,
    *,
    policy_id: str,
    policy_version: int,
    created_at: datetime,
) -> TogetherCapabilityAdjudicationPolicy:
    if continuation.corrected_capability_plan_sha256 != content_sha256(
        corrected_plan
    ):
        raise ValueError("adjudication continuation binds another plan")
    if (
        corrected_plan.together_suite_sha256,
        corrected_plan.robustness_profile_sha256,
    ) != (content_sha256(suite), content_sha256(profile)):
        raise ValueError("adjudication plan inputs differ")
    candidate_id = provisional_authorization.manual_approval.candidate_id
    candidate_plan = candidate_plan_for(continuation, candidate_id)
    validate_candidate_capability_execution_state(
        provisional_state,
        continuation,
        candidate_plan,
        provisional_authorization,
        suite,
        profile,
    )
    finalization, binding = _terminal_binding(provisional_state)
    if (
        finalization.outcome is not ProviderCallOutcome.INVALID_OUTPUT
        or finalization.failure_code != "structured_output_invalid"
    ):
        raise ValueError("adjudication provisional state is not schema-invalid")
    role_contracts = {item.role: item for item in suite.shared_role_contracts}
    if (
        binding.response_schema_sha256
        != role_contracts[binding.role].response_schema_sha256
    ):
        raise ValueError("adjudication failure binds another response schema")
    if created_at < finalization.created_at:
        raise ValueError("adjudication policy predates provisional failure")
    all_candidate_ids = sorted(
        item.candidate_id for item in continuation.candidate_plans
    )
    return TogetherCapabilityAdjudicationPolicy(
        policy_id=policy_id,
        policy_version=policy_version,
        created_at=created_at,
        continuation_plan_sha256=content_sha256(continuation),
        corrected_capability_plan_sha256=content_sha256(corrected_plan),
        together_suite_sha256=content_sha256(suite),
        provisional_authorization_sha256=content_sha256(
            provisional_authorization
        ),
        provisional_state_sha256=content_sha256(provisional_state),
        provisional_candidate_id=candidate_id,
        provisional_role=binding.role,
        provisional_outcome=ProviderCallOutcome.INVALID_OUTPUT,
        provisional_failure_code="structured_output_invalid",
        provisional_response_schema_sha256=binding.response_schema_sha256,
        all_candidate_ids=all_candidate_ids,
        remaining_candidate_ids=[
            item for item in all_candidate_ids if item != candidate_id
        ],
    )


def validate_capability_adjudication_policy(
    policy: TogetherCapabilityAdjudicationPolicy,
    continuation: TogetherCapabilityContinuationPlan,
    corrected_plan: TogetherCapabilityPlan,
    suite: Phase4TogetherSuite,
    profile: Phase4ERobustnessProfile,
    provisional_authorization: TogetherCandidateCapabilityAuthorizationBundle,
    provisional_state: TogetherCandidateCapabilityExecutionState,
) -> None:
    rebuilt = build_capability_adjudication_policy(
        continuation,
        corrected_plan,
        suite,
        profile,
        provisional_authorization,
        provisional_state,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        created_at=policy.created_at,
    )
    if policy != rebuilt:
        raise ValueError("capability adjudication policy does not rebuild")


def build_adjudicated_candidate_authorization(
    policy: TogetherCapabilityAdjudicationPolicy,
    authorization: TogetherCandidateCapabilityAuthorizationBundle,
) -> TogetherAdjudicatedCandidateCapabilityAuthorization:
    candidate_id = authorization.manual_approval.candidate_id
    if candidate_id not in policy.remaining_candidate_ids:
        raise ValueError("candidate is outside adjudication continuation")
    return TogetherAdjudicatedCandidateCapabilityAuthorization(
        adjudication_policy_sha256=content_sha256(policy),
        provisional_state_sha256=policy.provisional_state_sha256,
        candidate_id=candidate_id,
        candidate_authorization=authorization,
    )


def validate_adjudicated_candidate_authorization(
    wrapper: TogetherAdjudicatedCandidateCapabilityAuthorization,
    policy: TogetherCapabilityAdjudicationPolicy,
) -> None:
    rebuilt = build_adjudicated_candidate_authorization(
        policy,
        wrapper.candidate_authorization,
    )
    if wrapper != rebuilt:
        raise ValueError("adjudicated candidate authorization does not rebuild")


def capability_adjudication_summary(
    policy: TogetherCapabilityAdjudicationPolicy,
) -> dict[str, JsonValue]:
    return {
        "schema_version": policy.schema_version,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "policy_sha256": content_sha256(policy),
        "candidate_count": len(policy.all_candidate_ids),
        "provisional_failure_count": 1,
        "remaining_candidate_count": len(policy.remaining_candidate_ids),
        "uniform_failure_required_candidate_count": (
            policy.uniform_failure_required_candidate_count
        ),
        "future_invalid_output_diagnostic_required": (
            policy.future_invalid_output_diagnostic_required
        ),
        "provider_inference_calls_executed_by_policy_creation": 0,
        "provider_spend_microusd_by_policy_creation": 0,
    }


def load_capability_adjudication_policy(
    path: str | Path,
) -> TogetherCapabilityAdjudicationPolicy:
    return TogetherCapabilityAdjudicationPolicy.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
