from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import TypeAdapter

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_capability_io import (
    provider_error_diagnostic_path,
    write_provider_error_diagnostic,
)
from eval.phase4_provider import (
    ProviderBudgetRuntime,
    ProviderCallOutcome,
    ProviderHTTPErrorCode,
    ProviderHTTPErrorEnvelopeState,
    ProviderHTTPErrorMetadata,
    ProviderHTTPErrorType,
    ProviderPriceCard,
    ProviderRejectedRequestField,
    ProviderResponseContract,
    ProviderSeedStatus,
    ProviderTransportResult,
    ScriptedProviderTransport,
    build_public_development_attestation,
    prepare_provider_request,
)
from eval.phase4_robustness import (
    BudgetSegment,
    LLMRole,
    ModelCapability,
    OpenWeightModelCandidate,
    load_phase4_robustness_profile,
)
from eval.phase4_together_live import _together_http_error_metadata


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
NOW = datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)


class DemoOutput(ContractModel):
    choice: str


OUTPUT_CONTRACT = ProviderResponseContract(
    adapter=TypeAdapter(DemoOutput)
)


def _candidate() -> OpenWeightModelCandidate:
    return OpenWeightModelCandidate(
        candidate_id="http_diagnostic_candidate",
        artifact_id="http_diagnostic_artifact",
        artifact_version=1,
        upstream_model_id="publisher/http-diagnostic-model",
        upstream_model_revision="http-diagnostic-upstream-revision",
        weights_manifest_sha256=content_sha256("http-diagnostic-weights"),
        license_id="open-weight-license",
        license_sha256=content_sha256("http-diagnostic-license"),
        deployment_mode="hosted_api",
        backend_id="provider_neutral_backend",
        backend_version=1,
        serving_model_id="provider/http-diagnostic-model",
        serving_model_revision="http-diagnostic-serving-revision",
        provider_terms_sha256=content_sha256("http-diagnostic-terms"),
        context_window_tokens=32_768,
        capabilities=list(ModelCapability),
    )


def _price_card(model: OpenWeightModelCandidate) -> ProviderPriceCard:
    return ProviderPriceCard(
        price_card_id="http_diagnostic_price",
        price_card_version=1,
        model_candidate_id=model.candidate_id,
        model_candidate_artifact_version=model.artifact_version,
        model_candidate_sha256=content_sha256(model),
        input_microusd_per_million_tokens=200_000,
        output_microusd_per_million_tokens=600_000,
        provider_pricing_terms_sha256=content_sha256(
            "http-diagnostic-pricing"
        ),
        effective_at=NOW,
    )


def _request(model: OpenWeightModelCandidate, price: ProviderPriceCard):
    profile = load_phase4_robustness_profile(PROFILE_PATH)
    prompt_payload = {"system": "Return the structured contract."}
    input_payload = {"public_development_case": "case_one"}
    schema = OUTPUT_CONTRACT.json_schema(mode="validation")
    attestation = build_public_development_attestation(
        attestation_id="http_diagnostic_privacy",
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_json_schema=schema,
        tool_definitions=[],
    )
    return prepare_provider_request(
        profile,
        model,
        price,
        call_id="http_diagnostic_call",
        role=LLMRole.DIRECT_READOUT,
        prompt_id="http_diagnostic_prompt",
        prompt_version=1,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_schema_id="http_diagnostic_response",
        response_schema_version=1,
        response_adapter=OUTPUT_CONTRACT,
        privacy_attestation=attestation,
        request_seed=42,
        provider_seed_parameter_sent=True,
        temperature=0.0,
        input_token_upper_bound=1_000,
        output_token_upper_bound=200,
        created_at=NOW,
        tool_definitions=[],
    )


def test_standard_together_error_retains_only_allowlisted_categories() -> None:
    metadata = _together_http_error_metadata(
        httpx.Response(
            400,
            json={
                "error": {
                    "message": "PRIVATE REMOTE EXPLANATION",
                    "type": "invalid_request_error",
                    "code": "context_length_exceeded",
                    "param": "response_format.json_schema",
                },
                "private_extra": "PRIVATE EXTRA VALUE",
            },
        )
    )

    assert metadata == ProviderHTTPErrorMetadata(
        http_status_code=400,
        envelope_state=ProviderHTTPErrorEnvelopeState.STANDARD,
        error_type=ProviderHTTPErrorType.INVALID_REQUEST_ERROR,
        error_code=ProviderHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
        rejected_request_field=ProviderRejectedRequestField.RESPONSE_FORMAT,
    )
    serialized = metadata.model_dump_json()
    assert "PRIVATE" not in serialized
    assert "REMOTE EXPLANATION" not in serialized
    assert "json_schema" not in serialized


