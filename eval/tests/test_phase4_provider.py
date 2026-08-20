from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_provider import (
    PrivateStructuredProviderRequest,
    ProviderBudgetRuntime,
    ProviderCallOutcome,
    ProviderDataScope,
    ProviderNoChargeAttestation,
    ProviderNoChargeBasis,
    ProviderPriceCard,
    ProviderPrivacyAttestation,
    ProviderRequestBinding,
    ProviderSeedStatus,
    ProviderTransportResult,
    ScriptedProviderTransport,
    build_public_development_attestation,
    prepare_provider_request,
    price_provider_tokens,
    provider_request_content_sha256,
)
from eval.phase4_qualification import (
    CandidateQualificationResult,
    DevelopmentPredictionMetrics,
    Phase4QualificationBundle,
    ProjectedRoleUsage,
    ProviderCallAssessment,
    ProviderCostProjection,
    QualificationStatus,
    build_candidate_qualification_result,
    build_phase4_qualification_bundle,
    build_provider_cost_projection,
    phase4_qualification_summary,
    validate_phase4_qualification_bundle,
)
from eval.phase4_robustness import (
    BudgetSegment,
    LLMRole,
    ModelCapability,
    OpenWeightModelCandidate,
    PHASE4E_PERTURBATION_EXPECTATIONS,
    Phase4ERobustnessProfile,
    ProviderUsageLedger,
    RobustnessAggregate,
    RobustnessPerturbationKind,
    build_robustness_evaluation_binding,
    load_phase4_robustness_profile,
)
from eval.validate_phase4_qualification import main as validate_main

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
NOW = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
ZERO_HASH = "0" * 64
FIXTURE_HASH = "1" * 64


class DemoStructuredOutput(ContractModel):
    choice: str
    confidence: float


OUTPUT_ADAPTER = TypeAdapter(DemoStructuredOutput)
NON_JSON_OUTPUT_ADAPTER = TypeAdapter(set[int])


def profile() -> Phase4ERobustnessProfile:
    return load_phase4_robustness_profile(PROFILE_PATH)


def candidate(candidate_id: str) -> OpenWeightModelCandidate:
    return OpenWeightModelCandidate(
        candidate_id=candidate_id,
        artifact_id=f"{candidate_id}_artifact",
        artifact_version=1,
        upstream_model_id=f"publisher/{candidate_id}",
        upstream_model_revision=f"{candidate_id}-upstream-revision",
        weights_manifest_sha256=content_sha256(f"{candidate_id}:weights"),
        license_id="open-weight-license",
        license_sha256=content_sha256(f"{candidate_id}:license"),
        deployment_mode="hosted_api",
        backend_id="provider_neutral_backend",
        backend_version=1,
        serving_model_id=f"provider/{candidate_id}",
        serving_model_revision=f"{candidate_id}-serving-revision",
        provider_terms_sha256=content_sha256(f"{candidate_id}:terms"),
        context_window_tokens=32_768,
        capabilities=list(ModelCapability),
    )


def price_card(
    model: OpenWeightModelCandidate,
    *,
    input_rate: int = 200_000,
    output_rate: int = 600_000,
) -> ProviderPriceCard:
    return ProviderPriceCard(
        price_card_id=f"{model.candidate_id}_price",
        price_card_version=1,
        model_candidate_id=model.candidate_id,
        model_candidate_artifact_version=model.artifact_version,
        model_candidate_sha256=content_sha256(model),
        input_microusd_per_million_tokens=input_rate,
        output_microusd_per_million_tokens=output_rate,
        provider_pricing_terms_sha256=content_sha256(
            f"{model.candidate_id}:pricing"
        ),
        effective_at=NOW,
    )