def test_unknown_together_error_values_cannot_leak_remote_text() -> None:
    planted = "private_planted_remote_secret"
    metadata = _together_http_error_metadata(
        httpx.Response(
            400,
            json={
                "error": {
                    "message": planted,
                    "type": planted,
                    "code": planted,
                    "param": planted,
                    planted: planted,
                }
            },
        )
    )

    assert metadata.envelope_state is ProviderHTTPErrorEnvelopeState.STANDARD
    assert metadata.error_type is ProviderHTTPErrorType.UNRECOGNIZED
    assert metadata.error_code is ProviderHTTPErrorCode.UNRECOGNIZED
    assert (
        metadata.rejected_request_field
        is ProviderRejectedRequestField.UNRECOGNIZED
    )
    assert planted not in metadata.model_dump_json()


def test_nested_allowlisted_token_does_not_overstate_rejected_root() -> None:
    metadata = _together_http_error_metadata(
        httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "param": "private_wrapper.messages",
                }
            },
        )
    )

    assert (
        metadata.rejected_request_field
        is ProviderRejectedRequestField.UNRECOGNIZED
    )


@pytest.mark.parametrize(
    ("response", "expected_state"),
    [
        (
            httpx.Response(400, content=b""),
            ProviderHTTPErrorEnvelopeState.EMPTY,
        ),
        (
            httpx.Response(400, content=b"PRIVATE NOT JSON"),
            ProviderHTTPErrorEnvelopeState.INVALID_JSON,
        ),
        (
            httpx.Response(400, json={"error": "PRIVATE UNSTRUCTURED"}),
            ProviderHTTPErrorEnvelopeState.UNSTRUCTURED,
        ),
    ],
)
def test_nonstandard_together_error_bodies_are_only_classified(
    response: httpx.Response,
    expected_state: ProviderHTTPErrorEnvelopeState,
) -> None:
    metadata = _together_http_error_metadata(response)

    assert metadata.envelope_state is expected_state
    assert metadata.error_type is ProviderHTTPErrorType.NOT_PRESENT
    assert metadata.error_code is ProviderHTTPErrorCode.NOT_PRESENT
    assert (
        metadata.rejected_request_field
        is ProviderRejectedRequestField.NOT_PRESENT
    )
    assert "PRIVATE" not in metadata.model_dump_json()


def test_informational_http_response_can_be_safely_classified() -> None:
    metadata = _together_http_error_metadata(
        httpx.Response(101, content=b"PRIVATE NOT JSON")
    )

    assert metadata.http_status_code == 101
    assert metadata.envelope_state is ProviderHTTPErrorEnvelopeState.INVALID_JSON
    assert "PRIVATE" not in metadata.model_dump_json()


def test_http_diagnostic_rejects_a_mismatched_together_status() -> None:
    profile = load_phase4_robustness_profile(PROFILE_PATH)
    model = _candidate()
    price = _price_card(model)
    request = _request(model, price)
    runtime = ProviderBudgetRuntime(
        profile,
        ledger_id="http_mismatch_ledger",
        journal_id="http_mismatch_journal",
    )

    with pytest.raises(ValueError, match="status differs"):
        runtime.execute(
            request,
            price,
            OUTPUT_CONTRACT,
            ScriptedProviderTransport(
                [
                    ProviderTransportResult(
                        record_version=(
                            "phase4_provider_transport_result.v3"
                        ),
                        outcome=ProviderCallOutcome.PROVIDER_ERROR,
                        provider_http_error_metadata=ProviderHTTPErrorMetadata(
                            http_status_code=400,
                            envelope_state=(
                                ProviderHTTPErrorEnvelopeState.EMPTY
                            ),
                        ),
                        output_payload=None,
                        input_tokens=0,
                        output_tokens=0,
                        provider_request_id=None,
                        provider_request_sent=True,
                        provider_seed_status=(
                            ProviderSeedStatus.SENT_UNCONFIRMED
                        ),
                        latency_ms=1.0,
                        failure_code="together_http_429",
                        completed_at=NOW + timedelta(seconds=1),
                    )
                ]
            ),
            segment=BudgetSegment.QUALIFICATION,
        )
    assert [item.call_id for item in runtime.ledger_snapshot().calls] == [
        request.binding.call_id
    ]
    assert [
        item.call_id for item in runtime.journal_snapshot().finalizations
    ] == [request.binding.call_id]
    runtime.audit([model], [price])