def tool_definitions(role: LLMRole) -> list[dict[str, JsonValue]]:
    if role is not LLMRole.INTERVIEWER:
        return []
    return [
        {
            "name": "read_evidence_coverage",
            "description": "Read aggregate evidence coverage.",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def prepared_request(
    robustness_profile: Phase4ERobustnessProfile,
    model: OpenWeightModelCandidate,
    pricing: ProviderPriceCard,
    *,
    call_id: str,
    role: LLMRole,
    created_at: datetime,
    attestation_id: str | None = None,
    provider_seed_parameter_sent: bool = True,
    response_adapter: TypeAdapter = OUTPUT_ADAPTER,
) -> PrivateStructuredProviderRequest:
    prompt_payload = {"system": "Return the exact structured contract."}
    input_payload = {"public_development_case": "case_one"}
    schema = response_adapter.json_schema(mode="validation")
    tools = tool_definitions(role)
    attestation = build_public_development_attestation(
        attestation_id=attestation_id or f"{call_id}_privacy",
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_json_schema=schema,
        tool_definitions=tools,
    )
    return prepare_provider_request(
        robustness_profile,
        model,
        pricing,
        call_id=call_id,
        role=role,
        prompt_id=f"{role.value}_prompt",
        prompt_version=1,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_schema_id=f"{role.value}_response",
        response_schema_version=1,
        response_adapter=response_adapter,
        privacy_attestation=attestation,
        request_seed=42,
        provider_seed_parameter_sent=provider_seed_parameter_sent,
        temperature=0.0,
        input_token_upper_bound=1_000,
        output_token_upper_bound=200,
        created_at=created_at,
        tool_definitions=tools,
    )


def successful_transport_result(
    completed_at: datetime,
    *,
    latency_ms: float = 20.0,
    tool_calls: int = 0,
) -> ProviderTransportResult:
    return ProviderTransportResult(
        outcome=ProviderCallOutcome.SUCCESS,
        output_payload={"choice": "one", "confidence": 0.75},
        input_tokens=100,
        output_tokens=20,
        provider_request_id="provider-request-id",
        provider_request_sent=True,
        provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
        tool_call_count=tool_calls,
        tool_call_failure_count=0,
        latency_ms=latency_ms,
        completed_at=completed_at,
    )


def robustness_aggregate(
    robustness_profile: Phase4ERobustnessProfile,
    model: OpenWeightModelCandidate,
    kind: RobustnessPerturbationKind,
    *,
    mean_jsd: float,
    invalid_count: int = 0,
    flip_count: int = 0,
) -> RobustnessAggregate:
    count = {
        RobustnessPerturbationKind.PROMPT_PARAPHRASE: 2,
        RobustnessPerturbationKind.OPTION_ORDER: 1,
        RobustnessPerturbationKind.OPTION_LABEL: 1,
        RobustnessPerturbationKind.STOCHASTIC_REPEAT: 3,
    }[kind]
    valid_count = count - invalid_count
    return RobustnessAggregate(
        evaluation_binding=build_robustness_evaluation_binding(
            robustness_profile,
            model,
        ),
        comparison_sha256s=[
            content_sha256(f"{model.candidate_id}:{kind.value}:{index}")
            for index in range(count)
        ],
        perturbation_kind=kind,
        expectation=PHASE4E_PERTURBATION_EXPECTATIONS[kind],
        comparison_count=count,
        invalid_output_count=invalid_count,
        invalid_output_rate=invalid_count / count,
        valid_comparison_count=valid_count,
        top_choice_flip_count=flip_count,
        top_choice_flip_rate=(
            flip_count / valid_count if valid_count else None
        ),
        mean_max_absolute_probability_delta=(
            mean_jsd if valid_count else None
        ),
        maximum_absolute_probability_delta=(
            mean_jsd if valid_count else None
        ),
        mean_jensen_shannon_divergence=(mean_jsd if valid_count else None),
        maximum_jensen_shannon_divergence=(mean_jsd if valid_count else None),
        unsupported_assumption_delta_total=0,
    )


def development_metrics(
    *,
    mean_log_loss: float,
) -> DevelopmentPredictionMetrics:
    return DevelopmentPredictionMetrics(
        fixture_id="preference_eval_dev_v1",
        fixture_version=1,
        fixture_sha256=FIXTURE_HASH,
        sample_count=48,
        mean_log_loss=mean_log_loss,
        multiclass_brier=0.4,
        top_choice_accuracy=0.7,
        high_confidence_coverage=0.5,
        high_confidence_delegated_error=0.1,
    )


def projection(
    model: OpenWeightModelCandidate,
    pricing: ProviderPriceCard,
) -> ProviderCostProjection:
    return build_provider_cost_projection(
        model,
        pricing,
        [
            ProjectedRoleUsage(
                role=role,
                request_count=2,
                input_tokens_per_request=500,
                output_tokens_per_request=100,
            )
            for role in LLMRole
        ],
        workload_id="phase4_personal_study_projection",
        workload_version=1,
        workload_sha256=content_sha256("shared projected call workload"),
        token_counter_id=f"{model.candidate_id}_tokenizer",
        token_counter_version=1,
        token_counter_sha256=content_sha256(
            f"{model.candidate_id}:tokenizer"
        ),
    )


def test_one_budgeted_adapter_serves_all_five_roles_and_audits():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_all_roles",
        journal_id="provider_journal_all_roles",
    )
    results = [
        successful_transport_result(
            NOW + timedelta(seconds=index, milliseconds=500),
            tool_calls=(1 if role is LLMRole.INTERVIEWER else 0),
        )
        for index, role in enumerate(LLMRole, start=1)
    ]
    transport = ScriptedProviderTransport(results)

    for index, role in enumerate(LLMRole, start=1):
        request = prepared_request(
            robustness_profile,
            model,
            pricing,
            call_id=f"call_{role.value}",
            role=role,
            created_at=NOW + timedelta(seconds=index),
        )
        execution = runtime.execute(
            request,
            pricing,
            OUTPUT_ADAPTER,
            transport,
            segment=BudgetSegment.QUALIFICATION,
        )
        assert isinstance(execution.output, DemoStructuredOutput)
        assert execution.finalization.outcome is ProviderCallOutcome.SUCCESS

    runtime.audit([model], [pricing])
    journal = runtime.journal_snapshot()
    assert [item.role for item in journal.request_bindings] == list(LLMRole)
    assert len(transport.requests) == len(LLMRole)
    expected = len(LLMRole) * price_provider_tokens(
        pricing,
        input_tokens=100,
        output_tokens=20,
    )
    assert runtime.committed_totals[BudgetSegment.QUALIFICATION] == expected


def test_private_request_hashes_bind_content_and_retry_ignores_local_identity():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    first = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="first_attempt",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
        attestation_id="shared_privacy_attestation",
    )
    retry = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="retry_attempt",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW + timedelta(seconds=1),
        attestation_id="shared_privacy_attestation",
    )

    assert content_sha256(first.binding) != content_sha256(retry.binding)
    assert provider_request_content_sha256(
        first.binding
    ) == provider_request_content_sha256(retry.binding)

    tampered = first.model_dump(mode="json")
    tampered["input_payload"] = {"public_development_case": "changed"}
    with pytest.raises(ValidationError, match="does not bind transmitted payload"):
        first.__class__.model_validate(tampered)


def test_provider_error_closes_reservation_and_retry_uses_same_request():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_retry",
        journal_id="provider_journal_retry",
    )
    first = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="first_attempt",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
        attestation_id="shared_privacy_attestation",
    )
    failed_transport = ScriptedProviderTransport(
        [
            ProviderTransportResult(
                outcome=ProviderCallOutcome.PROVIDER_ERROR,
                input_tokens=100,
                output_tokens=0,
                provider_request_id="provider-failure-id",
                provider_request_sent=True,
                provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
                latency_ms=12.0,
                failure_code="provider_overloaded",
                completed_at=NOW + timedelta(milliseconds=500),
            )
        ]
    )
    first_execution = runtime.execute(
        first,
        pricing,
        OUTPUT_ADAPTER,
        failed_transport,
        segment=BudgetSegment.QUALIFICATION,
    )
    assert first_execution.output is None
    assert first_execution.finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR

    retry = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="retry_attempt",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW + timedelta(seconds=1),
        attestation_id="shared_privacy_attestation",
    )
    retry_execution = runtime.execute(
        retry,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport(
            [successful_transport_result(NOW + timedelta(seconds=2))]
        ),
        segment=BudgetSegment.RETRY_RESERVE,
        retry_of_call_id="first_attempt",
    )
    assert retry_execution.finalization.outcome is ProviderCallOutcome.SUCCESS
    runtime.audit([model], [pricing])
    assert len(runtime.ledger_snapshot().calls) == 2


def test_cancelled_call_releases_full_reservation_and_is_auditable():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model).model_copy(
        update={"fixed_request_cost_microusd": 10}
    )
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_cancel",
        journal_id="provider_journal_cancel",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="cancelled_call",
        role=LLMRole.HYBRID_READOUT,
        created_at=NOW,
    )
    finalization = runtime.cancel(
        request,
        pricing,
        segment=BudgetSegment.QUALIFICATION,
        completed_at=NOW + timedelta(seconds=1),
    )

    assert finalization.outcome is ProviderCallOutcome.CANCELLED
    assert runtime.committed_totals[BudgetSegment.QUALIFICATION] == 0
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd == 0
    runtime.audit([model], [pricing])


def test_progressive_artifacts_resume_and_close_an_aborted_transport():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_resume",
        journal_id="provider_journal_resume",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="aborted_transport",
        role=LLMRole.HYBRID_READOUT,
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="has no result"):
        runtime.execute(
            request,
            pricing,
            OUTPUT_ADAPTER,
            ScriptedProviderTransport([]),
            segment=BudgetSegment.QUALIFICATION,
        )
    reserved = runtime.committed_totals[BudgetSegment.QUALIFICATION]
    assert reserved > 0

    resumed = ProviderBudgetRuntime.resume(
        robustness_profile,
        runtime.ledger_snapshot(),
        runtime.journal_snapshot(),
        [model],
        [pricing],
    )
    assert resumed.committed_totals[BudgetSegment.QUALIFICATION] == reserved
    resumed.cancel_outstanding(
        "aborted_transport",
        pricing,
        completed_at=NOW + timedelta(seconds=1),
        no_charge_attestation=ProviderNoChargeAttestation(
            attestation_id="aborted_transport_no_charge",
            call_id="aborted_transport",
            basis=ProviderNoChargeBasis.PROVIDER_VOID_CONFIRMED,
            provider_confirmation_sha256=content_sha256(
                "provider confirmed no request was billed"
            ),
            confirmed_at=NOW + timedelta(milliseconds=900),
        ),
    )
    assert resumed.committed_totals[BudgetSegment.QUALIFICATION] == 0
    resumed.audit([model], [pricing])