def test_provider_error_closes_runtime_with_auditable_http_diagnostic() -> None:
    profile = load_phase4_robustness_profile(PROFILE_PATH)
    model = _candidate()
    price = _price_card(model)
    request = _request(model, price)
    runtime = ProviderBudgetRuntime(
        profile,
        ledger_id="http_diagnostic_ledger",
        journal_id="http_diagnostic_journal",
    )
    transport = ScriptedProviderTransport(
        [
            ProviderTransportResult(
                record_version="phase4_provider_transport_result.v3",
                outcome=ProviderCallOutcome.PROVIDER_ERROR,
                provider_http_error_metadata=ProviderHTTPErrorMetadata(
                    http_status_code=400,
                    envelope_state=ProviderHTTPErrorEnvelopeState.STANDARD,
                    error_type=(
                        ProviderHTTPErrorType.INVALID_REQUEST_ERROR
                    ),
                    rejected_request_field=(
                        ProviderRejectedRequestField.RESPONSE_FORMAT
                    ),
                ),
                output_payload=None,
                input_tokens=0,
                output_tokens=0,
                provider_request_id=None,
                provider_request_sent=True,
                provider_seed_status=ProviderSeedStatus.SENT_UNCONFIRMED,
                latency_ms=263.0,
                failure_code="together_http_400",
                completed_at=NOW + timedelta(seconds=1),
            )
        ]
    )

    execution = runtime.execute(
        request,
        price,
        OUTPUT_CONTRACT,
        transport,
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output is None
    assert execution.finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR
    assert execution.provider_error_diagnostic is not None
    diagnostic = execution.provider_error_diagnostic
    assert diagnostic.call_id == request.binding.call_id
    assert diagnostic.request_binding_sha256 == content_sha256(request.binding)
    assert diagnostic.finalization_sha256 == content_sha256(
        execution.finalization
    )
    assert diagnostic.http_status_code == 400
    assert diagnostic.rejected_request_field is (
        ProviderRejectedRequestField.RESPONSE_FORMAT
    )
    assert diagnostic.raw_body_omitted is True
    assert diagnostic.free_text_message_omitted is True
    ledger = runtime.ledger_snapshot()
    assert ledger.calls[0].billed_cost_microusd == 0
    assert ledger.calls[0].input_tokens == 0
    assert ledger.calls[0].output_tokens == 0
    runtime.audit([model], [price])


def test_provider_error_diagnostic_writer_is_atomic_and_idempotent(
    tmp_path: Path,
) -> None:
    profile = load_phase4_robustness_profile(PROFILE_PATH)
    model = _candidate()
    price = _price_card(model)
    request = _request(model, price)
    runtime = ProviderBudgetRuntime(
        profile,
        ledger_id="http_sidecar_ledger",
        journal_id="http_sidecar_journal",
    )
    execution = runtime.execute(
        request,
        price,
        OUTPUT_CONTRACT,
        ScriptedProviderTransport(
            [
                ProviderTransportResult(
                    record_version="phase4_provider_transport_result.v3",
                    outcome=ProviderCallOutcome.PROVIDER_ERROR,
                    provider_http_error_metadata=ProviderHTTPErrorMetadata(
                        http_status_code=400,
                        envelope_state=(
                            ProviderHTTPErrorEnvelopeState.INVALID_JSON
                        ),
                    ),
                    output_payload=None,
                    input_tokens=0,
                    output_tokens=0,
                    provider_request_id=None,
                    provider_request_sent=True,
                    provider_seed_status=(
                        ProviderSeedStatus.SENT_UNCONFIRMED
                    ),
                    latency_ms=10.0,
                    failure_code="together_http_400",
                    completed_at=NOW + timedelta(seconds=1),
                )
            ]
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    diagnostic = execution.provider_error_diagnostic
    assert diagnostic is not None
    state_path = tmp_path / "candidate_state.json"
    output_path = provider_error_diagnostic_path(state_path)

    write_provider_error_diagnostic(output_path, diagnostic)
    write_provider_error_diagnostic(output_path, diagnostic)

    assert output_path.exists()
    assert not output_path.with_suffix(f"{output_path.suffix}.tmp").exists()
    assert output_path.read_text(encoding="utf-8").endswith("\n")
    changed = diagnostic.model_copy(
        update={"failure_code": "together_http_429"}
    )
    with pytest.raises(ValueError, match="already differs"):
        write_provider_error_diagnostic(output_path, changed)