def test_invalid_structured_output_is_billed_and_terminal():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_invalid",
        journal_id="provider_journal_invalid",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="invalid_output",
        role=LLMRole.EVIDENCE_EXTRACTOR,
        created_at=NOW,
    )
    invalid = successful_transport_result(NOW + timedelta(seconds=1)).model_copy(
        update={"output_payload": {"unexpected": "shape"}}
    )
    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport([invalid]),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output is None
    assert execution.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd > 0
    runtime.audit([model], [pricing])


def test_non_json_structured_output_is_billed_and_terminal():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_non_json",
        journal_id="provider_journal_non_json",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="non_json_output",
        role=LLMRole.EVIDENCE_EXTRACTOR,
        created_at=NOW,
        response_adapter=NON_JSON_OUTPUT_ADAPTER,
    )
    result = successful_transport_result(
        NOW + timedelta(seconds=1)
    ).model_copy(update={"output_payload": [1, 2]})

    execution = runtime.execute(
        request,
        pricing,
        NON_JSON_OUTPUT_ADAPTER,
        ScriptedProviderTransport([result]),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output is None
    assert execution.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd > 0
    runtime.audit([model], [pricing])


def test_token_bound_overrun_records_true_usage_and_closes_call():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_token_overrun",
        journal_id="provider_journal_token_overrun",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="token_bound_overrun",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
    )
    overrun = successful_transport_result(
        NOW + timedelta(seconds=1)
    ).model_copy(update={"input_tokens": 1_001, "output_tokens": 201})

    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport([overrun]),
        segment=BudgetSegment.QUALIFICATION,
    )

    usage = runtime.ledger_snapshot().calls[0]
    assert execution.output is None
    assert (
        execution.finalization.outcome
        is ProviderCallOutcome.TOKEN_BOUND_EXCEEDED
    )
    assert (usage.input_tokens, usage.output_tokens) == (1_001, 201)
    assert usage.authorization_overrun_microusd > 0
    assert runtime.committed_totals[BudgetSegment.QUALIFICATION] == (
        usage.billed_cost_microusd
    )
    runtime.audit([model], [pricing])

    old_usage = usage.model_dump(mode="json")
    old_usage["record_version"] = "phase4_provider_call_usage.v1"
    with pytest.raises(ValidationError):
        usage.__class__.model_validate(old_usage)
    old_ledger = runtime.ledger_snapshot().model_dump(mode="json")
    old_ledger["schema_version"] = "phase4_provider_usage_ledger.v1"
    with pytest.raises(ValidationError):
        ProviderUsageLedger.model_validate(old_ledger)


@pytest.mark.parametrize(
    ("role", "seed_sent", "seed_status", "tool_calls", "failure_code"),
    [
        (
            LLMRole.DIRECT_READOUT,
            False,
            ProviderSeedStatus.SENT_UNCONFIRMED,
            0,
            "transport_seed_claim_invalid",
        ),
        (
            LLMRole.HYBRID_READOUT,
            True,
            ProviderSeedStatus.SENT_UNCONFIRMED,
            1,
            "transport_tool_claim_invalid",
        ),
    ],
)
def test_transport_contract_errors_record_observed_paid_usage(
    role,
    seed_sent,
    seed_status,
    tool_calls,
    failure_code,
):
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id=f"provider_usage_{failure_code}",
        journal_id=f"provider_journal_{failure_code}",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id=failure_code,
        role=role,
        created_at=NOW,
        provider_seed_parameter_sent=seed_sent,
    )
    result = successful_transport_result(
        NOW + timedelta(seconds=1),
        tool_calls=tool_calls,
    ).model_copy(update={"provider_seed_status": seed_status})

    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport([result]),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output is None
    assert (
        execution.finalization.outcome
        is ProviderCallOutcome.TRANSPORT_CONTRACT_ERROR
    )
    assert execution.finalization.failure_code == failure_code
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd > 0
    runtime.audit([model], [pricing])


def test_unsent_transport_error_has_attested_zero_cost_even_with_fixed_fee():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model).model_copy(
        update={"fixed_request_cost_microusd": 25}
    )
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_unsent_transport",
        journal_id="provider_journal_unsent_transport",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="unsent_transport",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
    )
    result = ProviderTransportResult(
        outcome=ProviderCallOutcome.TRANSPORT_ERROR,
        input_tokens=0,
        output_tokens=0,
        provider_request_sent=False,
        provider_seed_status=ProviderSeedStatus.NOT_SENT,
        latency_ms=1.0,
        failure_code="connection_failed_before_send",
        completed_at=NOW + timedelta(seconds=1),
    )

    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport([result]),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.finalization.outcome is ProviderCallOutcome.CANCELLED
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd == 0
    assert len(runtime.journal_snapshot().no_charge_attestations) == 1
    runtime.audit([model], [pricing])


def test_sent_zero_token_transport_error_still_pays_fixed_request_cost():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model).model_copy(
        update={"fixed_request_cost_microusd": 25}
    )
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_sent_transport",
        journal_id="provider_journal_sent_transport",
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="sent_transport",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
    )
    result = ProviderTransportResult(
        outcome=ProviderCallOutcome.TRANSPORT_ERROR,
        input_tokens=0,
        output_tokens=0,
        provider_request_sent=True,
        provider_seed_status=ProviderSeedStatus.NOT_SENT,
        latency_ms=1.0,
        failure_code="connection_lost_after_send",
        completed_at=NOW + timedelta(seconds=1),
    )

    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport([result]),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.finalization.outcome is ProviderCallOutcome.TRANSPORT_ERROR
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd == 25
    runtime.audit([model], [pricing])


def test_participant_privacy_attestation_requires_resolved_local_scan():
    with pytest.raises(ValidationError, match="cannot retain unresolved"):
        ProviderPrivacyAttestation(
            attestation_id="participant_scan",
            data_scope=ProviderDataScope.PSEUDONYMOUS_PARTICIPANT,
            transmitted_payload_sha256=ZERO_HASH,
            participant_content_present=True,
            opaque_participant_id="participant_opaque_001",
            scanner_id="local_identifier_scanner",
            scanner_version=1,
            scanner_result_sha256=ZERO_HASH,
            direct_identifier_finding_count=1,
            unresolved_finding_count=1,
        )

    attestation = ProviderPrivacyAttestation(
        attestation_id="participant_scan",
        data_scope=ProviderDataScope.PSEUDONYMOUS_PARTICIPANT,
        transmitted_payload_sha256=ZERO_HASH,
        participant_content_present=True,
        opaque_participant_id="participant_opaque_001",
        scanner_id="local_identifier_scanner",
        scanner_version=1,
        scanner_result_sha256=ZERO_HASH,
        direct_identifier_finding_count=2,
        redacted_finding_count=1,
        participant_confirmed_false_positive_count=1,
    )
    assert attestation.approved_for_transmission is True


def test_live_authorization_path_does_not_run_full_history_validation(monkeypatch):
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_incremental",
        journal_id="provider_journal_incremental",
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("full ledger validation entered live hot path")

    monkeypatch.setattr(
        "eval.phase4_provider.validate_provider_usage_ledger",
        fail_if_called,
    )
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="incremental_call",
        role=LLMRole.ONTOLOGY_PROPOSER,
        created_at=NOW,
    )
    execution = runtime.execute(
        request,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport(
            [successful_transport_result(NOW + timedelta(seconds=1))]
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    assert execution.finalization.outcome is ProviderCallOutcome.SUCCESS


def test_next_authorization_must_follow_prior_completion_timestamp():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_monotonic_authorization",
        journal_id="provider_journal_monotonic_authorization",
    )
    first = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="future_stamped_completion",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
    )
    runtime.execute(
        first,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport(
            [successful_transport_result(NOW + timedelta(seconds=100))]
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    second = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="backdated_next_authorization",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW + timedelta(seconds=5),
    )
    second_transport = ScriptedProviderTransport(
        [successful_transport_result(NOW + timedelta(seconds=6))]
    )

    with pytest.raises(ValueError, match="follow the latest runtime event"):
        runtime.execute(
            second,
            pricing,
            OUTPUT_ADAPTER,
            second_transport,
            segment=BudgetSegment.QUALIFICATION,
        )

    assert second_transport.requests == []
    runtime.audit([model], [pricing])


def test_outstanding_call_cannot_be_finalized_before_a_later_runtime_event():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_monotonic_finalization",
        journal_id="provider_journal_monotonic_finalization",
    )
    outstanding = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="outstanding_call",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="has no result"):
        runtime.execute(
            outstanding,
            pricing,
            OUTPUT_ADAPTER,
            ScriptedProviderTransport([]),
            segment=BudgetSegment.QUALIFICATION,
        )
    later = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="later_closed_call",
        role=LLMRole.DIRECT_READOUT,
        created_at=NOW + timedelta(seconds=5),
    )
    runtime.execute(
        later,
        pricing,
        OUTPUT_ADAPTER,
        ScriptedProviderTransport(
            [successful_transport_result(NOW + timedelta(seconds=6))]
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    backdated_attestation = ProviderNoChargeAttestation(
        attestation_id="outstanding_backdated_no_charge",
        call_id="outstanding_call",
        basis=ProviderNoChargeBasis.PROVIDER_VOID_CONFIRMED,
        provider_confirmation_sha256=content_sha256("provider void proof"),
        confirmed_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="predate the latest runtime event"):
        runtime.cancel_outstanding(
            "outstanding_call",
            pricing,
            completed_at=NOW + timedelta(seconds=2),
            no_charge_attestation=backdated_attestation,
        )

    runtime.cancel_outstanding(
        "outstanding_call",
        pricing,
        completed_at=NOW + timedelta(seconds=7),
        no_charge_attestation=backdated_attestation,
    )
    runtime.audit([model], [pricing])


def qualification_artifacts():
    robustness_profile = profile()
    candidates = [candidate(f"candidate_{letter}") for letter in "abc"]
    prices = [price_card(item) for item in candidates]
    runtime = ProviderBudgetRuntime(
        robustness_profile,
        ledger_id="provider_usage_qualification",
        journal_id="provider_journal_qualification",
    )
    assessments: list[ProviderCallAssessment] = []
    second = 0
    for model, pricing in zip(candidates, prices, strict=True):
        for role in LLMRole:
            second += 1
            call_id = f"{model.candidate_id}_{role.value}"
            request = prepared_request(
                robustness_profile,
                model,
                pricing,
                call_id=call_id,
                role=role,
                created_at=NOW + timedelta(seconds=second),
            )
            execution = runtime.execute(
                request,
                pricing,
                OUTPUT_ADAPTER,
                ScriptedProviderTransport(
                    [
                        successful_transport_result(
                            NOW + timedelta(seconds=second, milliseconds=500),
                            latency_ms=float(second),
                            tool_calls=(
                                1 if role is LLMRole.INTERVIEWER else 0
                            ),
                        )
                    ]
                ),
                segment=BudgetSegment.QUALIFICATION,
            )
            assessments.append(
                ProviderCallAssessment(
                    call_id=call_id,
                    role=role,
                    finalization_sha256=content_sha256(
                        execution.finalization
                    ),
                    exact_role_contract_valid=True,
                    tool_result_replay_valid=(
                        True if role is LLMRole.INTERVIEWER else None
                    ),
                )
            )
    ledger = runtime.ledger_snapshot()
    journal = runtime.journal_snapshot()
    runtime.audit(candidates, prices)
    sensitivity = {
        "candidate_a": 0.02,
        "candidate_b": 0.01,
        "candidate_c": 0.01,
    }
    log_loss = {
        "candidate_a": 0.40,
        "candidate_b": 0.60,
        "candidate_c": 0.70,
    }
    aggregates = [
        robustness_aggregate(
            robustness_profile,
            model,
            kind,
            mean_jsd=(
                sensitivity[model.candidate_id]
                if kind
                in {
                    RobustnessPerturbationKind.PROMPT_PARAPHRASE,
                    RobustnessPerturbationKind.STOCHASTIC_REPEAT,
                }
                else 0.0
            ),
        )
        for model in candidates
        for kind in RobustnessPerturbationKind
    ]
    results = [
        build_candidate_qualification_result(
            robustness_profile,
            model,
            pricing,
            ledger,
            journal,
            [
                item
                for item in assessments
                if item.call_id.startswith(f"{model.candidate_id}_")
            ],
            aggregates,
            development_metrics(mean_log_loss=log_loss[model.candidate_id]),
            projection(model, pricing),
        )
        for model, pricing in zip(candidates, prices, strict=True)
    ]
    bundle = build_phase4_qualification_bundle(
        robustness_profile,
        qualification_id="phase4_qualification_test",
        qualification_version=1,
        created_at=NOW + timedelta(minutes=1),
        public_development_fixture_id="preference_eval_dev_v1",
        public_development_fixture_version=1,
        public_development_fixture_sha256=FIXTURE_HASH,
        candidates=candidates,
        price_cards=prices,
        ledger=ledger,
        journal=journal,
        results=results,
        call_assessments=assessments,
        robustness_aggregates=aggregates,
    )
    return robustness_profile, bundle, ledger, journal


def test_qualification_selects_three_candidates_by_frozen_priority_order():
    robustness_profile, bundle, ledger, journal = qualification_artifacts()

    validate_phase4_qualification_bundle(
        bundle,
        robustness_profile,
        ledger,
        journal,
    )
    assert bundle.status is QualificationStatus.SELECTED
    assert bundle.selected_model_candidate_id == "candidate_b"
    assert len(bundle.candidates) == 3
    assert all(result.passed_hard_gates for result in bundle.results)
    assert bundle.held_out_study_spend_microusd == 0
    summary = phase4_qualification_summary(bundle)
    assert summary["candidate_count"] == 3
    assert summary["selected_model_candidate_id"] == "candidate_b"

    changed = bundle.model_dump(mode="json")
    changed["selected_model_candidate_id"] = "candidate_a"
    with pytest.raises(ValidationError, match="frozen criteria"):
        Phase4QualificationBundle.model_validate(changed)

    changed = bundle.model_dump(mode="json")
    changed["selection_policy"][
        "prompt_and_stochastic_mean_jsd_tolerance"
    ] = 0.002
    with pytest.raises(ValidationError):
        Phase4QualificationBundle.model_validate(changed)


def test_qualification_bands_negligible_jsd_before_using_log_loss():
    robustness_profile, bundle, ledger, journal = qualification_artifacts()
    results = [item.model_copy(deep=True) for item in bundle.results]
    results[0] = results[0].model_copy(
        update={
            "prompt_and_stochastic_mean_jsd": 0.0201,
            "development_metrics": results[0].development_metrics.model_copy(
                update={"mean_log_loss": 1.0}
            ),
        }
    )
    results[1] = results[1].model_copy(
        update={
            "prompt_and_stochastic_mean_jsd": 0.0202,
            "development_metrics": results[1].development_metrics.model_copy(
                update={"mean_log_loss": 0.1}
            ),
        }
    )
    results[2] = results[2].model_copy(
        update={
            "prompt_and_stochastic_mean_jsd": 0.5,
            "development_metrics": results[2].development_metrics.model_copy(
                update={"mean_log_loss": 0.05}
            ),
        }
    )

    changed = build_phase4_qualification_bundle(
        robustness_profile,
        qualification_id="phase4_qualification_banded_test",
        qualification_version=1,
        created_at=NOW + timedelta(minutes=2),
        public_development_fixture_id=(
            bundle.public_development_fixture_id
        ),
        public_development_fixture_version=(
            bundle.public_development_fixture_version
        ),
        public_development_fixture_sha256=(
            bundle.public_development_fixture_sha256
        ),
        candidates=bundle.candidates,
        price_cards=bundle.price_cards,
        ledger=ledger,
        journal=journal,
        results=results,
        call_assessments=bundle.call_assessments,
        robustness_aggregates=bundle.robustness_aggregates,
    )

    assert changed.selected_model_candidate_id == "candidate_b"


def test_qualification_builder_rejects_missing_usage_without_key_error():
    robustness_profile, bundle, ledger, journal = qualification_artifacts()
    target = bundle.results[0]
    incomplete_ledger = ledger.model_copy(
        update={
            "calls": [
                item
                for item in ledger.calls
                if item.call_id != target.call_ids[0]
            ]
        }
    )
    candidate_by_id = {
        item.candidate_id: item for item in bundle.candidates
    }
    price_by_id = {
        item.model_candidate_id: item for item in bundle.price_cards
    }

    with pytest.raises(ValueError, match="unmatched provider usage"):
        build_candidate_qualification_result(
            robustness_profile,
            candidate_by_id[target.model_candidate_id],
            price_by_id[target.model_candidate_id],
            incomplete_ledger,
            journal,
            [
                item
                for item in bundle.call_assessments
                if item.call_id in target.call_ids
            ],
            bundle.robustness_aggregates,
            target.development_metrics,
            target.cost_projection,
        )


def test_hard_failure_excludes_candidate_instead_of_reordering_criteria():
    _, bundle, _, _ = qualification_artifacts()
    payload = bundle.model_dump(mode="json")
    failed = payload["results"][1]
    failed["provider_call_failure_count"] = 1
    failed["hard_failure_reasons"] = ["provider_call_failure"]
    failed["passed_hard_gates"] = False
    payload["selected_model_candidate_id"] = "candidate_c"

    changed = Phase4QualificationBundle.model_validate(payload)
    assert changed.selected_model_candidate_id == "candidate_c"


def test_qualification_costs_share_workload_and_recompute_from_price_card():
    _, bundle, _, _ = qualification_artifacts()
    payload = bundle.model_dump(mode="json")
    payload["results"][2]["cost_projection"]["workload_sha256"] = "2" * 64
    with pytest.raises(ValidationError, match="share one workload"):
        Phase4QualificationBundle.model_validate(payload)

    payload = bundle.model_dump(mode="json")
    payload["results"][0]["cost_projection"][
        "projected_cost_microusd"
    ] += 1
    with pytest.raises(ValidationError, match="projected cost does not reconcile"):
        Phase4QualificationBundle.model_validate(payload)


def test_qualification_rejects_participant_scope_and_held_out_spend():
    robustness_profile, bundle, ledger, journal = qualification_artifacts()
    changed_binding = journal.request_bindings[0].model_copy(
        update={"data_scope": ProviderDataScope.PSEUDONYMOUS_PARTICIPANT}
    )
    changed_journal = journal.model_copy(
        update={
            "request_bindings": [
                changed_binding,
                *journal.request_bindings[1:],
            ]
        }
    )
    changed_bundle = bundle.model_copy(
        update={
            "provider_execution_journal_sha256": content_sha256(changed_journal)
        }
    )
    with pytest.raises(ValueError, match="participant provider inputs"):
        validate_phase4_qualification_bundle(
            changed_bundle,
            robustness_profile,
            ledger,
            changed_journal,
        )

    changed_authorization = ledger.authorizations[0].model_copy(
        update={"segment": BudgetSegment.HELD_OUT_STUDY}
    )
    changed_ledger = ledger.model_copy(
        update={
            "authorizations": [
                changed_authorization,
                *ledger.authorizations[1:],
            ]
        }
    )
    changed_bundle = bundle.model_copy(
        update={"provider_usage_ledger_sha256": content_sha256(changed_ledger)}
    )
    with pytest.raises((ValidationError, ValueError)):
        validate_phase4_qualification_bundle(
            changed_bundle,
            robustness_profile,
            changed_ledger,
            journal,
        )


def test_qualification_cli_prints_aggregate_only(capsys, tmp_path):
    robustness_profile, bundle, ledger, journal = qualification_artifacts()
    bundle_path = tmp_path / "qualification.json"
    profile_path = tmp_path / "profile.json"
    ledger_path = tmp_path / "ledger.json"
    journal_path = tmp_path / "journal.json"
    for path, artifact in (
        (bundle_path, bundle),
        (profile_path, robustness_profile),
        (ledger_path, ledger),
        (journal_path, journal),
    ):
        path.write_text(
            json.dumps(artifact.model_dump(mode="json")),
            encoding="utf-8",
        )

    assert validate_main(
        [
            str(bundle_path),
            str(profile_path),
            str(ledger_path),
            str(journal_path),
        ]
    ) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary == phase4_qualification_summary(bundle)
    assert "input_payload" not in output
    assert "response_sha256" not in output


def test_cost_projection_requires_all_roles_and_exact_price_card():
    model = candidate("candidate_a")
    pricing = price_card(model)
    with pytest.raises(ValidationError, match="complete Phase 4E v1 set"):
        ProviderCostProjection(
            model_candidate_id=model.candidate_id,
            price_card_sha256=content_sha256(pricing),
            workload_id="phase4_personal_study_projection",
            workload_version=1,
            workload_sha256=content_sha256("shared projected call workload"),
            token_counter_id="candidate_a_tokenizer",
            token_counter_version=1,
            token_counter_sha256=content_sha256("candidate_a:tokenizer"),
            role_usage=[
                ProjectedRoleUsage(
                    role=LLMRole.INTERVIEWER,
                    request_count=1,
                    input_tokens_per_request=1,
                    output_tokens_per_request=1,
                )
            ],
            projected_request_count=1,
            projected_cost_microusd=1,
        )


def test_qualification_result_rejects_caller_asserted_hard_gate():
    _, bundle, _, _ = qualification_artifacts()
    result: CandidateQualificationResult = bundle.results[0]
    payload = result.model_dump(mode="json")
    payload["passed_hard_gates"] = False
    with pytest.raises(ValidationError, match="hard-gate outcome"):
        CandidateQualificationResult.model_validate(payload)


def test_qualification_validator_rebuilds_results_from_bound_sources():
    robustness_profile, bundle, ledger, journal = qualification_artifacts()
    changed_assessment = bundle.call_assessments[0].model_copy(
        update={"exact_role_contract_valid": False}
    )
    changed_hashes = list(bundle.results[0].call_assessment_sha256s)
    changed_hashes[0] = content_sha256(changed_assessment)
    changed_result = bundle.results[0].model_copy(
        update={"call_assessment_sha256s": changed_hashes}
    )
    changed_bundle = bundle.model_copy(
        update={
            "call_assessments": [
                changed_assessment,
                *bundle.call_assessments[1:],
            ],
            "results": [changed_result, *bundle.results[1:]],
        }
    )
    with pytest.raises(ValueError, match="does not rebuild from sources"):
        validate_phase4_qualification_bundle(
            changed_bundle,
            robustness_profile,
            ledger,
            journal,
        )


def test_request_binding_rejects_tool_schema_on_non_interviewer_role():
    robustness_profile = profile()
    model = candidate("candidate_a")
    pricing = price_card(model)
    request = prepared_request(
        robustness_profile,
        model,
        pricing,
        call_id="tool_binding",
        role=LLMRole.INTERVIEWER,
        created_at=NOW,
    )
    payload = request.binding.model_dump(mode="json")
    payload["role"] = LLMRole.DIRECT_READOUT
    with pytest.raises(ValidationError, match="only the interviewer"):
        ProviderRequestBinding.model_validate(payload)


def test_public_attestation_cannot_masquerade_as_participant_scan():
    with pytest.raises(ValidationError, match="cannot claim participant scan"):
        ProviderPrivacyAttestation(
            attestation_id="bad_public_scan",
            data_scope=ProviderDataScope.PUBLIC_DEVELOPMENT,
            transmitted_payload_sha256=ZERO_HASH,
            participant_content_present=False,
            scanner_id="scanner",
            scanner_version=1,
            scanner_result_sha256=ZERO_HASH,
        )
